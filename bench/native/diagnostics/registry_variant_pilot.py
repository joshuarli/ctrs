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
import registry_portfolio
import ownership
import resource
import resource_cycles
import runner
from diagnostics.registry_pilot import deploy, save
from diagnostics import w8_under_pull
from diagnostics.resource_pilot import host_snapshot


def require_missing_image(cp):
    if cp.returncode == 0:
        raise ValueError('derived image unexpectedly present before pull')
    if 'no such image:' not in cp.stderr.lower() or cp.stdout.strip() != '[]':
        raise ValueError('cannot establish derived image absence through image API')


def require_layers_transferred(layers, transfers):
    for layer in layers:
        delivered = sum(t['bytes'] for t in transfers if t['digest'] == layer['digest']
                        and t['method'] == 'GET' and t['complete'])
        if delivered < layer['size']:
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


def measure_engine(engine, directory, run, contract, portfolio, receipt, layout, server, under_load=False):
    result = {'correctness': False, 'qualification_eligible': False, 'errors': [], 'pulls': [],
              'resources': {'phases': {}}, 'phase_status': {},
              'pre_content_state': 'unknown below image API; no cache purge'}
    sampler = trace = None
    names = ['pre_pull_setup'] + [f'{kind}_{repository.rsplit("/", 1)[1]}'
        for repository in portfolio.manifests for kind in ('pre_pull_inspection', 'pull_install', 'markers')] + [
        'identity_verification', 'stack_health', 'load_1000', 'persistence_recovery',
        'marked_verification', 'owned_cleanup', 'retained_identity']
    if under_load:
        names += ['under_pull_setup', 'under_pull_verification', 'under_pull_cleanup']
    result['phase_status'] = {phase: {'status': 'partial'} for phase in names}
    try:
        _, api_image = w8_under_pull.baseline_image_reference(engine.name, contract['images']['np-v2/api'])
        prepare_warm_engine(engine, run, api_image=api_image)
        coordinator = ownership.current_coordinator()
        coordinator['owned_service'] = {'kind': 'local-fixture-registry',
            'address': server.server_address, 'fd': server.fileno()}
        sampler, trace = runner.start_sampler(engine, directory, fixture_processes=(coordinator,))
        phase = lambda phase_name: measured_phase(engine, result, phase_name)
        with phase('whole_workflow'):
            refs = {}
            with phase('pre_pull_setup'):
                engine_transfer_start = len(portfolio.transfers)
                old_refs = [w8_under_pull.baseline_image_reference(engine.name, contract['images']['np-v2/' + name])[1]
                            for name in ('api', 'postgres', 'redis', 'marked')]
                retained_before = json.loads(engine.sh(['image', 'inspect', *old_refs]).stdout)
                save(directory / 'retained-before.json', retained_before)
            context = w8_under_pull.baseline(engine, directory, run, contract, phase) if under_load else nullcontext(None)
            with context as load:
                for repository, digest in portfolio.manifests.items():
                    short = repository.rsplit('/', 1)[1]
                    image = receipt['images'][repository]
                    ref = f'127.0.0.1:{server.server_port}/{repository}@{digest}'
                    with phase('pre_pull_inspection_' + short):
                        missing = engine.sh(['image', 'inspect', image['config']], check=False)
                        save(directory / (short + '-pre-image.json'), {
                            'exit': missing.returncode, 'stdout': missing.stdout, 'stderr': missing.stderr})
                        require_missing_image(missing)
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
                        require_layers_transferred(image['layers'], portfolio.transfers[engine_transfer_start:])
                    with phase('markers_' + short):
                        markers = {item['digest']: item for item in receipt['layers']}
                        selected = [markers[layer['digest']] for layer in image['layers']]
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
                result['deployment'] = deploy(engine, refs, layout, directory, run, contract, phase=phase)
            result['pull_to_health_s'] = result['phase_status']['stack_health']['ended_monotonic'] - result['first_pull_monotonic']
            if load is not None:
                result['under_pull_intervals'] = load['intervals']
            with phase('retained_identity'):
                retained_after = json.loads(engine.sh(['image', 'inspect', *old_refs]).stdout)
                save(directory / 'retained-after.json', retained_after)
                if [i['Id'] for i in retained_before] != [i['Id'] for i in retained_after]:
                    raise ValueError('retained image identity changed')
            result['correctness'] = True
    except BaseException:
        result['errors'].append(traceback.format_exc())
    finally:
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
    contract = json.loads((runner.FIXTURES / 'w8-v2/portfolio.json').read_text())
    portfolio = registry_portfolio.prepare_layout(layout, {
        name: image['reference'] for name, image in receipt['images'].items()})
    run = 'w8-unique-' + time.strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(2)
    root = runner.RESULTS / run
    root.mkdir()
    save(root / 'plan.json', {'qualification_eligible': False, 'fixture_version': 'w8-v4-under-pull' if args.under_load else 'w8-v3',
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
