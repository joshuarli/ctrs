import copy
import json
import subprocess
import threading
import unittest
from types import SimpleNamespace

import ci_jobs

IMAGE = 'example/image@' + ci_jobs.IMAGE_DIGEST
CASES = ci_jobs.SPEC['cases']
BODY = {'tools': ci_jobs.TOOLS, 'source_lock': ci_jobs.SOURCE_LOCK,
        'artifact': ci_jobs.ARTIFACT, 'tests': [case['result'] for case in CASES]}


class FakeEngine:
    def __init__(self, concurrency=1, failure=None, cleanup_failure=False):
        self.concurrency = concurrency
        self.failure = failure
        self.cleanup_failure = cleanup_failure
        self.lock = threading.Condition()
        self.active = 0
        self.maximum = 0
        self.started = 0
        self.names = []
        self.removed = []

    def sh(self, args, **kwargs):
        if args[0] == 'run':
            name = args[args.index('--name') + 1]
            index = int(name[-2:])
            with self.lock:
                self.names.append(name)
                self.started += 1
                self.active += 1
                self.maximum = max(self.maximum, self.active)
                self.lock.notify_all()
                if self.started <= self.concurrency:
                    if not self.lock.wait_for(lambda: self.started >= self.concurrency, timeout=5):
                        raise RuntimeError('concurrency did not start')
                self.active -= 1
            if index == self.failure:
                raise subprocess.TimeoutExpired('run', 120)
            return SimpleNamespace(returncode=0, stdout=json.dumps(BODY), stderr='')
        if args[0] == 'inspect':
            name = args[1]
            owner = name.rsplit('-', 1)[0]
            return SimpleNamespace(returncode=0, stdout=json.dumps([{'Config': {'Labels': {'dev.ctrs.campaign.run': owner}}}]), stderr='')
        if args[0] == 'rm':
            self.removed.append(args[-1])
            if self.cleanup_failure:
                raise RuntimeError('cleanup failed')
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        raise AssertionError(args)


class CIJobsTests(unittest.TestCase):
    def test_fixed_jobs_and_concurrency(self):
        for concurrency in (1, 4, 8, 16):
            with self.subTest(concurrency=concurrency):
                engine = FakeEngine(concurrency)
                results = ci_jobs.run_condition(engine, IMAGE, 'np-campaign', concurrency)
                self.assertEqual([r['job'] for r in results], list(range(16)))
                self.assertEqual(engine.maximum, concurrency)
                self.assertEqual(len(set(engine.names)), 16)
                self.assertTrue(all(r['body'] == BODY and r['error'] is None for r in results))

    def test_result_validation_rejects_wrong_artifact_tools_and_cli(self):
        for key, value in [('artifact', 'wrong'), ('source_lock', 'wrong'), ('tools', {}), ('tests', []), ('extra', 1)]:
            body = copy.deepcopy(BODY)
            body[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                ci_jobs.validate_result(body, CASES)
        for key, value in [('status', 1), ('stdout', 'wrong'), ('stderr', 'warning')]:
            body = copy.deepcopy(BODY)
            body['tests'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                ci_jobs.validate_result(body, CASES)

    def test_failure_waits_for_all_jobs_and_cleans_owned_container(self):
        engine = FakeEngine(4, failure=3)
        with self.assertRaises(ci_jobs.ConditionFailed) as raised:
            ci_jobs.run_condition(engine, IMAGE, 'np-campaign', 4)
        results = raised.exception.results
        self.assertEqual(len(results), 16)
        self.assertEqual(len([r for r in results if r['error']]), 1)
        self.assertIn('TimeoutExpired', results[3]['error'])
        self.assertEqual(engine.removed, [results[3]['name']])
        self.assertTrue(all(r['body'] == BODY for r in results if r['job'] != 3))

    def test_cleanup_failure_is_visible(self):
        engine = FakeEngine(4, failure=3, cleanup_failure=True)
        with self.assertRaises(ci_jobs.ConditionFailed) as raised:
            ci_jobs.run_condition(engine, IMAGE, 'np-campaign', 4)
        self.assertIn('cleanup failed', raised.exception.results[3]['cleanup_error'])
        self.assertEqual(len(raised.exception.results), 16)

    def test_rejects_invalid_inputs_before_engine_calls(self):
        for image, prefix, concurrency, _ in [('example:tag', 'np-test', 1, 16), (IMAGE, 'other', 1, 16),
                                                   (IMAGE, 'np-test', 2, 16), (IMAGE, 'np-test', False, 16),
                                                   ('example/image@sha256:' + 'a' * 64, 'np-test', 1, 16)]:
            engine = FakeEngine()
            with self.assertRaises(ValueError):
                ci_jobs.run_condition(engine, image, prefix, concurrency)
            self.assertEqual(engine.names, [])

    def test_cleanup_refuses_unowned_container(self):
        class Unowned:
            def sh(self, args, **kwargs):
                if args[0] == 'inspect':
                    return SimpleNamespace(returncode=0, stdout=json.dumps([{'Config': {'Labels': {'dev.ctrs.campaign.run': 'other'}}}]), stderr='')
                raise AssertionError('unowned container removed')
        with self.assertRaisesRegex(RuntimeError, 'ownership mismatch'):
            ci_jobs.cleanup(Unowned(), 'np-test-00', 'np-test')


if __name__ == '__main__':
    unittest.main()
