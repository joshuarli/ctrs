import hashlib
from importlib.metadata import distributions
import json
import re


packages = {}
for distribution in distributions():
    name = re.sub(r'[-_.]+', '-', distribution.metadata['Name']).lower()
    if name in packages or not distribution.files:
        raise ValueError(f'cannot identify installed distribution {name}')
    files = {}
    for entry in distribution.files:
        if entry.hash is None or any(part.endswith('.dist-info') for part in entry.parts):
            continue
        with distribution.locate_file(entry).open('rb') as source:
            files[str(entry)] = hashlib.file_digest(source, 'sha256').hexdigest()
    if not files:
        raise ValueError(f'no installed runtime files for {name}')
    canonical = json.dumps(files, sort_keys=True, separators=(',', ':')).encode()
    packages[name] = {'version': distribution.version, 'runtime_sha256': hashlib.sha256(canonical).hexdigest()}
print(json.dumps(packages, sort_keys=True))
