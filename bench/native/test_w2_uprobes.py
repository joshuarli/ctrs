from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent / 'diagnostics'))
import w2_uprobes_guest as trace

TAG = 'npu0123456789ab'
REAL_IDENTITY = trace.library_identity


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.trace = root / 'trace'
        self.state = root / 'state'
        (self.trace / 'instances').mkdir(parents=True)
        for name in ('uprobe_events', 'kprobe_events'):
            (self.trace / name).write_text('')
        self.identity = {'path': str(trace.LIBRARY), 'stat': [1, 2, trace.LIBRARY_SIZE, 3, 4],
                         'sha256': trace.LIBRARY_SHA256}
        for name, value in (('TRACE', self.trace), ('STATE', self.state)):
            p = patch.object(trace, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(trace, 'library_identity', return_value=self.identity)
        self.pin = p.start()
        self.addCleanup(p.stop)
        p = patch.object(trace, '_write', side_effect=self.write)
        self.writer = p.start()
        self.addCleanup(p.stop)
        p = patch.object(Path, 'mkdir', autospec=True, side_effect=self.mkdir)
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(Path, 'rmdir', autospec=True, side_effect=self.rmdir)
        p.start()
        self.addCleanup(p.stop)

    def mkdir(self, path, mode=0o777, parents=False, exist_ok=False):
        import os
        if parents:
            os.makedirs(path, mode=mode, exist_ok=exist_ok)
        else:
            os.mkdir(path, mode)
        if path == self.trace / 'instances' / TAG:
            for name, content in (('tracing_on', '0'), ('trace_clock', '[mono]'),
                                  ('buffer_size_kb', '0'), ('trace', 'raw trace')):
                (path / name).write_text(content)
            (path / 'per_cpu' / 'cpu0').mkdir(parents=True)
            (path / 'per_cpu' / 'cpu0' / 'stats').write_text(
                'overrun: 0\ncommit overrun: 0\ndropped events: 0\n')
            for event in trace.event_paths(TAG):
                event_dir = path / 'events' / event
                event_dir.mkdir(parents=True, exist_ok=True)
                for name, value in (('enable', '0'), ('filter', ''), ('format', 'format')):
                    (event_dir / name).write_text(value)

    def rmdir(self, path):
        import shutil
        if path == self.trace / 'instances' / TAG:
            shutil.rmtree(path)
        else:
            import os
            os.rmdir(path)

    def write(self, path, value):
        value = str(value)
        if path.parent == self.trace and path.name in ('kprobe_events', 'uprobe_events'):
            lines = path.read_text().splitlines()
            if value.startswith('-:'):
                name = value[2:]
                lines = [line for line in lines if line.split()[0].split(':', 1)[1] != name]
            else:
                lines.append(value)
            path.write_text('\n'.join(lines) + '\n')
        elif path.name == 'trace_clock':
            path.write_text('[mono]')
        else:
            path.write_text(value)

    def profiles(self):
        (self.trace / 'kprobe_profile').write_text(
            f'{TAG}_futex 10 0\n{TAG}_futex_ret 10 0\nforeign 0 1\n')
        (self.trace / 'uprobe_profile').write_text(''.join(
            f'{trace.LIBRARY} {TAG}_{name} 2\n' for name in ('save', 'save_ret', 'restore', 'restore_ret')))

    def test_validation_and_filters(self):
        for bad in ('npu0123456789a', 'npu0123456789AB', 'npu0123456789ab;'):
            with self.assertRaises(ValueError):
                trace.validate_tag(bad)
        for bad in ('0', '01', '1,1', '-1', '1,', ',1', '4194305', ','.join(map(str, range(1, 130)))):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                trace.parse_tids(bad)
        trace.setup(TAG, '12,34')
        for event in trace.event_paths(TAG):
            self.assertEqual((self.trace / 'instances' / TAG / 'events' / event / 'filter').read_text(),
                             'common_pid == 12 || common_pid == 34')

    def test_lifecycle_and_profile_rows(self):
        trace.setup(TAG, '12,34')
        trace.start(TAG)
        self.profiles()
        result = trace.stop(TAG)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['raw_trace'], 'raw trace')
        self.assertEqual(len(result['profiles']['uprobe']['rows']), 4)
        self.assertNotIn('missed', json.dumps(result['profiles']['uprobe']))
        with self.assertRaisesRegex(RuntimeError, 'cannot be restarted'):
            trace.start(TAG)
        trace.cleanup(TAG)
        self.assertFalse((self.state / (TAG + '.json')).exists())
        self.assertEqual((self.trace / 'uprobe_events').read_text().strip(), '')

    def test_pin_and_adoption_fail_before_mutation(self):
        self.pin.side_effect = RuntimeError('wrong library')
        with self.assertRaisesRegex(RuntimeError, 'wrong library'):
            trace.setup(TAG, '1')
        self.writer.assert_not_called()
        self.pin.side_effect = None
        (self.trace / 'uprobe_events').write_text(f'p:{TAG}/foreign /x:0x0\n')
        with self.assertRaisesRegex(RuntimeError, 'refuse adoption'):
            trace.setup(TAG, '1')
        self.writer.assert_not_called()

    def test_real_library_pin_rejects_wrong_file(self):
        path = Path(self.tmp.name) / 'library'
        path.write_bytes(b'wrong')
        with patch.object(trace, 'LIBRARY', path), patch.object(trace, 'library_identity', REAL_IDENTITY):
            with self.assertRaisesRegex(RuntimeError, 'digest mismatch'):
                trace.setup(TAG, '1')
        self.writer.assert_not_called()

    def test_changed_definition_refuses_cleanup_before_any_mutation(self):
        trace.setup(TAG, '1')
        path = self.trace / 'kprobe_events'
        path.write_text(path.read_text().replace('__arm64_sys_futex', '__arm64_sys_read', 1))
        self.writer.reset_mock()
        with self.assertRaisesRegex(RuntimeError, 'definitions changed'):
            trace.cleanup(TAG)
        self.writer.assert_not_called()

    def test_changed_inode_blocks_start_but_not_cleanup(self):
        trace.setup(TAG, '1')
        self.pin.return_value = dict(self.identity, stat=[1, 9, trace.LIBRARY_SIZE, 3, 4])
        self.writer.reset_mock()
        with self.assertRaisesRegex(RuntimeError, 'inode changed'):
            trace.start(TAG)
        self.writer.assert_not_called()
        trace.cleanup(TAG)

    def test_stop_rejects_missing_or_loss_and_profiles(self):
        trace.setup(TAG, '1')
        trace.start(TAG)
        self.profiles()
        stats = self.trace / 'instances' / TAG / 'per_cpu' / 'cpu0' / 'stats'
        stats.write_text('overrun: 1\ncommit overrun: 0\ndropped events: 0\n')
        (self.trace / 'uprobe_profile').write_text('')
        (self.trace / 'kprobe_profile').write_text(f'{TAG}_futex 1 1\n')
        result = trace.stop(TAG)
        self.assertEqual(result['status'], 'invalid')
        self.assertTrue(any('overrun' in e for e in result['errors']))
        self.assertTrue(any('profile' in e for e in result['errors']))
        trace.cleanup(TAG)


if __name__ == '__main__':
    unittest.main()
