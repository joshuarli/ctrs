#!/usr/bin/env python3
"""Raw HTTP request/response latency for the CTRS-17 net bench: performs
ITER TCP requests to host:port and prints 'label p50_ms p99_ms mean_ms
min_ms samples'. Closes the connection between requests (fresh TCP each)
or keeps it alive with --keepalive."""
import socket
import statistics
import sys
import time

host = sys.argv[1]
port = int(sys.argv[2])
path = sys.argv[3]
count = int(sys.argv[4]) if len(sys.argv) > 4 else 50
keepalive = len(sys.argv) > 5 and sys.argv[5] == "keepalive"
label = f"{host}:{port}{path}"

def one(sock):
    t0 = time.perf_counter()
    sock.sendall(f"GET {path} HTTP/1.0\r\nhost: x\r\n\r\n".encode())
    buf = b""
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
        if b"\r\n\r\n" in buf:
            head, _, rest = buf.partition(b"\r\n\r\n")
            headers = dict((k.decode().lower(), v.decode().strip()) for k, _, v in (l.partition(b":") for l in head.decode("latin-1").split("\r\n")[1:]) if k)
            cl = int(headers.get("content-length", "0") or "0")
            if len(rest) >= cl:
                break
    return (time.perf_counter() - t0) * 1000

times = []
if keepalive:
    s = socket.create_connection((host, port), timeout=10)
    for _ in range(count):
        t0 = time.perf_counter()
        s.sendall(f"GET {path} HTTP/1.1\r\nhost: x\r\nconnection: keep-alive\r\n\r\n".encode())
        buf = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            head_end = buf.find(b"\r\n\r\n")
            if head_end >= 0:
                head = buf[:head_end].decode("latin-1")
                headers = dict((k.strip().lower(), v.strip()) for k, _, v in (l.partition(":") for l in head.split("\r\n")[1:]) if k)
                cl = int(headers.get("content-length", "0") or "0")
                if len(buf) >= head_end + 4 + cl:
                    break
        times.append((time.perf_counter() - t0) * 1000)
    s.close()
else:
    for _ in range(count):
        with socket.create_connection((host, port), timeout=10) as s:
            times.append(one(s))

times.sort()
n = len(times)
p50 = times[n // 2]
p99 = times[min(n - 1, int(n * 0.99))]
print(f"{label} p50={p50:.2f}ms p99={p99:.2f}ms mean={statistics.fmean(times):.2f}ms min={times[0]:.2f}ms n={n}")
