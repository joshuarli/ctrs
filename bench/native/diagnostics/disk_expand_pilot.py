"""Verify an owned legacy-size ext4 disk and real database through automatic expansion."""
import argparse
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import diagnostic_signals
import ownership
import resource_cells
import runner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-binary', 'candidate-binary', 'baseline-guest-dir', 'candidate-guest-dir', 'portfolio-archive', 'proof-binary'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin' or os.uname().machine != 'arm64':
        parser.error('native ARM64 macOS only')
    diagnostic_signals.install_cleanup_signals()
    runner.DOCKER = runner.find_docker()
    spec = json.loads((runner.FIXTURES / 'w8-v6/portfolio.json').read_text())
    if runner.sha256_file(args.portfolio_archive) != spec['archive_sha256']:
        parser.error('common portfolio archive differs from pin')
    elf = args.proof_binary.read_bytes()
    if len(elf) > 8 * 1024 * 1024 or elf[:6] != b'\x7fELF\x02\x01' or int.from_bytes(elf[18:20], 'little') != 183:
        parser.error('proof must be a bounded native ARM64 Linux binary')
    run = 'disk-expand-' + secrets.token_hex(4)
    root = (Path.cwd() / '.work/tmp' / run).resolve()
    if len(str(root / 'engine/run/docker.sock').encode()) >= 104:
        parser.error('run from the main checkout so the owned socket path fits')
    root.mkdir()
    (root / 'driver.py').write_bytes(Path(__file__).read_bytes())
    engine_dir = root / 'engine'
    disk = engine_dir / 'data/vm/data.img'
    disk.parent.mkdir(parents=True)
    with disk.open('xb') as stream:
        stream.truncate(64 << 30)
    archive = root / 'proof.tar'
    with tarfile.open(archive, 'w') as stream:
        info = tarfile.TarInfo('proof'); info.mode = 0o755; info.size = len(elf)
        stream.addfile(info, io.BytesIO(elf))
        info = tarfile.TarInfo('state'); info.mode = 0o755; info.type = tarfile.DIRTYPE
        stream.addfile(info)
    assets = {}
    for label in ('baseline', 'candidate'):
        binary = getattr(args, label + '_binary').resolve()
        guest = getattr(args, label + '_guest_dir').resolve()
        assets[label] = {'binary': str(binary), 'binary_sha256': runner.sha256_file(binary),
                         'guest': str(guest), 'Image': runner.sha256_file(guest / 'Image'),
                         'initramfs': runner.sha256_file(guest / 'initramfs.cpio')}
        if not all(assets[label].values()):
            parser.error('missing host or guest input')
    def save(name, value):
        (root / name).write_text(json.dumps(value, indent=2) + '\n')
    save('plan.json', {'kind': __doc__, 'assets': assets, 'old_bytes': 64 << 30, 'target_bytes': 1 << 40,
        'metadata_allocation_budget_bytes': 512 << 20, 'required_initial_host_free_bytes': 1 << 30,
        'portfolio_archive_sha256': spec['archive_sha256'], 'qualification_eligible': False,
        'power_loss_tested': False, 'cpu_count': 2, 'memory_mib': 4096,
        'allocation_module_sha256': runner.sha256_file(Path(resource_cells.__file__))})
    print('RESULTS', root, flush=True)
    tools = runner.Engine('orbstack', run)
    tool_name = run + '-tools'
    compiler = 'gcc@sha256:c5be79575f0886a3f8bdcf7cacc7de808ed56089975d43f54fda739a1d183d6c'
    def tool(label, command):
        cp = tools.sh(['run', '--rm', '--name', tool_name, '--label', 'dev.ctrs.campaign.run=' + run,
            '--pull=never', '-v', str(disk.parent) + ':/out', compiler, *command], timeout=60, check=False)
        (root / (label + '.stdout')).write_text(cp.stdout)
        (root / (label + '.stderr')).write_text(cp.stderr)
        if cp.returncode:
            raise RuntimeError('filesystem tool failed: ' + cp.stderr)
        return cp.stdout
    def fs_metadata(label):
        text = tool(label, ['dumpe2fs', '-h', '/out/data.img'])
        expr = 'split("\\n") | map(capture("^(?<key>Filesystem UUID|Block count|Block size|Filesystem features):[[:space:]]*(?<value>.*)$")?) | from_entries'
        cp = subprocess.run(['jaq', '-R', '-s', expr], input=text, capture_output=True, text=True, check=True)
        value = json.loads(cp.stdout)
        if 'Filesystem UUID' not in value or 'Block count' not in value:
            raise ValueError('missing filesystem identity')
        save(label + '.json', value)
        return value
    os.environ['CTRS_CPUS'] = '2'
    os.environ['CTRS_MEMORY_MIB'] = '4096'
    project = runner.project_name(run, 'ctrs', 'upgrade')
    port = runner.free_port()
    base = f'http://127.0.0.1:{port}'
    env = {'NP_API_PORT': str(port), 'NP_API_TAG': runner.API_TAG}
    sentinel = 'owned-expand-sentinel'
    engine = None
    result = {'errors': []}
    def compose(command):
        return engine.sh(['compose', '-f', str(runner.COMPOSE_FILE), '-p', project, *command], env_extra=env, timeout=120)
    def proof(mode, label):
        name = run + '-' + label
        try:
            cp = engine.sh(['run', '--rm', '--name', name, '--label', 'dev.ctrs.campaign.run=' + run,
                '--privileged', '--network', 'none', '-v', sentinel + ':/state', 'np-disk-expand:proof', '/proof', mode],
                timeout=60, check=False)
            (root / (label + '.stdout')).write_text(cp.stdout)
            (root / (label + '.stderr')).write_text(cp.stderr)
            if cp.returncode:
                raise RuntimeError('volume proof failed: ' + cp.stderr)
            return json.loads(cp.stdout)
        finally:
            item = engine.sh(['inspect', name], check=False)
            if item.returncode == 0:
                if json.loads(item.stdout)[0]['Config']['Labels'].get('dev.ctrs.campaign.run') != run:
                    raise RuntimeError('volume proof cleanup ownership mismatch')
                engine.sh(['rm', '-f', name])
    def query_items():
        db = compose(['ps', '-q', 'db']).stdout.strip()
        return json.loads(engine.sh(['exec', db, 'psql', '-U', 'app', '-d', 'app', '-At', '-c',
            'SELECT json_agg(json_build_array(name,payload)) FROM items']).stdout)
    try:
        tools.ensure_up()
        tool('mkfs', ['mke2fs', '-q', '-t', 'ext4', '-F', '-b', '4096', '-m', '0', '-E',
                      'lazy_itable_init=1,lazy_journal_init=1', '/out/data.img'])
        before_fs = fs_metadata('filesystem-before')
        runner.CTRS_BIN = Path(assets['baseline']['binary'])
        os.environ['CTRS_GUEST_DIR'] = assets['baseline']['guest']
        engine = runner.Engine('ctrs', run, fresh_dir=engine_dir)
        engine.ensure_up()
        engine.sh(['load', '-i', str(args.portfolio_archive.resolve())], timeout=180)
        engine.sh(['import', str(archive), 'np-disk-expand:proof'])
        engine.sh(['volume', 'create', '--label', 'dev.ctrs.campaign.run=' + run, sentinel])
        old_geometry = proof('write', 'baseline-write')
        if old_geometry['device_bytes'] != 64 << 30:
            raise ValueError('baseline was not the declared legacy capacity')
        compose(['up', '-d', '--no-build', '--pull', 'never'])
        if runner.wait_health(base, 60)[0] is None:
            raise RuntimeError('baseline application readiness')
        load = root / 'load.json'
        cp = subprocess.run([sys.executable, str(runner.LOAD_PY), '--url', base, '--concurrency', '4',
            '--operations', '5000', '--write-ratio', '.3', '--seed', '7', '--out', str(load)], capture_output=True, text=True, timeout=90)
        summary = json.loads(load.read_text())
        if cp.returncode or summary['requests_ok'] != 5000 or summary['errors']:
            raise RuntimeError('baseline fixed application work failed')
        writes = [json.loads(line) for line in Path(str(load) + '.writes.jsonl').read_text().splitlines()]
        before_rows = query_items()
        if not runner.exact_w2_items(before_rows, writes):
            raise ValueError('baseline exact persisted state mismatch')
        save('items-before.json', before_rows)
        status, _ = runner.http_json_write(base + '/records', {'key': 'disk-expand', 'value': 'exact-authoritative-data'})
        if status != 200:
            raise ValueError('baseline committed DB/cache record failed')
        db_volume = project + '_dbdata'
        before_volumes = json.loads(engine.sh(['volume', 'inspect', sentinel, db_volume]).stdout)
        save('volumes-before.json', before_volumes)
        save('engine-before.json', ownership.discover('ctrs', Path(engine.socket.removeprefix('unix://')), engine.dir))
        compose(['stop'])
        engine.stop()
        before_allocation = resource_cells.allocation_snapshot([disk])
        save('allocation-before.json', before_allocation)
        before_inode = disk.stat().st_ino
        runner.CTRS_BIN = Path(assets['candidate']['binary'])
        os.environ['CTRS_GUEST_DIR'] = assets['candidate']['guest']
        engine.ensure_up()
        geometry = proof('read', 'candidate-read')
        if geometry['device_bytes'] != 1 << 40 or geometry['statvfs_blocks_after'] <= old_geometry['statvfs_blocks_after']:
            raise ValueError('candidate did not expand actual device/filesystem capacity')
        save('engine-candidate.json', ownership.discover('ctrs', Path(engine.socket.removeprefix('unix://')), engine.dir))
        compose(['up', '-d', '--no-build', '--pull', 'never'])
        if runner.wait_health(base, 60)[0] is None:
            raise RuntimeError('upgraded application readiness')
        after_rows = query_items()
        if not runner.exact_w2_items(after_rows, writes):
            raise ValueError('acknowledged application state did not survive expansion')
        save('items-after.json', after_rows)
        status, body = runner.http_json(base + '/records/disk-expand')
        if status != 200 or body != {'key': 'disk-expand', 'value': 'exact-authoritative-data', 'cache_match': True}:
            raise ValueError('committed DB/cache record did not survive: ' + repr(body))
        if json.loads(engine.sh(['volume', 'inspect', sentinel, db_volume]).stdout) != before_volumes:
            raise ValueError('named-volume identity changed')
        compose(['stop'])
        engine.stop()
        after_allocation = resource_cells.allocation_snapshot([disk])
        save('allocation-after.json', after_allocation)
        after_fs = fs_metadata('filesystem-after')
        if after_fs['Filesystem UUID'] != before_fs['Filesystem UUID'] or int(after_fs['Block count']) * int(after_fs['Block size']) != 1 << 40:
            raise ValueError('filesystem UUID or geometry differs')
        increase = after_allocation['allocated_bytes'] - before_allocation['allocated_bytes']
        if increase > 512 << 20 or disk.stat().st_ino != before_inode:
            raise ValueError('allocation or inode-preservation budget failed')
        engine.ensure_up()
        proof('read', 'candidate-restart-read')
        if json.loads(engine.sh(['volume', 'inspect', sentinel, db_volume]).stdout) != before_volumes:
            raise ValueError('volume identity changed after subsequent restart')
        result.update(correctness=True, successful_operations=summary['requests_ok'], reads=summary['reads_ok'],
            writes=summary['writes_ok'], exact_database_and_cache_survived=True, filesystem_uuid_unchanged=True,
            named_volumes_unchanged=True, disk_inode_unchanged=True, allocated_increase_bytes=increase,
            power_loss_tested=False, qualification_eligible=False, retained='owned stopped state for audit; no shared daemon/state cleanup')
    except BaseException as exc:
        result['errors'].append(repr(exc))
        raise
    finally:
        try:
            if engine is not None:
                engine.stop()
        finally:
            item = tools.sh(['inspect', tool_name], check=False)
            if item.returncode == 0:
                if json.loads(item.stdout)[0]['Config']['Labels'].get('dev.ctrs.campaign.run') != run:
                    raise RuntimeError('filesystem tool cleanup ownership mismatch')
                tools.sh(['rm', '-f', tool_name])
            save('result.json', result)
    print('PASS', root, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
