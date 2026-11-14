#!/usr/bin/env python3
"""Expect: 100-continue (#134): the interim response is sent before the
body; clients that wait for it are not stuck."""
import sys, socket
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import Conn, report

def run(sock):
    failures = []
    # 1) Client waits for the interim response before sending the body.
    c = Conn(sock)
    try:
        c.s.settimeout(5)
        c.send_all(b"POST /containers/create HTTP/1.1\r\nhost: x\r\nexpect: 100-continue\r\ncontent-length: 7\r\n\r\n")
        interim = c.readline().decode("latin-1").rstrip("\r\n")
        if not interim.startswith("HTTP/1.1 100"):
            failures.append(f"no 100 Continue; first line: {interim!r}")
        c.readline()  # the interim's terminating blank line
        c.send_all(b"garbage")
        status, _, _ = c.read_response()
        if not (400 <= status < 500):
            failures.append(f"after 100-continue flow -> {status}, want 4xx for garbage")
    except socket.timeout:
        failures.append("timed out waiting for 100 Continue")
    finally:
        c.close()

    # 2) Client sends the body without waiting (legal either way).
    c = Conn(sock)
    try:
        c.s.settimeout(5)
        c.send_all(b"POST /containers/create HTTP/1.1\r\nhost: x\r\nexpect: 100-continue\r\ncontent-length: 7\r\n\r\ngarbage")
        first = c.readline().decode("latin-1").rstrip("\r\n")
        if first.startswith("HTTP/1.1 100"):
            c.readline()  # the interim's terminating blank line
            status, _, body = c.read_response()
        else:
            # no interim, this was the final status line; read headers+body manually
            status = int(first.split(" ")[1])
            while True:
                line = c.readline()
                if line in (b"\r\n", b"\n"):
                    break
            body = b""
        if not (400 <= status < 500):
            failures.append(f"no-wait flow -> {status}, want 4xx")
    except socket.timeout:
        failures.append("no-wait flow timed out")
    finally:
        c.close()

    # 3) GET with Expect still gets its final answer (interim then 200).
    c = Conn(sock)
    try:
        c.s.settimeout(5)
        c.send_all(b"GET /_ping HTTP/1.1\r\nhost: x\r\nexpect: 100-continue\r\n\r\n")
        first = c.readline().decode("latin-1").rstrip("\r\n")
        if first.startswith("HTTP/1.1 100"):
            c.readline()  # the interim's terminating blank line
            status, _, body = c.read_response()
        else:
            status = int(first.split(" ")[1])
            headers = {}
            while True:
                line = c.readline()
                if line in (b"\r\n", b"\n"):
                    break
                k, _, v = line.partition(b":")
                if k:
                    headers[k.decode().strip().lower()] = v.decode().strip()
            if "content-length" in headers:
                body = c._read_exactly(int(headers["content-length"]))
            else:
                body = b""
        if (status, body) != (200, b"OK"):
            failures.append(f"GET /_ping with Expect -> {status} {body!r}")
    except socket.timeout:
        failures.append("GET with Expect timed out")
    finally:
        c.close()
    return report("expect-100-continue", not failures, "; ".join(failures))

if __name__ == "__main__":
    sys.exit(run(sys.argv[1]))
