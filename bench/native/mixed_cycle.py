"""Finite mixed application/queue/build cycles with exact cumulative persisted state."""
import concurrent.futures
from contextlib import nullcontext
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlsplit

import ci_jobs
import ownership
import runner

PIN = json.loads((runner.FIXTURES / 'w8-v2/portfolio.json').read_text())
WORKER = json.loads((runner.FIXTURES / 'w11-v2/worker-pin.json').read_text())
VERSION = 'w11-v2-mixed-fixed-cycles'
OPERATIONS = 5000
CONCURRENCY = 4


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def validate_refs(refs):
    expected = {name.rsplit('/', 1)[1]: item['manifest'] for name, item in PIN['images'].items()}
    expected['worker'] = WORKER['worker']['manifest']
    if refs.keys() != expected.keys():
        raise ValueError('mixed cycles require all five pinned image references')
    for name, digest in expected.items():
        if not re.fullmatch(r'[a-z0-9][a-z0-9._:/-]*@sha256:[0-9a-f]{64}', refs[name]) or refs[name].rsplit('@', 1)[1] != digest:
            raise ValueError('mixed image differs from pin: ' + name)
    if runner.sha256_file(runner.LOAD_PY) != PIN['w2_load_sha256'] or runner.sha256_file(runner.FIXTURES / 'w1/seed.sql') != PIN['seed_sql_sha256']:
        raise ValueError('application workload inputs differ from pin')
    if runner.sha256_file(runner.FIXTURES / 'w4/app.py') != WORKER['worker']['app_sha256']:
        raise ValueError('queue application differs from pin')


def load_cycle(base, cycle, directory):
    spec = importlib.util.spec_from_file_location('mixed_w2_load', runner.LOAD_PY)
    load = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(load)
    url = urlsplit(base)
    counts = dict(reads=0, writes=0, errors=0)
    latencies, errors, writes = [], [], []
    stop = threading.Event()
    timer = threading.Timer(60, stop.set)
    begin = time.monotonic()
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY)
    try:
        timer.start()
        futures = [pool.submit(load.worker, cycle * CONCURRENCY + i, (url.hostname, url.port), 60, .3, 7000 + i,
                               latencies, counts, stop, errors, begin, operations=OPERATIONS // CONCURRENCY,
                               writes=writes) for i in range(CONCURRENCY)]
        for future in futures:
            future.result()
    finally:
        stop.set()
        timer.cancel()
        timer.join()
        pool.shutdown(wait=True, cancel_futures=True)
        elapsed = time.monotonic() - begin
        latencies.sort()
        save(directory / 'load.json', {'fixture_version': VERSION, 'cycle': cycle,
             'worker_ids': list(range(cycle * CONCURRENCY, (cycle + 1) * CONCURRENCY)),
             'reads_ok': counts['reads'], 'writes_ok': counts['writes'], 'errors': counts['errors'],
             'target_operations': OPERATIONS, 'duration_seconds': elapsed,
             'successful_latency_ms': {key: load.pct(latencies, q) for key, q in (('p50', .5), ('p95', .95), ('p99', .99))},
             'deadline_seconds': 60, 'error_details': errors})
        save(directory / 'acknowledged-writes.json', writes)
    if counts['errors'] or counts['reads'] + counts['writes'] != OPERATIONS:
        raise RuntimeError('mixed API fixed work failed or exceeded deadline')
    return writes


def run(engine, ctx, refs, cycles):
    validate_refs(refs)
    if type(cycles) is not int or not 1 <= cycles <= 3:
        raise ValueError('short mixed pilot requires 1..3 cycles')
    directory = ctx.results_dir / engine.name
    directory.mkdir()
    rec = ctx.new_record(engine, 'W11', 'mixed-v2', directory)
    rec.update(fixture_version=VERSION, qualification_eligible=False, cycles=[])
    rec['notes'].append('Functional finite pilot. API/queue/build tasks start together; actual intervals recorded. Boot warmup precedes accounting. No reliability duration, growth or performance verdict.')
    project = runner.project_name(ctx.run_id, engine.name, 'mixed')
    warmup = 'np-mixed-' + hashlib.sha256(project.encode()).hexdigest()[:16]
    override = directory / 'compose.json'
    save(override, {'services': {service: {'image': refs[image]} for service, image in
         (('api', 'api'), ('db', 'postgres'), ('cache', 'redis'))}})
    port = runner.free_port()
    base = f'http://127.0.0.1:{port}'
    def compose(args):
        return engine.sh(['compose', '-f', str(runner.COMPOSE_FILE), '-f', str(override), '-p', project, *args],
                         env_extra={'NP_API_PORT': str(port), 'NP_API_TAG': runner.API_TAG}, timeout=120)
    def rows(db):
        return json.loads(engine.sh(['exec', db, 'psql', '-U', 'app', '-d', 'app', '-At', '-c',
            'SELECT json_agg(json_build_array(name,payload)) FROM items'], timeout=30).stdout)
    sampler = trace = None
    cumulative = []
    try:
        engine.ensure_up()
        engine.sh(['run', '--rm', '--pull=never', '--name', warmup, '--label', 'dev.ctrs.campaign.run=' + warmup,
                   '--entrypoint', 'node', refs['marked'], '-e', 'process.exit(0)'], timeout=90)
        identity = ownership.discover(engine.name, Path(engine.socket.removeprefix('unix://')), engine.dir)
        save(directory / 'running-engine-before.json', identity)
        if engine.name == 'ctrs' and [p['executable']['sha256'] for p in identity['required_processes'] if p['role'] == 'daemon'] != [runner.sha256_file(runner.CTRS_BIN)]:
            raise ValueError('adopted daemon differs from requested binary')
        for name, ref in refs.items():
            info = json.loads(engine.sh(['image', 'inspect', ref]).stdout)[0]
            pin = WORKER['worker'] if name == 'worker' else PIN['images']['np-v2/' + name]
            if info['Architecture'] != 'arm64' or ref not in info['RepoDigests'] or info['RootFS']['Layers'] != pin['diff_ids']:
                raise ValueError('running image identity differs from pin: ' + name)
            save(directory / (name + '-image.json'), info)
        sampler, trace = runner.start_sampler(engine, directory)
        with runner.resource_phase(engine, rec, 'setup'):
            compose(['up', '-d', '--no-build', '--pull', 'never'])
            if runner.wait_health(base, 60)[0] is None:
                raise RuntimeError('mixed persistent stack readiness')
            ids = {service: compose(['ps', '-q', service]).stdout.strip() for service in ('api', 'db', 'cache')}
            if any(not value or '\n' in value for value in ids.values()):
                raise ValueError('ambiguous persistent service identities')
            app_hashes = json.loads(engine.sh(['exec', ids['api'], 'python', '-c',
                "import json,hashlib,pathlib;print(json.dumps({p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in ['/app/app.py','/app/requirements.txt']}))"]).stdout)
            if app_hashes != PIN['api_files_sha256']:
                raise ValueError('running API contents differ from pin')
            volume = project + '_dbdata'
            volume_before = json.loads(engine.sh(['volume', 'inspect', volume]).stdout)
            save(directory / 'volume-before.json', volume_before)
            status, _ = runner.http_json_write(base + '/records', {'key': 'mixed-committed', 'value': 'exact-v2'})
            if status != 200 or not runner.exact_w2_items(rows(ids['db']), []):
                raise ValueError('initial exact database state failed')
        for cycle in range(cycles):
            cycle_dir = directory / f'cycle-{cycle}'
            cycle_dir.mkdir()
            cycle_ctx = runner.RunContext(ctx.run_id + f'-c{cycle}')
            cycle_ctx.design = 'mixed-functional-diagnostic'
            intervals = {}
            def timed(name, action):
                intervals[name] = {'begin_monotonic': time.monotonic()}
                try:
                    return action()
                finally:
                    intervals[name]['end_monotonic'] = time.monotonic()
            def queue_work():
                result = runner.trial_w4(cycle_ctx, engine, 'mixed', workers=(4,), image_ref=refs['worker'], redis_ref=refs['redis'])
                save(cycle_dir / 'queue.json', result)
                return result
            def build_work():
                try:
                    result = ci_jobs.run_condition(engine, refs['marked'], warmup + f'-c{cycle}', 4)
                except ci_jobs.ConditionFailed as exc:
                    save(cycle_dir / 'build-jobs.json', exc.results)
                    raise
                save(cycle_dir / 'build-jobs.json', result)
                return result
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)
            try:
                with runner.resource_phase(engine, rec, f'cycle_{cycle}_mixed_work'):
                    futures = {
                        'api': pool.submit(timed, 'api', lambda: load_cycle(base, cycle, cycle_dir)),
                        'queue': pool.submit(timed, 'queue', queue_work),
                        'build': pool.submit(timed, 'build', build_work)}
                    outcomes, failures = {}, []
                    for name, future in futures.items():
                        try:
                            outcomes[name] = future.result()
                        except Exception as exc:
                            failures.append(name + ': ' + repr(exc))
                    if failures:
                        raise RuntimeError('; '.join(failures))
                    api_writes, queue_result, jobs = (outcomes[name] for name in ('api', 'queue', 'build'))
                    if not queue_result['correctness']['ok'] or len(jobs) != 16:
                        raise RuntimeError('mixed queue/build work failed')
            finally:
                pool.shutdown(wait=True, cancel_futures=True)
                save(cycle_dir / 'intervals.json', intervals)
            cumulative.extend(api_writes)
            with runner.resource_phase(engine, rec, f'cycle_{cycle}_verify'):
                actual = rows(ids['db'])
                save(cycle_dir / 'persisted-items.json', actual)
                if len({write['name'] for write in cumulative}) != len(cumulative) or not runner.exact_w2_items(actual, cumulative):
                    raise ValueError('cumulative writes lost, duplicated or corrupted')
                status, body = runner.http_json(base + '/records/mixed-committed')
                if status != 200 or body != {'key': 'mixed-committed', 'value': 'exact-v2', 'cache_match': True}:
                    raise ValueError('committed DB/cache data changed')
                if json.loads(engine.sh(['volume', 'inspect', volume]).stdout) != volume_before:
                    raise ValueError('persistent named-volume identity changed')
                after = ownership.discover(engine.name, Path(engine.socket.removeprefix('unix://')), engine.dir)
                save(cycle_dir / 'running-engine.json', after)
                if after != identity:
                    raise ValueError('engine identity changed during mixed cycles')
            rec['cycles'].append({'cycle': cycle, 'successful_operations': OPERATIONS,
                'acknowledged_writes': len(api_writes), 'cumulative_writes': len(cumulative),
                'queue_jobs': 200, 'queue_events': 12800, 'artifacts': 400, 'build_jobs': len(jobs), 'exact_state': True})
        rec['correctness']['ok'] = True
    except BaseException as exc:
        rec['correctness']['ok'] = False
        rec['validation_errors'].append(repr(exc))
        raise
    finally:
        try:
            with runner.resource_phase(engine, rec, 'cleanup') if sampler is not None else nullcontext():
                compose(['down', '-v', '--remove-orphans'])
                ci_jobs.cleanup(engine, warmup, warmup)
                containers = engine.sh(['ps', '-a', '--no-trunc', '--format', '{{json .}}']).stdout
                save(directory / 'containers-after.json', [json.loads(line) for line in containers.splitlines()])
                if any(json.loads(line)['Names'].startswith(project) or json.loads(line)['Names'].startswith(warmup) for line in containers.splitlines()):
                    raise RuntimeError('owned mixed service/build containers remain')
        except BaseException as exc:
            rec['correctness']['ok'] = False
            rec['validation_errors'].append('cleanup: ' + repr(exc))
            raise
        finally:
            if sampler is not None:
                runner.stop_sampler(sampler)
            rec['resources'].update(runner.summarize_trace(trace) if trace else {})
            if trace:
                rec['resources']['trace'] = runner._trace_ref(trace)
            save(directory / 'result.json', rec)
    return rec
