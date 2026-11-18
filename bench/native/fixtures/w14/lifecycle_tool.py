import concurrent.futures
from contextlib import nullcontext
import errno
import json
import signal
import socket
import socketserver
import sys
import threading
import time
import uuid

RECONNECT_DEADLINE_SECONDS = 60


def send(sock, value):
    sock.sendall(json.dumps(value, separators=(',', ':')).encode() + b'\n')


def receive(sock):
    data = bytearray()
    while not data.endswith(b'\n'):
        part = sock.recv(1)
        if not part:
            raise ConnectionResetError('unexpected EOF')
        data.extend(part)
        if len(data) > 65536:
            raise ValueError('oversized response')
    return json.loads(data)


def response(ident, chunk=0):
    return {'id': ident, 'chunk': chunk, 'body': 'w14:' + str(ident) + ':' + str(chunk)}


def verify(value, ident, chunk=0):
    instance = value.pop('instance', None) if isinstance(value, dict) else None
    if value != response(ident, chunk):
        raise ValueError('wrong data')
    return instance


def classify(exc):
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return 'timeout'
    if isinstance(exc, ConnectionRefusedError) or getattr(exc, 'errno', None) == errno.ECONNREFUSED:
        return 'refused'
    if isinstance(exc, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)) or getattr(exc, 'errno', None) in (errno.ECONNRESET, errno.EPIPE, errno.ENOTCONN):
        return 'reset'
    return 'wrong_data' if isinstance(exc, (ValueError, json.JSONDecodeError)) else 'other'


def percentile(values, percent):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * percent / 100
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def lateness(arrival, start, index, interval):
    return max(0, (arrival - (start + (index + 1) * interval)) * 1000)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    def __init__(self, address):
        self.lock = threading.Lock()
        self.open_clients = 0
        self.instance = uuid.uuid4().hex
        super().__init__(address, Handler)


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        active = False
        try:
            while True:
                req = receive(self.request)
                if req['op'] == 'count':
                    with self.server.lock:
                        send(self.request, {'open': self.server.open_clients})
                    return
                if not active:
                    with self.server.lock:
                        self.server.open_clients += 1
                    active = True
                if req['op'] == 'get':
                    send(self.request, {**response(req['id']), 'instance': self.server.instance})
                elif req['op'] in ('stream', 'cancel'):
                    for i in range(req['chunks']):
                        time.sleep(req['interval'])
                        send(self.request, response(req['id'], i))
                else:
                    raise ValueError('unknown operation')
        except (OSError, ValueError, KeyError):
            pass
        finally:
            if active:
                with self.server.lock:
                    self.server.open_clients -= 1


def connect(host, port, timeout):
    return socket.create_connection((host, port), timeout=timeout)


def get(sock, ident):
    send(sock, {'op': 'get', 'id': ident})
    return verify(receive(sock), ident)


def count(host, port, timeout=2):
    with connect(host, port, timeout) as sock:
        send(sock, {'op': 'count'})
        return receive(sock)['open']


def wait_closed(host, port, timeout):
    start = time.monotonic()
    deadline = start + timeout
    while True:
        remaining = count(host, port)
        if remaining == 0 or time.monotonic() >= deadline:
            return (time.monotonic() - start) * 1000, remaining
        time.sleep(0.01)


def run(host, port, mode, clients=32, operations=100, chunks=50, interval=0.02,
        idle_seconds=30, timeout=5, restart=None, phase=nullcontext):
    barrier = threading.Barrier(clients + (1 if mode == 'reconnect' else 0))
    restart_at = [None]
    restart_error = [None]
    def worker(i):
        result = {'id': i, 'latencies_ms': [], 'lateness_ms': [], 'successes': 0, 'errors': [], 'chunks_received': 0}
        sock = None
        instance = None
        def failure(exc):
            result['errors'].append(classify(exc))
        def reconnect(start, previous=None):
            window = result.setdefault('window_errors', [])
            deadline = start + RECONNECT_DEADLINE_SECONDS
            while time.monotonic() < deadline:
                try:
                    with connect(host, port, min(1, timeout)) as s:
                        seen = get(s, i)
                    if previous is None or seen != previous:
                        result['reconnect_ms'] = (time.monotonic() - start) * 1000
                        return
                    window.append('previous_instance')
                except (OSError, ValueError) as exc:
                    window.append(classify(exc))
                time.sleep(0.02)
            result['errors'].append('reconnect_deadline')
        try:
            if mode != 'fresh':
                sock = connect(host, port, timeout)
                instance = get(sock, i)
            barrier.wait(timeout=timeout + 10)
            if mode == 'reconnect':
                barrier.wait(timeout=timeout + 10)
                sock.close(); sock = None
                reconnect(restart_at[0], instance)
                if restart_error[0]:
                    result['errors'].append('restart_failed')
                return result
            if mode == 'idle-resume':
                time.sleep(idle_seconds)
                start = time.monotonic()
                try:
                    get(sock, i)
                    result['resume'] = 'ok'
                    result['successes'] += 1
                    result['latencies_ms'].append((time.monotonic() - start) * 1000)
                except (OSError, ValueError) as exc:
                    result['resume'] = classify(exc)
                    failure(exc)
                    sock.close(); sock = None
                    reconnect(time.monotonic())
            elif mode in ('streaming', 'cancel'):
                send(sock, {'op': 'stream' if mode == 'streaming' else 'cancel', 'id': i,
                            'chunks': chunks, 'interval': interval})
                start = time.monotonic()
                for j in range(chunks if mode == 'streaming' else 1):
                    verify(receive(sock), i, j)
                    result['chunks_received'] += 1
                    result['lateness_ms'].append(lateness(time.monotonic(), start, j, interval))
                result['successes'] += 1
            else:
                for _ in range(operations):
                    start = time.monotonic()
                    try:
                        if mode == 'fresh':
                            with connect(host, port, timeout) as s:
                                get(s, i)
                        else:
                            get(sock, i)
                        result['successes'] += 1
                        result['latencies_ms'].append((time.monotonic() - start) * 1000)
                    except (OSError, ValueError) as exc:
                        failure(exc)
                        if mode != 'fresh':
                            break
        except (OSError, ValueError, threading.BrokenBarrierError) as exc:
            failure(exc)
            if mode == 'idle-resume':
                result['resume'] = classify(exc)
        finally:
            if sock is not None:
                sock.close()
        return result
    with phase(), concurrent.futures.ThreadPoolExecutor(max_workers=clients) as pool:
        futures = [pool.submit(worker, i) for i in range(clients)]
        if mode == 'reconnect':
            try:
                barrier.wait(timeout=timeout + 10)
                restart_at[0] = time.monotonic()
                barrier.wait(timeout=timeout + 10)
            except threading.BrokenBarrierError as exc:
                restart_error[0] = 'barrier: ' + str(exc)
                barrier.abort()
            else:
                try:
                    restart()
                except Exception as exc:
                    restart_error[0] = str(exc)
        results = [f.result() for f in futures]
    try:
        cleanup_ms, leaked = wait_closed(host, port, timeout)
    except (OSError, ValueError) as exc:
        cleanup_ms, leaked = None, None
        results.append({'id': 'cleanup', 'errors': [classify(exc)], 'successes': 0, 'latencies_ms': [], 'lateness_ms': [], 'chunks_received': 0})
    after_ms = None
    if mode == 'cancel':
        start = time.monotonic()
        try:
            with connect(host, port, timeout) as sock:
                get(sock, 'after')
            after_ms = (time.monotonic() - start) * 1000
        except (OSError, ValueError) as exc:
            results.append({'id': 'after', 'errors': [classify(exc)], 'successes': 0, 'latencies_ms': [], 'lateness_ms': [], 'chunks_received': 0})
        try:
            _, after_leaked = wait_closed(host, port, timeout)
            if leaked == 0:
                leaked = after_leaked
        except (OSError, ValueError) as exc:
            leaked = None
            results[-1]['errors'].append(classify(exc))
    errors = [e for r in results for e in r['errors']]
    latencies = [x for r in results for x in r['latencies_ms']]
    late = [x for r in results for x in r['lateness_ms']]
    reconnects = [r['reconnect_ms'] for r in results if 'reconnect_ms' in r]
    window = [e for r in results for e in r.get('window_errors', [])]
    expected = clients * operations if mode in ('fresh', 'persistent') else clients
    successes = sum(r['successes'] for r in results) if mode != 'reconnect' else len(reconnects)
    return {'clients': results, 'successes': successes, 'expected_successes': expected,
            'errors': {key: errors.count(key) for key in ('refused', 'reset', 'timeout', 'wrong_data', 'other', 'restart_failed', 'reconnect_deadline')},
            'restart_window_errors': {key: window.count(key) for key in sorted(set(window))},
            'latency_p50_ms': percentile(latencies, 50), 'latency_p95_ms': percentile(latencies, 95),
            'latency_p99_ms': percentile(latencies, 99), 'chunk_lateness_p99_ms': percentile(late, 99),
            'chunks_received': sum(r['chunks_received'] for r in results),
            'cleanup_latency_ms': cleanup_ms, 'post_cancel_latency_ms': after_ms,
            'reconnect_p99_ms': percentile(reconnects, 99), 'server_open_connections': leaked,
            'leaked_sessions': leaked, 'ok': successes == expected and not errors and leaked == 0}


if __name__ == '__main__':
    if sys.argv[1] == 'server':
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        with Server((sys.argv[2], int(sys.argv[3]))) as server:
            server.serve_forever()
