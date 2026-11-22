"""Exercise cumulative mixed-load identities through the real W2 HTTP client."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import mixed_cycle
import reporting
import runner


def setUpModule():
    (runner.REPO / '.work/tmp').mkdir(parents=True, exist_ok=True)


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


class DurationAdmission(unittest.TestCase):
    def test_persistent_cycles_and_deadline_admission(self):
        from types import SimpleNamespace
        from contextlib import nullcontext
        with tempfile.TemporaryDirectory(dir=runner.REPO / '.work/tmp') as scratch:
            root = Path(scratch)
            ctx = SimpleNamespace(results_dir=root, run_id='run', new_record=lambda *a: {
                'notes': [], 'cycles': [], 'correctness': {'checks': {}}, 'validation_errors': [], 'resources': {}})
            engine = SimpleNamespace(name='ctrs', socket='unix:///socket', dir=root, ensure_up=lambda: None)
            ids = {'api': 'api-id', 'db': 'db-id', 'cache': 'cache-id'}
            cumulative = []
            def sh(args, **kwargs):
                if args[:1] == ['compose'] and 'ps' in args:
                    out = ids[args[-1]]
                elif args[:2] == ['image', 'inspect']:
                    name = next(k for k, v in refs.items() if v == args[-1])
                    pin = mixed_cycle.WORKER['worker'] if name == 'worker' else mixed_cycle.PIN['images']['np-v6/' + name]
                    out = json.dumps([{'Architecture': 'arm64', 'RepoDigests': [args[-1]], 'RootFS': {'Layers': pin['diff_ids']}}])
                elif args[:2] == ['volume', 'inspect']:
                    out = '[{"identity":"volume"}]'
                elif args[:2] == ['exec', 'api-id']:
                    out = json.dumps(mixed_cycle.PIN['api_files_sha256'])
                elif args[:2] == ['exec', 'db-id']:
                    if 'DELETE FROM items' in args[-1]:
                        out = json.dumps([[row['name'], row['payload']] for row in cumulative])
                        cumulative.clear()
                    else:
                        out = json.dumps(cumulative)
                else:
                    out = ''
                return SimpleNamespace(stdout=out, stderr='', returncode=0)
            engine.sh = sh
            refs = {n.rsplit('/', 1)[1]: 'example/image@' + p['manifest'] for n, p in mixed_cycle.PIN['images'].items()}
            refs['worker'] = 'example/worker@' + mixed_cycle.WORKER['worker']['manifest']
            clock = [0]
            def load(base, cycle, directory):
                row = {'name': f'write-{cycle}', 'payload': str(cycle)}
                cumulative.append(row)
                clock[0] += 1
                return [row]
            with patch.object(mixed_cycle.time, 'monotonic', side_effect=lambda: clock[0]), \
                 patch.object(mixed_cycle.ownership, 'discover', return_value={'required_processes': []}), \
                 patch.object(runner, 'CTRS_BIN', root / 'binary'), \
                 patch.object(runner, 'start_sampler', return_value=(object(), None)), \
                 patch.object(runner, 'stop_sampler'), \
                 patch.object(runner, 'resource_phase', side_effect=lambda *a: nullcontext()), \
                 patch.object(runner, 'wait_health', return_value=(200, {})), \
                 patch.object(runner, 'http_json_write', return_value=(200, {})), \
                 patch.object(runner, 'http_json', return_value=(200, {'key': 'mixed-committed', 'value': 'exact-v3', 'cache_match': True})), \
                 patch.object(runner, 'exact_w2_items', side_effect=lambda actual, expected: actual == expected), \
                 patch.object(runner, 'trial_w4', return_value={'correctness': {'ok': True}, 'metrics': dict(runner.W4_FIXED_WORK)}), \
                 patch.object(mixed_cycle, 'bounded_load_cycle', side_effect=lambda base, cycle, directory, deadline: load(base, cycle, directory)), \
                 patch.object(mixed_cycle.ci_jobs, 'run_condition', return_value=[{}] * 16), \
                 patch.object(mixed_cycle.ci_jobs, 'cleanup') as cleanup:
                engine.name = 'orbstack'
                result = mixed_cycle.run(engine, ctx, refs, work_deadline=2, drain_deadline=10)
                cumulative.clear()
                clock[0] = 0
                observation_root = root / 'observed'; observation_root.mkdir()
                ctx.results_dir = observation_root
                def observe(plan, cycle, directory):
                    self.assertEqual(cumulative, [])
                    return {'cycle': cycle, 'version': mixed_cycle.mixed_resources.VERSION,
                            'interval': {'status': 'unknown', 'errors': ['missing VM']}}
                with patch.object(mixed_cycle.mixed_resources, 'observe', side_effect=observe):
                    observed = mixed_cycle.run(engine, ctx, refs, work_deadline=2, drain_deadline=10,
                                               observation={'seconds': 30})
                growth = observed['resources']['cycle_growth']
                self.assertEqual(observed['fixture_version'], mixed_cycle.mixed_resources.VERSION)
                self.assertEqual(len(growth['observations']), 2)
                self.assertEqual(growth['physical_footprint']['status'], 'unknown')
                self.assertFalse(growth['qualification_eligible'])
                self.assertTrue((observation_root / 'orbstack/cycle-0/resource-observation.json').exists())
                self.assertNotIn('cycle_growth', result['resources'])
                cumulative.clear()
                clock[0] = 0
                combined_root = root / 'combined-failure'; combined_root.mkdir()
                ctx.results_dir = combined_root
                def load_then_fail(base, cycle, directory, deadline):
                    if cycle == 1:
                        raise RuntimeError('later workload failure')
                    return load(base, cycle, directory)
                with patch.object(mixed_cycle.mixed_resources, 'observe', side_effect=RuntimeError('observation failed')), \
                     patch.object(mixed_cycle, 'bounded_load_cycle', side_effect=load_then_fail):
                    with self.assertRaisesRegex(RuntimeError, 'later workload failure'):
                        mixed_cycle.run(engine, ctx, refs, work_deadline=2, drain_deadline=10, observation={})
                combined = json.loads((combined_root / 'orbstack/result.json').read_text())
                self.assertIn('observation failed', combined['resources']['cycle_growth']['observations'][0]['interval']['errors'][0])
                self.assertTrue(any('later workload failure' in error for error in combined['validation_errors']))
                cumulative.clear()
                clock[0] = 0
                failure_root = root / 'failure'; failure_root.mkdir()
                ctx.results_dir = failure_root
                with patch.object(mixed_cycle, 'bounded_load_cycle', side_effect=RuntimeError('injected workload failure')), \
                     patch.object(runner, 'stop_sampler', side_effect=RuntimeError('sampler stop failed')):
                    with self.assertRaisesRegex(RuntimeError, 'injected workload failure'):
                        mixed_cycle.run(engine, ctx, refs, work_deadline=2, drain_deadline=10)
                failure = json.loads((failure_root / 'orbstack/result.json').read_text())
                self.assertFalse(failure['correctness']['ok'])
                self.assertTrue(any('injected workload failure' in e for e in failure['validation_errors']))
                self.assertTrue(any('sampler stop failed' in e for e in failure['validation_errors']))
                boot_root = root / 'boot-mismatch'; boot_root.mkdir()
                ctx.results_dir = boot_root
                with self.assertRaisesRegex(ValueError, 'boot assets differ'):
                    mixed_cycle.run(engine, ctx, refs, work_deadline=2, drain_deadline=10,
                                    expected_boot_assets={'/unexpected/Image': {'sha256': 'wrong'}})
                budget_root = root / 'budget-mismatch'; budget_root.mkdir()
                ctx.results_dir = budget_root
                with patch.object(runner, 'safe_engine_info', return_value={'ncpu': 4, 'mem_total_bytes': 8 << 30}), \
                     self.assertRaisesRegex(ValueError, 'resource envelope differs'):
                    mixed_cycle.run(engine, ctx, refs, work_deadline=2, drain_deadline=10,
                                    expected_resources={'ncpu': 2, 'mem_total_bytes': 8 << 30})
                self.assertEqual(cleanup.call_count, 6)
            self.assertEqual([c['cumulative_writes'] for c in result['cycles']], [1, 2])
            self.assertEqual([c['explicitly_deleted_writes'] for c in result['cycles']], [1, 1])
            for cycle in result['cycles']:
                self.assertEqual(cycle['queue_jobs'], 200)
                self.assertEqual(cycle['queue_events'], 12800)
                self.assertEqual(cycle['artifacts'], 400)
                self.assertEqual(cycle['build_jobs'], 16)
            for index in range(2):
                directory = root / 'orbstack' / f'cycle-{index}'
                self.assertEqual(len(json.loads((directory / 'persisted-items.json').read_text())), 1)
                self.assertEqual(json.loads((directory / 'retained-items.json').read_text()), [])
            self.assertEqual([c['service_ids'] for c in result['cycles']], [ids, ids])
            self.assertEqual(len(result['cycles']), 2)
            self.assertTrue(reporting._correct(result))


class CycleRetention(unittest.TestCase):
    def test_cleanup_checks_every_deleted_payload_and_retained_seed(self):
        import hashlib
        from types import SimpleNamespace
        seed = [[f'item-{i}', hashlib.md5(str(i).encode()).hexdigest()] for i in range(1, 501)]
        writes = [{'name': 'write-0', 'payload': 'one'}, {'name': 'write-1', 'payload': 'two'}]
        expected = [[row['name'], row['payload']] for row in writes]
        for removed, remaining, valid in ((expected, seed, True),
                (expected[:-1], seed, False),
                (expected + [expected[0]], seed, False),
                ([['write-0', 'corrupt'], expected[1]], seed, False),
                (expected, seed[:-1], False),
                (expected, seed + [expected[0]], False)):
            with self.subTest(removed=removed, valid=valid), tempfile.TemporaryDirectory() as tmp:
                engine = SimpleNamespace(sh=Mock(side_effect=[
                    SimpleNamespace(stdout=json.dumps(removed)),
                    SimpleNamespace(stdout=json.dumps(remaining))]))
                if valid:
                    mixed_cycle.cleanup_cycle_items(engine, 'owned-db', writes, Path(tmp))
                    self.assertEqual(json.loads((Path(tmp) / 'retained-items.json').read_text()), seed)
                else:
                    with self.assertRaisesRegex(ValueError, 'cleanup'):
                        mixed_cycle.cleanup_cycle_items(engine, 'owned-db', writes, Path(tmp))


class DurationLoadBound(unittest.TestCase):
    def test_joined_worker_cleanup_errors_remain_in_parent_evidence(self):
        from concurrent.futures import Future
        queue, build = Future(), Future()
        queue.set_result({'correctness': {'ok': False}, 'validation_errors': ['cleanup error: owned network remains']})
        build.set_exception(mixed_cycle.ci_jobs.ConditionFailed([
            {'job': 3, 'error': 'work deadline', 'cleanup_error': 'owned container remains'}]))
        errors = mixed_cycle.worker_failures({'queue': queue, 'build': build})
        self.assertEqual(len(errors), 2)
        self.assertIn('owned network remains', errors[0])
        self.assertIn('owned container remains', errors[1])

    def test_unresponsive_http_load_child_is_stopped_at_drain(self):
        import socket
        import subprocess
        import time
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(8)
        listener.settimeout(2)
        released = threading.Event()
        accepted = []
        def hold():
            try:
                connection, _ = listener.accept()
                accepted.append(connection)
                released.wait(3)
            except OSError:
                pass
            finally:
                for connection in accepted:
                    connection.close()
        thread = threading.Thread(target=hold)
        thread.start()
        try:
            with tempfile.TemporaryDirectory(dir=runner.REPO / '.work/tmp') as tmp:
                started = time.monotonic()
                with self.assertRaises(subprocess.TimeoutExpired):
                    mixed_cycle.bounded_load_cycle(f'http://127.0.0.1:{listener.getsockname()[1]}', 0, Path(tmp), started + .6)
                self.assertLess(time.monotonic() - started, 3)
                self.assertTrue(accepted)
        finally:
            released.set()
            listener.close()
            thread.join(timeout=3)
        self.assertFalse(thread.is_alive())
