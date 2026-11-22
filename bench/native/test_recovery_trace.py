import unittest
import errno
import hashlib
from copy import deepcopy
import urllib.error
import recovery_trace as trace


class RecoveryTraceTests(unittest.TestCase):
    def test_owned_engine_restart_checks_new_processes_and_same_boot_and_disk(self):
        socket = '/private/run/docker.sock'
        daemon = dict(role='daemon', pid=10, kernel_start_identity=20, executable={'sha256': 'binary'})
        vm = dict(role='vm', pid=11, kernel_start_identity=21, executable={'sha256': 'vm'},
                  boot_assets=[{'path': '/guest/Image', 'sha256': 'kernel'},
                               {'path': '/guest/initramfs.cpio', 'sha256': 'initrd'}])
        manifest = dict(engine='ctrs', socket=socket, required_processes=[daemon, vm])
        before = trace.owned_ctrs_processes(manifest, socket, daemon['pid'], 'binary')
        after = deepcopy(before)
        after['daemon'].update(pid=12, kernel_start_identity=22)
        after['vm'].update(pid=13, kernel_start_identity=23)
        trace.verify_ctrs_restart(before, after, (1, 10), (1, 10))
        with self.assertRaisesRegex(ValueError, 'requested child'):
            trace.owned_ctrs_processes(manifest, socket, 99, 'binary')
        with self.assertRaisesRegex(ValueError, 'disk identity'):
            trace.verify_ctrs_restart(before, after, (1, 10), (1, 11))
        with self.assertRaisesRegex(ValueError, 'vm process did not restart'):
            trace.verify_ctrs_restart(before, after | {'vm': vm}, (1, 10), (1, 10))
        after['vm']['boot_assets'][0]['sha256'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'booted guest artifacts changed'):
            trace.verify_ctrs_restart(before, after, (1, 10), (1, 10))

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

    def test_refusal_trace_filters_owned_target_and_anchors_the_first_exact_read(self):
        backend = trace.api_backend({
            'Id': 'api', 'Config': {'Labels': {'com.docker.compose.project': 'owned',
                                             'com.docker.compose.service': 'api'}},
            'NetworkSettings': {'Networks': {'owned_appnet': {'IPAddress': '172.20.0.4'}},
                                'Ports': {'8000/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '58264'}]}},
        }, 'owned')
        timeline = {'kill_command_begin_ns': 100_000_000, 'start_command_begin_ns': 200_000_000,
                    'start_command_returned_ns': 220_000_000, 'first_success_ns': 420_000_000}

        def attempt(start_ms, end_ms, ok, scope, offset=0):
            return {'kind': 'read', 'ok': ok, 'started_ns': start_ms * 1_000_000,
                    'ended_ns': end_ms * 1_000_000, 'scope': scope,
                    'wall_ns': 1795373100000000000 + end_ms * 1_000_000 + offset}

        requests = [attempt(199, 235, True, 'load'), attempt(240, 250, False, 'readiness', 10),
                    attempt(370, 388, True, 'load'), attempt(400, 420, True, 'readiness')]
        result = trace.refusal_recovery_trace(timeline, requests, [
            '2026-11-22T18:45:00.099Z DEBUG guest refusal cached ip=172.20.0.4 port=8000',
            '2026-11-22T18:45:00.134Z DEBUG guest refusal cached ip=172.20.0.4 port=8000',
            '2026-11-22T18:45:00.201Z DEBUG guest refusal cache first hit ip=172.20.0.5 port=8000',
            '2026-11-22T18:45:00.384Z DEBUG guest refusal cache expired ip=172.20.0.4 port=8000 hits=12 age_ms=250',
            '2026-11-22T18:45:00.450Z DEBUG guest refusal cached ip=172.20.0.4 port=8000',
        ], backend)
        self.assertEqual(result['first_exact_read_scope'], 'load')
        self.assertEqual(result['first_exact_read_end_ms'], 188)
        self.assertEqual([event['event'] for event in result['events']], ['cached', 'cache expired'])
        self.assertEqual(result['events'][1]['hits'], 12)
        self.assertEqual(result['events'][1]['since_restart_start_ms_bounds'], [183.99999, 184.999999])


if __name__ == '__main__':
    unittest.main()
