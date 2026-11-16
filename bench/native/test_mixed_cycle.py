"""Source-only checks for W11's W4 image-reference plumbing."""
import json
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
                'resources': {}, 'validation_errors': []}


class Engine:
    name = 'fake'

    def __init__(self):
        self.calls = []

    def ensure_up(self):
        pass

    def sh(self, args, **kwargs):
        self.calls.append(args)
        if args[:2] == ['exec', 'nptest-w11fakew4-ingest'] and len(args) > 2 and args[2] == 'python':
            if 'hashlib' in args[-1]:
                return Result(runner.sha256_file(runner.FIXTURES / 'w4/app.py'))
        if args[0] == 'run' and 'verify' in args:
            return Result('verified 200')
        if len(args) > 1 and args[1] == 'inspect':
            return Result(returncode=1, stderr='no such object')
        return Result()


class W4References(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
