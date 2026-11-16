#!/usr/bin/env python3
"""W4 deterministic HTTP-to-Redis event batch fixture."""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import socket
import sys
from urllib.request import Request, urlopen

JOBS = 200
EVENTS = 64
QUEUE = 'npw4:jobs'
ROUTES = ('/api/orders', '/api/products', '/api/users', '/health')
STATUSES = (200, 201, 400, 404, 500, 503)
TENANTS = ('north', 'south', 'east', 'west')
MAX_BODY = 65536


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


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def batch(job):
    events = []
    for index in range(EVENTS):
        n = job * EVENTS + index
        events.append({
            'timestamp': (datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=n)).isoformat().replace('+00:00', 'Z'),
            'status': STATUSES[(n + job) % len(STATUSES)],
            'route': ROUTES[(n // 3 + job) % len(ROUTES)],
            'latency_ms': 1 + (n * 37 + job * 11) % 2000,
            'tenant': TENANTS[(n // 7 + job) % len(TENANTS)],
        })
    return {'id': job, 'events': events}


def validate_batch(value):
    if not isinstance(value, dict) or set(value) != {'id', 'events'}:
        raise ValueError('expected batch with id and events')
    job = value['id']
    if type(job) is not int or not 0 <= job < JOBS:
        raise ValueError(f'id must be an integer in 0..{JOBS - 1}')
    events = value['events']
    if not isinstance(events, list) or len(events) != EVENTS:
        raise ValueError(f'expected {EVENTS} events')
    for event in events:
        if not isinstance(event, dict) or set(event) != {'timestamp', 'status', 'route', 'latency_ms', 'tenant'}:
            raise ValueError('invalid event fields')
        timestamp = event['timestamp']
        try:
            if not isinstance(timestamp, str) or not timestamp.endswith('Z'):
                raise ValueError('timestamp must be UTC')
            datetime.fromisoformat(timestamp[:-1] + '+00:00')
        except ValueError as exc:
            raise ValueError('invalid timestamp') from exc
        if type(event['status']) is not int or event['status'] not in STATUSES:
            raise ValueError('invalid status')
        if event['route'] not in ROUTES or event['tenant'] not in TENANTS:
            raise ValueError('invalid route or tenant')
        if type(event['latency_ms']) is not int or not 1 <= event['latency_ms'] <= 2000:
            raise ValueError('invalid latency')
    return value


def artifacts(value):
    events = value['events']
    summary = {
        'id': value['id'],
        'event_count': len(events),
        'status_counts': dict(Counter(str(event['status']) for event in events)),
        'route_counts': dict(Counter(event['route'] for event in events)),
        'tenant_counts': dict(Counter(event['tenant'] for event in events)),
        'latency_ms_total': sum(event['latency_ms'] for event in events),
        'latency_ms_max': max(event['latency_ms'] for event in events),
    }
    raw = b''.join(encode(event) + b'\n' for event in events)
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode='wb', filename='', mtime=0) as stream:
        stream.write(raw)
    return compressed.getvalue(), encode(summary) + b'\n'


def filenames(job):
    return f'job-{job:04d}.ndjson.gz', f'job-{job:04d}.summary.json'


def handler(host, port):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != '/health':
                self.reply(404, {'ok': False})
                return
            try:
                redis = Redis(host, port)
                try:
                    if redis.command('PING') != b'PONG':
                        raise RuntimeError('unexpected Redis ping response')
                finally:
                    redis.close()
            except (OSError, RuntimeError) as exc:
                self.reply(503, {'error': str(exc)})
                return
            self.reply(200, {'ok': True})

        def do_POST(self):
            if self.path != '/jobs':
                self.reply(404, {'error': 'not found'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_BODY:
                    raise ValueError('invalid body length')
                payload = self.rfile.read(length)
                if len(payload) != length:
                    raise ValueError('truncated body')
                value = validate_batch(json.loads(payload))
            except (ValueError, TypeError, UnicodeDecodeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            try:
                redis = Redis(host, port)
                try:
                    redis.command('RPUSH', QUEUE, payload)
                finally:
                    redis.close()
            except (OSError, RuntimeError) as exc:
                self.reply(503, {'error': str(exc)})
                return
            self.reply(202, {'id': value['id']})

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


def worker(host, port, output_dir):
    output_dir = Path(output_dir)
    redis = Redis(host, port)
    try:
        while True:
            item = redis.command('LPOP', QUEUE)
            if item is None:
                return
            value = validate_batch(json.loads(item))
            contents = artifacts(value)
            for name, content in zip(filenames(value['id']), contents):
                with (output_dir / name).open('xb') as output:
                    output.write(content)
    finally:
        redis.close()


def verify(host, port, output_dir):
    redis = Redis(host, port)
    try:
        pending = redis.command('LLEN', QUEUE)
    finally:
        redis.close()
    directory = Path(output_dir)
    expected = {name: content for job in range(JOBS)
                for name, content in zip(filenames(job), artifacts(batch(job)))}
    actual = {path.name for path in directory.iterdir()}
    missing = set(expected) - actual
    extra = actual - set(expected)
    corrupt = []
    for name in set(expected) & actual:
        path = directory / name
        if not path.is_file() or path.is_symlink() or path.read_bytes() != expected[name]:
            corrupt.append(name)
    if pending or missing or extra or corrupt:
        raise ValueError(f'pending={pending} missing={len(missing)} extra={len(extra)} corrupt={len(corrupt)}')
    return JOBS


def submit(url):
    for job in range(JOBS):
        req = Request(url.rstrip('/') + '/jobs', data=encode(batch(job)),
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
    parser.add_argument('--output-dir', default='/output')
    args = parser.parse_args()
    if args.command == 'serve':
        ThreadingHTTPServer((args.listen, args.port), handler(args.redis_host, args.redis_port)).serve_forever()
    elif args.command == 'submit':
        submit(args.url)
        print(f'submitted {JOBS}')
    elif args.command == 'worker':
        worker(args.redis_host, args.redis_port, args.output_dir)
    else:
        print(f'verified {verify(args.redis_host, args.redis_port, args.output_dir)}')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'w4: {exc}', file=sys.stderr)
        sys.exit(1)
