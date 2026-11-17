"""Pinned fixed-work observer controls; raw ratios never qualify product performance."""
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
import threading
import time
import uuid

import collect
import diagnostic_signals
import mixed_cycle
import ownership
import registry_portfolio
import runner
from diagnostics import resource_pilot


def _trial_totals(record, operations):
    metrics, resources = record['metrics'], record['resources']
    if record['correctness']['ok'] is not True or record['validation_errors']:
        raise ValueError('W2 control failed correctness')
    reads, writes = metrics['reads_ok'], metrics['writes_ok']
    if reads + writes != operations or metrics['errors'] != 0:
        raise ValueError('W2 control did not complete the declared useful work')
    for phase in ('setup', 'workload', 'cleanup'):
        boundary = resources['phases'][phase]
        if boundary['errors'] or boundary['cpu_seconds'] is None:
            raise ValueError('incomplete W2 control CPU boundary: ' + phase)
    if resources.get('resource_errors'):
        raise ValueError('periodic resource collection failed')
    workload = resources['phases']['workload']
    values = {
        'cpu_seconds_per_success': workload['cpu_seconds'] / operations,
        'api_cpu_seconds_per_success': resources['application_cpu']['delta']['usage_usec'] / 1e6 / operations,
        'wall_seconds': workload['operation_wall_seconds'],
    }
    if any(not math.isfinite(value) or value <= 0 for value in values.values()):
        raise ValueError('missing or invalid control cost')
    return values | {'reads_ok': reads, 'writes_ok': writes}


def _paired_controls(rows, pairs):
    for pair in range(1, pairs + 1):
        counts = {(row['reads_ok'], row['writes_ok']) for row in rows if row['pair'] == pair}
        if len(counts) != 1:
            raise ValueError('engines or observer modes completed different useful work')
    result = {}
    for name in ('ctrs', 'orbstack'):
        ratios = []
        for pair in range(1, pairs + 1):
            members = [r for r in rows if r['engine'] == name and r['pair'] == pair]
            modes = {r['sampling_mode']: r for r in members}
            if len(members) != 2 or set(modes) != {m.value for m in runner.SamplingMode}:
                raise ValueError('incomplete or duplicate observer control pair')
            off, on = (modes[mode.value] for mode in (runner.SamplingMode.BOUNDARIES, runner.SamplingMode.PERIODIC))
            if any(off[key] != on[key] for key in ('reads_ok', 'writes_ok')):
                raise ValueError('observer modes completed different useful work')
            ratios.append({key: on[key] / off[key] for key in
                ('cpu_seconds_per_success', 'api_cpu_seconds_per_success', 'wall_seconds')})
        result[name] = {'pairs': ratios, 'median_on_over_off': {
            key: statistics.median(r[key] for r in ratios) for key in ratios[0]},
            'budget_verdict': 'unqualified: exclusivity and observer acceptance require separate confirmation'}
    return result


def run_calibration(*, run_id, portfolio_layout, ctrs_binary, pairs=5, operations=10000):
    """Run finite diagnostic controls in a dedicated process; return their result directory."""
    if (not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', run_id)
            or type(pairs) is not int or not 1 <= pairs <= 5
            or type(operations) is not int or not 1 <= operations <= 100000):
        raise ValueError('require a simple run ID, 1..5 pairs and 1..100000 operations')
    if sys.platform != 'darwin' or os.uname().machine != 'arm64':
        raise ValueError('native ARM64 macOS only')
    binary = Path(ctrs_binary).resolve(strict=True)
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError('ctrs binary must be an executable file')
    if (runner.RESULTS / run_id).exists():
        raise ValueError('refuse existing calibration output')
    pin = mixed_cycle.PIN
    if (runner.sha256_file(runner.LOAD_PY) != pin['w2_load_sha256']
            or runner.sha256_file(runner.FIXTURES / 'w1/seed.sql') != pin['seed_sql_sha256']):
        raise ValueError('W2 load or seed differs from the common portfolio pin')
    portfolio = registry_portfolio.prepare_pinned_portfolio(portfolio_layout, pin)
    diagnostic_signals.install_cleanup_signals()
    runner.DOCKER = runner.find_docker()
    runner.CTRS_BIN = binary
    ctx = runner.RunContext(run_id)
    ctx.design = 'sampler-calibration'
    root = ctx.results_dir
    result = {'status': 'failed', 'records': [], 'cleanup_errors': [],
              'timing_eligible': False, 'qualification_eligible': False}
    resource_pilot.save(root / 'plan.json', {'pairs_per_engine': pairs, 'operations': operations,
        'concurrency': 4, 'write_ratio': .3, 'seed': '7 + pair', 'sampler_version': collect.SAMPLER_VERSION,
        'order': 'engine blocks; alternate boundaries/periodic within each engine',
        'observer_limits': {'cpu_per_success_inflation': .05, 'wall_inflation': .05},
        'timing_eligible': False, 'qualification_eligible': False,
        'scope': 'pinned W2 fixed work; no engine comparison or certified observer-overhead verdict',
        'ctrs_binary_sha256': runner.sha256_file(binary), 'source_contract': pin,
        'source_sha256': {str(path.relative_to(runner.REPO)): runner.sha256_file(path) for path in
            (Path(__file__), Path(runner.__file__), runner.COLLECT, Path(ownership.__file__),
             Path(resource_pilot.__file__), runner.LOAD_PY, runner.COMPOSE_FILE)}})
    server = registry_portfolio.serve(portfolio, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05})
    try:
        thread.start()
        refs = {name.rsplit('/', 1)[1]: f'127.0.0.1:{server.server_port}/{name}@{digest}'
                for name, digest in portfolio.manifests.items()}
        for name in ('ctrs', 'orbstack'):
            directory = root / name
            directory.mkdir()
            store = runner.REPO / '.work/tmp' / ('sc-' + uuid.uuid4().hex[:8]) if name == 'ctrs' else None
            engine = resource_pilot.ResourceEngine(name, run_id, refs, directory, fresh_dir=store)
            identity = None
            try:
                engine.ensure_up()
                for image in ('api', 'postgres', 'redis'):
                    cp = engine.sh(['pull', refs[image]], timeout=180)
                    (directory / (image + '-pull.log')).write_text(cp.stdout + cp.stderr)
                resource_pilot.verify_images(engine, refs, directory)
                resource_pilot.warmup_api(engine, refs['api'])
                identity = ownership.discover(name, Path(engine.socket.removeprefix('unix://')), engine.dir)
                if name == 'ctrs':
                    resource_pilot.verify_binary(identity, runner.sha256_file(binary))
                resource_pilot.save(directory / 'running-engine.json', identity)
                resource_pilot.save(directory / 'engine-info.json', runner.safe_engine_info(engine))
                for pair in range(1, pairs + 1):
                    modes = [runner.SamplingMode.BOUNDARIES, runner.SamplingMode.PERIODIC]
                    if pair % 2 == 0:
                        modes.reverse()
                    for mode in modes:
                        trial = directory / f'{pair}-{mode.value}'
                        trial.mkdir()
                        resource_pilot.host_snapshot(trial, 'before')
                        ctx.workload_params = {'operations': operations, 'concurrency': 4, 'write_ratio': .3, 'seed': 7 + pair}
                        rec = runner.trial_w2(ctx, engine, 'sampler-' + mode.value, 4, 20, .3, 7 + pair,
                                              operations, sampling=mode)
                        rec.update(measurement_valid=False, measurement_invalidation='observer diagnostic; host exclusivity not certified',
                                   calibration_pair=pair, sampling_mode=mode.value, engine_server_version=runner.safe_version(engine))
                        ctx.write(rec)
                        resource_pilot.host_snapshot(trial, 'after')
                        row = _trial_totals(rec, operations) | {'engine': name, 'pair': pair,
                            'sampling_mode': mode.value, 'trial_id': rec['trial_id']}
                        result['records'].append(row)
                        resource_pilot.save(root / 'result.json', result)
            finally:
                primary = sys.exc_info()[1]
                if store is not None:
                    result['ctrs_store'] = str(store)
                    result['native_stop_verified'] = False
                try:
                    engine.stop()
                    if store is not None:
                        current = getattr(engine, 'measurement_identity', {})
                        known = [*(identity or {}).get('required_processes', []), *current.get('required_processes', [])]
                        deadline = time.monotonic() + 10
                        while known:
                            table = ownership.process_table()
                            live = [p['pid'] for p in known
                                    if table.get(p['pid'], {}).get('start_identity') == p['start_identity']]
                            if not live or time.monotonic() >= deadline:
                                result['native_stop_verified'] = not live
                                break
                            time.sleep(.2)
                        if not result['native_stop_verified']:
                            result['cleanup_errors'].append('native stop not verified')
                except BaseException as exc:
                    result['cleanup_errors'].append(repr(exc))
                    if primary is None:
                        raise
            if result['cleanup_errors']:
                raise RuntimeError('observer control cleanup failed')
        result['comparison'] = _paired_controls(result['records'], pairs)
        result['status'] = 'passed' if not result['cleanup_errors'] else 'failed'
    except BaseException as exc:
        result['error'] = repr(exc)
        raise
    finally:
        primary = sys.exc_info()[1]
        try:
            try:
                if thread.is_alive():
                    server.shutdown()
            finally:
                try:
                    server.server_close()
                finally:
                    if thread.ident is not None:
                        thread.join(timeout=5)
                        if thread.is_alive():
                            raise RuntimeError('registry thread remains')
        except BaseException as exc:
            result['cleanup_errors'].append(repr(exc))
            result['status'] = 'failed'
            if primary is None:
                raise
        finally:
            resource_pilot.save(root / 'result.json', result)
    if result['status'] != 'passed':
        raise RuntimeError('observer control cleanup failed')
    return root
