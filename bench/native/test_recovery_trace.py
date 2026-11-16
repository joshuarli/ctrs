import unittest
import recovery_trace as trace


class RecoveryTraceTests(unittest.TestCase):
    def test_only_errors_overlapping_outage_are_expected(self):
        attempts = [dict(started_ns=a, ended_ns=b, ok=ok) for a, b, ok in
                    [(1, 9, False), (8, 11, False), (11, 19, False),
                     (19, 22, False), (21, 23, False), (5, 7, True)]]
        result = trace.classify_failures(attempts, 10, 20)
        self.assertEqual(len(result['expected_outage_errors']), 3)
        self.assertEqual(len(result['unexpected_errors']), 2)

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
