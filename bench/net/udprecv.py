#!/usr/bin/env python3
"""UDP receiver for the CTRS-17 net bench: reads datagrams with a
per-socket timeout, counting arrivals. Exits when COUNT distinct
datagrams arrived or the timeout expires. Prints READY on bind, then
'label received lost loss_pct mbps'."""
import socket
import sys
import time

port = int(sys.argv[1])
count = int(sys.argv[2])
label = sys.argv[3] if len(sys.argv) > 3 else "udprecv"
size_hint = int(sys.argv[4]) if len(sys.argv) > 4 else 1024
timeout = float(sys.argv[5]) if len(sys.argv) > 5 else 120.0

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 << 20)
s.bind(("0.0.0.0", port))
s.settimeout(timeout)
print(f"READY {port}", flush=True)
seen = 0
t0 = time.perf_counter()
try:
    while seen < count:
        data, _ = s.recvfrom(size_hint + 64)
        seen += 1
        if seen % 500 == 0:
            print(f"progress {seen}", flush=True)
except socket.timeout:
    pass
dt = time.perf_counter() - t0
total = seen * size_hint
print(f"{label} {seen} {count - seen} {100 * (count - seen) / count:.2f} {total * 8 / dt / 1e6:.1f}")
