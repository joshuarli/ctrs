#!/usr/bin/env python3
"""W4 deterministic HTTP-to-Redis content processing fixture."""
import argparse
from collections import Counter
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import sys
from urllib.request import Request, urlopen

JOBS = 200
QUEUE = 'npw4:jobs'
RESULTS = 'npw4:results'
ROUNDS = 256


class Redis:
    """Small RESP2 client; each instance owns one connection."""
    def __init__(self, host, port):
        self.sock = socket.create_connection((host, port), timeout=10)
        self.file = self.sock.makefile('rb')

    def close(self):
        self.file.close()
        self.sock.close()

    def command(self, *args):
        parts = [str(a).encode() if not isinstance(a, bytes) else a for a in args]
        self.sock.sendall(b'*%d\r\n' % len(parts) + b''.join(
            b'$%d\r\n' % len(p) + p + b'\r\n' for p in parts))
        return self._read()

    def _read(self):
        line = self.file.readline()
        if not line.endswith(b'\r\n'):
            raise RuntimeError('truncated Redis response')
        kind, value = line[:1], line[1:-2]
        if kind == b'-':
            raise RuntimeError('Redis error: ' + value.decode(errors='replace'))
        if kind == b'+':
            return value
        if kind == b':':
            return int(value)
        if kind == b'$':
            n = int(value)
            if n == -1:
                return None
            data = self.file.read(n + 2)
            if len(data) != n + 2 or data[-2:] != b'\r\n':
                raise RuntimeError('truncated Redis bulk response')
            return data[:-2]
        if kind == b'*':
            n = int(value)
            return None if n == -1 else [self._read() for _ in range(n)]
        raise RuntimeError('invalid Redis response')


def artifact(job):
    """Pinned input and work: 256 chained SHA-256 rounds per job."""
    data = f'ctrs-w4-v2-input-{job:04d}\n'.encode()
    digest = data
    for _ in range(ROUNDS):
        digest = hashlib.sha256(digest).digest()
    return json.dumps({'id': job, 'content': data.decode(), 'sha256': digest.hex()},
                      sort_keys=True, separators=(',', ':')).encode()


def parse_job(value):
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < JOBS:
        raise ValueError(f'id must be an integer in 0..{JOBS - 1}')
    return value


def handler(host, port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.reply(200 if self.path == '/health' else 404, {'ok': self.path == '/health'})

        def do_POST(self):
            if self.path != '/jobs':
                self.reply(404, {'error': 'not found'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1024:
                    raise ValueError('invalid body length')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or set(body) != {'id'}:
                    raise ValueError('expected object with id')
                job = parse_job(body['id'])
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            try:
                redis = Redis(host, port)
                try:
                    redis.command('RPUSH', QUEUE, job)
                finally:
                    redis.close()
            except (OSError, RuntimeError) as exc:
                self.reply(503, {'error': str(exc)})
                return
            self.reply(202, {'id': job})

        def reply(self, status, obj):
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass
    return Handler


def worker(host, port):
    redis = Redis(host, port)
    try:
        while True:
            item = redis.command('LPOP', QUEUE)
            if item is None:
                return
            job = parse_job(int(item))
            redis.command('RPUSH', RESULTS, artifact(job))
    finally:
        redis.close()


def verify(host, port):
    redis = Redis(host, port)
    try:
        pending = redis.command('LLEN', QUEUE)
        results = redis.command('LRANGE', RESULTS, 0, -1)
    finally:
        redis.close()
    expected = Counter(artifact(i) for i in range(JOBS))
    actual = Counter(results)
    missing = sum((expected - actual).values())
    unexpected = sum((actual - expected).values())
    if pending or missing or unexpected:
        raise ValueError(f'pending={pending} missing={missing} unexpected={unexpected} results={len(results)}')
    return len(results)


def submit(url):
    for job in range(JOBS):
        req = Request(url.rstrip('/') + '/jobs', data=json.dumps({'id': job}).encode(),
                      headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(req, timeout=10) as response:
            if response.status != 202 or json.load(response) != {'id': job}:
                raise RuntimeError(f'ingest rejected job {job}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['serve', 'submit', 'worker', 'verify'])
    parser.add_argument('--redis-host', default='redis')
    parser.add_argument('--redis-port', type=int, default=6379)
    parser.add_argument('--listen', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--url', default='http://app:8080')
    args = parser.parse_args()
    if args.command == 'serve':
        ThreadingHTTPServer((args.listen, args.port), handler(args.redis_host, args.redis_port)).serve_forever()
    elif args.command == 'submit':
        submit(args.url)
        print(f'submitted {JOBS}')
    elif args.command == 'worker':
        worker(args.redis_host, args.redis_port)
    else:
        print(f'verified {verify(args.redis_host, args.redis_port)}')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'w4: {exc}', file=sys.stderr)
        sys.exit(1)
