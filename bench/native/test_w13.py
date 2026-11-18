import hashlib
import socket
import threading
import time
import unittest
from fixtures.w13 import transfer_tool as tool
from transfer import tool_limited, transfer_result, record_attempt


class TransferTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)

    def expected(self, payload):
        import os
        path = os.path.join(self.scratch.name, 'expected')
        with open(path, 'wb') as f:
            f.write(payload)
        return path

    def run_receive(self, payload, declared, digest, delay=0, expected=None):
        expected_path = self.expected(expected if expected is not None else payload)
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
            result = tool.receive(right, '0', declared, digest, expected_path)
        thread.join()
        return result

    def test_verified_and_partial(self):
        payload = b'payload'; digest = hashlib.sha256(payload).hexdigest()
        self.assertIsNone(self.run_receive(payload, len(payload), digest)['error'])
        partial = self.run_receive(payload[:-1], len(payload), digest)
        self.assertIsNotNone(partial['error']); self.assertEqual(partial['bytes'], len(payload)-1)
        self.assertIsNotNone(self.run_receive(b'PAYLOAD', len(payload), digest, expected=payload)['error'])

    def test_multi_chunk_exactness(self):
        payload = bytes(range(256)) * (10 * 1024 + 17)
        digest = hashlib.sha256(payload).hexdigest()
        result = self.run_receive(payload, len(payload), digest)
        self.assertIsNone(result['error']); self.assertEqual(result['sha256'], digest)
        corrupt = payload[:-1] + bytes([payload[-1] ^ 1])
        result = self.run_receive(corrupt, len(payload), digest, expected=payload)
        self.assertEqual(result['error'], 'ValueError: byte count or content mismatch')
        self.assertIsNone(result['sha256'])

    def test_short_transfer_survives_trial_record(self):
        payload = b'payload'
        digest = hashlib.sha256(payload).hexdigest()
        partial = self.run_receive(payload[:-1], len(payload), digest)
        attempt = transfer_result({'seconds': partial['seconds'], 'streams': [partial]},
                                  [{'id': '0'}], 'download', 1, len(payload), digest)
        rec = {'metrics': {'attempts': []}, 'correctness': {'ok': True}, 'validation_errors': []}
        record_attempt(rec, attempt)
        self.assertFalse(rec['correctness']['ok'])
        self.assertEqual(rec['metrics']['attempts'][0]['partial_bytes'], len(payload) - 1)
        self.assertEqual(rec['metrics']['attempts'][0]['receivers'][0]['bytes'], len(payload) - 1)
        self.assertGreater(rec['metrics']['attempts'][0]['seconds'], 0)
        self.assertTrue(rec['validation_errors'])
        self.assertIsNone(attempt['goodput_bytes_per_second'])

    def test_ack_timeout_keeps_receiver_count(self):
        payload = b'payload'
        digest = hashlib.sha256(payload).hexdigest()
        complete = self.run_receive(payload, len(payload), digest)
        client = {'id': '0', 'bytes': None, 'seconds': 1.5, 'error': 'TimeoutError: ack'}
        attempt = transfer_result({'seconds': 1.5, 'streams': [client]}, [complete],
                                  'upload', 1, len(payload), digest)
        rec = {'metrics': {'attempts': []}, 'correctness': {'ok': True}, 'validation_errors': []}
        record_attempt(rec, attempt)
        self.assertFalse(rec['correctness']['ok'])
        self.assertEqual(attempt['verified_bytes'], len(payload))
        self.assertEqual(attempt['partial_bytes'], len(payload))
        self.assertIn('TimeoutError: ack', rec['validation_errors'])
        self.assertIsNone(attempt['goodput_bytes_per_second'])

    def test_bad_header(self):
        left, right = socket.socketpair()
        with left, right:
            left.sendall(b'{"id":"wrong","bytes":0,"sha256":"x"}\n')
            self.assertEqual(tool.receive(right, '0', 0, 'x', self.expected(b''))['error'], 'ValueError: header mismatch')

    def test_stall(self):
        payload = b'x'; digest = hashlib.sha256(payload).hexdigest()
        result = self.run_receive(payload, 1, digest, delay=1.05)
        self.assertEqual(result['stall_count'], 1)
        self.assertGreaterEqual(result['longest_gap_seconds'], 1)

    def test_capacity_limit(self):
        self.assertFalse(tool_limited(50, 100, 200))
        self.assertTrue(tool_limited(51, 100, 200))
