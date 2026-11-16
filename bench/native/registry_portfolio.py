"""Validate an OCI layout and serve its selected images through a pull-only API."""
import hashlib
import os
import stat
import time
from dataclasses import dataclass
import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit


DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
NAME = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*\Z")
OCI_INDEX = "application/vnd.oci.image.index.v1+json"
OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
DOCKER_INDEX = "application/vnd.docker.distribution.manifest.list.v2+json"
DOCKER_MANIFEST = "application/vnd.docker.distribution.manifest.v2+json"


def _regular_path(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f"symlink in layout path: {part}")
    if not path.is_file():
        raise ValueError(f"not a regular file: {path}")
    return path


@dataclass(frozen=True)
class VerifiedBlob:
    path: Path
    digest: str
    size: int
    identity: tuple

    def open(self):
        descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        stream = os.fdopen(descriptor, 'rb')
        if _identity(os.fstat(stream.fileno())) != self.identity:
            stream.close()
            raise ValueError('verified blob changed before transfer')
        return stream

    def metadata(self):
        if self.size > 8 * 1024 * 1024:
            raise ValueError('image metadata exceeds 8 MiB')
        with self.open() as stream:
            data = stream.read()
            if hashlib.sha256(data).hexdigest() != self.digest[7:]:
                raise ValueError('verified metadata changed')
            return data


def _identity(value):
    if not stat.S_ISREG(value.st_mode):
        raise ValueError('not a regular blob')
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)


def _read(path):
    path = _regular_path(path)
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('layout metadata exceeds 8 MiB')
    return path.read_bytes()


def _json(data):
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("OCI object must be a JSON object")
    return value


def _blob(root, descriptor):
    digest = descriptor.get("digest")
    size = descriptor.get("size")
    if not isinstance(digest, str) or not DIGEST.fullmatch(digest) or type(size) is not int or size < 0:
        raise ValueError("invalid OCI descriptor")
    path = _regular_path(root / "blobs" / "sha256" / digest[7:])
    checksum = hashlib.sha256()
    with path.open('rb') as stream:
        before = _identity(os.fstat(stream.fileno()))
        while chunk := stream.read(1024 * 1024):
            checksum.update(chunk)
        after = _identity(os.fstat(stream.fileno()))
    if before != after or after[2] != size or checksum.hexdigest() != digest[7:]:
        raise ValueError(f"OCI blob integrity failure: {digest}")
    return VerifiedBlob(path, digest, size, after)


def prepare_layout(layout, repositories):
    """Return immutable verified responses for {repository: OCI ref.name} selections."""
    root = Path(layout)
    if _json(_read(root / "oci-layout")).get("imageLayoutVersion") != "1.0.0":
        raise ValueError("unsupported OCI layout")
    index = _json(_read(root / "index.json"))
    if index.get("schemaVersion") != 2 or not isinstance(index.get("manifests"), list):
        raise ValueError("invalid OCI layout index")
    routes = {}
    selected = {}
    for name, ref in repositories.items():
        if not NAME.fullmatch(name) or not isinstance(ref, str) or not ref:
            raise ValueError("invalid repository selection")
        matches = [d for d in index["manifests"] if isinstance(d, dict) and
                   d.get("annotations", {}).get("org.opencontainers.image.ref.name") == ref]
        if len(matches) != 1:
            raise ValueError(f"expected one layout reference: {ref}")
        descriptor = matches[0]
        blob = _blob(root, descriptor)
        data = blob.metadata()
        media = descriptor.get("mediaType")
        if media in (OCI_INDEX, DOCKER_INDEX):
            image_index = _json(data)
            if image_index.get("schemaVersion") != 2 or not isinstance(image_index.get("manifests"), list):
                raise ValueError("invalid image index")
            candidates = [d for d in image_index["manifests"] if isinstance(d, dict) and
                          d.get("platform", {}).get("os") == "linux" and
                          d.get("platform", {}).get("architecture") == "arm64" and
                          d.get("platform", {}).get("variant", "v8") == "v8"]
            if len(candidates) != 1:
                raise ValueError("expected one linux/arm64 image")
            descriptor = candidates[0]
            blob = _blob(root, descriptor)
            data = blob.metadata()
            media = descriptor.get("mediaType")
        if media not in (OCI_MANIFEST, DOCKER_MANIFEST):
            raise ValueError("unsupported image manifest")
        manifest = _json(data)
        layers = manifest.get("layers")
        if manifest.get("schemaVersion") != 2 or not isinstance(layers, list) or len(layers) < 2:
            raise ValueError("expected a multilayer image")
        config_descriptor = manifest.get("config")
        if not isinstance(config_descriptor, dict) or not all(isinstance(layer, dict) for layer in layers):
            raise ValueError("invalid image descriptors")
        config = _json(_blob(root, config_descriptor).metadata())
        if config.get("os") != "linux" or config.get("architecture") != "arm64":
            raise ValueError("image config is not linux/arm64")
        digest = descriptor["digest"]
        routes[(name, "manifests", digest)] = (media, digest, blob)
        for item in [config_descriptor, *layers]:
            content = _blob(root, item)
            routes[(name, "blobs", item["digest"])] = ("application/octet-stream", item["digest"], content)
        selected[name] = digest
    if not selected:
        raise ValueError("empty portfolio")
    return Portfolio(routes, selected)


class Portfolio:
    def __init__(self, routes, manifests):
        self.routes = routes
        self.manifests = manifests
        self.transfers = []

    def handler(self):
        portfolio = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_HEAD(self):
                self.respond(False)

            def do_GET(self):
                self.respond(True)

            def respond(self, body):
                started = time.monotonic()
                path = urlsplit(self.path).path
                if path in ("/v2", "/v2/"):
                    self.send_response(200)
                    self.send_header("Docker-Distribution-Api-Version", "registry/2.0")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                parts = path.split("/")
                if len(parts) < 5 or parts[1] != "v2":
                    self.send_error(404)
                    return
                name = "/".join(parts[2:-2])
                key = (name, parts[-2], parts[-1])
                item = portfolio.routes.get(key)
                if item is None:
                    self.send_error(404)
                    return
                media, digest, blob = item
                self.send_response(200)
                self.send_header("Content-Type", media)
                self.send_header("Content-Length", str(blob.size))
                self.send_header("Docker-Content-Digest", digest)
                self.send_header("Docker-Distribution-Api-Version", "registry/2.0")
                self.end_headers()
                sent = 0
                complete = False
                try:
                    if body:
                        with blob.open() as stream:
                            while chunk := stream.read(65536):
                                count = self.wfile.write(chunk)
                                if count != len(chunk):
                                    raise ConnectionError('short registry write')
                                sent += count
                            if _identity(os.fstat(stream.fileno())) != blob.identity:
                                raise ValueError('verified blob changed during transfer')
                        if sent != blob.size:
                            raise ValueError('verified blob size changed during transfer')
                    complete = True
                finally:
                    portfolio.transfers.append({"repository": name, "kind": parts[-2],
                                                "method": self.command,
                                                "started_monotonic": started,
                                                "ended_monotonic": time.monotonic(),
                                                "digest": digest, "bytes": sent,
                                                "complete": complete,
                                                "byte_method": "completed body writes; failed-write partial bytes unknown"})

        return Handler


def prepare_pinned_portfolio(layout, contract):
    """Verify every selected manifest, config and diff ID against the pinned contract."""
    if contract.get('schema_version') != 1 or contract.get('fixture_version') != 'w8-v2-common-portfolio':
        raise ValueError('unsupported portfolio contract')
    images = contract.get('images')
    if not isinstance(images, dict) or not images:
        raise ValueError('empty pinned portfolio')
    portfolio = prepare_layout(layout, {name: image['layout_reference'] for name, image in images.items()})
    if portfolio.manifests != {name: image['manifest'] for name, image in images.items()}:
        raise ValueError('portfolio manifest differs from pin')
    for name, image in images.items():
        manifest = _json(portfolio.routes[(name, 'manifests', image['manifest'])][2].metadata())
        if manifest['config']['digest'] != image['config'] or len(manifest['layers']) != image['layer_count']:
            raise ValueError('portfolio config or layer count differs from pin')
        config = _json(portfolio.routes[(name, 'blobs', image['config'])][2].metadata())
        if config.get('rootfs') != {'type': 'layers', 'diff_ids': image['diff_ids']}:
            raise ValueError('portfolio diff IDs differ from pin')
    return portfolio


def serve(portfolio, port):
    """Construct a loopback server; its owner controls serving and shutdown."""
    return HTTPServer(("127.0.0.1", port), portfolio.handler())
