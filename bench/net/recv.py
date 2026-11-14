#!/usr/bin/env python3
"""TCP receiver for the CTRS-17 net bench. Binds PORT, prints READY,
accepts connections, drains them in threads until N bytes arrived. The
rate is computed from the first accepted connection to the last byte.
Prints 'label bytes elapsed_s mbps'."""
import socket
import sys
import threading
import time

port = int(sys.argv[1])
nbytes = int(sys.argv[2])
label = sys.argv[3] if len(sys.argv) > 3 else "recv"
deadline = float(sys.argv[4]) if len(sys.argv) > 4 else 120

lock = threading.Lock()
state = {"total": 0, "t_first": None}

def drain(conn):
    with conn:
        while True:
            try:
                chunk = conn.recv(1 << 20)
            except socket.timeout:
                return
            if not chunk:
                return
            with lock:
                if state["t_first"] is None:
                    state["t_first"] = time.perf_counter()
                state["total"] += len(chunk)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", port))
s.listen(16)
s.settimeout(1)
print(f"READY {port}", flush=True)
t_end = time.perf_counter() + deadline
while state["total"] < nbytes and time.perf_counter() < t_end:
    try:
        conn, _ = s.accept()
    except socket.timeout:
        continue
    conn.settimeout(5)
    threading.Thread(target=drain, args=(conn,), daemon=True).start()
dt = time.perf_counter() - (state["t_first"] or time.perf_counter())
total = state["total"]
print(f"{label} {total} {dt:.3f} {total * 8 / dt / 1e6:.1f}")
s.close()
