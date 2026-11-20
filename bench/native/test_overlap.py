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


class CyclicTransferTests(unittest.TestCase):
    def test_send_cycles_a_smaller_artifact_and_receiver_checks_every_byte(self):
        import socket
        import threading
        from fixtures.w13 import transfer_tool as tool
        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root) / 'a.bin'
            digest = tool.prepare(str(artifact), 3 * tool.CHUNK + 5)
            total = 3 * (3 * tool.CHUNK + 5) + 7
            for corrupt in (False, True):
                left, right = socket.socketpair()
                sent = Path(root) / 'sent.bin'
                data = artifact.read_bytes()
                cycled = (data * 4)[:total]
                if corrupt:
                    cycled = cycled[:-1] + bytes([cycled[-1] ^ 1])
                sent.write_bytes(cycled)
                def sender():
                    with left:
                        left.sendall((json.dumps({'id': '0'}) + '\n').encode())
                        tool.send(left, str(sent if corrupt else artifact), '0', total, digest)
                thread = threading.Thread(target=sender)
                thread.start()
                with right:
                    self.assertEqual(tool.line(right), {'id': '0'})
                    result = tool.receive(right, '0', total, digest, str(artifact))
                thread.join()
                self.assertEqual(result['bytes'], total)
                self.assertEqual(result['error'] is None, not corrupt)

    def test_overlap_sends_one_cycled_transfer(self):
        calls = []
        def fake(ctx, engine, state, **kw):
            calls.append(kw)
            raise RuntimeError('stop')
        def w2(ctx, *a, **k):
            try:
                with ctx.overlap_workload():
                    pass
            except RuntimeError:
                pass
            return {'metrics': {}, 'correctness': {'ok': False}}
        with tempfile.TemporaryDirectory() as root, patch.object(runner, 'trial_w13', fake), \
                patch.object(runner, 'trial_w2', w2):
            rec = overlap.trial_overlap(Context(root), Engine(), 'warm', size_bytes=1 << 20, loops=8)
        self.assertFalse(rec['correctness']['ok'])
        self.assertEqual(calls, [{'size_bytes': 8 << 20, 'repeats': 1, 'streams': 1, 'artifact_bytes': 1 << 20}])


class OverlapTests(unittest.TestCase):
    def test_conservative_union_and_empty_window(self):
        transfers = [{'host_start': 0, 'host_end': 10, 'receipts': [receipt()]},
                     {'host_start': 7, 'host_end': 17, 'receipts': [receipt()]}]
        self.assertAlmostEqual(overlap.overlap_fraction((2, 15), transfers), 11.8 / 13)
        self.assertEqual(overlap.overlap_fraction((1, 1), transfers), 0)

    def test_transfer_pairs_on_verified_identity_not_the_engine_image_id(self):
        def record(image_id):
            def w13(ctx, engine, state, **kwargs):
                ctx.overlap_transfer_observer('start', 0, None)
                ctx.overlap_transfer_observer('end', 8, {'streams': [receipt()]})
                return {'metrics': {}, 'correctness': {'ok': True}, 'validation_errors': [],
                        'inputs': {'image_id': image_id, 'sha256_per_stream': 'hash'},
                        'paired_inputs': {'api_config': 'sha256:c', 'sha256_per_stream': 'hash'}}
            def w2(ctx, engine, state, *args, **kwargs):
                with ctx.overlap_workload():
                    pass
                return {'metrics': {}, 'correctness': {'ok': True}, 'validation_errors': [],
                        'paired_inputs': {'seed_sha256': 's'}}
            with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'trial_w13', w13), \
                    patch.object(runner, 'trial_w2', w2), \
                    patch.object(overlap.time, 'monotonic', side_effect=[3, 7]), patch.object(overlap.time, 'sleep'):
                return overlap.trial_overlap(Context(tmp), Engine(), 'warm', lead_seconds=0)['paired_inputs']
        ctrs, orbstack = record('sha256:config'), record('sha256:manifest')
        self.assertEqual(ctrs, orbstack)
        self.assertEqual(ctrs['transfer']['api_config'], 'sha256:c')

    def test_the_record_carries_the_engine_resources_of_the_measured_window(self):
        resources = {'cpu_seconds_est': 12.0, 'phases': {'workload': {'foreign_cpu_cores': 0.7,
                                                                      'operation_wall_seconds': 9}}}
        def w13(ctx, engine, state, **kwargs):
            ctx.overlap_transfer_observer('start', 0, None)
            ctx.overlap_transfer_observer('end', 8, {'streams': [receipt()]})
            return {'metrics': {}, 'correctness': {'ok': True}, 'validation_errors': []}
        def w2(ctx, engine, state, *args, **kwargs):
            with ctx.overlap_workload():
                pass
            return {'metrics': {}, 'correctness': {'ok': True}, 'validation_errors': [], 'resources': resources}
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'trial_w13', w13), \
                patch.object(runner, 'trial_w2', w2), \
                patch.object(overlap.time, 'monotonic', side_effect=[3, 7]), patch.object(overlap.time, 'sleep'):
            rec = overlap.trial_overlap(Context(tmp), Engine(), 'warm', lead_seconds=0)
        self.assertEqual(rec['resources'], resources)

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
                 patch.object(runner, 'resource_phase', return_value=__import__('contextlib').nullcontext()), \
                 patch.object(runner, 'pinned_api_image', return_value=('image', {'api_config': 'sha256:c'})):
                rec = transfer.trial_w13(ctx, engine, 'warm', size_bytes=10, repeats=1)
            self.assertTrue(rec['correctness']['ok'], rec['validation_errors'])
            self.assertEqual(rec['paired_inputs']['api_config'], 'sha256:c')
            self.assertEqual(rec['paired_inputs']['sha256_per_stream'], 'hash')
            self.assertEqual(rec['metrics']['fixture_version'], 'w13-v3')
            creations = [c for c in engine.commands if c[:2] == ['network', 'create'] or c[:2] == ['run', '-d']]
            self.assertEqual(len(creations), 3)
            self.assertTrue(all('dev.ctrs.campaign.run=test-run' in c for c in creations))
            self.assertEqual(len([c for c in engine.commands if 'inspect' in c]), 3)
            self.assertEqual(len([c for c in engine.commands if c[0] == 'rm' or c[:2] == ['network', 'rm']]), 3)


if __name__ == '__main__':
    unittest.main()
