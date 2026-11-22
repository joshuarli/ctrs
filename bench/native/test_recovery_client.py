import http.server
import errno
import hashlib
import json
import signal
import socket
import socketserver
import threading
import unittest
from unittest.mock import Mock, patch

import recovery_client
import runner
from test_safety import FixtureContext, completed, fake_engine
from pathlib import Path
from contextlib import nullcontext
import tempfile


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(('127.0.0.1', 0), _Handler)
        self.accepted = 0
        self.requests_seen = 0
        self.health_body = {'ok': True}

    def get_request(self):
        result = super().get_request()
        self.accepted += 1
        return result


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def do_GET(self):
        self.server.requests_seen += 1
        if self.path == '/items?limit=25':
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()
            return
        body = json.dumps(self.server.health_body).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class PersistentProbeTests(unittest.TestCase):
    def test_w10_database_interruption_uses_persistent_attempts_and_exact_rows(self):
        self.recovery_run('db')

    def test_w10_owned_engine_interruption_requires_new_generation_and_exact_rows(self):
        self.recovery_run('engine')

    def recovery_run(self, interrupt_service):
        healthy = threading.Event()
        healthy.set()
        rows = [[i, f'item-{i}', hashlib.md5(str(i).encode()).hexdigest()] for i in range(1, 501)]
        rows_lock = threading.Lock()

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def respond(self, status, value):
                body = json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if healthy.is_set():
                    self.respond(200, {'items': [{'id': i, 'name': f'item-{i}'} for i in range(1, 26)]})
                else:
                    self.respond(503, {})

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if not healthy.is_set():
                    self.respond(503, {})
                    return
                with rows_lock:
                    identity = len(rows) + 1
                    rows.append([identity, request['name'], request['payload']])
                self.respond(201, {'id': identity, 'name': request['name']})

            def log_message(self, *args):
                pass

        with http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server, \
                tempfile.TemporaryDirectory() as tmp:
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                engine = fake_engine('ctrs' if interrupt_service == 'engine' else 'orbstack')
                engine.compose.side_effect = lambda _, args, **kw: completed(f'owned-{args[-1]}\n' if args[0] == 'ps' else '')

                if interrupt_service == 'engine':
                    engine.recovery_root = Path(tmp) / 'private'
                    engine.proc.poll.return_value = None
                    engine.ensure_up.side_effect = lambda **kw: healthy.set()

                def effects(args, **kwargs):
                    if args == ['kill', 'owned-db']:
                        healthy.clear()
                    elif args == ['start', 'owned-db']:
                        healthy.set()
                    elif args[:4] == ['exec', 'owned-db', 'sh', '-ec']:
                        self.assertEqual('sync ' in args[-1], healthy.is_set() and not crash.called)
                        return completed('a' * 64 + ' /data/pg_hba.conf')
                    elif args[:2] == ['exec', 'owned-db']:
                        return completed(json.dumps(rows))
                    else:
                        raise AssertionError(args)
                    return completed()

                engine.sh.side_effect = effects
                identities = [({'daemon': {'pid': 1}}, (1, 2)), ({'daemon': {'pid': 2}}, (1, 2))]
                inputs = {'portfolio_sha256': 'portfolio', 'seed_sha256': 'seed'}
                with patch.object(runner, 'free_port', return_value=server.server_port), \
                        patch.object(runner, 'prepare_pinned_stack', return_value=({}, inputs)) as provision, \
                        patch.object(runner, 'wait_health', return_value=(0, {})), \
                        patch.object(runner, 'start_sampler', return_value=(None, None)), \
                        patch.object(runner, 'resource_phase', return_value=nullcontext()), \
                        patch.object(runner, 'sha256_file', return_value='binary'), \
                        patch.object(runner, '_w10_engine_identity', side_effect=identities), \
                        patch.object(runner, '_w10_crash_engine', side_effect=lambda *args: healthy.clear()) as crash, \
                        patch.object(runner.recovery_trace, 'verify_ctrs_restart') as verify_restart:
                    rec = runner.trial_w10(FixtureContext(tmp), engine, 'warm', duration=1.4, concurrency=2,
                                           write_ratio=.5, kill_at=.4, down_for=.2, interrupt_service=interrupt_service)
                self.assertTrue(rec['correctness']['ok'], rec)
                self.assertEqual(rec['paired_inputs'], inputs)
                self.assertEqual(provision.call_args.kwargs['layout'],
                                 runner.WORK / 'inputs/w8-portfolio-v6/layout' if interrupt_service == 'engine' else None)
                for call in engine.compose.call_args_list:
                    self.assertEqual(call.kwargs['override'].name, 'pinned-compose.json')
                if interrupt_service == 'engine':
                    self.assertFalse(rec['measurement_valid'])
                    self.assertTrue(rec['correctness']['checks']['database_startup_auth_preserved'])
                    crash.assert_called_once()
                    verify_restart.assert_called_once_with(
                        identities[0][0], identities[1][0], (1, 2), (1, 2))
                    self.assertTrue(any('--no-build' in call.args[1] and 'never' in call.args[1]
                                        for call in engine.compose.call_args_list))
                self.assertGreater(rec['metrics']['expected_outage_errors'], 0)
                self.assertEqual(rec['metrics']['unexpected_errors'], 0)
                self.assertEqual(rec['metrics']['acknowledged_writes'], len(rows) - 500)
                self.assertGreater(rec['metrics']['recovered_p99_ms'], 0)
                attempts = [json.loads(line) for line in
                            (Path(tmp) / engine.name / 'W10/attempts.jsonl').read_text().splitlines()]
                self.assertTrue(any(attempt['reused_socket'] for attempt in attempts))
                self.assertEqual(rec['metrics']['requests_ok'], sum(
                    attempt['scope'] == 'load' and attempt['ok'] for attempt in attempts))
                self.assertTrue(any(attempt['scope'] == 'readiness' and attempt['ok']
                                    for attempt in attempts))
            finally:
                server.shutdown()
                thread.join(timeout=2)

    def test_planned_crash_checks_child_and_waits_for_old_vm(self):
        engine = fake_engine('ctrs')
        engine.proc = Mock(pid=10)
        child = engine.proc
        child.poll.return_value = None
        child.wait.return_value = -signal.SIGKILL
        before = {'daemon': {'pid': 10}, 'vm': {'pid': 11, 'start_identity': 'old'}}
        with patch.object(runner.ownership, 'process_table', side_effect=[
                {11: {'start_identity': 'old'}}, {11: {'start_identity': 'unrelated'}}]) as table, \
                patch.object(runner.time, 'sleep'):
            with self.assertRaisesRegex(ValueError, 'daemon identity changed'):
                runner._w10_crash_engine(engine, before | {'daemon': {'pid': 99}}, runner.time.monotonic() + 1)
            with self.assertRaisesRegex(TimeoutError, 'deadline expired'):
                runner._w10_crash_engine(engine, before, runner.time.monotonic() - 1)
            child.kill.assert_not_called()
            runner._w10_crash_engine(engine, before, runner.time.monotonic() + 1)
        child.kill.assert_called_once()
        self.assertEqual(table.call_count, 2)
        self.assertIsNone(engine.proc)

    def test_engine_interrupt_refuses_a_shared_engine_before_start(self):
        engine = fake_engine('orbstack')
        with self.assertRaisesRegex(ValueError, 'new private ctrs root'):
            runner.trial_w10(None, engine, 'warm', interrupt_service='engine')
        engine.ensure_up.assert_not_called()

    def test_reuse_failure_is_visible_and_next_call_reconnects_without_retry(self):
        server = _Server()
        worker = threading.Thread(target=server.serve_forever)
        worker.start()
        client = recovery_client.ProbeClient('127.0.0.1', server.server_port)
        try:
            first = client.query('health')
            second = client.query('health')
            self.assertTrue(first['ok'] and second['ok'])
            self.assertEqual(first['connections_opened'], 1)
            self.assertEqual(second['connect_attempts'], 0)
            self.assertTrue(second['reused_socket'])
            self.assertEqual(server.accepted, 1)
            failed = client.query('read')
            self.assertFalse(failed['ok'])
            self.assertIsNotNone(failed['error'])
            self.assertEqual(server.requests_seen, 3)
            self.assertEqual(server.accepted, 1)
            recovered = client.query('health')
            self.assertTrue(recovered['ok'])
            self.assertEqual(recovered['connections_opened'], 1)
            self.assertFalse(recovered['reused_socket'])
            self.assertEqual(server.requests_seen, 4)
            self.assertEqual(server.accepted, 2)
            self.assertEqual(recovered['client_version'], recovery_client.VERSION)
            server.health_body = {'ok': False}
            incorrect = client.query('health')
            self.assertFalse(incorrect['ok'])
            self.assertEqual(incorrect['status'], 200)
            self.assertEqual(incorrect['body'], {'ok': False})
        finally:
            client.close()
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)
        self.assertFalse(worker.is_alive())

    def test_host_address_failure_keeps_errno_and_does_not_retry(self):
        client = recovery_client.ProbeClient('127.0.0.1', 1)
        try:
            with patch('http.client.HTTPConnection.connect', side_effect=OSError(errno.EADDRNOTAVAIL, 'unavailable')) as connect:
                result = client.query('health')
            self.assertFalse(result['ok'])
            self.assertEqual(result['error_errno'], errno.EADDRNOTAVAIL)
            self.assertEqual(result['connect_attempts'], 1)
            self.assertEqual(result['connections_opened'], 0)
            self.assertEqual(connect.call_count, 1)
        finally:
            client.close()


if __name__ == '__main__':
    unittest.main()
