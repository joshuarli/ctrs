"""Offline W4 integration tests with a RESP server at the Redis boundary."""
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
import importlib.util
from pathlib import Path
import socketserver
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

spec = importlib.util.spec_from_file_location('w4_app', Path(__file__).parent / 'fixtures/w4/app.py')
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
                cmd, key = args[0], args[1]
                values = self.server.lists.setdefault(key, [])
                if cmd == b'RPUSH':
                    values.extend(args[2:])
                    response = b':%d\r\n' % len(values)
                elif cmd == b'LPOP':
                    item = values.pop(0) if values else None
                    response = b'$-1\r\n' if item is None else b'$%d\r\n' % len(item) + item + b'\r\n'
                elif cmd == b'LLEN':
                    response = b':%d\r\n' % len(values)
                elif cmd == b'LRANGE':
                    assert args[2:] == [b'0', b'-1']
                    response = b'*%d\r\n' % len(values) + b''.join(
                        b'$%d\r\n' % len(item) + item + b'\r\n' for item in values)
                else:
                    response = b'-ERR unsupported\r\n'
            self.wfile.write(response)


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

    def run_pipeline(self, workers):
        w4.submit(self.url)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(w4.worker, self.host, self.port) for _ in range(workers)]
            for future in futures:
                future.result()
        self.assertEqual(w4.verify(self.host, self.port), w4.JOBS)

    def test_pipeline_all_worker_counts(self):
        for workers in (1, 4, 16):
            with self.subTest(workers=workers):
                self.setUp()
                self.run_pipeline(workers)

    def test_missing_duplicate_and_corrupt_artifacts_fail(self):
        self.run_pipeline(4)
        results = self.redis.lists[w4.RESULTS.encode()]
        original = results[:]
        for mutation in ('missing', 'duplicate', 'corrupt'):
            with self.subTest(mutation=mutation):
                results[:] = original
                if mutation == 'missing':
                    results.pop()
                elif mutation == 'duplicate':
                    results.append(results[0])
                else:
                    results[0] = results[0].replace(b'ctrs-w4', b'bad--w4')
                with self.assertRaises(ValueError):
                    w4.verify(self.host, self.port)

    def test_pending_and_bad_ingest_fail(self):
        for body in (b'{"id":200}', b'{"id":true}', b'{"id":0,"extra":1}', b'invalid'):
            req = Request(self.url + '/jobs', data=body, method='POST')
            with self.assertRaises(HTTPError) as error:
                urlopen(req, timeout=10)
            self.assertEqual(error.exception.code, 400)
            error.exception.close()
        self.assertEqual(self.redis.lists, {})
        w4.submit(self.url)
        with self.assertRaisesRegex(ValueError, 'pending=200'):
            w4.verify(self.host, self.port)

    def test_pinned_artifact(self):
        self.assertEqual(w4.artifact(0), b'{"content":"ctrs-w4-v2-input-0000\\n","id":0,"sha256":"' +
                         b'639d166d6c9ad42d5b5eafb8eaf7e2f80c8484e7bd1090f0a4b1c4d2354bb42d' + b'"}')


if __name__ == '__main__':
    unittest.main()
