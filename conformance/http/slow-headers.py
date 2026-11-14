#!/usr/bin/env python3
"""Slow headers: a byte-by-byte client must not be cut off; the server
answers once the head is complete."""
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import Conn, report

def run(sock):
    c = Conn(sock)
    try:
        c.send_byte_at_a_time(b"GET /_ping HTTP/1.1\r\nhost: x\r\n\r\n", delay=0.01)
        status, _, body = c.read_response()
        ok = (status, body) == (200, b"OK")
        return report("slow-headers", ok, f"{status} {body!r}")
    finally:
        c.close()

if __name__ == "__main__":
    sys.exit(run(sys.argv[1]))
