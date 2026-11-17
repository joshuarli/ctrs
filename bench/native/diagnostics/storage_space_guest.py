"""Hold an owned ext4 unwritten reservation with bounded automatic release."""
import errno
import fcntl
import json
import os
from pathlib import Path
import select
import signal
import struct
import sys

STAGES = ('allocation', 'enospc')
LEAVE_AVAILABLE_BYTES = 8 << 20


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in STAGES:
        raise ValueError('require allocation or enospc mode')
    if sys.platform != 'linux' or os.uname().machine != 'aarch64':
        raise RuntimeError('native ARM64 Linux guest only')
    mode = sys.argv[1]
    path = Path('/fill/reservation')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)

    def expire(*args):
        raise TimeoutError('bounded reservation expired')

    signal.signal(signal.SIGALRM, expire)
    signal.alarm(90)

    def fs_uuid():
        with Path('/dev/vda').open('rb') as raw:
            raw.seek(1128)
            return raw.read(16).hex()

    def state():
        fs = os.statvfs('/fill')
        device = os.stat('/dev/vda').st_rdev
        if not (os.stat('/fill').st_dev == device):
            raise ValueError('fill is not the owned vda filesystem')
        return {'block_size': fs.f_frsize, 'blocks': fs.f_blocks, 'free_bytes': fs.f_bfree * fs.f_frsize,
                'available_bytes': fs.f_bavail * fs.f_frsize, 'device': device,
                'reservation_size': os.fstat(fd).st_size, 'reservation_allocated': os.fstat(fd).st_blocks * 512,
                'volume_inode': os.stat('/fill').st_ino, 'fs_uuid': fs_uuid()}

    def extents():
        count = 16384
        buf = bytearray(struct.pack('=QQIIII', 0, (1 << 64)-1, 1, 0, count, 0) + bytes(56 * count))
        fcntl.ioctl(fd, 0xC020660B, buf, True)
        mapped = struct.unpack_from('=I', buf, 20)[0]
        rows = [struct.unpack_from('=QQQQQIIII', buf, 32 + 56 * i) for i in range(mapped)]
        if not (rows and len(rows) < count and all(row[5] & 0x800 for row in rows)):
            raise ValueError('reservation includes written or unbounded extents')
        return {'count': mapped, 'all_unwritten': True, 'length': sum(row[2] for row in rows),
                'first': rows[0], 'last': rows[-1]}

    def proceed():
        print(json.dumps({'event': 'progress'}), flush=True)
        if not select.select([sys.stdin], [], [], 75)[0]:
            raise TimeoutError('no reservation command')
        line = sys.stdin.readline()
        if line in ('RELEASE\n', ''):
            return False
        if line != 'CONTINUE\n':
            raise ValueError('invalid reservation command')
        return True

    try:
        before = state()
        offset = 0
        attempts = 0
        allocation_errors = []
        step = 64 << 20
        if mode == 'allocation':
            os.posix_fallocate(fd, 0, 64 << 20)
            attempts = 1
            if not proceed():
                return
        else:
            while True:
                fs = os.statvfs('/fill')
                available = fs.f_bavail * fs.f_frsize
                if available <= LEAVE_AVAILABLE_BYTES:
                    break
                length = min(step, ((available - LEAVE_AVAILABLE_BYTES) // fs.f_frsize) * fs.f_frsize)
                if not (length > 0):
                    raise ValueError('diagnostic validation failed: length > 0')
                attempts += 1
                try:
                    os.posix_fallocate(fd, offset, length)
                except OSError as exc:
                    allocation_errors.append({'offset': offset, 'length': length, 'available_bytes': available, 'error': repr(exc)})
                    if exc.errno != errno.ENOSPC or step <= fs.f_frsize:
                        raise
                    step = max(fs.f_frsize, step // 8)
                else:
                    offset += length
                if not proceed():
                    return
        print(json.dumps({'event': 'reserved', 'before': before, 'after': state(), 'extents': extents(), 'allocation_attempts': attempts,
                          'allocation_errors': allocation_errors}), flush=True)
        if not select.select([sys.stdin], [], [], 75)[0]:
            raise TimeoutError('no release command')
        line = sys.stdin.readline()
        if line not in ('RELEASE\n', ''):
            raise ValueError('invalid release command')
    finally:
        path.unlink(missing_ok=True)
        os.close(fd)
        signal.alarm(0)
        fs = os.statvfs('/fill')
        print(json.dumps({'event': 'released', 'free_bytes': fs.f_bfree * fs.f_frsize,
                          'available_bytes': fs.f_bavail * fs.f_frsize, 'volume_inode': os.stat('/fill').st_ino,
                          'fs_uuid': fs_uuid()}), flush=True)


if __name__ == '__main__':
    main()
