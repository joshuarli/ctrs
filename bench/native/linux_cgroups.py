import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import signal
import socket
import struct
import time

VERSION = '2-linux-cgroup-v2-memory-stat'
ROOT = Path('/sys/fs/cgroup')
SERVICES = ('system.slice/docker.service', 'system.slice/containerd.service')


def host_cpu_ticks(path=Path('/proc/stat')):
    line = path.read_text().splitlines()[0].split()
    if line[0] != 'cpu' or len(line) < 9:
        raise ValueError('missing /proc/stat aggregate CPU counters')
    return list(map(int, line[1:9]))


def busy_cores(before, after, cpus):
    delta = [b - a for a, b in zip(before, after, strict=True)]
    total = sum(delta)
    if any(d < 0 for d in delta) or total <= 0:
        return None
    return (total - delta[3] - delta[4]) / total * cpus


def host_metadata():
    mem = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    return {'ncpu': os.cpu_count(), 'mem_total_bytes': int(mem['MemTotal'].split()[0]) * 1024,
            'resource_lane': 'native-host-no-vm-cap', 'kernel': os.uname().release,
            'cgroup_version': 2}


def cgroup(pid, proc=Path('/proc'), allow_root=False):
    lines = (proc / str(pid) / 'cgroup').read_text().splitlines()
    unified = [line[3:].lstrip('/') for line in lines if line.startswith('0::')]
    if len(unified) != 1 or (not unified[0] and not allow_root):
        raise ValueError(f'no dedicated unified cgroup for PID {pid}')
    return unified[0]


def within(child, parent):
    return child == parent or child.startswith(parent + '/')


def checked(path, root):
    target = root / path
    if target.resolve() != target.absolute() or not target.is_relative_to(root):
        raise ValueError(f'cgroup symlink or escaping path refused: {path}')
    return target


def socket_holder(endpoint, root=ROOT, proc=Path('/proc')):
    inodes = set()
    for line in (proc / 'net/unix').read_text().splitlines()[1:]:
        row = line.split(maxsplit=7)
        if (len(row) == 8 and int(row[3], 16) & 0x10000
                and Path(row[7]).resolve() == endpoint.resolve()):
            inodes.add('socket:[' + row[6] + ']')
    holders = []
    for pid in (root / SERVICES[0] / 'cgroup.procs').read_text().split():
        try:
            if any(str(fd.readlink()) in inodes for fd in (proc / pid / 'fd').iterdir()):
                if cgroup(pid, proc) != SERVICES[0]:
                    raise ValueError('socket holder moved out of docker.service')
                holders.append(int(pid))
        except (FileNotFoundError, ProcessLookupError):
            continue
    if len(holders) != 1:
        raise ValueError('cannot establish a unique docker.service holder of the listening socket')
    return holders[0]


def docker_transients(identity, root, proc):
    processes = {}
    anchors = set()

    def observe(entry):
        before = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
        if before[0] in ('Z', 'X'):
            return
        group = cgroup(entry.name, proc, allow_root=True)
        args = (entry / 'cmdline').read_bytes().split(b'\0')
        after = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
        if before[19] != after[19]:
            raise ValueError('PID identity changed during Docker ownership discovery')
        pid = int(entry.name)
        previous = processes.get(pid)
        if previous and previous['start_ticks'] != int(before[19]):
            raise ValueError('PID reused during Docker ownership discovery')
        processes[pid] = {'pid': pid, 'parent': int(before[1]), 'cgroup': group,
                          'start_ticks': int(before[19])}
        if within(group, SERVICES[0]):
            anchors.add(pid)
        if args and b'containerd-shim' in args[0] and b'moby' in args:
            if not within(group, SERVICES[1]):
                raise ValueError('Docker shim outside containerd.service')
            anchors.add(pid)

    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            observe(entry)
        except (FileNotFoundError, ProcessLookupError):
            continue
    owned = set(anchors)
    while True:
        children = {pid for pid, p in processes.items() if p['parent'] in owned}
        if children <= owned:
            break
        owned |= children

    def verify(pid, seen):
        if not pid or pid in seen:
            return False
        seen.add(pid)
        try:
            observe(proc / str(pid))
        except (FileNotFoundError, ProcessLookupError):
            return False
        if pid not in processes:
            return False
        if pid in owned or pid in anchors or verify(processes[pid]['parent'], seen):
            owned.add(pid)
            return True
        return False
    candidates = {p['cgroup'] for pid, p in processes.items() if pid in owned
                  and not any(within(p['cgroup'], service) for service in SERVICES)}
    candidates |= {str(p.relative_to(root)) for p in (root / 'system.slice').iterdir()
                   if re.fullmatch(r'(?:docker-[0-9a-f]{64}\.scope|system\.slice:docker:[a-zA-Z0-9_-]+)', p.name)}
    known = identity.setdefault('verified_transients', {})
    candidates |= {name for name in known if (root / name).exists()}
    candidates = {name for name in candidates
                  if not any(other != name and within(name, other) for other in candidates)}
    proof = {}
    for name in sorted(candidates):
        try:
            if not name:
                raise ValueError('Docker process lacks a dedicated transient cgroup')
            inode = checked(name, root).stat().st_ino
            members = [p for p in processes.values() if within(p['cgroup'], name)]
            for file in checked(name, root).rglob('cgroup.procs'):
                checked(str(file.parent.relative_to(root)), root)
                for pid in file.read_text().split():
                    verify(int(pid), set())
                    member = processes.get(int(pid))
                    if member is not None and member not in members:
                        members.append(member)
            if any(p['pid'] not in owned for p in members):
                raise ValueError('unverified process in Docker transient cgroup: ' + name)
            method = 'docker.service ancestry or verified containerd moby shim; inode continuity when empty'
            if not members and known.get(name) != inode:
                scope = re.fullmatch(r'system.slice/docker-([0-9a-f]{64})\.scope', name)
                if scope and scope[1] in docker_container_ids(identity['endpoint']):
                    method = 'container ID verified through the owned Docker socket during empty scope creation'
                elif buildkit_metadata_owner(name, identity):
                    method = 'matching OCI cgroupsPath in the owned DockerRootDir BuildKit executor metadata'
                else:
                    raise ValueError('unverified Docker transient cgroup: ' + name)
            if any(within(service, name) for service in SERVICES):
                raise ValueError('Docker process lacks a dedicated transient cgroup: ' + name)
            known[name] = inode
            proof[name] = {'inode': inode, 'members': members, 'anchors': sorted(anchors),
                           'method': method}
        except FileNotFoundError:
            continue
    identity['verified_transients'] = {name: p['inode'] for name, p in proof.items()}
    return proof


def docker_get(endpoint, path):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(2)
        sock.connect(endpoint)
        sock.sendall(('GET ' + path + ' HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n').encode())
        response = http.client.HTTPResponse(sock)
        response.begin()
        if response.status != 200:
            raise ValueError('Docker ownership API request failed')
        return json.loads(response.read())


def docker_container_ids(endpoint):
    return {entry['Id'] for entry in docker_get(endpoint, '/containers/json?all=1')}


def buildkit_metadata_owner(name, identity):
    match = re.fullmatch(r'system.slice/(system\.slice:docker:([a-zA-Z0-9_-]+))', name)
    if not match or not identity.get('docker_root_dir'):
        return False
    config = Path(identity['docker_root_dir']) / 'buildkit/executor' / match[2] / 'config.json'
    try:
        if config.resolve() != config.absolute():
            raise ValueError('symlink or escaping Docker executor metadata')
        stat = config.stat()
        if stat.st_uid != identity['docker_uid'] or stat.st_mode & 0o022:
            raise ValueError('Docker executor metadata has unsafe ownership or permissions')
        return json.loads(config.read_text()).get('linux', {}).get('cgroupsPath') == match[1]
    except FileNotFoundError:
        return False


def paths(identity, root=ROOT, transients=()):
    own = list(identity['cgroup_roots'])
    if identity['engine'] == 'dockerd':
        own += list(transients)
    other = identity.get('excluded_cgroups', [])
    if any(within(a, b) or within(b, a) for a in own for b in other):
        raise ValueError('engine cgroup sets overlap')
    if any(within(a, b) for i, a in enumerate(own) for j, b in enumerate(own) if i != j):
        raise ValueError('nested engine cgroups would be counted twice')
    for name in own:
        checked(name, root)
    return sorted(own)


def discover(engine, endpoint):
    if not (ROOT / 'cgroup.controllers').is_file():
        raise ValueError('Linux resource accounting requires cgroup v2')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(str(endpoint))
        pid, _, _ = struct.unpack('3i', sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    group = cgroup(pid)
    peer_pid = pid
    if engine == 'dockerd':
        if group != SERVICES[0]:
            pid = socket_holder(Path(endpoint))
        own = list(SERVICES)
        excluded = []
    elif engine == 'ctrs':
        parts = Path(group).parts
        units = [i for i, part in enumerate(parts) if part.endswith('.service')]
        if len(units) != 1:
            raise ValueError('ctrs must run in a dedicated delegated service')
        own = ['/'.join(parts[:units[0] + 1])]
        if len(Path(own[0]).parts) != 2 or not own[0].startswith('system.slice/'):
            raise ValueError('ctrs requires a dedicated system.slice service, outside Docker scopes')
        excluded = list(SERVICES)
    else:
        raise ValueError('Linux supports ctrs and dockerd only')
    shims = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            args = (entry / 'cmdline').read_bytes().split(b'\0')
            if args and b'containerd-shim' in args[0] and b'moby' in args:
                actual = cgroup(entry.name)
                if not within(actual, SERVICES[1]):
                    raise ValueError(f'Docker shim {entry.name} outside containerd.service: {actual}')
                shims.append({'pid': int(entry.name), 'cgroup': actual})
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    executable = Path(f'/proc/{pid}/exe')
    identity = {'sampler_version': VERSION, 'engine': engine, 'cgroup_roots': own,
                'endpoint': str(endpoint),
                'excluded_cgroups': excluded, 'socket_peer_pid': peer_pid, 'socket_holder_pid': pid,
                'executable': str(executable.resolve()),
                'executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
                'shim_verification': shims, 'method': 'socket peer and cgroup-v2 service ownership'}
    identity['root_inodes'] = {p: checked(p, ROOT).stat().st_ino for p in own}
    if engine == 'dockerd':
        identity['docker_root_dir'] = docker_get(str(endpoint), '/info')['DockerRootDir']
        if not Path(identity['docker_root_dir']).is_absolute():
            raise ValueError('DockerRootDir is not absolute')
        identity['docker_uid'] = Path(f'/proc/{pid}').stat().st_uid
    paths(identity)
    return identity


def sample(identity, root=ROOT, proc=Path('/proc')):
    result = {'sampler_version': VERSION, 'started_monotonic': time.monotonic(),
              'groups': {}, 'errors': []}
    try:
        proof = docker_transients(identity, root, proc) if identity['engine'] == 'dockerd' else {}
        result['transient_ownership'] = proof
        for name in paths(identity, root, proof):
            directory = checked(name, root)
            try:
                inode = directory.stat().st_ino
                expected = identity.get('root_inodes', {}).get(name, inode)
                if expected != inode:
                    raise ValueError(f'cgroup was replaced: {name}')
                cpu = dict(line.split() for line in (directory / 'cpu.stat').read_text().splitlines())
                memory = int((directory / 'memory.current').read_text())
                stat = dict(line.split() for line in (directory / 'memory.stat').read_text().splitlines())
                stat = {key: int(stat[key]) for key in ('anon', 'file', 'kernel')}
                if any(value < 0 for value in stat.values()):
                    raise ValueError('negative memory.stat counter')
                peak = directory / 'memory.peak'
                result['groups'][name] = {'inode': inode, 'cpu_seconds': int(cpu['usage_usec']) / 1e6,
                                          'memory_current_bytes': memory,
                                          'memory_stat': stat,
                                          'memory_anon_kernel_bytes': stat['anon'] + stat['kernel'],
                                          'memory_peak_bytes': int(peak.read_text()) if peak.exists() else None}
            except FileNotFoundError:
                if name in identity['cgroup_roots']:
                    raise
    except (OSError, ValueError, KeyError) as exc:
        result['errors'].append(str(exc))
    result['ended_monotonic'] = time.monotonic()
    result['ownership_verified'] = bool(result['groups']) and not result['errors']
    return result


def cpu_delta(before, after):
    errors = list(before['errors']) + list(after['errors'])
    total = 0.0
    for name, group in after['groups'].items():
        old = before['groups'].get(name)
        if old is not None and (old['inode'] != group['inode'] or old['cpu_seconds'] > group['cpu_seconds']):
            errors.append(f'cgroup CPU identity/counter changed: {name}')
        else:
            total += group['cpu_seconds'] - (old['cpu_seconds'] if old else 0)
    missing = set(before['groups']) - after['groups'].keys()
    if missing:
        errors.append('CPU boundary lost cgroups: ' + ', '.join(sorted(missing)))
    if not before['groups'] or not after['groups']:
        errors.append('empty cgroup coverage')
    return {'cpu_seconds': total if not errors else None, 'errors': errors,
            'before': before, 'after': after}


def phase_delta(before, after, trace):
    records = []
    if trace is not None and trace.exists():
        for line in trace.read_text().splitlines(keepends=True):
            if not line.endswith('\n'):
                continue
            record = json.loads(line)
            if (record.get('started_monotonic', -1) >= before['ended_monotonic']
                    and record.get('ended_monotonic', float('inf')) <= after['started_monotonic']):
                records.append(record)
    summary = summarize([before, *records, after])
    return {'cpu_seconds': summary['cpu_seconds_est'], 'errors': summary['resource_errors'],
            'before': before, 'after': after, 'periodic_samples': len(records),
            'method': 'service boundaries plus sampled transient lifetime CPU; lower bound for exited cgroups'}


def summarize(records):
    samples = [r for r in records if r.get('sampler_version') == VERSION and 'groups' in r]
    errors = [e for r in records for e in r.get('errors', [])]
    errors += [r['error'] for r in records if r.get('error')]
    high = {}
    first = {}
    memory = []
    peaks = []
    anon_kernel = []
    components = {key: [] for key in ('anon', 'file', 'kernel')}
    for record in samples:
        if record.get('ownership_verified') is not True:
            errors.append('full cgroup ownership not verified')
        memory.append(sum(g['memory_current_bytes'] for g in record['groups'].values()))
        anon_kernel.append(sum(g['memory_anon_kernel_bytes'] for g in record['groups'].values()))
        for key, values in components.items():
            values.append(sum(g['memory_stat'][key] for g in record['groups'].values()))
        peaks.append(sum(g['memory_peak_bytes'] or 0 for g in record['groups'].values()))
        for name, group in record['groups'].items():
            key = (name, group['inode'])
            value = group['cpu_seconds']
            if key in high and value < high[key]:
                errors.append('cgroup CPU counter regressed')
            first.setdefault(key, value if record is samples[0] else 0)
            high[key] = value
    if any('procs' in r for r in records):
        errors.append('mixed process/cgroup sampler formats')
    valid = len(samples) >= 2 and not errors and bool(high)
    return {'sampler_version': VERSION, 'samples': len(samples), 'ownership_verified': valid,
            'footprint_field': 'anon+kernel',
            'cpu_seconds_est': sum(high[k] - first[k] for k in high) if valid else None,
            'peak_memory_current_bytes': max(memory) if memory and not errors else None,
            'peak_anon_kernel_bytes': max(anon_kernel) if anon_kernel and valid else None,
            **{'peak_memory_' + key + '_bytes': max(values) if values and valid else None
               for key, values in components.items()},
            'cgroup_lifetime_memory_peak_bytes': max(peaks) if peaks else None,
            'peak_phys_footprint_bytes': None, 'resource_errors': errors,
            'method': 'cgroup v2; full live service/transient set verified; anon+kernel footprint analog; exited-scope CPU is a sampled lower bound'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ownership', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--interval', type=float, default=0.2)
    args = parser.parse_args()
    if not 0 < args.interval <= 60:
        parser.error('interval must be within (0, 60]')
    identity = json.loads(args.ownership.read_text())
    stop = None

    def terminate(*_):
        nonlocal stop
        stop = time.monotonic()

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    with args.out.open('w') as output:
        while stop is None:
            tick = time.monotonic()
            record = sample(identity)
            record.update(t=time.time(), monotonic=tick,
                          ownership_verified=bool(record['groups']) and not record['errors'])
            output.write(json.dumps(record) + '\n')
            output.flush()
            time.sleep(max(0, args.interval - (time.monotonic() - tick)))
    args.out.with_suffix('.stop.json').write_text(json.dumps({
        'sampler_version': VERSION, 'pid': os.getpid(), 'stop_requested_monotonic': stop}))


if __name__ == '__main__':
    main()
