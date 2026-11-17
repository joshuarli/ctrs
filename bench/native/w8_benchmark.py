"""Canonical paired W8 pilot; native execution remains unqualified."""
import hashlib
import json
from pathlib import Path
import secrets
import threading
import traceback

import registry_portfolio
import registry_variant
import runner
from diagnostics import registry_variant_pilot as pilot
from diagnostics.resource_pilot import host_snapshot

FIXTURE = 'w8-paired-v1'
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
    run = 'w8-paired-' + secrets.token_hex(12)
    ctx = runner.RunContext(run)
    ctx.workload_params = {'fixture_version': FIXTURE, 'resource_scope': SCOPE, 'under_load': args.under_load}
    ctx.provenance.update({'w8_source_contract_sha256': runner.sha256_file(runner.FIXTURES / 'w8-v2/portfolio.json'),
                           'w8_driver_sha256': runner.sha256_file(Path(__file__)),
                           'w8_pilot_sha256': runner.sha256_file(Path(pilot.__file__))})
    engines = {name: engine_factory(name, run) for name in ('ctrs', 'orbstack')}
    failed = False
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
                    try:
                        before = gate_fn(directory, 'before')
                        if not before and not args.diagnostic:
                            raise RuntimeError('initial host gate busy; scored trial refused')
                        result = measure(engine, directory, run, contract, portfolio, receipt, layout, server, args.under_load)
                        rec['engine_server_version'] = runner.safe_version(engine)
                        info = runner.safe_engine_info(engine)
                        rec['resources'] = resource_metrics(result)
                        rec['resources']['engine'] = info or {}
                        rec['resources']['detail'] = result.get('resources', {})
                        ok = result.get('correctness') is True and result.get('resources', {}).get('status') == 'ok' and bool(info) and rec['engine_server_version'] != 'unreachable'
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
                    failed |= not rec['correctness']['ok'] or not rec['measurement_valid']
                    print(f"pair {pair} {name}: {'OK' if rec['correctness']['ok'] else 'FAIL'}", flush=True)
            finally:
                if thread.ident is not None:
                    server.shutdown()
                server.server_close()
                if thread.ident is not None:
                    thread.join(timeout=5)
                if thread.is_alive():
                    raise RuntimeError('registry did not terminate')
        print(f'results: {ctx.jsonl}')
        return int(failed)
    finally:
        engines['ctrs'].stop()
