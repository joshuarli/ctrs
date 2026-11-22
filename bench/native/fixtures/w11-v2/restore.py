#!/usr/bin/env python3
"""Restore the pinned W11 OCI worker from a local archive."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile


HERE = Path(__file__).resolve().parent
BENCH = HERE.parents[1]
sys.path.insert(0, str(BENCH))

import registry_portfolio


OUTPUT = BENCH.parents[1] / '.work/native-perf/inputs/w11-worker-v5'


def copy_blob(archive, destination, digest, expected_size=None):
    if not registry_portfolio.DIGEST.fullmatch(digest):
        raise ValueError('invalid worker blob digest')
    name = 'blobs/sha256/' + digest[7:]
    member = archive.getmember(name)
    if not member.isfile() or (expected_size is not None and member.size != expected_size):
        raise ValueError(f'invalid worker archive entry: {name}')
    if expected_size is None and member.size > 8 * 1024 * 1024:
        raise ValueError('worker manifest exceeds 8 MiB')
    target = destination / name
    with archive.extractfile(member) as source, target.open('xb') as stream:
        shutil.copyfileobj(source, stream)
    return target


def restore(source, output, pin):
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    with tempfile.TemporaryDirectory(prefix='.w11-worker-', dir=output.parent) as tmp:
        layout = Path(tmp) / 'layout'
        (layout / 'blobs/sha256').mkdir(parents=True)
        manifest_digest = pin['manifest']
        with tarfile.open(source, 'r:*') as archive:
            manifest = copy_blob(archive, layout, manifest_digest).read_bytes()
            if hashlib.sha256(manifest).hexdigest() != manifest_digest[7:]:
                raise ValueError('worker manifest integrity failure')
            image = json.loads(manifest)
            config = image['config']
            if config['digest'] != pin['config']:
                raise ValueError('worker config differs from pin')
            blobs = {item['digest']: item['size'] for item in (config, *image['layers'])}
            for digest, size in blobs.items():
                copy_blob(archive, layout, digest, size)
        descriptor = {
            'digest': manifest_digest,
            'size': len(manifest),
            'mediaType': image.get('mediaType', registry_portfolio.OCI_MANIFEST),
            'annotations': {'org.opencontainers.image.ref.name': pin['layout_reference']},
        }
        (layout / 'index.json').write_text(json.dumps({'schemaVersion': 2, 'manifests': [descriptor]}) + '\n')
        (layout / 'oci-layout').write_text('{"imageLayoutVersion":"1.0.0"}\n')
        repo = pin['repository']
        portfolio = registry_portfolio.prepare_layout(layout, {repo: pin['layout_reference']})
        metadata = portfolio.routes[(repo, 'blobs', pin['config'])][2].metadata()
        if json.loads(metadata)['rootfs']['diff_ids'] != pin['diff_ids']:
            raise ValueError('worker diff IDs differ from pin')
        output.mkdir()
        try:
            layout.rename(output / 'layout')
        except OSError:
            output.rmdir()
            raise
    return output / 'layout'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path, help='original worker archive or exact OCI Docker export')
    args = parser.parse_args()
    pin = json.loads((HERE / 'worker-pin.json').read_text())['worker']
    try:
        print(restore(args.archive, OUTPUT, pin))
    except (OSError, ValueError, KeyError, tarfile.TarError) as exc:
        parser.exit(1, f'worker restore: {exc}\n')


if __name__ == '__main__':
    main()
