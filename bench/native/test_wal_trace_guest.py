from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

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

    def test_encoded_linux_device_filter_uses_actual_dev_t_value(self):
        self.assertEqual(wal_trace.encode_dev_t('254:0'), 254 << 20)
        self.assertEqual(wal_trace.block_flush_filter(254 << 20), 'dev == 266338304 && rwbs ~ "*F*"')
        with self.assertRaises(ValueError):
            wal_trace.encode_dev_t('4096:0')

    def test_kprobe_profile_requires_both_owned_events_and_zero_misses(self):
        tag = 'npwal0123456789ab'
        profile = f'{tag}_fdatasync 8 0\n{tag}_fdatasync_ret 8 0\nforeign_probe 0 0'
        self.assertEqual(wal_trace.probe_profile_summary(profile, tag)['status'], 'ok')
        missed = profile.replace(f'{tag}_fdatasync_ret 8 0', f'{tag}_fdatasync_ret 8 1')
        self.assertEqual(wal_trace.probe_profile_summary(missed, tag)['status'], 'loss')
        self.assertEqual(wal_trace.probe_profile_summary(f'{tag}_fdatasync 8 0', tag)['status'], 'unknown')
        self.assertEqual(wal_trace.probe_profile_summary(f'{tag}_fdatasync malformed', tag)['status'], 'unknown')

    def test_changed_probe_is_never_disabled_or_removed(self):
        tag = 'npwal0123456789ab'
        with tempfile.TemporaryDirectory() as directory:
            trace, state = Path(directory) / 'trace', Path(directory) / 'state'
            instance = trace / 'instances' / tag
            instance.mkdir(parents=True)
            state.mkdir()
            definitions = wal_trace.event_definitions(tag)
            flush = 'dev == 266338304 && rwbs ~ "*F*"'
            wal_trace.marker_path(tag, state).write_text(json.dumps({
                'schema': wal_trace.SCHEMA, 'tag': tag, 'pid': 274,
                'instance': str(instance), 'definitions': definitions, 'device': '254:0',
                'device_filter_value': 266338304,
                'filters': {'fdatasync': 'common_pid == 274', 'fdatasync_ret': 'common_pid == 274',
                            'block_rq_issue': flush, 'block_rq_complete': flush},
                'scope': {'backend_pid': 274, 'device': '/dev/vda', 'device_major_minor': '254:0',
                          'device_filter_value': 266338304, 'instance': str(instance)}}))
            (trace / 'kprobe_events').write_text('\n'.join(definitions).replace(
                '__arm64_sys_fdatasync', '__arm64_sys_fsync', 1))
            for action in (wal_trace.start, wal_trace.stop, wal_trace.cleanup):
                with self.subTest(action=action.__name__), patch.object(wal_trace, '_write') as write:
                    with self.assertRaisesRegex(RuntimeError, 'definition changed'):
                        action(tag, trace=trace, state=state)
                    write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
