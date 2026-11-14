#!/usr/bin/env python3
"""TCP sender for the CTRS-17 net bench: streams N bytes of a repeating
pattern to host:port. Parallel streams all connect to the same port
(iperf3 -s accepts them). Prints 'label bytes elapsed_s mbps'."""
import socket
import sys
import threading
import time

host = sys.argv[1]
port = int(sys.argv[2])
nbytes = int(sys.argv[3])
label = sys.argv[4] if len(sys.argv) > 4 else f"{host}:{port}"
parallel = int(sys.argv[5]) if len(sys.argv) > 5 else 1

CHUNK = 1 << 20
pattern = (b"0123456789abcdef" * (CHUNK // 16))

def worker(idx, results):
    s = socket.create_connection((host, port), timeout=10)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    sent = 0
    t0 = time.perf_counter()
    remaining = nbytes
    while remaining > 0:
        n = s.send(pattern[:CHUNK] if remaining >= CHUNK else pattern[:remaining])
        if n <= 0:
            raise BrokenPipeError
        remaining -= n
        sent += n
    s.shutdown(socket.SHUT_WR)
    t1 = time.perf_counter()
    results[idx] = (sent, t1 - t0)
    s.close()

results = {}
t0 = time.perf_counter()
threads = []
for i in range(parallel):
    th = threading.Thread(target=worker, args=(i, results))
    th.start()
    threads.append(th)
for th in threads:
    th.join()
dt = time.perf_counter() - t0
total = sum(r[0] for r in results.values())
print(f"{label} {total} {dt:.3f} {total * 8 / dt / 1e6:.1f}")
