"""Derive the W8 content-unique OCI portfolio from the pinned common layout."""
import argparse
import copy
import gzip
import hashlib
import json
import os
import posixpath
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import zlib

import registry_portfolio as registry


GZIP_LAYERS = {'application/vnd.oci.image.layer.v1.tar+gzip',
               'application/vnd.docker.image.rootfs.diff.tar.gzip'}
TAR_LAYERS = {'application/vnd.oci.image.layer.v1.tar',
              'application/vnd.docker.image.rootfs.diff.tar'}
LABEL = 'org.ctrs.fixture.version'
DERIVED_VERSION = 'w8-v3'
RETAINED_VERSION = 'w8-v3-retained-cancel'
CHUNK = 1024 * 1024


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def _put(root, data, descriptor):
    digest = hashlib.sha256(data).hexdigest()
    path = root / 'blobs' / 'sha256' / digest
    if not path.exists():
        path.write_bytes(data)
    result = copy.deepcopy(descriptor)
    result.update(digest='sha256:' + digest, size=len(data))
    return result


def _tar_end(raw):
    raw.seek(0)
    while True:
        block = raw.read(512)
        if len(block) != 512:
            raise ValueError('truncated tar header')
        if block == bytes(512):
            end = raw.tell() - 512
            remaining = 512
            while chunk := raw.read(CHUNK):
                remaining += len(chunk)
                if any(chunk):
                    raise ValueError('invalid tar terminal records')
            if remaining < 1024 or remaining % 512:
                raise ValueError('invalid tar terminal records')
            return end
        try:
            header = tarfile.TarInfo.frombuf(block, 'utf-8', 'surrogateescape')
        except tarfile.HeaderError as error:
            raise ValueError('invalid tar header') from error
        if header.size < 0:
            raise ValueError('invalid tar member size')
        if header.type == tarfile.XGLTYPE or header.type == tarfile.GNUTYPE_SPARSE:
            raise ValueError('unsupported global or sparse tar header')
        if header.type in (tarfile.XHDTYPE, tarfile.SOLARIS_XHDTYPE, tarfile.GNUTYPE_LONGNAME, tarfile.GNUTYPE_LONGLINK) and header.size > CHUNK:
            raise ValueError('oversized tar extension')
        left = (header.size + 511) // 512 * 512
        while left:
            chunk = raw.read(min(CHUNK, left))
            if not chunk:
                raise ValueError('truncated tar member')
            left -= len(chunk)


def _layer(blob, media, diff_id, seed_hash, root):
    if media not in GZIP_LAYERS | TAR_LAYERS:
        raise ValueError('unsupported layer media type')
    if not isinstance(diff_id, str) or not registry.DIGEST.fullmatch(diff_id):
        raise ValueError('invalid diff ID')
    marker = '.ctrs-w8-v3-' + hashlib.sha256((seed_hash + diff_id).encode()).hexdigest()
    with tempfile.TemporaryFile(dir=root) as raw:
        digest = hashlib.sha256()
        with blob.open() as source:
            reader = gzip.GzipFile(fileobj=source, mode='rb') if media in GZIP_LAYERS else source
            try:
                while chunk := reader.read(CHUNK):
                    raw.write(chunk)
                    digest.update(chunk)
            finally:
                if reader is not source:
                    reader.close()
            if registry._identity(os.fstat(source.fileno())) != blob.identity:
                raise ValueError('source layer changed during read')
        if 'sha256:' + digest.hexdigest() != diff_id:
            raise ValueError('uncompressed diff ID mismatch')
        end = _tar_end(raw)
        raw.seek(0)
        with tarfile.open(fileobj=raw, mode='r:') as archive:
            for member in archive:
                name = posixpath.normpath(member.name)
                if name.startswith('/') or name == '..' or name.startswith('../'):
                    raise ValueError('unsafe tar member path')
                if (name == marker or name == '.wh.' + marker or member.sparse is not None or
                        any(k == 'size' or k.startswith(('GNU.sparse', 'SCHILY.realsize')) for k in member.pax_headers)):
                    raise ValueError('marker collision or unsupported sparse layer')
                if member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE,
                                       tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE,
                                       tarfile.BLKTYPE, tarfile.FIFOTYPE):
                    raise ValueError('unsupported tar member')
            if archive.offset != end:
                raise ValueError('unsupported tar layout')
        raw.seek(0)
        info = tarfile.TarInfo(marker)
        payload = (seed_hash + '\n' + diff_id + '\n').encode()
        info.size = len(payload)
        info.mode = 0o444
        header = info.tobuf(format=tarfile.USTAR_FORMAT)
        output_hash = hashlib.sha256()
        with tempfile.NamedTemporaryFile(dir=root, delete=False) as output:
            temporary = Path(output.name)
            try:
                with gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0, compresslevel=9) as compressed:
                    def write(data):
                        output_hash.update(data)
                        compressed.write(data)
                    left = end
                    while left:
                        chunk = raw.read(min(CHUNK, left))
                        if not chunk:
                            raise ValueError('truncated tar prefix')
                        write(chunk)
                        left -= len(chunk)
                    write(header)
                    write(payload + bytes((-len(payload)) % 512))
                    write(bytes(1024))
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        try:
            checksum = hashlib.sha256()
            with temporary.open('rb') as stream:
                while chunk := stream.read(CHUNK):
                    checksum.update(chunk)
            compressed_digest = checksum.hexdigest()
            size = temporary.stat().st_size
            target = root / 'blobs' / 'sha256' / compressed_digest
            if target.exists():
                temporary.unlink()
            else:
                temporary.rename(target)
        finally:
            temporary.unlink(missing_ok=True)
    return {'digest': 'sha256:' + compressed_digest, 'size': size,
            'diff_id': 'sha256:' + output_hash.hexdigest(), 'marker': marker}


def largest_layer_digest(layers):
    return max(layers, key=lambda layer: layer['size'])['digest']


def prepare_variant(layout, contract, destination, seed, *, retain_other_layers=False, architecture='arm64'):
    """Create a new w8-v3 layout and receipt; seed is 1..1024 explicit bytes."""
    if not isinstance(seed, bytes) or not 1 <= len(seed) <= 1024:
        raise ValueError('seed must contain 1..1024 bytes')
    source = Path(layout).absolute()
    dest = Path(destination).absolute()
    if dest == source or source in dest.parents or dest in source.parents:
        raise ValueError('source and destination must be separate')
    for parent in (dest.parent, *dest.parent.parents):
        if parent.is_symlink():
            raise ValueError('symlink in destination path')
    portfolio = registry.prepare_pinned_portfolio(source, contract, architecture=architecture)
    version = RETAINED_VERSION if retain_other_layers else DERIVED_VERSION
    dest.mkdir()
    try:
        (dest / 'blobs' / 'sha256').mkdir(parents=True)
        (dest / 'oci-layout').write_bytes(_encoded({'imageLayoutVersion': '1.0.0'}))
        source_index = registry._json(registry._read(source / 'index.json'))
        index = copy.deepcopy(source_index)
        index['manifests'] = []
        seed_hash = hashlib.sha256(seed).hexdigest()
        derived = {}
        images = {}
        for name, image in sorted(contract['images'].items()):
            manifest = registry._json(portfolio.routes[(name, 'manifests', image['manifest'])][2].metadata())
            config = registry._json(portfolio.routes[(name, 'blobs', image['config'])][2].metadata())
            layers = []
            diff_ids = []
            changed_digest = largest_layer_digest(manifest['layers']) if retain_other_layers else None
            for descriptor, diff_id in zip(manifest['layers'], image['diff_ids'], strict=True):
                blob = portfolio.routes[(name, 'blobs', descriptor['digest'])][2]
                if retain_other_layers and descriptor['digest'] != changed_digest:
                    target = dest / 'blobs' / 'sha256' / descriptor['digest'].removeprefix('sha256:')
                    if not target.exists():
                        with blob.open() as original, target.open('xb') as retained:
                            shutil.copyfileobj(original, retained)
                    layers.append(copy.deepcopy(descriptor))
                    diff_ids.append(diff_id)
                    continue
                key = (descriptor['digest'], diff_id, descriptor.get('mediaType'))
                if key not in derived:
                    derived[key] = _layer(blob, key[2], diff_id, seed_hash, dest)
                item = derived[key]
                layer = copy.deepcopy(descriptor)
                layer.update(mediaType='application/vnd.oci.image.layer.v1.tar+gzip', digest=item['digest'], size=item['size'])
                layers.append(layer)
                diff_ids.append(item['diff_id'])
            config['rootfs']['diff_ids'] = diff_ids
            config.setdefault('config', {})
            if config['config'] is None:
                config['config'] = {}
            labels = config['config'].setdefault('Labels', {})
            if labels is None:
                labels = config['config']['Labels'] = {}
            if LABEL in labels:
                raise ValueError('fixture label already exists')
            labels[LABEL] = version
            manifest['config'] = _put(dest, _encoded(config), manifest['config'])
            manifest['layers'] = layers
            source_descriptor = next(d for d in source_index['manifests'] if d.get('annotations', {}).get('org.opencontainers.image.ref.name') == image['layout_reference'])
            descriptor = _put(dest, _encoded(manifest), {'mediaType': portfolio.routes[(name, 'manifests', image['manifest'])][0], 'annotations': copy.deepcopy(source_descriptor['annotations'])})
            index['manifests'].append(descriptor)
            images[name] = {'reference': image['layout_reference'], 'source_manifest': image['manifest'], 'manifest': descriptor['digest'], 'config': manifest['config']['digest'], 'layers': layers, 'diff_ids': diff_ids}
        (dest / 'index.json').write_bytes(_encoded(index))
        receipt = {'schema_version': 1, 'fixture_version': version, 'source_fixture_version': contract['fixture_version'], 'source_contract_sha256': hashlib.sha256(_encoded(contract)).hexdigest(), 'method': 'append owned marker to each selected source tar before terminal records; gzip level 9 mtime 0' if retain_other_layers else 'append owned marker to each source tar before terminal records; gzip level 9 mtime 0', 'seed_sha256': seed_hash, 'python': sys.version, 'zlib_version': zlib.ZLIB_VERSION, 'zlib_runtime_version': zlib.ZLIB_RUNTIME_VERSION, 'images': images, 'layers': [{'source_digest': key[0], 'source_diff_id': key[1], **value} for key, value in sorted(derived.items())]}
        registry.prepare_layout(dest, {name: image['layout_reference'] for name, image in contract['images'].items()}, architecture=architecture)
        (dest / 'receipt.json').write_bytes(_encoded(receipt) + b'\n')
        return receipt
    except BaseException:
        shutil.rmtree(dest)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     epilog="Example: registry_variant.py common-layout portfolio.json pair-layout 0102")
    parser.add_argument('layout', type=Path, help='original pinned OCI layout')
    parser.add_argument('contract', type=Path, help='source portfolio pin JSON')
    parser.add_argument('destination', type=Path, help='new OCI layout directory')
    parser.add_argument('seed_hex', help='hex-encoded per-pair seed')
    parser.add_argument('--retain-other-layers', action='store_true',
                        help='change only the largest layer of each image')
    args = parser.parse_args()
    try:
        prepare_variant(args.layout, json.loads(args.contract.read_text()), args.destination,
                        bytes.fromhex(args.seed_hex), retain_other_layers=args.retain_other_layers)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f'fixture preparation: {exc}\n')


if __name__ == '__main__':
    main()
