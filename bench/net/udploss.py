#!/usr/bin/env python3
"""UDP sender for the CTRS-17 net bench: emits N datagrams of SIZE bytes
with a sequence header, as fast as the socket allows (or at rate pps).
Prints 'label sent_bytes elapsed_s mbps'."""
import socket
import sys
import time

host = sys.argv[1]
port = int(sys.argv[2])
count = int(sys.argv[3])
size = int(sys.argv[4]) if len(sys.argv) > 4 else 1024
label = sys.argv[5] if len(sys.argv) > 5 else f"{host}:{port}"

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 << 20)
t0 = time.perf_counter()
for seq in range(count):
    payload = seq.to_bytes(8, "big") + b"\0" * max(0, size - 8)
    s.sendto(payload, (host, port))
dt = time.perf_counter() - t0
sent = count * size
print(f"{label} {sent} {dt:.3f} {sent * 8 / dt / 1e6:.1f}")
