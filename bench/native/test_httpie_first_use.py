import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

import httpie_first_use


class HttpieInputTests(unittest.TestCase):
    def write_archive(self, path, arch='arm64', image_count=1):
        diff_id = 'sha256:' + 'a' * 64
        config = json.dumps({'os': 'linux', 'architecture': arch,
                             'rootfs': {'diff_ids': [diff_id]}}).encode()
        manifest = json.dumps([{'Config': 'config.json', 'Layers': ['layer.tar']}] * image_count)
        with tarfile.open(path, 'w') as archive:
            for name, data in (('manifest.json', manifest.encode()), ('config.json', config),
                               ('layer.tar', b'layer bytes')):
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
        return diff_id, config

    def test_freeze_retains_exact_archive_config_and_ordered_diff_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'httpie.tar'
            diff_id, config = self.write_archive(path)
            identity = httpie_first_use.archive_identity(path)
            self.assertEqual(identity, {'archive_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'config_sha256': 'sha256:' + hashlib.sha256(config).hexdigest(), 'diff_ids': [diff_id]})
            image = {'Id': 'sha256:' + 'c' * 64, 'Os': 'linux', 'Architecture': 'arm64',
                     'RootFS': {'Layers': [diff_id]}}
            self.assertEqual(httpie_first_use.verify_loaded_image(image, identity), image['Id'])
            image['RootFS']['Layers'].append('sha256:' + 'b' * 64)
            with self.assertRaisesRegex(ValueError, 'differs from the frozen'):
                httpie_first_use.verify_loaded_image(image, identity)

    def test_freeze_rejects_emulation_and_multi_image_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'httpie.tar'
            self.write_archive(path, arch='amd64')
            with self.assertRaisesRegex(ValueError, 'Linux ARM64'):
                httpie_first_use.archive_identity(path)
            self.write_archive(path, image_count=2)
            with self.assertRaisesRegex(ValueError, 'exactly one image'):
                httpie_first_use.archive_identity(path)
