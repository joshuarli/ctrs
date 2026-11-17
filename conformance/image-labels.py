#!/usr/bin/env python3
"""Inspect labels and adjacent config fields through an isolated engine socket."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tarfile
import tempfile
import time


def archive(name, config):
    raw = json.dumps(config, sort_keys=True).encode()
    digest = hashlib.sha256(raw).hexdigest()
    manifest = json.dumps([{'Config': digest + '.json', 'RepoTags': [name], 'Layers': []}]).encode()
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w') as tar:
        for path, data in [(digest + '.json', raw), ('manifest.json', manifest)]:
            info = tarfile.TarInfo(path)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return output.getvalue(), 'sha256:' + digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ctrs-binary', required=True, type=Path)
    args = parser.parse_args()
    binary = args.ctrs_binary.resolve(strict=True)
    repo = Path(__file__).resolve().parents[1]
    base = repo / '.work/tmp'
    base.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='image-labels-', dir=base)).resolve()
    socket = root / 'docker.sock'
    if len(os.fsencode(socket)) >= 104:
        raise ValueError('isolated socket path exceeds the Unix socket limit')
    docker = shutil.which('docker')
    if docker is None:
        raise RuntimeError('docker CLI unavailable')
    env = os.environ.copy()
    env.update(CTRS_DATA_DIR=str(root / 'data'), CTRS_STATE_DIR=str(root / 'state'),
               CTRS_SOCKET=str(socket), CTRS_CPUS='2', CTRS_MEMORY_MIB='4096',
               DOCKER_HOST='unix://' + str(socket))
    for key in ('DOCKER_CONTEXT', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'):
        env.pop(key, None)
    result = {'status': 'failed', 'checks': {}, 'cleanup_errors': [],
              'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
              'test_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    proc = None
    def command(args, data=None):
        cp = subprocess.run([docker, *args], input=data, env=env, capture_output=True, timeout=30)
        if cp.returncode:
            raise RuntimeError(f'docker {args[:2]}: {cp.returncode}: {cp.stderr.decode(errors="replace")}')
        return cp.stdout
    def interrupted(signum, _frame):
        raise RuntimeError(f'interrupted by signal {signum}')
    previous = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGINT, signal.SIGTERM)}
    print('RESULTS', root, flush=True)
    try:
        with (root / 'daemon.log').open('wb') as log:
            proc = subprocess.Popen([str(binary), 'daemon'], cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 60
            while True:
                if proc.poll() is not None:
                    raise RuntimeError(f'daemon exited {proc.returncode}')
                try:
                    command(['version'])
                    break
                except RuntimeError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('isolated daemon readiness')
                    time.sleep(.1)
            health = {'Test': ['CMD', '/bin/true'], 'Interval': 30000000000, 'Timeout': 1000000000, 'Retries': 3}
            for suffix, labels in [('present', {'dev.ctrs.campaign.run': root.name, 'description': 'owned: ✓'}), ('empty', {}), ('absent', None)]:
                name = 'ctrs-image-labels/' + suffix + ':proof'
                config = {'architecture': 'arm64', 'os': 'linux', 'rootfs': {'type': 'layers', 'diff_ids': []},
                          'config': {'Env': ['LABEL_PROOF=yes'], 'Cmd': ['/bin/true'], 'WorkingDir': '/proof',
                                     'User': '123:456', 'Healthcheck': health}}
                if labels is not None:
                    config['config']['Labels'] = labels
                data, digest = archive(name, config)
                command(['load'], data)
                actual = json.loads(command(['image', 'inspect', name]))[0]
                (root / (suffix + '.json')).write_text(json.dumps(actual, indent=2) + '\n')
                checks = {'identity': actual['Id'] == digest, 'labels': 'Labels' in actual['Config'] and actual['Config']['Labels'] == labels,
                          'healthcheck': actual['Config']['Healthcheck'] == health,
                          'env': actual['Config']['Env'] == config['config']['Env'],
                          'cmd': actual['Config']['Cmd'] == config['config']['Cmd'],
                          'working_dir': actual['Config']['WorkingDir'] == '/proof',
                          'user': actual['Config']['User'] == '123:456',
                          'rootfs': actual['RootFS'] == {'Type': 'layers', 'Layers': []}}
                result['checks'][suffix] = checks
                if not all(checks.values()):
                    raise AssertionError(f'{suffix}: {checks}')
                command(['image', 'rm', name])
            result['status'] = 'passed'
    except BaseException as exc:
        result['error'] = repr(exc)
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
                result['cleanup_errors'].append('daemon required KILL')
        if proc is not None:
            result['daemon_exit'] = proc.returncode
        if result['cleanup_errors']:
            result['status'] = 'failed'
        (root / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    print(json.dumps(result), flush=True)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
