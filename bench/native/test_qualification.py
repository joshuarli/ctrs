import copy
import contextlib
import io
import hashlib
import json
from pathlib import Path
import tempfile
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import durable_job
import qualification as gate
import test_mixed_resources as growth_examples
import test_resource_cycles as resource_examples
from diagnostics import mixed_pilot


CPU_CELL = 'w2.resident-idle.resource-cycle.cpu-cores'
RECOVERY_CELL = 'w10.warm.api-interruption.recovery-s'
CORRECTNESS_CELL = 'w1.warm.compose-stack.startup-or-roundtrip-failures'
EDIT_CELL = 'w5.warm.bind.bind-edit-to-result-median-s'


class Readiness(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        root = Path(self.scratch.name)
        self.assets = root / 'assets.lock'
        self.source = root / 'runtime.py'; self.source.write_text('frozen input\n')
        artifacts = {}
        for name in ('ctrs_binary', 'guest_kernel', 'guest_initramfs', 'python', 'docker', 'compose', 'buildx', 'proof'):
            path = root / name; path.write_text(name)
            artifacts[name] = durable_job.receipt(path)
        proof = artifacts['proof']
        versions = {key: key + '-v-test' for key in gate.CASES}
        versions['W11'] = gate.mixed_resources.VERSION
        contract = {key: {**cell, 'fixture_version': versions[cell['workload']]}
                    for key, cell in gate.W1_W10_CELLS.items()}
        contract.update(copy.deepcopy(gate.W11_CELLS))
        contract['extra'] = {**contract[EDIT_CELL], 'metric': 'extra_metric'}
        contract_digest = hashlib.sha256(
            json.dumps(contract, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assets.write_text(f'[freeze]\nstatus="frozen"\ncell_contract_sha256="{contract_digest}"\n[tools]\npython="test-version"\n'
            'docker_cli="test-version"\ndocker_compose="test-version"\ndocker_buildx="test-version"\n[images]\n' +
            '\n'.join(f'{name}="example/{name}@{gate.PIN["images"][image]["manifest"]}"' for name, image in
                (('postgres', 'np-v2/postgres'), ('redis', 'np-v2/redis'), ('fixture_api', 'np-v2/api'), ('api_base', 'np-v2/api'))))
        review = root / 'review.json'
        review.write_text(json.dumps({'kind': 'native-cell-contract-review', 'reviewer': 'test-reviewer',
            'conclusion': 'complete', 'cell_contract_sha256': contract_digest}))
        host_review = root / 'host-review.json'
        stamp = time.time()
        host_review.write_text(json.dumps({'kind': 'native-host-conditions-review', 'host_id': gate.socket.gethostname(),
            'observed_epoch': stamp, 'expires_epoch': stamp + 300, 'conclusion': 'exclusive',
            'reviewer': 'test-reviewer', 'observations': [proof]}))
        self.doc = {'schema': 1, 'scope': 'native-arm64-macos', 'freeze_status': 'frozen',
            'runtime_revision': 'a' * 40,
            'artifacts': {key: artifacts[key] for key in ('ctrs_binary', 'guest_kernel', 'guest_initramfs')},
            'engine_versions': {'ctrs': 'ctrs-test', 'orbstack': 'orb-test'},
            'tools': {key: {'version': 'test-version', 'artifact': artifacts[key]} for key in ('python', 'docker', 'compose', 'buildx')},
            'inputs': [*artifacts.values(), durable_job.receipt(self.assets), durable_job.receipt(self.source)],
            'fixtures': {key: {'version': version, 'evidence': proof} for key, version in versions.items()},
            'prerequisites': {key: {'status': 'pass', 'evidence': proof} for key in gate.PREREQUISITES},
            'durability': {'failure_model': 'explicit disposable fixture failure model',
                'ctrs_guarantee': 'declared', 'orbstack_guarantee': 'declared', 'comparable': True, 'evidence': proof},
            'comparison': {'label': 'resource-matched-default-driver', 'builder_driver': 'docker',
                'ctrs_cpus': 2, 'ctrs_memory_mib': 8192,
                'engine_resources': {name: {'ncpu': 2, 'mem_total_bytes': 8 << 30} for name in ('ctrs', 'orbstack')}},
            'cell_contract': contract,
            'matrix': {key: {'status': 'unmeasured', 'evidence': None} for key in contract}}
        self.doc['prerequisites']['complete_cell_contract']['evidence'] = durable_job.receipt(review)
        self.doc['prerequisites']['host_conditions']['evidence'] = durable_job.receipt(host_review)
        self.path = root / 'readiness.json'

    def check(self, doc=None):
        self.path.write_text(json.dumps(self.doc if doc is None else doc))
        return gate.require_readiness(self.path, required_paths=(self.source,), assets_path=self.assets)

    def test_frozen_receipts_admit_readiness_without_promoting_unknown_cells(self):
        result = self.check()
        self.assertEqual(result['matrix'][CPU_CELL]['status'], 'unmeasured')
        self.doc['matrix'][CPU_CELL] = {'status': 'loss', 'evidence': self.doc['inputs'][0]}
        self.assertEqual(self.check()['matrix'][CPU_CELL]['status'], 'loss')

    def test_reliability_dimensions_on_other_workloads_cannot_cover_w11(self):
        contract = self.doc['cell_contract']
        for cell in contract.values():
            if cell['workload'] == 'W11' and cell['dimension'] != 'application':
                cell.update(workload='W1', fixture_version=self.doc['fixtures']['W1']['version'])
        proof = self.doc['prerequisites']['complete_cell_contract']
        path = Path(proof['evidence']['path'])
        review = json.loads(path.read_text())
        review['cell_contract_sha256'] = hashlib.sha256(
            json.dumps(contract, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        path.write_text(json.dumps(review))
        proof['evidence'] = durable_job.receipt(path)
        with self.assertRaisesRegex(gate.ReadinessError, 'missing or changed required W11 cell'):
            self.check()

    def test_one_growth_cell_cannot_cover_other_resources(self):
        name = 'w11.active-disk-allocation-growth'
        self.doc['cell_contract'].pop(name)
        self.doc['matrix'].pop(name)
        with self.assertRaisesRegex(gate.ReadinessError, 'missing or changed required W11 cell: ' + name):
            self.check()

    def test_a_missing_load_or_state_cannot_be_covered_by_other_cells(self):
        for name in ('w2.warm.container-to-container-saturation-c16.p99-ms',
                     'w6.warm.rust-default-builder.build-rust-s',
                     'w8.derived.cancelled-delivery.cancellation-or-cleanup-failures',
                     'w10.warm.database-interruption.recovery-s'):
            with self.subTest(name=name):
                doc = copy.deepcopy(self.doc)
                del doc['cell_contract'][name]
                del doc['matrix'][name]
                with self.assertRaisesRegex(gate.ReadinessError, 'missing or changed required qualification cell: ' + name):
                    self.check(doc)

    def test_reviewed_cell_edit_cannot_change_a_frozen_contract(self):
        contract = self.doc['cell_contract']
        contract['extra']['load'] = 'edited after freeze'
        proof = self.doc['prerequisites']['complete_cell_contract']
        path = Path(proof['evidence']['path'])
        review = json.loads(path.read_text())
        review['cell_contract_sha256'] = hashlib.sha256(
            json.dumps(contract, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        path.write_text(json.dumps(review))
        proof['evidence'] = durable_job.receipt(path)
        with self.assertRaisesRegex(gate.ReadinessError, 'cell contract differs from assets.lock'):
            self.check()

    def test_unfrozen_assets_fail_before_receipt_verification(self):
        self.assets.write_text('[freeze]\nstatus="pilot"\n')
        with patch.object(durable_job, 'check_receipt') as verify, self.assertRaisesRegex(gate.ReadinessError, 'not frozen'):
            self.check()
        verify.assert_not_called()

    def test_missing_failed_or_incomparable_prerequisites_cannot_admit(self):
        mutations = (
            lambda d: d['fixtures'].pop('W5'),
            lambda d: d['matrix'].pop(CPU_CELL),
            lambda d: d['cell_contract'][CPU_CELL].update(load='changed after review'),
            lambda d: d['cell_contract'][EDIT_CELL].update(fixture_version='old-proxy'),
            lambda d: d['matrix'][RECOVERY_CELL].update(status='tie'),
            lambda d: d['matrix'][CORRECTNESS_CELL].update(status='loss'),
            lambda d: d['prerequisites']['observer_overhead'].update(status='unknown'),
            lambda d: d['prerequisites']['host_conditions'].update(status='fail'),
            lambda d: d['durability'].update(comparable=False),
            lambda d: d['durability'].update(failure_model=''),
            lambda d: d['comparison'].update(ctrs_cpus=True),
            lambda d: d['comparison']['engine_resources']['orbstack'].update(ncpu=18),
            lambda d: d['comparison'].update(builder_driver='docker-container'),
            lambda d: d.update(scope='linux'),
            lambda d: d.update(runtime_revision='unknown'))
        for mutation in mutations:
            doc = copy.deepcopy(self.doc); mutation(doc)
            with self.subTest(mutation=mutation), self.assertRaises(gate.ReadinessError):
                self.check(doc)

    def test_changed_or_missing_inputs_and_conflicting_receipts_cannot_admit(self):
        original = self.source.read_bytes()
        self.source.write_bytes(original + b'changed')
        with self.assertRaisesRegex(gate.ReadinessError, 'input changed'):
            self.check()
        self.source.write_bytes(original)
        self.doc['inputs'][-1] = durable_job.receipt(self.source)
        self.doc['inputs'].pop()
        with self.assertRaisesRegex(gate.ReadinessError, 'missing frozen inputs'):
            self.check()
        self.doc['inputs'].append(durable_job.receipt(self.source))
        conflict = copy.deepcopy(self.doc['inputs'][0]); conflict['sha256'] = '0' * 64
        self.doc['inputs'].append(conflict)
        with self.assertRaisesRegex(gate.ReadinessError, 'conflicting receipt'):
            self.check()

    def test_duplicate_json_fields_and_unsupported_schema_fail_closed(self):
        self.path.write_text('{"schema":1,"schema":1}')
        with self.assertRaisesRegex(gate.ReadinessError, 'duplicate readiness field'):
            gate.require_readiness(self.path, required_paths=(), assets_path=self.assets)
        for value in (True, 2):
            with self.subTest(value=value), self.assertRaisesRegex(gate.ReadinessError, 'schema'):
                self.check(self.doc | {'schema': value})

    def test_host_review_is_fresh_at_admission_and_rechecked_at_the_original_epoch(self):
        self.check()
        observed = json.loads(Path(self.doc['prerequisites']['host_conditions']['evidence']['path']).read_text())['observed_epoch']
        with self.assertRaisesRegex(gate.ReadinessError, 'stale'):
            gate.require_readiness(self.path, required_paths=(self.source,), assets_path=self.assets,
                                   admission_epoch=observed + 301)
        result = gate.require_readiness(self.path, required_paths=(self.source,), assets_path=self.assets,
                                        admission_epoch=observed + 1)
        self.assertEqual(result['freeze_status'], 'frozen')


class CompletedLeg(unittest.TestCase):
    def record(self):
        fixture = growth_examples.Growth(); fixture.setUp()
        manifest, _ = resource_examples.manifest_and_boundary()
        fixture.plan['manifest'] = manifest
        deadline = 10 + gate.MINIMUM_WORK_SECONDS
        cycles = []
        phases = {}
        for index, row in enumerate(fixture.rows):
            start = 10. + index * 7200
            cycles.append({'cycle': row['cycle'], 'successful_operations': 5000, 'exact_state': True,
                           'queue_jobs': 200, 'queue_events': 12800, 'artifacts': 400, 'build_jobs': 16})
            phases[f'cycle_{index}_mixed_work'] = {
                'operation_started_monotonic': start, 'operation_ended_monotonic': start + 7150,
            }
            phases[f'cycle_{index}_observation'] = {
                'operation_started_monotonic': start + 7160, 'operation_ended_monotonic': start + 7200,
            }
        return {'fixture_version': gate.mixed_resources.VERSION, 'validation_errors': [], 'engine': 'ctrs',
            'running_identity': manifest, 'cycles': cycles, 'work_loop_ended_monotonic': deadline,
            'correctness': {'ok': True, 'checks': {'exact_state_every_cycle': True, 'bounded_retained_items': True}},
            'resources': {'ownership_verified': True, 'cpu_counters_complete': True,
                'resource_errors': [], 'footprint_field': 'phys_footprint', 'peak_phys_footprint_bytes': 100,
                'cpu_seconds_est': 20.,
                'sampler_version': gate.mixed_resources.collect.SAMPLER_VERSION,
                'phases': phases,
                'cycle_growth': gate.mixed_resources.summarize(fixture.plan, fixture.rows)}}

    def test_short_incomplete_or_over_budget_leg_never_passes(self):
        record = self.record()
        deadline = 10 + gate.MINIMUM_WORK_SECONDS
        self.assertEqual(gate.leg_issues(record, work_deadline=deadline, completed_monotonic=deadline + 1), [])
        self.assertTrue(gate.leg_issues(record, work_deadline=deadline - 1, completed_monotonic=deadline))
        self.assertTrue(gate.leg_issues(record, work_deadline=deadline, completed_monotonic=deadline - 1))
        self.assertTrue(gate.leg_issues(record, work_deadline=float('inf'), completed_monotonic=float('inf')))
        for fault in ('correctness', 'resource', 'peak-growth', 'budget', 'missing-observation', 'missing-vm'):
            bad = copy.deepcopy(record)
            if fault == 'correctness': bad['correctness']['ok'] = False
            if fault == 'resource': bad['resources']['resource_errors'] = ['missing required VM']
            growth = bad['resources']['cycle_growth']
            if fault == 'peak-growth': growth['observations'][3]['file_descriptors']['total'] += 17
            if fault == 'budget': growth['plan']['budgets']['file_descriptors'] += 1
            if fault == 'missing-observation': growth['observations'].pop()
            if fault == 'missing-vm': bad['running_identity']['required_processes'].pop()
            with self.subTest(fault=fault):
                self.assertTrue(gate.leg_issues(bad, work_deadline=deadline, completed_monotonic=deadline + 1))

    def test_completed_work_and_observations_are_bound_to_the_work_loop(self):
        deadline = 10 + gate.MINIMUM_WORK_SECONDS
        faults = (
            lambda r: r.pop('cycles'),
            lambda r: r.update(cycles=[]),
            lambda r: r['cycles'].pop(),
            lambda r: r['cycles'][1].update(cycle=0),
            lambda r: r['cycles'][1].update(successful_operations=4999),
            lambda r: r['cycles'][1].update(exact_state=False),
            lambda r: r['resources']['phases'].pop('cycle_1_mixed_work'),
            lambda r: r['resources']['phases'].pop('cycle_1_observation'),
            lambda r: r['resources']['phases']['cycle_1_observation'].update(operation_started_monotonic=11.),
            lambda r: r.pop('work_loop_ended_monotonic'),
            lambda r: r.update(work_loop_ended_monotonic=deadline - 1),
        )
        for index, mutate in enumerate(faults):
            with self.subTest(fault=index):
                record = self.record()
                mutate(record)
                issues = gate.leg_issues(record, work_deadline=deadline, completed_monotonic=deadline + 1)
                self.assertTrue(issues)

    def test_every_cycle_requires_complete_queue_and_build_work(self):
        deadline = 10 + gate.MINIMUM_WORK_SECONDS
        for field in ('queue_jobs', 'queue_events', 'artifacts', 'build_jobs'):
            for value in (None, 0, True):
                with self.subTest(field=field, value=value):
                    record = self.record()
                    cycle = record['cycles'][1]
                    if value is None:
                        del cycle[field]
                    else:
                        cycle[field] = value
                    issues = gate.leg_issues(record, work_deadline=deadline, completed_monotonic=deadline + 1)
                    self.assertTrue(any(field in issue for issue in issues), issues)


class ToolIdentity(unittest.TestCase):
    def test_selected_plugin_files_are_pinned_and_missing_or_duplicate_plugins_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = {name: Path(tmp) / name for name in ('docker', 'compose', 'buildx')}
            for name, path in paths.items(): path.write_text(name)
            plugins = [{'Name': name, 'Path': str(paths[name])} for name in ('compose', 'buildx')]
            versions = {tuple(contract['version_command']): name + '-version' for name, contract in
                        mixed_pilot.runner.TOOL_CONTRACTS.items() if contract['version_command']}
            def sh(args):
                return SimpleNamespace(stdout=json.dumps(plugins) if args[0] == 'info' else versions[tuple(args)])
            engine = SimpleNamespace(sh=sh)
            with patch.object(mixed_pilot.runner, 'DOCKER', str(paths['docker'])):
                captured = mixed_pilot.runner.tool_provenance(engine)
                self.assertEqual(captured['compose']['artifact']['path'], str(paths['compose']))
                self.assertEqual(captured['buildx']['version'], 'buildx-version')
                paths['compose'].write_text('changed plugin')
                with self.assertRaisesRegex(ValueError, 'input changed'):
                    durable_job.check_receipt(captured['compose']['artifact'])
                plugins.pop()
                with self.assertRaisesRegex(ValueError, 'loaded plugin'):
                    mixed_pilot.runner.tool_provenance(engine)
                plugins.append(plugins[0])
                with self.assertRaisesRegex(ValueError, 'loaded plugin'):
                    mixed_pilot.runner.tool_provenance(engine)


class ManualAdmission(unittest.TestCase):
    def test_required_sources_cover_shared_runner_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readiness = root / 'readiness.json'
            readiness.write_text('{}')
            with patch.object(gate, 'require_readiness', side_effect=gate.ReadinessError('stop after inventory')) as require:
                with self.assertRaisesRegex(gate.ReadinessError, 'stop after inventory'):
                    gate.require_leg_readiness(readiness, ctrs_binary=root / 'ctrs', guest=root,
                                               portfolio_layout=root, worker_layout=root)
            required = require.call_args.kwargs['required_paths']
            self.assertIn(gate.runner.BENCH / 'runner.py', required)
            self.assertIn(gate.runner.RATE_LOAD_PY, required)
            self.assertIn(gate.runner.FIXTURES / 'w4/latency.py', required)

    def test_primary_failure_survives_engine_registry_and_result_cleanup(self):
        for stage in ('engine', 'registry', 'save'):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / 'result'; root.mkdir()
                pin = mixed_pilot.mixed_cycle.WORKER['worker']
                manifests = {name: item['manifest'] for name, item in mixed_pilot.mixed_cycle.PIN['images'].items()}
                common = SimpleNamespace(routes={}, manifests=manifests)
                manifest = SimpleNamespace(metadata=lambda: json.dumps({'config': {'digest': pin['config']}}))
                config = SimpleNamespace(metadata=lambda: json.dumps({'rootfs': {'diff_ids': pin['diff_ids']}}))
                worker = SimpleNamespace(manifests={pin['repository']: pin['manifest']}, routes={
                    (pin['repository'], 'manifests', pin['manifest']): (None, None, manifest),
                    (pin['repository'], 'blobs', pin['config']): (None, None, config)})
                class Server:
                    server_port = 1234
                    def __init__(self): self.end = threading.Event()
                    def serve_forever(self, **kwargs):
                        self.thread = threading.current_thread()
                        self.end.wait()
                    def shutdown(self): self.end.set()
                    def server_close(self):
                        self.closed = True
                        if stage == 'registry': raise RuntimeError('registry cleanup failed')
                class Engine:
                    def __init__(self, *args, **kwargs): pass
                    def ensure_up(self): raise RuntimeError('initial engine failure')
                    def stop(self):
                        if stage == 'engine': raise RuntimeError('engine cleanup failed')
                server = Server()
                save = mixed_pilot.mixed_cycle.save
                def save_result(path, value):
                    if stage == 'save' and path.name == 'driver-result.json': raise OSError('result write failed')
                    save(path, value)
                with contextlib.redirect_stdout(io.StringIO()), \
                     patch('sys.argv', ['mixed_pilot', '--portfolio-layout', '/unused', '--worker-layout', '/unused',
                        '--ctrs-binary', sys.executable, '--engines', 'orbstack', '--cycles', '1']), \
                     patch.object(mixed_pilot.registry_portfolio, 'prepare_pinned_portfolio', return_value=common), \
                     patch.object(mixed_pilot.registry_portfolio, 'prepare_layout', return_value=worker), \
                     patch.object(mixed_pilot.registry_portfolio, 'serve', return_value=server), \
                     patch.object(mixed_pilot.runner, 'RunContext', return_value=SimpleNamespace(results_dir=root, run_id='test')), \
                     patch.object(mixed_pilot.runner, 'Engine', Engine), \
                     patch.object(mixed_pilot.runner, 'find_docker', return_value='docker'), \
                     patch.object(mixed_pilot.runner, 'DOCKER', mixed_pilot.runner.DOCKER), \
                     patch.object(mixed_pilot.runner, 'CTRS_BIN', mixed_pilot.runner.CTRS_BIN), \
                     patch.object(mixed_pilot, 'host_snapshot'), \
                     patch.object(mixed_pilot.mixed_cycle, 'save', side_effect=save_result), \
                     patch.object(mixed_pilot.diagnostic_signals, 'install_cleanup_signals'):
                    with self.assertRaisesRegex(RuntimeError, 'initial engine failure'):
                        mixed_pilot.main()
                self.assertTrue(server.closed)
                self.assertFalse(server.thread.is_alive())
                if stage != 'save':
                    outcome = json.loads((root / 'driver-result.json').read_text())
                    self.assertIn('initial engine failure', outcome['error'])
                    self.assertEqual(outcome['status'], 'failed')
                    self.assertTrue(any(stage + ' cleanup failed' in error for error in outcome['cleanup_errors']))

    def invoke(self, extra, reason=None):
        args = ['mixed_pilot', '--portfolio-layout', '/missing', '--worker-layout', '/missing',
                '--ctrs-binary', '/missing', *extra]
        errors = io.StringIO()
        with patch('sys.argv', args), contextlib.redirect_stderr(errors), \
             patch.object(mixed_pilot.runner, 'find_docker') as docker, \
             patch.object(mixed_pilot.diagnostic_signals, 'install_cleanup_signals') as signals:
            with self.assertRaises(SystemExit) as error:
                mixed_pilot.main()
            self.assertEqual(error.exception.code, 2)
        if reason is not None:
            self.assertIn(reason, errors.getvalue())
        docker.assert_not_called()
        signals.assert_not_called()

    def test_invalid_observation_and_missing_readiness_refuse_before_effects(self):
        for extra, reason in ((['--qualification'], '--readiness must identify'),
                      (['--readiness', '/missing'], '--readiness requires'),
                      (['--resource-observation-seconds', 'nan'], 'observation seconds must be positive'),
                      (['--resource-observation-seconds', '3601'], 'at most 3600'),
                      (['--resource-observation-seconds', '61'], 'limited to 60 seconds'),
                      (['--orbstack-storage-file', '/missing'], 'requires --resource-observation-seconds')):
            with self.subTest(extra=extra): self.invoke(extra, reason)
        deadline = time.time() + 3600
        self.invoke(['--engines', 'orbstack', '--work-deadline-epoch', str(deadline),
            '--drain-deadline-epoch', str(deadline + 300), '--cleanup-deadline-epoch', str(deadline + 600)],
            'diagnostic work is limited to fifteen minutes')

    def test_current_pilot_assets_cannot_admit_a_long_leg(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'readiness.json'
            path.write_text(json.dumps({'schema': 1, 'scope': 'native-arm64-macos', 'freeze_status': 'frozen'}))
            deadline = time.time() + gate.MINIMUM_WORK_SECONDS + 600
            with patch.dict('os.environ', {'CTRS_GUEST_DIR': tmp}):
                self.invoke(['--qualification', '--readiness', str(path), '--engines', 'orbstack',
                    '--portfolio-layout', tmp, '--worker-layout', tmp,
                    '--resource-observation-seconds', '30', '--orbstack-storage-file', '/missing',
                    '--work-deadline-epoch', str(deadline), '--drain-deadline-epoch', str(deadline + 300),
                    '--cleanup-deadline-epoch', str(deadline + 600)], 'assets.lock is not frozen')
