#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import subprocess
import sys

CONTRACT = json.loads(Path(__file__).with_name('workload.json').read_text())
ARCHIVE_SHA256 = CONTRACT['source']['sha256']
LOCK_SHA256 = CONTRACT['source']['lock_sha256']

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(archive, destination):
    if digest(archive) != ARCHIVE_SHA256:
        raise ValueError('source archive SHA256 mismatch')
    destination.mkdir(parents=True, exist_ok=False)
    subprocess.run(['tar', '-xzf', str(archive.resolve()), '--strip-components=1', '-C', str(destination)], check=True)
    if digest(destination / 'package-lock.json') != LOCK_SHA256:
        raise ValueError('dependency lock SHA256 mismatch')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit('usage: prepare.py ARCHIVE NEW_DESTINATION')
    prepare(Path(sys.argv[1]), Path(sys.argv[2]))
