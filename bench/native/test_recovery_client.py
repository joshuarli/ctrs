import http.server
import errno
import json
import socket
import socketserver
import threading
import unittest
from unittest.mock import patch

import recovery_client


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
