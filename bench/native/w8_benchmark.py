"""Canonical paired W8 pilot; native execution remains unqualified."""
import hashlib
import json
from pathlib import Path
import secrets
import threading
import traceback
import sys

import registry_portfolio
import registry_variant
import runner
import reporting
from diagnostics import registry_variant_pilot as pilot
from diagnostics.resource_pilot import host_snapshot

FIXTURE = reporting.W8_PAIRED_FIXTURE
SCOPE = 'w8-whole-workflow-v1'


def gate(directory, label):
    host_snapshot(directory, label)
    data = json.loads((directory / (label + '-gate.json')).read_text())
    return data.get('exit') == 0 and 'hot process tree' not in data.get('stderr', '').lower()


def resource_metrics(result):
    cell = result.get('resources', {}).get('phase_summaries', {}).get('whole_workflow', {})
    if cell.get('status') != 'ok':
        return {}
    return {'cpu_seconds_est': cell.get('cpu_seconds'),
            'peak_phys_footprint_bytes': cell.get('peak_phys_footprint_bytes')}


def completion_metrics(directory, intervals):
    rows = [json.loads(line) for line in (directory / 'completions.jsonl').read_text().splitlines()]
    values = sorted(row['latency_ms'] for row in rows if any(
        interval['begin_monotonic'] <= row['completion_monotonic'] <= interval['end_monotonic']
        for interval in intervals))
    if not values:
        raise ValueError('no completions during pulls')
    return {'under_pull_p95_ms': values[round(.95 * (len(values) - 1))],
            'under_pull_p99_ms': values[round(.99 * (len(values) - 1))]}


def run_batch(args, *, engine_factory=None, measure=None, prepare=None, serve=None, gate_fn=None):
    engine_factory = engine_factory or runner.Engine
    measure = measure or pilot.measure_engine
    prepare = prepare or registry_variant.prepare_variant
    serve = serve or registry_portfolio.serve
    gate_fn = gate_fn or gate
    contract = json.loads((runner.FIXTURES / 'w8-v2/portfolio.json').read_text())
    registry_portfolio.prepare_pinned_portfolio(args.layout, contract)
    run = 'w8-paired-' + secrets.token_hex(6)
    ctx = runner.RunContext(run)
    ctx.workload_params = {'fixture_version': FIXTURE, 'resource_scope': SCOPE, 'under_load': args.under_load}
    ctx.provenance.update({'w8_source_contract_sha256': runner.sha256_file(runner.FIXTURES / 'w8-v2/portfolio.json'),
                           'w8_driver_sha256': runner.sha256_file(Path(__file__)),
                           'w8_pilot_sha256': runner.sha256_file(Path(pilot.__file__))})
    outputs = ctx.provenance.get('build_outputs', {})
    ctx.provenance.update({key: outputs[key] for key in ('ctrs_binary_sha256', 'guest_kernel_sha256',
        'guest_initramfs_sha256', 'guest_data_sha256') if key in outputs})
    pilot.save(ctx.results_dir / 'plan.json', {'pairs': args.pairs, 'seed': args.seed,
        'under_load': args.under_load, 'diagnostic': args.diagnostic, 'fixture_version': FIXTURE,
        'resource_scope': SCOPE, 'source_layout': str(args.layout), 'provenance': ctx.provenance,
        'order': 'AB/BA', 'qualification_eligible': False})
    print(f'results: {ctx.jsonl}', flush=True)
    engines = {name: engine_factory(name, run) for name in ('ctrs', 'orbstack')}
    failed = False
    completed = 0
    finished = False
    stopped_reason = None
    try:
        for pair in range(1, args.pairs + 1):
            seed = hashlib.sha256(f'{run}:{args.seed}:{pair}'.encode()).digest()
            layout = ctx.results_dir / f'pair-{pair}-layout'
            receipt = prepare(args.layout, contract, layout, seed)
            portfolio = registry_portfolio.prepare_layout(layout, {name: image['reference'] for name, image in receipt['images'].items()})
            server = serve(portfolio, 0)
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05})
            try:
                thread.start()
                for index, name in enumerate(('ctrs', 'orbstack') if pair % 2 else ('orbstack', 'ctrs')):
                    engine = engines[name]
                    directory = ctx.trial_dir(name, 'W8', 'warm')
                    ctx.workload_id = runner.workload_id(run, 'W8', pair, 0)
                    rec = ctx.new_record(engine, 'W8', 'warm', directory)
                    rec.update(pair_id=pair, order_index=index, paired_inputs={'seed_hex': seed.hex(), 'receipt': receipt})
                    rec['correctness'] = {'ok': False, 'checks': {'workload': False}}
                    rec['measurement_valid'] = False
                    busy_initial = False
                    try:
                        before = gate_fn(directory, 'before')
                        if not before and not args.diagnostic:
                            busy_initial = True
                            raise RuntimeError('initial host gate busy; scored trial refused')
                        result = measure(engine, directory, f'{run}-p{pair:03d}', contract, portfolio, receipt, layout, server, args.under_load)
                        rec['engine_server_version'] = runner.safe_version(engine)
                        info = runner.safe_engine_info(engine)
                        rec['resources'] = resource_metrics(result)
                        rec['resources']['engine'] = info or {}
                        rec['resources']['detail'] = result.get('resources', {})
                        budgets = bool(info) and all(type(info.get(key)) is int and info[key] > 0
                                                    for key in ('ncpu', 'mem_total_bytes'))
                        ok = result.get('correctness') is True and result.get('resources', {}).get('status') == 'ok' and budgets and rec['engine_server_version'] != 'unreachable'
                        rec['correctness'] = {'ok': ok, 'checks': {'workload_and_resources': ok}}
                        rec['validation_errors'].extend(result.get('errors', []))
                        if ok:
                            rec['metrics']['pull_to_health_s'] = result['pull_to_health_s']
                            if args.under_load:
                                rec['metrics'].update(completion_metrics(directory, result['under_pull_intervals']))
                        rec['measurement_valid'] = before and not args.diagnostic
                    except Exception:
                        rec['validation_errors'].append(traceback.format_exc())
                    finally:
                        try:
                            after = gate_fn(directory, 'after')
                        except Exception:
                            after = False
                            rec['validation_errors'].append(traceback.format_exc())
                        rec['measurement_valid'] = rec['measurement_valid'] and after
                        if not rec['measurement_valid']:
                            rec['measurement_invalidation'] = 'diagnostic mode or host gate contamination'
                        ctx.write(rec)
                        completed += 1
                    failed |= not rec['correctness']['ok'] or bool(rec['validation_errors']) or (not args.diagnostic and not rec['measurement_valid'])
                    print(f"pair {pair} {name}: {'OK' if rec['correctness']['ok'] else 'FAIL'}", flush=True)
                    if busy_initial:
                        stopped_reason = 'initial-host-busy'
                        return 1
            finally:
                if thread.ident is not None:
                    server.shutdown()
                server.server_close()
                if thread.ident is not None:
                    thread.join(timeout=5)
                if thread.is_alive():
                    raise RuntimeError('registry did not terminate')
        finished = True
        return int(failed)
    finally:
        primary = sys.exc_info()[1]
        cleanup_error = None
        try:
            engines['ctrs'].stop()
        except Exception as exc:
            finished = False
            cleanup_error = repr(exc)
            if primary is None:
                raise
        finally:
            termination = sys.exc_info()[1] or primary
            interrupted = isinstance(termination, (SystemExit, KeyboardInterrupt))
            pilot.save(ctx.results_dir / 'status.json', {'state': 'interrupted' if interrupted else 'complete' if finished and not failed else 'failed',
                'completed_records': completed, 'planned_records': args.pairs * 2,
                'stopped_reason': stopped_reason, 'error': repr(termination) if termination else None,
                'cleanup_error': cleanup_error,
                'timing_eligible': not args.diagnostic, 'qualification_eligible': False})
