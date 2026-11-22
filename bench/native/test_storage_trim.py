import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from diagnostics import storage_trim_guest as trim


class TrimProbeTests(unittest.TestCase):
    def test_trims_verified_ext4_and_keeps_the_synced_sentinel(self):
        with tempfile.TemporaryDirectory() as directory:
            probe = Path(directory)
            device = probe.stat().st_dev
            mount = f'1 0 {os.major(device)}:{os.minor(device)} / {probe} rw - ext4 /dev/vda rw'

            def discard(fd, opcode, request):
                self.assertEqual(os.fstat(fd).st_dev, device)
                self.assertEqual(opcode, trim.FITRIM)
                self.assertEqual(struct.unpack('=QQQ', request), (0, (1 << 64) - 1, 0))
                struct.pack_into('=QQQ', request, 0, 0, 4096, 4096)

            with (patch.object(trim, 'PROBE', probe), patch.object(trim, 'SENTINEL', probe / 'sentinel'),
                  patch.object(Path, 'read_text', return_value=mount),
                  patch.object(trim.fcntl, 'ioctl', side_effect=discard) as ioctl):
                initial = trim.observe('seed')
                result = trim.observe('trim')
                self.assertEqual(result['discard_submitted_bytes'], 4096)
                self.assertEqual(trim.observe('sample')['sentinel_sha256'], initial['sentinel_sha256'])
                ioctl.assert_called_once()
                with patch.object(Path, 'read_text', return_value=mount.replace('/dev/vda', '/dev/vdb')):
                    with self.assertRaisesRegex(ValueError, 'unexpected trim probe mount'):
                        trim.observe('trim')
                ioctl.assert_called_once()
