#!/usr/bin/env python3
"""Head-read deadline: a peer that connects and sends an incomplete head
is disconnected once the deadline passes (~10 s), without an answer."""
import sys
import time
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import Conn, report

def run(sock):
    c = Conn(sock, timeout=16.0)
    try:
        c.send_all(b"GET /_ping HTTP/1.1\r\nhost: x\r\n")  # head never completes
        t0 = time.time()
        try:
            data = c.s.recv(4096)
            closed = data == b""
        except TimeoutError:
            closed = None
        elapsed = time.time() - t0
        ok = closed is True and elapsed >= 9.0
        return report("head-timeout", ok, f"closed={closed} after={elapsed:.1f}s")
    finally:
        c.close()

if __name__ == "__main__":
    sys.exit(run(sys.argv[1]))
