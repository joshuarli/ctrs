"""Short representative W11 mixed cycles; never a qualified reliability or speed result."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import diagnostic_signals
import mixed_cycle
import registry_portfolio
import runner
from resource_pilot import host_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portfolio-layout', type=Path, required=True)
    parser.add_argument('--worker-layout', type=Path, required=True)
    parser.add_argument('--ctrs-binary', type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--cycles', type=int, choices=(1, 2, 3))
    modes.add_argument('--work-deadline-epoch', type=float)
    parser.add_argument('--drain-deadline-epoch', type=float)
    parser.add_argument('--qualification', action='store_true')
    parser.add_argument('--engines', default='ctrs,orbstack')
    args = parser.parse_args()
    if args.qualification:
        parser.error('qualification refused: frozen candidate, assets, workload, final matrix and readiness evidence schema/proof are missing; 12-hour qualification is not authorized')
    if args.work_deadline_epoch is not None:
        if args.drain_deadline_epoch is None or not time.time() < args.work_deadline_epoch < args.drain_deadline_epoch:
            parser.error('duration requires future work and later drain deadlines')
        if ',' in args.engines:
            parser.error('duration requires exactly one engine')
        work_deadline = time.monotonic() + args.work_deadline_epoch - time.time()
        drain_deadline = time.monotonic() + args.drain_deadline_epoch - time.time()
    else:
        if args.drain_deadline_epoch is not None:
            parser.error('drain deadline requires duration mode')
        args.cycles = args.cycles or 2
        work_deadline = drain_deadline = None
    engines = args.engines.split(',')
    if len(set(engines)) != len(engines) or any(name not in ('ctrs', 'orbstack') for name in engines):
        parser.error('require distinct supported engines')
    if sys.platform != 'darwin' or os.uname().machine != 'arm64':
        parser.error('native ARM64 macOS only')
    diagnostic_signals.install_cleanup_signals()
    runner.DOCKER = runner.find_docker()
    runner.CTRS_BIN = args.ctrs_binary.resolve()
    common = registry_portfolio.prepare_pinned_portfolio(args.portfolio_layout, mixed_cycle.PIN)
    pin = mixed_cycle.WORKER['worker']
    worker = registry_portfolio.prepare_layout(args.worker_layout, {pin['repository']: pin['layout_reference']})
    if worker.manifests != {pin['repository']: pin['manifest']}:
        raise ValueError('worker manifest differs from pin')
    manifest = json.loads(worker.routes[(pin['repository'], 'manifests', pin['manifest'])][2].metadata())
    config_blob = worker.routes[(pin['repository'], 'blobs', pin['config'])][2]
    if manifest['config']['digest'] != pin['config'] or json.loads(config_blob.metadata())['rootfs']['diff_ids'] != pin['diff_ids']:
        raise ValueError('worker config or diff IDs differ from pin')
    if set(common.routes) & set(worker.routes):
        raise ValueError('registry route collision')
    portfolio = registry_portfolio.Portfolio(common.routes | worker.routes, common.manifests | worker.manifests)
    run_id = 'w11-mixed-' + time.strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(2)
    ctx = runner.RunContext(run_id)
    ctx.design = 'mixed-functional-diagnostic'
    root = ctx.results_dir
    sources = root / 'source'; sources.mkdir()
    source_paths = (Path(__file__), Path(mixed_cycle.__file__), Path(runner.__file__), Path(registry_portfolio.__file__),
                    runner.BENCH / 'ci_jobs.py', runner.LOAD_PY, runner.FIXTURES / 'w4/app.py',
                    runner.FIXTURES / 'w8-v2/portfolio.json', runner.FIXTURES / 'w11-v2/worker-pin.json')
    hashes = {}
    for index, path in enumerate(source_paths):
        target = sources / f'{index}-{path.name}'; target.write_bytes(path.read_bytes())
        hashes[target.name] = runner.sha256_file(target)
    mixed_cycle.save(root / 'plan.json', {'fixture_version': mixed_cycle.VERSION, 'cycles': args.cycles,
        'work_deadline_epoch': args.work_deadline_epoch, 'drain_deadline_epoch': args.drain_deadline_epoch,
        'operations_per_cycle': mixed_cycle.OPERATIONS, 'source_sha256': hashes,
        'qualification_eligible': False, 'reason': 'short functional diagnostic; no frozen candidate, exclusivity or growth verdict',
        'comparison_label': 'functional capacity-disclosed diagnostic; allocation equality not asserted', 'manifests': portfolio.manifests,
        'resources': {'ctrs_cpus': os.environ.get('CTRS_CPUS'), 'ctrs_memory_mib': os.environ.get('CTRS_MEMORY_MIB')}})
    print('RESULTS', root, flush=True)
    server = registry_portfolio.serve(portfolio, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05})
    try:
        thread.start()
        refs = {repository.rsplit('/', 1)[1]: f'127.0.0.1:{server.server_port}/{repository}@{digest}' for repository, digest in common.manifests.items()}
        refs['worker'] = f'127.0.0.1:{server.server_port}/{pin["repository"]}@{pin["manifest"]}'
        mixed_cycle.validate_refs(refs)
        for name in engines:
            engine = runner.Engine(name, run_id)
            before = root / (name + '-host'); before.mkdir()
            host_snapshot(before, 'before')
            try:
                engine.ensure_up()
                for image, ref in refs.items():
                    cp = engine.sh(['pull', ref], timeout=180, check=False)
                    (before / (image + '-pull.log')).write_text(cp.stdout + cp.stderr)
                    if cp.returncode:
                        raise RuntimeError('pinned image preparation failed: ' + image)
                mixed_cycle.save(before / 'refs.json', refs)
                rec = mixed_cycle.run(engine, ctx, refs, args.cycles, work_deadline=work_deadline, drain_deadline=drain_deadline)
                ctx.write(rec)
                print(name, 'exact mixed cycles', len(rec['cycles']), flush=True)
            finally:
                try:
                    engine.stop()
                finally:
                    host_snapshot(before, 'after')
    finally:
        if thread.ident is not None:
            server.shutdown()
        server.server_close()
        if thread.ident is not None:
            thread.join(timeout=5)
        mixed_cycle.save(root / 'transfers.json', portfolio.transfers)
        if thread.is_alive():
            raise RuntimeError('registry server did not stop')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
