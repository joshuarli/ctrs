import hashlib
import importlib.util
import json
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock

import runner
from diagnostics import w8_load_guest, w8_under_pull as under


class API(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args):
        pass
    def do_GET(self):
        self.respond({'items': [{'id': i, 'name': f'item-{i}'} for i in range(1, 26)]})
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.respond({'id': 1, 'name': body['name']})
    def respond(self, body):
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class UnderPull(unittest.TestCase):
    def test_real_worker_callbacks_cover_only_completions_in_interval(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), API)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                spec = importlib.util.spec_from_file_location('test_w2', runner.LOAD_PY)
                worker = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(worker)
                counts = dict(reads=0, writes=0, errors=0)
                writes, errors = [], []
                with (directory / 'events').open('w', buffering=1) as stream:
                    recorder = w8_load_guest.Recorder(stream, directory)
                    begin = time.monotonic()
                    worker.worker(0, server.server_address, 10, .3, 7000, recorder, counts,
                                  threading.Event(), errors, begin, operations=12, writes=writes)
                    end = time.monotonic()
                events = [json.loads(line) for line in (directory / 'events').read_text().splitlines()]
                ready = json.loads((directory / 'readiness.json').read_text())
                self.assertEqual(len(events), 12)
                self.assertEqual(ready['completion_monotonic'], events[0]['completion_monotonic'])
                self.assertEqual(counts['errors'], 0)
                cells = under.require_coverage([{'begin_monotonic': begin, 'end_monotonic': end}], events)
                self.assertEqual(cells[0]['completion_count'], 12)
                with self.assertRaisesRegex(ValueError, 'overlap'):
                    under.require_coverage([{'begin_monotonic': end + 1, 'end_monotonic': end + 2}], events)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_exact_payload_and_complete_coverage_are_required(self):
        writes = [{'name': 'load-0-1', 'payload': 'x' * 64}]
        rows = [[f'item-{i}', hashlib.md5(str(i).encode()).hexdigest()] for i in range(1, 501)] + [[writes[0]['name'], writes[0]['payload']]]
        client = {'counts': {'reads': 49999, 'writes': 1, 'errors': 0}, 'errors': [], 'writes': writes}
        events = [{'sequence': i, 'completion_monotonic': 1 + i / 50000, 'latency_ms': 2} for i in range(50000)]
        under.verify_payload(rows, client, events)
        with self.assertRaisesRegex(ValueError, 'payload'):
            under.verify_payload(rows, client, [events[0]] * 50000)
        rows[-1][1] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'payload'):
            under.verify_payload(rows, client, events)
        with self.assertRaisesRegex(ValueError, 'overlap'):
            under.require_coverage([{'begin_monotonic': 0, 'end_monotonic': 2},
                                    {'begin_monotonic': 3, 'end_monotonic': 4}], events)

    def test_failed_health_after_compose_up_cleans_project(self):
        contract = json.loads((runner.FIXTURES / 'w8-v2/portfolio.json').read_text())
        engine = mock.Mock()
        engine.name = 'orbstack'
        def command(args, **kwargs):
            if args[:2] == ['image', 'inspect']:
                ref = args[-1]
                name = next(name for name in ('api', 'postgres', 'redis')
                            if contract['images']['np-v2/' + name]['manifest'] == ref)
                pin = contract['images']['np-v2/' + name]
                return subprocess.CompletedProcess(args, 0, json.dumps([{'Id': pin['manifest'], 'RootFS': {'Layers': pin['diff_ids']}, 'Architecture': 'arm64'}]), '')
            return subprocess.CompletedProcess(args, 0, '', '')
        engine.sh.side_effect = command
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(under.runner, 'wait_health', return_value=(None, None)):
            with self.assertRaisesRegex(RuntimeError, 'healthy'):
                with under.baseline(engine, Path(tmp), 'run', contract, lambda name: nullcontext()):
                    self.fail('unhealthy stack admitted')
            receipt = json.loads((Path(tmp) / 'under-pull-ownership.json').read_text())
        self.assertEqual(receipt['cleanup'], 'complete')
        self.assertTrue(any('down' in call.args[0] for call in engine.sh.call_args_list))

    def test_failure_after_start_terminates_client_and_cleans_stack(self):
        contract = json.loads((runner.FIXTURES / 'w8-v2/portfolio.json').read_text())
        engine = mock.Mock()
        engine.name = 'ctrs'
        def command(args, **kwargs):
            if args[:2] == ['image', 'inspect']:
                ref = args[-1]
                name = next(name for name in ('api', 'postgres', 'redis')
                            if contract['images']['np-v2/' + name]['config'] == ref)
                pin = contract['images']['np-v2/' + name]
                return subprocess.CompletedProcess(args, 0, json.dumps([{'Id': pin['config'], 'RootFS': {'Layers': pin['diff_ids']}, 'Architecture': 'arm64'}]), '')
            if args[:1] == ['exec']:
                return subprocess.CompletedProcess(args, 0, json.dumps(contract['api_files_sha256']), '')
            return subprocess.CompletedProcess(args, 0, 'container-id\n', '')
        engine.sh.side_effect = command
        process = mock.Mock(pid=42, returncode=-15)
        process.poll.return_value = None
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(under.runner, 'wait_health', return_value=(200, {})), mock.patch.object(under.subprocess, 'Popen', return_value=process):
            directory = Path(tmp)
            (directory / 'readiness.json').write_text('{"completion_monotonic": 1}')
            (directory / 'completions.jsonl').write_text('{"truncated":')
            with self.assertRaisesRegex(RuntimeError, 'pull fault'):
                with under.baseline(engine, directory, 'run', contract, lambda name: nullcontext()):
                    raise RuntimeError('pull fault')
            receipt = json.loads((directory / 'under-pull-ownership.json').read_text())
        process.terminate.assert_called_once()
        process.wait.assert_called_once()
        self.assertEqual(receipt['cleanup'], 'complete')
        self.assertIn('JSONDecodeError', receipt['receipt_error'])
        self.assertTrue(any('down' in call.args[0] for call in engine.sh.call_args_list))


if __name__ == '__main__':
    unittest.main()
