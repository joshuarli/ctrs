"""Restore the frozen CPython 3.13 Linux ARM64 wheel inputs for W7."""
import json
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import runner


LOCK = Path(__file__).with_name('wheels-arm64.json')


def prepare(destination):
    lock = json.loads(LOCK.read_text())
    if (lock['schema'], lock['platform'], lock['python_abi']) != (1, 'linux/arm64', 'cp313'):
        raise ValueError('unexpected HTTPie wheel lock identity')
    wheels = lock['wheels']
    names = {wheel['file'] for wheel in wheels}
    if not names or len(names) != len(wheels):
        raise ValueError('HTTPie wheel lock is empty or has duplicate files')
    for wheel in wheels:
        name = wheel['file']
        url = urlsplit(wheel['url'])
        if (not re.fullmatch(r'[A-Za-z0-9_.-]+\.whl', name)
                or (url.scheme, url.netloc) != ('https', 'files.pythonhosted.org')
                or Path(url.path).name != name
                or not re.fullmatch(r'[a-f0-9]{64}', wheel['sha256'])):
            raise ValueError('invalid PyPI wheel source in the HTTPie lock')
    destination.mkdir(parents=True, exist_ok=True)
    if {path.name for path in destination.glob('*.whl')} - names:
        raise ValueError('HTTPie wheelhouse contains wheels outside the lock')
    for wheel in wheels:
        name = wheel['file']
        target = destination / name
        if runner.sha256_file(target) == wheel['sha256']:
            continue
        with tempfile.TemporaryDirectory(prefix='download-', dir=destination) as directory:
            runner.ensure_pinned_source(wheel, Path(directory)).replace(target)
    return {'path': str(destination), 'lock_sha256': runner.sha256_file(LOCK), 'wheel_count': len(wheels)}


if __name__ == '__main__':
    if runner.linux_lane.enabled():
        sys.exit('run without the Linux amd64 campaign lane enabled')
    print(json.dumps(prepare(runner.REPO / '.work/tmp/w7-httpie-wheelhouse'), indent=2))
