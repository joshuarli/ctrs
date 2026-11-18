import socket
import threading
import unittest
from fixtures.w14 import lifecycle_tool as tool


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.server = tool.Server(('127.0.0.1', 0))
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_codec_and_verification(self):
        a, b = socket.socketpair()
        with a, b:
            tool.send(a, tool.response('id', 2))
            tool.verify(tool.receive(b), 'id', 2)
            with self.assertRaises(ValueError):
                tool.verify(tool.response('id', 1), 'id', 2)
            a.sendall(b'broken\n')
            with self.assertRaises(ValueError):
                tool.receive(b)

    def test_statistics_and_errors(self):
        self.assertEqual(tool.percentile([0, 10], 95), 9.5)
        self.assertIsNone(tool.percentile([], 99))
        self.assertAlmostEqual(tool.lateness(1.25, 1, 1, 0.1), 50)
        self.assertEqual(tool.lateness(1, 1, 0, 0.1), 0)
        self.assertEqual(tool.classify(ConnectionRefusedError()), 'refused')
        self.assertEqual(tool.classify(ConnectionResetError()), 'reset')
        self.assertEqual(tool.classify(TimeoutError()), 'timeout')
        self.assertEqual(tool.classify(ValueError()), 'wrong_data')

    def test_modes_on_loopback(self):
        for mode in ('fresh', 'persistent', 'streaming', 'cancel', 'idle-resume'):
            with self.subTest(mode=mode):
                result = tool.run('127.0.0.1', self.port, mode, clients=3, operations=3,
                                  chunks=4, interval=0.005, idle_seconds=0.01, timeout=2)
                self.assertTrue(result['ok'], result)
                self.assertEqual(result['server_open_connections'], 0)
                self.assertEqual(result['successes'], result['expected_successes'])
                if mode == 'streaming':
                    self.assertEqual(result['chunks_received'], 12)
                if mode == 'idle-resume':
                    self.assertEqual([r['resume'] for r in result['clients']], ['ok'] * 3)
                if mode == 'cancel':
                    self.assertIsNotNone(result['post_cancel_latency_ms'])

    def replace_server(self):
        old = self.server
        old.shutdown()
        old.server_close()
        self.thread.join()
        self.server = tool.Server(('127.0.0.1', self.port))
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def test_reconnect_requires_new_instance(self):
        calls = []
        def restart():
            calls.append('restart')
            threading.Timer(0.2, self.replace_server).start()
        result = tool.run('127.0.0.1', self.port, 'reconnect', clients=3, timeout=2, restart=restart)
        self.assertEqual(calls, ['restart'])
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['successes'], 3)
        self.assertGreaterEqual(result['reconnect_p99_ms'], 200)
        self.assertGreater(result['restart_window_errors'].get('previous_instance', 0), 0)

    def test_restart_failure_is_preserved(self):
        def restart():
            raise RuntimeError('failure')
        original = tool.RECONNECT_DEADLINE_SECONDS
        tool.RECONNECT_DEADLINE_SECONDS = 0.3
        self.addCleanup(setattr, tool, 'RECONNECT_DEADLINE_SECONDS', original)
        result = tool.run('127.0.0.1', self.port, 'reconnect', clients=2, timeout=2, restart=restart)
        self.assertFalse(result['ok'])
        self.assertEqual(result['errors']['reconnect_deadline'], 2)
        self.assertEqual(result['errors']['restart_failed'], 2)
