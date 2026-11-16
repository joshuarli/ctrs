"""Verify owned guest allocation and PostgreSQL relation ENOSPC recovery."""
import argparse
import json
import os
from pathlib import Path
import secrets
import select
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ci_jobs
import diagnostic_signals
import ownership
import resource_cells
import runner
from diagnostics import storage_space_guest as guest

def relation_enospc(returncode, stderr):
    return (returncode != 0 and ('no space left on device' in stderr.lower() or '53100' in stderr)
            and 'pgsql_tmp' not in stderr and ('base/' in stderr or 'pg_wal' in stderr))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=guest.STAGES, required=True, help='64MiB unwritten preflight or bounded relation ENOSPC test')
    parser.add_argument('--modes', choices=('fsync', 'full', 'both'), default='both', help='disclosed binary variants to exercise')
    parser.add_argument('--fsync-binary', type=Path, required=True, help='signed baseline release executable')
    parser.add_argument('--full-binary', type=Path, required=True, help='signed Full-sync candidate executable')
    parser.add_argument('--portfolio-archive', type=Path, required=True, help='pinned common service archive')
    if len(sys.argv) == 1:
        parser.print_help()
        return
    args = parser.parse_args()
    if sys.platform != 'darwin' or os.uname().machine != 'arm64':
        parser.error('native ARM64 macOS only')
    modes = ('fsync', 'full') if args.modes == 'both' else (args.modes,)
    manifest = runner.validate_manifest()
    diagnostic_signals.install_cleanup_signals()
    runner.DOCKER = runner.find_docker()
    run = 'space-' + secrets.token_hex(4)
    root = (runner.REPO / '.work/tmp' / run).resolve()
    if len(os.fsencode(str(root / 'fsync/e/run/docker.sock'))) >= 104:
        parser.error('run from the main checkout so the isolated socket path fits')
    root.mkdir()
    (root / 'driver.py').write_bytes(Path(__file__).read_bytes())
    (root / 'guest.py').write_bytes(Path(__file__).with_name('storage_space_guest.py').read_bytes())
    (root / 'hypothesis.md').write_bytes(Path(__file__).with_name('storage-space.md').read_bytes())
    spec = json.loads((runner.FIXTURES / 'w8-v2/portfolio.json').read_text())
    archive = args.portfolio_archive.resolve()
    if not (runner.sha256_file(archive) == spec['archive_sha256']):
        raise ValueError("diagnostic validation failed: runner.sha256_file(archive) == spec['archive_sha256']")
    if not (shutil.disk_usage(root).free >= 2 << 30):
        raise ValueError('diagnostic validation failed: shutil.disk_usage(root).free >= 2 << 30')
    assets = {'fsync': args.fsync_binary.resolve(), 'full': args.full_binary.resolve()}
    def save(path, value):
        Path(path).write_text(json.dumps(value, indent=2) + '\n')
    save(root / 'plan.json', {'run': run, 'stage': args.stage, 'modes': modes,
        'binary_sha256': {mode: runner.sha256_file(assets[mode]) for mode in modes},
        'manifest': manifest, 'guest': runner.guest_provenance(), 'archive_sha256': spec['archive_sha256'],
        'helper_sha256': runner.sha256_file(root / 'guest.py'), 'driver_sha256': runner.sha256_file(root / 'driver.py'),
        'qualification_eligible': False, 'required_host_free_bytes': 2 << 30,
        'host_reservation_growth_budget_bytes': (8 if args.stage == 'allocation' else 512) << 20,
        'scope': 'owned guest filesystem allocation/ENOSPC; no timing, host-full-disk, power-loss or exclusive APFS reclaim claim'})
    print('RESULTS', root, flush=True)
    os.environ.update(CTRS_CPUS='2', CTRS_MEMORY_MIB='4096')
    boot_assets = None
    for mode in modes:
        directory = root / mode; directory.mkdir()
        runner.CTRS_BIN = assets[mode]
        engine = runner.Engine('ctrs', run, fresh_dir=directory / 'e')
        project = runner.project_name(run + mode, 'ctrs', 'space')
        helper = project + '-fill'; volume = project + '-fill'
        port = runner.free_port(); base = f'http://127.0.0.1:{port}'
        holder = log = None
        disk = engine.dir / 'data/vm/data.img'
        result = {'correctness': False, 'errors': [], 'cleanup_errors': [], 'qualification_eligible': False}
        def compose(command):
            return engine.sh(['compose', '-f', str(runner.COMPOSE_FILE), '-p', project, *command],
                             env_extra={'NP_API_PORT': str(port), 'NP_API_TAG': runner.API_TAG}, timeout=120)
        def frame(event):
            if not select.select([holder.stdout], [], [], 60)[0]:
                raise TimeoutError('reservation frame deadline')
            row = json.loads(holder.stdout.readline())
            save(directory / 'last-frame.json', row)
            if row['event'] != event:
                raise ValueError('unexpected reservation event: ' + repr(row))
            return row
        def records():
            db = compose(['ps', '-q', 'db']).stdout.strip()
            cp = engine.sh(['exec', db, 'psql', '-v', 'ON_ERROR_STOP=1', '-U', 'app', '-d', 'app', '-At', '-c',
                'SELECT json_object_agg(key,value) FROM records'], timeout=15)
            return json.loads(cp.stdout)
        def release():
            if holder and holder.poll() is None:
                holder.stdin.write('RELEASE\n'); holder.stdin.flush(); holder.stdin.close()
                saved = frame('released'); save(directory / 'released.json', saved)
                code = holder.wait(timeout=10)
                result['holder_exit'] = code
                if code:
                    raise RuntimeError('reservation helper failed')
                return saved
        try:
            engine.ensure_up()
            engine.sh(['load', '-i', str(archive)], timeout=180)
            for name, reference in (('api', 'np-fixture-api:' + runner.API_TAG), ('postgres', 'postgres:17-alpine'), ('redis', 'redis:7-alpine')):
                installed = json.loads(engine.sh(['image', 'inspect', reference]).stdout)[0]
                if not (installed['Architecture'] == 'arm64' and installed['RootFS']['Layers'] == spec['images']['np-v2/' + name]['diff_ids']):
                    raise ValueError("diagnostic validation failed: installed['Architecture'] == 'arm64' and installed['RootFS']['Layers'] == spec['images']['np-v2/' + name]['diff_ids']")
            compose(['up', '-d', '--no-build', '--pull', 'never'])
            if not (runner.wait_health(base, 60)[0]):
                raise ValueError('diagnostic validation failed: runner.wait_health(base, 60)[0]')
            db = compose(['ps', '-q', 'db']).stdout.strip()
            settings = json.loads(engine.sh(['exec', db, 'psql', '-U', 'app', '-d', 'app', '-At', '-c',
                "SELECT json_build_object('fsync',current_setting('fsync'),'synchronous_commit',current_setting('synchronous_commit'),'full_page_writes',current_setting('full_page_writes'))"]).stdout)
            save(directory / 'postgres-settings.json', settings)
            if not (set(settings.values()) == {'on'}):
                raise ValueError("diagnostic validation failed: set(settings.values()) == {'on'}")
            expected = {}
            for index in range(100):
                key, value = f'committed-{index}', f'exact-{index}'
                status, body = runner.http_json_write(base + '/records', {'key': key, 'value': value})
                if not (status == 200 and body == {'stored': key}):
                    raise ValueError("diagnostic validation failed: status == 200 and body == {'stored': key}")
                expected[key] = value
            save(directory / 'acknowledged-before.json', expected)
            if not (records() == expected):
                raise ValueError('diagnostic validation failed: records() == expected')
            db_volume = json.loads(engine.sh(['volume', 'inspect', project + '_dbdata']).stdout)
            save(directory / 'volume-before.json', db_volume)
            engine.sh(['volume', 'create', '--label', 'dev.ctrs.campaign.run=' + run, volume])
            engine.sh(['run', '-d', '--pull=never', '--name', helper, '--label', 'dev.ctrs.campaign.run=' + run,
                       '--privileged', '--network', 'none', '-v', volume + ':/fill', '-v', str(root / 'guest.py') + ':/guest.py:ro',
                       'np-fixture-api:' + runner.API_TAG, 'python', '-c', 'import time;time.sleep(300)'])
            identity = ownership.discover('ctrs', Path(engine.socket.removeprefix('unix://')), engine.dir)
            save(directory / 'running-engine.json', identity)
            actual_boot = {Path(asset['path']).name: asset['sha256'] for process in identity['required_processes']
                           if process['role'] == 'vm' for asset in process['boot_assets']}
            if boot_assets is None:
                boot_assets = actual_boot
            elif actual_boot != boot_assets:
                raise ValueError('running boot assets differ between binary variants')
            if not ([p['executable']['sha256'] for p in identity['required_processes'] if p['role'] == 'daemon'] == [runner.sha256_file(runner.CTRS_BIN)]):
                raise ValueError("diagnostic validation failed: [p['executable']['sha256'] for p in identity['required_processes'] if p['role'] == 'daemon'] == [runner.sha256_file(runner.CTRS_BIN)]")
            before = resource_cells.allocation_snapshot([disk]); save(directory / 'allocation-before.json', before)
            if not (before['status'] == 'ok' and before['files'][0]['filesystem_free_bytes'] >= 2 << 30):
                raise ValueError("diagnostic validation failed: before['status'] == 'ok' and before['files'][0]['filesystem_free_bytes'] >= 2 << 30")
            log = (directory / 'holder.stderr').open('wb')
            holder = subprocess.Popen([runner.DOCKER, 'exec', '-i', '--privileged', helper, 'python', '-u', '/guest.py', args.stage],
                                      env=engine.env(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True)
            reserved = frame('reserved'); save(directory / 'reserved.json', reserved)
            after = resource_cells.allocation_snapshot([disk]); save(directory / 'allocation-reserved.json', after)
            growth = after['allocated_bytes'] - before['allocated_bytes']
            budget = (8 if args.stage == 'allocation' else 512) << 20
            if not (after['status'] == 'ok' and growth <= budget):
                raise ValueError('host reservation allocation budget exceeded')
            if args.stage == 'enospc':
                if not (reserved['after']['available_bytes'] <= guest.LEAVE_AVAILABLE_BYTES):
                    raise ValueError("diagnostic validation failed: reserved['after']['available_bytes'] <= guest.LEAVE_AVAILABLE_BYTES")
                sql = "BEGIN; SET LOCAL work_mem='128MB'; CREATE TABLE space_probe(payload text); INSERT INTO space_probe SELECT string_agg(md5(g::text||clock_timestamp()::text),'') FROM generate_series(1,1048576) g; COMMIT;"
                cp = engine.sh(['exec', db, 'psql', '-v', 'ON_ERROR_STOP=1', '-v', 'VERBOSITY=verbose', '-U', 'app', '-d', 'app', '-c', sql], timeout=30, check=False)
                save(directory / 'enospc-command.json', {'returncode': cp.returncode, 'stdout': cp.stdout, 'stderr': cp.stderr})
                if not relation_enospc(cp.returncode, cp.stderr):
                    raise ValueError('authoritative relation/WAL ENOSPC not observed')
            released = release()
            if released is None or any(released[key] != reserved['before'][key] for key in ('fs_uuid', 'volume_inode')):
                raise ValueError('filesystem or fill-volume identity changed')
            if released['available_bytes'] < reserved['before']['available_bytes'] - (64 << 20):
                raise ValueError('guest capacity did not return after reservation release')
            save(directory / 'allocation-released.json', resource_cells.allocation_snapshot([disk]))
            compose(['up', '-d', '--no-build', '--pull', 'never'])
            if not (runner.wait_health(base, 60)[0]):
                raise ValueError('diagnostic validation failed: runner.wait_health(base, 60)[0]')
            if not (records() == expected):
                raise ValueError('acknowledged prefix differs after release/recovery')
            if args.stage == 'enospc':
                for index in range(100, 110):
                    key, value = f'committed-{index}', f'exact-{index}'
                    status, body = runner.http_json_write(base + '/records', {'key': key, 'value': value})
                    if not (status == 200 and body == {'stored': key}):
                        raise ValueError("diagnostic validation failed: status == 200 and body == {'stored': key}")
                    expected[key] = value
                if not (records() == expected):
                    raise ValueError('diagnostic validation failed: records() == expected')
            if not (json.loads(engine.sh(['volume', 'inspect', project + '_dbdata']).stdout) == db_volume):
                raise ValueError("diagnostic validation failed: json.loads(engine.sh(['volume', 'inspect', project + '_dbdata']).stdout) == db_volume")
            save(directory / 'acknowledged-after.json', expected)
            result.update(correctness=True, exact_records=len(expected), host_reservation_growth_bytes=growth,
                          guest_reserved_bytes=reserved['after']['reservation_allocated'], unwritten_extents=reserved['extents'])
        except BaseException as exc:
            result['errors'].append(repr(exc))
            raise
        finally:
            try:
                release()
            except Exception as exc:
                result['cleanup_errors'].append('reservation: ' + repr(exc))
            if holder and holder.poll() is None:
                holder.stdin.close() if holder.stdin and not holder.stdin.closed else None
                try: holder.wait(timeout=95)
                except subprocess.TimeoutExpired:
                    holder.kill(); holder.wait(timeout=5)
                    result['cleanup_errors'].append('reservation helper required kill')
            try:
                ci_jobs.cleanup(engine, helper, run)
                inspected = json.loads(engine.sh(['volume', 'inspect', volume]).stdout)[0]
                if not (inspected['Labels']['dev.ctrs.campaign.run'] == run):
                    raise ValueError("diagnostic validation failed: inspected['Labels']['dev.ctrs.campaign.run'] == run")
                engine.sh(['volume', 'rm', volume])
            except Exception as exc:
                result['cleanup_errors'].append('fill fixture: ' + repr(exc))
            try:
                compose(['down', '-v', '--remove-orphans'])
            except Exception as exc:
                result['cleanup_errors'].append('stack: ' + repr(exc))
            if disk.exists(): save(directory / 'allocation-cleanup.json', resource_cells.allocation_snapshot([disk]))
            engine.stop()
            if log: log.close()
            if result['cleanup_errors']: result['correctness'] = False
            save(directory / 'result.json', result)
        if not (result['correctness']):
            raise ValueError("diagnostic validation failed: result['correctness']")
    print('PASS', root)


if __name__ == '__main__':
    main()
