import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from diagnostics import storage_space_guest, storage_space_pilot


class StorageSpace(unittest.TestCase):
    def test_relation_enospc_accepts_authoritative_errors_and_rejects_temp_spill(self):
        relation = 'ERROR: 53100: could not extend file "base/16384/16405": No space left on device'
        temporary = 'ERROR: 53100: could not write to file "base/pgsql_tmp/pgsql_tmp65.0": No space left on device'
        wal = 'PANIC: could not write file "pg_wal/00000001": No space left on device'
        self.assertTrue(storage_space_pilot.relation_enospc(1, relation))
        self.assertTrue(storage_space_pilot.relation_enospc(1, wal))
        self.assertFalse(storage_space_pilot.relation_enospc(1, temporary))
        self.assertFalse(storage_space_pilot.relation_enospc(0, relation))
        self.assertFalse(storage_space_pilot.relation_enospc(1, 'connection failed'))
        self.assertFalse(storage_space_pilot.relation_enospc(1, 'ERROR in base/16384: permission denied'))

    def test_guest_rejects_unknown_mode_before_any_path_effect(self):
        program = Path(storage_space_guest.__file__)
        result = subprocess.run([sys.executable, '-O', str(program), 'typo'], capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('require allocation or enospc mode', result.stderr)
        self.assertNotIn('/fill/reservation', result.stderr)

    def test_offline_help_and_bad_stage_do_not_start_engines(self):
        program = Path(storage_space_pilot.__file__)
        env = os.environ.copy()
        env['PATH'] = '/nonexistent'
        for arguments in ([], ['-h'], ['--help']):
            result = subprocess.run([sys.executable, str(program), *arguments], env=env, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('--portfolio-archive', result.stdout)
            self.assertIn('PostgreSQL relation ENOSPC', result.stdout)
        result = subprocess.run([sys.executable, str(program), '--stage', 'typo'], env=env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn('invalid choice', result.stderr)

class ReservationFaults(unittest.TestCase):
    def test_guard_releases_during_allocation_on_growth_or_low_free_space(self):
        from unittest.mock import Mock
        baseline = {'allocated_bytes': 100}
        for snapshot in (
            {'status': 'ok', 'allocated_bytes': 110, 'files': [{'filesystem_free_bytes': 3 << 30}]},
            {'status': 'ok', 'allocated_bytes': 100, 'files': [{'filesystem_free_bytes': (2 << 30) - 1}]},
        ):
            with self.subTest(snapshot=snapshot):
                holder = Mock()
                frame = Mock(side_effect=[{'event': 'progress'}, {'event': 'progress'}])
                healthy = {'status': 'ok', 'allocated_bytes': 100, 'files': [{'filesystem_free_bytes': 3 << 30}]}
                snapshots = iter([healthy, snapshot])
                with self.assertRaises(ValueError):
                    storage_space_pilot.await_reservation(holder, frame, lambda: next(snapshots), baseline, 8)
                self.assertEqual([call.args[0] for call in holder.stdin.write.call_args_list], ['CONTINUE\n', 'RELEASE\n'])
                holder.stdin.close.assert_called_once_with()
                self.assertEqual(frame.call_count, 2)

    def test_cleanup_snapshot_failure_still_stops_closes_and_persists_failure(self):
        from unittest.mock import Mock
        result = {'correctness': True, 'cleanup_errors': []}
        stop, close, persist = Mock(), Mock(), Mock()
        def fail_snapshot():
            raise OSError('receipt failed')
        storage_space_pilot.finish_cleanup(result, fail_snapshot, stop, close, persist)
        stop.assert_called_once_with()
        close.assert_called_once_with()
        persist.assert_called_once_with(result)
        self.assertFalse(result['correctness'])
        self.assertIn('receipt failed', result['cleanup_errors'][0])

    def test_guest_releases_before_second_allocation_when_host_requests_it(self):
        import io
        from types import SimpleNamespace
        from unittest.mock import patch
        fs = SimpleNamespace(f_frsize=4096, f_blocks=100000, f_bfree=100000, f_bavail=100000)
        stat = SimpleNamespace(st_rdev=7, st_dev=7, st_ino=42)
        file_stat = SimpleNamespace(st_size=0, st_blocks=0)
        output = io.StringIO()
        with (patch.object(sys, 'argv', ['guest', 'enospc']),
              patch.object(sys, 'platform', 'linux'),
              patch.object(sys, 'stdin', io.StringIO('RELEASE\n')),
              patch.object(sys, 'stdout', output),
              patch.object(storage_space_guest.os, 'uname', return_value=SimpleNamespace(machine='aarch64')),
              patch.object(storage_space_guest.os, 'open', return_value=9),
              patch.object(storage_space_guest.os, 'close') as close,
              patch.object(storage_space_guest.os, 'statvfs', return_value=fs),
              patch.object(storage_space_guest.os, 'stat', return_value=stat),
              patch.object(storage_space_guest.os, 'fstat', return_value=file_stat),
              patch.object(storage_space_guest.os, 'posix_fallocate', create=True) as allocate,
              patch.object(storage_space_guest.signal, 'signal'),
              patch.object(storage_space_guest.signal, 'alarm'),
              patch.object(storage_space_guest.select, 'select', return_value=([sys.stdin], [], [])),
              patch.object(Path, 'open', side_effect=lambda *args, **kwargs: io.BytesIO(bytes(1144))),
              patch.object(Path, 'unlink') as unlink):
            storage_space_guest.main()
        self.assertEqual(allocate.call_count, 1)
        self.assertEqual([json.loads(line)['event'] for line in output.getvalue().splitlines()],
                         ['progress', 'released'])
        unlink.assert_called_once_with(missing_ok=True)
        close.assert_called_once_with(9)


if __name__ == '__main__':
    unittest.main()
