#!/usr/bin/env python3
"""Framing rejection: contradictory or invalid Content-Length, and
Content-Length + Transfer-Encoding, are refused before dispatch;
identical repeated Content-Length values are accepted."""
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import Conn, report

def raw(sock, request):
    c = Conn(sock)
    try:
        c.send_all(request)
        try:
            return c.read_response()
        except (EOFError, ConnectionResetError, BrokenPipeError):
            return None
    finally:
        c.close()

def run(sock):
    failures = []
    # Identical repeated CL: accepted (body read, handler reached -> 4xx for garbage JSON).
    r = raw(sock, b"POST /containers/create HTTP/1.1\r\nhost: x\r\ncontent-length: 5\r\ncontent-length: 5\r\n\r\nhello")
    if r is None:
        failures.append("identical repeated CL: connection dropped")
    elif not (400 <= r[0] < 500) or b"bad request framing" in r[2]:
        failures.append(f"identical repeated CL: {r[0]} {r[2]!r}, want the handler's 4xx")

    # Differing CL: refused as framing, not silently accepted.
    r = raw(sock, b"POST /containers/create HTTP/1.1\r\nhost: x\r\ncontent-length: 5\r\ncontent-length: 6\r\n\r\nhello")
    # hyper (h12tiny path) refuses these itself, with an empty 400 body.
    if r is None:
        failures.append("differing CL: connection dropped without 400")
    elif r[0] != 400 or (r[2] and b"bad request framing" not in r[2]):
        failures.append(f"differing CL: {r[0]} {r[2]!r}, want 400")

    # CL + TE together: refused.
    r = raw(sock, b"POST /containers/create HTTP/1.1\r\nhost: x\r\ncontent-length: 5\r\ntransfer-encoding: chunked\r\n\r\n0\r\n\r\n")
    if r is None:
        failures.append("CL+TE: connection dropped without 400")
    elif r[0] != 400 or (r[2] and b"bad request framing" not in r[2]):
        failures.append(f"CL+TE: {r[0]} {r[2]!r}, want 400")

    # Non-numeric CL: refused, never read as zero.
    r = raw(sock, b"POST /containers/create HTTP/1.1\r\nhost: x\r\ncontent-length: five\r\n\r\nhello")
    if r is None:
        failures.append("non-numeric CL: connection dropped without 400")
    elif r[0] != 400 or (r[2] and b"bad request framing" not in r[2]):
        failures.append(f"non-numeric CL: {r[0]} {r[2]!r}, want 400")

    # Daemon is alive after all the rejections.
    c = Conn(sock)
    try:
        status, _, body = c.roundtrip("GET", "/_ping")
        if (status, body) != (200, b"OK"):
            failures.append("daemon wedged after framing rejections")
    finally:
        c.close()
    return report("conflicting-content-length", not failures, "; ".join(failures))

if __name__ == "__main__":
    sys.exit(run(sys.argv[1]))
