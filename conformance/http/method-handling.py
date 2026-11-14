#!/usr/bin/env python3
"""Method handling: known routes answer their methods; unknown method or
route is a sane 4xx, never a 2xx, and the daemon stays up."""
import sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import Conn, report

def run(sock):
    failures = []
    c = Conn(sock)
    try:
        status, headers, body = c.roundtrip("GET", "/_ping")
        if status != 200 or body != b"OK":
            failures.append(f"GET /_ping -> {status} {body!r}")
        if "1.47" not in headers.get("api-version", ""):
            failures.append(f"missing/incorrect Api-Version header: {headers.get('api-version')!r}")
    finally:
        c.close()

    c = Conn(sock)
    try:
        status, headers, body = c.roundtrip("HEAD", "/_ping")
        if status != 200 or body != b"":
            failures.append(f"HEAD /_ping -> {status} with body {body!r}")
        # connection must stay usable
        status2, _, body2 = c.roundtrip("GET", "/_ping")
        if (status2, body2) != (200, b"OK"):
            failures.append("connection unusable after HEAD")
    finally:
        c.close()

    for method, path in [("DELETE", "/_ping"), ("GARBAGE", "/_ping"), ("POST", "/nope"), ("GET", "/v99/nope")]:
        c = Conn(sock)
        try:
            status, _, _ = c.roundtrip(method, path)
            if status in (200, 201, 204):
                failures.append(f"{method} {path} got {status}")
        finally:
            c.close()

    c = Conn(sock)
    try:
        status, _, body = c.roundtrip("GET", "/v1.47/_ping")
        if (status, body) != (200, b"OK"):
            failures.append(f"GET /v1.47/_ping -> {status} {body!r}")
    finally:
        c.close()

    c = Conn(sock)
    try:
        status, _, body = c.roundtrip("GET", "/_ping")
        if status != 200:
            failures.append("daemon wedged after unknown routes/methods")
    finally:
        c.close()
    return report("method-handling", not failures, "; ".join(failures))

if __name__ == "__main__":
    sys.exit(run(sys.argv[1]))
