"""Cross-check native counters against independent OS clocks and failures."""
import os
import sys
import time
import unittest
from unittest.mock import Mock

import collect
from macos_counters import Counters, host_cpu_ticks


class CoverageTests(unittest.TestCase):
    def test_missing_vm_preserves_error_and_invalidates_boundary(self):
        counters = Mock()
        counters.read.side_effect = [{'pid': 1, 'kernel_start_identity': 10,
                                     'cputime_s': 1}, ProcessLookupError('VM gone')]
        required = {1: {'kernel_start_identity': 10, 'comm': 'daemon', 'start_identity': 'a'},
                    2: {'kernel_start_identity': 20, 'comm': 'VM', 'start_identity': 'b'}}
        result = collect.native_sample(counters, required)
        self.assertEqual(len(result['procs']), 1)
        self.assertIn('required process 2', result['errors'][0])
        self.assertIsNone(collect.cpu_delta(result, result)['cpu_seconds'])

    def test_pid_reuse_rejected_at_kernel_start_precision(self):
        counters = Mock()
        counters.read.return_value = {'pid': 1, 'kernel_start_identity': 11}
        result = collect.native_sample(counters, {1: {'kernel_start_identity': 10}})
        self.assertEqual(result['procs'], [])
        self.assertIn('start identity changed', result['errors'][0])


@unittest.skipUnless(sys.platform == 'darwin' and os.uname().machine == 'arm64',
                     'native ARM64 macOS counters')
class NativeCounterTests(unittest.TestCase):
    def test_host_ticks_advance_at_subsecond_phase_boundaries(self):
        previous = host_cpu_ticks()
        for _ in range(24):
            time.sleep(.05)
            current = host_cpu_ticks()
            self.assertNotEqual(current, previous, 'host CPU tick snapshot repeated')
            previous = current

    def test_cpu_units_match_process_clock_and_bad_pid_errors(self):
        counters = Counters()
        before = counters.read(os.getpid())
        start = time.process_time()
        while time.process_time() - start < .02:
            pass
        after = counters.read(os.getpid())
        elapsed = time.process_time() - start
        self.assertAlmostEqual(after['cputime_s'] - before['cputime_s'], elapsed, delta=.005)
        self.assertEqual(before['kernel_start_identity'], after['kernel_start_identity'])
        self.assertGreater(after['footprint_bytes'], 0)
        with self.assertRaises(OSError):
            counters.read(2147483647)
