import concurrent.futures
import hashlib
import json
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
        while True:
            data = f.read(CHUNK)
            if not data:
                break
            sock.sendall(data)
    sock.shutdown(socket.SHUT_WR)


def receive(sock, ident, size, digest):
    start = time.monotonic()
    total = 0
    gaps = []
    first = None
    error = None
    actual = hashlib.sha256()
    try:
        header = line(sock)
        if header != {'id': ident, 'bytes': size, 'sha256': digest}:
            raise ValueError('header mismatch')
        last = time.monotonic()
        while True:
            block = sock.recv(CHUNK)
            now = time.monotonic()
            if not block:
                break
            if first is None:
                first = now - start
            gaps.append(now - last)
            last = now
            total += len(block)
            actual.update(block)
            if total > size:
                raise ValueError('excess bytes')
        if total != size or actual.hexdigest() != digest:
            raise ValueError('byte count or hash mismatch')
    except Exception as exc:
        error = str(exc)
    elapsed = time.monotonic() - start
    return {'id': ident, 'bytes': total, 'sha256': actual.hexdigest(), 'seconds': elapsed,
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
                    result = receive(conn, ident, size, digest)
                    conn.sendall((json.dumps(result) + '\n').encode())
                    return result
                send(conn, path, ident, size, digest)
                return {'id': ident}
        with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
            futures = [pool.submit(handle, listener.accept()[0]) for _ in range(count)]
            results = [f.result() for f in futures]
    with open(output, 'w') as f:
        json.dump(results, f)


def client(host, port, direction, count, path, size, digest):
    def stream(i):
        with socket.create_connection((host, port), timeout=120) as sock:
            sock.settimeout(120)
            ident = str(i)
            sock.sendall((json.dumps({'id': ident}) + '\n').encode())
            if direction == 'upload':
                send(sock, path, ident, size, digest)
                return line(sock)
            return receive(sock, ident, size, digest)
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
