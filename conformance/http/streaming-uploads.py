#!/usr/bin/env python3
"""Streaming uploads: the streamed path (/images/load) reads bodies larger
than the buffered cap; the daemon survives and stays usable.

Builds a real one-layer image archive (> 8 MiB) in memory; no network,
no pre-staged files."""
import io, json, sys, tarfile
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from common import Conn, report

def image_tar():
    layer = io.BytesIO()
    with tarfile.open(fileobj=layer, mode="w") as t:
        big = io.BytesIO(b"\0" * (9 << 20))
        info = tarfile.TarInfo("big.bin")
        info.size = 9 << 20
        t.addfile(info, big)
    layer_bytes = layer.getvalue()

    config = json.dumps({
        "architecture": "arm64",
        "os": "linux",
        "created": "2026-11-14T00:00:00Z",
        "config": {"Env": ["PATH=/usr/bin"], "Cmd": ["/bin/true"]},
        "rootfs": {"type": "layers", "diff_ids": ["sha256:00"]},
    }).encode()
    manifest = json.dumps([{"Config": "ctrs14.json", "RepoTags": ["ctrs14-http:latest"], "Layers": ["ctrs14-layer.tar"]}]).encode()

    outer = io.BytesIO()
    with tarfile.open(fileobj=outer, mode="w") as t:
        for name, data in [("ctrs14.json", config), ("ctrs14-layer.tar", layer_bytes), ("manifest.json", manifest)]:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return outer.getvalue()

def run(sock):
    failures = []
    body = image_tar()
    if len(body) <= (8 << 20):
        return report("streaming-uploads", False, f"staged image is only {len(body)} bytes; want > 8 MiB")

    c = Conn(sock)
    try:
        c.s.settimeout(120)
        req = b"POST /images/load HTTP/1.1\r\nhost: x\r\ncontent-length: %d\r\n\r\n" % len(body)
        c.send_all(req)
        for i in range(0, len(body), 1 << 20):
            c.send_all(body[i:i + (1 << 20)])
        status, headers, response = c.read_response()
        lowered = response.lower()
        if b"request body too large" in lowered:
            failures.append("streamed body was capped at the buffered limit")
        if status >= 400:
            failures.append(f"load answered {status}: {response[:200]!r}")
    except (BrokenPipeError, ConnectionResetError) as e:
        failures.append(f"daemon closed mid-stream: {e}")
    except socket.timeout:
        failures.append("streamed upload timed out")
    finally:
        c.close()

    c = Conn(sock)
    try:
        status, _, body_ = c.roundtrip("GET", "/_ping")
        if (status, body_) != (200, b"OK"):
            failures.append("daemon wedged after streamed upload")
    finally:
        c.close()
    return report("streaming-uploads", not failures, "; ".join(failures))

if __name__ == "__main__":
    sys.exit(run(sys.argv[1]))
