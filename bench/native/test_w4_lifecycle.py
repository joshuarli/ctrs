"""W4 ownership cleanup and image plumbing under lifecycle failures."""
import json
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import runner


class Result:
    def __init__(self, stdout='', returncode=0, stderr=''):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


class Context:
    run_id = 'test-w11'

    def __init__(self, directory):
        self.directory = directory

    def trial_dir(self, *args):
        return self.directory

    def new_record(self, *args):
        return {'metrics': {}, 'correctness': {'ok': True, 'checks': {}},
                'resources': {}, 'workload_params': {}, 'validation_errors': []}


class Engine:
    name = 'fake'

    def __init__(self, verify_timeout=False, inspection_error=False):
        self.calls = []
        self.verify_timeout = verify_timeout
        self.inspection_error = inspection_error

    def ensure_up(self):
        pass

    def sh(self, args, **kwargs):
        self.calls.append(args)
        if args[:2] == ['exec', 'nptest-w11fakew4-ingest'] and len(args) > 2 and args[2] == 'python':
            if 'hashlib' in args[-1]:
                return Result(runner.sha256_file(runner.FIXTURES / 'w4/app.py'))
        if args[0] == 'run' and 'verify' in args:
            if self.verify_timeout:
                raise subprocess.TimeoutExpired('docker run verify', 180)
            return Result('verified 200')
        if len(args) > 1 and args[1] == 'inspect':
            if self.inspection_error:
                return Result(returncode=1, stderr='permission denied')
            if '-verify-' in args[-1]:
                return Result(json.dumps([{'Config': {'Labels': {'dev.ctrs.campaign.run': 'test-w11'}}}]))
            return Result(returncode=1, stderr='no such object')
        return Result()


class W4References(unittest.TestCase):
    def test_w10_queue_verifies_recovered_backlog_before_workers_and_measures_fresh_work(self):
        queue_id = "a" * 64
        pending = [{"job": i, "clock": "guest", "enqueued_ns": i} for i in range(200)]
        images = [
            {"Id": "sha256:" + digit * 64, "Os": "linux", "Architecture": "arm64",
             "RootFS": {"Layers": ["sha256:" + layer * 64]}, "Config": {"Cmd": [role]}}
            for digit, layer, role in (("b", "d", "worker"), ("c", "e", "redis-server"))
        ]

        class PersistentQueue(Engine):
            def __init__(self, lose_backlog=False):
                super().__init__()
                self.lose_backlog = lose_backlog
                self.snapshots = 0
                self.pings = 0
                self.owned = {}

            def sh(self, args, **kwargs):
                self.calls.append(args)
                if args[:2] == ["image", "inspect"]:
                    return Result(json.dumps(images if len(args) == 4 else [images[1]]))
                if args[:2] == ["run", "-d"] and "redis-server" in args:
                    self.owned[args[args.index("--name") + 1]] = "container"
                    return Result(queue_id)
                if args[:2] == ["volume", "create"]:
                    self.owned[args[-1]] = "volume"
                if args[:1] == ["exec"] and "hashlib" in args[-1]:
                    file = "latency.py" if "/app/latency.py" in args[-1] else "app.py"
                    return Result(runner.sha256_file(runner.FIXTURES / "w4" / file))
                if args[:1] == ["exec"] and "pending" in args:
                    self.snapshots += 1
                    rows = pending[:-1] if self.lose_backlog and self.snapshots == 2 else pending
                    return Result(json.dumps(rows))
                if args == ["exec", queue_id, "redis-cli", "PING"]:
                    self.pings += 1
                    return Result("LOADING" if self.pings == 1 else "PONG")
                if args[:1] == ["run"] and "verify" in args:
                    name = args[args.index("--name") + 1]
                    extra = 50_000_000 if name.endswith("-backlog") else 1_000_000
                    rows = [row | {"completed_ns": row["enqueued_ns"] + extra} for row in pending]
                    return Result(json.dumps({"verified": 200, "clock": "guest", "timings": rows}))
                if len(args) > 1 and args[1] == "inspect":
                    kind = self.owned.get(args[-1])
                    if kind is None:
                        return Result(returncode=1, stderr="no such object")
                    labels = {"Labels": {"dev.ctrs.campaign.run": "test-w11"}}
                    return Result(json.dumps([{"Config": labels} if kind == "container" else labels]))
                return Result()

        with tempfile.TemporaryDirectory(dir=Path(runner.REPO) / ".work/tmp") as directory:
            with patch.object(runner, "start_sampler", return_value=(None, None)), \
                    patch.object(runner, "resource_phase", side_effect=lambda *args: __import__("contextlib").nullcontext()), \
                    patch.object(runner.time, "sleep"):
                engine = PersistentQueue()
                outcome = runner.trial_w10(Context(Path(directory)), engine, "warm", concurrency=4, interrupt_service="queue")
                lost = PersistentQueue(lose_backlog=True)
                wrong = runner.trial_w10(Context(Path(directory)), lost, "warm", concurrency=4, interrupt_service="queue")

            self.assertTrue(outcome["correctness"]["ok"], outcome)
            self.assertEqual(outcome["metrics"]["jobs"], 400)
            self.assertEqual(outcome["metrics"]["retries_until_recovery"], 1)
            self.assertEqual(outcome["metrics"]["queue_p99_ms_at_backlog"], 50)
            self.assertEqual(outcome["metrics"]["recovered_p99_ms"], 1)
            self.assertTrue(outcome["workload_params"]["pinned_recovery_inputs"])
            self.assertEqual(outcome["paired_inputs"]["images"]["worker"]["diff_ids"],
                             images[0]["RootFS"]["Layers"])
            self.assertEqual(lost.snapshots, 2)
            self.assertFalse(wrong["correctness"]["ok"])
            self.assertNotIn("recovered_p99_ms", wrong["metrics"])
            self.assertFalse(any(cmd[0] == "run" and "worker" in cmd for cmd in lost.calls))
            for queue_engine in (engine, lost):
                redis = next(cmd for cmd in queue_engine.calls if "redis-server" in cmd)
                self.assertIn(images[1]["Id"], redis)
                self.assertIn("--appendfsync", redis)
                self.assertEqual(redis[redis.index("--appendfsync") + 1], "always")
                volume = redis[redis.index("-v") + 1].removesuffix(":/data")
                self.assertIn(["kill", queue_id], queue_engine.calls)
                self.assertIn(["start", queue_id], queue_engine.calls)
                self.assertIn(["volume", "rm", volume], queue_engine.calls)

    def test_timed_w4_publishes_tails_only_for_complete_receipts(self):
        class TimedEngine(Engine):
            def __init__(self, omit=False):
                super().__init__()
                self.omit = omit

            def sh(self, args, **kwargs):
                if args[:1] == ['exec'] and '/app/latency.py' in args[-1] and 'hashlib' in args[-1]:
                    return Result(runner.sha256_file(runner.FIXTURES / 'w4/latency.py'))
                if args[:1] == ['run'] and 'verify' in args:
                    timings = [{'job': i, 'clock': 'guest', 'enqueued_ns': 0, 'completed_ns': (i + 1) * 1_000_000}
                               for i in range(199 if self.omit else 200)]
                    return Result(json.dumps({'verified': 200, 'clock': 'guest', 'timings': timings}))
                return super().sh(args, **kwargs)

        with tempfile.TemporaryDirectory(dir=Path(runner.REPO) / '.work/tmp') as directory:
            with patch.object(runner, 'start_sampler', return_value=(None, None)), patch.object(runner, 'resource_phase', side_effect=lambda *args: __import__('contextlib').nullcontext()):
                context = Context(Path(directory))
                result = runner.trial_w4(context, TimedEngine(), 'warm', workers=(4,), fixture_version=runner.W4_LATENCY_VERSION)
                missing = runner.trial_w4(context, TimedEngine(omit=True), 'warm', workers=(4,), fixture_version=runner.W4_LATENCY_VERSION)
            self.assertTrue(result['correctness']['ok'], result)
            self.assertEqual(result['metrics']['queue_p95_ms_at_4'], 190)
            self.assertEqual(result['metrics']['queue_p99_ms_at_4'], 198)
            self.assertEqual(result['metrics']['jobs_at_4'], 200)
            self.assertFalse(missing['correctness']['ok'])
            self.assertNotIn('queue_p95_ms_at_4', missing['metrics'])
            self.assertNotIn('jobs_at_4', missing['metrics'])

    def test_explicit_images_are_used_for_queue_and_workers(self):
        with tempfile.TemporaryDirectory(dir=Path(runner.REPO) / '.work/tmp') as directory:
            engine = Engine()
            with patch.object(runner, 'start_sampler', return_value=(None, None)), patch.object(runner, 'resource_phase', side_effect=lambda *args: __import__('contextlib').nullcontext()):
                result = runner.trial_w4(Context(Path(directory)), engine, 'mixed', workers=(4,), image_ref='worker@sha256:test', redis_ref='redis@sha256:test')
            self.assertTrue(result['correctness']['ok'], result)
            runs = [call for call in engine.calls if call[0] == 'run']
            self.assertTrue(any('redis@sha256:test' in call and 'redis-server' in call for call in runs))
            self.assertEqual(sum('worker@sha256:test' in call and 'worker' in call for call in runs), 4)
            self.assertTrue(any('worker@sha256:test' in call and 'verify' in call for call in runs))


    def trial(self, engine):
        with tempfile.TemporaryDirectory(dir=Path(runner.REPO) / '.work/tmp') as directory:
            with patch.object(runner, 'start_sampler', return_value=(None, None)), patch.object(runner, 'resource_phase', side_effect=lambda *args: __import__('contextlib').nullcontext()):
                return runner.trial_w4(Context(Path(directory)), engine, 'mixed', workers=(4,))

    def test_verifier_timeout_cleans_its_owned_container(self):
        engine = Engine(verify_timeout=True)
        result = self.trial(engine)
        self.assertFalse(result['correctness']['ok'])
        runs = [call for call in engine.calls if call[0] == 'run' and 'verify' in call]
        name = runs[0][runs[0].index('--name') + 1]
        self.assertIn(['rm', '-f', name], engine.calls)
        self.assertTrue(any('timed out' in error for error in result['validation_errors']))

    def test_inspection_failure_is_not_treated_as_absent(self):
        result = self.trial(Engine(inspection_error=True))
        self.assertFalse(result['correctness']['ok'])
        self.assertTrue(any('permission denied' in error for error in result['validation_errors']))

    def test_work_expiry_keeps_owned_cleanup_available(self):
        from types import SimpleNamespace
        engine = Engine()
        expired = [False]
        def work(args, **kwargs):
            if args[0] == 'run' and 'verify' in args:
                expired[0] = True
            if expired[0]:
                raise TimeoutError('work drain expired')
            return engine.sh(args, **kwargs)
        effects = SimpleNamespace(name=engine.name, ensure_up=engine.ensure_up, sh=work)
        with tempfile.TemporaryDirectory(dir=Path(runner.REPO) / '.work/tmp') as directory:
            with patch.object(runner, 'start_sampler', return_value=(None, None)), patch.object(runner, 'resource_phase', side_effect=lambda *args: __import__('contextlib').nullcontext()):
                result = runner.trial_w4(Context(Path(directory)), effects, 'mixed', workers=(4,), cleanup_command=engine.sh)
        self.assertFalse(result['correctness']['ok'])
        self.assertTrue(any('work drain expired' in error for error in result['validation_errors']))
        self.assertFalse(any('cleanup error' in error for error in result['validation_errors']))
        self.assertIn(['rm', '-f', 'nptest-w11fakew4-verify-4'], engine.calls)


if __name__ == '__main__':
    unittest.main()
