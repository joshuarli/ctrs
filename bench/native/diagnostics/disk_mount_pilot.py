"""Reject an invalid owned disk; verify volume bytes through guest upgrade and restart."""
import argparse
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runner
import ownership
import diagnostic_signals

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--candidate-guest-dir', type=Path, required=True)
parser.add_argument('--baseline-guest-dir', type=Path, default=runner.REPO / 'guest/out')
parser.add_argument('--proof-binary', type=Path, required=True)
parser.add_argument('--ctrs-binary', type=Path, default=runner.CTRS_BIN)
args = parser.parse_args()
if sys.platform != 'darwin' or os.uname().machine != 'arm64':
    parser.error('requires native ARM64 macOS')
runner.DOCKER = runner.find_docker()
runner.CTRS_BIN = args.ctrs_binary.resolve()
binary = args.proof_binary.resolve()
with os.fdopen(os.open(binary, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW), 'rb') as source:
    before = os.fstat(source.fileno())
    if not stat.S_ISREG(before.st_mode) or before.st_size > 8 * 1024 * 1024:
        parser.error('proof binary must be a regular file no larger than 8 MiB')
    elf = source.read()
    after = os.fstat(source.fileno())
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        parser.error('proof binary changed while reading')
if elf[:6] != b'\x7fELF\x02\x01' or int.from_bytes(elf[18:20], 'little') != 183:
    parser.error('proof binary must be native ARM64 Linux ELF')
diagnostic_signals.install_cleanup_signals()
run = 'disk-guard-' + secrets.token_hex(4)
root = (runner.REPO / '.work/tmp' / run).resolve()
assets = {}
for label, directory in [('baseline', args.baseline_guest_dir.resolve()), ('candidate', args.candidate_guest_dir.resolve())]:
    assets[label] = {'directory': str(directory), **{file: runner.sha256_file(directory / file) for file in ('Image', 'initramfs.cpio')}}
    if not all(assets[label][key] for key in ('Image', 'initramfs.cpio')):
        parser.error('missing guest assets')
root.mkdir()
(root / 'driver.py').write_bytes(Path(__file__).read_bytes())
(root / 'owner.json').write_text(json.dumps({'run': run, 'purpose': __doc__, 'assets': assets,
    'proof_binary_sha256': hashlib.sha256(elf).hexdigest(), 'host_binary_sha256': runner.sha256_file(runner.CTRS_BIN)}, indent=2))
print('RESULTS', root, flush=True)
saved = {key: os.environ.get(key) for key in ('CTRS_GUEST_DIR', 'CTRS_CPUS', 'CTRS_MEMORY_MIB')}
os.environ['CTRS_CPUS'] = '2'
os.environ['CTRS_MEMORY_MIB'] = '2048'


def archive(generation):
    path = root / f'rootfs-{generation}.tar'
    with tarfile.open(path, 'w') as tar:
        entry = tarfile.TarInfo('proof')
        entry.mode = 0o755
        entry.size = len(elf)
        tar.addfile(entry, io.BytesIO(elf))
        entry = tarfile.TarInfo('state')
        entry.type = tarfile.DIRTYPE
        entry.mode = 0o755
        tar.addfile(entry)
        data = str(generation).encode()
        entry = tarfile.TarInfo('generation')
        entry.size = len(data)
        entry.mode = 0o644
        tar.addfile(entry, io.BytesIO(data))
    return str(path)


archives = {i: archive(i) for i in range(1, 4)}
volume = 'owned-persistent-proof'


def call(engine, directory, label, command):
    result = engine.sh(command, check=False, timeout=60)
    (directory / (label + '.stdout')).write_text(result.stdout)
    (directory / (label + '.stderr')).write_text(result.stderr)
    (directory / (label + '.exit')).write_text(str(result.returncode))
    return result


def run_proof(engine, directory, stage, mode, generation):
    imported = call(engine, directory, stage + '-import', ['import', archives[generation], f'np-disk-proof:{generation}'])
    if imported.returncode:
        return imported
    return call(engine, directory, stage, ['run', '--rm', '--network', 'none', '--label',
        f'dev.ctrs.campaign.run={run}', '-v', volume + ':/state', f'np-disk-proof:{generation}', '/proof', mode])


try:
    directory = root / 'bad'
    disk = directory / 'data/vm/data.img'
    disk.parent.mkdir(parents=True)
    with disk.open('xb') as stream:
        stream.write(b'owned-invalid-ext4-proof\n')
        stream.truncate(64 * 1024 * 1024)
    before = (disk.stat().st_dev, disk.stat().st_ino, disk.stat().st_size, runner.sha256_file(disk))
    os.environ['CTRS_GUEST_DIR'] = assets['candidate']['directory']
    engine = runner.Engine('ctrs', run, fresh_dir=directory)
    try:
        engine.ensure_up()
        engine.sh(['volume', 'create', '--label', f'dev.ctrs.campaign.run={run}', volume])
        result = run_proof(engine, directory, 'reject', 'write', 1)
        assert result.returncode != 0, 'invalid data disk accepted a successful write'
        assert '"ok":true' not in result.stdout
        console_path = directory / 'data/vm-console.log'
        console = console_path.read_text(errors='replace') if console_path.exists() else ''
        rejected = console + result.stderr
        assert ('mount /var/lib/ctrs' in rejected or ('data disk' in rejected and 'ext4' in rejected))
        assert 'keeping images in memory' not in rejected
        engine.sh(['version'])
    finally:
        engine.stop()
    after = (disk.stat().st_dev, disk.stat().st_ino, disk.stat().st_size, runner.sha256_file(disk))
    assert before == after, 'invalid disk identity or contents changed'
    (directory / 'result.json').write_text(json.dumps({'rejected_before_write_ack': True, 'disk_identity_contents_unchanged': True}))

    directory = root / 'valid'
    disk = directory / 'data/vm/data.img'
    disk.parent.mkdir(parents=True)
    template = (args.baseline_guest_dir.resolve() / 'data.img').resolve(strict=True)
    clonefile = ctypes.CDLL(None, use_errno=True).clonefile
    clonefile.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]
    clonefile.restype = ctypes.c_int
    # CLONE_NOFOLLOW_ANY from sys/clonefile.h; no full-copy fallback.
    if clonefile(os.fsencode(template), os.fsencode(disk), 0x0008) != 0:
        raise OSError(ctypes.get_errno(), f'clonefile {template} to {disk}')
    os.environ['CTRS_GUEST_DIR'] = assets['baseline']['directory']
    engine = runner.Engine('ctrs', run, fresh_dir=directory)
    try:
        engine.ensure_up()
        engine.sh(['volume', 'create', '--label', f'dev.ctrs.campaign.run={run}', volume])
        identity = json.loads(engine.sh(['volume', 'inspect', volume]).stdout)
        (directory / 'volume-before.json').write_text(json.dumps(identity, indent=2))
        result = run_proof(engine, directory, 'baseline-write', 'write', 1)
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout)['filesystem_magic'] == 'ef53'
        for generation, stage in [(2, 'guest-upgrade'), (3, 'candidate-restart')]:
            engine.stop()
            os.environ['CTRS_GUEST_DIR'] = assets['candidate']['directory']
            engine.ensure_up()
            result = run_proof(engine, directory, stage, 'read', generation)
            assert result.returncode == 0, result.stdout + result.stderr
            assert json.loads(result.stdout)['filesystem_magic'] == 'ef53'
            after = json.loads(engine.sh(['volume', 'inspect', volume]).stdout)
            (directory / (stage + '-volume.json')).write_text(json.dumps(after, indent=2))
            assert identity == after, 'named volume identity changed'
            (directory / (stage + '-engine.json')).write_text(json.dumps(
                ownership.discover(engine.name, Path(engine.socket.removeprefix('unix://')), engine.dir), indent=2))
        (directory / 'result.json').write_text(json.dumps({'exact_payload_survived_guest_upgrade_and_restart': True,
            'volume_identity_unchanged': True, 'host_power_loss_tested': False, 'performance_claim': False}))
    finally:
        engine.stop()
finally:
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
print('PASS', root, flush=True)
