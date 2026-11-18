"""Pull one pinned multilayer portfolio from an independent host registry."""
import argparse
from contextlib import nullcontext
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import diagnostic_signals
import ownership
import registry_portfolio
import runner


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def deploy(engine, refs, layout, directory, run_id, contract, *, phase=nullcontext):
    project = runner.project_name(run_id, engine.name, 'W8v2')
    port = runner.free_port()
    base = f'http://127.0.0.1:{port}'
    override = directory / 'compose.json'
    save(override, {'services': {service: {'image': refs[image]} for service, image in
                               (('api', 'api'), ('db', 'postgres'), ('cache', 'redis'))}})
    def compose(args):
        return engine.sh(['compose', '-f', str(runner.COMPOSE_FILE), '-f', str(override), '-p', project, *args],
                         env_extra={'NP_API_PORT': str(port), 'NP_API_TAG': runner.API_TAG}, timeout=120)
    marked_name = project + '-marked'
    try:
        with phase('identity_verification'):
            for name, ref in refs.items():
                image = json.loads(engine.sh(['image', 'inspect', ref]).stdout)[0]
                manifest = json.loads((layout / 'blobs/sha256' / ref.rsplit('@sha256:', 1)[1]).read_text())
                config = json.loads((layout / 'blobs/sha256' / manifest['config']['digest'][7:]).read_text())
                if image['RootFS']['Layers'] != config['rootfs']['diff_ids'] or ref not in image['RepoDigests'] or image['Architecture'] != 'arm64':
                    raise ValueError(f'image identity mismatch: {name}')
                save(directory / (name + '-image.json'), image)
        with phase('stack_health'):
            compose(['up', '-d', '--no-build', '--pull', 'never'])
            if runner.wait_health(base, 60)[0] is None:
                raise RuntimeError('portfolio stack did not become healthy')
        identity = ownership.discover(engine.name, Path(engine.socket.removeprefix('unix://')), engine.dir)
        save(directory / 'running-engine.json', identity)
        if engine.name == 'ctrs' and [p['executable']['sha256'] for p in identity['required_processes'] if p['role'] == 'daemon'] != [runner.sha256_file(runner.CTRS_BIN)]:
            raise ValueError('running daemon differs from requested binary')
        with phase('load_1000'):
            load = directory / 'load.json'
            cp = subprocess.run([sys.executable, str(runner.LOAD_PY), '--url', base, '--concurrency', '4',
                '--operations', '1000', '--write-ratio', '.3', '--seed', '7', '--out', str(load)],
                capture_output=True, text=True, timeout=60)
            summary = json.loads(load.read_text())
            if cp.returncode or summary['requests_ok'] != 1000 or summary['errors']:
                raise RuntimeError('fixed application work failed')
        with phase('persistence_recovery'):
            ids = {service: compose(['ps', '-q', service]).stdout.strip() for service in ('api', 'db', 'cache')}
            writes = [json.loads(line) for line in Path(str(load) + '.writes.jsonl').read_text().splitlines()]
            rows = json.loads(engine.sh(['exec', ids['db'], 'psql', '-U', 'app', '-d', 'app', '-At', '-c',
                'SELECT json_agg(json_build_array(name,payload)) FROM items']).stdout)
            save(directory / 'persisted-items.json', rows)
            if not runner.exact_w2_items(rows, writes):
                raise ValueError('persisted application payload mismatch')
            status, _ = runner.http_json_write(base + '/records', {'key': 'w8-pinned', 'value': 'exact-portfolio-v2'})
            if status != 200:
                raise ValueError('committed write failed')
            engine.sh(['restart', ids['api']])
            if runner.wait_health(base, 60)[0] is None:
                raise RuntimeError('restarted application did not become healthy')
            status, body = runner.http_json(base + '/records/w8-pinned')
            if status != 200 or body != {'key': 'w8-pinned', 'value': 'exact-portfolio-v2', 'cache_match': True}:
                raise ValueError('committed DB/cache record did not survive application restart')
        with phase('marked_verification'):
            versions = {name: engine.sh(['exec', ids[service], *command]).stdout.strip() for name, service, command in (
                ('python', 'api', ['python', '--version']), ('postgres', 'db', ['postgres', '--version']),
                ('redis', 'cache', ['redis-server', '--version']))}
            wanted = contract['runtime_versions']
            if (versions['python'] != 'Python ' + wanted['python']
                    or versions['postgres'] != 'postgres (PostgreSQL) ' + wanted['postgres']
                    or not versions['redis'].startswith('Redis server v=' + wanted['redis'] + ' ')):
                raise ValueError('service runtime version differs from pin')
            hashes = json.loads(engine.sh(['exec', ids['api'], 'python', '-c',
                "import json,hashlib,pathlib;print(json.dumps({p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in ['/app/app.py','/app/requirements.txt']}))"]).stdout)
            if hashes != contract['api_files_sha256']:
                raise ValueError('deployed application contents differ from pin')
            javascript = (runner.FIXTURES / 'w8-v5' / 'marked-check.mjs').read_text()
            marked = json.loads(engine.sh(['run', '--rm', '--name', marked_name, '--label', 'np.w8.run=' + run_id,
                '--entrypoint', 'node', refs['marked'], '--input-type=module', '-e', javascript], timeout=90).stdout)
            if (marked['artifact_sha256'] != contract['marked_artifact_sha256']
                    or any(marked[key] != wanted[key] for key in ('node', 'npm', 'esbuild'))):
                raise ValueError('Marked artifact or tool version differs from pin')
        return {'correctness': True, 'requests_ok': summary['requests_ok'], 'reads_ok': summary['reads_ok'],
                'writes_ok': summary['writes_ok'], 'versions': versions, 'api_files_sha256': hashes, 'marked': marked}
    finally:
        with phase('owned_cleanup'):
            try:
                inspection = engine.sh(['inspect', marked_name], check=False)
                if inspection.returncode == 0:
                    container = json.loads(inspection.stdout)[0]
                    if container.get('Config', {}).get('Labels', {}).get('np.w8.run') != run_id:
                        raise RuntimeError('refusing cleanup of unowned Marked container')
                    engine.sh(['rm', '-f', marked_name])
                elif not any(message in inspection.stderr.lower() for message in ('no such object', 'no such container')):
                    raise RuntimeError('cannot establish Marked container cleanup state: ' + inspection.stderr)
            finally:
                compose(['down', '-v', '--remove-orphans'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layout', type=Path, required=True)
    parser.add_argument('--ctrs-binary', type=Path, required=True)
    parser.add_argument('--engines', default='ctrs,orbstack')
    args = parser.parse_args()
    engines = args.engines.split(',')
    if len(set(engines)) != len(engines) or any(e not in ('ctrs', 'orbstack') for e in engines):
        parser.error('distinct valid engines required')
    if sys.platform != 'darwin' or os.uname().machine != 'arm64':
        parser.error('native ARM64 macOS only')
    diagnostic_signals.install_cleanup_signals()
    runner.DOCKER = runner.find_docker()
    runner.CTRS_BIN = args.ctrs_binary.resolve()
    contract_path = runner.FIXTURES / 'w8-v5' / 'portfolio.json'
    contract = json.loads(contract_path.read_text())
    if (runner.sha256_file(runner.FIXTURES / 'w1' / 'seed.sql') != contract['seed_sql_sha256']
            or runner.sha256_file(runner.LOAD_PY) != contract['w2_load_sha256']):
        raise ValueError('application workload input differs from pin')
    portfolio = registry_portfolio.prepare_pinned_portfolio(args.layout, contract)
    run_id = 'w8-common-' + time.strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(2)
    root = runner.RESULTS / run_id
    root.mkdir(parents=True)
    save(root / 'plan.json', {'qualification_eligible': False, 'fixture_version': contract['fixture_version'],
        'reason': 'functional diagnostic; content absence, exclusivity and frozen qualification not established',
        'contract_sha256': runner.sha256_file(contract_path), 'manifests': portfolio.manifests})
    for path in (Path(__file__), Path(registry_portfolio.__file__), contract_path, runner.FIXTURES / 'w8-v5' / 'marked-check.mjs'):
        (root / path.name).write_bytes(path.read_bytes())
    print('RESULTS', root, flush=True)
    server = registry_portfolio.serve(portfolio, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05})
    try:
        thread.start()
        for name in engines:
            engine = runner.Engine(name, run_id)
            directory = root / name
            directory.mkdir()
            result = {'qualification_eligible': False, 'pulls': [], 'errors': []}
            try:
                engine.ensure_up()
                refs = {}
                for repository, digest in portfolio.manifests.items():
                    begin = len(portfolio.transfers)
                    ref = f'127.0.0.1:{server.server_port}/{repository}@{digest}'
                    cp = engine.sh(['pull', ref], timeout=180, check=False)
                    (directory / (repository.rsplit('/', 1)[1] + '-pull.log')).write_text(cp.stdout + cp.stderr)
                    result['pulls'].append({'reference': ref, 'exit': cp.returncode, 'transfers': portfolio.transfers[begin:],
                                           'pre_content_state': 'unknown; no tag deletion or cache purge'})
                    save(directory / 'result.json', result)
                    if cp.returncode:
                        raise RuntimeError('portfolio pull failed')
                    refs[repository.rsplit('/', 1)[1]] = ref
                result['deployment'] = deploy(engine, refs, args.layout, directory, run_id, contract)
                print(name, 'healthy exact portfolio', flush=True)
            except BaseException as exc:
                result['errors'].append(traceback.format_exc())
                raise
            finally:
                try:
                    engine.stop()
                finally:
                    save(directory / 'result.json', result)
    finally:
        if thread.ident is not None:
            server.shutdown()
        server.server_close()
        if thread.ident is not None:
            thread.join(timeout=5)
        save(root / 'transfers.json', portfolio.transfers)
        if thread.is_alive():
            raise RuntimeError('registry server did not stop')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
