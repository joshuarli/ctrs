#!/usr/bin/env python3
"""Detached, at-most-once supervisor for a single finite local command."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
import uuid


def receipt(path):
    path = Path(path).resolve(strict=True)
    with path.open('rb') as f:
        before = os.fstat(f.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f'not a regular file: {path}')
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
        after = os.fstat(f.fileno())
    identity = lambda s: [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]
    if identity(before) != identity(after) or identity(after) != identity(path.stat()):
        raise ValueError(f'input changed while hashing: {path}')
    return {'path': str(path), 'identity': identity(after), 'sha256': digest}


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path, value):
    tmp = path.with_name('.' + path.name + '.tmp')
    try:
        with tmp.open('x') as f:
            json.dump(value, f, sort_keys=True)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        sync_directory(path.parent)
    finally:
        if tmp.exists():
            tmp.unlink()


def process_identity(pid):
    from macos_counters import Counters
    return {'pid': pid, 'kernel_start_identity': Counters().read(pid)['kernel_start_identity'],
            'method': 'proc_pid_rusage.ri_proc_start_abstime'}


def child_done(pid):
    return os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None


def live_group_members(pgid):
    groups = subprocess.run(['/bin/ps', '-axo', 'pid=,pgid=,state='], capture_output=True, text=True, check=True, timeout=2)
    return [int(row[0]) for line in groups.stdout.splitlines()
            if len(row := line.split()) == 3 and int(row[1]) == pgid and not row[2].startswith('Z')]


def kill_owned_group(child, sig):
    try:
        os.killpg(child.pid, sig)
    except ProcessLookupError:
        pass
    except PermissionError:
        if not child_done(child.pid) or live_group_members(child.pid):
            raise


def supervise(job):
    claim = os.open(job / 'claim.lock', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(claim, 'w') as file:
        file.write(str(os.getpid()) + '\n')
        file.flush()
        os.fsync(file.fileno())
    sync_directory(job)
    spec = json.loads((job / 'spec.json').read_text())
    signal_seen = [None]
    def on_signal(signum, frame):
        if signal_seen[0] is None:
            signal_seen[0] = signum
    signals = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT, signal.SIGQUIT)
    for sig in signals:
        signal.signal(sig, on_signal)
    signal.pthread_sigmask(signal.SIG_UNBLOCK, signals)
    result = {'version': 1, 'job_id': spec['job_id'], 'state': 'error',
              'supervisor': None, 'child': None, 'cleanup_errors': [], 'cleanup_complete': True,
              'exit_code': None, 'exit_signal': None, 'supervisor_started_epoch': time.time(),
              'supervisor_started_monotonic': time.monotonic()}
    child = None
    stdout = stderr = None
    def finish_child(terminate):
        until = time.monotonic() + 5
        try:
            if terminate:
                kill_owned_group(child, signal.SIGTERM)
                grace = time.monotonic() + .5
                while not child_done(child.pid) and time.monotonic() < grace:
                    time.sleep(.02)
            kill_owned_group(child, signal.SIGKILL)
            while live_group_members(child.pid):
                if time.monotonic() >= until:
                    raise TimeoutError('owned process group remains live after SIGKILL')
                time.sleep(.02)
        except Exception as exc:
            result['cleanup_complete'] = False
            result['cleanup_errors'].append(f'{type(exc).__name__}: {exc}')
        try:
            code = child.wait(timeout=max(.01, until - time.monotonic()))
            result['exit_code'] = code if code >= 0 else None
            result['exit_signal'] = -code if code < 0 else None
        except Exception as exc:
            result['cleanup_complete'] = False
            result['cleanup_errors'].append('child wait: ' + repr(exc))
    try:
        if spec['version'] != 1:
            raise ValueError('unsupported durable job specification version')
        result['supervisor'] = process_identity(os.getpid())
        for expected in spec['inputs']:
            if receipt(expected['path']) != expected:
                raise ValueError(f"input changed: {expected['path']}")
        if signal_seen[0] is not None:
            result.update(state='interrupted', signal=signal_seen[0])
        elif time.time() >= spec['deadline_epoch'] or time.monotonic() >= spec['deadline_monotonic']:
            result.update(state='deadline')
        else:
            stdout = (job / 'stdout').open('xb')
            stderr = (job / 'stderr').open('xb')
            result['child_spawn_begin_epoch'] = time.time()
            result['child_spawn_begin_monotonic'] = time.monotonic()
            child = subprocess.Popen(spec['argv'], stdin=subprocess.DEVNULL, stdout=stdout,
                                     stderr=stderr, start_new_session=True, close_fds=True, cwd=spec['cwd'])
            result['child_spawn_end_epoch'] = time.time()
            result['child_spawn_end_monotonic'] = time.monotonic()
            try:
                result['child'] = process_identity(child.pid)
            except (OSError, ProcessLookupError):
                if not child_done(child.pid):
                    raise
            if not child_done(child.pid):
                atomic_json(job / 'running.json', {**result, 'state': 'running'})
            while (not child_done(child.pid) and not signal_seen[0]
                   and time.monotonic() < spec['deadline_monotonic'] and time.time() < spec['deadline_epoch']):
                time.sleep(.02)
            if signal_seen[0]:
                result.update(state='interrupted', signal=signal_seen[0])
            elif not child_done(child.pid):
                result.update(state='deadline')
            else:
                result.update(state='exited')
            finish_child(result['state'] != 'exited')
    except Exception as exc:
        result.update(state='error', error=f'{type(exc).__name__}: {exc}')
        if child is not None and child.returncode is None:
            finish_child(False)
    finally:
        for stream in (stdout, stderr):
            if stream is not None:
                try:
                    stream.flush()
                    os.fsync(stream.fileno())
                except OSError as exc:
                    result['cleanup_complete'] = False
                    result['cleanup_errors'].append('log synchronization: ' + repr(exc))
                finally:
                    stream.close()
        result['finished_epoch'] = time.time()
        try:
            atomic_json(job / 'status.json', result)
        finally:
            if signal_seen[0]:
                signal.signal(signal_seen[0], signal.SIG_DFL)
                os.kill(os.getpid(), signal_seen[0])


def launch(job, deadline, inputs, argv):
    if not math.isfinite(deadline) or deadline <= time.time():
        raise ValueError('deadline must be a finite future Unix timestamp')
    if not argv or not Path(argv[0]).is_absolute():
        raise ValueError('command must start with an absolute executable path')
    argv = [str(Path(argv[0]).resolve(strict=True)), *argv[1:]]
    expected = json.loads(Path(inputs).read_text())
    if not isinstance(expected, list) or not expected:
        raise ValueError('input receipt must be a nonempty array')
    if str(Path(argv[0]).resolve(strict=True)) not in [entry['path'] for entry in expected]:
        raise ValueError('input receipt must include the executable')
    for entry in expected:
        if receipt(entry['path']) != entry:
            raise ValueError(f"input changed: {entry['path']}")
    common = Path(subprocess.check_output(['git', 'rev-parse', '--git-common-dir'], text=True).strip()).resolve()
    work = (common.parent / '.work').resolve(strict=True)
    job = Path(job).absolute()
    parent = job.parent.resolve(strict=True)
    if not parent.is_relative_to(work) or job.name in ('', '.', '..'):
        raise ValueError('new job directory must be directly inside an existing directory under repository .work')
    job = parent / job.name
    job.mkdir(mode=0o700)
    supervisor_inputs = [receipt(Path(sys.executable).resolve(strict=True)), receipt(Path(__file__).resolve())]
    by_path = {entry['path']: entry for entry in expected}
    for entry in supervisor_inputs:
        if entry['path'] in by_path and by_path[entry['path']] != entry:
            raise ValueError('supervisor input changed: ' + entry['path'])
        by_path[entry['path']] = entry
    created_epoch, created_monotonic = time.time(), time.monotonic()
    spec = {'version': 1, 'created_epoch': created_epoch, 'created_monotonic': created_monotonic, 'job_id': uuid.uuid4().hex, 'deadline_epoch': deadline,
            'inputs': list(by_path.values()),
            'deadline_monotonic': created_monotonic + max(0, deadline - created_epoch),
            'argv': argv, 'cwd': os.getcwd()}
    atomic_json(job / 'spec.json', spec)
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '_supervise', str(job)],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True, close_fds=True)
    print(spec['job_id'])


def main():
    if sys.platform != 'darwin' or os.uname().machine != 'arm64':
        raise RuntimeError('native ARM64 macOS only')
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest='action', required=True)
    freeze = subs.add_parser('receipt')
    freeze.add_argument('paths', nargs='+')
    start = subs.add_parser('launch')
    start.add_argument('--job', required=True)
    start.add_argument('--deadline-epoch', type=float, required=True)
    start.add_argument('--inputs', required=True)
    start.add_argument('argv', nargs=argparse.REMAINDER)
    worker = subs.add_parser('_supervise')
    worker.add_argument('job', type=Path)
    args = parser.parse_args()
    if args.action == 'receipt':
        print(json.dumps([receipt(path) for path in args.paths], sort_keys=True))
    elif args.action == 'launch':
        argv = args.argv[1:] if args.argv[:1] == ['--'] else args.argv
        launch(args.job, args.deadline_epoch, args.inputs, argv)
    else:
        supervise(args.job)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(f'durable job: {exc}', file=sys.stderr)
        sys.exit(1)
