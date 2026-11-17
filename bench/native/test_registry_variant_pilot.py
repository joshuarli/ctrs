import subprocess
import json
import tempfile
from pathlib import Path
from unittest import mock
from diagnostics import registry_pilot
import unittest
from diagnostics import registry_variant_pilot as pilot


class VariantTransferProof(unittest.TestCase):
    def test_missing_image_requires_daemon_absence_response(self):
        absent = subprocess.CompletedProcess([], 1, '[]\n', 'Error response from daemon: No such image: sha256:abc\n')
        pilot.require_missing_image(absent)
        for cp in (subprocess.CompletedProcess([], 0, '[{}]', ''),
                   subprocess.CompletedProcess([], 1, '', 'Cannot connect to the Docker daemon'),
                   subprocess.CompletedProcess([], 1, '', 'permission denied')):
            with self.subTest(cp=cp), self.assertRaises(ValueError):
                pilot.require_missing_image(cp)

    def test_shared_layer_transfer_counts_once_across_repository_pulls(self):
        shared = {'digest': 'sha256:shared', 'size': 100}
        other = {'digest': 'sha256:other', 'size': 50}
        transfers = [{'digest': 'sha256:shared', 'bytes': 100, 'method': 'GET', 'complete': True}]
        pilot.require_layers_transferred([shared], transfers)
        with self.assertRaises(ValueError):
            pilot.require_layers_transferred([shared, other], transfers)
        transfers.append({'digest': 'sha256:other', 'bytes': 50, 'method': 'GET', 'complete': True})
        pilot.require_layers_transferred([shared, other], transfers)

    def test_failed_partial_and_head_requests_do_not_establish_complete_transfer(self):
        layer = {'digest': 'sha256:layer', 'size': 100}
        for changes in ({'complete': False}, {'method': 'HEAD'}, {'bytes': 99}, {'digest': 'sha256:foreign'}):
            row = {'digest': layer['digest'], 'bytes': 100, 'method': 'GET', 'complete': True} | changes
            with self.subTest(row=row), self.assertRaises(ValueError):
                pilot.require_layers_transferred([layer], [row])


class PhaseAccounting(unittest.TestCase):
    def test_warm_engine_executes_and_checks_guest_work_before_sampling(self):
        engine = mock.Mock(name='engine')
        engine.name = 'ctrs'
        engine.sh.return_value = subprocess.CompletedProcess([], 0, 'np-w8-warm\n', '')
        with mock.patch.object(pilot.ci_jobs, 'cleanup') as cleanup:
            pilot.prepare_warm_engine(engine, 'run')
        engine.ensure_up.assert_called_once_with()
        self.assertIn('--pull=never', engine.sh.call_args.args[0])
        cleanup.assert_called_once()
        engine.sh.return_value = subprocess.CompletedProcess([], 0, '', '')
        with mock.patch.object(pilot.ci_jobs, 'cleanup') as cleanup, \
             self.assertRaisesRegex(RuntimeError, 'preconditioning did not complete'):
            pilot.prepare_warm_engine(engine, 'run')
        cleanup.assert_called_once()

    def test_failed_phase_records_boundary_and_unknown_missing_counters(self):
        engine = mock.Mock()
        engine.measurement_identity = {'required_processes': []}
        result = {'resources': {'phases': {}}, 'phase_status': {}}
        boundary = {'started_monotonic': 1, 'ended_monotonic': 2, 'errors': [], 'procs': []}
        with mock.patch.object(pilot.runner.collect, 'cpu_boundary', return_value=boundary):
            with self.assertRaisesRegex(ValueError, 'work failed'):
                with pilot.measured_phase(engine, result, 'load_1000'):
                    raise ValueError('work failed')
        pilot.summarize_resources(result, engine, None)
        self.assertEqual(result['phase_status']['load_1000']['status'], 'failed')
        cell = result['resources']['phase_summaries']['load_1000']
        self.assertEqual(cell['status'], 'unknown')
        self.assertIsNone(cell['cpu_seconds'])
        self.assertIsNone(cell['peak_phys_footprint_bytes'])
        self.assertEqual(result['resources']['status'], 'unknown')

    def test_complete_phase_uses_boundary_and_trace_summary(self):
        engine = mock.Mock()
        engine.measurement_identity = {'required_processes': [{'pid': 7}]}
        result = {'resources': {'phases': {'load_1000': {'before': {}, 'after': {}}}},
                  'phase_status': {'load_1000': {'status': 'complete'}}}
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / 'resources.jsonl'
            trace.write_text(json.dumps({'monotonic': 2}) + '\n')
            with mock.patch.object(pilot.resource_cycles, 'phase_summary',
                    return_value={'status': 'ok', 'cpu_seconds': 3, 'peak_phys_footprint_bytes': 42}) as summary:
                pilot.summarize_resources(result, engine, trace)
        summary.assert_called_once_with(engine.measurement_identity, result['resources']['phases']['load_1000'],
                                        [{'monotonic': 2}])
        self.assertEqual(result['resources']['status'], 'ok')
        self.assertEqual(result['resources']['phase_summaries']['load_1000']['cpu_seconds'], 3)

    def test_failed_deployment_still_runs_owned_cleanup_phase(self):
        engine = mock.Mock()
        engine.name = 'ctrs'
        engine.sh.side_effect = [
            subprocess.CompletedProcess([], 0, '', ''),
            subprocess.CompletedProcess([], 1, '', 'No such container'),
            subprocess.CompletedProcess([], 0, '', ''),
        ]
        result = {'resources': {'phases': {}}, 'phase_status': {}}
        engine.measurement_identity = {}
        class Refs(dict):
            def items(self):
                return []

        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(pilot.runner, 'resource_phase') as resource_phase, \
             mock.patch.object(registry_pilot.runner, 'wait_health', return_value=(None, None)):
            from contextlib import nullcontext
            resource_phase.side_effect = lambda *args: nullcontext()
            with self.assertRaisesRegex(RuntimeError, 'did not become healthy'):
                registry_pilot.deploy(engine, Refs(api='api', postgres='postgres', redis='redis'), Path(directory), Path(directory), 'run', {},
                    phase=lambda name: pilot.measured_phase(engine, result, name))
        self.assertEqual(result['phase_status']['stack_health']['status'], 'failed')
        self.assertEqual(result['phase_status']['owned_cleanup']['status'], 'complete')
        self.assertIn('down', engine.sh.call_args_list[-1].args[0])

    def test_boundary_failure_does_not_skip_cleanup_body(self):
        engine = mock.Mock()
        result = {'resources': {'phases': {}}, 'phase_status': {}}
        with mock.patch.object(pilot.runner, 'resource_phase', side_effect=RuntimeError('counter')):
            with pilot.measured_phase(engine, result, 'owned_cleanup'):
                cleaned = True
        self.assertTrue(cleaned)
        pilot.summarize_resources(result, engine, None)
        self.assertEqual(result['resources']['status'], 'unknown')

    def test_summary_failure_stops_engine_persists_failure_and_rejects_result(self):
        engine = mock.Mock()
        result = {'correctness': True, 'errors': [], 'resources': {'phases': {}}, 'phase_status': {}}
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(pilot, 'summarize_resources', side_effect=OSError('damaged trace')), \
             mock.patch.object(pilot, 'host_snapshot'):
            pilot.finish_engine(result, engine, None, None, Path(directory))
            saved = json.loads((Path(directory) / 'result.json').read_text())
        engine.stop.assert_called_once_with()
        self.assertFalse(saved['correctness'])
        self.assertEqual(saved['resources']['status'], 'unknown')
        self.assertIn('damaged trace', ''.join(saved['errors']))
        with self.assertRaisesRegex(RuntimeError, 'resource coverage failed'):
            pilot.require_valid_result(saved)

    def test_empty_phase_set_cannot_pass_resource_coverage(self):
        result = {'resources': {'phases': {}}, 'phase_status': {}}
        pilot.summarize_resources(result, mock.Mock(measurement_identity={}), None)
        self.assertEqual(result['resources']['status'], 'unknown')


if __name__ == '__main__':
    unittest.main()
