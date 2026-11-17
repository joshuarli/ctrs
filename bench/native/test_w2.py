"""Fixed useful-work behavior through an actual local HTTP connection."""
import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import time
import threading
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('w2_load', Path(__file__).parent / 'fixtures/w2/load.py')
load = importlib.util.module_from_spec(spec)
spec.loader.exec_module(load)
rate_spec = importlib.util.spec_from_file_location('w2_rate_load', Path(__file__).parent / 'fixtures/w2/v3.py')
rate_load = importlib.util.module_from_spec(rate_spec)
rate_spec.loader.exec_module(rate_load)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        with self.server.lock:
            self.server.writes.append(body)
        self.reply(201, {**body, 'id': 501})

    def do_GET(self):
        self.reply(200, {'items': [{'id': i, 'name': f'item-{i}'} for i in range(1, 26)]})

    def reply(self, status, data):
        time.sleep(getattr(self.server, "delay", 0))
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


class FixedRateTests(unittest.TestCase):
    def run_load(self, delay):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.writes, server.lock, server.delay = [], threading.Lock(), delay
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / 'load.json'
                with patch.object(rate_load.sys, 'argv', ['v3.py', '--url',
                        f'http://127.0.0.1:{server.server_port}', '--operations', '8',
                        '--concurrency', '2', '--request-rate', '10', '--seed', '7',
                        '--write-ratio', '.7', '--out', str(output)]), contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as result:
                        rate_load.main()
                summary = json.loads(output.read_text())
                writes = [json.loads(line) for line in Path(str(output) + '.writes.jsonl').read_text().splitlines()]
                self.assertEqual(sorted(server.writes, key=lambda row: row['name']), writes)
                self.assertEqual(len(writes), summary['writes_ok'])
                return result.exception.code, summary, writes
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_paced_exact_work_and_late_backlog(self):
        code, healthy, writes = self.run_load(0)
        self.assertEqual(code, 0 if healthy['offered_rate_valid'] else 1)
        self.assertEqual(healthy['fixture_version'], 'w2-v3.1-fixed-rate')
        self.assertEqual(healthy['mode'], 'fixed-rate')
        self.assertEqual(healthy['errors'], 0)
        self.assertEqual((healthy['planned_requests'], healthy['offered_requests'],
                          healthy['delivered_requests']), (8, 8, 8))
        self.assertEqual([row['slot'] for row in healthy['slots']], list(range(8)))
        code, delayed, delayed_writes = self.run_load(.3)
        self.assertEqual(code, 1)
        self.assertFalse(delayed['offered_rate_valid'])
        self.assertGreater(delayed['late_requests'], 0)
        self.assertEqual((delayed['planned_requests'], delayed['offered_requests'],
                          delayed['delivered_requests']), (8, 8, 8))
        self.assertEqual(writes, delayed_writes)
        self.assertEqual([row['slot'] for row in delayed['slots']], list(range(8)))
        self.assertGreater(delayed['slots'][-1]['start_lag_ms'], 100)
        self.assertGreater(delayed['slots'][-1]['scheduled_latency_ms'], 400)
        self.assertEqual(delayed['latency_scope'], 'successful_requests_from_scheduled_slot')
        self.assertGreater(delayed['latency_ms']['p99'], 400)
        self.assertGreater(delayed['latency_ms']['p99'], delayed['service_latency_ms']['p99'])

    def scripted_load(self, delays, request_rate=10, sleep_overshoot=0.0):
        clock = [0.0]
        response_delays = iter(delays)
        connection = Mock()
        response = Mock(status=200)
        payload = json.dumps({'items': [{'id': i, 'name': f'item-{i}'} for i in range(1, 26)]}).encode()
        def read():
            clock[0] += next(response_delays)
            return payload
        response.read.side_effect = read
        connection.getresponse.return_value = response
        def sleep(seconds):
            self.assertGreater(seconds, 0)
            clock[0] += seconds + sleep_overshoot
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'load.json'
            argv = ['v3.py', '--url', 'http://unused', '--operations', str(len(delays)),
                    '--concurrency', '1', '--request-rate', str(request_rate), '--write-ratio', '0', '--out', str(output)]
            with patch.object(rate_load.sys, 'argv', argv), \
                    patch.object(rate_load.time, 'monotonic', side_effect=lambda: clock[0]), \
                    patch.object(rate_load.time, 'sleep', side_effect=sleep), \
                    patch.object(rate_load.http.client, 'HTTPConnection', return_value=connection), \
                    contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    rate_load.main()
            summary = json.loads(output.read_text())
        return result.exception.code, summary

    def test_healthy_delivery_with_controlled_clock(self):
        code, summary = self.scripted_load([.004] * 3)
        self.assertEqual(code, 0)
        self.assertTrue(summary['offered_rate_valid'])
        self.assertEqual(summary['late_requests'], 0)
        self.assertEqual([row['slot'] for row in summary['slots']], [0, 1, 2])
        self.assertEqual(summary['delivered_requests'], 3)
        self.assertAlmostEqual(summary['latency_ms']['p99'], 4.0)

    def test_one_late_response_does_not_rebase_future_slots(self):
        code, summary = self.scripted_load([.020, .001, .001, .001, .001], request_rate=125,
                                           sleep_overshoot=.001)
        self.assertEqual(code, 1)
        self.assertFalse(summary['offered_rate_valid'])
        self.assertEqual(summary['delivered_requests'], 5)
        self.assertEqual(summary['late_requests'], 1)
        self.assertGreater(summary['slots'][1]['start_lag_ms'], 10)
        self.assertLess(summary['slots'][-1]['start_lag_ms'], 2)

    def test_invalid_options_rejected_before_engine_access(self):
        import runner
        for rate in ('nan', 'inf', '-1', '0', '1e-320'):
            argv = ['runner.py', 'run', '--case', 'W2', '--engine', 'ctrs',
                    '--operations', '2', '--request-rate', rate]
            with self.subTest(rate=rate), patch.object(runner.sys, 'argv', argv), \
                    patch.object(runner, 'find_docker', side_effect=AssertionError('engine access')), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    runner.main()
                self.assertEqual(result.exception.code, 2)
        for extra in (['--request-rate', '1'],
                      ['--operations', '2', '--request-rate', '1', '--case', 'W1'],
                      ['--operations', '2', '--request-rate']):
            argv = ['runner.py', 'run', '--case', 'W2', '--engine', 'ctrs'] + extra
            with self.subTest(extra=extra), patch.object(runner.sys, 'argv', argv), \
                    patch.object(runner, 'find_docker', side_effect=AssertionError('engine access')), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    runner.main()
                self.assertEqual(result.exception.code, 2)
        for rate in ('nan', 'inf', '0', '1e-320'):
            with self.subTest(loader_rate=rate), patch.object(rate_load.sys, 'argv',
                    ['load.py', '--url', 'http://unused', '--operations', '2', '--request-rate', rate]), \
                    patch.object(rate_load.http.client, 'HTTPConnection', side_effect=AssertionError('connection')), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    rate_load.main()
                self.assertEqual(result.exception.code, 2)


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
