import copy
import tempfile
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import mixed_resources as resources
import resource_cells


class Growth(unittest.TestCase):
    def setUp(self):
        self.plan = resources.plan({}, {'engine': 'ctrs', 'required_processes': []})
        self.rows = [dict(cycle=i, version=resources.VERSION,
            interval={'status': 'ok', 'elapsed_s': 31, 'steady_phys_footprint_bytes': 100},
            file_descriptors={'status': 'ok', 'total': 20},
            allocation={'status': 'ok', 'allocated_bytes': 100, 'files': [{'device': 1, 'inode': 2}]}) for i in range(6)]

    def test_passing_and_peak_growth(self):
        result = resources.summarize(self.plan, self.rows)
        self.assertTrue(result['minimum_coverage_met'])
        self.assertFalse(result['qualification_eligible'])
        for key in ('physical_footprint', 'file_descriptors', 'active_disk_allocation'):
            self.assertEqual(result[key]['status'], 'pass')
        self.rows[3]['interval']['steady_phys_footprint_bytes'] += 17 * 1024 * 1024
        self.rows[3]['file_descriptors']['total'] += 17
        self.rows[3]['allocation']['allocated_bytes'] += 17 * 1024 * 1024
        result = resources.summarize(self.plan, self.rows)
        for key in ('physical_footprint', 'file_descriptors', 'active_disk_allocation'):
            self.assertEqual(result[key]['status'], 'fail')
            self.assertGreater(result[key]['return_difference'], 0)

    def test_incomplete_coverage_and_missing_cells(self):
        for rows in (self.rows[:5], copy.deepcopy(self.rows)):
            if len(rows) == 6:
                rows[2]['interval']['elapsed_s'] = 29
            result = resources.summarize(self.plan, rows)
            self.assertFalse(result['minimum_coverage_met'])
            self.assertEqual(result['physical_footprint']['status'], 'unknown')
        for cell, key in (('interval', 'physical_footprint'), ('file_descriptors', 'file_descriptors'), ('allocation', 'active_disk_allocation')):
            rows = copy.deepcopy(self.rows)
            rows[2][cell]['status'] = 'unknown'
            self.assertEqual(resources.summarize(self.plan, rows)[key]['status'], 'unknown')
        rows = copy.deepcopy(self.rows)
        rows[2]['allocation']['files'][0]['inode'] = 3
        self.assertEqual(resources.summarize(self.plan, rows)['active_disk_allocation']['status'], 'unknown')

    def test_manifest_and_native_counter_failures(self):
        manifest = {'engine': 'ctrs', 'required_processes': [
            {'pid': 1, 'role': 'daemon', 'comm': 'd', 'start_identity': 'a', 'kernel_start_identity': 1},
            {'pid': 2, 'role': 'vm', 'comm': 'v', 'start_identity': 'b', 'kernel_start_identity': 2}]}
        def sample(t):
            return {'monotonic': t, 'ownership_verified': True, 'procs': [dict(p, cputime_s=t, user_cpu_s=t, system_cpu_s=t, pkg_idle_wakeups=t, interrupt_wakeups=t, footprint_bytes=1, counter_method='native', footprint_method='rusage_info_v0.ri_phys_footprint') for p in manifest['required_processes']]}
        for fault in ('vm', 'counter', 'identity'):
            samples = [sample(1), sample(32)]
            if fault == 'vm': samples[1]['procs'].pop()
            if fault == 'counter': samples[1]['procs'][1]['interrupt_wakeups'] = None
            if fault == 'identity': samples[1]['procs'][1]['kernel_start_identity'] = 9
            self.assertEqual(resource_cells.interval_summary(manifest, samples)['status'], 'unknown')

    def test_files_require_owned_open_handle_and_stable_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'disk'; path.write_bytes(b'data')
            manifest = {'engine': 'ctrs', 'required_processes': [{'pid': 1, 'role': 'vm', 'kernel_start_identity': 4}]}
            with patch.object(resources, 'Counters') as counters, patch.object(resources.ownership, 'open_files') as files:
                counters.return_value.read.return_value = {'kernel_start_identity': 4}
                files.return_value = []
                self.assertEqual(resources.allocation(manifest, [str(path)])['status'], 'unknown')
                files.return_value = [{'fd': '3', 'n': str(path), 'i': str(path.stat().st_ino)}]
                self.assertEqual(resources.allocation(manifest, [str(path)])['status'], 'ok')
                counters.return_value.read.return_value = {'kernel_start_identity': 5}
                self.assertEqual(resources.allocation(manifest, [str(path)])['status'], 'unknown')
                self.assertEqual(resources.allocation(manifest, [])['status'], 'unknown')
                self.assertEqual(resources.allocation(manifest, [str(path), str(path)])['status'], 'unknown')
                link = Path(tmp) / 'link'; link.symlink_to(path)
                self.assertEqual(resources.allocation(manifest, [str(link)])['status'], 'unknown')

    def test_missing_required_fd_invalidates_total(self):
        manifest = {'engine': 'ctrs', 'required_processes': [
            {'pid': 1, 'role': 'daemon', 'kernel_start_identity': 1},
            {'pid': 2, 'role': 'vm', 'kernel_start_identity': 2}]}
        lib = MagicMock()
        lib.proc_pidinfo.side_effect = [8, 8, 0]
        with patch.object(resources.sys, 'platform', 'darwin'), \
             patch.object(resources.os, 'uname') as uname, \
             patch.object(resources.ctypes, 'CDLL', return_value=lib), \
             patch.object(resources, 'Counters') as counters:
            uname.return_value.machine = 'arm64'
            counters.return_value.read.side_effect = lambda pid: {'kernel_start_identity': pid}
            result = resources.fd_snapshot(manifest)
        self.assertEqual(result['status'], 'unknown')
        self.assertIsNone(result['total'])
        self.assertEqual(len(result['processes']), 1)
        self.assertTrue(result['errors'])

    def test_config_bounds(self):
        for config in ({'seconds': 0}, {'seconds': 3601}, {'seconds': float('nan')}, {'owned_files': []}):
            with self.assertRaises(ValueError): resources.plan(config, {})
