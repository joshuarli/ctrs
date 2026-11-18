import hashlib
import socket
import threading
import time
import unittest
from fixtures.w13 import transfer_tool as tool
from transfer import tool_limited


class TransferTests(unittest.TestCase):
    def run_receive(self, payload, declared, digest, delay=0):
        left, right = socket.socketpair()
        def writer():
            with left:
                left.sendall((__import__('json').dumps({'id': '0', 'bytes': declared, 'sha256': digest}) + '\n').encode())
                if delay:
                    time.sleep(delay)
                left.sendall(payload)
        thread = threading.Thread(target=writer)
        thread.start()
        with right:
            result = tool.receive(right, '0', declared, digest)
        thread.join()
        return result

    def test_verified_and_partial(self):
        payload = b'payload'; digest = hashlib.sha256(payload).hexdigest()
        self.assertIsNone(self.run_receive(payload, len(payload), digest)['error'])
        partial = self.run_receive(payload[:-1], len(payload), digest)
        self.assertIsNotNone(partial['error']); self.assertEqual(partial['bytes'], len(payload)-1)
        self.assertIsNotNone(self.run_receive(b'PAYLOAD', len(payload), digest)['error'])

    def test_bad_header(self):
        left, right = socket.socketpair()
        with left, right:
            left.sendall(b'{"id":"wrong","bytes":0,"sha256":"x"}\n')
            self.assertEqual(tool.receive(right, '0', 0, 'x')['error'], 'header mismatch')

    def test_stall(self):
        payload = b'x'; digest = hashlib.sha256(payload).hexdigest()
        result = self.run_receive(payload, 1, digest, delay=1.05)
        self.assertEqual(result['stall_count'], 1)
        self.assertGreaterEqual(result['longest_gap_seconds'], 1)

    def test_capacity_limit(self):
        self.assertFalse(tool_limited(50, 100, 200))
        self.assertTrue(tool_limited(51, 100, 200))
