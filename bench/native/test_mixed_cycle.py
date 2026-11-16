"""Exercise cumulative mixed-load identities through the real W2 HTTP client."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import mixed_cycle
import runner


class MixedLoad(unittest.TestCase):
    def test_real_http_cycles_have_disjoint_writes_and_exact_cumulative_state(self):
        writes = []
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *args):
                pass
            def reply(self, body):
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def do_GET(self):
                self.reply({'items': [{'id': i, 'name': f'item-{i}'} for i in range(1, 26)]})
            def do_POST(self):
                value = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                writes.append(value)
                self.reply({'id': len(writes), 'name': value['name']})
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
        thread.start()
        try:
            with tempfile.TemporaryDirectory(dir=runner.REPO / '.work/tmp') as scratch, patch.object(mixed_cycle, 'OPERATIONS', 32):
                cumulative = []
                for cycle in range(2):
                    directory = Path(scratch) / str(cycle); directory.mkdir()
                    cumulative.extend(mixed_cycle.load_cycle(f'http://127.0.0.1:{server.server_port}', cycle, directory))
                    summary = json.loads((directory / 'load.json').read_text())
                    self.assertEqual(summary['reads_ok'] + summary['writes_ok'], 32)
                    self.assertEqual(summary['errors'], 0)
                self.assertGreater(len(cumulative), 0)
                self.assertEqual(len(cumulative), len({row['name'] for row in cumulative}))
                seed = [[f'item-{i}', __import__('hashlib').md5(str(i).encode()).hexdigest()] for i in range(1, 501)]
                actual = seed + [[row['name'], row['payload']] for row in writes]
                self.assertTrue(runner.exact_w2_items(actual, cumulative))
                self.assertFalse(runner.exact_w2_items(actual[:-1], cumulative))
                self.assertFalse(runner.exact_w2_items(actual + [actual[-1]], cumulative))
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
        self.assertFalse(thread.is_alive())

    def test_image_pin_failure_precedes_engine_access(self):
        refs = {name.rsplit('/', 1)[1]: 'example/image@' + pin['manifest'] for name, pin in mixed_cycle.PIN['images'].items()}
        refs['worker'] = 'example/worker@' + mixed_cycle.WORKER['worker']['manifest']
        mixed_cycle.validate_refs(refs)
        refs['redis'] = 'redis:latest'
        with self.assertRaisesRegex(ValueError, 'redis'):
            mixed_cycle.run(None, None, refs, 1)


if __name__ == '__main__':
    unittest.main()
