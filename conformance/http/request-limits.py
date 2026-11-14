#!/usr/bin/env python3
"""Request limits: oversized JSON bodies and oversized headers are refused
before dispatch, and the daemon answers the next connection."""
import sys, socket
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import Conn, report

def run(sock):
    failures = []
    # 1) Content-Length: 9 MiB on a JSON endpoint: refused before dispatch.
    c = Conn(sock)
    try:
        try:
            c.send_all(b"POST /containers/create HTTP/1.1\r\nhost: x\r\ncontent-length: 9437184\r\n\r\n" + b"x" * (9 << 20))
        except OSError:
            # The daemon refused early and closed; that is the refusal path.
            pass
        else:
            try:
                status, _, body = c.read_response()
                if status < 400:
                    failures.append(f"9 MiB body got a {status} response, want refusal")
            except (BrokenPipeError, ConnectionResetError, EOFError, socket.timeout):
                pass
    finally:
        c.close()

    # 2) Endless header line: capped, never a 2xx.
    c = Conn(sock)
    try:
        try:
            c.send_all(b"GET /_ping HTTP/1.1\r\nhost: x\r\nx-fill: " + b"a" * 500000 + b"\r\n\r\n")
        except OSError:
            pass
        else:
            try:
                status, _, _ = c.read_response()
                if status < 400:
                    failures.append(f"endless header got {status}, want refusal")
            except (BrokenPipeError, ConnectionResetError, EOFError, socket.timeout):
                pass
    finally:
        c.close()

    # 3) The daemon answers afterwards.
    c = Conn(sock)
    try:
        status, _, body = c.roundtrip("GET", "/_ping")
        if status != 200 or body != b"OK":
            failures.append(f"/_ping after limits answered {status} {body!r}")
    finally:
        c.close()
    return report("request-limits", not failures, "; ".join(failures))

if __name__ == "__main__":
    sys.exit(run(sys.argv[1]))
