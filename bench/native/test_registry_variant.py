import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

import registry_portfolio as registry
import registry_variant as variant


def digest(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def tar_bytes(name):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w', format=tarfile.PAX_FORMAT) as tar:
        item = tarfile.TarInfo(name)
        item.uid, item.gid, item.mode, item.mtime = 42, 23, 0o751, 123
        item.pax_headers = {'comment': 'preserve this metadata'}
        body = b'payload:' + name.encode()
        item.size = len(body)
        tar.addfile(item, io.BytesIO(body))
        link = tarfile.TarInfo('link')
        link.type = tarfile.SYMTYPE
        link.linkname = name
        tar.addfile(link)
        whiteout = tarfile.TarInfo('.wh.removed')
        tar.addfile(whiteout, io.BytesIO())
    return stream.getvalue()


class VariantTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[2] / '.work' / 'tmp'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        (self.source / 'blobs' / 'sha256').mkdir(parents=True)
        (self.source / 'oci-layout').write_text('{"imageLayoutVersion":"1.0.0"}')
        self.raw = [tar_bytes('shared'), tar_bytes('first'), tar_bytes('second')]
        self.layers = [self.blob(gzip.compress(raw, mtime=0), 'application/vnd.oci.image.layer.v1.tar+gzip') for raw in self.raw]
        self.contract = {'schema_version': 1, 'fixture_version': 'w8-v2-common-portfolio', 'images': {}}
        entries = []
        self.configs = {}
        for name, indexes in [('app', [0, 1]), ('tool', [0, 2])]:
            config = {'os': 'linux', 'architecture': 'arm64', 'config': {'Cmd': ['run', name], 'Env': ['X=1'], 'Labels': {'existing': 'value'}}, 'rootfs': {'type': 'layers', 'diff_ids': [digest(self.raw[i]) for i in indexes]}}
            self.configs[name] = config
            cd = self.blob(variant._encoded(config), 'application/vnd.oci.image.config.v1+json')
            manifest = {'schemaVersion': 2, 'config': cd, 'layers': [self.layers[i] for i in indexes]}
            md = self.blob(variant._encoded(manifest), registry.OCI_MANIFEST)
            md['annotations'] = {'org.opencontainers.image.ref.name': name}
            entries.append(md)
            self.contract['images'][name] = {'layout_reference': name, 'manifest': md['digest'], 'config': cd['digest'], 'layer_count': 2, 'diff_ids': config['rootfs']['diff_ids']}
        (self.source / 'index.json').write_bytes(variant._encoded({'schemaVersion': 2, 'manifests': entries}))

    def blob(self, data, media):
        d = digest(data)
        (self.source / 'blobs' / 'sha256' / d[7:]).write_bytes(data)
        return {'digest': d, 'size': len(data), 'mediaType': media}

    def snapshot(self, root):
        return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}

    def test_deterministic_unique_shared_and_preserved(self):
        before = self.snapshot(self.source)
        for path in self.source.rglob('*'):
            if path.is_file():
                path.chmod(0o444)
        a = variant.prepare_variant(self.source, self.contract, self.root / 'a', b'seed')
        b = variant.prepare_variant(self.source, self.contract, self.root / 'b', b'seed')
        c = variant.prepare_variant(self.source, self.contract, self.root / 'c', b'other')
        self.assertEqual(a, b)
        self.assertEqual(self.snapshot(self.root / 'a'), self.snapshot(self.root / 'b'))
        self.assertEqual(before, self.snapshot(self.source))
        self.assertEqual(len(a['layers']), 3)
        for left, right in zip(a['layers'], c['layers']):
            self.assertNotEqual(left['digest'], left['source_digest'])
            self.assertNotEqual(left['diff_id'], left['source_diff_id'])
            self.assertNotEqual(left['digest'], right['digest'])
            self.assertNotEqual(left['diff_id'], right['diff_id'])
            source = self.raw[[digest(x) for x in self.raw].index(left['source_diff_id'])]
            output = gzip.decompress((self.root / 'a' / 'blobs' / 'sha256' / left['digest'][7:]).read_bytes())
            with tarfile.open(fileobj=io.BytesIO(source)) as tar:
                original = list(tar)
                end = tar.offset
            self.assertEqual(output[:end], source[:end])
            self.assertEqual(digest(output), left['diff_id'])
            with tarfile.open(fileobj=io.BytesIO(output)) as tar:
                members = list(tar)
                self.assertEqual([(m.name, m.type, m.linkname, m.uid, m.gid, m.mode, m.mtime, m.pax_headers) for m in members[:-1]], [(m.name, m.type, m.linkname, m.uid, m.gid, m.mode, m.mtime, m.pax_headers) for m in original])
                self.assertEqual(members[-1].name, left['marker'])
        self.assertEqual(a['images']['app']['layers'][0]['digest'], a['images']['tool']['layers'][0]['digest'])
        portfolio = registry.prepare_layout(self.root / 'a', {'app': 'app', 'tool': 'tool'})
        for name, image in a['images'].items():
            config = json.loads(portfolio.routes[(name, 'blobs', image['config'])][2].metadata())
            expected = copy.deepcopy(self.configs[name])
            expected['rootfs']['diff_ids'] = image['diff_ids']
            expected['config']['Labels'][variant.LABEL] = 'w8-v3'
            self.assertEqual(config, expected)

    def test_corruption_and_invalid_input_are_rejected(self):
        with self.assertRaises(ValueError):
            variant.prepare_variant(self.source, self.contract, self.root / 'badseed', b'')
        wrong = copy.deepcopy(self.contract)
        wrong['images']['app']['diff_ids'][0] = 'sha256:' + '0' * 64
        with self.assertRaises(ValueError):
            variant.prepare_variant(self.source, wrong, self.root / 'badpin', b'x')
        blob = self.source / 'blobs' / 'sha256' / self.layers[0]['digest'][7:]
        blob.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            variant.prepare_variant(self.source, self.contract, self.root / 'badblob', b'x')
        self.assertFalse((self.root / 'badblob').exists())

    def test_uncompressed_source_tar(self):
        raw = self.raw[0]
        descriptor = self.blob(raw, 'application/vnd.oci.image.layer.v1.tar')
        (self.root / 'blobs' / 'sha256').mkdir(parents=True)
        result = variant._layer(registry._blob(self.source, descriptor), descriptor['mediaType'], digest(raw), hashlib.sha256(b'x').hexdigest(), self.root)
        output = gzip.decompress((self.root / 'blobs' / 'sha256' / result['digest'][7:]).read_bytes())
        self.assertEqual(digest(output), result['diff_id'])
        with tarfile.open(fileobj=io.BytesIO(output)) as tar:
            self.assertEqual([m.name for m in tar], ['shared', 'link', '.wh.removed', result['marker']])

    def test_marker_collision_and_malformed_tar_rejected(self):
        seed_hash = hashlib.sha256(b'x').hexdigest()
        raw = tar_bytes('ordinary')
        source_diff = digest(raw)
        marker = '.ctrs-w8-v3-' + hashlib.sha256((seed_hash + source_diff).encode()).hexdigest()
        collision = tar_bytes(marker)
        for content, expected_diff, message in ((collision, source_diff, 'diff ID mismatch'),
                                                (b'not a tar', digest(b'not a tar'), 'truncated tar header')):
            descriptor = self.blob(gzip.compress(content, mtime=0), self.layers[0]['mediaType'])
            with self.assertRaisesRegex(ValueError, message):
                variant._layer(registry._blob(self.source, descriptor), descriptor['mediaType'], expected_diff, seed_hash, self.root)
        with self.assertRaisesRegex(ValueError, 'collision'):
            self._collision_check()

    def _collision_check(self):
        raw = tar_bytes('ordinary')
        source_diff = digest(raw)
        seed_hash = hashlib.sha256(b'x').hexdigest()
        marker = '.ctrs-w8-v3-' + hashlib.sha256((seed_hash + source_diff).encode()).hexdigest()
        content = tar_bytes(marker)
        descriptor = self.blob(gzip.compress(content, mtime=0), self.layers[0]['mediaType'])
        blob = registry._blob(self.source, descriptor)
        content_diff = digest(content)
        marker_input = (seed_hash + content_diff).encode()
        original = variant.hashlib.sha256
        class FakeHash:
            def hexdigest(self):
                return marker.removeprefix('.ctrs-w8-v3-')
        from unittest.mock import patch
        with patch.object(variant.hashlib, 'sha256', side_effect=lambda data=b'': FakeHash() if data == marker_input else original(data)):
            variant._layer(blob, descriptor['mediaType'], content_diff, seed_hash, self.root)

    def test_actual_diff_id_mismatch_is_rejected(self):
        raw = self.raw[0]
        changed = bytearray(raw)
        changed[512] ^= 1
        layer = self.blob(gzip.compress(bytes(changed), mtime=0), self.layers[0]['mediaType'])
        for name in self.contract['images']:
            image = self.contract['images'][name]
            index = json.loads((self.source / 'index.json').read_bytes())
            entry = next(d for d in index['manifests'] if d['annotations']['org.opencontainers.image.ref.name'] == name)
            manifest = json.loads((self.source / 'blobs' / 'sha256' / entry['digest'][7:]).read_bytes())
            manifest['layers'][0] = layer
            new = self.blob(variant._encoded(manifest), registry.OCI_MANIFEST)
            new['annotations'] = entry['annotations']
            index['manifests'][index['manifests'].index(entry)] = new
            (self.source / 'index.json').write_bytes(variant._encoded(index))
            image['manifest'] = new['digest']
        with self.assertRaisesRegex(ValueError, 'diff ID mismatch'):
            variant.prepare_variant(self.source, self.contract, self.root / 'bad', b'x')
        self.assertFalse((self.root / 'bad').exists())


if __name__ == '__main__':
    unittest.main()
