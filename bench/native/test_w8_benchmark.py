import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import reporting
import w8_benchmark as w8


class PairedBatch(unittest.TestCase):
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
                    self.jsonl = root / 'trials.jsonl'
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
                def write(self, row): self.rows.append(row)
            contexts = []
            def prepare(source, contract, dest, seed):
                return {'images': {'api': {'reference': 'api'}}, 'seed': seed.hex()}
            def measure(engine, directory, run, contract, portfolio, receipt, layout, server, under_load):
                calls.append((engine.name, id(engine), receipt['seed'], str(layout), server))
                return {'correctness': True, 'pull_to_health_s': 1, 'errors': [],
                        'resources': {'status': 'ok', 'phase_summaries': {'whole_workflow':
                            {'status': 'ok', 'cpu_seconds': 2, 'peak_phys_footprint_bytes': 3}}}}
            args = SimpleNamespace(layout=root, seed=7, pairs=2, under_load=False, diagnostic=False)
            with mock.patch.object(w8.runner, 'RunContext', Context), \
                 mock.patch.object(w8.registry_portfolio, 'prepare_pinned_portfolio'), \
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
            self.assertEqual(reporting.analyze(rows)['cohorts'][0]['valid_pairs'], 2)
            for change in ('mismatch', 'failed', 'diagnostic', 'duplicate'):
                altered = json.loads(json.dumps(rows))
                if change == 'mismatch': altered[0]['paired_inputs']['seed_hex'] = 'other'
                if change == 'failed': altered[0]['correctness']['ok'] = False
                if change == 'diagnostic': altered[0]['measurement_valid'] = False
                if change == 'duplicate': altered.append(altered[0])
                self.assertTrue(reporting.analyze(altered)['cohorts'][0]['rejections'], change)
            args.diagnostic = True
            with mock.patch.object(w8.runner, 'RunContext', Context), \
                 mock.patch.object(w8.registry_portfolio, 'prepare_pinned_portfolio'), \
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

    def test_failed_leg_is_retained_and_ctrs_is_stopped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            instances = {}
            class Engine:
                def __init__(self, name, run):
                    self.name, self.stops = name, 0
                    instances[name] = self
                def stop(self): self.stops += 1
            class Server:
                def serve_forever(self, **kwargs): pass
                def shutdown(self): pass
                def server_close(self): pass
            args = SimpleNamespace(layout=root, seed=1, pairs=1, under_load=False, diagnostic=False)
            with mock.patch.object(w8.runner, 'RESULTS', root), \
                 mock.patch.object(w8.registry_portfolio, 'prepare_pinned_portfolio'), \
                 mock.patch.object(w8.registry_portfolio, 'prepare_layout', return_value=object()), \
                 mock.patch.object(w8.runner, 'safe_version', return_value='v'), \
                 mock.patch.object(w8.runner, 'safe_engine_info', return_value={'ncpu': 1, 'mem_total_bytes': 1}):
                code = w8.run_batch(args, engine_factory=Engine,
                    prepare=lambda *a: {'images': {'api': {'reference': 'api'}}},
                    serve=lambda *a: Server(), gate_fn=lambda *a: True,
                    measure=mock.Mock(side_effect=RuntimeError('failed leg')))
            records = [json.loads(line) for line in next(root.glob('*/trials.jsonl')).read_text().splitlines()]
            self.assertEqual(code, 1)
            self.assertEqual(len(records), 2)
            self.assertTrue(all('failed leg' in ''.join(r['validation_errors']) for r in records))
            self.assertTrue(reporting.analyze(records)['cohorts'][0]['rejections'])
            self.assertEqual((instances['ctrs'].stops, instances['orbstack'].stops), (1, 0))

    def test_measurement_does_not_swallow_cancellation(self):
        engine = mock.Mock(name='engine')
        engine.name = 'ctrs'
        contract = {'images': {'np-v2/api': {'config': 'sha256:api'}}}
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
        result = {'resources': {'phase_summaries': {'whole_workflow': {'status': 'ok', 'cpu_seconds': 4,
                   'peak_phys_footprint_bytes': 10}, 'nested': {'status': 'ok', 'cpu_seconds': 3,
                   'peak_phys_footprint_bytes': 9}}}}
        self.assertEqual(w8.resource_metrics(result), {'cpu_seconds_est': 4, 'peak_phys_footprint_bytes': 10})
        result['resources']['phase_summaries']['whole_workflow'] = {'status': 'unknown'}
        self.assertEqual(w8.resource_metrics(result), {})

    def test_completion_union_counts_each_completion_once(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            (path / 'completions.jsonl').write_text(''.join(json.dumps({'completion_monotonic': i, 'latency_ms': i}) + '\n' for i in range(10)))
            self.assertEqual(w8.completion_metrics(path, [{'begin_monotonic': 0, 'end_monotonic': 9},
                {'begin_monotonic': 0, 'end_monotonic': 8}]), {'under_pull_p95_ms': 9, 'under_pull_p99_ms': 9})
