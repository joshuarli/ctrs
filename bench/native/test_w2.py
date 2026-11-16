"""Fixed useful-work behavior through an actual local HTTP connection."""
import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('w2_load', Path(__file__).parent / 'fixtures/w2/load.py')
load = importlib.util.module_from_spec(spec)
spec.loader.exec_module(load)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        with self.server.lock:
            self.server.writes.append(body)
        self.reply(201, {**body, 'id': 501})

    def do_GET(self):
        self.reply(200, {'items': [{'id': i, 'name': f'item-{i}'} for i in range(1, 26)]})

    def reply(self, status, data):
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_):
        pass


class FixedWorkTests(unittest.TestCase):
    def test_identical_fixed_work_counts_and_write_payloads(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.writes = []
        server.lock = threading.Lock()
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            results = []
            for repetition in range(2):
                server.writes.clear()
                with tempfile.TemporaryDirectory() as directory:
                    output = Path(directory) / 'load.json'
                    with patch.object(load.sys, 'argv', ['load.py', '--url',
                            f'http://127.0.0.1:{server.server_port}', '--operations', '37',
                            '--concurrency', '4', '--write-ratio', '.7', '--seed', '7',
                            '--out', str(output)]), contextlib.redirect_stdout(io.StringIO()):
                        with self.assertRaises(SystemExit) as result:
                            load.main()
                    self.assertEqual(result.exception.code, 0)
                    summary = json.loads(output.read_text())
                    writes = [json.loads(line) for line in Path(str(output) + '.writes.jsonl').read_text().splitlines()]
                    self.assertEqual(summary['requests_ok'], 37)
                    self.assertEqual(summary['requests'], 37)
                    self.assertEqual(summary['errors'], 0)
                    self.assertEqual(summary['mode'], 'fixed-work')
                    self.assertEqual(len(writes), summary['writes_ok'])
                    self.assertEqual(summary['reads_ok'] + len(writes), 37)
                    self.assertEqual(len({row['name'] for row in writes}), len(writes))
                    self.assertEqual(sorted(server.writes, key=lambda row: row['name']), writes)
                    results.append(writes)
            self.assertEqual(*results)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class PersistedStateTests(unittest.TestCase):
    def test_equal_count_corruption_duplicate_or_missing_seed_fails(self):
        import hashlib
        import runner
        rows = [[f'item-{i}', hashlib.md5(str(i).encode()).hexdigest()] for i in range(1, 501)]
        writes = [{'name': 'load-0-1', 'payload': 'value'}]
        valid = rows + [['load-0-1', 'value']]
        self.assertTrue(runner.exact_w2_items(valid, writes))
        for corrupt in (rows + [['load-0-1', 'corrupt']],
                        valid[:-1] + [valid[0]], valid[1:], valid + [valid[-1]]):
            self.assertFalse(runner.exact_w2_items(corrupt, writes))


class WorkerFailureTests(unittest.TestCase):
    def test_fatal_worker_error_cannot_emit_successful_partial_summary(self):
        with patch.object(load, 'worker', side_effect=RuntimeError('worker failed')), \
                patch.object(load.sys, 'argv', ['load.py', '--url', 'http://unused',
                                                '--concurrency', '1']):
            with self.assertRaisesRegex(RuntimeError, 'worker failed'):
                load.main()
