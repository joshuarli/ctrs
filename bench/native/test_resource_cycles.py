import copy
import unittest

import resource_cycles as cycles


def manifest_and_boundary():
    processes = []
    for pid, role, footprint in ((101, 'daemon', 8), (202, 'vm', 1000)):
        processes.append(dict(pid=pid, role=role, comm=role, start_identity=str(pid),
            kernel_start_identity=pid, footprint_bytes=footprint,
            cputime_s=10., user_cpu_s=6., system_cpu_s=4., pkg_idle_wakeups=10,
            interrupt_wakeups=20, counter_method='native',
            footprint_method='rusage_info_v0.ri_phys_footprint'))
    manifest = dict(engine='ctrs', method='test-owned', required_processes=[
        {k: p[k] for k in ('pid', 'role', 'comm', 'start_identity', 'kernel_start_identity')}
        for p in processes])
    return manifest, dict(started_monotonic=10., ended_monotonic=10.0001, procs=processes, errors=[])


class ResourceCycleTests(unittest.TestCase):
    def test_nonfinite_duration_never_starts_unbounded_collection(self):
        for seconds, interval in ((float('nan'), .2), (float('inf'), .2), (1, float('nan'))):
            with self.subTest(seconds=seconds, interval=interval), self.assertRaises(ValueError):
                cycles.idle_interval({}, seconds, None, interval)

    def phase(self):
        manifest, before = manifest_and_boundary()
        after = copy.deepcopy(before)
        after.update(started_monotonic=10.01, ended_monotonic=10.0101)
        after['procs'][1].update(cputime_s=10.004, user_cpu_s=6.002, system_cpu_s=4.002)
        phase = dict(before=before, after=after, operation_started_monotonic=10.0001,
                     operation_ended_monotonic=10.01, operation_wall_seconds=.0099)
        return manifest, phase

    def test_short_work_has_exact_boundaries_without_interior_sample(self):
        manifest, phase = self.phase()
        outside = cycles.boundary_sample(manifest, phase['before'])
        outside['monotonic'] = 9
        outside['procs'] = []
        result = cycles.phase_summary(manifest, phase, [outside])
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['interior_sample_count'], 0)
        self.assertAlmostEqual(result['cpu_seconds'], .004)
        self.assertEqual(result['peak_phys_footprint_bytes'], 1008)
        self.assertAlmostEqual(result['operation_wall_seconds'], .0099)
        self.assertAlmostEqual(result['boundary_collection_seconds'][0], .0001)

    def test_small_daemon_without_large_vm_is_never_small_engine(self):
        for fault in ('boundary', 'interior'):
            with self.subTest(fault=fault):
                manifest, phase = self.phase()
                samples = []
                if fault == 'boundary':
                    phase['after']['procs'].pop()
                else:
                    sample = cycles.boundary_sample(manifest, copy.deepcopy(phase['before']))
                    sample.update(monotonic=10.005)
                    sample['procs'].pop()
                    samples.append(sample)
                result = cycles.phase_summary(manifest, phase, samples)
                self.assertEqual(result['status'], 'unknown')
                self.assertIsNone(result['peak_phys_footprint_bytes'])
                self.assertIsNone(result['cpu_seconds'])

    def test_growth_needs_five_cycles_and_keeps_unknown_disk_unknown(self):
        initial = dict(steady_phys_footprint_bytes=1008, allocated_bytes=4096)
        cycle = dict(reclaimed=dict(status='ok', steady_phys_footprint_bytes=1008),
                     allocation_reclaimed=dict(status='ok', allocated_bytes=4096))
        result = cycles.cycle_growth(initial, [cycle] * 2)
        self.assertEqual(result['footprint']['status'], 'unknown')
        self.assertEqual(result['active_disk_allocation']['status'], 'unknown')
        result = cycles.cycle_growth(initial, [cycle] * 5)
        self.assertEqual(result['footprint']['status'], 'pass')
        self.assertEqual(result['active_disk_allocation']['status'], 'pass')
        self.assertEqual(result['exclusive_allocation']['status'], 'unknown')
        self.assertEqual(result['build_cache']['status'], 'unknown')
        invalid = copy.deepcopy(cycle)
        invalid['allocation_reclaimed'].update(status='unknown', allocated_bytes=None)
        self.assertEqual(cycles.cycle_growth(initial, [cycle] * 4 + [invalid])['active_disk_allocation']['status'], 'unknown')


class ComparisonTests(unittest.TestCase):
    def test_unknown_vm_coverage_cannot_become_memory_win(self):
        manifest, boundary = manifest_and_boundary()
        phase = dict(before=boundary, after=copy.deepcopy(boundary),
            operation_started_monotonic=10.0001, operation_ended_monotonic=11,
            operation_wall_seconds=.9999)
        phase['after'].update(started_monotonic=11, ended_monotonic=11.0001)
        complete = cycles.phase_summary(manifest, phase, [])
        invalid = copy.deepcopy(complete)
        invalid.update(status='unknown', peak_phys_footprint_bytes=8,
                       steady_phys_footprint_bytes=8)
        def report(cell):
            return dict(initial_idle=cell, cycles=[dict(index=0, work_trial_id='trial',
                next_use_seconds=1, reclaimed=cell,
                phases={p: cell for p in ('setup', 'workload', 'cleanup')})])
        result = cycles.compare_runs(report(complete), report(invalid))
        self.assertEqual(result['idle']['steady_phys_footprint_bytes']['status'], 'unknown')
        self.assertEqual(result['cycles'][0]['workload']['peak_phys_footprint_bytes']['status'], 'unknown')
        self.assertEqual(result['storage']['status'], 'unknown')
        self.assertFalse(result['qualification_eligible'])
        self.assertEqual(cycles.compare_runs(report(complete), dict(initial_idle=complete, cycles=[]))['cycles'], [])


if __name__ == '__main__':
    unittest.main()
