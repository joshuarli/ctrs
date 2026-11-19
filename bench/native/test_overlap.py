import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import overlap
import runner
import transfer


class Context:
    run_id = 'test-run'

    def __init__(self, root):
        self.root = Path(root)
        self.n = 0

    def trial_dir(self, engine, case, state):
        self.n += 1
        path = self.root / str(self.n)
        path.mkdir()
        return path

    def new_record(self, engine, case, state, directory):
        return {'metrics': {}, 'inputs': {}, 'resources': {},
                'correctness': {'ok': True, 'checks': {}}, 'validation_errors': []}


class Engine:
    name = 'fake'
    w13_image_id = 'image'

    def __init__(self):
        self.commands = []

    def ensure_up(self):
        pass

    def env(self):
        return {}

    def sh(self, args, **kwargs):
        self.commands.append(args)
        if 'inspect' in args:
            return Result('test-run')
        if 'cat' in args:
            return Result(json.dumps([receipt()]))
        return Result('')


class Result:
    def __init__(self, stdout='', returncode=0):
        self.stdout = stdout
        self.stderr = ''
        self.returncode = returncode


def receipt():
    return {'id': '0', 'bytes': 10, 'sha256': 'hash', 'seconds': 8.0,
            'first_byte_seconds': 0.1, 'error': None}


class OverlapTests(unittest.TestCase):
    def test_conservative_union_and_empty_window(self):
        transfers = [{'host_start': 0, 'host_end': 10, 'receipts': [receipt()]},
                     {'host_start': 7, 'host_end': 17, 'receipts': [receipt()]}]
        self.assertAlmostEqual(overlap.overlap_fraction((2, 15), transfers), 11.8 / 13)
        self.assertEqual(overlap.overlap_fraction((1, 1), transfers), 0)

    def run_case(self, end):
        with tempfile.TemporaryDirectory() as tmp:
            ctx, engine = Context(tmp), Engine()
            events = []
            def w13(ctx, engine, state, **kwargs):
                events.append('transfer')
                ctx.overlap_transfer_observer('start', 0, None)
                ctx.overlap_transfer_observer('end', end, {'streams': [receipt()]})
                ctx.overlap_transfer_observer('receipts', end, [receipt()])
                return {'metrics': {'goodput_bytes_per_second': 42}, 'correctness': {'ok': True}, 'validation_errors': []}
            def w2(ctx, engine, state, *args, **kwargs):
                with ctx.overlap_workload():
                    events.append('w2')
                (ctx.overlap_dir / 'w2-load.json').write_text('{}')
                return {'metrics': {'p50_ms': 1, 'p99_ms': 3, 'rps': 9}, 'correctness': {'ok': True}, 'validation_errors': []}
            with patch.object(runner, 'trial_w13', w13), patch.object(runner, 'trial_w2', w2), \
                 patch.object(overlap.time, 'monotonic', side_effect=[3, 7]), patch.object(overlap.time, 'sleep'):
                record = overlap.trial_overlap(ctx, engine, 'warm', lead_seconds=0)
            self.assertEqual(events, ['transfer', 'w2'])
            self.assertTrue((ctx.root / '1' / 'w13-receipts.json').exists())
            self.assertTrue((ctx.root / '1' / 'w2-load.json').exists())
            return record

    def test_metrics_and_overlap(self):
        rec = self.run_case(8)
        self.assertTrue(rec['correctness']['ok'])
        self.assertEqual([rec['metrics'][k] for k in ('w2_latency_p50_ms', 'w2_latency_p99_ms', 'w2_rps', 'transfer_goodput_bytes_per_second')], [1, 3, 9, 42])
        self.assertEqual(rec['metrics']['overlap_fraction'], 1)

    def test_missing_overlap_fails(self):
        rec = self.run_case(20)
        self.assertFalse(rec['correctness']['ok'])
        self.assertIn('transfer_not_overlapping', rec['validation_errors'])

    def test_transfer_ownership_labels_and_cleanup(self):
        class Process:
            returncode = 0
            def __init__(self, command, **kwargs):
                result = Path(command[-1])
                if result.is_absolute() and result.parent.exists():
                    result.write_text(json.dumps([receipt()]))
            def poll(self): return 0 if getattr(self, 'done', False) else None
            def communicate(self, **kwargs):
                self.done = True
                return '', ''
        def invoke(cmd, **kwargs):
            if 'prepare' in cmd:
                return Result('hash')
            return Result(json.dumps({'seconds': 8, 'streams': [receipt()]}))
        with tempfile.TemporaryDirectory() as tmp:
            ctx, engine = Context(tmp), Engine()
            with patch.object(transfer.subprocess, 'run', side_effect=invoke), \
                 patch.object(transfer.subprocess, 'Popen', Process), \
                 patch.object(transfer.time, 'sleep'), patch.object(runner, 'free_port', return_value=1234), \
                 patch.object(runner, 'start_sampler', return_value=(None, None)), \
                 patch.object(runner, 'resource_phase', return_value=__import__('contextlib').nullcontext()):
                rec = transfer.trial_w13(ctx, engine, 'warm', size_bytes=10, repeats=1)
            self.assertTrue(rec['correctness']['ok'], rec['validation_errors'])
            creations = [c for c in engine.commands if c[:2] == ['network', 'create'] or c[:2] == ['run', '-d']]
            self.assertEqual(len(creations), 3)
            self.assertTrue(all('dev.ctrs.campaign.run=test-run' in c for c in creations))
            self.assertEqual(len([c for c in engine.commands if 'inspect' in c]), 3)
            self.assertEqual(len([c for c in engine.commands if c[0] == 'rm' or c[:2] == ['network', 'rm']]), 3)


if __name__ == '__main__':
    unittest.main()
