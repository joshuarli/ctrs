import concurrent.futures
import hashlib
import json
import mmap
import os
import socket
import sys
import time

CHUNK = 1024 * 1024
SEED = 'w13-v1-seed-2026'


def prepare(path, size):
    digest = hashlib.sha256()
    with open(path, 'wb') as f:
        for offset in range(0, size, CHUNK):
            block = hashlib.shake_256((SEED + ':' + str(offset // CHUNK)).encode()).digest(min(CHUNK, size - offset))
            f.write(block)
            digest.update(block)
    return digest.hexdigest()


def line(sock):
    data = bytearray()
    while not data.endswith(b'\n'):
        byte = sock.recv(1)
        if not byte or len(data) >= 4096:
            raise ValueError('incomplete or oversized header')
        data.extend(byte)
    return json.loads(data)


def send(sock, path, ident, size, digest):
    sock.sendall((json.dumps({'id': ident, 'bytes': size, 'sha256': digest}) + '\n').encode())
    with open(path, 'rb') as f:
        length = os.fstat(f.fileno()).st_size
        sent = 0
        while sent < size:
            offset = sent % length
            n = sock.sendfile(f, offset, min(length - offset, size - sent))
            if not n:
                raise OSError('sendfile sent nothing')
            sent += n
    sock.shutdown(socket.SHUT_WR)


def receive(sock, ident, size, digest, expected_path):
    start = time.monotonic()
    total = 0
    gaps = []
    first = None
    error = None
    exact = True
    buffer = bytearray(CHUNK)
    try:
        header = line(sock)
        if header != {'id': ident, 'bytes': size, 'sha256': digest}:
            raise ValueError('header mismatch')
        last = time.monotonic()
        with open(expected_path, 'rb') as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
            with memoryview(mapped) as expected, memoryview(buffer) as received:
                length = len(expected)
                while True:
                    count = sock.recv_into(buffer)
                    now = time.monotonic()
                    if not count:
                        break
                    if first is None:
                        first = now - start
                    gaps.append(now - last)
                    last = now
                    total += count
                    if total > size:
                        raise ValueError('excess bytes')
                    at = (total - count) % length
                    first_part = min(count, length - at)
                    if received[:first_part] != expected[at:at + first_part] or \
                            received[first_part:count] != expected[:count - first_part]:
                        exact = False
        if total != size or not exact:
            raise ValueError('byte count or content mismatch')
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
        if 'last' in locals():
            gaps.append(time.monotonic() - last)
    elapsed = time.monotonic() - start
    return {'id': ident, 'bytes': total, 'sha256': digest if error is None else None, 'seconds': elapsed,
            'first_byte_seconds': first, 'stall_count': sum(g >= 1 for g in gaps),
            'longest_gap_seconds': max(gaps, default=0), 'error': error}


def serve(bind, port, direction, count, path, size, digest, output):
    results = []
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((bind, port)); listener.listen(count); listener.settimeout(120)
        def handle(conn):
            with conn:
                conn.settimeout(120)
                request = line(conn)
                ident = request['id']
                if direction == 'upload':
                    result = receive(conn, ident, size, digest, path)
                    try:
                        conn.sendall((json.dumps(result) + '\n').encode())
                    except OSError as exc:
                        result['ack_error'] = f'{type(exc).__name__}: {exc}'
                    return result
                try:
                    send(conn, path, ident, size, digest)
                    return {'id': ident}
                except OSError as exc:
                    return {'id': ident, 'error': f'{type(exc).__name__}: {exc}'}
        with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
            futures = []
            for _ in range(count):
                try:
                    futures.append(pool.submit(handle, listener.accept()[0]))
                except socket.timeout:
                    break
            for future in futures:
                try:
                    results.append(future.result())
                except Exception as exc:
                    results.append({'id': 'unknown', 'bytes': None,
                                    'error': f'{type(exc).__name__}: {exc}'})
    with open(output, 'w') as f:
        json.dump(results, f)


def client(host, port, direction, count, path, size, digest):
    def stream(i):
        ident = str(i)
        started = time.monotonic()
        try:
            with socket.create_connection((host, port), timeout=120) as sock:
                sock.settimeout(120)
                sock.sendall((json.dumps({'id': ident}) + '\n').encode())
                if direction == 'upload':
                    send(sock, path, ident, size, digest)
                    return line(sock)
                return receive(sock, ident, size, digest, path)
        except Exception as exc:
            return {'id': ident, 'bytes': None, 'seconds': time.monotonic() - started,
                    'error': f'{type(exc).__name__}: {exc}'}
    start = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
        results = list(pool.map(stream, range(count)))
    return {'seconds': time.monotonic() - start, 'streams': results}


if __name__ == '__main__':
    mode, *args = sys.argv[1:]
    if mode == 'prepare':
        print(prepare(args[0], int(args[1])))
    elif mode == 'server':
        serve(args[0], int(args[1]), args[2], int(args[3]), args[4], int(args[5]), args[6], args[7])
    elif mode == 'client':
        print(json.dumps(client(args[0], int(args[1]), args[2], int(args[3]), args[4], int(args[5]), args[6])))
