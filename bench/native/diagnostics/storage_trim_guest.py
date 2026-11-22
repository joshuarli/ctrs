"""Measure the ctrs ext4 data disk from a private probe volume."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import struct
import sys


PROBE = Path('/probe')
SENTINEL = PROBE / 'trim-sentinel'
# Linux UAPI include/uapi/linux/fs.h: _IOWR('X', 121, struct fstrim_range).
FITRIM = 0xC0185879


def capacity(fd):
    status = os.fstatvfs(fd)
    return {'used_bytes': (status.f_blocks - status.f_bfree) * status.f_frsize,
            'free_bytes': status.f_bfree * status.f_frsize}


def observe(operation):
    if operation not in ('seed', 'sample', 'trim'):
        raise ValueError('unknown storage trim operation')
    fd = os.open(PROBE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        device = f'{os.major(st.st_dev)}:{os.minor(st.st_dev)}'
        matched = []
        for line in Path('/proc/self/mountinfo').read_text().splitlines():
            mount, _, source = line.partition(' - ')
            fields = mount.split()
            if fields[4] == os.fspath(PROBE):
                matched.append((fields[2], source.split()[:2]))
        if matched != [(device, ['ext4', '/dev/vda'])]:
            raise ValueError(f'unexpected trim probe mount: {matched}')
        if operation == 'seed':
            with SENTINEL.open('xb') as output:
                output.write(os.urandom(65536))
                output.flush()
                os.fsync(output.fileno())
            os.fsync(fd)
        receipt = {'operation': operation, 'device': device, 'before': capacity(fd),
                   'sentinel_sha256': hashlib.sha256(SENTINEL.read_bytes()).hexdigest()}
        if operation == 'trim':
            request = bytearray(struct.pack('=QQQ', 0, (1 << 64) - 1, 0))
            fcntl.ioctl(fd, FITRIM, request)
            _, receipt['discard_submitted_bytes'], receipt['min_extent_bytes'] = struct.unpack('=QQQ', request)
            receipt['after'] = capacity(fd)
        return receipt
    finally:
        os.close(fd)


if __name__ == '__main__':
    print(json.dumps(observe(sys.argv[1])))
