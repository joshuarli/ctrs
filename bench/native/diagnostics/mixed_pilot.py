"""Representative mixed cycles with explicit frozen-evidence qualification admission."""
import argparse
import json
import os
import platform
from pathlib import Path
import secrets
import sys
import subprocess
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import diagnostic_signals
import mixed_cycle
import registry_portfolio
import runner
import qualification
import durable_job
from diagnostics.resource_pilot import host_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portfolio-layout', type=Path, required=True)
    parser.add_argument('--worker-layout', type=Path, required=True)
    parser.add_argument('--ctrs-binary', type=Path, required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--cycles', type=int, choices=(1, 2, 3))
    modes.add_argument('--work-deadline-epoch', type=float)
    parser.add_argument('--drain-deadline-epoch', type=float)
    parser.add_argument('--cleanup-deadline-epoch', type=float)
    parser.add_argument('--expected-boot-assets', type=json.loads)
    parser.add_argument('--ctrs-root', type=Path)
    parser.add_argument('--qualification', action='store_true')
    parser.add_argument('--readiness', type=Path, help='frozen reviewed evidence declaration required for qualification')
    parser.add_argument('--resource-observation-seconds', type=float,
                        help='observe owned resources after each cycle; qualification requires at least 30 seconds')
    parser.add_argument('--orbstack-storage-file', type=Path, action='append', default=[],
                        help='explicit open OrbStack backing file; repeat for each file, otherwise storage stays unknown')
    parser.add_argument('--engines', default='ctrs,orbstack')
    args = parser.parse_args()
    if args.qualification and args.readiness is None:
        parser.error('qualification refused: --readiness must identify frozen candidate, assets, workload, final matrix and readiness evidence')
    if args.readiness is not None and not args.qualification:
        parser.error('--readiness requires --qualification')
    if args.orbstack_storage_file and args.resource_observation_seconds is None:
        parser.error('--orbstack-storage-file requires --resource-observation-seconds')
    if args.resource_observation_seconds is not None:
        try:
            mixed_cycle.mixed_resources.plan({'seconds': args.resource_observation_seconds}, {})
        except ValueError as exc:
            parser.error(str(exc))
        if not args.qualification and args.resource_observation_seconds > 60:
            parser.error('diagnostic resource observations are limited to 60 seconds; long runs require qualification')
    if args.work_deadline_epoch is not None:
        if args.drain_deadline_epoch is None or args.cleanup_deadline_epoch is None or not time.time() < args.work_deadline_epoch < args.drain_deadline_epoch < args.cleanup_deadline_epoch:
            parser.error('duration requires future work and later drain deadlines')
        if ',' in args.engines:
            parser.error('duration requires exactly one engine')
        if args.engines == 'ctrs' and args.ctrs_root is None:
            parser.error('ctrs duration requires a new isolated root')
        work_deadline = time.monotonic() + args.work_deadline_epoch - time.time()
        if not args.qualification and args.work_deadline_epoch - time.time() > qualification.MAX_DIAGNOSTIC_WORK_SECONDS:
            parser.error('diagnostic work is limited to fifteen minutes; long runs require frozen qualification')
        drain_deadline = time.monotonic() + args.drain_deadline_epoch - time.time()
        cleanup_deadline = time.monotonic() + args.cleanup_deadline_epoch - time.time()
    else:
        if args.drain_deadline_epoch is not None or args.cleanup_deadline_epoch is not None:
            parser.error('drain deadline requires duration mode')
        args.cycles = args.cycles or 2
        work_deadline = drain_deadline = cleanup_deadline = None
    engines = args.engines.split(',')
    if len(set(engines)) != len(engines) or any(name not in ('ctrs', 'orbstack') for name in engines):
        parser.error('require distinct supported engines')
    if sys.platform != 'darwin' or os.uname().machine != 'arm64':
        parser.error('native ARM64 macOS only')
    frozen = None
    readiness_receipt = None
    resource_environment = {}
    admission_epoch = time.time()
    assets = runner.BENCH / 'assets.lock'
    frozen_paths = []
    if args.qualification:
        if work_deadline is None or args.work_deadline_epoch - time.time() < qualification.MINIMUM_WORK_SECONDS:
            parser.error('qualification requires a finite work deadline at least twelve hours away, plus setup allowance')
        if args.resource_observation_seconds is None or args.resource_observation_seconds < 30:
            parser.error('qualification requires --resource-observation-seconds of at least 30')
        if 'orbstack' in engines and not args.orbstack_storage_file:
            parser.error('qualification requires explicit --orbstack-storage-file coverage')
        if 'ctrs' in engines and args.ctrs_root.exists():
            parser.error('qualification requires a new isolated --ctrs-root')
        try:
            guest = Path(os.environ['CTRS_GUEST_DIR'])
            template = guest / 'data.img'
            frozen_paths = [Path(sys.executable), args.ctrs_binary, guest / 'Image', guest / 'initramfs.cpio', template,
                            runner.COMPOSE_FILE, runner.FIXTURES / 'w1/seed.sql', runner.LOAD_PY,
                            runner.FIXTURES / 'w4/app.py', runner.FIXTURES / 'w8-v2/portfolio.json',
                            runner.FIXTURES / 'w11-v2/worker-pin.json', runner.CASES_FILE, assets]
            frozen_paths += [path for path in runner.BENCH.glob('*.py') if not path.name.startswith('test_')]
            frozen_paths += list((runner.BENCH / 'diagnostics').glob('*.py'))
            for layout in (args.portfolio_layout, args.worker_layout):
                frozen_paths += [path for path in layout.rglob('*') if path.is_file()]
            readiness_receipt = durable_job.receipt(args.readiness)
            frozen = qualification.require_readiness(args.readiness, required_paths=frozen_paths,
                                                    assets_path=assets, sparse_paths=(template,), admission_epoch=admission_epoch)
            durable_job.check_receipt(readiness_receipt)
            if frozen['fixtures']['W11']['version'] != mixed_cycle.mixed_resources.VERSION:
                raise qualification.ReadinessError('W11 fixture version differs from the observation runner')
            expected = {'ctrs_binary': args.ctrs_binary, 'guest_kernel': guest / 'Image',
                        'guest_initramfs': guest / 'initramfs.cpio'}
            if any(frozen['artifacts'][key]['path'] != str(path.resolve(strict=True)) for key, path in expected.items()):
                raise qualification.ReadinessError('requested running artifacts differ from the freeze')
            if (frozen['tools']['python']['version'] != platform.python_version()
                    or frozen['tools']['python']['artifact']['path'] != str(Path(sys.executable).resolve())):
                raise qualification.ReadinessError('running Python differs from the freeze')
            boot = {item['path']: {'inode': item['identity'][1], 'size': item['identity'][2], 'sha256': item['sha256']}
                    for key, item in frozen['artifacts'].items() if key != 'ctrs_binary'}
            if args.expected_boot_assets is not None and args.expected_boot_assets != boot:
                raise qualification.ReadinessError('--expected-boot-assets differs from the freeze')
            args.expected_boot_assets = boot
            allowed = {'CTRS_GUEST_DIR', 'CTRS_CPUS', 'CTRS_MEMORY_MIB'}
            if any(key.startswith('CTRS_') and key not in allowed for key in os.environ):
                raise qualification.ReadinessError('undeclared CTRS environment overrides prevent qualification')
            for key, field in (('CTRS_CPUS', 'ctrs_cpus'), ('CTRS_MEMORY_MIB', 'ctrs_memory_mib')):
                value = str(frozen['comparison'][field])
                if key in os.environ and os.environ[key] != value:
                    raise qualification.ReadinessError(key + ' differs from the frozen resource budget')
                resource_environment[key] = value
        except (OSError, KeyError, ValueError) as exc:
            parser.error('qualification refused: ' + str(exc))
    diagnostic_signals.install_cleanup_signals()
    os.environ.update(resource_environment)
    runner.DOCKER = runner.find_docker()
    if frozen is not None and str(Path(runner.DOCKER).resolve()) != frozen['tools']['docker']['artifact']['path']:
        parser.error('running Docker CLI differs from the freeze')
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
    ctx.design = 'mixed-functional-diagnostic' if frozen is None else 'mixed-qualification'
    root = ctx.results_dir
    sources = root / 'source'; sources.mkdir()
    source_paths = (Path(__file__), Path(mixed_cycle.__file__), Path(runner.__file__), Path(registry_portfolio.__file__),
                    Path(qualification.__file__), Path(mixed_cycle.mixed_resources.__file__),
                    runner.BENCH / 'resource_cycles.py', runner.COLLECT, runner.BENCH / 'macos_counters.py', runner.BENCH / 'ownership.py',
                    runner.BENCH / 'ci_jobs.py', runner.LOAD_PY, runner.FIXTURES / 'w4/app.py',
                    runner.FIXTURES / 'w8-v2/portfolio.json', runner.FIXTURES / 'w11-v2/worker-pin.json')
    hashes = {}
    for index, path in enumerate(source_paths):
        target = sources / f'{index}-{path.name}'; target.write_bytes(path.read_bytes())
        hashes[target.name] = runner.sha256_file(target)
    mixed_cycle.save(root / 'plan.json', {'fixture_version': mixed_cycle.VERSION if args.resource_observation_seconds is None else mixed_cycle.mixed_resources.VERSION, 'cycles': args.cycles,
        'work_deadline_epoch': args.work_deadline_epoch, 'drain_deadline_epoch': args.drain_deadline_epoch,
        'operations_per_cycle': mixed_cycle.OPERATIONS, 'source_sha256': hashes,
        'resource_observation_seconds': args.resource_observation_seconds,
        'readiness_admitted': frozen is not None,
        'readiness': frozen,
        'readiness_receipt': readiness_receipt,
        'admission_epoch': admission_epoch,
        'retention': {'seed_rows': 500, 'persistent_record': 'mixed-committed=exact-v3',
                      'transient_rows': 'verify all acknowledged writes, explicitly delete them, verify exact seed',
                      'volume': 'same named volume throughout; removed only during final owned cleanup'},
        'qualification_eligible': False,
        'reason': ('functional diagnostic; no qualification verdict' if frozen is None
                   else 'frozen leg admitted; completed hard checks and independent review still required'),
        'comparison_label': ('functional capacity-disclosed diagnostic; allocation equality not asserted' if frozen is None
                             else frozen['comparison']['label']), 'manifests': portfolio.manifests,
        'resources': {'ctrs_cpus': os.environ.get('CTRS_CPUS'), 'ctrs_memory_mib': os.environ.get('CTRS_MEMORY_MIB')}})
    print('RESULTS', root, flush=True)
    server = registry_portfolio.serve(portfolio, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05})
    outcome = {'status': 'failed', 'cleanup_errors': [], 'error': None}
    try:
        thread.start()
        refs = {repository.rsplit('/', 1)[1]: f'127.0.0.1:{server.server_port}/{repository}@{digest}' for repository, digest in common.manifests.items()}
        refs['worker'] = f'127.0.0.1:{server.server_port}/{pin["repository"]}@{pin["manifest"]}'
        mixed_cycle.validate_refs(refs)
        for name in engines:
            engine = runner.Engine(name, run_id, fresh_dir=args.ctrs_root) if name == 'ctrs' else runner.Engine(name, run_id)
            before = root / (name + '-host'); before.mkdir()
            host_snapshot(before, 'before')
            try:
                engine.ensure_up()
                tooling = runner.tool_provenance(engine)
                mixed_cycle.save(before / 'tools.json', tooling)
                if frozen is not None:
                    admission_gate = json.loads((before / 'before-gate.json').read_text())
                    if admission_gate.get('exit') != 0:
                        raise qualification.ReadinessError('performance gate prevents qualification admission')
                    containers = engine.sh(['ps', '--no-trunc', '--format', '{{json .}}']).stdout
                    (before / 'containers-at-admission.jsonl').write_text(containers)
                    host_policy = json.loads(Path(frozen['prerequisites']['host_conditions']['evidence']['path']).read_text())
                    if containers.strip() and host_policy['conclusion'] == 'exclusive':
                        raise qualification.ReadinessError('active containers contradict the exclusive host declaration')
                    if engine.server_version() != frozen['engine_versions'][name]:
                        raise qualification.ReadinessError('running engine version differs from the freeze: ' + name)
                    for tool in runner.TOOL_CONTRACTS:
                        if tooling[tool] != frozen['tools'][tool]:
                            raise qualification.ReadinessError('running tool differs from the freeze: ' + tool)
                for image, ref in refs.items():
                    cp = engine.sh(['pull', ref], timeout=180, check=False)
                    (before / (image + '-pull.log')).write_text(cp.stdout + cp.stderr)
                    if cp.returncode:
                        raise RuntimeError('pinned image preparation failed: ' + image)
                mixed_cycle.save(before / 'refs.json', refs)
                observation = None
                if args.resource_observation_seconds is not None:
                    paths = (engine.dir / 'data/vm/data.img',) if name == 'ctrs' else tuple(path.absolute() for path in args.orbstack_storage_file)
                    observation = {'seconds': args.resource_observation_seconds, 'owned_files': paths}
                rec = mixed_cycle.run(engine, ctx, refs, args.cycles, work_deadline=work_deadline,
                    drain_deadline=drain_deadline, cleanup_deadline=cleanup_deadline,
                    expected_boot_assets=args.expected_boot_assets if name == 'ctrs' else None, observation=observation,
                    expected_resources=frozen['comparison']['engine_resources'][name] if frozen else None)
                rec['engine_server_version'] = runner.safe_version(engine)
                rec['resources']['engine'] = runner.safe_engine_info(engine)
                rec['tools'] = tooling
                rec['comparison_label'] = frozen['comparison']['label'] if frozen else 'functional-capacity-disclosed'
                if frozen is not None:
                    issues = qualification.leg_issues(rec, work_deadline=work_deadline, completed_monotonic=time.monotonic())
                    if rec['engine_server_version'] != frozen['engine_versions'][name]:
                        issues.append('engine version changed during qualification')
                    if not runner.resource_cells.engine_budget_matches(frozen['comparison']['engine_resources'][name], rec['resources']['engine']):
                        issues.append('engine resource envelope changed or became unknown')
                    try:
                        durable_job.check_receipt(readiness_receipt)
                        qualification.require_readiness(args.readiness, required_paths=frozen_paths,
                                                       assets_path=assets, sparse_paths=(template,), admission_epoch=admission_epoch)
                    except (OSError, ValueError) as exc:
                        issues.append(str(exc))
                    try:
                        post_gate = subprocess.run(['perf-gate-ready', '-1'], capture_output=True, text=True, timeout=15)
                        mixed_cycle.save(before / 'qualification-post-gate.json', {'exit': post_gate.returncode,
                            'stdout': post_gate.stdout, 'stderr': post_gate.stderr})
                        if post_gate.returncode != 0:
                            issues.append('performance gate invalidates qualification completion')
                    except (OSError, subprocess.SubprocessError) as exc:
                        issues.append('qualification post-gate failed: ' + repr(exc))
                    rec.update(evidence_status='qualification-unreviewed', qualification_issues=issues,
                               readiness_admitted=True, requires_independent_review=True)
                    mixed_cycle.save(before / 'qualification.json', rec)
                    ctx.write(rec)
                    if issues:
                        raise RuntimeError('qualification hard requirements failed: ' + '; '.join(issues))
                else:
                    rec.update(measurement_valid=False, measurement_invalidation='functional diagnostic; exclusivity not certified')
                    ctx.write(rec)
                print(name, 'exact mixed cycles', len(rec['cycles']), flush=True)
            finally:
                primary = sys.exc_info()[1]
                pending = primary
                for label, action in (('engine stop', engine.stop), ('host snapshot', lambda: host_snapshot(before, 'after'))):
                    try:
                        action()
                    except BaseException as exc:
                        outcome['cleanup_errors'].append(label + ': ' + repr(exc))
                        if pending is None:
                            pending = exc
                if primary is None and pending is not None:
                    raise pending
        outcome['status'] = 'passed'
    except BaseException as exc:
        outcome['error'] = repr(exc)
        raise
    finally:
        primary = sys.exc_info()[1]
        pending = primary
        actions = [('registry close', server.server_close),
                   ('save transfers', lambda: mixed_cycle.save(root / 'transfers.json', portfolio.transfers))]
        if thread.ident is not None:
            actions.insert(0, ('registry shutdown', server.shutdown))
            actions.append(('registry join', lambda: thread.join(timeout=5)))
        try:
            for label, action in actions:
                try:
                    action()
                except BaseException as exc:
                    outcome['cleanup_errors'].append(label + ': ' + repr(exc))
                    if pending is None:
                        pending = exc
            if thread.is_alive():
                exc = RuntimeError('registry server did not stop')
                outcome['cleanup_errors'].append(str(exc))
                if pending is None:
                    pending = exc
            if outcome['cleanup_errors']:
                outcome['status'] = 'failed'
            if primary is None and pending is not None:
                outcome['error'] = repr(pending)
                raise pending
        finally:
            pending = sys.exc_info()[1]
            try:
                mixed_cycle.save(root / 'driver-result.json', outcome)
            except OSError:
                if pending is None:
                    raise
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
