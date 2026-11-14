#!/usr/bin/env python3
"""Corrupted framing (negative control): deliberately broken chunked
framing is rejected before dispatch and the daemon stays usable."""
import sys, socket
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import Conn, report

def probe(sock, payload):
    c = Conn(sock)
    try:
        c.send_all(payload)
        c.s.shutdown(socket.SHUT_WR)
        try:
            status, _, body = c.read_response()
            return status, body
        except (EOFError, ConnectionResetError, BrokenPipeError, socket.timeout):
            return None, b""
    finally:
        c.close()

def run(sock):
    failures = []
    cases = {
        "bad chunk hex": b"POST /x HTTP/1.1\r\nhost: x\r\ntransfer-encoding: chunked\r\n\r\nZZ\r\nhello\r\n0\r\n\r\n",
        "bad chunk order": b"POST /x HTTP/1.1\r\nhost: x\r\ntransfer-encoding: chunked\r\n\r\n5\r\nhelloXX0\r\n\r\n",
        "missing data CRLF": b"POST /x HTTP/1.1\r\nhost: x\r\ntransfer-encoding: chunked\r\n\r\n5\r\nhello",
    }
    for name, payload in cases.items():
        status, body = probe(sock, payload)
        if status is not None and not (400 <= status < 500):
            failures.append(f"{name}: got {status}, want refusal/close")
        if status == 200:
            failures.append(f"{name}: got 200")

    c = Conn(sock)
    try:
        status, _, body = c.roundtrip("GET", "/_ping")
        if (status, body) != (200, b"OK"):
            failures.append("daemon wedged after corrupted framing")
    finally:
        c.close()
    return report("corrupted-framing", not failures, "; ".join(failures))

if __name__ == "__main__":
    sys.exit(run(sys.argv[1]))
