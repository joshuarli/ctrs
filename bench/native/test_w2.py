"""Fixed useful-work behavior through an actual local HTTP connection."""
import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import errno
from pathlib import Path
import select
import sys
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
        self.assertEqual(healthy['fixture_version'], 'w2-v3.2-fixed-rate')
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
                    patch.object(rate_load.sys, 'platform', 'linux'), \
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

    @unittest.skipUnless(sys.platform == 'darwin', 'requires Darwin kqueue timers')
    def test_darwin_timer_waits_until_deadline(self):
        deadline = time.monotonic() + 0.02
        rate_load._wait_until(deadline)
        self.assertGreaterEqual(time.monotonic(), deadline)

    @unittest.skipUnless(sys.platform == 'darwin', 'requires Darwin kqueue timers')
    def test_kqueue_timer_errors_and_empty_results_close_queue(self):
        class Queue:
            def __init__(self, events):
                self.events = events
                self.closed = False
                self.timeout = None

            def control(self, _, max_events, timeout):
                self.timeout = timeout
                self.assert_max_events = max_events
                return self.events

            def close(self):
                self.closed = True

        cases = (
            ([type('Event', (), {'flags': select.KQ_EV_ERROR, 'data': errno.EINVAL,
                                 'filter': select.KQ_FILTER_TIMER})()],
             OSError),
            ([], RuntimeError),
            ([type('Event', (), {'flags': 0, 'data': 1,
                                 'filter': select.KQ_FILTER_READ})()],
             RuntimeError),
            ([type('Event', (), {'flags': 0, 'data': 0,
                                 'filter': select.KQ_FILTER_TIMER})()],
             RuntimeError),
        )
        for events, error_type in cases:
            with self.subTest(error_type=error_type.__name__):
                queue = Queue(events)
                with patch.object(rate_load.select, 'kqueue', return_value=queue):
                    with self.assertRaises(error_type):
                        rate_load._wait_until_kqueue(time.monotonic() + 1)
                self.assertTrue(queue.closed)
                self.assertGreater(queue.timeout, 0)
                self.assertEqual(queue.assert_max_events, 1)

    @unittest.skipUnless(sys.platform == 'darwin', 'requires Darwin kqueue timers')
    def test_kqueue_timeout_is_bounded_and_elapsed_deadline_owns_no_queue(self):
        class Queue:
            def __init__(self):
                self.timeout = None
                self.closed = False

            def control(self, _, __, timeout):
                self.timeout = timeout
                return []

            def close(self):
                self.closed = True

        queue = Queue()
        with patch.object(rate_load.time, 'monotonic', return_value=10.0), \
                patch.object(rate_load.select, 'kqueue', return_value=queue):
            with self.assertRaises(RuntimeError):
                rate_load._wait_until_kqueue(10.0 + rate_load.MAX_PLANNED_SPAN_S + 100)
        self.assertEqual(queue.timeout, rate_load.MAX_PLANNED_SPAN_S + 1)
        self.assertTrue(queue.closed)
        with patch.object(rate_load.time, 'monotonic', return_value=10.0), \
                patch.object(rate_load.select, 'kqueue', side_effect=AssertionError('queue allocated')):
            rate_load._wait_until_kqueue(10.0)

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


class GuestPlacementTests(unittest.TestCase):
    def test_pinned_trial_rejects_image_drift_before_compose_or_sampling(self):
        import runner
        from test_safety import FixtureContext, fake_engine

        with tempfile.TemporaryDirectory() as directory:
            engine = fake_engine()
            with patch.object(runner, "prepare_pinned_stack", side_effect=ValueError("image differs from pin")), \
                    patch.object(runner, "start_sampler") as sampler, patch.object(runner, "compose_down") as down:
                rec = runner.trial_w2(FixtureContext(directory), engine, "warm", 2, 20, .5, 7,
                                      2, pinned_stack=True)
        self.assertFalse(rec["correctness"]["ok"])
        self.assertEqual(rec["validation_errors"], ["ValueError: image differs from pin"])
        engine.compose.assert_not_called()
        sampler.assert_not_called()
        down.assert_not_called()

    def test_guest_uses_verified_peer_for_each_workload_mode(self):
        import hashlib
        import runner
        from test_safety import FixtureContext, completed, fake_engine

        image = "sha256:" + "a" * 64
        for operations, rate, mode in ((None, None, "saturation"), (2, None, "fixed-work"),
                                       (2, 100, "fixed-rate"), (2, None, "corrupt"),
                                       (2, None, "source-mismatch")):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                engine = fake_engine()
                engine.measurement_identity = {"required_processes": []}
                pinned = mode == "fixed-rate"
                engine.compose.side_effect = lambda _, args, **kw: completed(f"{args[-1]}-id") if "ps" in args else completed()
                args_seen = {}
                events = []
                files = {
                    "load.json.writes.jsonl": json.dumps({"name": "write-1", "payload": "value"}) + "\n",
                    "load.json.errors.jsonl": "", "load.stdout": "", "load.stderr": "",
                }
                summary = dict(fixture_version=rate_load.FIXTURE_VERSION if rate else "w2-v2-fixed-work",
                               mode=mode, requests_ok=2, duration_s=1, rps=2, requests=2,
                               errors=0, writes_ok=1, reads_ok=1, latency_ms={"p50": 1, "p95": 2, "p99": 3})
                if rate:
                    summary.update(latency_scope="scheduled", service_latency_ms={}, request_rate=rate,
                                   planned_span_s=.01, schedule_lag_budget_ms=10, planned_requests=2,
                                   offered_requests=2, delivered_requests=2, late_requests=0,
                                   offered_rate_valid=True, slots=[])
                files["load.json"] = json.dumps(summary)

                def command(args, **kwargs):
                    if args[0] == "create":
                        self.assertEqual(args[args.index("--network") + 1],
                                         runner.project_name("test-run-000001", engine.name, "W2") + "_appnet")
                        self.assertIn(image, args)
                    elif args[0] == "inspect":
                        return completed(json.dumps([{"Id": args[1], "Image": image,
                                                       "Config": {"Image": image, "Labels": {"dev.ctrs.campaign.run": "test-run-000001"}}}]))
                    elif args[:2] == ["exec", "api-id"]:
                        events.append("api-cpu")
                        return completed("usage_usec 42\n")
                    elif args[:2] == ["exec", "db-id"]:
                        rows = [[f"item-{i}", hashlib.md5(str(i).encode()).hexdigest()] for i in range(1, 501)]
                        rows.append(["write-1", "corrupt" if mode == "corrupt" else "value"])
                        return completed("\n".join(json.dumps(row) for row in rows))
                    elif args[0] == "exec":
                        script = args[4]
                        if "write_bytes" in script:
                            files["source"] = args[-1]
                        elif "hashlib" in script:
                            return completed("wrong" if mode == "source-mismatch" else hashlib.sha256(files["source"].encode()).hexdigest())
                        elif "ProxyHandler" in script:
                            self.assertTrue(args[5].startswith("http://api:8000/"))
                            return completed(json.dumps([200, {"ok": True, "items": 501}]))
                        elif "subprocess.run" in script:
                            args_seen.update(dict(zip(args[7::2], args[8::2], strict=True)))
                            events.append("guest-load")
                        elif "read_bytes" in script:
                            events.append("copy")
                            return completed(files[Path(args[-1]).name])
                    elif args[:2] == ["rm", "-f"]:
                        events.append("remove-peer")
                    return completed()

                @contextlib.contextmanager
                def phase(engine, record, name):
                    yield
                    record["resources"].setdefault("phases", {})[name] = {"cpu_seconds": 1}

                engine.sh.side_effect = command
                with patch.object(runner, "start_sampler", return_value=(None, None)), \
                        patch.object(runner, "resource_phase", phase), patch.object(runner, "compose_down") as down, \
                        patch.object(runner, "prepare_pinned_stack", return_value=(
                            {"api": image}, {"portfolio_sha256": "portfolio", "seed_sha256": "seed"})), \
                        patch("diagnostics.resource_pilot.warmup_api", return_value={"app.py": "app"}) as warmup, \
                        patch.object(runner.subprocess, "run", side_effect=AssertionError("host load")):
                    rec = runner.trial_w2(FixtureContext(directory), engine, "warm", 2, 20, .5, 7,
                                           operations, request_rate=rate, client_location="guest", pinned_stack=pinned)
                self.assertEqual(down.call_count, 2)
                if pinned:
                    warmup.assert_called_once_with(engine, image)
                    first = engine.compose.call_args_list[0]
                    self.assertEqual(first.args[1], ["up", "-d", "--no-build", "--pull", "never"])
                    self.assertEqual(first.kwargs["override"].name, "pinned-compose.json")
                    self.assertEqual(rec["paired_inputs"]["api_files_sha256"], {"app.py": "app"})
                    self.assertEqual(rec["paired_inputs"]["load_client_sha256"], runner.sha256_file(runner.RATE_LOAD_PY))
                self.assertIn("remove-peer", events)
                self.assertEqual(rec["correctness"]["ok"], mode not in ("corrupt", "source-mismatch"), rec)
                if mode == "source-mismatch":
                    self.assertNotIn("guest-load", events)
                    self.assertIn("source differs", rec["validation_errors"][0])
                else:
                    self.assertEqual(args_seen["--url"], "http://api:8000")
                    self.assertEqual(args_seen.get("--operations"), str(operations) if operations else None)
                    self.assertEqual(args_seen.get("--request-rate"), str(rate) if rate else None)
                    self.assertEqual(events[:4], ["api-cpu", "guest-load", "api-cpu", "copy"])
                    source = runner.RATE_LOAD_PY if rate else runner.LOAD_PY
                    self.assertEqual(files["source"], source.read_text())
                    self.assertEqual(rec["correctness"]["checks"]["exact_persisted_items"], mode != "corrupt")


class WorkerFailureTests(unittest.TestCase):
    def test_fatal_worker_error_cannot_emit_successful_partial_summary(self):
        with patch.object(load, 'worker', side_effect=RuntimeError('worker failed')), \
                patch.object(load.sys, 'argv', ['load.py', '--url', 'http://unused',
                                                '--concurrency', '1']):
            with self.assertRaisesRegex(RuntimeError, 'worker failed'):
                load.main()
