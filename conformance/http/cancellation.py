#!/usr/bin/env python3
"""Cancellation: clients that hang up mid-request do not wedge the
connection loop or the daemon."""
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import Conn, report

def run(sock):
    failures = []
    for i in range(6):
        c = Conn(sock)
        try:
            c.send_all(b"POST /containers/create HTTP/1.1\r\nhost: x\r\ncontent-length: 9000\r\n\r\npartial")
        finally:
            c.close()
    c = Conn(sock)
    try:
        status, _, body = c.roundtrip("GET", "/_ping")
        if (status, body) != (200, b"OK"):
            failures.append(f"after cancellations -> {status} {body!r}")
    finally:
        c.close()
    return report("cancellation", not failures, "; ".join(failures))

if __name__ == "__main__":
    sys.exit(run(sys.argv[1]))
