import subprocess
import unittest
from diagnostics import registry_variant_pilot as pilot


class VariantTransferProof(unittest.TestCase):
    def test_missing_image_requires_daemon_absence_response(self):
        absent = subprocess.CompletedProcess([], 1, '[]\n', 'Error response from daemon: No such image: sha256:abc\n')
        pilot.require_missing_image(absent)
        for cp in (subprocess.CompletedProcess([], 0, '[{}]', ''),
                   subprocess.CompletedProcess([], 1, '', 'Cannot connect to the Docker daemon'),
                   subprocess.CompletedProcess([], 1, '', 'permission denied')):
            with self.subTest(cp=cp), self.assertRaises(ValueError):
                pilot.require_missing_image(cp)

    def test_shared_layer_transfer_counts_once_across_repository_pulls(self):
        shared = {'digest': 'sha256:shared', 'size': 100}
        other = {'digest': 'sha256:other', 'size': 50}
        transfers = [{'digest': 'sha256:shared', 'bytes': 100, 'method': 'GET', 'complete': True}]
        pilot.require_layers_transferred([shared], transfers)
        with self.assertRaises(ValueError):
            pilot.require_layers_transferred([shared, other], transfers)
        transfers.append({'digest': 'sha256:other', 'bytes': 50, 'method': 'GET', 'complete': True})
        pilot.require_layers_transferred([shared, other], transfers)

    def test_failed_partial_and_head_requests_do_not_establish_complete_transfer(self):
        layer = {'digest': 'sha256:layer', 'size': 100}
        for changes in ({'complete': False}, {'method': 'HEAD'}, {'bytes': 99}, {'digest': 'sha256:foreign'}):
            row = {'digest': layer['digest'], 'bytes': 100, 'method': 'GET', 'complete': True} | changes
            with self.subTest(row=row), self.assertRaises(ValueError):
                pilot.require_layers_transferred([layer], [row])


if __name__ == '__main__':
    unittest.main()
