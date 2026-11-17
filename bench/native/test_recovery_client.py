import http.server
import errno
import hashlib
import json
import socket
import socketserver
import threading
import unittest
from unittest.mock import patch

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
                engine = fake_engine()
                engine.compose.side_effect = lambda _, args, **kw: completed('owned-db\n' if args[0] == 'ps' else '')

                def effects(args, **kwargs):
                    if args == ['kill', 'owned-db']:
                        healthy.clear()
                    elif args == ['start', 'owned-db']:
                        healthy.set()
                    elif args[:2] == ['exec', 'owned-db']:
                        return completed(json.dumps(rows))
                    else:
                        raise AssertionError(args)
                    return completed()

                engine.sh.side_effect = effects
                with patch.object(runner, 'free_port', return_value=server.server_port), \
                        patch.object(runner, 'compose_down'), \
                        patch.object(runner, 'wait_health', return_value=(0, {})), \
                        patch.object(runner, 'start_sampler', return_value=(None, None)), \
                        patch.object(runner, 'resource_phase', return_value=nullcontext()):
                    rec = runner.trial_w10(FixtureContext(tmp), engine, 'warm', duration=1.4, concurrency=2,
                                           write_ratio=.5, kill_at=.4, down_for=.2, interrupt_service='db')
                self.assertTrue(rec['correctness']['ok'], rec)
                self.assertGreater(rec['metrics']['expected_outage_errors'], 0)
                self.assertEqual(rec['metrics']['unexpected_errors'], 0)
                self.assertEqual(rec['metrics']['acknowledged_writes'], len(rows) - 500)
                self.assertGreater(rec['metrics']['recovered_p99_ms'], 0)
                attempts = [json.loads(line) for line in
                            (Path(tmp) / 'orbstack/W10/attempts.jsonl').read_text().splitlines()]
                self.assertTrue(any(attempt['reused_socket'] for attempt in attempts))
            finally:
                server.shutdown()
                thread.join(timeout=2)

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
