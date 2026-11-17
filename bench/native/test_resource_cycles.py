import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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
    def test_idle_window_spans_the_requested_counter_interval(self):
        manifest, before = manifest_and_boundary()
        boundaries = [copy.deepcopy(before) for _ in range(3)]
        for boundary, stamp in zip(boundaries, (10., 39.5, 40.)):
            boundary.update(started_monotonic=stamp, ended_monotonic=stamp + .0001)
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(cycles.collect, 'cpu_boundary', side_effect=boundaries), \
             patch.object(cycles.time, 'monotonic', side_effect=(0., 10., 39.5, 40.)), \
             patch.object(cycles.time, 'sleep'):
            result = cycles.idle_interval(manifest, 30, Path(tmp) / 'idle.jsonl')
        self.assertEqual(result['sample_count'], 3)
        self.assertGreaterEqual(result['elapsed_s'], result['requested_seconds'])

    def test_fixture_service_is_included_and_cannot_silently_disappear(self):
        manifest, phase = self.phase()
        fixture = copy.deepcopy(phase['before']['procs'][0])
        fixture.update(pid=303, role='fixture-coordinator', comm='python', start_identity='303',
                       kernel_start_identity=303, footprint_bytes=2000)
        manifest['required_processes'].append({k: fixture[k] for k in
            ('pid', 'role', 'comm', 'start_identity', 'kernel_start_identity')})
        phase['before']['procs'].append(fixture)
        after = copy.deepcopy(fixture)
        after.update(cputime_s=10.002, user_cpu_s=6.001, system_cpu_s=4.001)
        phase['after']['procs'].append(after)
        complete = cycles.phase_summary(manifest, phase, [])
        self.assertEqual(complete['status'], 'ok')
        self.assertAlmostEqual(complete['cpu_seconds'], .006)
        self.assertEqual(complete['peak_phys_footprint_bytes'], 3008)
        phase['after']['procs'].pop()
        missing = cycles.phase_summary(manifest, phase, [])
        self.assertEqual(missing['status'], 'unknown')
        self.assertIsNone(missing['cpu_seconds'])
        self.assertIsNone(missing['peak_phys_footprint_bytes'])

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

    def test_sampler_failure_invalidates_each_phase_without_losing_its_error(self):
        manifest, phase = self.phase()
        error = 'sampler exited before requested stop: exit 7'
        result = cycles.phase_summary(manifest, phase, [
            {'record_type': 'sampler_exit', 'error': error, 'exit_status': 7}])
        self.assertEqual(result['status'], 'unknown')
        self.assertIn(error, result['errors'])
        self.assertIsNone(result['cpu_seconds'])
        self.assertIsNone(result['peak_phys_footprint_bytes'])
        self.assertEqual(result['interior_sample_count'], 0)

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
