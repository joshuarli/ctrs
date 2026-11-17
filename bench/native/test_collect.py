"""Regression cases for incomplete macOS resource measurements."""
import json
from pathlib import Path
import tempfile
import unittest
import time
from types import SimpleNamespace
from unittest.mock import patch

import collect
import runner


class ResourceTests(unittest.TestCase):
    def summary(self, records):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / 'trace.jsonl'
            trace.write_text(''.join(json.dumps(r) + '\n' for r in records))
            return runner.summarize_trace(trace)

    def sample(self, cpu=2.0, vm_cpu=10.0, owned=True):
        return {'t': cpu, 'ownership_verified': owned, 'procs': [
            {'pid': 1, 'start_identity': 'daemon-start', 'cputime_s': cpu},
            {'pid': 2, 'start_identity': 'vm-start', 'cputime_s': vm_cpu}],
            'footprint': {'required_pids': [1, 2],
                          'values': {'1': 100, '2': 100000}, 'error': None}}

    def test_real_auxiliary_field_wins_over_category(self):
        output = 'daemon [1]: Footprint: 10 B\n    phys_footprint: 100 B\nVM [2]: Footprint: 20 B\n    phys_footprint: 100000 B\n'
        self.assertEqual(collect.parse_footprint(output), {1: 100, 2: 100000})

    def test_real_shared_category_heading_does_not_change_owner(self):
        output = ("OrbStack Helper [1396]: 64-bit    Footprint: 1014130776 B\n"
                  "Shared with OrbStack [1299]:\n"
                  "Auxiliary data:\n    phys_footprint: 15389157464 B\n"
                  "OrbStack [1299]: 64-bit    Footprint: 72008736 B\n"
                  "Shared with OrbStack Helper [1396]:\n"
                  "Auxiliary data:\n    phys_footprint: 72008736 B\n")
        self.assertEqual(collect.parse_footprint(output),
                         {1396: 15389157464, 1299: 72008736})

    def test_category_only_is_unknown(self):
        self.assertEqual(collect.parse_footprint('VM [2]: Footprint: 20 B\n'), {})

    def test_missing_large_vm_never_scores_small_daemon(self):
        sample = self.sample()
        del sample['footprint']['values']['2']
        result = self.summary([sample])
        self.assertIsNone(result['peak_phys_footprint_bytes'])
        self.assertEqual(result['footprint_samples'], 0)

    def test_one_exact_counter_cannot_hide_missing_vm_counter(self):
        result = self.summary([self.sample(), self.sample(3, None)])
        self.assertIsNone(result['cpu_seconds_est'])
        self.assertFalse(result['cpu_counters_complete'])

    def test_single_boundary_is_not_zero_cpu(self):
        self.assertIsNone(self.summary([self.sample()])['cpu_seconds_est'])

    def test_complete_pair_counts_every_process(self):
        result = self.summary([self.sample(), self.sample(3, 12)])
        self.assertEqual(result['cpu_seconds_est'], 3)
        self.assertEqual(result['peak_phys_footprint_bytes'], 100100)

    def test_discovery_does_not_qualify(self):
        result = self.summary([self.sample(owned=False), self.sample(3, 12, False)])
        self.assertIsNone(result['cpu_seconds_est'])
        self.assertIsNone(result['peak_phys_footprint_bytes'])

    def test_reused_pid_invalidates_cpu(self):
        sample = self.sample(3, 12)
        sample['procs'][1]['start_identity'] = 'replacement'
        self.assertIsNone(self.summary([self.sample(), sample])['cpu_seconds_est'])


if __name__ == '__main__':
    unittest.main()

class BoundaryTests(unittest.TestCase):
    def test_short_operation_has_two_explicit_cpu_boundaries(self):
        def boundary(value):
            return {'errors': [], 'procs': [
                {'pid': 1, 'start_identity': 'daemon', 'cputime_s': value},
                {'pid': 2, 'start_identity': 'VM', 'cputime_s': value * 10}]}
        result = collect.cpu_delta(boundary(1), boundary(1.01))
        self.assertAlmostEqual(result['cpu_seconds'], .11)
        self.assertEqual(result['errors'], [])
        broken = boundary(1.01)
        broken['procs'][1]['cputime_s'] = None
        self.assertIsNone(collect.cpu_delta(boundary(1), broken)['cpu_seconds'])

    def test_terminal_footprint_does_not_erase_cpu_coverage(self):
        fixture = ResourceTests()
        samples = [fixture.sample(), fixture.sample(3, 12)]
        samples.append({'record_type': 'footprint_only', 'footprint': {
            'required_pids': [1, 2], 'values': {'1': 100, '2': 200000}, 'error': None}})
        result = fixture.summary(samples)
        self.assertEqual(result['cpu_seconds_est'], 3)
        self.assertEqual(result['peak_phys_footprint_bytes'], 200100)


class SamplerLifecycleTests(unittest.TestCase):
    def test_early_collector_exit_invalidates_partial_resource_trace(self):
        fixture = ResourceTests()
        samples = ''.join(json.dumps(row) + '\n' for row in
                          [fixture.sample(), fixture.sample(3, 12)])
        for code in (0, 7):
            with self.subTest(exit_status=code), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                collector = root / 'collector.py'
                collector.write_text(
                    'import sys\nfrom pathlib import Path\n'
                    f'Path(sys.argv[sys.argv.index("--out") + 1]).write_text({samples!r})\n'
                    'print("collector ended early", file=sys.stderr)\n'
                    f'raise SystemExit({code})\n')
                engine = SimpleNamespace(name='ctrs', socket='unix:///owned.sock', dir=root)
                with patch.object(runner, 'COLLECT', collector), \
                        patch.object(runner.ownership, 'discover', return_value={'required_processes': []}):
                    sampler, trace = runner.start_sampler(engine, root)
                self.assertEqual(sampler.process.wait(timeout=5), code)
                self.assertEqual(runner.summarize_trace(trace)['cpu_seconds_est'], 3)
                runner.stop_sampler(sampler)
                summary = runner.summarize_trace(trace)
                self.assertIsNone(summary['cpu_seconds_est'])
                self.assertIsNone(summary['peak_phys_footprint_bytes'])
                self.assertTrue(any('before requested stop' in error for error in summary['resource_errors']))
                self.assertIn('collector ended early', sampler.stderr.read_text())

    def test_exit_between_liveness_check_and_signal_cannot_keep_partial_totals(self):
        fixture = ResourceTests()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trace = root / 'resources.jsonl'
            trace.write_text(''.join(json.dumps(row) + '\n' for row in
                                    [fixture.sample(), fixture.sample(3, 12)]))
            process = runner.subprocess.Popen([runner.sys.executable, '-c', 'raise SystemExit(0)'])
            self.assertEqual(process.wait(timeout=5), 0)
            sampler = runner.Sampler(process, trace, root / 'sampler.stderr')
            with patch.object(process, 'poll', return_value=None):
                runner.stop_sampler(sampler)
            summary = runner.summarize_trace(trace)
            self.assertIsNone(summary['cpu_seconds_est'])
            self.assertIsNone(summary['peak_phys_footprint_bytes'])
            self.assertTrue(any('did not acknowledge' in error for error in summary['resource_errors']))

    def test_requested_stop_keeps_complete_collector_samples(self):
        fixture = ResourceTests()
        samples = ''.join(json.dumps(row) + '\n' for row in
                          [fixture.sample(), fixture.sample(3, 12)])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            collector = root / 'collector.py'
            ready = root / 'ready'
            collector.write_text(
                'import json, os, signal, sys, time\nfrom pathlib import Path\n'
                'def stop(*_):\n'
                f'    Path({str(collect.stop_receipt_path(root / "resources.jsonl"))!r}).write_text(json.dumps({{"pid":os.getpid(),"sampler_version":{collect.SAMPLER_VERSION!r},"stop_requested_monotonic":time.monotonic()}}))\n'
                '    sys.exit(0)\n'
                'signal.signal(signal.SIGTERM, stop)\n'
                f'Path(sys.argv[sys.argv.index("--out") + 1]).write_text({samples!r})\n'
                f'Path({str(ready)!r}).touch()\n'
                'signal.pause()\n')
            engine = SimpleNamespace(name='ctrs', socket='unix:///owned.sock', dir=root)
            with patch.object(runner, 'COLLECT', collector), \
                    patch.object(runner.ownership, 'discover', return_value={'required_processes': []}):
                sampler, trace = runner.start_sampler(engine, root)
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(ready.exists(), 'collector did not reach readiness')
                runner.stop_sampler(sampler)
                summary = runner.summarize_trace(trace)
                self.assertEqual(sampler.process.returncode, 0)
                self.assertEqual(summary['cpu_seconds_est'], 3)
                self.assertEqual(summary['peak_phys_footprint_bytes'], 100100)
                self.assertEqual(summary['resource_errors'], [])
            finally:
                if sampler.process.poll() is None:
                    sampler.process.kill()
                    sampler.process.wait(timeout=5)
