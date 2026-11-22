import json
import hashlib
import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import reporting
import w8_benchmark as w8


def digest(value):
    return 'sha256:' + hashlib.sha256(value.encode()).hexdigest()


def source_for(contract):
    routes = {}
    for name, image in contract['images'].items():
        layers = [{'digest': digest('source-' + diff_id)} for diff_id in image['diff_ids']]
        blob = mock.Mock()
        blob.metadata.return_value = json.dumps({'layers': layers}).encode()
        routes[(name, 'manifests', image['manifest'])] = (None, None, blob)
    return SimpleNamespace(routes=routes)


def receipt_for(contract, source, seed):
    images, layers = {}, {}
    for name, image in contract['images'].items():
        manifest = json.loads(source.routes[(name, 'manifests', image['manifest'])][2].metadata())
        descriptors, diff_ids = [], []
        for original, diff_id in zip(manifest['layers'], image['diff_ids'], strict=True):
            key = (original['digest'], diff_id)
            item = layers.setdefault(key, {'source_digest': key[0], 'source_diff_id': key[1],
                'digest': digest(seed.hex() + key[0]), 'diff_id': digest(seed.hex() + key[1]),
                'size': 123, 'marker': 'marker'})
            descriptors.append({'digest': item['digest'], 'size': item['size']})
            diff_ids.append(item['diff_id'])
        images[name] = {'reference': image['layout_reference'], 'source_manifest': image['manifest'],
                        'manifest': digest(seed.hex() + name + 'manifest'),
                        'config': digest(seed.hex() + name + 'config'),
                        'layers': descriptors, 'diff_ids': diff_ids}
    return {'schema_version': 1, 'fixture_version': 'w8-v3',
            'source_fixture_version': contract['fixture_version'],
            'source_contract_sha256': hashlib.sha256(w8.registry_variant._encoded(contract)).hexdigest(),
            'seed_sha256': hashlib.sha256(seed).hexdigest(), 'seed': seed.hex(),
            'images': images, 'layers': list(layers.values())}


def prepare_fake(source, contract, dest, seed):
    return receipt_for(contract, source_for(contract), seed)


class PairedBatch(unittest.TestCase):
    def test_receipt_identity_mutations_and_shared_layers(self):
        shared = digest('shared')
        contract = {'fixture_version': 'source', 'images': {
            name: {'layout_reference': name, 'manifest': digest(name), 'layer_count': 1, 'diff_ids': [shared]}
            for name in ('a', 'b')}}
        source = source_for(contract)
        seed = b'first'
        valid = receipt_for(contract, source, seed)
        previous_digests, previous_diff_ids = set(), set()
        w8.validate_receipt(valid, contract, source, seed, previous_digests, previous_diff_ids)
        self.assertEqual(len(valid['layers']), 1)
        second_seed = b'second'
        second = receipt_for(contract, source, second_seed)
        for mutation in ('source_digest', 'source_diff_id', 'previous_digest', 'previous_diff_id',
                         'missing', 'duplicate', 'mismatch', 'image_missing', 'shared_conflict'):
            altered = copy.deepcopy(second)
            layer = altered['layers'][0]
            if mutation in ('source_digest', 'previous_digest'):
                layer['digest'] = layer['source_digest'] if mutation == 'source_digest' else valid['layers'][0]['digest']
                for image in altered['images'].values(): image['layers'][0]['digest'] = layer['digest']
            if mutation in ('source_diff_id', 'previous_diff_id'):
                layer['diff_id'] = layer['source_diff_id'] if mutation == 'source_diff_id' else valid['layers'][0]['diff_id']
                for image in altered['images'].values(): image['diff_ids'][0] = layer['diff_id']
            if mutation == 'missing': altered['layers'].clear()
            if mutation == 'duplicate': altered['layers'].append(copy.deepcopy(layer))
            if mutation == 'mismatch': layer['source_digest'] = digest('wrong')
            if mutation == 'image_missing': del altered['images']['a']
            if mutation == 'shared_conflict': altered['images']['a']['diff_ids'][0] = digest('wrong')
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                w8.validate_receipt(altered, contract, source, second_seed, previous_digests, previous_diff_ids)
        w8.validate_receipt(second, contract, source, second_seed, previous_digests, previous_diff_ids)

    def test_shared_layer_receipt_passes_batch_once_per_pair(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = root / 'w8-v6'
            fixture.mkdir()
            shared = digest('shared')
            contract = {'fixture_version': 'source', 'images': {
                name: {'layout_reference': name, 'manifest': digest(name), 'layer_count': 1, 'diff_ids': [shared]}
                for name in ('a', 'b')}}
            (fixture / 'portfolio.json').write_text(json.dumps(contract))
            engine = mock.Mock(proc=object())
            engine.name = 'ctrs'
            result = {'correctness': True, 'pull_to_health_s': 1, 'errors': [],
                      'resources': {'status': 'ok', 'ownership': {'required_processes': [
                          {'pid': 1, 'role': 'daemon', 'kernel_start_identity': 2}]}}}
            measure = mock.Mock(return_value=result)
            server = mock.Mock()
            args = SimpleNamespace(layout=root, seed=1, pairs=1, under_load=False, diagnostic=True)
            with mock.patch.object(w8.runner, 'RESULTS', root), \
                 mock.patch.object(w8.runner, 'FIXTURES', root), \
                 mock.patch.object(w8.registry_portfolio, 'prepare_pinned_portfolio', side_effect=lambda layout, contract: source_for(contract)), \
                 mock.patch.object(w8.registry_portfolio, 'prepare_layout', return_value=object()), \
                 mock.patch.object(w8.runner, 'safe_version', return_value='v'), \
                 mock.patch.object(w8.runner, 'safe_engine_info', return_value={'ncpu': 1, 'mem_total_bytes': 1}), \
                 mock.patch.object(w8, 'validate_receipt', wraps=w8.validate_receipt) as validate:
                self.assertEqual(w8.run_batch(args, engine_factory=lambda *a: engine, prepare=prepare_fake,
                    measure=measure, serve=lambda *a: server, gate_fn=lambda *a: True), 0)
            validate.assert_called_once()
            self.assertEqual(len(validate.call_args.args[0]['layers']), 1)
            self.assertEqual(measure.call_count, 2)

    def test_invalid_receipt_stops_before_measurement_and_retains_status(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            engine = mock.Mock()
            measure = mock.Mock()
            def invalid(source, contract, dest, seed):
                receipt = prepare_fake(source, contract, dest, seed)
                receipt['layers'].pop()
                return receipt
            args = SimpleNamespace(layout=root, seed=1, pairs=1, under_load=False, diagnostic=False)
            with mock.patch.object(w8.runner, 'RESULTS', root), \
                 mock.patch.object(w8.registry_portfolio, 'prepare_pinned_portfolio', side_effect=lambda layout, contract: source_for(contract)), \
                 mock.patch.object(w8.registry_portfolio, 'prepare_layout') as prepare_layout:
                with self.assertRaisesRegex(ValueError, 'incomplete receipt'):
                    w8.run_batch(args, engine_factory=lambda *a: engine, prepare=invalid, measure=measure)
            measure.assert_not_called()
            prepare_layout.assert_not_called()
            status = json.loads(next(root.glob('*/status.json')).read_text())
            self.assertEqual(status['state'], 'failed')
            self.assertEqual(status['completed_records'], 0)
            self.assertIn('incomplete receipt', status['error'])
            engine.stop.assert_called_once()

    def test_cli_installs_cleanup_policy_before_batch(self):
        import runner
        with tempfile.TemporaryDirectory() as temp:
            binary = Path(temp) / 'ctrs'
            binary.write_bytes(b'candidate')
            with mock.patch('sys.argv', ['runner.py', 'w8-baseline', '--layout', temp,
                    '--ctrs-binary', str(binary), '--pairs', '1', '--diagnostic']), \
                 mock.patch.object(runner, 'CTRS_BIN', binary), \
                 mock.patch.object(runner, 'DOCKER', '/docker'), \
                 mock.patch.object(runner, 'find_docker', return_value='/docker'), \
                 mock.patch.object(runner.os, 'uname', return_value=SimpleNamespace(sysname='Darwin', machine='arm64')), \
                 mock.patch('diagnostic_signals.install_cleanup_signals') as install, \
                 mock.patch.object(w8, 'run_batch', side_effect=lambda args: 0 if install.called else 1):
                self.assertEqual(runner.main(), 0)
            install.assert_called_once_with()

    def test_shared_inputs_order_retention_and_reporting(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            engines = {}
            calls = []
            class Engine:
                def __init__(self, name, run):
                    self.name = name
                    self.stops = 0
                    self.proc = object()
                    engines[name] = self
                def stop(self):
                    self.stops += 1
            class Server:
                def serve_forever(self, **kwargs): pass
                def shutdown(self): pass
                def server_close(self): pass
            class Context:
                def __init__(self, run):
                    self.run_id = run
                    self.results_dir = root
                    self.jsonl = root / (run + '-trials.jsonl')
                    self.provenance = {'source': 'fixed'}
                    self.rows = []
                    contexts.append(self)
                def trial_dir(self, name, case, state):
                    path = root / f'{len(contexts)}-{len(self.rows)}'; path.mkdir(); return path
                def new_record(self, engine, case, state, directory):
                    return dict(run_id=self.run_id, host_id='host', arch='arm64', git_sha='sha', case=case,
                                state=state, engine=engine.name, workload_params=dict(self.workload_params),
                                provenance=dict(self.provenance), workload_id=self.workload_id,
                                evidence_status='pilot', metrics={}, resources={}, validation_errors=[])
                def write(self, row):
                    self.rows.append(row)
                    with self.jsonl.open('a') as stream:
                        stream.write(json.dumps(row) + '\n')
            contexts = []
            def prepare(source, contract, dest, seed):
                return prepare_fake(source, contract, dest, seed)
            def measure(engine, directory, run, contract, portfolio, receipt, layout, server, under_load):
                self.assertEqual(w8.os.environ['CTRS_IDLE_SECS'], '0')
                calls.append((engine.name, id(engine), receipt['seed'], str(layout), server))
                processes = [{'pid': 1 if engine.name == 'ctrs' else 2,
                              'role': 'daemon', 'kernel_start_identity': 100}]
                return {'correctness': True, 'pull_to_health_s': 1, 'errors': [],
                        'resources': {'status': 'ok', 'ownership': {'required_processes': processes},
                            'phase_summaries': {'whole_workflow': {
                                'status': 'ok', 'errors': [], 'required_processes': processes,
                                'counter_methods': ['proc_pid_rusage'],
                                'footprint_method': 'rusage_info_v0.ri_phys_footprint',
                                'cpu_seconds': 2, 'peak_phys_footprint_bytes': 3}}}}
            args = SimpleNamespace(layout=root, seed=7, pairs=2, under_load=False, diagnostic=False)
            with mock.patch.object(w8.runner, 'RunContext', Context), \
                 mock.patch.object(w8.registry_portfolio, 'prepare_pinned_portfolio', side_effect=lambda layout, contract: source_for(contract)), \
                 mock.patch.object(w8.registry_portfolio, 'prepare_layout', return_value=object()), \
                 mock.patch.object(w8.runner, 'safe_version', return_value='v'), \
                 mock.patch.object(w8.runner, 'safe_engine_info', return_value={'ncpu': 4, 'mem_total_bytes': 100}):
                code = w8.run_batch(args, engine_factory=Engine, measure=measure, prepare=prepare,
                                    serve=lambda *a: Server(), gate_fn=lambda *a: True)
            self.assertEqual(code, 0)
            self.assertEqual([c[0] for c in calls], ['ctrs', 'orbstack', 'orbstack', 'ctrs'])
            self.assertEqual(calls[0][2:], calls[1][2:])
            self.assertEqual(calls[2][2:], calls[3][2:])
            self.assertNotEqual(calls[0][2], calls[2][2])
            self.assertEqual(calls[0][1], calls[3][1])
            self.assertEqual((engines['ctrs'].stops, engines['orbstack'].stops), (1, 0))
            rows = contexts[0].rows
            cohort = reporting.analyze(rows)['cohorts'][0]
            self.assertEqual(cohort['valid_pairs'], 2)
            metrics = {m['metric']: m for m in cohort['metrics']}
            self.assertEqual(metrics['peak_phys_footprint_bytes']['valid_pairs'], 2)
            self.assertEqual(metrics['cpu_seconds_est']['cpu_accounting_incomplete_trials'], 2)
            for change in ('mismatch', 'failed', 'diagnostic', 'duplicate'):
                altered = json.loads(json.dumps(rows))
                if change == 'mismatch': altered[0]['paired_inputs']['seed_hex'] = 'other'
                if change == 'failed': altered[0]['correctness']['ok'] = False
                if change == 'diagnostic': altered[0]['measurement_valid'] = False
                if change == 'duplicate': altered.append(altered[0])
                self.assertTrue(reporting.analyze(altered)['cohorts'][0]['rejections'], change)
            args.diagnostic = True
            with mock.patch.object(w8.runner, 'RunContext', Context), \
                 mock.patch.object(w8.registry_portfolio, 'prepare_pinned_portfolio', side_effect=lambda layout, contract: source_for(contract)), \
                 mock.patch.object(w8.registry_portfolio, 'prepare_layout', return_value=object()), \
                 mock.patch.object(w8.runner, 'safe_version', return_value='v'), \
                 mock.patch.object(w8.runner, 'safe_engine_info', return_value={'ncpu': 4, 'mem_total_bytes': 100}):
                code = w8.run_batch(args, engine_factory=Engine, measure=measure, prepare=prepare,
                                    serve=lambda *a: Server(), gate_fn=lambda *a: False)
            self.assertEqual(code, 0)
            diagnostic = contexts[-1].rows
            self.assertTrue(all(r['correctness']['ok'] and not r['measurement_valid'] for r in diagnostic))
            cohort = reporting.analyze(diagnostic)['cohorts'][0]
            self.assertEqual(cohort['valid_pairs'], 0)
            self.assertTrue(all(m['ratio_median'] is None for m in cohort['metrics']))
            status = json.loads((root / 'status.json').read_text())
            self.assertEqual(status['completed_records'], status['planned_records'])
            self.assertFalse(status['timing_eligible'])
            seen = []
            def drifting(*arguments):
                result = measure(*arguments)
                if arguments[0].name == 'ctrs':
                    seen.append(True)
                    if len(seen) == 2:
                        result['resources']['ownership']['required_processes'][0]['kernel_start_identity'] += 1
                return result
            previous_idle = w8.os.environ.get('CTRS_IDLE_SECS')
            with mock.patch.object(w8.runner, 'RunContext', Context), \
                 mock.patch.object(w8.registry_portfolio, 'prepare_pinned_portfolio', side_effect=lambda layout, contract: source_for(contract)), \
                 mock.patch.object(w8.registry_portfolio, 'prepare_layout', return_value=object()), \
                 mock.patch.object(w8.runner, 'safe_version', return_value='v'), \
                 mock.patch.object(w8.runner, 'safe_engine_info', return_value={'ncpu': 4, 'mem_total_bytes': 100}):
                code = w8.run_batch(args, engine_factory=Engine, measure=drifting, prepare=prepare,
                                    serve=lambda *a: Server(), gate_fn=lambda *a: True)
            self.assertEqual(code, 1)
            self.assertIn('identity changed', ''.join(contexts[-1].rows[-1]['validation_errors']))
            self.assertEqual(w8.os.environ.get('CTRS_IDLE_SECS'), previous_idle)

    def test_failed_leg_is_retained_and_ctrs_is_stopped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            instances = {}
            class Engine:
                def __init__(self, name, run):
                    self.name, self.stops = name, 0
                    self.proc = object()
                    instances[name] = self
                def stop(self): self.stops += 1
            class Server:
                def serve_forever(self, **kwargs): pass
                def shutdown(self): pass
                def server_close(self): pass
            args = SimpleNamespace(layout=root, seed=1, pairs=1, under_load=False, diagnostic=False)
            with mock.patch.object(w8.runner, 'RESULTS', root), \
                 mock.patch.object(w8.registry_portfolio, 'prepare_pinned_portfolio', side_effect=lambda layout, contract: source_for(contract)), \
                 mock.patch.object(w8.registry_portfolio, 'prepare_layout', return_value=object()), \
                 mock.patch.object(w8.runner, 'safe_version', return_value='v'), \
                 mock.patch.object(w8.runner, 'safe_engine_info', return_value={'ncpu': 1, 'mem_total_bytes': 1}):
                code = w8.run_batch(args, engine_factory=Engine,
                    prepare=prepare_fake,
                    serve=lambda *a: Server(), gate_fn=lambda *a: True,
                    measure=mock.Mock(side_effect=RuntimeError('failed leg')))
            records = [json.loads(line) for line in next(root.glob('*/trials.jsonl')).read_text().splitlines()]
            self.assertEqual(code, 1)
            self.assertEqual(len(records), 2)
            self.assertTrue(all('failed leg' in ''.join(r['validation_errors']) for r in records))
            self.assertTrue(reporting.analyze(records)['cohorts'][0]['rejections'])
            self.assertEqual((instances['ctrs'].stops, instances['orbstack'].stops), (1, 0))

            for scenario in ('busy', 'signal', 'signal-cleanup'):
                previous = set(root.glob('*/trials.jsonl'))
                class FaultEngine(Engine):
                    def stop(self):
                        super().stop()
                        if scenario == 'signal-cleanup' and self.name == 'ctrs':
                            raise OSError('shutdown fault')
                measurement = mock.Mock(side_effect=SystemExit(143))
                with self.subTest(scenario=scenario), \
                     mock.patch.object(w8.runner, 'RESULTS', root), \
                     mock.patch.object(w8.registry_portfolio, 'prepare_pinned_portfolio', side_effect=lambda layout, contract: source_for(contract)), \
                     mock.patch.object(w8.registry_portfolio, 'prepare_layout', return_value=object()):
                    def execute():
                        return w8.run_batch(args, engine_factory=FaultEngine,
                            prepare=prepare_fake,
                            serve=lambda *a: Server(), gate_fn=lambda *a: scenario != 'busy', measure=measurement)
                    if scenario == 'busy':
                        self.assertEqual(execute(), 1)
                        measurement.assert_not_called()
                    else:
                        with self.assertRaises(SystemExit) as interrupted:
                            execute()
                        self.assertEqual(interrupted.exception.code, 143)
                path = (set(root.glob('*/trials.jsonl')) - previous).pop()
                status = json.loads((path.parent / 'status.json').read_text())
                self.assertEqual(status['completed_records'], 1)
                self.assertEqual(status['planned_records'], 2)
                self.assertEqual(status['state'], 'failed' if scenario == 'busy' else 'interrupted')
                if scenario == 'busy':
                    self.assertEqual(status['stopped_reason'], 'initial-host-busy')
                if scenario == 'signal-cleanup':
                    self.assertIn('shutdown fault', status['cleanup_error'])
                self.assertEqual((instances['ctrs'].stops, instances['orbstack'].stops), (1, 0))

    def test_measurement_does_not_swallow_cancellation(self):
        engine = mock.Mock(name='engine')
        engine.name = 'ctrs'
        contract = {'images': {'np-v6/api': {'config': 'sha256:api'}}}
        with tempfile.TemporaryDirectory() as temp, \
             mock.patch.object(w8.pilot, 'prepare_warm_engine', side_effect=SystemExit(143)), \
             mock.patch.object(w8.pilot, 'finish_engine') as finish:
            with self.assertRaises(SystemExit) as signal:
                w8.pilot.measure_engine(engine, Path(temp), 'run', contract,
                    mock.Mock(manifests={}), {}, Path(temp), mock.Mock())
        self.assertEqual(signal.exception.code, 143)
        self.assertFalse(finish.call_args.kwargs['stop'])
        engine.stop.assert_not_called()

    def test_trial_names_do_not_collide_after_engine_project_truncation(self):
        import runner
        run = 'w8-paired-' + 'a' * 12
        projects = [runner.project_name(f'{run}-p{pair:03d}', engine, case)
            for pair in (1, 100) for engine in ('ctrs', 'orbstack')
            for case in ('W8v2', 'w8underpull', 'marker-api', 'marker-redis')]
        self.assertEqual(len(projects), len(set(projects)))

    def test_gate_rejects_hot_tree_even_on_success(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            def snapshot(path, label):
                (path / (label + '-gate.json')).write_text(json.dumps({'exit': 0, 'stderr': 'hot process tree'}))
            with mock.patch.object(w8, 'host_snapshot', side_effect=snapshot):
                self.assertFalse(w8.gate(directory, 'before'))

    def test_whole_scope_does_not_sum_or_invent(self):
        cell = {'status': 'ok', 'errors': [], 'required_processes': [{'pid': 1}],
                'counter_methods': ['proc_pid_rusage'],
                'footprint_method': 'rusage_info_v0.ri_phys_footprint',
                'cpu_seconds': 4, 'peak_phys_footprint_bytes': 10}
        phases = {'whole_workflow': cell, 'nested': cell | {'cpu_seconds': 3, 'peak_phys_footprint_bytes': 9}}
        result = {'resources': {'phase_summaries': phases}}
        resources = {'resources': w8.resource_metrics(result)}
        self.assertEqual(reporting._metric(resources, 'cpu_seconds_est'), (4, None))
        self.assertEqual(reporting._metric(resources, 'peak_phys_footprint_bytes'), (10, None))
        for invalid in ({'status': 'unknown'}, {'errors': ['sample missing']},
                        {'required_processes': []}, {'counter_methods': []}, {'footprint_method': 'RSS'}):
            phases['whole_workflow'] = cell | invalid
            self.assertEqual(w8.resource_metrics(result), {})

    def test_allocation_receipt_requires_three_snapshots_of_the_same_backing_file(self):
        def sample(allocated, inode=23, status='ok'):
            return {'status': status, 'allocated_bytes': allocated,
                    'files': [{'path': '/engine/data', 'device': 1, 'inode': inode}]}

        snapshots = {'before_pull': sample(4096), 'before_app_cleanup': sample(16384),
                     'after_app_cleanup': sample(8192)}
        receipt = w8.pilot.allocation_receipt(snapshots)
        self.assertEqual(receipt['status'], 'ok')
        self.assertEqual(receipt['deployment_delta_bytes'], 12288)
        self.assertEqual(receipt['after_app_cleanup_delta_bytes'], 4096)
        for bad in ({}, {'after_app_cleanup': sample(16384, inode=42)},
                    {'after_app_cleanup': sample(None, status='unknown')}):
            base = snapshots if bad else {k: v for k, v in snapshots.items() if k != 'after_app_cleanup'}
            receipt = w8.pilot.allocation_receipt(base | bad)
            self.assertEqual(receipt['status'], 'unknown')
            self.assertIsNone(receipt['deployment_delta_bytes'])
            self.assertIsNone(receipt['after_app_cleanup_delta_bytes'])

    def test_completion_union_counts_each_completion_once(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / 'completions.jsonl').write_text(''.join(json.dumps({'completion_monotonic': i, 'latency_ms': i}) + '\n' for i in range(10)))
            self.assertEqual(w8.completion_metrics(path, [{'begin_monotonic': 0, 'end_monotonic': 9},
                {'begin_monotonic': 0, 'end_monotonic': 8}]), {'under_pull_p95_ms': 9, 'under_pull_p99_ms': 9})
