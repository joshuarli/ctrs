"""Offline W4 integration tests with a RESP server at the Redis boundary."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import gzip
from http.server import ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import socketserver
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

APP = Path(__file__).parent / 'fixtures/w4/app.py'
spec = importlib.util.spec_from_file_location('w4_app', APP)
w4 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w4)


class FakeRedis(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 128

    def __init__(self):
        self.lists = {}
        self.lock = threading.Lock()
        super().__init__(('127.0.0.1', 0), RedisHandler)


class RedisHandler(socketserver.StreamRequestHandler):
    def handle(self):
        while True:
            line = self.rfile.readline()
            if not line:
                return
            assert line.startswith(b'*')
            args = []
            for _ in range(int(line[1:])):
                length = int(self.rfile.readline()[1:])
                args.append(self.rfile.read(length))
                assert self.rfile.read(2) == b'\r\n'
            with self.server.lock:
                cmd = args[0]
                if cmd == b'PING':
                    response = b'+PONG\r\n'
                else:
                    values = self.server.lists.setdefault(args[1], [])
                    if cmd == b'RPUSH':
                        values.extend(args[2:])
                        response = b':%d\r\n' % len(values)
                    elif cmd == b'LPOP':
                        item = values.pop(0) if values else None
                        response = b'$-1\r\n' if item is None else b'$%d\r\n' % len(item) + item + b'\r\n'
                    elif cmd == b'LLEN':
                        response = b':%d\r\n' % len(values)
                    else:
                        response = b'-ERR unsupported\r\n'
            self.wfile.write(response)


def expected_events(job):
    routes = ('/api/orders', '/api/products', '/api/users', '/health')
    statuses = (200, 201, 400, 404, 500, 503)
    tenants = ('north', 'south', 'east', 'west')
    result = []
    for index in range(64):
        n = job * 64 + index
        result.append({
            'timestamp': (datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=n)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'status': statuses[(n + job) % 6],
            'route': routes[(n // 3 + job) % 4],
            'latency_ms': 1 + (n * 37 + job * 11) % 2000,
            'tenant': tenants[(n // 7 + job) % 4],
        })
    return result


class W4Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.redis = FakeRedis()
        cls.redis_thread = threading.Thread(target=cls.redis.serve_forever, daemon=True)
        cls.redis_thread.start()
        cls.host, cls.port = cls.redis.server_address
        cls.http = ThreadingHTTPServer(('127.0.0.1', 0), w4.handler(cls.host, cls.port))
        cls.http_thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.http_thread.start()
        cls.url = 'http://127.0.0.1:%d' % cls.http.server_port

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.http_thread.join()
        cls.redis.shutdown()
        cls.redis.server_close()
        cls.redis_thread.join()

    def setUp(self):
        with self.redis.lock:
            self.redis.lists.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)

    def cli(self, command):
        return subprocess.run([sys.executable, str(APP), command, '--redis-host', self.host,
                               '--redis-port', str(self.port), '--output-dir', str(self.output)],
                              capture_output=True, text=True, timeout=120)

    def run_pipeline(self, workers):
        w4.submit(self.url)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(lambda _: self.cli('worker'), range(workers)))
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
        result = self.cli('verify')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'verified 200')

    def assert_artifacts(self):
        names = set()
        for job in range(200):
            events = expected_events(job)
            gz_name = f'job-{job:04d}.ndjson.gz'
            summary_name = f'job-{job:04d}.summary.json'
            names.update((gz_name, summary_name))
            compressed = (self.output / gz_name).read_bytes()
            self.assertEqual(compressed[4:8], b'\0\0\0\0')
            lines = gzip.decompress(compressed).splitlines()
            self.assertEqual([json.loads(line) for line in lines], events)
            summary = json.loads((self.output / summary_name).read_bytes())
            self.assertEqual(summary, {
                'id': job,
                'event_count': 64,
                'status_counts': dict(Counter(str(event['status']) for event in events)),
                'route_counts': dict(Counter(event['route'] for event in events)),
                'tenant_counts': dict(Counter(event['tenant'] for event in events)),
                'latency_ms_total': sum(event['latency_ms'] for event in events),
                'latency_ms_max': max(event['latency_ms'] for event in events),
            })
        self.assertEqual({p.name for p in self.output.iterdir()}, names)

    def test_pipeline_all_worker_counts(self):
        for workers in (1, 4, 16):
            with self.subTest(workers=workers), tempfile.TemporaryDirectory() as directory:
                with self.redis.lock:
                    self.redis.lists.clear()
                self.output = Path(directory)
                self.run_pipeline(workers)
                self.assert_artifacts()

    def test_missing_duplicate_corrupt_and_extra_fail(self):
        self.run_pipeline(4)
        path = self.output / 'job-0000.ndjson.gz'
        original = path.read_bytes()
        path.unlink()
        self.assertNotEqual(self.cli('verify').returncode, 0)
        path.write_bytes(original)
        path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        self.assertNotEqual(self.cli('verify').returncode, 0)
        path.write_bytes(original)
        extra = self.output / 'extra.json'
        extra.write_text('{}')
        self.assertNotEqual(self.cli('verify').returncode, 0)
        extra.unlink()
        redis = w4.Redis(self.host, self.port)
        try:
            redis.command('RPUSH', w4.QUEUE, w4.encode(w4.batch(0)))
        finally:
            redis.close()
        duplicate = self.cli('worker')
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn('File exists', duplicate.stderr)
        self.assertEqual(path.read_bytes(), original)

    def test_worker_uses_submitted_payload_and_rejects_invalid_queue_data(self):
        value = w4.batch(0)
        value['events'][0]['latency_ms'] = 1999
        req = Request(self.url + '/jobs', data=w4.encode(value), method='POST')
        with urlopen(req, timeout=10) as response:
            self.assertEqual(response.status, 202)
        result = self.cli('worker')
        self.assertEqual(result.returncode, 0, result.stderr)
        events = [json.loads(line) for line in gzip.decompress(
            (self.output / 'job-0000.ndjson.gz').read_bytes()).splitlines()]
        self.assertEqual(events, value['events'])
        summary = json.loads((self.output / 'job-0000.summary.json').read_text())
        self.assertEqual(summary['latency_ms_total'], sum(e['latency_ms'] for e in events))
        redis = w4.Redis(self.host, self.port)
        try:
            redis.command('RPUSH', w4.QUEUE, b'{"id":1,"events":[]}')
        finally:
            redis.close()
        result = self.cli('worker')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('expected 64 events', result.stderr)

    def test_pending_bad_ingest_and_readiness(self):
        with urlopen(self.url + '/health', timeout=10) as response:
            self.assertEqual(response.status, 200)
        invalid = w4.batch(0)
        invalid['events'][0]['latency_ms'] = True
        for body in (b'{"id":200}', b'{"id":true}', b'invalid', w4.encode(invalid)):
            req = Request(self.url + '/jobs', data=body, method='POST')
            with self.assertRaises(HTTPError) as error:
                urlopen(req, timeout=10)
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
        self.assertEqual(self.redis.lists, {})
        w4.submit(self.url)
        result = self.cli('verify')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('pending=200', result.stderr)
        unavailable = ThreadingHTTPServer(('127.0.0.1', 0), w4.handler(self.host, 0))
        thread = threading.Thread(target=unavailable.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(HTTPError) as error:
                urlopen('http://127.0.0.1:%d/health' % unavailable.server_port, timeout=10)
            self.assertEqual(error.exception.code, 503)
            error.exception.close()
        finally:
            unavailable.shutdown()
            unavailable.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()


class CleanupOwnershipTests(unittest.TestCase):
    def test_setup_failure_preserves_network_with_other_owner(self):
        import runner
        from test_safety import FixtureContext, completed, fake_engine
        engine = fake_engine()
        def command(args, **kwargs):
            if args[:2] == ['image', 'inspect']:
                raise RuntimeError('fixture image unavailable')
            if args[:2] == ['network', 'inspect']:
                return completed(json.dumps([{'Labels': {'dev.ctrs.campaign.run': 'other-owner'}}]))
            raise AssertionError(args)
        engine.sh.side_effect = command
        with tempfile.TemporaryDirectory() as directory:
            record = runner.trial_w4(FixtureContext(directory), engine, 'warm', workers=(1,))
        self.assertFalse(record['correctness']['ok'])
        self.assertTrue(any('ownership mismatch' in error for error in record['validation_errors']))
        self.assertFalse(any(call.args[0][:2] == ['network', 'rm'] for call in engine.sh.call_args_list))
