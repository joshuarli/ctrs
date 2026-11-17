"""Owned fixed-work baseline application during W8 pulls."""
from contextlib import contextmanager
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import runner
from diagnostics.registry_pilot import save

CLIENT = Path(__file__).with_name('w8_load_guest.py')


def coverage(intervals, completions):
    result = []
    for interval in intervals:
        values = sorted(row['latency_ms'] for row in completions
            if interval['begin_monotonic'] <= row['completion_monotonic'] <= interval['end_monotonic'])
        def pct(q):
            return values[min(len(values) - 1, round(q * (len(values) - 1)))] if values else None
        result.append({**interval, 'completion_count': len(values),
            'completion_latency_ms': {'p50': pct(.5), 'p95': pct(.95), 'p99': pct(.99),
                                      'max': values[-1] if values else None}})
    return result


def require_coverage(intervals, completions):
    cells = coverage(intervals, completions)
    if not cells or any(not cell['completion_count'] for cell in cells):
        raise ValueError('pull interval lacks completion overlap')
    return cells


def verify_payload(rows, client, completions):
    counts = client['counts']
    writes = client['writes']
    valid_trace = (len(completions) == 50000 and
        all(row.get('sequence') == index and
            all(isinstance(row.get(k), (int, float)) and math.isfinite(row[k]) and row[k] >= 0
                for k in ('completion_monotonic', 'latency_ms'))
            for index, row in enumerate(completions)) and
        all(a['completion_monotonic'] <= b['completion_monotonic']
            for a, b in zip(completions, completions[1:])))
    if (counts['errors'] or client['errors'] or counts['reads'] + counts['writes'] != 50000
            or not valid_trace or len(writes) != counts['writes']
            or len({item['name'] for item in writes}) != len(writes)
            or not runner.exact_w2_items(rows, writes)):
        raise ValueError('fixed client work or exact persisted payload mismatch')


@contextmanager
def baseline(engine, directory, run, contract, phase):
    project = runner.project_name(run, engine.name, 'w8underpull')
    port = runner.free_port()
    base = f'http://127.0.0.1:{port}'
    override = directory / 'under-pull-compose.json'
    process = None
    stdout = stderr = None
    intervals = []
    started = False
    state = {'project': project, 'port': port, 'intervals': intervals,
             'network': project + '_appnet', 'volume': project + '_dbdata'}
    def compose(args):
        return engine.sh(['compose', '-f', str(runner.COMPOSE_FILE), '-f', str(override), '-p', project, *args],
            env_extra={'NP_API_PORT': str(port), 'NP_API_TAG': runner.API_TAG}, timeout=120)
    try:
        with phase('under_pull_setup'):
            if (runner.sha256_file(runner.LOAD_PY) != contract['w2_load_sha256'] or
                    runner.sha256_file(runner.FIXTURES / 'w1/seed.sql') != contract['seed_sql_sha256']):
                raise ValueError('application workload inputs differ from pin')
            state['hashes'] = {'w2_load': runner.sha256_file(runner.LOAD_PY),
                'seed_sql': runner.sha256_file(runner.FIXTURES / 'w1/seed.sql'),
                'client': runner.sha256_file(CLIENT), 'controller': runner.sha256_file(Path(__file__)),
                'contract': runner.sha256_file(runner.FIXTURES / 'w8-v2/portfolio.json'),
                'compose': runner.sha256_file(runner.COMPOSE_FILE)}
            identity_kind = {'ctrs': 'config', 'orbstack': 'manifest'}[engine.name]
            state['baseline_image_id_kind'] = identity_kind
            refs = {name: contract['images']['np-v2/' + name][identity_kind] for name in ('api', 'postgres', 'redis')}
            images = {}
            for name, ref in refs.items():
                image = json.loads(engine.sh(['image', 'inspect', ref]).stdout)[0]
                pin = contract['images']['np-v2/' + name]
                if image['Id'] != ref or image['RootFS']['Layers'] != pin['diff_ids'] or image['Architecture'] != 'arm64':
                    raise ValueError('baseline image differs from pin: ' + name)
                images[name] = image
            state['images'] = images
            save(override, {'services': {service: {'image': images[name]['Id']} for service, name in
                (('api', 'api'), ('db', 'postgres'), ('cache', 'redis'))}})
            started = True
            compose(['up', '-d', '--no-build', '--pull', 'never'])
            if runner.wait_health(base, 60)[0] is None:
                raise RuntimeError('baseline stack did not become healthy')
            ids = {service: compose(['ps', '-q', service]).stdout.strip() for service in ('api', 'db', 'cache')}
            if any(not item or '\n' in item for item in ids.values()):
                raise ValueError('ambiguous baseline service identity')
            state['containers'] = ids
            hashes = json.loads(engine.sh(['exec', ids['api'], 'python', '-c',
                "import json,hashlib,pathlib;print(json.dumps({p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in ['/app/app.py','/app/requirements.txt']}))"]).stdout)
            state['api_files_sha256'] = hashes
            if hashes != contract['api_files_sha256']:
                raise ValueError('baseline application contents differ from pin')
            stdout = (directory / 'under-pull-client.stdout').open('w')
            stderr = (directory / 'under-pull-client.stderr').open('w')
            process = subprocess.Popen([sys.executable, str(CLIENT), str(runner.LOAD_PY), contract['w2_load_sha256'], base, str(directory)], stdout=stdout, stderr=stderr)
            state['deadline_monotonic'] = time.monotonic() + 900
            state['client_pid'] = process.pid
            state['process'] = process
            deadline = time.monotonic() + 60
            while not (directory / 'readiness.json').exists():
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('client readiness failed')
                time.sleep(.02)
            state['readiness'] = json.loads((directory / 'readiness.json').read_text())
            if process.poll() is not None:
                raise RuntimeError('client finished before pulls')
        yield state
        with phase('under_pull_verification'):
            try:
                code = process.wait(timeout=max(0, state['deadline_monotonic'] - time.monotonic()))
            except subprocess.TimeoutExpired as exc:
                raise TimeoutError('client deadline expired') from exc
            state['client_exit'] = code
            completions = [json.loads(line) for line in (directory / 'completions.jsonl').read_text().splitlines()]
            client = json.loads((directory / 'client-result.json').read_text())
            state['coverage'] = coverage(intervals, completions)
            save(directory / 'under-pull-coverage.json', state['coverage'])
            rows = json.loads(engine.sh(['exec', ids['db'], 'psql', '-U', 'app', '-d', 'app', '-At', '-c',
                'SELECT json_agg(json_build_array(name,payload)) FROM items'], timeout=30).stdout)
            save(directory / 'under-pull-items.json', rows)
            verify_payload(rows, client, completions)
            if code:
                raise ValueError('client failed')
            require_coverage(intervals, completions)
            if max(row['completion_monotonic'] for row in completions) < intervals[-1]['end_monotonic']:
                raise ValueError('client finished before pulls ended')
    finally:
        try:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=15)
                state['client_exit'] = process.returncode
            if stdout is not None:
                stdout.close()
            if stderr is not None:
                stderr.close()
        finally:
            try:
                with phase('under_pull_cleanup'):
                    if started:
                        compose(['down', '-v', '--remove-orphans'])
                    state['cleanup'] = 'complete'
            finally:
                state.pop('process', None)
                try:
                    completion_path = directory / 'completions.jsonl'
                    if completion_path.exists():
                        completions = [json.loads(line) for line in completion_path.read_text().splitlines()]
                        state['coverage'] = coverage(intervals, completions)
                        save(directory / 'under-pull-coverage.json', state['coverage'])
                except Exception as exc:
                    state['receipt_error'] = repr(exc)
                finally:
                    save(directory / 'under-pull-ownership.json', state)
