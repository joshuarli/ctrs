import copy
from contextlib import nullcontext
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from diagnostics import sampler_pilot as pilot
from test_safety import FixtureContext, fake_engine


def trial():
    return {'correctness': {'ok': True}, 'validation_errors': [],
            'metrics': {'reads_ok': 700, 'writes_ok': 300, 'errors': 0,
                        'cpu_seconds_per_success': 999},
            'resources': {'cpu_seconds_est': 999,
                'application_cpu': {'delta': {'usage_usec': 3000000}},
                'phases': {name: {'cpu_seconds': cpu, 'errors': [], 'operation_wall_seconds': 2.}
                    for name, cpu in [('setup', 50.), ('workload', 10.), ('cleanup', 60.)]}}}


class ObserverControls(unittest.TestCase):
    def test_trial_preserves_measurement_and_cleanup_failures(self):
        for failure in (RuntimeError('measurement failed'), SystemExit(143)):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                ctx = FixtureContext(directory)
                engine = fake_engine()
                engine.compose.side_effect = failure
                with patch.object(pilot.runner, 'compose_down', side_effect=[None, RuntimeError('cleanup failed')]), \
                     patch.object(pilot.runner, 'start_sampler', return_value=(object(), None)), \
                     patch.object(pilot.runner, 'resource_phase', side_effect=lambda *args: nullcontext()), \
                     patch.object(pilot.runner, 'stop_sampler', side_effect=RuntimeError('sampler stop failed')) as stop:
                    invoke = lambda: pilot.runner.trial_w2(ctx, engine, 'warm', 4, 20, .3, 7, 1000)
                    if isinstance(failure, SystemExit):
                        with self.assertRaises(SystemExit) as interrupted:
                            invoke()
                        self.assertEqual(interrupted.exception.code, 143)
                    else:
                        record = invoke()
                        self.assertFalse(record['correctness']['ok'])
                    stop.assert_called_once()
                saved = json.loads((Path(directory) / 'orbstack/W2/trial-result.json').read_text())
                self.assertFalse(saved['correctness']['ok'])
                errors = '\n'.join(saved['validation_errors'])
                self.assertIn(str(failure), errors)
                self.assertIn('cleanup failed', errors)
                self.assertIn('sampler stop failed', errors)

    def test_periodic_control_requires_complete_observation(self):
        for missing in ('ownership_verified', 'cpu_counters_complete', 'peak_phys_footprint_bytes'):
            record = trial()
            record['resources'].update(sampling_mode='periodic', ownership_verified=True,
                                      cpu_counters_complete=True, peak_phys_footprint_bytes=100000)
            record['resources'][missing] = None
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, 'incomplete periodic'):
                pilot._trial_totals(record, 1000)

    def test_work_failure_survives_cleanup_failure_and_closes_registry(self):
        for failure in ('engine', 'registry', 'result-save'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                results = Path(directory)
                written, engines = [], []
                class Context:
                    def __init__(self, run_id):
                        self.results_dir = results / run_id
                        self.results_dir.mkdir()
                    def write(self, record):
                        written.append(record)
                class Engine:
                    def __init__(self, name, *args, **kwargs):
                        self.name, self.dir, self.socket = name, kwargs['fresh_dir'], 'unix:///fake'
                        engines.append(self)
                    def ensure_up(self): pass
                    def sh(self, *args, **kwargs): return SimpleNamespace(stdout='', stderr='')
                    def server_version(self): return 'test'
                    def stop(self):
                        self.stopped = True
                        if failure == 'engine': raise RuntimeError('engine cleanup failed')
                class Server:
                    server_port = 1234
                    def __init__(self): self.end = threading.Event()
                    def serve_forever(self, **kwargs):
                        self.thread = threading.current_thread()
                        self.end.wait()
                    def shutdown(self): self.end.set()
                    def server_close(self):
                        self.closed = True
                        if failure == 'registry': raise RuntimeError('registry cleanup failed')
                server = Server()
                failed = trial(); failed['correctness']['ok'] = False
                portfolio = SimpleNamespace(manifests={'np-v2/' + name: 'sha256:' + 'a' * 64
                    for name in ('api', 'postgres', 'redis')})
                identity = {'required_processes': [{'pid': 999999, 'start_identity': 'absent'}]}
                save = pilot.resource_pilot.save
                def failing_save(path, value):
                    if failure == 'result-save' and path.name == 'result.json':
                        raise OSError('result save failed')
                    save(path, value)
                with patch.object(pilot.runner, 'RESULTS', results), \
                     patch.object(pilot.runner, 'CTRS_BIN', pilot.runner.CTRS_BIN), \
                     patch.object(pilot.runner, 'DOCKER', pilot.runner.DOCKER), \
                     patch.object(pilot.runner, 'RunContext', Context), \
                     patch.object(pilot.runner, 'find_docker', return_value='docker'), \
                     patch.object(pilot.runner, 'trial_w2', return_value=failed), \
                     patch.object(pilot.registry_portfolio, 'prepare_pinned_portfolio', return_value=portfolio), \
                     patch.object(pilot.registry_portfolio, 'serve', return_value=server), \
                     patch.object(pilot.resource_pilot, 'ResourceEngine', Engine), \
                     patch.object(pilot.resource_pilot, 'verify_images'), \
                     patch.object(pilot.resource_pilot, 'warmup_api'), \
                     patch.object(pilot.resource_pilot, 'verify_binary'), \
                     patch.object(pilot.resource_pilot, 'host_snapshot'), \
                     patch.object(pilot.resource_pilot, 'save', side_effect=failing_save), \
                     patch.object(pilot.ownership, 'discover', return_value=identity), \
                     patch.object(pilot.ownership, 'process_table', return_value={}), \
                     patch.object(pilot.diagnostic_signals, 'install_cleanup_signals'):
                    with self.assertRaisesRegex(ValueError, 'failed correctness'):
                        pilot.run_calibration(run_id='failed-control', portfolio_layout=results,
                                              ctrs_binary=Path(sys.executable), pairs=1, operations=1000)
                if failure != 'result-save':
                    outcome = json.loads((results / 'failed-control/result.json').read_text())
                    self.assertIn('failed correctness', outcome['error'])
                    self.assertTrue(any(failure + ' cleanup failed' in item for item in outcome['cleanup_errors']))
                    self.assertEqual(outcome['status'], 'failed')
                self.assertEqual(len(engines), 1)
                self.assertTrue(engines[0].stopped)
                self.assertFalse(written[0]['correctness']['ok'])
                self.assertTrue(server.closed)
                self.assertFalse(server.thread.is_alive())

    def test_costs_come_from_raw_workload_phase_and_success_count(self):
        result = pilot._trial_totals(trial(), 1000)
        self.assertEqual(result['cpu_seconds_per_success'], .01)
        self.assertEqual(result['api_cpu_seconds_per_success'], .003)
        self.assertEqual(result['wall_seconds'], 2.)

    def test_failed_work_partial_cpu_and_dead_observer_cannot_form_control(self):
        faults = []
        bad = trial(); bad['correctness']['ok'] = False; faults.append(bad)
        bad = trial(); bad['metrics']['reads_ok'] = 699; faults.append(bad)
        bad = trial(); bad['resources']['phases']['cleanup']['cpu_seconds'] = None; faults.append(bad)
        bad = trial(); bad['resources']['resource_errors'] = ['sampler exited']; faults.append(bad)
        bad = trial(); bad['resources']['phases']['workload']['cpu_seconds'] = float('nan'); faults.append(bad)
        for record in faults:
            with self.subTest(record=record), self.assertRaises(ValueError):
                pilot._trial_totals(record, 1000)

    def rows(self):
        return [dict(engine=name, pair=1, sampling_mode=mode, reads_ok=700, writes_ok=300,
                     cpu_seconds_per_success=cpu, api_cpu_seconds_per_success=cpu * 2,
                     wall_seconds=cpu * 10)
                for name in ('ctrs', 'orbstack') for mode, cpu in [('boundaries', .01), ('periodic', .012)]]

    def test_raw_pairs_reject_missing_duplicate_and_different_work(self):
        rows = self.rows()
        result = pilot._paired_controls(rows, 1)
        self.assertAlmostEqual(result['ctrs']['median_on_over_off']['cpu_seconds_per_success'], 1.2)
        bad = copy.deepcopy(rows); bad[0]['writes_ok'] -= 1
        for invalid in (rows[:-1], [*rows, rows[0]], bad):
            with self.subTest(rows=invalid), self.assertRaises(ValueError):
                pilot._paired_controls(invalid, 1)

    def test_invalid_invocation_cannot_prepare_or_access_engine(self):
        for changed in ({'run_id': '../outside'}, {'pairs': 0}, {'pairs': True},
                        {'operations': 0}, {'operations': 100001}):
            with self.subTest(changed=changed), \
                    patch.object(pilot.resource_pilot, 'ResourceEngine') as engine, \
                    patch.object(pilot.registry_portfolio, 'prepare_pinned_portfolio') as prepare:
                arguments = dict(run_id='sampler-control-test', pairs=1, operations=1000,
                                 portfolio_layout=Path('/missing'), ctrs_binary=Path('/missing')) | changed
                with self.assertRaises(ValueError):
                    pilot.run_calibration(**arguments)
            engine.assert_not_called()
            prepare.assert_not_called()

    def test_workload_pin_failure_precedes_engine_and_output_creation(self):
        with patch.object(pilot.runner, 'sha256_file', return_value='wrong'), \
                patch.object(pilot.runner, 'RunContext') as context, \
                patch.object(pilot.resource_pilot, 'ResourceEngine') as engine:
            with self.assertRaisesRegex(ValueError, 'differs.*pin'):
                pilot.run_calibration(run_id='sampler-control-test', portfolio_layout=Path('/unused'),
                                      ctrs_binary=Path(sys.executable), pairs=1, operations=1000)
        context.assert_not_called()
        engine.assert_not_called()
