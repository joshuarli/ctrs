#!/usr/bin/env python3
"""Check idle, VM loss recovery, and normal daemon shutdown on native macOS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]
UNEXPECTED = 'the VM stopped unexpectedly; the next request boots a new one'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def wait_for(description, predicate, seconds, process):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'daemon exited {process.returncode} while waiting for {description}')
        if predicate():
            return
        time.sleep(0.25)
    raise TimeoutError(description)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ctrs-binary', required=True, type=Path, help='signed ctrs executable')
    parser.add_argument('--portfolio-archive', required=True, type=Path, help='pinned common portfolio archive')
    args = parser.parse_args()
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        parser.error('native ARM64 macOS only')
    binary, archive = args.ctrs_binary.resolve(strict=True), args.portfolio_archive.resolve(strict=True)
    spec_path = REPO / 'bench/native/fixtures/w8-v5/portfolio.json'
    spec = json.loads(spec_path.read_text())
    archive_hash = digest(archive)
    if archive_hash != spec['archive_sha256']:
        raise ValueError('portfolio archive does not match the pinned SHA-256')
    docker = shutil.which('docker')
    if not docker:
        raise RuntimeError('docker CLI not found')
    common = Path(subprocess.run(['git', 'rev-parse', '--git-common-dir'], cwd=REPO,
                                 text=True, capture_output=True, check=True, timeout=10).stdout.strip()).resolve()
    base = common.parent / '.work/tmp'
    base.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='vm-stop-', dir=base)).resolve()
    sock = root / 'run/docker.sock'
    if len(os.fsencode(sock)) >= 104:
        raise ValueError(f'owned socket path is too long: {sock}')
    sock.parent.mkdir()
    print('RESULTS', root, flush=True)
    result = {'status': 'failed', 'daemon_exit': None, 'cleanup_errors': [],
              'sha256': {'binary': digest(binary), 'archive': archive_hash,
                         'test': digest(Path(__file__).resolve()), 'portfolio_spec': digest(spec_path),
                         'engine_source': digest(REPO / 'crates/ctrs/src/daemon/engine.rs')}}
    env = os.environ.copy()
    env.update(CTRS_DATA_DIR=str(root / 'data'), CTRS_STATE_DIR=str(root / 'state'),
               CTRS_SOCKET=str(sock), CTRS_IDLE_SECS='10', CTRS_TEST_VM_CRASH='1',
               CTRS_CPUS='2', CTRS_MEMORY_MIB='4096')
    client_env = env.copy()
    client_env.update(DOCKER_HOST='unix://' + str(sock), DOCKER_TLS_VERIFY='')
    for key in ('DOCKER_CONTEXT', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'):
        client_env.pop(key, None)
    proc = None
    log_path = root / 'state/logs/daemon.log'
    def log_text():
        return log_path.read_text(errors='replace') if log_path.exists() else ''
    def docker_run(*command, timeout=90):
        cp = subprocess.run([docker, *command], env=client_env, capture_output=True, text=True, timeout=timeout)
        if cp.returncode:
            raise RuntimeError(f'docker {command[:2]} exited {cp.returncode}: {cp.stderr}')
        return cp.stdout
    def guest():
        output = docker_run('run', '--rm', '--pull=never', '--network=none',
                            'redis:7-alpine', 'sh', '-c', 'printf vm-stop-guest-ok')
        if output.strip() != 'vm-stop-guest-ok':
            raise ValueError(f'unexpected guest output: {output!r}')
    def interrupted(signum, _frame):
        raise RuntimeError(f'interrupted by signal {signum}')
    previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        with (root / 'daemon-output.log').open('wb') as output:
            proc = subprocess.Popen([str(binary), 'daemon'], cwd=REPO, env=env, stdout=output, stderr=subprocess.STDOUT)
            def ready():
                try:
                    cp = subprocess.run([docker, 'version', '--format', '{{.Server.Version}}'], env=client_env,
                                        capture_output=True, timeout=3)
                    return cp.returncode == 0
                except subprocess.TimeoutExpired:
                    return False
            wait_for('daemon socket', ready, 120, proc)
            docker_run('load', '-i', str(archive), timeout=180)
            image = json.loads(docker_run('image', 'inspect', 'redis:7-alpine'))[0]
            if image['Architecture'] != 'arm64' or image['RootFS']['Layers'] != spec['images']['np-v5/redis']['diff_ids']:
                raise ValueError('loaded Redis image differs from pinned portfolio')
            guest()
            wait_for('idle VM stop', lambda: 'VM asleep: idle' in log_text(), 45, proc)
            if UNEXPECTED in log_text():
                raise ValueError('idle stop logged unexpected VM loss')
            guest()
            if log_text().count('VM booted') < 2:
                raise ValueError('guest did not wake after idle')
            proc.send_signal(signal.SIGUSR2)
            wait_for('unexpected VM loss', lambda: UNEXPECTED in log_text(), 45, proc)
            guest()
            if log_text().count('VM booted') < 3:
                raise ValueError('guest did not recover after VM loss')
            before = log_text().count(UNEXPECTED)
            if before != 1:
                raise ValueError(f'expected one crash diagnostic, got {before}')
            proc.send_signal(signal.SIGTERM)
            result['daemon_exit'] = proc.wait(timeout=45)
            if result['daemon_exit'] != 0:
                raise ValueError(f'daemon shutdown exit {result["daemon_exit"]}')
            after = log_text().count(UNEXPECTED)
            result.update(unexpected_before_shutdown=before, unexpected_after_shutdown=after)
            if after != before:
                raise ValueError('normal shutdown added an unexpected VM stop error')
            result['status'] = 'passed'
    except BaseException as exc:
        result['error'] = repr(exc)
    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.send_signal(signal.SIGTERM)
                result['daemon_exit'] = proc.wait(timeout=45)
            except Exception as exc:
                result['cleanup_errors'].append(repr(exc))
                proc.kill()
                result['daemon_exit'] = proc.wait(timeout=10)
        if proc is not None and result['daemon_exit'] is None:
            result['daemon_exit'] = proc.returncode
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        try:
            if proc is None or proc.poll() is not None:
                disk = root / 'data/vm/data.img'
                if disk.exists():
                    deadline = time.monotonic() + 15
                    while True:
                        opened = subprocess.run(['lsof', '-n', str(disk)], capture_output=True, text=True, timeout=10)
                        if opened.returncode == 1 and not opened.stdout and not opened.stderr:
                            break
                        if opened.returncode not in (0, 1) or opened.stderr:
                            raise RuntimeError(f'cannot verify disk ownership: {opened.stderr}')
                        if time.monotonic() >= deadline:
                            raise RuntimeError(f'owned disk still open: {opened.stdout}')
                        time.sleep(0.25)
                if (root / 'data').exists():
                    shutil.rmtree(root / 'data')
                if sock.exists():
                    raise RuntimeError('owned socket still exists after daemon exit')
                if (root / 'data').exists():
                    raise RuntimeError('owned data remains after cleanup')
        except Exception as exc:
            result['cleanup_errors'].append(repr(exc))
        if result['cleanup_errors']:
            result['status'] = 'failed'
        result['exit_status'] = 0 if result['status'] == 'passed' else 1
        (root / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2), flush=True)
    return result['exit_status']


if __name__ == '__main__':
    sys.exit(main())
