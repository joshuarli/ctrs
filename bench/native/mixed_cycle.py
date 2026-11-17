"""Finite mixed cycles with verified transient data and a persistent committed witness."""
import concurrent.futures
from contextlib import nullcontext
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import signal
import sys
import subprocess
import threading
import time
from urllib.parse import urlsplit

import ci_jobs
import ownership
import mixed_resources
import runner

PIN = json.loads((runner.FIXTURES / 'w8-v5/portfolio.json').read_text())
WORKER = json.loads((runner.FIXTURES / 'w11-v2/worker-pin.json').read_text())
VERSION = 'w11-v3-bounded-working-set'
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


def bounded_load_cycle(base, cycle, directory, drain_deadline):
    """Keep an unresponsive HTTP peer from retaining load threads past drain."""
    remaining = min(75, drain_deadline - time.monotonic())
    if remaining <= 0:
        raise TimeoutError('mixed load drain deadline expired')
    program = ("import sys;from pathlib import Path;"
               "sys.path.insert(0,sys.argv[1]);import mixed_cycle;"
               "mixed_cycle.load_cycle(sys.argv[2],int(sys.argv[3]),Path(sys.argv[4]))")
    subprocess.run([sys.executable, '-c', program, str(Path(__file__).resolve().parent),
                    base, str(cycle), str(directory)], timeout=remaining, check=True)
    return json.loads((directory / 'acknowledged-writes.json').read_text())


def worker_failures(futures):
    errors = []
    for name, future in futures.items():
        try:
            result = future.result()
            if name == 'queue' and not result['correctness']['ok']:
                errors.append('queue: ' + repr(result.get('validation_errors', ['failed integrity checks'])))
        except ci_jobs.ConditionFailed as exc:
            errors.append(name + ': ' + repr([{key: job[key] for key in ('job', 'error', 'cleanup_error')}
                                             for job in exc.results if job['error'] or job['cleanup_error']]))
        except Exception as exc:
            errors.append(name + ': ' + repr(exc))
    return errors


def cleanup_cycle_items(engine, db, writes, directory):
    query = ('WITH deleted AS (DELETE FROM items WHERE id > 500 RETURNING name,payload) '
             'SELECT COALESCE(json_agg(json_build_array(name,payload)),\'[]\'::json) FROM deleted')
    removed = json.loads(engine.sh(['exec', db, 'psql', '-U', 'app', '-d', 'app', '-At', '-c', query],
                                   timeout=30).stdout)
    save(directory / 'explicitly-deleted-items.json', removed)
    if sorted(removed) != sorted([[row['name'], row['payload']] for row in writes]):
        raise ValueError('explicit item cleanup differs from acknowledged writes')
    remaining = json.loads(engine.sh(['exec', db, 'psql', '-U', 'app', '-d', 'app', '-At', '-c',
        'SELECT json_agg(json_build_array(name,payload)) FROM items'], timeout=30).stdout)
    save(directory / 'retained-items.json', remaining)
    if not runner.exact_w2_items(remaining, []):
        raise ValueError('explicit item cleanup changed seed rows or retained transient data')


def run(engine, ctx, refs, cycles=None, *, work_deadline=None, drain_deadline=None,
        cleanup_deadline=None, expected_boot_assets=None, observation=None, expected_resources=None):
    validate_refs(refs)
    if observation is not None:
        mixed_resources.plan(observation, {})
    if work_deadline is None:
        if type(cycles) is not int or not 1 <= cycles <= 3:
            raise ValueError('short mixed pilot requires 1..3 cycles')
    elif cycles is not None or drain_deadline is None or drain_deadline <= work_deadline:
        raise ValueError('duration mode requires separate work and drain deadlines')
    if cleanup_deadline is not None and (drain_deadline is None or cleanup_deadline <= drain_deadline):
        raise ValueError('cleanup deadline must follow drain deadline')
    directory = ctx.results_dir / engine.name
    directory.mkdir()
    rec = ctx.new_record(engine, 'W11', 'mixed-v3' if observation is None else 'mixed-v4-resources', directory)
    rec.update(fixture_version=VERSION if observation is None else mixed_resources.VERSION, qualification_eligible=False, cycles=[])
    observation_plan = None
    observations = []
    if observation is not None:
        rec['resources']['cycle_growth'] = mixed_resources.summarize(mixed_resources.plan(observation, {}), observations)
    rec['notes'].append('Functional finite pilot. API/queue/build tasks start together. Each cycle verifies all writes before explicit transient-row cleanup; 500 seed rows and the committed record persist. No reliability duration, growth or performance verdict.')
    project = runner.project_name(ctx.run_id, engine.name, 'mixed')
    warmup = 'np-mixed-' + hashlib.sha256(project.encode()).hexdigest()[:16]
    override = directory / 'compose.json'
    save(override, {'services': {service: {'image': refs[image]} for service, image in
         (('api', 'api'), ('db', 'postgres'), ('cache', 'redis'))}})
    port = runner.free_port()
    base = f'http://127.0.0.1:{port}'
    def compose(args):
        command = cleanup_sh if args[:1] == ['down'] else engine.sh
        return command(['compose', '-f', str(runner.COMPOSE_FILE), '-f', str(override), '-p', project, *args],
                         env_extra={'NP_API_PORT': str(port), 'NP_API_TAG': runner.API_TAG}, timeout=120)
    def rows(db):
        return json.loads(engine.sh(['exec', db, 'psql', '-U', 'app', '-d', 'app', '-At', '-c',
            'SELECT json_agg(json_build_array(name,payload)) FROM items'], timeout=30).stdout)
    sampler = trace = None
    total_writes = 0
    original_sh = engine.sh
    def cleanup_sh(args, env_extra=None, timeout=120, check=True):
        if cleanup_deadline is not None:
            remaining = cleanup_deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('mixed cleanup deadline expired')
            timeout = min(timeout, remaining)
        return original_sh(args, env_extra=env_extra, timeout=timeout, check=check)
    old_alarm = None
    command_deadline = [drain_deadline]
    if work_deadline is not None:
        old_alarm = signal.getsignal(signal.SIGALRM)
        def expire(signum, frame):
            raise TimeoutError('mixed work drain deadline expired')
        signal.signal(signal.SIGALRM, expire)
        signal.setitimer(signal.ITIMER_REAL, max(.001, drain_deadline - time.monotonic()))
        def bounded_sh(args, env_extra=None, timeout=120, check=True):
            remaining = command_deadline[0] - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('mixed command deadline expired')
            return original_sh(args, env_extra=env_extra, timeout=min(timeout, remaining), check=check)
        engine.sh = bounded_sh
    try:
        engine.ensure_up()
        engine.sh(['run', '--rm', '--pull=never', '--name', warmup, '--label', 'dev.ctrs.campaign.run=' + warmup,
                   '--entrypoint', 'node', refs['marked'], '-e', 'process.exit(0)'], timeout=90)
        identity = ownership.discover(engine.name, Path(engine.socket.removeprefix('unix://')), engine.dir)
        save(directory / 'running-engine-before.json', identity)
        rec['running_identity'] = identity
        if observation is not None:
            observation_plan = mixed_resources.plan(observation, identity)
            save(directory / 'resource-plan.json', observation_plan)
        if engine.name == 'ctrs' and [p['executable']['sha256'] for p in identity['required_processes'] if p['role'] == 'daemon'] != [runner.sha256_file(runner.CTRS_BIN)]:
            raise ValueError('adopted daemon differs from requested binary')
        if expected_boot_assets is not None:
            actual = {str(Path(asset['path']).resolve()): {key: asset[key] for key in ('inode', 'size', 'sha256')}
                      for process in identity['required_processes'] if process['role'] == 'vm' for asset in process['boot_assets']}
            if actual != expected_boot_assets:
                raise ValueError('running VM boot assets differ from frozen inputs')
        rec['resources']['engine'] = runner.safe_engine_info(engine)
        if expected_resources is not None and not runner.resource_cells.engine_budget_matches(expected_resources, rec['resources']['engine']):
            raise ValueError('running engine resource envelope differs from the freeze or is unknown')
        for name, ref in refs.items():
            info = json.loads(engine.sh(['image', 'inspect', ref]).stdout)[0]
            pin = WORKER['worker'] if name == 'worker' else PIN['images']['np-v5/' + name]
            if info['Architecture'] != 'arm64' or ref not in info['RepoDigests'] or info['RootFS']['Layers'] != pin['diff_ids']:
                raise ValueError('running image identity differs from pin: ' + name)
            save(directory / (name + '-image.json'), info)
        sampler, trace = runner.start_sampler(engine, directory)
        rec['resources']['sampler_version'] = runner.collect.SAMPLER_VERSION
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
            status, _ = runner.http_json_write(base + '/records', {'key': 'mixed-committed', 'value': 'exact-v3'})
            if status != 200 or not runner.exact_w2_items(rows(ids['db']), []):
                raise ValueError('initial exact database state failed')
        cycle = 0
        while cycle < cycles if work_deadline is None else time.monotonic() < work_deadline:
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
                result = runner.trial_w4(cycle_ctx, engine, 'mixed', workers=(4,), image_ref=refs['worker'], redis_ref=refs['redis'], cleanup_command=cleanup_sh)
                save(cycle_dir / 'queue.json', result)
                return result
            def build_work():
                try:
                    result = ci_jobs.run_condition(engine, refs['marked'], warmup + f'-c{cycle}', 4, cleanup_command=cleanup_sh)
                except ci_jobs.ConditionFailed as exc:
                    save(cycle_dir / 'build-jobs.json', exc.results)
                    raise
                save(cycle_dir / 'build-jobs.json', result)
                return result
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=3)
            futures = {}
            try:
                with runner.resource_phase(engine, rec, f'cycle_{cycle}_mixed_work'):
                    futures['api'] = pool.submit(timed, 'api', lambda: load_cycle(base, cycle, cycle_dir) if drain_deadline is None else bounded_load_cycle(base, cycle, cycle_dir, drain_deadline))
                    futures['queue'] = pool.submit(timed, 'queue', queue_work)
                    futures['build'] = pool.submit(timed, 'build', build_work)
                    outcomes, failures = {}, []
                    for name, future in futures.items():
                        try:
                            timeout = None if drain_deadline is None else max(0, drain_deadline - time.monotonic())
                            outcomes[name] = future.result(timeout=timeout)
                        except Exception as exc:
                            failures.append(name + ': ' + repr(exc))
                    if failures:
                        raise RuntimeError('; '.join(failures))
                    api_writes, queue_result, jobs = (outcomes[name] for name in ('api', 'queue', 'build'))
                    if not queue_result['correctness']['ok'] or len(jobs) != 16:
                        raise RuntimeError('mixed queue/build work failed')
            finally:
                cycle_failure = sys.exc_info()[1]
                if drain_deadline is not None:
                    signal.setitimer(signal.ITIMER_REAL, 0)
                pool.shutdown(wait=True, cancel_futures=True)
                save(cycle_dir / 'intervals.json', intervals)
                errors = worker_failures(futures)
                rec['validation_errors'].extend(f'cycle {cycle} worker outcome: {error}' for error in errors)
                if errors and cycle_failure is None:
                    raise RuntimeError('mixed worker outcomes failed: ' + repr(errors))
                if drain_deadline is not None and sys.exc_info()[0] is None:
                    signal.setitimer(signal.ITIMER_REAL, max(.001, drain_deadline - time.monotonic()))
            with runner.resource_phase(engine, rec, f'cycle_{cycle}_verify'):
                actual = rows(ids['db'])
                save(cycle_dir / 'persisted-items.json', actual)
                if len({write['name'] for write in api_writes}) != len(api_writes) or not runner.exact_w2_items(actual, api_writes):
                    raise ValueError('cycle writes lost, duplicated or corrupted')
                status, body = runner.http_json(base + '/records/mixed-committed')
                if status != 200 or body != {'key': 'mixed-committed', 'value': 'exact-v3', 'cache_match': True}:
                    raise ValueError('committed DB/cache data changed')
                if json.loads(engine.sh(['volume', 'inspect', volume]).stdout) != volume_before:
                    raise ValueError('persistent named-volume identity changed')
                after = ownership.discover(engine.name, Path(engine.socket.removeprefix('unix://')), engine.dir)
                save(cycle_dir / 'running-engine.json', after)
                if after != identity:
                    raise ValueError('engine identity changed during mixed cycles')
            with runner.resource_phase(engine, rec, f'cycle_{cycle}_data_cleanup'):
                cleanup_cycle_items(engine, ids['db'], api_writes, cycle_dir)
                status, body = runner.http_json(base + '/records/mixed-committed')
                if status != 200 or body != {'key': 'mixed-committed', 'value': 'exact-v3', 'cache_match': True}:
                    raise ValueError('committed DB/cache witness changed after item cleanup')
                if json.loads(engine.sh(['volume', 'inspect', volume]).stdout) != volume_before:
                    raise ValueError('persistent named-volume identity changed after item cleanup')
            current_ids = {service: compose(['ps', '-q', service]).stdout.strip() for service in ('api', 'db', 'cache')}
            if current_ids != ids:
                raise ValueError('persistent service identities changed')
            if observation_plan is not None:
                try:
                    with runner.resource_phase(engine, rec, f'cycle_{cycle}_observation'):
                        observed = mixed_resources.observe(observation_plan, cycle, cycle_dir)
                except Exception as exc:
                    observed = {'cycle': cycle, 'version': mixed_resources.VERSION,
                                'interval': {'status': 'unknown', 'errors': [repr(exc)]}}
                observations.append(observed)
                try:
                    save(cycle_dir / 'resource-observation.json', observed)
                except OSError as exc:
                    observed['interval'] = {'status': 'unknown', 'errors': ['observation write: ' + repr(exc)]}
            total_writes += len(api_writes)
            rec['cycles'].append({'cycle': cycle, 'successful_operations': OPERATIONS,
                'acknowledged_writes': len(api_writes), 'cumulative_writes': total_writes,
                'explicitly_deleted_writes': len(api_writes), 'retained_seed_rows': 500,
                'queue_jobs': 200, 'queue_events': 12800, 'artifacts': 400, 'build_jobs': len(jobs), 'exact_state': True, 'service_ids': current_ids})
            cycle += 1
        rec['work_loop_ended_monotonic'] = time.monotonic()
        if not rec['cycles']:
            raise RuntimeError('work deadline expired before a complete cycle')
        rec['correctness']['checks'].update(
            exact_state_every_cycle=all(row['exact_state'] for row in rec['cycles']),
            bounded_retained_items=all(row['explicitly_deleted_writes'] == row['acknowledged_writes']
                                      and row['retained_seed_rows'] == 500 for row in rec['cycles']))
        rec['correctness']['ok'] = True
    except BaseException as exc:
        rec['correctness']['ok'] = False
        rec['validation_errors'].append(repr(exc))
        raise
    finally:
        primary_failure = sys.exc_info()[1]
        if observation is not None:
            rec['resources']['cycle_growth'] = mixed_resources.summarize(
                observation_plan or mixed_resources.plan(observation, {}), observations)
        if work_deadline is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_alarm)
            engine.sh = original_sh
        try:
            with runner.resource_phase(engine, rec, 'cleanup') if sampler is not None else nullcontext():
                compose(['down', '-v', '--remove-orphans'])
                ci_jobs.cleanup(engine, warmup, warmup, command=cleanup_sh)
                containers = cleanup_sh(['ps', '-a', '--no-trunc', '--format', '{{json .}}']).stdout
                save(directory / 'containers-after.json', [json.loads(line) for line in containers.splitlines()])
                if any(json.loads(line)['Names'].startswith(project) or json.loads(line)['Names'].startswith(warmup) for line in containers.splitlines()):
                    raise RuntimeError('owned mixed service/build containers remain')
        except BaseException as exc:
            rec['correctness']['ok'] = False
            rec['validation_errors'].append('cleanup: ' + repr(exc))
            if primary_failure is None:
                raise
        finally:
            pending = sys.exc_info()[1]
            try:
                if sampler is not None:
                    runner.stop_sampler(sampler)
                rec['resources'].update(runner.summarize_trace(trace) if trace else {})
                if trace:
                    rec['resources']['trace'] = runner._trace_ref(trace)
            except BaseException as exc:
                rec['correctness']['ok'] = False
                rec['validation_errors'].append('sampler finalization: ' + repr(exc))
                if pending is None:
                    raise
            finally:
                pending = sys.exc_info()[1]
                try:
                    save(directory / 'result.json', rec)
                except OSError:
                    if pending is None:
                        raise
    return rec
