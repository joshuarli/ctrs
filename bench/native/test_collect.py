"""Regression cases for incomplete macOS resource measurements."""
import json
from pathlib import Path
import tempfile
import unittest

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
