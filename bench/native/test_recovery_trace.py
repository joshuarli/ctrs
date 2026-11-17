import unittest
import errno
import hashlib
import urllib.error
import recovery_trace as trace


class RecoveryTraceTests(unittest.TestCase):
    def test_host_address_error_invalidates_even_inside_expected_outage(self):
        error, error_errno = trace.transport_error(
            urllib.error.URLError(OSError(errno.EADDRNOTAVAIL, "Can't assign requested address")))
        result = trace.classify_failures([dict(started_ns=12, ended_ns=13,
                    ok=False, error=error, error_errno=error_errno)], 10, 20)
        self.assertFalse(result['host_client_valid'])
        self.assertEqual(len(result['expected_outage_errors']), 1)
        self.assertEqual(len(result['host_address_errors']), 1)

    def test_only_errors_overlapping_outage_are_expected(self):
        attempts = [dict(started_ns=a, ended_ns=b, ok=ok) for a, b, ok in
                    [(1, 9, False), (8, 11, False), (11, 19, False),
                     (19, 22, False), (21, 23, False), (5, 7, True)]]
        result = trace.classify_failures(attempts, 10, 20)
        self.assertEqual(len(result['expected_outage_errors']), 3)
        self.assertEqual(len(result['unexpected_errors']), 2)

    def test_wrong_payload_is_unexpected_even_during_outage(self):
        attempt = dict(started_ns=12, ended_ns=19, ok=False, status=201, invalid_response=True)
        result = trace.classify_failures([attempt], 10, 20)
        self.assertEqual(result['unexpected_errors'], [attempt])
        self.assertEqual(result['expected_outage_errors'], [])

    def test_persisted_items_allow_only_exact_uncertain_outage_writes(self):
        seed = [[i, f'item-{i}', hashlib.md5(str(i).encode()).hexdigest()] for i in range(1, 501)]
        ack = [{'id': 501, 'name': 'ack', 'payload': 'x'}]
        uncertain = [{'id': None, 'name': 'uncertain', 'payload': 'y'}]
        rows = seed + [[501, 'ack', 'x']]
        self.assertEqual(trace.verify_persisted_items(rows, ack, uncertain), 0)
        self.assertEqual(trace.verify_persisted_items(rows + [[503, 'uncertain', 'y']], ack, uncertain), 1)
        for invalid in (seed + [[503, 'uncertain', 'y']], seed + [[501, 'ack', 'wrong']],
                        seed + [[502, 'ack', 'x']], rows + [[503, 'uncertain', 'wrong']],
                        rows + [[503, 'unsent', 'anything']], rows + [[505, 'ack', 'x']]):
            with self.subTest(invalid=invalid[-1]), self.assertRaises(ValueError):
                trace.verify_persisted_items(invalid, ack, uncertain)

    def test_recovered_latency_excludes_outage_spanning_success(self):
        attempts = [dict(started_ns=a, ended_ns=b, ok=ok, kind=kind) for a, b, ok, kind in
                    [(2, 3, True, 'write'), (3, 4, True, 'read'), (5, 60_000_000, True, 'read'),
                     (30, 40, True, 'read'), (40, 60, True, 'write'), (60, 10_000_000, False, 'read')]]
        result = trace.workload_metrics(attempts, 10, 25, require_reads=True, require_writes=True)
        self.assertEqual(result, {'recovered_p99_ms': 20 / 1e6, 'recovered_requests_ok': 2})
        with self.assertRaisesRegex(ValueError, 'before interruption and after recovery'):
            trace.workload_metrics(attempts[:-2], 10, 25, require_reads=True, require_writes=True)

    def test_end_to_end_includes_command_even_if_service_recovers_early(self):
        result = trace.recovery_intervals(dict(start_command_begin_ns=10,
                    start_command_returned_ns=110, first_success_ns=70))
        self.assertEqual(result['restart_to_first_success_s'], 60e-9)
        self.assertEqual(result['start_command_s'], 100e-9)
        self.assertEqual(result['command_and_ready_s'], 100e-9)
        self.assertTrue(result['success_preceded_command_return'])
        self.assertEqual(result['after_command_to_first_success_s'], 0)

    def test_clock_uses_narrowest_roundtrip_and_exposes_uncertainty(self):
        result = trace.clock_bracket([dict(host_begin_ns=10, host_end_ns=110, guest_ns=80),
                                     dict(host_begin_ns=200, host_end_ns=210, guest_ns=225)])
        self.assertEqual(result, dict(guest_minus_host_ns=20, uncertainty_ns=5))
        with self.assertRaises(ValueError):
            trace.clock_bracket([dict(host_begin_ns=10, host_end_ns=9, guest_ns=2)])


if __name__ == '__main__':
    unittest.main()
