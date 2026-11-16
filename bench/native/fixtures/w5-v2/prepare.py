#!/usr/bin/env python3
import hashlib
from pathlib import Path
import subprocess
import sys

ARCHIVE_SHA256 = '2da1adfd5d17b47477dbeecdf6d9de69cbfd84558320807987406b9e7a1e8ca5'
LOCK_SHA256 = '5acaa75805a6efc1d58be5415cc94cb09058ad6ec3ff7c0fb1a4f05491b1abf4'


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
