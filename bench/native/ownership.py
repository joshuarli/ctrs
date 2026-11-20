"""Fail-closed macOS engine ownership from open socket and disk identities."""
import hashlib
import os
from pathlib import Path
import subprocess
import time

from macos_counters import Counters


def process_table():
    cp = subprocess.run(['ps', '-axo', 'pid=,lstart=,comm='],
                        capture_output=True, text=True, check=True, timeout=5)
    result = {}
    for line in cp.stdout.splitlines():
        parts = line.split(None, 6)
        if len(parts) == 7:
            result[int(parts[0])] = {'pid': int(parts[0]),
                                    'start_identity': ' '.join(parts[1:6]),
                                    'comm': parts[6]}
    return result


def open_files(pid):
    cp = subprocess.run(['lsof', '-n', '-a', '-p', str(pid), '-F', 'pftniD'],
                        capture_output=True, text=True, timeout=10)
    if cp.returncode:
        raise RuntimeError(f'lsof {pid}: {cp.stderr}')
    files, current = [], None
    for line in cp.stdout.splitlines():
        if line.startswith('f'):
            current = {'fd': line[1:]}
            files.append(current)
        elif current is not None and line[:1] in ('t', 'n', 'i', 'D'):
            current[line[0]] = line[1:]
    return files


def artifact(record, started):
    path = Path(record['n'])
    st = path.stat()
    if str(st.st_ino) != record.get('i') or st.st_mtime >= started:
        raise ValueError(f'open artifact changed since process start: {path}')
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    # Compare identity fields only: reading the file updates st_atime on Linux.
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if identity(path.stat()) != identity(st):
        raise ValueError(f'artifact changed while hashing: {path}')
    return {'path': str(path), 'inode': st.st_ino, 'size': st.st_size,
            'sha256': digest.hexdigest()}


def current_coordinator():
    pid = os.getpid()
    proc = dict(process_table()[pid], role='fixture-coordinator')
    proc['kernel_start_identity'] = Counters().read(pid)['kernel_start_identity']
    started = time.mktime(time.strptime(proc['start_identity'], '%a %b %d %H:%M:%S %Y'))
    executable = [f for f in open_files(pid) if f['fd'] == 'txt' and f.get('n') == proc['comm']]
    if len(executable) != 1:
        raise ValueError('cannot identify loaded coordinator executable')
    proc['executable'] = artifact(executable[0], started)
    current = process_table()[pid]
    if any(current[k] != proc[k] for k in ('pid', 'comm', 'start_identity')):
        raise ValueError('coordinator identity changed during discovery')
    return proc


def discover(engine, socket_path, engine_dir):
    table = process_table()
    candidates = {pid: proc for pid, proc in table.items()
                  if ('ctrs' in proc['comm'] or 'VirtualMachine' in proc['comm']
                      if engine == 'ctrs' else '/OrbStack.app/' in proc['comm'])}
    files = {pid: open_files(pid) for pid in candidates}
    owners = [pid for pid, entries in files.items()
              if any(f.get('n') == str(socket_path) and f.get('t') == 'unix'
                     for f in entries)]
    if len(owners) != 1:
        raise ValueError(f'expected one socket owner, found {owners}')
    roles = {owners[0]: 'daemon'}
    if engine == 'ctrs':
        disk = str(Path(engine_dir) / 'data/vm/data.img')
        helpers = [pid for pid, entries in files.items()
                   if any(f.get('n') == disk for f in entries)]
        if len(helpers) != 1 or helpers[0] == owners[0]:
            raise ValueError(f'expected distinct disk-owning VM helper: {helpers}')
        roles[helpers[0]] = 'vm'
    else:
        for pid, proc in candidates.items():
            roles.setdefault(pid, 'application')
    required = []
    counters = Counters()
    for pid, role in roles.items():
        proc = dict(table[pid], role=role)
        proc["kernel_start_identity"] = counters.read(pid)["kernel_start_identity"]
        started = time.mktime(time.strptime(proc['start_identity'], '%a %b %d %H:%M:%S %Y'))
        executable = [f for f in files[pid]
                      if f['fd'] == 'txt' and f.get('n') == proc['comm']]
        if len(executable) != 1:
            raise ValueError(f'cannot identify loaded executable for {pid}')
        proc['executable'] = artifact(executable[0], started)
        if role == 'vm':
            proc['boot_assets'] = [artifact(f, started) for f in files[pid]
                                   if f.get('n', '').endswith(('/Image', '/initramfs.cpio'))]
            if len(proc['boot_assets']) != 2:
                raise ValueError('cannot identify both booted guest assets')
        required.append(proc)
    current = process_table()
    for proc in required:
        if current.get(proc['pid']) != table[proc['pid']]:
            raise ValueError('process identity changed during discovery')
    return {'schema_version': 1, 'engine': engine, 'socket': str(socket_path),
            'method': 'open Unix socket owner; ctrs VM open dedicated data disk',
            'required_processes': required}
