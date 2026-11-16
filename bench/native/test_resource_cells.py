import copy
import os
from pathlib import Path
import tempfile
import unittest

import resource_cells as cells


class IntervalTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {'engine': 'ctrs', 'method': 'owned socket and disk',
                         'required_processes': [
                             {'pid': 1, 'role': 'daemon', 'comm': 'daemon', 'start_identity': 'a', 'kernel_start_identity': 11},
                             {'pid': 2, 'role': 'vm', 'comm': 'vm', 'start_identity': 'b', 'kernel_start_identity': 22}]}

    def sample(self, t, step):
        procs = []
        for expected in self.manifest['required_processes']:
            pid = expected['pid']
            procs.append(dict(expected, cputime_s=pid * (1 + step),
                              user_cpu_s=pid * (.6 + step * .6),
                              system_cpu_s=pid * (.4 + step * .4),
                              pkg_idle_wakeups=pid * (10 + step * 4),
                              interrupt_wakeups=pid * (5 + step * 2),
                              footprint_bytes=pid * (100 + step * 10),
                              counter_method='proc_pid_rusage RUSAGE_INFO_V0; Mach timebase conversion',
                              footprint_method='rusage_info_v0.ri_phys_footprint'))
        return {'monotonic': t, 'ownership_verified': True, 'ownership_errors': [],
                'sampler_version': '3-native-rusage', 'procs': procs}

    def test_complete_idle_interval(self):
        result = cells.interval_summary(self.manifest, [self.sample(10, 0), self.sample(11, 1), self.sample(12, 2)])
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['elapsed_s'], 2)
        self.assertEqual(result['cpu_seconds'], 6)
        self.assertAlmostEqual(result['user_cpu_seconds'], 3.6)
        self.assertAlmostEqual(result['system_cpu_seconds'], 2.4)
        self.assertEqual(result['idle_cpu_cores'], 3)
        self.assertEqual(result['pkg_idle_wakeups_per_s'], 12)
        self.assertEqual(result['interrupt_wakeups_per_s'], 6)
        self.assertEqual(result['steady_phys_footprint_bytes'], 330)
        self.assertEqual(result['peak_phys_footprint_bytes'], 360)
        self.assertEqual(result['sample_provenance'][0]['sampler_version'], '3-native-rusage')
        self.assertEqual(result['ownership_method'], 'owned socket and disk')

    def test_missing_vm_or_counter_and_pid_reuse_invalidate_all_totals(self):
        for fault in ('missing_vm', 'counter', 'identity', 'manifest_vm', 'decrease'):
            with self.subTest(fault=fault):
                manifest = copy.deepcopy(self.manifest)
                samples = [self.sample(10, 0), self.sample(11, 1)]
                if fault == 'missing_vm':
                    samples[1]['procs'].pop()
                elif fault == 'counter':
                    samples[1]['procs'][1]['interrupt_wakeups'] = None
                elif fault == 'identity':
                    samples[1]['procs'][1]['kernel_start_identity'] = 99
                elif fault == 'manifest_vm':
                    manifest['required_processes'].pop()
                    for sample in samples:
                        sample['procs'].pop()
                else:
                    samples[1]['procs'][1]['user_cpu_s'] = 0
                result = cells.interval_summary(manifest, samples)
                self.assertEqual(result['status'], 'unknown')
                self.assertIsNone(result['cpu_seconds'])
                self.assertIsNone(result['peak_phys_footprint_bytes'])
                self.assertTrue(result['errors'])

    def test_no_single_sample_or_unverified_ownership(self):
        sample = self.sample(10, 0)
        self.assertEqual(cells.interval_summary(self.manifest, [sample])['status'], 'unknown')
        sample['ownership_verified'] = False
        self.assertEqual(cells.interval_summary(self.manifest, [sample, self.sample(11, 1)])['status'], 'unknown')


class AcceptanceTests(unittest.TestCase):
    def test_explicit_larger_budget_and_unknown(self):
        self.assertEqual(cells.compare_budget(100, 104, absolute_tolerance=5, relative_tolerance=.03)['status'], 'pass')
        self.assertEqual(cells.compare_budget(1000, 1031, absolute_tolerance=5, relative_tolerance=.03)['status'], 'fail')
        self.assertEqual(cells.compare_budget(None, 1, absolute_tolerance=5, relative_tolerance=.03)['status'], 'unknown')

    def test_post_warmup_growth_and_return(self):
        args = dict(warmup_cycles=1, minimum_cycles=5, growth_budget=16,
                    return_tolerance=30, reference_growth=2)
        good = cells.evaluate_cycles(100, [110, 112, 114, 116, 118, 125], **args)
        self.assertEqual(good['status'], 'pass')
        self.assertEqual(good['post_warmup_growth'], 13)
        self.assertEqual(cells.evaluate_cycles(100, [110, 112, 114, 116, 118, 135], **args)['growth_status'], 'fail')
        self.assertEqual(cells.evaluate_cycles(80, [110, 112, 114, 116, 118, 125], **args)['return_status'], 'fail')
        self.assertEqual(cells.evaluate_cycles(100, [110, 112], **args)['status'], 'unknown')
        self.assertEqual(cells.evaluate_cycles(100, [110, 112, 114, None, 118, 125], **args)['status'], 'unknown')
        args['reference_growth'] = None
        self.assertEqual(cells.evaluate_cycles(100, [110, 112, 114, 116, 118, 125], **args)['status'], 'unknown')

    def test_sparse_file_allocation_and_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sparse'
            with path.open('wb') as out:
                out.seek(8 * 1024 * 1024)
                out.write(b'x')
            snapshot = cells.allocation_snapshot([path])
            st = path.stat()
            self.assertEqual(snapshot['status'], 'ok')
            self.assertEqual(snapshot['allocated_bytes'], st.st_blocks * 512)
            self.assertEqual(snapshot['files'][0]['logical_bytes'], 8 * 1024 * 1024 + 1)
            self.assertEqual((snapshot['files'][0]['device'], snapshot['files'][0]['inode']), (st.st_dev, st.st_ino))
            self.assertEqual(snapshot['files'][0]['filesystem_free_bytes'], os.statvfs(path).f_bavail * os.statvfs(path).f_frsize)
            self.assertIsNone(snapshot['exclusive_allocated_bytes'])
            self.assertEqual(snapshot['exclusive_allocation_status'], 'unsupported')
            missing = cells.allocation_snapshot([path, Path(directory) / 'missing'])
            self.assertEqual(missing['status'], 'unknown')
            self.assertIsNone(missing['allocated_bytes'])
            self.assertEqual(cells.allocation_snapshot([path, path])['status'], 'unknown')


if __name__ == '__main__':
    unittest.main()
