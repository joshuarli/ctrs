"""Byte identity for the common native W7 HTTPie first-use input."""
import hashlib
import json
import re
import tarfile


def archive_identity(path):
    with path.open('rb') as source:
        archive_hash = hashlib.file_digest(source, 'sha256').hexdigest()
    with tarfile.open(path, 'r:*') as archive:
        manifest = json.loads(member_bytes(archive, 'manifest.json'))
        if not isinstance(manifest, list) or len(manifest) != 1:
            raise ValueError('HTTPie archive must contain exactly one image')
        entry = manifest[0]
        raw_config = member_bytes(archive, entry['Config'])
        config = json.loads(raw_config)
        if (config.get('os'), config.get('architecture')) != ('linux', 'arm64'):
            raise ValueError('HTTPie archive image must be Linux ARM64')
        diff_ids = config['rootfs']['diff_ids']
        layers = entry['Layers']
        if (not diff_ids or len(diff_ids) != len(layers)
                or any(not re.fullmatch(r'sha256:[a-f0-9]{64}', value) for value in diff_ids)
                or any(not archive.getmember(layer).isfile() for layer in layers)):
            raise ValueError('HTTPie archive layer list differs from the config')
    return {'archive_sha256': archive_hash,
            'config_sha256': 'sha256:' + hashlib.sha256(raw_config).hexdigest(),
            'diff_ids': diff_ids}


def member_bytes(archive, name):
    member = archive.getmember(name)
    if not member.isfile():
        raise ValueError(f'HTTPie archive member is not a regular file: {name}')
    with archive.extractfile(member) as source:
        return source.read()


def verify_loaded_image(image, identity):
    if ((image.get('Os'), image.get('Architecture')) != ('linux', 'arm64')
            or (image.get('RootFS') or {}).get('Layers') != identity['diff_ids']):
        raise ValueError('loaded HTTPie image differs from the frozen ARM64 rootfs')
    image_id = image.get('Id', '')
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', image_id):
        raise ValueError('loaded HTTPie image ID is unavailable')
    return image_id
