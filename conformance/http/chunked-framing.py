#!/usr/bin/env python3
"""Chunked framing: zero-size chunk with trailer fields must be fully
consumed so the next request on the same connection parses cleanly
(the #134 trailer defect); chunk extensions are legal."""
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import Conn, report

def post_chunked(c, chunk_lines, trailers):
    body = b"".join(chunk_lines)
    hs = b"transfer-encoding: chunked\r\n"
    c.send_all(b"POST /containers/create HTTP/1.1\r\nhost: x\r\n" + hs + b"\r\n" + body + trailers)

def run(sock):
    failures = []
    # 1) Trailer fields present; the following pipelined request must parse.
    c = Conn(sock)
    try:
        post_chunked(c, [b"5;ext=1\r\n", b"hello\r\n", b"1\r\n", b"!\r\n", b"0\r\n"], b"x-checksum: abc123\r\nx-note: hello\r\n")
        # trailer section must end with the empty line
        c.send_all(b"\r\n")
        status, _, _ = c.read_response()
        # the garbage JSON body must 4xx, not hang and not 2xx
        if not (400 <= status < 500):
            failures.append(f"chunked create -> {status}, want 4xx")
        # next request on the same connection:
        status, _, body = c.roundtrip("GET", "/_ping")
        if (status, body) != (200, b"OK"):
            failures.append(f"next request after trailers -> {status} {body!r}")
    finally:
        c.close()

    # 2) Zero chunk with empty trailer section.
    c = Conn(sock)
    try:
        post_chunked(c, [b"0\r\n"], b"\r\n")
        status, _, _ = c.read_response()
        if not (400 <= status < 500):
            failures.append(f"empty-body chunked -> {status}, want 4xx")
        status, _, body = c.roundtrip("GET", "/_ping")
        if (status, body) != (200, b"OK"):
            failures.append("connection unusable after zero-chunk body")
    finally:
        c.close()
    return report("chunked-framing", not failures, "; ".join(failures))

if __name__ == "__main__":
    sys.exit(run(sys.argv[1]))
