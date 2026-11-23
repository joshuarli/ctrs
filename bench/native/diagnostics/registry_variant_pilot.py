"""Verify complete derived W8 transfers and exact native application outputs."""
import argparse
from contextlib import contextmanager, nullcontext
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ci_jobs
import diagnostic_signals
import mixed_resources
import registry_portfolio
import registry_variant
import ownership
import resource
import resource_cycles
import runner
from diagnostics.registry_pilot import deploy, save
from diagnostics import w8_under_pull
from diagnostics.resource_pilot import host_snapshot

ALLOCATION_IDLE_SECONDS = 10


def require_missing_image(cp):
    if cp.returncode == 0:
        raise ValueError('derived image unexpectedly present before pull')
    if 'no such image:' not in cp.stderr.lower() or cp.stdout.strip() != '[]':
        raise ValueError('cannot establish derived image absence through image API')


def require_variant_absent(engine, image, receipt_path):
    kind, reference = w8_under_pull.baseline_image_reference(engine.name, image)
    missing = engine.sh(['image', 'inspect', reference], check=False)
    save(receipt_path, {'reference_kind': kind, 'reference': reference,
        'exit': missing.returncode, 'stdout': missing.stdout, 'stderr': missing.stderr})
    require_missing_image(missing)


def require_layers_transferred(layers, transfers):
    complete_gets = {(row['digest'], row['bytes']) for row in transfers
                     if row['method'] == 'GET' and row['complete'] is True}
    for layer in layers:
        if (layer['digest'], layer['size']) not in complete_gets:
            raise ValueError('layer not transferred completely: ' + layer['digest'])


@contextmanager
def measured_phase(engine, result, name):
    phase = result['phase_status'].setdefault(name, {'status': 'partial'})
    phase['status'] = 'partial'
    context = None
    entered = False
    children_before = None
    try:
        try:
            children_before = resource.getrusage(resource.RUSAGE_CHILDREN)
            context = runner.resource_phase(engine, result, name)
            context.__enter__()
            entered = True
        except Exception:
            phase['measurement_error'] = traceback.format_exc()
        try:
            yield
        except BaseException:
            phase['status'] = 'failed'
            raise
        else:
            phase['status'] = 'complete'
    finally:
        phase['ended_monotonic'] = time.monotonic()
        phase['waited_child_cpu_seconds'] = None
        try:
            if children_before is not None:
                children_after = resource.getrusage(resource.RUSAGE_CHILDREN)
                delta = (children_after.ru_utime + children_after.ru_stime -
                         children_before.ru_utime - children_before.ru_stime)
                if delta < 0:
                    raise ValueError('waited-child CPU counter decreased')
                phase['waited_child_cpu_seconds'] = delta
        except Exception:
            phase['measurement_error'] = traceback.format_exc()
        phase['child_cpu_scope'] = 'children reaped during phase; excludes still-live children; not a phase-aligned all-client total'
        if entered:
            try:
                context.__exit__(None, None, None)
            except Exception:
                phase['measurement_error'] = traceback.format_exc()


def summarize_resources(result, engine, trace):
    resources = result['resources']
    if runner.linux_lane.enabled():
        resources.update(runner.summarize_trace(trace) if trace else {})
        resources['trace'] = str(trace) if trace is not None else None
        resources['ownership'] = getattr(engine, 'measurement_identity', None)
        complete = all(phase['status'] == 'complete' and not phase.get('measurement_error')
                       for phase in result['phase_status'].values())
        resources['status'] = 'ok' if resources.get('ownership_verified') and complete else 'unknown'
        return
    resources['trace'] = str(trace) if trace is not None else None
    resources['ownership'] = getattr(engine, 'measurement_identity', None)
    resources['phase_summaries'] = {}
    try:
        samples = [json.loads(line) for line in trace.read_text().splitlines()] if trace else []
        manifest = resources['ownership'] or {}
        for name, status in result['phase_status'].items():
            raw = resources['phases'].get(name)
            if raw and status['status'] == 'complete' and not status.get('measurement_error'):
                resources['phase_summaries'][name] = resource_cycles.phase_summary(manifest, raw, samples)
            else:
                resources['phase_summaries'][name] = {'status': 'unknown', 'cpu_seconds': None,
                    'steady_phys_footprint_bytes': None, 'peak_phys_footprint_bytes': None,
                    'errors': ['phase boundaries unavailable']}
    except Exception:
        resources['summary_error'] = traceback.format_exc()
    for name in result['phase_status']:
        if (result['phase_status'][name]['status'] != 'complete' or
                result['phase_status'][name].get('measurement_error')) and name in resources['phases']:
            resources['phases'][name]['cpu_seconds'] = None
        resources['phase_summaries'].setdefault(name, {'status': 'unknown', 'cpu_seconds': None,
            'steady_phys_footprint_bytes': None, 'peak_phys_footprint_bytes': None,
            'errors': ['resource summary unavailable']})
    resources['status'] = ('ok' if result['phase_status'] and all(v['status'] == 'ok' for v in resources['phase_summaries'].values())
                           and all(v['status'] == 'complete' for v in result['phase_status'].values()) else 'unknown')


def finish_engine(result, engine, sampler, trace, directory, *, stop=True):
    try:
        try:
            if sampler is not None:
                runner.stop_sampler(sampler)
        except Exception:
            result['errors'].append(traceback.format_exc())
            result['resources']['sampler_error'] = traceback.format_exc()
        try:
            summarize_resources(result, engine, trace)
        except Exception:
            result['errors'].append(traceback.format_exc())
            result['resources']['status'] = 'unknown'
        if result['resources'].get('sampler_error'):
            result['resources']['status'] = 'unknown'
            for raw in result['resources']['phases'].values():
                raw['cpu_seconds'] = None
            for cell in result['resources'].get('phase_summaries', {}).values():
                cell.update(status='unknown', cpu_seconds=None, user_cpu_seconds=None,
                    system_cpu_seconds=None, cpu_cores=None, steady_phys_footprint_bytes=None,
                    peak_phys_footprint_bytes=None)
        if result['resources'].get('status') != 'ok':
            result['correctness'] = False
    finally:
        try:
            if stop:
                engine.stop()
        except BaseException:
            result['errors'].append(traceback.format_exc())
            result['correctness'] = False
            raise
        finally:
            try:
                host_snapshot(directory, 'after')
            finally:
                save(directory / 'result.json', result)


def require_valid_result(result):
    if not result['correctness'] or result['resources'].get('status') != 'ok':
        raise RuntimeError('W8 integrity or resource coverage failed; retain the failed run')


def prepare_warm_engine(engine, run, *, api_image):
    engine.ensure_up()
    container = runner.project_name(run, engine.name, 'warm')
    try:
        cp = engine.sh(['run', '--rm', '--pull=never', '--name', container,
            '--label', 'dev.ctrs.campaign.run=' + run,
            api_image, 'python', '-c', "print('np-w8-warm')"], timeout=90)
        if cp.stdout.strip() != 'np-w8-warm':
            raise RuntimeError('warm-engine preconditioning did not complete')
    finally:
        ci_jobs.cleanup(engine, container, run)


def allocation_receipt(snapshots):
    stages = ('before_pull_idle', 'before_pull', 'before_app_cleanup',
              'after_app_cleanup', 'after_cleanup_idle')
    receipt = {'status': 'unknown', 'snapshots': snapshots,
               'deployment_delta_bytes': None, 'after_app_cleanup_delta_bytes': None,
               'exclusive_deployment_delta_bytes': None, 'exclusive_after_app_cleanup_delta_bytes': None,
               'idle_deltas': None}
    if any(snapshots.get(stage, {}).get('status') != 'ok' for stage in stages):
        receipt['error'] = 'missing or invalid owned allocation snapshot'
        return receipt
    early, before, deployed, cleaned, settled = (snapshots[stage] for stage in stages)
    identities = [[(entry['path'], entry['device'], entry['inode']) for entry in snapshot['files']]
                  for snapshot in (early, before, deployed, cleaned, settled)]
    if not identities[0] or any(identity != identities[0] for identity in identities[1:]):
        receipt['error'] = 'owned backing file identity changed between snapshots'
        return receipt
    idle = {}
    for name, start, end in (('before_pull', early, before), ('after_app_cleanup', cleaned, settled)):
        private = None
        if start.get('exclusive_allocation_status') == end.get('exclusive_allocation_status') == 'ok':
            private = end['exclusive_allocated_bytes'] - start['exclusive_allocated_bytes']
        idle[name] = {'allocated_bytes': end['allocated_bytes'] - start['allocated_bytes'],
                      'exclusive_allocated_bytes': private}
    receipt.update(status='ok',
                   deployment_delta_bytes=deployed['allocated_bytes'] - before['allocated_bytes'],
                   after_app_cleanup_delta_bytes=cleaned['allocated_bytes'] - before['allocated_bytes'],
                   idle_deltas=idle)
    if all(s.get('exclusive_allocation_status') == 'ok' for s in (before, deployed, cleaned)):
        baseline = before['exclusive_allocated_bytes']
        receipt.update(exclusive_deployment_delta_bytes=deployed['exclusive_allocated_bytes'] - baseline,
                       exclusive_after_app_cleanup_delta_bytes=cleaned['exclusive_allocated_bytes'] - baseline)
    return receipt


def measure_engine(engine, directory, run, contract, portfolio, receipt, layout, server,
                   under_load=False, *, orbstack_storage_files=()):
    result = {'correctness': False, 'workload_correct': False, 'qualification_eligible': False, 'errors': [], 'pulls': [],
              'resources': {'phases': {}}, 'phase_status': {},
              'pre_content_state': 'unknown below image API; no cache purge'}
    sampler = trace = None
    snapshots = {}
    names = ['pre_pull_setup'] + [f'{kind}_{repository.rsplit("/", 1)[1]}'
        for repository in portfolio.manifests for kind in ('pre_pull_inspection', 'pull_install', 'markers')] + [
        'identity_verification', 'stack_health', 'load_1000', 'persistence_recovery',
        'marked_verification', 'owned_cleanup', 'retained_identity']
    if under_load:
        names += ['under_pull_setup', 'under_pull_verification', 'under_pull_cleanup']
    result['phase_status'] = {phase: {'status': 'partial'} for phase in names}
    try:
        _, api_image = w8_under_pull.baseline_image_reference(engine.name, contract['images']['np-v6/api'])
        prepare_warm_engine(engine, run, api_image=api_image)
        if runner.linux_lane.enabled():
            sampler, trace = runner.start_sampler(engine, directory)
        else:
            coordinator = ownership.current_coordinator()
            coordinator['owned_service'] = {'kind': 'local-fixture-registry',
                'address': server.server_address, 'fd': server.fileno()}
            sampler, trace = runner.start_sampler(engine, directory, fixture_processes=(coordinator,))
        phase = lambda phase_name: measured_phase(engine, result, phase_name)
        if orbstack_storage_files:
            paths = ((engine.dir / 'data/vm/data.img',) if engine.name == 'ctrs'
                     else tuple(path.absolute() for path in orbstack_storage_files))
            manifest = dict(engine.measurement_identity)
            manifest['required_processes'] = [process for process in manifest['required_processes']
                                              if process['role'] != 'fixture-coordinator']

            def snapshot(stage):
                try:
                    snapshots[stage] = mixed_resources.allocation(manifest, paths, include_private=True)
                except Exception as exc:
                    snapshots[stage] = {'status': 'unknown', 'errors': [str(exc)]}

            def snapshot_idle(stage, inventory_file):
                inventory = engine.sh(['ps', '--no-trunc', '--format', '{{json .}}']).stdout
                (directory / inventory_file).write_text(inventory)
                if inventory.strip():
                    raise ValueError(f'running containers present at W8 allocation boundary {stage}')
                snapshot(stage)

            @contextmanager
            def deployment_phase(phase_name):
                with phase(phase_name):
                    yield
                if phase_name == 'marked_verification':
                    snapshot('before_app_cleanup')
        else:
            deployment_phase = phase
        relays_before = runner.relay_counts(engine)
        markers = {item['digest']: item for item in receipt['layers']}
        with phase('whole_workflow'):
            refs = {}
            with phase('pre_pull_setup'):
                engine_transfer_start = len(portfolio.transfers)
                retained_pins = {name: contract['images']['np-v6/' + name]
                                 for name in ('api', 'postgres', 'redis', 'marked')}
                old_refs = [w8_under_pull.baseline_image_reference(engine.name, pin)[1]
                            for pin in retained_pins.values()]
                retained_before = json.loads(engine.sh(['image', 'inspect', *old_refs]).stdout)
                save(directory / 'retained-before.json', retained_before)
                w8_under_pull.require_baseline_images(engine.name, retained_pins, retained_before)
                if orbstack_storage_files:
                    snapshot_idle('before_pull_idle', 'containers-before-idle.jsonl')
                    time.sleep(ALLOCATION_IDLE_SECONDS)
                    snapshot_idle('before_pull', 'containers-before.jsonl')
            context = w8_under_pull.baseline(engine, directory, run, contract, phase) if under_load else nullcontext(None)
            with context as load:
                for repository, digest in portfolio.manifests.items():
                    short = repository.rsplit('/', 1)[1]
                    image = receipt['images'][repository]
                    changed_layers = [layer for layer in image['layers'] if layer['digest'] in markers]
                    if not changed_layers or (receipt['fixture_version'] != registry_variant.RETAINED_VERSION
                                              and len(changed_layers) != len(image['layers'])):
                        raise ValueError('missing changed layer markers')
                    selected = [markers[layer['digest']] for layer in changed_layers]
                    ref = f'127.0.0.1:{server.server_port}/{repository}@{digest}'
                    with phase('pre_pull_inspection_' + short):
                        require_variant_absent(engine, image, directory / (short + '-pre-image.json'))
                    with phase('pull_install_' + short):
                        begin = len(portfolio.transfers)
                        if load is not None and load['process'].poll() is not None:
                            raise RuntimeError('client finished before pull')
                        interval = {'name': short}
                        try:
                            remaining = load['deadline_monotonic'] - time.monotonic() if load is not None else 240
                            if remaining <= 0:
                                raise TimeoutError('client deadline expired before pull')
                            interval['begin_monotonic'] = time.monotonic()
                            result.setdefault('first_pull_monotonic', interval['begin_monotonic'])
                            cp = engine.sh(['pull', ref], timeout=min(240, remaining), check=False)
                        finally:
                            interval['end_monotonic'] = time.monotonic()
                            if load is not None and 'begin_monotonic' in interval:
                                load['intervals'].append(interval)
                        transfers = portfolio.transfers[begin:]
                        result['pulls'].append({'ref': ref, 'exit': cp.returncode,
                            'stdout': cp.stdout, 'stderr': cp.stderr, 'transfers': transfers})
                        if cp.returncode:
                            raise ValueError('pull failed')
                        require_layers_transferred(changed_layers, portfolio.transfers[engine_transfer_start:])
                    with phase('markers_' + short):
                        container = runner.project_name(run, engine.name, 'marker-' + short)
                        try:
                            marker_output = engine.sh(['run', '--rm', '--name', container, '--pull=never',
                                '--label', 'dev.ctrs.campaign.run=' + run, '--entrypoint', 'cat', ref,
                                *['/' + item['marker'] for item in selected]], timeout=90).stdout
                            if marker_output != ''.join(receipt['seed_sha256'] + '\n' +
                                    item['source_diff_id'] + '\n' for item in selected):
                                raise ValueError('installed marker contents differ')
                        finally:
                            ci_jobs.cleanup(engine, container, run)
                    refs[short] = ref
                    save(directory / 'result.json', result)
                result['deployment'] = deploy(engine, refs, layout, directory, run, contract, phase=deployment_phase)
            result['pull_to_health_s'] = result['phase_status']['stack_health']['ended_monotonic'] - result['first_pull_monotonic']
            if load is not None:
                result['under_pull_intervals'] = load['intervals']
            with phase('retained_identity'):
                if orbstack_storage_files:
                    snapshot_idle('after_app_cleanup', 'containers-after.jsonl')
                retained_after = json.loads(engine.sh(['image', 'inspect', *old_refs]).stdout)
                save(directory / 'retained-after.json', retained_after)
                w8_under_pull.require_baseline_images(engine.name, retained_pins, retained_after)
            result['workload_correct'] = True
            result['correctness'] = True
        if engine.name == 'ctrs':
            result['cpu_accounting'] = runner.cpu_accounting(
                relays_before, runner.relay_counts(engine) if relays_before is not None else None)
        if orbstack_storage_files:
            time.sleep(ALLOCATION_IDLE_SECONDS)
            snapshot_idle('after_cleanup_idle', 'containers-after-idle.jsonl')
    except BaseException as exc:
        result['errors'].append(traceback.format_exc())
        if not isinstance(exc, Exception):
            raise
    finally:
        if orbstack_storage_files:
            result['allocation'] = allocation_receipt(snapshots)
            if result['allocation']['status'] != 'ok':
                result['errors'].append(result['allocation']['error'])
        finish_engine(result, engine, sampler, trace, directory, stop=False)

    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layout', type=Path, required=True)
    parser.add_argument('--ctrs-binary', type=Path, required=True)
    parser.add_argument('--under-load', action='store_true')
    args = parser.parse_args()
    if sys.platform != 'darwin' or os.uname().machine != 'arm64':
        parser.error('native ARM64 macOS only')
    runner.DOCKER = runner.find_docker()
    runner.CTRS_BIN = args.ctrs_binary.resolve()
    diagnostic_signals.install_cleanup_signals()
    layout = args.layout.resolve()
    receipt = json.loads((layout / 'receipt.json').read_text())
    contract = json.loads((runner.FIXTURES / 'w8-v6/portfolio.json').read_text())
    portfolio = registry_portfolio.prepare_layout(layout, {
        name: image['reference'] for name, image in receipt['images'].items()})
    run = 'w8-unique-' + time.strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(2)
    root = runner.RESULTS / run
    root.mkdir()
    save(root / 'plan.json', {'qualification_eligible': False, 'fixture_version': 'w8-v4-under-pull' if args.under_load else registry_variant.DERIVED_VERSION,
        'receipt': receipt, 'reason': 'functional resource diagnostic; timing and guest pre-content absence unqualified',
        'resource_scope_version': 'w8-engine-fixture-v1',
        'resource_scope': 'warm engine plus native registry/coordinator process; excludes boot/preconditioning, CLI footprint, sampler and active backing allocation; waited-child CPU disclosed separately'})
    (root / 'driver.py').write_bytes(Path(__file__).read_bytes())
    server = registry_portfolio.serve(portfolio, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05})
    print('RESULTS', root, flush=True)
    try:
        thread.start()
        for name in ('ctrs', 'orbstack'):
            directory = root / name
            directory.mkdir()
            engine = runner.Engine(name, run)
            try:
                host_snapshot(directory, 'before')
                result = measure_engine(engine, directory, run, contract, portfolio, receipt, layout, server, args.under_load)
            finally:
                engine.stop()
            require_valid_result(result)
            print(name, 'PASS full transfers, exact data and engine resource phases', flush=True)
    finally:
        if thread.ident is not None:
            server.shutdown()
        server.server_close()
        thread.join(timeout=5) if thread.ident is not None else None
        save(root / 'transfers.json', portfolio.transfers)
        if thread.is_alive():
            raise RuntimeError('registry did not terminate')


if __name__ == '__main__':
    main()
