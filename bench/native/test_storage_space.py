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


if __name__ == '__main__':
    unittest.main()
