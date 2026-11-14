#!/usr/bin/env python3
"""Keep-alive and pipelining: sequential requests on one connection, and
two back-to-back requests answered in order without waiting for reads."""
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import Conn, report

def run(sock):
    failures = []
    c = Conn(sock)
    try:
        for i in range(3):
            status, _, body = c.roundtrip("GET", "/_ping")
            if (status, body) != (200, b"OK"):
                failures.append(f"request {i}: {status} {body!r}")
    finally:
        c.close()

    c = Conn(sock)
    try:
        c.send_all(b"GET /_ping HTTP/1.1\r\nhost: x\r\n\r\nGET /_ping HTTP/1.1\r\nhost: x\r\n\r\n")
        s1, _, b1 = c.read_response()
        s2, _, b2 = c.read_response()
        if (s1, b1) != (200, b"OK") or (s2, b2) != (200, b"OK"):
            failures.append(f"pipelined responses wrong: {(s1, b1)} {(s2, b2)}")
    finally:
        c.close()
    return report("keep-alive", not failures, "; ".join(failures))

if __name__ == "__main__":
    sys.exit(run(sys.argv[1]))
