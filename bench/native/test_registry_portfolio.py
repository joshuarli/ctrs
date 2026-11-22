import hashlib
import importlib.util
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import threading
import urllib.request
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import registry_portfolio as registry


def encoded(value):
    return json.dumps(value, separators=(',', ':')).encode()


class Connection:
    def __init__(self, request):
        self.input = io.BytesIO(request)
        self.output = io.BytesIO()

    def makefile(self, mode, *args, **kwargs):
        return self.input if 'r' in mode else self.output

    def sendall(self, data):
        self.output.write(data)


class Server:
    server_name = 'localhost'
    server_port = 1234


class RegistryTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[2] / '.work' / 'tmp'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'blobs' / 'sha256').mkdir(parents=True)
        (self.root / 'oci-layout').write_text('{"imageLayoutVersion":"1.0.0"}')
        self.layers = [self.blob(value, 'application/vnd.oci.image.layer.v1.tar') for value in (b'first layer', b'second layer')]
        self.diff_ids = [layer['digest'] for layer in self.layers]
        config = self.blob(encoded({'os': 'linux', 'architecture': 'arm64', 'rootfs': {'type': 'layers', 'diff_ids': self.diff_ids}}), 'application/vnd.oci.image.config.v1+json')
        self.config = config
        manifest = encoded({'schemaVersion': 2, 'config': config, 'layers': self.layers})
        self.manifest = self.blob(manifest, registry.OCI_MANIFEST)
        arm = {**self.manifest, 'platform': {'os': 'linux', 'architecture': 'arm64', 'variant': 'v8'}}
        index = self.blob(encoded({'schemaVersion': 2, 'manifests': [arm]}), registry.OCI_INDEX)
        index['annotations'] = {'org.opencontainers.image.ref.name': 'app'}
        (self.root / 'index.json').write_bytes(encoded({'schemaVersion': 2, 'manifests': [index]}))
        self.manifest_bytes = manifest

    def blob(self, data, media):
        digest = hashlib.sha256(data).hexdigest()
        (self.root / 'blobs' / 'sha256' / digest).write_bytes(data)
        return {'mediaType': media, 'digest': 'sha256:' + digest, 'size': len(data)}

    def request(self, portfolio, method, path):
        connection = Connection(f'{method} {path} HTTP/1.1\r\nHost: localhost\r\n\r\n'.encode())
        portfolio.handler()(connection, ('127.0.0.1', 1234), Server())
        return connection.output.getvalue().split(b'\r\n\r\n', 1)

    def test_restore_requires_the_exact_worker_blob_bytes(self):
        path = Path(__file__).parent / 'fixtures/w11-v2/restore.py'
        spec = importlib.util.spec_from_file_location('w11_restore', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        archive = self.root / 'worker.tar'
        output = self.root / 'restored'
        pin = {'manifest': self.manifest['digest'], 'config': self.config['digest'],
               'diff_ids': self.diff_ids, 'layout_reference': 'v2', 'repository': 'np-w11/events'}
        layer = self.root / 'blobs/sha256' / self.layers[0]['digest'][7:]
        first = layer.read_bytes()

        def save():
            with tarfile.open(archive, mode='w') as stream:
                stream.add(self.root / 'blobs', arcname='blobs')

        layer.write_bytes(b'x' * len(first))
        save()
        with self.assertRaisesRegex(ValueError, 'OCI blob integrity failure'):
            module.restore(archive, output, pin)
        self.assertFalse(output.exists())

        layer.unlink()
        layer.symlink_to(self.root / 'index.json')
        save()
        with self.assertRaisesRegex(ValueError, 'invalid worker archive entry'):
            module.restore(archive, output, pin)
        self.assertFalse(output.exists())

        layer.unlink()
        layer.write_bytes(first)
        save()
        layout = module.restore(archive, output, pin)
        worker = registry.prepare_layout(layout, {pin['repository']: 'v2'})
        self.assertEqual(worker.manifests, {pin['repository']: pin['manifest']})
        with self.assertRaises(FileExistsError):
            module.restore(archive, output, pin)

    def test_native_amd64_is_explicit_and_does_not_admit_arm_images(self):
        with self.assertRaisesRegex(ValueError, 'linux/amd64'):
            registry.prepare_layout(self.root, {'linux/app': 'app'}, architecture='amd64')
        config = self.blob(encoded({'os': 'linux', 'architecture': 'amd64',
            'rootfs': {'type': 'layers', 'diff_ids': self.diff_ids}}), 'application/vnd.oci.image.config.v1+json')
        manifest = self.blob(encoded({'schemaVersion': 2, 'config': config, 'layers': self.layers}), registry.OCI_MANIFEST)
        manifest['annotations'] = {'org.opencontainers.image.ref.name': 'native'}
        (self.root / 'index.json').write_bytes(encoded({'schemaVersion': 2, 'manifests': [manifest]}))
        contract = {'schema_version': 1, 'fixture_version': 'w8-v6-common-portfolio',
                    'images': {'linux/app': {'layout_reference': 'native', 'manifest': manifest['digest'],
                                            'config': config['digest'], 'layer_count': 2, 'diff_ids': self.diff_ids}}}
        native = registry.prepare_pinned_portfolio(self.root, contract, architecture='amd64')
        self.assertEqual(native.manifests, {'linux/app': manifest['digest']})
        with self.assertRaisesRegex(ValueError, 'linux/arm64'):
            registry.prepare_pinned_portfolio(self.root, contract)
        with self.assertRaisesRegex(ValueError, 'empty pinned'):
            registry.prepare_pinned_portfolio(self.root, {**contract, 'images': {}}, architecture='amd64')
        with self.assertRaisesRegex(ValueError, 'unsupported portfolio architecture'):
            registry.prepare_layout(self.root, {'linux/app': 'native'}, architecture='other')

    def test_both_repositories_serve_identical_verified_manifest_and_blobs(self):
        portfolio = registry.prepare_layout(self.root, {'ctrs/app': 'app', 'orb/app': 'app'})
        self.assertEqual(portfolio.manifests, {'ctrs/app': self.manifest['digest'], 'orb/app': self.manifest['digest']})
        for name in portfolio.manifests:
            headers, body = self.request(portfolio, 'GET', f'/v2/{name}/manifests/{self.manifest["digest"]}')
            self.assertIn(b'200 OK', headers)
            self.assertIn(self.manifest['digest'].encode(), headers)
            self.assertEqual(body, self.manifest_bytes)
            for layer, expected in zip(self.layers, (b'first layer', b'second layer')):
                headers, body = self.request(portfolio, 'GET', f'/v2/{name}/blobs/{layer["digest"]}')
                self.assertIn(b'200 OK', headers)
                self.assertEqual(body, expected)
        self.assertEqual([event['bytes'] for event in portfolio.transfers], [len(self.manifest_bytes), 11, 12] * 2)
        headers, body = self.request(portfolio, 'HEAD', f'/v2/ctrs/app/blobs/{self.layers[0]["digest"]}')
        self.assertIn(b'200 OK', headers)
        self.assertEqual(body, b'')
        self.assertEqual(portfolio.transfers[-1]['bytes'], 0)
        self.assertEqual(portfolio.transfers[-1]['method'], 'HEAD')
        self.assertIn(b'404', self.request(portfolio, 'GET', '/v2/other/app/blobs/' + self.layers[0]['digest'])[0])

    def test_corruption_and_symlink_are_rejected(self):
        blob = self.root / 'blobs' / 'sha256' / self.layers[0]['digest'][7:]
        blob.write_bytes(b'wrong data!')
        with self.assertRaisesRegex(ValueError, 'integrity'):
            registry.prepare_layout(self.root, {'app': 'app'})
        blob.unlink()
        blob.symlink_to(self.root / 'oci-layout')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            registry.prepare_layout(self.root, {'app': 'app'})

    def test_ambiguous_arm64_and_wrong_config_are_rejected(self):
        config = self.blob(encoded({'os': 'linux', 'architecture': 'amd64'}), 'config')
        bad_manifest = self.blob(encoded({'schemaVersion': 2, 'config': config, 'layers': self.layers}), registry.OCI_MANIFEST)
        bad_manifest['platform'] = {'os': 'linux', 'architecture': 'arm64'}
        index = self.blob(encoded({'schemaVersion': 2, 'manifests': [bad_manifest]}), registry.OCI_INDEX)
        index['annotations'] = {'org.opencontainers.image.ref.name': 'app'}
        (self.root / 'index.json').write_bytes(encoded({'schemaVersion': 2, 'manifests': [index]}))
        with self.assertRaisesRegex(ValueError, 'config'):
            registry.prepare_layout(self.root, {'app': 'app'})
        index = self.blob(encoded({'schemaVersion': 2, 'manifests': [bad_manifest, bad_manifest]}), registry.OCI_INDEX)
        index['annotations'] = {'org.opencontainers.image.ref.name': 'app'}
        (self.root / 'index.json').write_bytes(encoded({'schemaVersion': 2, 'manifests': [index]}))
        with self.assertRaisesRegex(ValueError, 'one linux/arm64'):
            registry.prepare_layout(self.root, {'app': 'app'})

    def test_real_loopback_transfer_and_mutation_rejection(self):
        portfolio = registry.prepare_layout(self.root, {'app': 'app'})
        with registry.serve(portfolio, 0) as server:
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
            thread.start()
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/v2/app/blobs/{self.layers[0]["digest"]}', timeout=2) as response:
                    self.assertEqual(response.read(), b'first layer')
                    self.assertEqual(response.headers['Docker-Content-Digest'], self.layers[0]['digest'])
            finally:
                server.shutdown()
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())
        self.assertTrue(portfolio.transfers[-1]['complete'])
        blob = self.root / 'blobs' / 'sha256' / self.layers[0]['digest'][7:]
        blob.write_bytes(b'changed-after-verification')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.request(portfolio, 'GET', f'/v2/app/blobs/{self.layers[0]["digest"]}')
        self.assertFalse(portfolio.transfers[-1]['complete'])
        self.assertEqual(portfolio.transfers[-1]['bytes'], 0)

    def test_owned_pull_cancels_after_partial_blob_and_fresh_endpoint_delivers_full_blob(self):
        import w8_cancel

        portfolio = registry.prepare_layout(self.root, {'app': 'app'})
        retry = registry.prepare_layout(self.root, {'app': 'app'})
        layer = self.layers[0]
        pause = registry.TransferPause('app', layer['digest'], timeout=3)
        path = f'/v2/app/blobs/{layer["digest"]}'
        popen = subprocess.Popen

        def launch(args, **kwargs):
            # A shell may start this suite with SIGINT ignored, and Python keeps an inherited SIG_IGN.
            script = ('import signal,sys,urllib.request; signal.signal(signal.SIGINT, signal.default_int_handler); '
                      'urllib.request.urlopen(sys.argv[1],timeout=5).read()')
            return popen([sys.executable, '-c', script, args[-1]], **kwargs)

        with registry.running_registry(portfolio, pause=pause) as server, \
                patch.object(w8_cancel.subprocess, 'Popen', side_effect=launch):
            url = f'http://127.0.0.1:{server.server_port}{path}'
            result = w8_cancel.cancel_pull(SimpleNamespace(env=os.environ.copy), url, portfolio, pause, layer, self.root)
        self.assertEqual(len(result['transfers']), 1)
        transfer = result['transfers'][0]
        self.assertEqual(transfer['bytes'], layer['size'] - 1)
        self.assertFalse(transfer['complete'])
        self.assertGreaterEqual(result['peer_disconnected_monotonic'], result['signal_sent_monotonic'])
        with registry.running_registry(retry) as server:
            with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}{path}', timeout=2) as response:
                self.assertEqual(response.read(), b'first layer')
        self.assertTrue(retry.transfers[-1]['complete'])

    def test_partial_delivery_ended_before_interruption_is_rejected(self):
        import w8_cancel

        portfolio = registry.prepare_layout(self.root, {'app': 'app'})
        layer = self.layers[0]
        pause = registry.TransferPause('app', layer['digest'])
        pause.started.set()
        pause.finished.set()
        child = Mock()
        child.poll.return_value = None
        with patch.object(w8_cancel.subprocess, 'Popen', return_value=child):
            with self.assertRaisesRegex(ValueError, 'ended before the planned interruption'):
                w8_cancel.cancel_pull(SimpleNamespace(env=os.environ.copy), 'unused', portfolio, pause, layer, self.root)
        child.send_signal.assert_not_called()
        child.kill.assert_called_once()

    def test_pin_mismatch_cannot_silently_select_another_portfolio(self):
        image = {'layout_reference': 'app', 'manifest': self.manifest['digest'],
                 'config': self.config['digest'], 'layer_count': 2, 'diff_ids': self.diff_ids}
        contract = {'schema_version': 1, 'fixture_version': 'w8-v2-common-portfolio', 'images': {'app': image}}
        self.assertEqual(registry.prepare_pinned_portfolio(self.root, contract).manifests, {'app': self.manifest['digest']})
        for key, replacement in (('manifest', 'sha256:' + '1' * 64), ('config', 'sha256:' + '2' * 64),
                                 ('layer_count', 3), ('diff_ids', list(reversed(self.diff_ids)))):
            wrong = copy.deepcopy(contract)
            wrong['images']['app'][key] = replacement
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'differs|differ'):
                registry.prepare_pinned_portfolio(self.root, wrong)


if __name__ == '__main__':
    unittest.main()
