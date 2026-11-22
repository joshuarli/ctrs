import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

import httpie_first_use


class HttpieInputTests(unittest.TestCase):
    reference = 'np-httpie-first-use:00000000-0000-0000-0000-000000000001'

    def write_archive(self, path, arch='arm64', image_count=1, tags=None):
        diff_id = 'sha256:' + 'a' * 64
        config = json.dumps({'os': 'linux', 'architecture': arch,
                             'rootfs': {'diff_ids': [diff_id]}}).encode()
        manifest = json.dumps([{'Config': 'config.json', 'Layers': ['layer.tar'],
                                'RepoTags': tags if tags is not None else [self.reference]}] * image_count)
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
                'config_sha256': 'sha256:' + hashlib.sha256(config).hexdigest(), 'diff_ids': [diff_id],
                'reference': self.reference})
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

    def test_freeze_refuses_archive_that_would_retag_shared_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'httpie.tar'
            self.write_archive(path, tags=[self.reference, 'python:3.13-slim'])
            with self.assertRaisesRegex(ValueError, 'owned campaign tag'):
                httpie_first_use.archive_identity(path)

    def test_comparison_rejects_changed_archive_even_with_same_image_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'httpie.tar'
            self.write_archive(path)
            receipt = {**httpie_first_use.archive_identity(path),
                       'expected_note': 'incremental-1:' + 'd' * 64 + '\n',
                       'orbstack_image_id': 'sha256:' + 'e' * 64}
            frozen, orb_id = httpie_first_use.frozen_input(path, receipt)
            self.assertEqual(frozen['expected_note'], receipt['expected_note'])
            self.assertEqual(orb_id, receipt['orbstack_image_id'])
            with path.open('ab') as archive:
                archive.write(b'additional archive bytes')
            with self.assertRaisesRegex(ValueError, 'differs from its freeze receipt'):
                httpie_first_use.frozen_input(path, receipt)
