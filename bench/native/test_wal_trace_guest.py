from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent / 'diagnostics'))
import wal_trace_guest as wal_trace


class WalTraceGuestTests(unittest.TestCase):
    def test_tag_and_explicit_global_backend_pid_are_strict(self):
        for tag in ('npwal0123456789a', 'npwal0123456789AB',
                    'npwal0123456789abc', 'npwal0123456789ab;id'):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                wal_trace.validate(tag, 123)
        for pid in (None, 0, 1, -2, 4194305, True, '123'):
            with self.subTest(pid=pid), self.assertRaises(ValueError):
                wal_trace.validate('npwal0123456789ab', pid)
        wal_trace.validate('npwal0123456789ab', 274)

    def test_preexisting_instance_marker_and_foreign_probe_are_never_adopted(self):
        tag = 'npwal0123456789ab'
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            trace, state = base / 'trace', base / 'state'
            (trace / 'instances' / tag).mkdir(parents=True)
            with self.assertRaisesRegex(RuntimeError, 'instance already exists'):
                wal_trace.setup(tag, 274, trace=trace, state=state)
            (trace / 'instances' / tag).rmdir()
            state.mkdir()
            wal_trace.marker_path(tag, state).write_text('{}')
            with self.assertRaisesRegex(RuntimeError, 'receipt already exists'):
                wal_trace.setup(tag, 274, trace=trace, state=state)
            wal_trace.marker_path(tag, state).unlink()
            (trace / 'instances').mkdir(parents=True, exist_ok=True)
            group = 'npwal_' + tag[5:]
            (trace / 'kprobe_events').write_text(f'p:{group}/fdatasync __arm64_sys_fdatasync\n')
            with self.assertRaisesRegex(RuntimeError, 'name already exists'):
                wal_trace.setup(tag, 274, trace=trace, state=state)
            self.assertFalse((trace / 'instances' / tag).exists())
            self.assertFalse(wal_trace.marker_path(tag, state).exists())

    def test_loss_requires_all_cpu_stats_and_zero_counters(self):
        good = '\n'.join(('entries: 12', 'overrun: 0', 'commit overrun: 0', 'dropped events: 0'))
        result = wal_trace.loss_summary({'0': good, '1': good})
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['per_cpu']['1']['dropped events'], 0)
        self.assertEqual(wal_trace.loss_summary({})['status'], 'unknown')
        self.assertEqual(wal_trace.loss_summary({'0': 'overrun: 0\ndropped events: 0'})['status'], 'unknown')
        self.assertEqual(wal_trace.loss_summary({'1': None})['status'], 'unknown')
        for stats in (good.replace('overrun: 0', 'overrun: 1'),
                      good.replace('commit overrun: 0', 'commit overrun: 2'),
                      good.replace('dropped events: 0', 'dropped events: 3')):
            with self.subTest(stats=stats):
                self.assertEqual(wal_trace.loss_summary({'0': stats})['status'], 'loss')


if __name__ == '__main__':
    unittest.main()
