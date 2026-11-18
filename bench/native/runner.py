#!/usr/bin/env python3
"""Native-workload benchmark runner for the ctrs performance campaign.

Drives real application fixtures (bench/native/fixtures) against two
engines — ctrs (fresh Virtualization.framework guest per data root) and
OrbStack (the pinned macOS competitor) — through the same docker CLI,
records pilot JSONL trials under .work/native-perf/, and confines cleanup
to fixture resources. Shared image/build caches are retained; dedicated
benchmark builders persist between trials. See README for remaining
qualification and resource-accounting limits.

Requires Python >= 3.11 (tomllib). See README.md.
"""

from __future__ import annotations

import sys

if __name__ == "__main__":
    sys.modules.setdefault("runner", sys.modules[__name__])

import argparse
import ownership
import watch_loop
import workspace
import collect
import resource_cells
import resource_cycles
import recovery_client
import recovery_trace
import ci_jobs
import w2_peer
from transfer import trial_w13
from fixtures.w4 import app as w4_fixture, latency as w4_latency
from fixtures.w2.v3 import planned_span
from contextlib import contextmanager, nullcontext
import base64
import concurrent.futures
import hashlib
import inspect
import json
import math
import os
import random
import re
import shlex
import shutil
import signal
import statistics
import tempfile
import threading
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    sys.exit("runner.py requires Python >= 3.11 (tomllib); e.g. python3.14")

BENCH = Path(__file__).resolve().parent
REPO = BENCH.parent.parent
WORK = REPO / ".work" / "native-perf"
RESULTS = WORK / "results"
FIXTURES = BENCH / "fixtures"
COLLECT = BENCH / "collect.py"
CASES_FILE = BENCH / "cases.toml"

CTRS_BIN = REPO / "target" / "release" / "ctrs"
ORBSTACK_SOCK = os.environ.get(
    "NP_ORBSTACK_SOCK", os.path.expanduser("~/.orbstack/run/docker.sock")
)

# Attribution: on this host the ctrs guest VM is the
# com.apple.Virtualization.VirtualMachine XPC service; OrbStack's VM
# lives inside "OrbStack Helper". The bare `virtualization` token was
# removed from the orbstack pattern — it used to double-count the
# ctrs VM into orbstack trials (both engines' VMs stay warm).
MATCH_PATTERNS = {
    "ctrs": r"(^|/)ctrs$|ctrs-init|com\.apple\.Virtualization\.VirtualMachine",
    "orbstack": r"orbstack|orb-",
}

SERVICE_IMAGES = ["postgres:17-alpine", "redis:7-alpine", "python:3.13-slim",
                  "gcc:14.2.0-bookworm"]
W1_DIR = FIXTURES / "w1"
API_DOCKERFILE_DIR = W1_DIR / "api"
COMPOSE_FILE = W1_DIR / "compose.yaml"
LOAD_PY = FIXTURES / "w2" / "load.py"
RATE_LOAD_PY = FIXTURES / "w2" / "v3.py"
W8_DIR = FIXTURES / "w8"
W11_CHURN_IMAGE = "python:3.13-slim"
W3_FIXTURE_VERSION = "w3-v3-pinned-commit-latency"
W6_IMAGE = "gcc:14.2.0-bookworm"
W6_RUST_IMAGE = "rust:1.100.0-bookworm"
W6_DIR = FIXTURES / "w6"
# Checksum-pinned upstream sources for W6 (the "pinned Rust app plus
# another language" cell). Archives are gitignored (too large for the
# repo); ensure_pinned_source fetches them on demand and refuses
# anything that does not match the pinned sha256. Hashes verified
# 2026-11-15: zlib against the official madler/zlib v1.3.1 GitHub
# release asset; hyperfine against the sharkdp v2.0.0 codeload archive.
W6_ZLIB_SOURCE = {
    "url": "https://github.com/madler/zlib/releases/download/v1.3.1/"
           "zlib-1.3.1.tar.gz",
    "file": "zlib-1.3.1.tar.gz",
    "sha256": "9a93b2b7dfdac77ceba5a558a580e74667dd6fede4585b91eefb60f03b72df23",
}
W6_RUST_SOURCE = {
    "url": "https://codeload.github.com/sharkdp/hyperfine/tar.gz/"
           "refs/tags/v2.0.0",
    "file": "hyperfine-2.0.0.tar.gz",
    "sha256": "f4b71df3c78e4cf752ca6fb6ebc4b025f7ea6a5ca5c48fea75f8a1fdb4c7d721",
}
W6_SOURCES = {"zlib": W6_ZLIB_SOURCE, "rust": W6_RUST_SOURCE}

W7_DIR = FIXTURES / "w7"
W7_PYTHON_IMAGE = "python:3.13-slim"
W7_DEBIAN_IMAGE = "debian:bookworm-slim"
# W7 real apps: pinned upstream sources fetched on demand. hyperfine
# reuses the W6 pin (same archive, fetched into W7_DIR for locality).
# httpie hash is the PyPI-published sdist digest for 3.2.4.
W7_HTTPIE_SOURCE = {
    "url": "https://files.pythonhosted.org/packages/3e/bb/"
           "aefb0abbdbadeb9e8e7f04fb0f1942bc084f4215bf8dc729236153d09e1e/"
           "httpie-3.2.4.tar.gz",
    "file": "httpie-3.2.4.tar.gz",
    "sha256": "302ad436c3dc14fd0d1b19d4572ef8d62b146bcd94b505f3c2521f701e2e7a2a",
}
W7_SOURCES = {"hyperfine": W6_RUST_SOURCE, "httpie": W7_HTTPIE_SOURCE}


def ensure_pinned_source(source: dict, dest_dir: Path) -> Path:
    """Return a pinned source archive, fetching it if absent or corrupt.

    A present file with the wrong checksum is replaced only after the
    download verifies; a corrupt fetch never overwrites a good archive.
    """
    target = dest_dir / source["file"]
    if target.is_file() and sha256_file(target) == source["sha256"]:
        return target
    dest_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest_dir / (source["file"] + ".part")
    try:
        with urllib.request.urlopen(source["url"], timeout=300) as r, \
                tmp.open("wb") as out:
            shutil.copyfileobj(r, out, length=1024 * 1024)
        if sha256_file(tmp) != source["sha256"]:
            raise RuntimeError(
                f"pinned source {source['file']} checksum mismatch; "
                "refusing to use it")
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)
    return target


# Attribution control (campaign Phase B.2): a docker-container BuildKit
# builder usable on *both* engines, so W6/W7 can separate engine runtime
# from builder topology. The image is ctrs's pinned buildkit digest so
# both sides run the same BuildKit version.
DC_BUILDER_IMAGE = ("moby/buildkit@sha256:"
                    "aa632b921ef07411d2cb77292cd34213d4f7b384001d6fceef1e1f25bf9752bb")
W4_IMAGE = "redis@sha256:7f7d30b7fdd09467bac58198a1f166dd69789d348d4fe859cccb20e0cf287fbe"
W4_LATENCY_VERSION = "w4-v4-boot-clock"
W4_LATENCY_IMAGE = "np-w4-events:v4"
W10_FIXTURE_VERSION = "w10-v4-recovery"
W4_FIXED_WORK = {"jobs": w4_fixture.JOBS, "events": w4_fixture.JOBS * w4_fixture.EVENTS,
                 "artifacts": w4_fixture.JOBS * len(w4_fixture.filenames(0))}
# Holdout: a real third-party app never used for tuning — Gitea +
# Postgres. REST API seed/read workload plus git smart-HTTP clones over
# the published port. Executed once per engine at gates via the
# `holdout` subcommand; excluded from the scored W-matrix.
HOLDOUT_DIR = FIXTURES / "holdout"
HOLDOUT_COMPOSE = HOLDOUT_DIR / "compose.yaml"
HOLDOUT_IMAGE = "gitea/gitea:1.24.7"
HOLDOUT_USER = "npadmin"
HOLDOUT_PASSWORD = "npadmin-pass-123"
W3_PASSWORD = "npw3pw"
W3_TXS = 300
# Deterministic transaction mix: each tx inserts one row and updates a
# counter row; the final SELECT gives the runner an exact checksum.
W3_SQL = """\
CREATE TABLE IF NOT EXISTS npw3_events (
    id bigserial PRIMARY KEY, k int NOT NULL, v text NOT NULL);
CREATE TABLE IF NOT EXISTS npw3_meta (k text PRIMARY KEY, n bigint NOT NULL);
INSERT INTO npw3_meta VALUES ('txs', 0) ON CONFLICT DO NOTHING;
"""


def _w3_tx_sql(i: int) -> str:
    return (rf"BEGIN\; INSERT INTO npw3_events(k,v) VALUES ({i}, 'v{i}')\;"
            r" UPDATE npw3_meta SET n = n + 1 WHERE k = 'txs'\; COMMIT;" + "\n")


def _w3_commit_timings(stdout: str) -> list[float]:
    lines = stdout.splitlines()
    if lines[:2] != ["SET", "Timing is on."] or len(lines) != 2 + 5 * W3_TXS:
        raise ValueError(f"expected {W3_TXS} complete transaction timing receipts")
    latencies = []
    for offset in range(2, len(lines), 5):
        timing = re.fullmatch(r"Time: (\d+\.\d{3}) ms(?: \([^\n]+\))?", lines[offset + 4])
        if lines[offset:offset + 4] != ["BEGIN", "INSERT 0 1", "UPDATE 1", "COMMIT"] or not timing:
            raise ValueError(f"invalid transaction timing receipt {(offset - 2) // 5 + 1}")
        elapsed = float(timing[1])
        if not math.isfinite(elapsed):
            raise ValueError("nonfinite transaction timing")
        latencies.append(elapsed)
    return latencies


# ~0.6 s of CPU work inside the container, deterministic across engines
# (same image, same interpreter); argv[1] is the job marker.
W11_CHURN_WORK = (
    "import sys,time,hashlib\n"
    "end=time.monotonic()+0.6\n"
    "h=hashlib.sha256()\n"
    "i=0\n"
    "while time.monotonic()<end:\n"
    "    h.update(str(i).encode());i+=1\n"
    "print('npw11-'+sys.argv[1]+'-ok-'+h.hexdigest()[:12])\n"
)

# W8: a per-engine local OCI registry (registry:2 on a published loopback
# port, content in a named volume so it survives ctrs VM restarts) serves a
# portfolio of self-contained "relocated" images — scratch images holding a
# full copy of a real base rootfs, so pulls never dedup against cached base
# layers. `verify` runs inside the pulled image as the correctness probe.
REGISTRY_IMAGE = "registry:2"
REGISTRY_STATE = WORK / "registry-state.json"
PORTFOLIO_FILE = WORK / "w8-portfolio.json"
W8_IMAGES = [
    {"name": "busybox", "dir": "busybox",
     "verify": ["/bin/busybox", "echo", "npw8-ok"], "expect": "npw8-ok"},
    {"name": "redis", "dir": "redis",
     "verify": ["/usr/local/bin/redis-server", "--version"],
     "expect": "Redis server"},
    {"name": "py", "dir": "py",
     "verify": ["/usr/local/bin/python3", "-c", "print('npw8-ok')"],
     "expect": "npw8-ok"},
    {"name": "pg", "dir": "pg",
     "verify": ["/usr/local/bin/postgres", "--version"],
     "expect": "PostgreSQL"},
]

CHECK_COMPONENTS = {
    "w1": ("test_w1", "test_safety"),
    "uprobes": ("test_w2_uprobes", "test_uprobe_trace", "test_safety"),
    "w2": ("test_w2", "test_cpu_profile", "test_mixed_cycle", "test_sampler_pilot", "test_collect", "test_reporting", "test_safety"),
    "w5": ("test_w5", "test_resource_cycles", "test_reporting", "test_safety"),
    "w8": ("test_w8_benchmark", "test_w8_prepare", "test_w8_under_pull",
           "test_registry_portfolio", "test_registry_variant",
           "test_registry_variant_pilot", "test_safety"),
    "resources": ("test_resource_cells", "test_resource_cycles", "test_resource_pilot", "test_wal_trace_guest",
                  "test_collect", "test_storage_space",
                  "test_system_df_cache", "test_reporting", "test_safety"),
}
CHECK_TIMEOUT_SECONDS = 60

HEALTH_DEADLINE_S = 240.0
# Health/readiness polling granularity. Kept fine (0.1 s): coarser
# intervals quantize startup/recovery measurements and can invert the
# winner when one engine's faster API return lands early in a poll cycle.
POLL_INTERVAL_S = 0.1


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def find_docker() -> str:
    for cand in ("docker", "/opt/homebrew/bin/docker",
                 os.path.expanduser("~/.orbstack/bin/docker")):
        path = shutil.which(cand) if "/" not in cand else (
            cand if os.path.exists(cand) else None)
        if path:
            return path
    sys.exit("docker CLI not found on PATH or in known locations")


# Offline manifest validation/reporting must work without a Docker install.
# Runtime commands resolve this only after validating their inputs.
DOCKER: str | None = None


def api_tag() -> str:
    h = hashlib.sha256()
    for name in ("Dockerfile", "app.py", "requirements.txt"):
        h.update((API_DOCKERFILE_DIR / name).read_bytes())
    return f"np1-{h.hexdigest()[:12]}"


API_TAG = api_tag()


def load_cases() -> dict:
    with open(CASES_FILE, "rb") as f:
        return tomllib.load(f)


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as src:
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_sparse_file(path: Path) -> str | None:
    """Content hash of a sparse file that skips holes: sha256 over the
    file size plus each allocated extent's (offset, length, content
    digest). The 1 TiB data.img template is almost entirely holes, so a
    full read would hash ~1 TiB of zeros for minutes; extents are a few
    GiB at most. Values are NOT comparable to `sha256_file` output —
    used only for `guest_data_sha256`, whose asset already changed.
    Falls back to a full read where SEEK_HOLE/SEEK_DATA is unsupported."""
    if not path.is_file():
        return None
    size = path.stat().st_size
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return sha256_file(path)
    try:
        digest = hashlib.sha256(b"sparse-extent-v1")
        digest.update(size.to_bytes(8, "little"))
        pos = 0
        extents = 0
        while pos < size:
            try:
                start = os.lseek(fd, pos, os.SEEK_DATA)
            except OSError:
                break
            if start >= size:
                break
            try:
                end = os.lseek(fd, start, os.SEEK_HOLE)
            except OSError:
                end = size
            end = min(end, size)
            if end <= start:
                break
            inner = hashlib.sha256()
            remaining = end - start
            os.lseek(fd, start, os.SEEK_SET)
            while remaining > 0:
                chunk = os.read(fd, min(1024 * 1024, remaining))
                if not chunk:
                    break
                inner.update(chunk)
                remaining -= len(chunk)
            digest.update(start.to_bytes(8, "little"))
            digest.update((end - start).to_bytes(8, "little"))
            digest.update(inner.digest())
            extents += 1
            pos = end
        if extents == 0 and size > 0:
            # No data extents reported for a non-empty file: treat as
            # unsupported and hash fully rather than record a weak ID.
            return sha256_file(path)
        return digest.hexdigest()
    except OSError:
        return sha256_file(path)
    finally:
        os.close(fd)


def guest_provenance() -> dict:
    """Hashes of the guest kernel/initramfs/data disk — the guest-side
    identity behind `ctrs_binary_sha256`. data.img is a 1 TiB sparse
    file hashed by allocated extent (`sha256_sparse_file`), so results
    are cached by stat signature and only rehashed when the asset is
    rebuilt."""
    assets = {"guest_kernel_sha256": "Image",
              "guest_initramfs_sha256": "initramfs.cpio",
              "guest_data_sha256": "data.img"}
    cache_path = WORK / "guest-asset-hashes.json"
    try:
        cache = json.loads(cache_path.read_text())
    except Exception:
        cache = {}
    guest = REPO / os.environ.get("CTRS_GUEST_DIR", "guest/out")
    out, dirty = {}, False
    for key, name in assets.items():
        path = guest / name
        entry = cache.get(name)
        st = path.stat() if path.is_file() else None
        if (st is not None and isinstance(entry, dict)
                and entry.get("device") == st.st_dev
                and entry.get("inode") == st.st_ino
                and entry.get("size") == st.st_size
                and entry.get("mtime_ns") == st.st_mtime_ns):
            out[key] = entry["sha256"]
            continue
        digest = (sha256_sparse_file(path) if name == "data.img"
                  else sha256_file(path))
        out[key] = digest
        if st is not None:
            cache[name] = {"device": st.st_dev, "inode": st.st_ino,
                           "size": st.st_size, "mtime_ns": st.st_mtime_ns,
                           "sha256": digest}
            dirty = True
    if dirty:
        try:
            cache_path.write_text(json.dumps(cache, indent=2))
        except OSError:
            pass
    return out


GUEST_COUNTER_METHOD = ("guest-wide /proc/stat and /proc/interrupts read from an owned, idle, "
                        "privileged, network-less reader of the API image outside the workload "
                        "phase and the API cpu.stat delta; diagnostic only")


def parse_guest_kernel_counters(text: str) -> dict:
    stat: dict = {}
    interrupts: dict = {}
    cpus = 0
    for line in text.splitlines():
        fields = line.split()
        if not fields:
            continue
        if all(field.startswith("CPU") for field in fields):
            cpus = len(fields)
        elif fields[0] == "cpu":
            stat["cpu_ticks"] = dict(zip(
                ("user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal"),
                map(int, fields[1:9])))
        elif fields[0] in ("ctxt", "intr", "processes") and fields[1].isdigit():
            stat[fields[0]] = int(fields[1])
        elif cpus and fields[0].endswith(":") and fields[1:1 + cpus] and all(
                value.isdigit() for value in fields[1:1 + cpus]):
            interrupts[fields[0][:-1]] = {
                "total": sum(map(int, fields[1:1 + cpus])),
                "description": " ".join(fields[1 + cpus:])}
    if "cpu_ticks" not in stat or "ctxt" not in stat or not interrupts:
        raise ValueError("incomplete guest /proc/stat or /proc/interrupts")
    return {"stat": stat, "interrupts": interrupts}


def start_guest_counter_reader(engine: "Engine", name: str, owner: str, api_id: str) -> str | None:
    """Docker and ctrs both mask /proc/interrupts in unprivileged containers,
    so a separate privileged reader exposes it. Returns an error that keeps
    the counters missing, never zero; the caller always cleans up `name`."""
    try:
        info, = json.loads(engine.sh(["inspect", api_id], timeout=30).stdout)
        engine.sh(["run", "-d", "--pull", "never", "--privileged", "--network", "none",
                   "--name", name, "--label", "dev.ctrs.campaign.run=" + owner,
                   "--entrypoint", "python", info["Image"], "-c",
                   "import time; time.sleep(86400)"], timeout=60)
        return None
    except Exception as exc:
        return f"counter reader: {exc}"


def guest_kernel_counters(engine: "Engine", container: str, reader_error: str | None) -> dict:
    if reader_error is not None:
        return {"error": reader_error}
    try:
        cp = engine.sh(["exec", container, "cat", "/proc/stat", "/proc/interrupts"], timeout=30)
        if cp.returncode != 0:
            raise ValueError(f"exit {cp.returncode}: {cp.stderr.strip()[:200]}")
        return parse_guest_kernel_counters(cp.stdout)
    except Exception as exc:
        return {"error": str(exc)}


def guest_kernel_counter_delta(before: dict, after: dict) -> dict:
    result = {"before": before, "after": after, "method": GUEST_COUNTER_METHOD}
    if "error" in before or "error" in after:
        result["delta"] = None
        return result
    ticks = {key: after["stat"]["cpu_ticks"][key] - value
             for key, value in before["stat"]["cpu_ticks"].items()}
    stat = {key: after["stat"][key] - before["stat"][key]
            for key in ("ctxt", "intr", "processes")
            if key in before["stat"] and key in after["stat"]}
    interrupts = {label: after["interrupts"][label]["total"] - row["total"]
                  for label, row in before["interrupts"].items()
                  if label in after["interrupts"]}
    result["delta"] = {"cpu_ticks": ticks, **stat, "interrupts": interrupts}
    return result


RESOURCE_LANES = ("matched", "installed-default")


def fixture_sha256() -> str:
    digest = hashlib.sha256()
    for path in sorted(FIXTURES.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        digest.update(str(path.relative_to(FIXTURES)).encode() + b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def validate_manifest() -> dict:
    """Parse contracts before any engine access; hashes are provenance,
    not a claim that mutable image tags or the pilot suite are frozen."""
    cases = load_cases()
    ids = [case["id"] for case in cases.get("case", [])]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("case IDs must be nonempty and unique")
    with (BENCH / "assets.lock").open("rb") as src:
        assets = tomllib.load(src)
    json.loads((BENCH / "schema.json").read_text())
    return {"cases": ids, "asset_freeze_status": assets["freeze"]["status"],
            "cases_sha256": sha256_file(CASES_FILE),
            "assets_sha256": sha256_file(BENCH / "assets.lock"),
            "fixture_sha256": fixture_sha256()}


def workload_id(run_id: str, case_id: str, pair_id: int | None,
                sequence: int) -> str:
    # Both engines in a pair get exactly the same inputs. Another pair
    # gets a different stamp, so W6 cannot silently become a cache hit.
    sample = f"pair-{pair_id}" if pair_id is not None else f"trial-{sequence}"
    return f"{run_id}:{case_id}:{sample}"


_ORB_RESOURCES: tuple[int, int] | None = None
# MiB added to the OrbStack-derived ceiling so the ctrs guest's
# MemTotal (ceiling minus kernel/initramfs reservation) matches
# OrbStack's reported MemTotal within the reporter's 1% pair gate.
CTRS_GUEST_RESERVE_MIB = 950


def orbstack_resources() -> tuple[int, int] | None:
    """(vCPUs, memory MiB) OrbStack gives its VM, for resource-matched
    ctrs benchmarking. `docker info` NCPU/MemTotal reflect the VM's
    allocation; cached for the process."""
    global _ORB_RESOURCES
    if _ORB_RESOURCES is not None:
        return _ORB_RESOURCES
    try:
        env = os.environ.copy()
        env["DOCKER_HOST"] = f"unix://{ORBSTACK_SOCK}"
        env.pop("DOCKER_CONTEXT", None)
        cp = subprocess.run(
            [DOCKER, "info", "--format", "{{.NCPU}} {{.MemTotal}}"],
            env=env, capture_output=True, text=True, timeout=20)
        ncpu_s, mem_s = cp.stdout.split()
        ncpu, mem_b = int(ncpu_s), int(mem_s)
        _ORB_RESOURCES = (ncpu, mem_b >> 20)
    except Exception:
        _ORB_RESOURCES = None
    return _ORB_RESOURCES


class Engine:
    """One competitor engine: socket, env, and (for ctrs) daemon lifecycle."""

    def __init__(self, name: str, run_id: str, fresh_dir: Path | None = None,
                 resource_lane: str = "matched"):
        if name not in ("ctrs", "orbstack"):
            raise ValueError(f"unknown engine {name!r}")
        if resource_lane not in RESOURCE_LANES:
            raise ValueError(f"unknown resource lane {resource_lane!r}")
        self.resource_lane = resource_lane
        self.name = name
        self.run_id = run_id
        self.proc: subprocess.Popen | None = None
        self.recovery_root: Path | None = None
        if name == "orbstack":
            self.dir = None
            self.socket = f"unix://{ORBSTACK_SOCK}"
        else:
            base = fresh_dir or (WORK / "engines" / "ctrs-warm")
            self.dir = Path(base)
            (self.dir / "run").mkdir(parents=True, exist_ok=True)
            self.socket = f"unix://{self.dir / 'run' / 'docker.sock'}"
        endpoint_hash = hashlib.sha256(self.socket.encode()).hexdigest()[:12]
        self.builder_name = f"np-dc-{self.name}-{endpoint_hash}"
        self.buildx_config = WORK / "buildx" / f"{self.name}-{endpoint_hash}"

    @classmethod
    def for_recovery(cls, run_id: str):
        parent = WORK / "engines"
        parent.mkdir(parents=True, exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix="w10-", dir=parent))
        if len(os.fsencode(root / "run/docker.sock")) >= 104:
            raise ValueError("W10 recovery Unix socket path is too long")
        engine = cls("ctrs", run_id, fresh_dir=root)
        engine.recovery_root = root
        return engine

    def env(self, extra: dict | None = None) -> dict:
        env = os.environ.copy()
        # The credential helper and compose plugin live next to docker or in
        # ~/.orbstack/bin; make sure subprocesses can find them even when the
        # caller's PATH is minimal.
        extra_path = [os.path.dirname(DOCKER), "/usr/local/bin",
                      "/opt/homebrew/bin",
                      os.path.expanduser("~/.orbstack/bin")]
        env["PATH"] = os.pathsep.join(extra_path + [env.get("PATH", "")])
        env["DOCKER_HOST"] = self.socket
        env.pop("DOCKER_CONTEXT", None)
        env.pop("DOCKER_TLS_VERIFY", None)
        env.pop("COMPOSE_PROJECT_NAME", None)
        env.pop("COMPOSE_FILE", None)
        # Builder selection is client-global unless isolated explicitly.
        # Keep credentials/plugins in the normal Docker config, but never
        # select, reuse, or prune the user's buildx builders.
        env.pop("BUILDX_BUILDER", None)
        env["BUILDX_CONFIG"] = str(self.buildx_config)
        if extra:
            env.update(extra)
        return env

    def sh(self, args: list[str], env_extra: dict | None = None,
           timeout: float = 120, check: bool = True) -> subprocess.CompletedProcess:
        cp = subprocess.run(
            [DOCKER, *args], env=self.env(env_extra),
            capture_output=True, text=True, timeout=timeout,
        )
        if check and cp.returncode != 0:
            raise RuntimeError(
                f"docker {' '.join(args[:3])}… failed ({cp.returncode}): "
                f"{(cp.stderr or cp.stdout).strip()[:400]}")
        return cp

    def compose(self, project: str, args: list[str],
                env_extra: dict | None = None,
                timeout: float = 300, *, override: Path | None = None) -> subprocess.CompletedProcess:
        files = ["-f", str(COMPOSE_FILE)]
        if override is not None:
            files += ["-f", str(override)]
        return self.sh(
            ["compose", *files, "-p", project, *args],
            env_extra=env_extra, timeout=timeout, check=False)

    def server_version(self) -> str:
        cp = self.sh(["version", "--format", "{{.Server.Version}}"],
                     timeout=30)
        return cp.stdout.strip()

    def system_df(self) -> dict | None:
        """Raw-byte `GET /system/df` snapshot for allocated-storage
        accounting. Fields the engine does not report stay absent;
        callers must treat missing keys as unknown, not zero."""
        try:
            import http.client
            import json as _json
            import socket as _socket

            class _UnixHTTP(http.client.HTTPConnection):
                def __init__(self, path: str):
                    super().__init__("localhost")
                    self._path = path

                def connect(self):
                    self.sock = _socket.socket(
                        _socket.AF_UNIX, _socket.SOCK_STREAM)
                    self.sock.settimeout(30)
                    self.sock.connect(self._path)

            path = self.socket.removeprefix("unix://")
            conn = _UnixHTTP(path)
            conn.request("GET", "/system/df")
            resp = conn.getresponse()
            if resp.status != 200:
                return None
            data = _json.loads(resp.read())
            conn.close()
            out = {}
            if isinstance(data.get("LayersSize"), int):
                out["layers_size_bytes"] = data["LayersSize"]
            images = data.get("Images") or []
            if images:
                out["images_size_bytes"] = sum(
                    i.get("Size") or 0 for i in images)
                out["images_shared_bytes"] = sum(
                    i.get("SharedSize") or 0 for i in images)
            containers = data.get("Containers") or []
            if containers:
                out["containers_size_bytes"] = sum(
                    (c.get("SizeRw") or 0) + (c.get("SizeRootFs") or 0)
                    for c in containers)
            volumes = data.get("Volumes") or []
            if volumes:
                known = [(v.get("UsageData") or {}).get("Size")
                         for v in volumes]
                known = [s for s in known if isinstance(s, int) and s >= 0]
                if len(known) == len(volumes):
                    out["volumes_size_bytes"] = sum(known)
            cache = data.get("BuildCache") or []
            if cache:
                out["build_cache_entries"] = len(cache)
                sizes = [b.get("Size") for b in cache]
                if all(isinstance(size, int) and not isinstance(size, bool) and size >= 0
                       for size in sizes):
                    out["build_cache_size_bytes"] = sum(sizes)
            return out or None
        except Exception:
            return None

    def ensure_up(self, timeout: float = 300.0) -> None:
        if self.name == "orbstack":
            self.sh(["version"], timeout=30)
            return
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.sh(["version"], timeout=15)
                return
            except Exception:
                pass
        if self.proc is not None:
            self.stop()
        # An orphaned daemon from an earlier runner invocation may still
        # hold this engine dir; if its socket answers, adopt it rather
        # than spawning into the data-root lock.
        try:
            self.sh(["version"], timeout=10)
            return
        except Exception:
            pass
        env = os.environ.copy()
        env["CTRS_DATA_DIR"] = str(self.dir / "data")
        env["CTRS_SOCKET"] = str(self.dir / "run" / "docker.sock")
        # Diag state (logs, crashes, vm.json) defaults to
        # ~/.local/share/ctrs; keep bench engines out of the user's state.
        env["CTRS_STATE_DIR"] = str(self.dir / "state")
        # Resource parity: ctrs defaults to 2 vCPUs / 8 GiB while
        # OrbStack allocates ~all host cores. Give the bench VM the same
        # vCPU count and memory ceiling OrbStack reports so CPU-bound
        # cells compare engines, not allocations. Explicit ambient
        # CTRS_CPUS/CTRS_MEMORY_MIB still win.
        # The ceiling is not the guest-visible MemTotal: the pinned
        # guest kernel+initramfs reserve ~891 MiB, so match OrbStack's
        # reported MemTotal by adding CTRS_GUEST_RESERVE_MIB. Verified
        # 2026-11-15: +950 MiB lands guest MemTotal within 0.1% of
        # OrbStack (46,324,359,168 vs 46,278,524,928 bytes). If guest
        # assets change the reservation, pairs fail closed on the
        # reporter's 1% budget gate rather than silently mismatching.
        res = orbstack_resources() if self.resource_lane == "matched" else None
        if self.resource_lane == "installed-default":
            overrides = sorted(key for key in ("CTRS_CPUS", "CTRS_MEMORY_MIB") if key in env)
            if overrides:
                raise ValueError(f"installed-default lane forbids {', '.join(overrides)}")
        if res is not None:
            env.setdefault("CTRS_CPUS", str(res[0]))
            env.setdefault("CTRS_MEMORY_MIB",
                           str(res[1] + CTRS_GUEST_RESERVE_MIB))
        log = open(self.dir / "daemon.log", "ab")
        deadline = time.monotonic() + timeout
        # A previous daemon can still hold the data-root lock while its VM
        # finishes shutting down; "in use by another engine" is transient,
        # so retry the spawn until the deadline instead of failing fast.
        last_tail = b""
        while time.monotonic() < deadline:
            if self.proc is None:
                log = open(self.dir / "daemon.log", "ab")
                self.proc = subprocess.Popen(
                    [str(CTRS_BIN), "daemon"], env=env,
                    stdout=log, stderr=subprocess.STDOUT, cwd=REPO)
            if self.proc.poll() is not None:
                last_tail = (self.dir / "daemon.log").read_bytes()[-2000:]
                if b"in use by another engine" in last_tail:
                    time.sleep(2.0)
                    log = open(self.dir / "daemon.log", "ab")
                    self.proc = subprocess.Popen(
                        [str(CTRS_BIN), "daemon"], env=env,
                        stdout=log, stderr=subprocess.STDOUT, cwd=REPO)
                    continue
                raise RuntimeError(
                    f"ctrs daemon exited {self.proc.returncode}: "
                    f"{last_tail.decode(errors='replace')}")
            try:
                self.sh(["version"], timeout=10)
                return
            except Exception:
                time.sleep(0.5)
        self.stop()
        raise TimeoutError("ctrs daemon did not answer docker version")

    def stop(self) -> None:
        if self.proc is not None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
            self.proc = None


def project_name(run_id: str, engine: str, case: str) -> str:
    raw = f"np{run_id}{engine}{case}".lower()
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in raw)[:48]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http_json(url: str, timeout: float = 5.0):
    """Return (status, parsed-or-raw body). Never raises on HTTP errors."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        body = e.read()
        status = e.code
    except Exception as e:
        return 0, {"transport_error": str(e)}
    try:
        return status, json.loads(body)
    except Exception:
        return status, body.decode(errors="replace")[:500]


@dataclass(frozen=True)
class Sampler:
    process: subprocess.Popen
    trace: Path
    stderr: Path


class SamplingMode(Enum):
    PERIODIC = 'periodic'
    BOUNDARIES = 'boundaries'


def start_sampler(engine: Engine, trial_dir: Path, *, fixture_processes=(),
                  sampling=SamplingMode.PERIODIC):
    if not isinstance(sampling, SamplingMode):
        raise ValueError('require a SamplingMode')
    trace = trial_dir / "resources.jsonl"
    identity_path = trial_dir / "ownership.json"
    try:
        identity = ownership.discover(engine.name,
                                      Path(engine.socket.removeprefix("unix://")), engine.dir)
    except Exception as exc:
        identity = {"required_processes": [], "error": str(exc)}
    if fixture_processes:
        if identity.get('error') or not identity['required_processes']:
            raise ValueError('cannot add fixture processes without verified engine ownership')
        processes = identity['required_processes'] + list(fixture_processes)
        if len({p['pid'] for p in processes}) != len(processes):
            raise ValueError('duplicate engine/fixture process identity')
        identity['required_processes'] = processes
        identity['method'] = identity.get('method', '') + '; explicit owned fixture process identities'
    identity_path.write_text(json.dumps(identity, indent=2) + "\n")
    engine.measurement_identity = identity
    if sampling is SamplingMode.BOUNDARIES:
        return None, None
    stderr = trial_dir / "sampler.stderr"
    with stderr.open("wb") as errors:
        proc = subprocess.Popen(
            [sys.executable, str(COLLECT), "--match", MATCH_PATTERNS[engine.name],
             "--ownership", str(identity_path),
             "--interval", "0.2", "--out", str(trace)],
            stdout=subprocess.DEVNULL, stderr=errors)
    return Sampler(proc, trace, stderr), trace


@contextmanager
def resource_phase(engine, rec, name):
    identity = engine.measurement_identity
    before = collect.cpu_boundary(identity)
    started = time.monotonic()
    try:
        yield
    finally:
        ended = time.monotonic()
        after = collect.cpu_boundary(identity)
        result = collect.cpu_delta(before, after)
        result.update({"operation_started_monotonic": started,
                       "operation_ended_monotonic": ended,
                       "operation_wall_seconds": ended - started})
        rec["resources"].setdefault("phases", {})[name] = result


def stop_sampler(sampler: Sampler) -> None:
    proc = sampler.process
    requested = time.monotonic()
    running = proc.poll() is None
    forced = False
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=35)
    except subprocess.TimeoutExpired:
        forced = True
        proc.kill()
        proc.wait(timeout=5)
    error = None
    if not running:
        error = "sampler exited before requested stop"
    elif forced:
        error = "sampler required forced termination"
    elif proc.returncode != 0:
        error = "sampler failed during requested stop"
    else:
        try:
            receipt = json.loads(collect.stop_receipt_path(sampler.trace).read_text())
            received = receipt.get('stop_requested_monotonic')
            if (receipt.get('pid') != proc.pid or receipt.get('sampler_version') != collect.SAMPLER_VERSION
                    or type(received) not in (int, float) or not requested <= received <= time.monotonic()):
                raise ValueError('stop receipt does not acknowledge this request')
        except (OSError, ValueError, AttributeError) as exc:
            error = f"sampler did not acknowledge requested stop: {exc}"
    if error is not None:
        with sampler.trace.open("a") as trace:
            trace.write(json.dumps({"record_type": "sampler_exit",
                "error": f"{error}: exit {proc.returncode}",
                "exit_status": proc.returncode, "forced_stop": forced,
                "stderr": str(sampler.stderr)}) + "\n")


def _trace_ref(trace: Path) -> str:
    try:
        return str(trace.relative_to(WORK))
    except ValueError:
        return str(trace)


def summarize_trace(trace: Path) -> dict:
    if not trace.exists():
        return {"samples": 0}
    records = []
    errors = []
    for number, line in enumerate(trace.read_text().splitlines(), 1):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            errors.append(f"malformed sample {number}")
    peak_rss = 0
    footprints = []
    cpu = 0.0
    cpu_complete = len(records) >= 2
    ownership = bool(records) and all(r.get("ownership_verified") is True for r in records
                                      if r.get("record_type") != "footprint_only")
    previous = None
    cpu_records = 0
    footprint_incomplete = False
    for rec in records:
        procs = rec.get("procs", [])
        peak_rss = max(peak_rss, sum(p.get("rss_kb", 0) for p in procs))
        errors.extend(rec.get("ownership_errors", []))
        if rec.get("error"):
            errors.append(rec["error"])
            cpu_complete = False
        fp = rec.get("footprint")
        if fp:
            required = set(map(str, fp.get("required_pids", [])))
            values = {str(k): v for k, v in fp.get("values", {}).items()}
            if required and required <= values.keys() and not fp.get("error"):
                footprints.append(sum(values[k] for k in required))
            else:
                footprint_incomplete = True
                errors.append("incomplete phys_footprint sample")
        if rec.get("record_type") == "footprint_only":
            continue
        cpu_records += 1
        if previous is not None:
            old = {(p.get("pid"), p.get("start_identity")): p for p in previous.get("procs", [])}
            new = {(p.get("pid"), p.get("start_identity")): p for p in procs}
            if not new or old.keys() != new.keys():
                cpu_complete = False
            for key, proc in new.items():
                prior = old.get(key, {})
                before, after = prior.get("cputime_s"), proc.get("cputime_s")
                if before is None or after is None or after < before:
                    cpu_complete = False
                else:
                    cpu += after - before
        previous = rec
    cpu_complete = cpu_complete and cpu_records >= 2
    qualified_cpu = cpu_complete and ownership and not errors
    qualified_fp = ownership and cpu_records > 0 and bool(footprints) and not footprint_incomplete and not errors
    return {
        "samples": len(records),
        "peak_total_rss_kb": peak_rss,
        "peak_phys_footprint_bytes": max(footprints) if qualified_fp else None,
        "diagnostic_peak_phys_footprint_bytes": max(footprints) if footprints else None,
        "footprint_samples": len(footprints),
        "cpu_seconds_est": round(cpu, 6) if qualified_cpu else None,
        "diagnostic_cpu_seconds": round(cpu, 6) if cpu_complete else None,
        "cpu_counters_complete": cpu_complete,
        "ownership_verified": ownership,
        "resource_errors": errors,
        "method": "cumulative process CPU deltas; kernel ri_phys_footprint; ownership required",
        "footprint_field": "phys_footprint",
    }


def compose_down(engine: Engine, project: str,
                 compose_file: Path = COMPOSE_FILE) -> None:
    engine.sh(["compose", "-f", str(compose_file), "-p", project,
               "down", "-v", "--remove-orphans"], timeout=90, check=False)
    cp = engine.sh(["ps", "-aq", "--no-trunc", "--filter",
                    f"label=com.docker.compose.project={project}"], check=False, timeout=30)
    for cid in cp.stdout.split():
        inspected = json.loads(engine.sh(["inspect", "--", cid], timeout=30).stdout)
        if (not isinstance(inspected, list) or len(inspected) != 1
                or not isinstance(inspected[0], dict) or inspected[0].get("Id") != cid
                or ((inspected[0].get("Config") or {}).get("Labels") or {}).get("com.docker.compose.project") != project):
            raise RuntimeError(f"refusing cleanup without exact project ownership: {cid}")
        engine.sh(["rm", "-f", "--", cid], check=False, timeout=30)


def wait_health(base: str, deadline_s: float, *, request=None):
    """Poll /health; return (monotonic_time, body) or (None, last)."""
    end = time.monotonic() + deadline_s
    last = None
    get = http_json if request is None else request
    while time.monotonic() < end:
        status, body = get(f"{base}/health", timeout=3)
        last = (status, body)
        if status == 200 and isinstance(body, dict) and body.get("ok"):
            return time.monotonic(), body
        time.sleep(POLL_INTERVAL_S)
    return None, last


W1_FIXTURE_VERSION = "w1-v2-pinned-restart"


def prepare_pinned_stack(engine, override, *, layout=None):
    from diagnostics.w8_under_pull import baseline_image_reference, require_baseline_images

    pin_path = FIXTURES / "w8-v5/portfolio.json"
    source = json.loads(pin_path.read_text())
    seed_sha = sha256_file(W1_DIR / "seed.sql")
    if seed_sha != source["seed_sql_sha256"]:
        raise ValueError("stack seed differs from the pinned portfolio")
    repositories = {"api": "np-v5/api", "db": "np-v5/postgres", "cache": "np-v5/redis"}
    pins = {service: source["images"][repository] for service, repository in repositories.items()}
    if layout is not None:
        import registry_portfolio

        if not layout.is_dir():
            raise ValueError(f"pinned portfolio is required at {layout}")
        portfolio = registry_portfolio.prepare_pinned_portfolio(
            layout, {**source, "images": {name: source["images"][name] for name in repositories.values()}})
        with registry_portfolio.running_registry(portfolio) as server:
            for repository in repositories.values():
                ref = f"127.0.0.1:{server.server_port}/{repository}@{portfolio.manifests[repository]}"
                engine.sh(["pull", ref], timeout=180)
    refs = {service: baseline_image_reference(engine.name, pin)[1] for service, pin in pins.items()}
    installed = json.loads(engine.sh(["image", "inspect", *refs.values()]).stdout)
    images = require_baseline_images(engine.name, pins, installed)
    override.write_text(json.dumps({"services": {service: {"image": ref}
                                                for service, ref in refs.items()}}) + "\n")
    return refs, {"images": images, "seed_sha256": seed_sha, "portfolio_sha256": sha256_file(pin_path)}


def trial_w1(ctx, engine: Engine, state: str, fixture_version: str = W1_FIXTURE_VERSION) -> dict:
    """Verify startup and DB/cache recovery with a preinstalled pinned stack."""
    case_id = "W1"
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    cenv = {"NP_API_PORT": str(port), "NP_API_TAG": API_TAG}
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    trial_token = hashlib.sha256(rec["trial_id"].encode()).hexdigest()[:16]
    proj = project_name(trial_token, engine.name, case_id)
    override = trial_dir / "pinned-compose.json"
    checks = rec["correctness"]["checks"]
    rec["metrics"]["fixture_version"] = fixture_version
    recovery = rec["recovery"] = {}
    started = False
    sampler = trace = None
    t0 = None

    def compose(args):
        return engine.sh(["compose", "-f", str(COMPOSE_FILE), "-f", str(override),
                          "-p", proj, *args], env_extra=cenv, timeout=300)

    def inspect_service(service):
        selected = compose(["ps", "-q", service]).stdout.split()
        if len(selected) != 1:
            raise ValueError(f"expected one owned W1 {service} container")
        inspected, = json.loads(engine.sh(["inspect", "--", selected[0]], timeout=30).stdout)
        labels = inspected["Config"]["Labels"]
        if (not inspected["Id"].startswith(selected[0])
                or labels.get("com.docker.compose.project") != proj
                or labels.get("com.docker.compose.service") != service
                or inspected["Image"] != refs[service]
                or inspected["State"]["Running"] is not True):
            raise ValueError(f"wrong identity for W1 {service} container")
        return inspected

    def database_identity():
        inspected = inspect_service("db")
        mounts = [mount for mount in inspected["Mounts"]
                  if mount["Destination"] == "/var/lib/postgresql/data"]
        if (len(mounts) != 1 or mounts[0]["Type"] != "volume"
                or mounts[0].get("Name") != proj + "_dbdata" or mounts[0].get("RW") is not True
                or not inspected["State"]["StartedAt"]):
            raise ValueError("W1 database volume or process identity differs")
        return {"id": inspected["Id"], "volume": mounts[0]["Name"],
                "started_at": inspected["State"]["StartedAt"]}

    def write_record(stage, key, value):
        status, body = http_json_write(f"{base}/records", {"key": key, "value": value})
        recovery[stage] = {"status": status, "body": body.decode(errors="replace")
                           if isinstance(body, bytes) else body}
        if status != 200 or body != {"stored": key}:
            raise ValueError(f"W1 {stage} did not acknowledge the exact key")
        checks[stage] = True

    def read_record(stage, key, value):
        status, body = http_json(f"{base}/records/{key}", timeout=10)
        recovery[stage] = {"status": status, "body": body}
        if (status != 200 or body != {"key": key, "value": value, "cache_match": True}
                or body["cache_match"] is not True):
            raise ValueError(f"W1 {stage} did not return the exact database and cache record")
        checks[stage] = True

    try:
        if fixture_version != W1_FIXTURE_VERSION:
            raise ValueError("W1 fixture version mismatch")
        engine.ensure_up()
        refs, rec["inputs"] = prepare_pinned_stack(engine, override)
        sampler, trace = start_sampler(engine, trial_dir)
        started = True
        t0 = time.monotonic()
        compose(["up", "-d", "--no-build", "--pull", "never"])
        t_health, health_body = wait_health(base, HEALTH_DEADLINE_S)
        if t_health is None:
            raise RuntimeError(f"W1 health deadline; last={health_body}")
        checks["health"] = True
        rec["metrics"]["time_to_health_s"] = round(t_health - t0, 3)
        status, rt = http_json(f"{base}/roundtrip", timeout=10)
        recovery["initial_roundtrip"] = {"status": status, "body": rt}
        expected_row = {"id": 1, "name": "item-1", "payload": hashlib.md5(b"1").hexdigest()}
        if (status != 200 or not isinstance(rt, dict) or rt.get("ok") is not True
                or rt.get("db_row") != expected_row or rt.get("seed_rows") != 500
                or not re.fullmatch(r"rt-[0-9]+", str(rt.get("cache_token")))):
            raise ValueError("W1 initial DB/cache roundtrip differs from pin")
        rec["metrics"]["time_to_roundtrip_s"] = round(time.monotonic() - t0, 3)
        checks["roundtrip"] = True
        for service in ("api", "cache"):
            inspect_service(service)
        before = recovery["database_before"] = database_identity()
        key = "keep-" + trial_token
        write_record("write_before_restart", key, "persist-ok")
        engine.sh(["restart", before["id"]], timeout=120)
        t_ready, health_body = wait_health(base, HEALTH_DEADLINE_S)
        if t_ready is None:
            raise RuntimeError(f"W1 restart health deadline; last={health_body}")
        after = recovery["database_after"] = database_identity()
        if (before["id"] != after["id"] or before["volume"] != after["volume"]
                or before["started_at"] == after["started_at"]):
            raise ValueError("W1 did not observe the owned database restart on the same volume")
        read_record("persist_after_db_restart", key, "persist-ok")
        write_record("write_after_restart", key + "-after", "restart-ok")
        read_record("read_after_restart", key + "-after", "restart-ok")
        rec["correctness"]["ok"] = True
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(str(exc))
    finally:
        if t0 is not None:
            rec["metrics"]["wall_seconds"] = round(time.monotonic() - t0, 3)
        if started:
            try:
                compose(["down", "-v", "--remove-orphans"])
                checks["cleanup"] = True
            except Exception as exc:
                rec["correctness"]["ok"] = False
                rec["validation_errors"].append(f"W1 cleanup: {exc}")
        if sampler is not None:
            stop_sampler(sampler)
        rec["resources"].update(summarize_trace(trace) if trace else {})
        if trace:
            rec["resources"]["trace"] = _trace_ref(trace)
    return rec


def exact_w2_items(actual, writes):
    expected = sorted([[f"item-{i}", hashlib.md5(str(i).encode()).hexdigest()]
                       for i in range(1, 501)] +
                      [[row["name"], row["payload"]] for row in writes])
    return sorted(actual) == expected


def trial_w2(ctx, engine: Engine, state: str, concurrency: int,
             duration: float, write_ratio: float, seed: int,
             operations: int | None = None, *, request_rate: float | None = None,
             allocation_paths: tuple[Path, ...] = (),
             sampling=SamplingMode.PERIODIC, client_location: str = "host",
             pinned_stack: bool = False) -> dict:
    """W2: seeded stack up (untimed), then sustained mixed load timed."""
    if client_location not in ("host", "guest"):
        raise ValueError("W2 client location must be host or guest")
    span = planned_span(operations, request_rate) if request_rate is not None else None
    client_source = RATE_LOAD_PY if request_rate is not None else LOAD_PY
    case_id = "W2"
    proj = project_name(ctx.run_id, engine.name, case_id)
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    cenv = {"NP_API_PORT": str(port), "NP_API_TAG": API_TAG}
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    trial_dir.mkdir(parents=True, exist_ok=True)
    load_out = trial_dir / "load.json"
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    client_sha = sha256_file(client_source)
    rec.setdefault("inputs", {})["load_client"] = {
        "path": str(client_source.relative_to(REPO)), "sha256": client_sha}
    rec["metrics"]["client_location"] = client_location
    peer = None
    counter_reader = None
    get = http_json
    sampler = trace = None
    measurement_started = False
    cleanup_needed = not pinned_stack
    override = trial_dir / "pinned-compose.json" if pinned_stack else None
    t0 = time.monotonic()

    def compose(args, timeout=300):
        if override is None:
            return engine.compose(proj, args, env_extra=cenv, timeout=timeout)
        return engine.compose(proj, args, env_extra=cenv, timeout=timeout, override=override)

    try:
        engine.ensure_up()
        if pinned_stack:
            from diagnostics.resource_pilot import warmup_api

            refs, inputs = prepare_pinned_stack(engine, override)
            rec["inputs"].update(inputs)
            rec["paired_inputs"] = {
                "portfolio_sha256": inputs["portfolio_sha256"],
                "seed_sha256": inputs["seed_sha256"],
                "load_client_sha256": client_sha,
                "api_files_sha256": warmup_api(engine, refs["api"]),
            }
        cleanup_needed = True
        compose_down(engine, proj)
        if pinned_stack:
            t0 = time.monotonic()
        sampler, trace = start_sampler(engine, trial_dir, sampling=sampling)
        measurement_started = True
        rec['resources'].update(sampling_mode=sampling.value, sampler_version=collect.SAMPLER_VERSION)
        if allocation_paths:
            rec["resources"]["disk_allocation"] = {
                "before_setup": resource_cells.allocation_snapshot(allocation_paths)}
        with resource_phase(engine, rec, "setup"):
            up = compose(["up", "-d", "--no-build", "--pull", "never"] if pinned_stack else ["up", "-d"])
            if up.returncode != 0:
                rec["correctness"]["ok"] = False
                rec["validation_errors"].append(
                    f"compose up rc={up.returncode}: {(up.stderr or up.stdout)[-300:]}")
                return rec
            if client_location == "guest":
                api_id = compose(["ps", "-q", "api"], timeout=30).stdout.strip()
                api_info, = json.loads(engine.sh(["inspect", api_id], timeout=30).stdout)
                image_id = api_info["Image"]
                if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
                    raise ValueError("cannot identify the immutable W2 API image")
                peer = f"{proj}-client"
                info = w2_peer.prepare(engine, peer, ctx.run_id, proj, api_id, image_id, client_source, client_sha)
                if info["Image"] != image_id:
                    raise ValueError("W2 peer uses a different loaded image")
                (trial_dir / "guest-client.json").write_text(json.dumps(info, indent=2) + "\n")
                base = w2_peer.URL

                def get(url, timeout):
                    return w2_peer.get(engine, peer, url, timeout)

                t_ready, _ = wait_health(base, HEALTH_DEADLINE_S, request=get)
                rec["resources"]["engine_cpu_scope"] = "includes guest load client"
            else:
                t_ready, _ = wait_health(base, HEALTH_DEADLINE_S)
            if t_ready is None:
                rec["correctness"]["ok"] = False
                rec["validation_errors"].append("stack never became healthy")
                return rec
            rec["metrics"]["setup_seconds"] = round(t_ready - t0, 3)

        api_id = compose(["ps", "-q", "api"], timeout=30).stdout.strip()
        counter_reader = f"{proj}-counters"
        reader_error = start_guest_counter_reader(engine, counter_reader, ctx.run_id, api_id)
        def application_cpu():
            cp = engine.sh(["exec", api_id, "cat", "/sys/fs/cgroup/cpu.stat"], timeout=30)
            return {key: int(value) for key, value in
                    (line.split() for line in cp.stdout.splitlines())}
        guest_before = guest_kernel_counters(engine, counter_reader, reader_error)
        app_before = application_cpu()
        if allocation_paths:
            rec["resources"]["disk_allocation"]["before_work"] = resource_cells.allocation_snapshot(allocation_paths)
        output_path = str(load_out) if peer is None else f"{w2_peer.OUTPUT_DIR}/load.json"
        args = ["--url", base, "--concurrency", str(concurrency), "--duration", str(duration),
                "--write-ratio", str(write_ratio), "--seed", str(seed), "--out", output_path]
        if operations is not None:
            args += ["--operations", str(operations)]
        if request_rate is not None:
            args += ["--request-rate", str(request_rate)]
        timeout = max(duration, span or 0) + 120
        with resource_phase(engine, rec, "workload"):
            if peer is None:
                load = subprocess.run([sys.executable, str(client_source), *args],
                                      capture_output=True, text=True, timeout=timeout)
            else:
                load = w2_peer.run(engine, peer, "load", args, timeout)
        app_after = application_cpu()
        rec["resources"]["application_cpu"] = {"before": app_before, "after": app_after,
            "delta": {key: app_after[key] - value for key, value in app_before.items()
                      if key in app_after}, "method": "API cgroup v2 cpu.stat; includes counter-reader exec"}
        rec["resources"]["guest_kernel_counters"] = guest_kernel_counter_delta(
            guest_before, guest_kernel_counters(engine, counter_reader, reader_error))
        if peer is not None:
            w2_peer.copy_results(engine, peer, trial_dir, "load")
        if load_out.exists():
            summary = json.loads(load_out.read_text())
            rec["metrics"].update({
                "fixture_version": summary["fixture_version"],
                "mode": summary["mode"],
                "target_operations": operations,
                "requests_ok": summary["requests_ok"],
                "wall_seconds": summary["duration_s"],
                "rps": summary["rps"],
                "requests": summary["requests"],
                "errors": summary["errors"],
                "reads_ok": summary["reads_ok"],
                "writes_ok": summary["writes_ok"],
                "p50_ms": summary["latency_ms"]["p50"],
                "p95_ms": summary["latency_ms"]["p95"],
                "p99_ms": summary["latency_ms"]["p99"],
            })
        else:
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append(
                f"load driver produced no summary: {load.stderr[-300:]}")
            return rec

        if request_rate is not None:
            rec["metrics"].update(latency_scope=summary["latency_scope"],
                                  service_latency_ms=summary["service_latency_ms"])
            rec["metrics"].update({key: summary[key] for key in (
                "request_rate", "planned_span_s", "schedule_lag_budget_ms",
                "planned_requests", "offered_requests", "delivered_requests",
                "late_requests", "offered_rate_valid", "slots")})
            rec["correctness"]["checks"]["offered_rate_valid"] = summary["offered_rate_valid"]
            if not summary["offered_rate_valid"]:
                rec["validation_errors"].append("fixed offered-rate schedule invalid")

        phase_cpu = rec["resources"]["phases"]["workload"]["cpu_seconds"]
        rec["metrics"]["workload_cpu_seconds"] = phase_cpu
        rec["metrics"]["cpu_seconds_per_success"] = (
            phase_cpu / summary["requests_ok"] if phase_cpu is not None and summary["requests_ok"] else None)
        status, stats = get(f"{base}/stats", timeout=10)
        expected_items = 500 + summary["writes_ok"]
        got_items = stats.get("items") if isinstance(stats, dict) else None
        count_ok = status == 200 and got_items == expected_items
        rec["correctness"]["checks"]["item_count"] = {
            "expected": expected_items, "got": got_items, "ok": count_ok}
        rec["correctness"]["checks"]["load_errors_zero"] = (
            summary["errors"] == 0)
        expected_writes = [json.loads(line) for line in
                           Path(str(load_out) + ".writes.jsonl").read_text().splitlines()]
        db_id = compose(["ps", "-q", "db"], timeout=30).stdout.strip()
        rows = engine.sh(["exec", db_id, "psql", "-U", "app", "-d", "app", "-At", "-c",
                          "SELECT json_build_array(name,payload)::text FROM items ORDER BY name,payload"], timeout=60)
        actual = [json.loads(line) for line in rows.stdout.splitlines()]
        (trial_dir / "persisted-items.json").write_text(json.dumps(actual))
        exact_ok = exact_w2_items(actual, expected_writes) and len(expected_writes) == summary["writes_ok"]
        rec["correctness"]["checks"]["exact_persisted_items"] = exact_ok
        work_ok = operations is None or summary["requests_ok"] == operations
        rec["correctness"]["checks"]["fixed_work_complete"] = work_ok
        rec["correctness"]["ok"] = bool(count_ok and exact_ok and work_ok and
                                              load.returncode == 0 and summary["errors"] == 0 and
                                              (request_rate is None or summary["offered_rate_valid"]))
        return rec
    except BaseException as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(f"{type(exc).__name__}: {exc}")
        if isinstance(exc, Exception):
            return rec
        raise
    finally:
        interrupted = sys.exc_info()[1]
        if isinstance(interrupted, Exception):
            interrupted = None
        try:
            if allocation_paths:
                rec["resources"].setdefault("disk_allocation", {})["after_work"] = resource_cells.allocation_snapshot(allocation_paths)
            with resource_phase(engine, rec, "cleanup") if measurement_started else nullcontext():
                for owned in (peer, counter_reader):
                    if owned is None:
                        continue
                    try:
                        ci_jobs.cleanup(engine, owned, ctx.run_id)
                    except BaseException as exc:
                        rec["correctness"]["ok"] = False
                        rec["validation_errors"].append(f"{owned} cleanup {type(exc).__name__}: {exc}")
                        if not isinstance(exc, Exception) and interrupted is None:
                            interrupted = exc
                if cleanup_needed:
                    compose_down(engine, proj)
            if allocation_paths:
                rec["resources"]["disk_allocation"]["after_cleanup"] = resource_cells.allocation_snapshot(allocation_paths)
        except BaseException as exc:
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append(f"cleanup {type(exc).__name__}: {exc}")
            if not isinstance(exc, Exception) and interrupted is None:
                interrupted = exc
        try:
            if sampler is not None:
                stop_sampler(sampler)
        except BaseException as exc:
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append(f"sampler stop {type(exc).__name__}: {exc}")
            if not isinstance(exc, Exception) and interrupted is None:
                interrupted = exc
        try:
            rec["resources"].update(summarize_trace(trace) if trace else {})
            if trace:
                rec["resources"]["trace"] = _trace_ref(trace)
        except BaseException as exc:
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append(f"sampler summary {type(exc).__name__}: {exc}")
            if not isinstance(exc, Exception) and interrupted is None:
                interrupted = exc
        try:
            (trial_dir / "trial-result.json").write_text(json.dumps(rec) + "\n")
        except OSError:
            if interrupted is None:
                raise
        if interrupted is not None:
            raise interrupted


def registry_name(engine_name: str) -> str:
    return f"npw8-reg-{engine_name}"


def registry_volume(engine_name: str) -> str:
    return f"npw8-reg-data-{engine_name}"


def load_registry_state() -> dict:
    if REGISTRY_STATE.exists():
        try:
            return json.loads(REGISTRY_STATE.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def save_registry_state(state: dict) -> None:
    REGISTRY_STATE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_STATE.write_text(json.dumps(state, indent=2) + "\n")


def registry_alive(engine: Engine, port: int) -> bool:
    try:
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/v2/", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_registry(engine: Engine) -> int:
    """Return the host loopback port of this engine's W8 registry,
    creating or reviving the container as needed. The registry image and
    its data volume persist across ctrs daemon restarts."""
    engine.ensure_up()
    name = registry_name(engine.name)
    state = load_registry_state()
    port = state.get(engine.name, {}).get("port")

    cp = engine.sh(
        ["ps", "-a", "--filter", f"name=^{name}$",
         "--format", "{{.Names}} {{.Status}}"],
        check=False, timeout=30)
    line = next((l for l in cp.stdout.splitlines()
                 if l.split()[0] == name), "")
    running = "Up" in line

    if running and port and registry_alive(engine, port):
        return port
    if running and port is None:
        cp = engine.sh(["port", name, "5000/tcp"], check=False, timeout=30)
        m = re.search(r"127\.0\.0\.1:(\d+)", cp.stdout)
        if m and registry_alive(engine, int(m.group(1))):
            state.setdefault(engine.name, {})["port"] = int(m.group(1))
            save_registry_state(state)
            return int(m.group(1))
        port = None

    if not running:
        # Exists but stopped (e.g. after a ctrs VM restart without a
        # restart policy taking effect) or absent entirely.
        engine.sh(["rm", "-f", name], check=False, timeout=30)
    if port is None:
        port = free_port()
    engine.sh(
        ["run", "-d", "--name", name, "--restart", "unless-stopped",
         "-p", f"127.0.0.1:{port}:5000",
         "-v", f"{registry_volume(engine.name)}:/var/lib/registry",
         REGISTRY_IMAGE], timeout=120)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if registry_alive(engine, port):
            state.setdefault(engine.name, {})["port"] = port
            save_registry_state(state)
            return port
        time.sleep(0.5)
    raise TimeoutError(f"{name} registry did not come up on :{port}")


def trial_w8(ctx, engine: Engine, state: str, under_load: bool = False,
             duration: float = 30.0, concurrency: int = 8,
             write_ratio: float = 0.3, seed: int = 1) -> dict:
    """W8: pull a pinned portfolio of real rootfs images from the local
    registry by digest and run each image's own smoke command. With
    `under_load`, the W1 stack serves load.py while the pulls run — the
    EXP-1 responsiveness probe."""
    case_id = "W8"
    proj = project_name(ctx.run_id, engine.name, case_id)
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    trial_dir.mkdir(parents=True, exist_ok=True)
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    sampler = trace = None
    t0 = time.monotonic()
    load_proc = None
    load_out = trial_dir / "load.json"
    w1_proj = project_name(ctx.run_id, engine.name, "W1")
    try:
        port = ensure_registry(engine)
        portfolio = {}
        if PORTFOLIO_FILE.exists():
            portfolio = json.loads(PORTFOLIO_FILE.read_text()).get(
                engine.name, {})
        # verify/expect come from W8_IMAGES (source of truth); the
        # portfolio file only carries per-engine refs and digests.
        specs = {s["name"]: s for s in W8_IMAGES}
        items = []
        for name, item in portfolio.items():
            spec = specs.get(name)
            if spec is None:
                continue
            merged = dict(item)
            merged["verify"] = spec["verify"]
            merged["expect"] = spec["expect"]
            items.append((name, merged))
        portfolio = dict(items)
        if not portfolio:
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append(
                "no W8 portfolio; run `runner.py prepare` first")
            return rec
        engine.ensure_up()
        sampler, trace = start_sampler(engine, trial_dir)

        # Drop only fixture refs. Both engines keep their content caches;
        # removing tags cannot establish an empty-store comparison.
        # In particular, never prune the user's shared OrbStack daemon.
        for item in portfolio.values():
            for ref in {item["pull_ref"], item["tag_ref"],
                        item.get("local_ref", "")}:
                if ref:
                    engine.sh(["rmi", "-f", ref], check=False, timeout=60)
        rec["metrics"]["cache_mode"] = "fixture-refs-removed-content-retained"
        rec["notes"].append("W8 is a warm-content pilot, not an empty-store pull")

        base = None
        if under_load:
            cport = free_port()
            base = f"http://127.0.0.1:{cport}"
            cenv = {"NP_API_PORT": str(cport), "NP_API_TAG": API_TAG}
            up = engine.compose(w1_proj, ["up", "-d"], env_extra=cenv,
                                timeout=300)
            if up.returncode != 0:
                rec["correctness"]["ok"] = False
                rec["validation_errors"].append(
                    f"under-load stack up failed: "
                    f"{(up.stderr or up.stdout)[-300:]}")
                return rec
            t_ready, _ = wait_health(base, HEALTH_DEADLINE_S)
            if t_ready is None:
                rec["correctness"]["ok"] = False
                rec["validation_errors"].append(
                    "under-load stack never became healthy")
                return rec
            rec["metrics"]["setup_seconds"] = round(time.monotonic() - t0, 3)
            load_proc = subprocess.Popen(
                [sys.executable, str(LOAD_PY), "--url", base,
                 "--concurrency", str(concurrency),
                 "--duration", str(duration),
                 "--write-ratio", str(write_ratio),
                 "--seed", str(seed), "--out", str(load_out)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Let the load reach steady state before the pulls start.
            time.sleep(2.0)

        pull_start = time.monotonic()
        rec["metrics"]["setup_seconds"] = round(pull_start - t0, 3)
        pulls_ok = True
        for name, item in portfolio.items():
            ref = item["pull_ref"]
            tp = time.monotonic()
            cp = engine.sh(["pull", ref], timeout=600, check=False)
            pull_s = round(time.monotonic() - tp, 3)
            rec["metrics"][f"pull_{name}_s"] = pull_s
            out = cp.stdout + cp.stderr
            ok = (cp.returncode == 0
                  and item["digest"] in out)
            rec["correctness"]["checks"][f"pull_{name}"] = ok
            pulls_ok = pulls_ok and ok
            # Transparency: how many layers were actually fetched vs
            # deduped ("Already exists"), so store-warmth differences
            # between engines are visible per trial, not hidden.
            rec["metrics"][f"pull_{name}_fetched"] = out.count(
                "Pull complete") + out.count("Downloading")
            rec["metrics"][f"pull_{name}_cached"] = out.count(
                "Already exists")
            if not ok:
                rec["validation_errors"].append(
                    f"pull {name} rc={cp.returncode}: {out[-300:]}")

            tr = time.monotonic()
            run = engine.sh(["run", "--rm", ref, *item["verify"]],
                            timeout=180, check=False)
            run_s = round(time.monotonic() - tr, 3)
            rec["metrics"][f"run_{name}_s"] = run_s
            ok_run = (run.returncode == 0
                      and item["expect"] in run.stdout)
            rec["correctness"]["checks"][f"run_{name}"] = ok_run
            pulls_ok = pulls_ok and ok_run
            if not ok_run:
                rec["validation_errors"].append(
                    f"run {name} rc={run.returncode}: "
                    f"{(run.stdout + run.stderr)[-300:]}")
        rec["metrics"]["pull_wall_seconds"] = round(
            time.monotonic() - pull_start, 3)
        rec["metrics"]["wall_seconds"] = round(
            time.monotonic() - pull_start, 3)

        if under_load:
            if load_proc is not None:
                try:
                    load_proc.wait(timeout=duration + 120)
                except subprocess.TimeoutExpired:
                    load_proc.kill()
                    load_proc.wait(timeout=10)
            if load_out.exists():
                summary = json.loads(load_out.read_text())
                rec["metrics"].update({
                    "load_duration_s": summary["duration_s"],
                    "load_rps": summary["rps"],
                    "load_requests": summary["requests"],
                    "load_errors": summary["errors"],
                    "load_p50_ms": summary["latency_ms"]["p50"],
                    "load_p95_ms": summary["latency_ms"]["p95"],
                    "load_p99_ms": summary["latency_ms"]["p99"],
                })
                st, stats = http_json(f"{base}/stats", timeout=10)
                expected = 500 + summary["writes_ok"]
                got = stats.get("items") if isinstance(stats, dict) else None
                count_ok = got == expected
                rec["correctness"]["checks"]["item_count"] = {
                    "expected": expected, "got": got, "ok": count_ok}
                rec["correctness"]["checks"]["load_errors_zero"] = (
                    summary["errors"] == 0)
                pulls_ok = pulls_ok and count_ok and summary["errors"] == 0
                pulls_ok = pulls_ok and load_proc.returncode == 0
            else:
                pulls_ok = False
                rec["validation_errors"].append("load driver produced no summary")
        rec["correctness"]["ok"] = bool(pulls_ok)
        return rec
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(f"exception: {exc}")
        return rec
    finally:
        if load_proc is not None and load_proc.poll() is None:
            load_proc.kill()
            load_proc.wait(timeout=10)
        compose_down(engine, w1_proj)
        if sampler is not None:
            stop_sampler(sampler)
        rec["resources"].update(summarize_trace(trace) if trace else {})
        if trace:
            rec["resources"]["trace"] = _trace_ref(trace)


def ensure_dc_builder(engine: Engine) -> None:
    """Use a benchmark-owned builder bound to this exact engine socket.
    Buildx names/config are client-global by default, so names alone do
    not prove that a builder sends work to the intended competitor."""
    # The recorded buildx v0.22 has no inspect --format option. Parse
    # its labelled fields and fail closed on missing/ambiguous values.
    inspect = ["buildx", "inspect", engine.builder_name]
    cp = engine.sh(inspect, timeout=30, check=False)
    if cp.returncode != 0:
        engine.sh(
            ["buildx", "create", "--name", engine.builder_name,
             "--driver", "docker-container",
             "--driver-opt", f"image={DC_BUILDER_IMAGE}", "--bootstrap",
             engine.socket], timeout=600)
        cp = engine.sh(inspect, timeout=30, check=False)
    if cp.returncode != 0:
        raise RuntimeError("cannot verify benchmark builder endpoint")
    fields: dict[str, list[str]] = {}
    for line in cp.stdout.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields.setdefault(key.strip(), []).append(value.strip())
    if (fields.get("Driver") != ["docker-container"]
            or fields.get("Endpoint") != [engine.socket]):
        raise RuntimeError("benchmark builder belongs to a different endpoint/driver")
    options = fields.get("Driver Options", [])
    if (len(options) != 1
            or f"image={DC_BUILDER_IMAGE}" not in shlex.split(options[0])):
        raise RuntimeError("benchmark builder does not use the pinned BuildKit image")


def build_args(engine: Engine, driver: str, extra: list[str]) -> list[str]:
    """`docker buildx build --load` argv with explicit builder selection."""
    args = ["buildx", "build", "--load", *extra]
    if driver == "dc":
        args += ["--builder", engine.builder_name]
    else:
        args += ["--builder", "default"]
    return args


# W7 real apps: builder image, runtime base, source pin, Dockerfile,
# version probe argv. Each gets uncached/warm/incremental builds through
# the default or dc builder, then run probes.
W7_FIXTURE_VERSION = "w7-v3-cache-first-use"
W7_NOTE_STEP = "RUN mkdir -p /out && cat /stamp/note.txt > /out/note.txt"
W7_APPS = {
    "hyperfine": {
        "builder_image": W6_RUST_IMAGE,
        "runtime_image": W7_DEBIAN_IMAGE,
        "source": W6_RUST_SOURCE,
        "dockerfile": W7_DIR / "hyperfine" / "Dockerfile",
        "compile_step": "RUN cargo build --release --locked",
        "probe": ["hyperfine", "--version"],
        "expect": "hyperfine 2.0.0",
    },
    "httpie": {
        "builder_image": W7_PYTHON_IMAGE,
        "runtime_image": W7_PYTHON_IMAGE,
        "source": W7_HTTPIE_SOURCE,
        "dockerfile": W7_DIR / "httpie" / "Dockerfile",
        "compile_step": "RUN pip wheel --no-cache-dir -w /wheels /tmp/httpie-3.2.4.tar.gz",
        "probe": ["http", "--version"],
        "expect": "3.2.4",
    },
}


def trial_w7(ctx, engine: Engine, state: str,
             driver: str = "default", fixture_version: str = W7_FIXTURE_VERSION) -> dict:
    """W7: default buildx -> loaded runnable images for two real apps
    (hyperfine 2.0.0 Rust, httpie 3.2.4 Python). Per app: uncached (--no-cache)
    / warm (identical context) / incremental (one-file stamp bump)
    builds, each followed by version and note probes of its loaded image.
    Base images pull untimed in setup; stores remain warm."""
    case_id = "W7"
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    checks = rec["correctness"]["checks"]
    sampler = trace = None
    owner = os.urandom(12).hex()
    label = "dev.ctrs.campaign.w7"
    label_value = hashlib.sha256(ctx.workload_id.encode()).hexdigest()
    tags = []
    try:
        if fixture_version != W7_FIXTURE_VERSION:
            raise ValueError("W7 fixture version mismatch")
        engine.ensure_up()
        if driver == "dc":
            ensure_dc_builder(engine)
        rec["metrics"]["builder_driver"] = driver
        rec["metrics"]["fixture_version"] = fixture_version
        sources = {name: ensure_pinned_source(spec["source"], W7_DIR)
                   for name, spec in W7_APPS.items()}
        for spec in W7_APPS.values():
            for image in (spec["builder_image"], spec["runtime_image"]):
                cp = engine.sh(["image", "inspect", image], timeout=30,
                               check=False)
                if cp.returncode != 0:
                    engine.sh(["pull", image], timeout=900)
        sampler, trace = start_sampler(engine, trial_dir)

        rec["metrics"]["cache_mode"] = "no-cache-base-images-retained"
        rec["notes"].append("--no-cache bypasses layer reuse; "
                            "engine/content stores remain warm")
        for name, spec in W7_APPS.items():
            ctx_dir = trial_dir / f"ctx-{name}"
            ctx_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(spec["dockerfile"], ctx_dir / "Dockerfile")
            shutil.copy(sources[name],
                        ctx_dir / spec["source"]["file"])
            (ctx_dir / "stamp").mkdir(exist_ok=True)

            for condition, note_revision in (("uncached", 0), ("warm", 0), ("incr", 1)):
                expected_note = f"incremental-{note_revision}:{label_value}\n"
                cell = f"{name}_{condition}"
                tag = f"npw7/{name}:{owner}-{condition}"
                tags.append(tag)
                (ctx_dir / "stamp" / "note.txt").write_text(expected_note)
                flags = ["--no-cache"] if condition == "uncached" else []
                with resource_phase(engine, rec, f"{cell}_build"):
                    build = engine.sh(build_args(engine, driver, [
                        *flags, "--progress=rawjson", "--platform", "linux/arm64", "--label", f"{label}={label_value}",
                        "-t", tag, "-f", str(ctx_dir / "Dockerfile"), str(ctx_dir),
                    ]), timeout=1800, check=False)
                rec["metrics"][f"{cell}_s"] = rec["resources"]["phases"][f"{cell}_build"]["operation_wall_seconds"]
                (trial_dir / f"{cell}-progress.jsonl").write_text(build.stderr)
                checks[cell] = build.returncode == 0
                if build.returncode:
                    rec["validation_errors"].append(f"{cell} build failed: {(build.stderr or build.stdout)[-400:]}")
                    break
                try:
                    cache = {
                        "compile": _buildkit_vertex(build.stderr, spec["compile_step"], cached=condition != "uncached"),
                        "note": _buildkit_vertex(build.stderr, W7_NOTE_STEP, cached=condition == "warm"),
                    }
                except ValueError as exc:
                    checks[f"{cell}_cache"] = False
                    rec["validation_errors"].append(f"{cell} cache evidence: {exc}")
                    break
                (trial_dir / f"{cell}-cache.json").write_text(json.dumps(cache, indent=2) + "\n")
                checks[f"{cell}_cache"] = True
                with resource_phase(engine, rec, f"{cell}_first_use"):
                    version = engine.sh(["run", "--rm", "--pull=never", tag, *spec["probe"]],
                                        timeout=60, check=False)
                note = engine.sh(["run", "--rm", "--pull=never", tag, "cat", "/out/note.txt"],
                                 timeout=60, check=False)
                checks[f"{cell}_version"] = version.returncode == 0 and version.stdout == spec["expect"] + "\n"
                checks[f"{cell}_note"] = note.returncode == 0 and note.stdout == expected_note
                (trial_dir / f"{cell}-probe.json").write_text(json.dumps({
                    "tag": tag, "build_output": build.stdout,
                    "version": {"exit": version.returncode, "stdout": version.stdout, "stderr": version.stderr},
                    "note": {"exit": note.returncode, "stdout": note.stdout, "stderr": note.stderr},
                }, indent=2) + "\n")
                if checks[f"{cell}_version"] and checks[f"{cell}_note"]:
                    rec["metrics"][f"{cell}_first_use_s"] = rec["resources"]["phases"][f"{cell}_first_use"]["operation_wall_seconds"]
                else:
                    rec["validation_errors"].append(f"{cell} loaded image failed version or note verification")
                    break
        rec["correctness"]["ok"] = all(checks.values())
        return rec
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(f"exception: {exc}")
        return rec
    finally:
        try:
            if sampler is not None:
                stop_sampler(sampler)
            rec["resources"].update(summarize_trace(trace) if trace else {})
            if trace:
                rec["resources"]["trace"] = _trace_ref(trace)
        finally:
            for tag in tags:
                try:
                    inspected = engine.sh(["image", "inspect", "--format",
                                           '{{ index .Config.Labels "' + label + '" }}', tag], check=False)
                    if inspected.returncode and "no such image" in inspected.stderr.lower():
                        continue
                    if inspected.returncode or inspected.stdout.strip() != label_value:
                        raise ValueError("image ownership could not be established")
                    engine.sh(["image", "rm", "--no-prune", tag])
                except Exception as exc:
                    rec["correctness"]["ok"] = False
                    rec["validation_errors"].append(f"{tag} cleanup: {exc}")


def _buildkit_vertex(progress: str, instruction: str, *, cached: bool) -> dict:
    matches = {}
    for line in progress.splitlines():
        if not line.lstrip().startswith("{"):
            continue
        for vertex in json.loads(line).get("vertexes", ()):
            name = vertex.get("name", "")
            if name != instruction and not name.endswith("] " + instruction):
                continue
            if vertex.get("error"):
                raise ValueError(f"{instruction}: build vertex failed: {vertex['error']}")
            if vertex.get("completed"):
                digest = vertex.get("digest", "")
                if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                    raise ValueError(f"{instruction}: completed build vertex has no valid digest")
                if vertex.get("cached", False) is not cached or (not cached and not vertex.get("started")):
                    raise ValueError(f"{instruction}: build vertex did not prove cached={cached}")
                matches[digest] = vertex
    if len(matches) != 1:
        raise ValueError(f"{instruction}: expected exactly one completed build vertex")
    return next(iter(matches.values()))


def trial_w6(ctx, engine: Engine, state: str,
             driver: str = "default", *, build_cache: str = "uncached") -> dict:
    """W6: compiled-app CI — two timed `docker build`s per trial on
    pinned upstream sources: hyperfine 2.0.0 (Rust: cargo build
    --release --locked + cargo test on rust:1.100.0-bookworm) and zlib
    1.3.1 (C: configure -> make -j -> make check on
    gcc:14.2.0-bookworm). Each build ends with a run probe that sha256s
    the produced binary/lib. Base images are pulled untimed in setup if
    absent (prepare also pulls them). Warm builds prime the same context
    before sampling. Artifact digests must match assets.lock."""
    case_id = "W6"
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    tag_zlib = f"npw6/zlib:{ctx.run_id[-6:]}"
    tag_rust = f"npw6/hyperfine:{ctx.run_id[-6:]}"
    checks = rec["correctness"]["checks"]
    sampler = trace = None
    try:
        if build_cache not in ("uncached", "warm"):
            raise ValueError("W6 build cache must be uncached or warm")
        with (BENCH / "assets.lock").open("rb") as lock:
            artifact_pins = tomllib.load(lock)["artifacts"]["w6"]
        zlib_src = ensure_pinned_source(W6_ZLIB_SOURCE, W6_DIR)
        rust_src = ensure_pinned_source(W6_RUST_SOURCE, W6_DIR)
        engine.ensure_up()
        if driver == "dc":
            ensure_dc_builder(engine)
        rec["metrics"]["builder_driver"] = driver
        for image in (W6_RUST_IMAGE, W6_IMAGE):
            cp = engine.sh(["image", "inspect", image], timeout=30,
                           check=False)
            if cp.returncode != 0:
                engine.sh(["pull", image], timeout=900)
        builds = (
            ("rust", W6_DIR / "rust" / "Dockerfile", rust_src,
             W6_RUST_SOURCE["file"], tag_rust, "/src/target/release/hyperfine"),
            ("zlib", W6_DIR / "Dockerfile", zlib_src,
             W6_ZLIB_SOURCE["file"], tag_zlib, "/src/libz.a"),
        )
        contexts = {}
        for name, dockerfile, source, archive, _, _ in builds:
            ctx_dir = trial_dir / f"ctx-{name}"
            ctx_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(dockerfile, ctx_dir / "Dockerfile")
            shutil.copy(source, ctx_dir / archive)
            (ctx_dir / "stamp.txt").write_text(f"{ctx.workload_id}\n")
            instruction = (ctx_dir / "Dockerfile").read_text().strip().splitlines()[-1]
            if not instruction.startswith("RUN "):
                raise ValueError(f"{name} Dockerfile must end with the compile and test instruction")
            contexts[name] = ctx_dir, instruction

        def solve(name, tag, *, cached):
            ctx_dir, _ = contexts[name]
            flags = [] if cached else ["--no-cache"]
            return engine.sh(build_args(engine, driver, [
                *flags, "--progress=rawjson", "--platform", "linux/arm64",
                "-t", tag, "-f", str(ctx_dir / "Dockerfile"), str(ctx_dir),
            ]), timeout=1800, check=False)

        def verify_solve(name, phase, result, *, cached):
            (trial_dir / f"{name}-{phase}.stdout").write_text(result.stdout)
            (trial_dir / f"{name}-{phase}.stderr").write_text(result.stderr)
            try:
                if result.returncode:
                    raise ValueError(f"build exited {result.returncode}: {(result.stderr or result.stdout)[-400:]}")
                _, instruction = contexts[name]
                vertex = _buildkit_vertex(result.stderr, instruction, cached=cached)
                (trial_dir / f"{name}-{phase}-compile.json").write_text(json.dumps(vertex, indent=2) + "\n")
            except ValueError as exc:
                checks[f"{phase}_{name}"] = False
                rec["validation_errors"].append(f"{name} {phase}: {exc}")
                return False
            checks[f"{phase}_{name}"] = True
            return True

        warm_cache = build_cache == "warm"
        rec["metrics"]["cache_mode"] = ("primed-build-cache" if warm_cache else
                                        "no-cache-base-images-retained")
        if warm_cache:
            for name, _, _, _, tag, _ in builds:
                prime = solve(name, tag, cached=False)
                verify_solve(name, "prime", prime, cached=False)
        sampler, trace = start_sampler(engine, trial_dir)
        for name, _, _, _, tag, artifact in builds:
            if warm_cache and not checks[f"prime_{name}"]:
                continue
            phase = f"build_{name}"
            with resource_phase(engine, rec, phase):
                result = solve(name, tag, cached=warm_cache)
            rec["metrics"][phase + "_s"] = round(rec["resources"]["phases"][phase]["operation_wall_seconds"], 3)
            if not verify_solve(name, "build", result, cached=warm_cache):
                continue
            run = engine.sh(["run", "--rm", tag, "sha256sum", artifact],
                            timeout=120, check=False)
            fields = run.stdout.split(maxsplit=1)
            sha = fields[0] if run.returncode == 0 and fields else ""
            rec["metrics"][f"artifact_{name}_sha256"] = sha
            expected = artifact_pins[name]
            checks[f"artifact_{name}"] = bool(sha and sha == expected)
            if not checks[f"artifact_{name}"]:
                rec["validation_errors"].append(
                    f"{name} artifact probe rc={run.returncode}, expected {expected}, got {sha!r}")

        rec["correctness"]["ok"] = all(checks.values())
        return rec
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(f"exception: {exc}")
        return rec
    finally:
        if sampler is not None:
            stop_sampler(sampler)
        rec["resources"].update(summarize_trace(trace) if trace else {})
        if trace:
            rec["resources"]["trace"] = _trace_ref(trace)


def trial_w9(ctx, engine: Engine, state: str, image_ref: str,
             concurrency_levels: tuple = tuple(ci_jobs.SPEC['concurrency']),
             fixture_version: str = ci_jobs.SPEC['fixture_version']) -> dict:
    """Run the same fixed Marked build/test jobs at each declared concurrency."""
    ci_jobs.validate_image_ref(image_ref)
    if fixture_version != ci_jobs.SPEC['fixture_version'] or tuple(concurrency_levels) != tuple(ci_jobs.SPEC['concurrency']):
        raise ValueError('W9 fixture version or concurrency differs from declared work')
    trial_dir = ctx.trial_dir(engine.name, 'W9', state)
    rec = ctx.new_record(engine, 'W9', state, trial_dir)
    sampler = trace = None
    owned_jobs = []
    engine_ready = False
    prefix = 'np-w9-' + hashlib.sha256(rec['trial_id'].encode()).hexdigest()[:16]
    rec['metrics'].update(fixture_version=fixture_version, fixed_jobs=ci_jobs.SPEC['fixed_jobs'],
                          artifact_sha256=ci_jobs.ARTIFACT)
    rec['notes'].append('Warm engine: image must be preinstalled; boot/warmup before resource discovery is not scored. Job phases include create/start/build/test/rm. CPU scope is owned engine processes, excluding Docker CLI/coordinator.')
    try:
        engine.ensure_up()
        engine_ready = True
        warmup = prefix + '-warmup'
        owned_jobs.append({'name': warmup})
        engine.sh(['run', '--rm', '--pull=never', '--name', warmup, '--label', 'dev.ctrs.campaign.run=' + prefix, '--entrypoint', 'node', image_ref, '-e', 'process.exit(0)'], timeout=90)
        sampler, trace = start_sampler(engine, trial_dir)
        with resource_phase(engine, rec, 'setup'):
            image = json.loads(engine.sh(['image', 'inspect', image_ref]).stdout)[0]
            if image['Architecture'] != 'arm64' or image_ref not in image['RepoDigests']:
                raise ValueError('W9 installed image differs from native pinned reference')
            (trial_dir / 'image.json').write_text(json.dumps(image, indent=2))
        for concurrency in concurrency_levels:
            try:
                with resource_phase(engine, rec, f'jobs_at_{concurrency}'):
                    results = ci_jobs.run_condition(engine, image_ref, prefix, concurrency)
            except ci_jobs.ConditionFailed as exc:
                results = exc.results
                owned_jobs.extend(results)
                (trial_dir / f'jobs-at-{concurrency}.json').write_text(json.dumps(results, indent=2))
                raise
            owned_jobs.extend(results)
            (trial_dir / f'jobs-at-{concurrency}.json').write_text(json.dumps(results, indent=2))
            if len(results) != ci_jobs.SPEC['fixed_jobs']:
                raise ValueError(f'W9 returned incomplete fixed work at concurrency {concurrency}')
            wall = rec['resources']['phases'][f'jobs_at_{concurrency}']['operation_wall_seconds']
            latencies = sorted(row['completion_seconds'] for row in results)
            if (wall <= 0 or not math.isfinite(wall)
                    or not all(0 <= value <= wall for value in latencies)):
                raise ValueError(f'W9 completion clocks are outside the phase at concurrency {concurrency}')
            rec['metrics'][f'fixed16_at_{concurrency}_s'] = wall
            rec['metrics'][f'successful_jobs_per_minute_at_{concurrency}'] = 60 * len(results) / wall
            rec['metrics'][f'job_completion_p95_ms_at_{concurrency}'] = 1000 * latencies[math.ceil(.95 * len(latencies)) - 1]
            rec['correctness']['checks'][f'exact_jobs_at_{concurrency}'] = True
        rec['correctness']['ok'] = all(rec['correctness']['checks'].values())
        return rec
    except Exception as exc:
        rec['correctness']['ok'] = False
        rec['validation_errors'].append(str(exc))
        return rec
    finally:
        try:
            if engine_ready:
                with resource_phase(engine, rec, 'cleanup') if sampler is not None else nullcontext():
                    remaining = engine.sh(['ps', '-a', '--no-trunc', '--format', '{{json .}}']).stdout
                    (trial_dir / 'containers-after.jsonl').write_text(remaining)
                    present = {json.loads(row)['Names'] for row in remaining.splitlines()}
                    for job in owned_jobs:
                        if job['name'] in present:
                            rec['correctness']['ok'] = False
                            rec['validation_errors'].append('owned job remained after --rm: ' + job['name'])
                            try:
                                ci_jobs.cleanup(engine, job['name'], job['name'].rsplit('-', 1)[0])
                            except Exception as exc:
                                rec['validation_errors'].append('cleanup failed: ' + str(exc))
                    rec['correctness']['checks']['owned_cleanup'] = not any(job['name'] in present for job in owned_jobs)
        except Exception as exc:
            rec['correctness']['ok'] = False
            rec['validation_errors'].append('cleanup verification failed: ' + str(exc))
        finally:
            if sampler is not None:
                stop_sampler(sampler)
        rec['resources'].update(summarize_trace(trace) if trace else {})
        if trace:
            rec['resources']['trace'] = _trace_ref(trace)


@dataclass(frozen=True)
class QueueInterruption:
    down_seconds: float
    recovery_timeout: float


def _recover_queue(engine, queue_id, queue, app, directory, outage):
    def snapshot(stage, timeout):
        result = engine.sh(["exec", app, "python", "/app/latency.py", "pending", "--redis-host", queue],
                           timeout=timeout, check=False)
        (directory / f"queue-{stage}.json").write_text(result.stdout)
        if result.returncode:
            raise ValueError(f"queue snapshot {stage} failed: {(result.stderr or result.stdout)[-400:]}")
        return json.loads(result.stdout)

    before = snapshot("before", 15)
    engine.sh(["kill", queue_id], timeout=30)
    time.sleep(outage.down_seconds)
    started = time.monotonic()
    engine.sh(["start", queue_id], timeout=outage.recovery_timeout)
    retries = 0

    def recovery_remaining():
        remaining = outage.recovery_timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("W10 queue recovery deadline")
        return remaining

    while True:
        remaining = recovery_remaining()
        ready = engine.sh(["exec", queue_id, "redis-cli", "PING"], timeout=min(5, remaining), check=False)
        if ready.returncode == 0 and ready.stdout.strip() == "PONG":
            break
        retries += 1
        time.sleep(min(.05, remaining))
    if snapshot("after", min(15, recovery_remaining())) != before:
        raise ValueError("recovered queue differs from the acknowledged backlog")
    elapsed = time.monotonic() - started
    if elapsed > outage.recovery_timeout:
        raise TimeoutError("W10 queue recovery deadline")
    return before, {"recovery_s": elapsed, "retries_until_recovery": retries}


def trial_w4(ctx, engine: Engine, state: str,
             workers: tuple = (1, 4, 16), fixture_version: str = "w4-v2-events", *,
             image_ref: str | None = None, redis_ref: str = W4_IMAGE,
             cleanup_command=None, queue_interruption: QueueInterruption | None = None) -> dict:
    """HTTP ingest through Redis to workers producing exact filesystem artifacts."""
    case_id = "W10" if queue_interruption is not None else "W4"
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    checks = rec["correctness"]["checks"]
    proj = project_name(ctx.run_id, engine.name, case_id)
    if queue_interruption is not None:
        proj += "-" + os.urandom(4).hex()
    net, queue, app = f"{proj}-net", f"{proj}-queue", f"{proj}-ingest"
    timed = fixture_version == W4_LATENCY_VERSION
    if queue_interruption is not None and (not timed or len(workers) != 1):
        raise ValueError("queue interruption requires one timed W4 worker condition")
    image = image_ref or (W4_LATENCY_IMAGE if timed else "np-w4-events:v2")
    label = f"dev.ctrs.campaign.run={ctx.run_id}"
    sampler = trace = None
    owned_containers, owned_volumes = [], []
    try:
        engine.ensure_up()
        engine.sh(["image", "inspect", image])
        engine.sh(["network", "create", "--label", label, net])
        mounts = []
        persistence = ["--appendonly", "no"]
        if queue_interruption is not None:
            queue_volume = f"{proj}-redis-data"
            engine.sh(["volume", "create", "--label", label, queue_volume])
            owned_volumes.append(queue_volume)
            mounts = ["-v", f"{queue_volume}:/data"]
            persistence = ["--appendonly", "yes", "--appendfsync", "always", "--aof-load-truncated", "no"]
        owned_containers.append(queue)
        queue_id = engine.sh(["run", "-d", "--name", queue, "--label", label, "--network", net,
                              *mounts, redis_ref, "redis-server", "--save", "", *persistence]).stdout.strip()
        if queue_interruption is not None and not re.fullmatch(r"[0-9a-f]{64}", queue_id):
            raise ValueError("cannot establish the owned queue container identity")
        owned_containers.append(app)
        engine.sh(["run", "-d", "--name", app, "--label", label, "--network", net,
                   image, "serve", "--redis-host", queue])
        app_hash = engine.sh(["exec", app, "python", "-c",
            "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('/app/app.py').read_bytes()).hexdigest())"]).stdout.strip()
        if app_hash != sha256_file(FIXTURES / "w4" / "app.py"):
            raise ValueError("W4 fixture image does not match current pinned input")
        rec["metrics"]["fixture_app_sha256"] = app_hash
        if timed:
            latency_hash = engine.sh(["exec", app, "python", "-c",
                "import hashlib,pathlib;print(hashlib.sha256(pathlib.Path('/app/latency.py').read_bytes()).hexdigest())"]).stdout.strip()
            if latency_hash != sha256_file(FIXTURES / "w4" / "latency.py"):
                raise ValueError("W4 latency fixture image does not match pinned input")
            rec["metrics"]["fixture_latency_sha256"] = latency_hash
        deadline = time.monotonic() + 60
        while True:
            ready = engine.sh(["exec", app, "python", "-c",
                "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=2).read()"], check=False)
            if ready.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("W4 Redis-backed ingest readiness")
            time.sleep(.1)
        sampler, trace = start_sampler(engine, trial_dir)
        conditions = ([(workers[0], "backlog"), (workers[0], "recovered")] if queue_interruption is not None
                      else [(count, str(count)) for count in workers])
        backlog = recovery = None
        for count, condition in conditions:
            volume = f"{proj}-artifacts-{condition}"
            engine.sh(["volume", "create", "--label", label, volume])
            owned_volumes.append(volume)
            if queue_interruption is None:
                engine.sh(["exec", queue, "redis-cli", "FLUSHALL"])
            with resource_phase(engine, rec, f"workers_{condition}"):
                started = time.monotonic()
                engine.sh(["exec", app, "python", "/app/app.py", "submit", "--url", "http://127.0.0.1:8080"], timeout=120)
                ingested = time.monotonic()
                if condition == "backlog":
                    backlog, recovery = _recover_queue(engine, queue_id, queue, app, trial_dir, queue_interruption)
                names = [f"{proj}-worker-{condition}-{i}" for i in range(count)]
                owned_containers.extend(names)
                def work(name):
                    return engine.sh(["run", "--name", name, "--label", label, "--network", net,
                                      "-v", f"{volume}:/output", image, "worker", "--redis-host", queue],
                                     timeout=180, check=False)
                with concurrent.futures.ThreadPoolExecutor(max_workers=count) as pool:
                    outcomes = list(pool.map(work, names))
                completed = time.monotonic()
            rec["metrics"][f"workers_{condition}_s"] = completed - started
            rec["metrics"][f"ingest_{condition}_s"] = ingested - started
            rec["metrics"][f"drain_{condition}_s"] = completed - ingested
            verifier = f"{proj}-verify-{condition}"
            owned_containers.append(verifier)
            verify = engine.sh(["run", "--rm", "--name", verifier, "--label", label, "--network", net,
                                "-v", f"{volume}:/output:ro", image, "verify", "--redis-host", queue], timeout=180, check=False)
            (trial_dir / f"workers-{condition}.json").write_text(json.dumps({
                "workers": [{"exit": cp.returncode, "stderr": cp.stderr} for cp in outcomes],
                "verification_exit": verify.returncode, "verification": verify.stdout + verify.stderr}))
            verified = all(cp.returncode == 0 for cp in outcomes) and verify.returncode == 0
            if verified and timed:
                receipt = json.loads(verify.stdout)
                latencies = sorted(w4_latency.completed_latencies(receipt))
                if condition == "backlog":
                    consumed = [{key: row[key] for key in ("job", "clock", "enqueued_ns")}
                                for row in receipt["timings"]]
                    if consumed != backlog:
                        raise ValueError("workers did not consume the recovered backlog")
                for percentile in (95, 99):
                    rank = math.ceil(percentile * len(latencies) / 100)
                    rec["metrics"][f"queue_p{percentile}_ms_at_{condition}"] = latencies[rank - 1] / 1_000_000
            checks[f"workers_{condition}"] = verified and (timed or verify.stdout.strip() == f"verified {w4_fixture.JOBS}")
            if queue_interruption is not None and not checks[f"workers_{condition}"]:
                raise ValueError(f"W10 {condition} queue work failed verification")
        rec["metrics"].update(W4_FIXED_WORK, fixture_version=fixture_version)
        if queue_interruption is not None:
            rec["metrics"].update({key: value * len(conditions) for key, value in W4_FIXED_WORK.items()})
            rec["metrics"].update(recovery, fixture_version=W10_FIXTURE_VERSION, interrupt_service="queue",
                                  queue_fixture_version=fixture_version,
                                  recovered_p99_ms=rec["metrics"]["queue_p99_ms_at_recovered"])
        rec["correctness"]["ok"] = all(checks.values())
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(str(exc))
    finally:
        try:
            if sampler is not None:
                stop_sampler(sampler)
            rec["resources"].update(summarize_trace(trace) if trace else {})
            if trace:
                rec["resources"]["trace"] = _trace_ref(trace)
        except Exception as exc:
            rec["validation_errors"].append(f"sampler shutdown or receipt: {exc}")
            rec["correctness"]["ok"] = False
        def cleanup(kind, name, remove):
            try:
                command = engine.sh if cleanup_command is None else cleanup_command
                inspected = command([kind, "inspect", name], check=False)
                if inspected.returncode:
                    if any(message in inspected.stderr.lower() for message in
                           ("no such object", "no such container", "no such volume", "no such network")):
                        return
                    raise RuntimeError(f"inspection failed: {inspected.stderr}")
                data = json.loads(inspected.stdout)[0]
                labels = data.get("Config", {}).get("Labels", {}) if kind == "container" else data.get("Labels", {})
                if not labels or labels.get("dev.ctrs.campaign.run") != ctx.run_id:
                    rec["validation_errors"].append(f"cleanup ownership mismatch: {kind} {name}")
                    rec["correctness"]["ok"] = False
                    return
                removed = command(remove, check=False)
                if removed.returncode:
                    rec["validation_errors"].append(f"cleanup failed: {kind} {name}: {removed.stderr}")
                    rec["correctness"]["ok"] = False
            except Exception as exc:
                rec["validation_errors"].append(f"cleanup error: {kind} {name}: {exc}")
                rec["correctness"]["ok"] = False
        for name in owned_containers:
            cleanup("container", name, ["rm", "-f", name])
        for volume in owned_volumes:
            cleanup("volume", volume, ["volume", "rm", volume])
        cleanup("network", net, ["network", "rm", net])
    return rec


def trial_w3(ctx, engine: Engine, state: str, fixture_version: str = W3_FIXTURE_VERSION) -> dict:
    """W3: persistent transactional Postgres — real migrations, a
    deterministic 300-transaction mix, CHECKPOINT, `docker restart`,
    then exact row and counter verification on the persisted volume."""
    from diagnostics.w8_under_pull import baseline_image_reference, require_baseline_images

    case_id = "W3"
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    trial_token = hashlib.sha256(rec["trial_id"].encode()).hexdigest()[:16]
    proj = project_name(trial_token, engine.name, case_id)
    checks = rec["correctness"]["checks"]
    name = f"{proj}-db"
    vol = f"{proj}-pgdata"
    sampler = trace = None
    volume_created = container_attempted = False
    owner_label = f"dev.ctrs.campaign.run={ctx.run_id}"

    rec["metrics"]["fixture_version"] = fixture_version
    psql_cmd = ["exec", "-e", "LC_ALL=C", name, "psql", "-X", "-v", "ON_ERROR_STOP=1",
                "-U", "postgres", "-d", "postgres"]

    def psql(sql_file: str, phase: str, timeout: float = 300):
        with resource_phase(engine, rec, phase):
            cp = engine.sh(
                [*psql_cmd, "-v", "SHOW_ALL_RESULTS=on", "-f", f"/tmp/{sql_file}"],
                timeout=timeout, check=False)
        (trial_dir / f"{sql_file}.stdout").write_text(cp.stdout)
        (trial_dir / f"{sql_file}.stderr").write_text(cp.stderr)
        if cp.returncode != 0:
            rec["validation_errors"].append(
                f"psql {sql_file} rc={cp.returncode}: "
                f"{(cp.stderr or cp.stdout)[-300:]}")
        return cp

    def wait_ready(deadline: float = 90.0,
                   stable: bool = True) -> float | None:
        t0 = time.monotonic()
        ready_at = None
        while time.monotonic() - t0 < deadline:
            if not stable:
                cp = engine.sh(["exec", name, "pg_isready", "-U", "postgres"],
                               timeout=15, check=False)
                if cp.returncode == 0:
                    return round(time.monotonic() - t0, 3)
            elif ready_at is None:
                cp = engine.sh(["exec", name, "pg_isready", "-U", "postgres"],
                               timeout=15, check=False)
                if cp.returncode == 0:
                    ready_at = time.monotonic()
            else:
                # pg_isready can pass against the entrypoint's temporary
                # init server, which then shuts down for the final
                # postmaster — the orbstack W3 flake. Require a real
                # query to keep succeeding for ~1.2 s before ready.
                # First boot only: a restart has an initialized PGDATA
                # and no temp-server phase, so plain isready is exact.
                q = engine.sh(
                    ["exec", name, "psql", "-U", "postgres", "-d",
                     "postgres", "-tAc", "SELECT 1"],
                    timeout=15, check=False)
                if q.returncode != 0 or q.stdout.strip() != "1":
                    ready_at = None
                elif time.monotonic() - ready_at > 1.2:
                    return round(ready_at - t0, 3)
            # Fine poll: restart_s is dominated by this interval otherwise
            # (0.5 s ticks once made ctrs's *faster* restart look 2.5x
            # slower — the API returns early, then waits for the next tick).
            time.sleep(0.15)
        return None

    def require_volume_owner():
        info, = json.loads(engine.sh(["volume", "inspect", vol], timeout=30).stdout)
        if info.get("Name") != vol or (info.get("Labels") or {}).get("dev.ctrs.campaign.run") != ctx.run_id:
            raise ValueError("W3 database volume ownership mismatch")

    try:
        if fixture_version != W3_FIXTURE_VERSION:
            raise ValueError("W3 fixture version mismatch")
        pin_path = FIXTURES / "w8-v5/portfolio.json"
        contract = json.loads(pin_path.read_text())
        pin = contract["images"]["np-v5/postgres"]
        image = baseline_image_reference(engine.name, pin)[1]
        engine.ensure_up()
        inspected = json.loads(engine.sh(["image", "inspect", image], timeout=30).stdout)
        rec["inputs"] = {"images": require_baseline_images(engine.name, {"db": pin}, inspected),
                         "portfolio_sha256": sha256_file(pin_path)}
        engine.sh(["volume", "create", "--label", owner_label, vol], timeout=30)
        volume_created = True
        require_volume_owner()

        t0 = time.monotonic()
        container_attempted = True
        run = engine.sh(
            ["run", "-d", "--pull=never", "--name", name, "--label", owner_label,
             "-e", f"POSTGRES_PASSWORD={W3_PASSWORD}",
             "-v", f"{vol}:/var/lib/postgresql/data", image],
            timeout=120, check=False)
        checks["db_start"] = run.returncode == 0
        ready = wait_ready() if checks["db_start"] else None
        rec["metrics"]["up_s"] = round(time.monotonic() - t0, 3)
        checks["db_ready"] = ready is not None
        if ready is None:
            raise RuntimeError("postgres never became ready")
        sampler, trace = start_sampler(engine, trial_dir)

        mig = trial_dir / "migrate.sql"
        mig.write_text(W3_SQL)
        tx = trial_dir / "txmix.sql"
        tx.write_text("SET synchronous_commit = on;\n\\timing on\n"
                      + "".join(_w3_tx_sql(i) for i in range(W3_TXS)))
        for f in (mig, tx):
            cp = engine.sh(["cp", str(f), f"{name}:/tmp/{f.name}"],
                           timeout=60, check=False)
            if cp.returncode != 0:
                rec["validation_errors"].append(
                    f"docker cp {f.name} rc={cp.returncode}: "
                    f"{(cp.stderr or cp.stdout)[-300:]}")

        migration = psql("migrate.sql", "migration")
        rec["metrics"]["migrate_s"] = rec["resources"]["phases"]["migration"]["operation_wall_seconds"]
        checks["migrate"] = migration.returncode == 0

        transactions = psql("txmix.sql", "transactions", timeout=600)
        s = rec["resources"]["phases"]["transactions"]["operation_wall_seconds"]
        rec["metrics"]["txmix_s"] = s
        checks["txmix"] = transactions.returncode == 0
        if checks["txmix"]:
            try:
                latencies = _w3_commit_timings(transactions.stdout)
            except ValueError as exc:
                checks["txmix"] = False
                rec["validation_errors"].append(str(exc))
            else:
                rec["metrics"]["tx_tps"] = len(latencies) / s if s > 0 else None
                rec["metrics"]["transaction_p95_ms"] = sorted(latencies)[math.ceil(.95 * len(latencies)) - 1]
                (trial_dir / "commit-latencies-ms.json").write_text(json.dumps(latencies) + "\n")

        tp = time.monotonic()
        cp = engine.sh(["exec", name, "psql", "-U", "postgres", "-d",
                        "postgres", "-c", "CHECKPOINT"],
                       timeout=60, check=False)
        rec["metrics"]["checkpoint_s"] = round(time.monotonic() - tp, 3)
        checks["checkpoint"] = cp.returncode == 0

        tp = time.monotonic()
        rst = engine.sh(["restart", name], timeout=120, check=False)
        ready2 = (wait_ready(stable=False)
                  if rst.returncode == 0 else None)
        rec["metrics"]["restart_s"] = round(time.monotonic() - tp, 3)
        checks["restart_ready"] = ready2 is not None

        out = engine.sh(
            [*psql_cmd, "-tA", "-c",
             "SELECT json_build_object("
             "'rows', (SELECT json_agg(json_build_array(k,v) ORDER BY k) FROM npw3_events), "
             "'meta', (SELECT json_agg(json_build_array(k,n) ORDER BY k) FROM npw3_meta), "
             "'fsync', current_setting('fsync'))"],
            timeout=60, check=False)
        (trial_dir / "persisted-rows.stdout").write_text(out.stdout)
        expected = {"rows": [[i, f"v{i}"] for i in range(W3_TXS)],
                    "meta": [["txs", W3_TXS]], "fsync": "on"}
        checks["verify_rows"] = out.returncode == 0 and json.loads(out.stdout) == expected
        if not checks["verify_rows"]:
            rec["validation_errors"].append("persisted rows, counter, or fsync differs from W3 fixture")
        # Allocated-storage cell: bytes actually allocated for the
        # persisted dataset (du counts blocks, not apparent size).
        # `du -sk` is explicit KiB on both GNU and busybox.
        du = engine.sh(["exec", name, "du", "-sk",
                        "/var/lib/postgresql/data"],
                       timeout=120, check=False)
        if du.returncode == 0:
            try:
                rec["metrics"]["pgdata_allocated_bytes"] = (
                    int(du.stdout.split()[0]) * 1024)
            except (ValueError, IndexError):
                rec["validation_errors"].append(
                    f"du parse failed: {du.stdout.strip()[:120]}")
        else:
            rec["validation_errors"].append(
                f"du rc={du.returncode}: {(du.stderr or '')[-200:]}")
        rec["correctness"]["ok"] = not rec["validation_errors"] and all(
            checks.get(k) for k in
            ("db_start", "db_ready", "migrate", "txmix", "checkpoint",
             "restart_ready", "verify_rows"))
        return rec
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(f"exception: {exc}")
        return rec
    finally:
        try:
            if sampler is not None:
                stop_sampler(sampler)
            rec["resources"].update(summarize_trace(trace) if trace else {})
            if trace:
                rec["resources"]["trace"] = _trace_ref(trace)
        except Exception as exc:
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append(f"W3 resource receipt: {exc}")

        def remove_volume():
            if volume_created:
                require_volume_owner()
                engine.sh(["volume", "rm", vol], timeout=60)

        for action in (lambda: ci_jobs.cleanup(engine, name, ctx.run_id) if container_attempted else None,
                       remove_volume):
            try:
                action()
            except Exception as exc:
                rec["correctness"]["ok"] = False
                rec["validation_errors"].append(f"W3 cleanup: {exc}")


def w5_phase_receipts(identity, phases, samples, iterations):
    receipts = {}
    for mode in ("bind", "volume"):
        for phase in ("setup", "verify-inputs", *(f"edit-{i}" for i in range(iterations)), "cleanup"):
            name = f"{mode}-{phase}"
            if name in phases:
                receipts[name] = resource_cycles.phase_summary(identity, phases[name], samples)
            else:
                receipts[name] = {"status": "unknown", "errors": ["phase boundaries unavailable"]}
    return receipts


def trial_w5(ctx, engine: Engine, state: str,
             iters: int = 5, fixture_version: str = watch_loop.RECEIPT_VERSION) -> dict:
    """Persistent real TS app watch/rebuild/test; bind and volume kept separate."""
    trial_dir = ctx.trial_dir(engine.name, "W5", state)
    rec = ctx.new_record(engine, "W5", state, trial_dir)
    sampler = trace = None
    try:
        spec = watch_loop.contract()
        if fixture_version != watch_loop.RECEIPT_VERSION:
            raise ValueError("W5 fixture version mismatch")
        archive = WORK / "inputs" / f"marked-{spec['source']['version']}.tar.gz"
        source = watch_loop.pinned_source(archive)
        engine.ensure_up()
        rec["inputs"] = watch_loop.check_image(engine, source)
        rec["paired_inputs"] = {key: rec["inputs"][key] for key in
                                ("layers", "tools", "source_sha256", "dependency_lock_sha256")}
        sampler, trace = start_sampler(engine, trial_dir)
        for mode in ("bind", "volume"):
            result = watch_loop.run_mode(engine, trial_dir / mode, mode, rec["trial_id"],
                                         archive, iters,
                                         lambda phase: resource_phase(engine, rec, f"{mode}-{phase}"),
                                         docker_cli=DOCKER, image_id=rec["inputs"]["image_id"],
                                         source_receipt=source)
            rec["metrics"][f"{mode}_edit_to_result_median_s"] = result["median_s"]
            rec["metrics"][f"{mode}_setup_s"] = result["setup_s"]
            rec["metrics"][f"{mode}_edits_s"] = [e["edit_to_result_s"] for e in result["edits"]]
            rec["correctness"]["checks"][f"{mode}_persistent_exact_results"] = True
            rec["correctness"]["checks"][f"{mode}_pinned_mount"] = True
        rec["metrics"]["fixture_version"] = fixture_version
        rec["correctness"]["ok"] = True
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(str(exc))
    finally:
        if sampler is not None:
            stop_sampler(sampler)
        rec["resources"].update(summarize_trace(trace) if trace else {})
        if trace:
            rec["resources"]["trace"] = _trace_ref(trace)
            try:
                samples = [json.loads(line) for line in trace.read_text().splitlines()]
                receipts = w5_phase_receipts(engine.measurement_identity, rec["resources"].get("phases", {}),
                                              samples, iters)
                rec["resources"]["phase_receipts"] = receipts
                missing = [name for name, receipt in receipts.items() if receipt["status"] != "ok"]
                if missing:
                    raise ValueError("unverified W5 resource phases: " + ", ".join(missing))
            except (OSError, ValueError, KeyError) as exc:
                rec.update(measurement_valid=False, measurement_invalidation=str(exc))
    return rec


def _w10_engine_identity(engine, binary_sha):
    if engine.name != "ctrs" or engine.dir != engine.recovery_root or engine.recovery_root is None:
        raise ValueError("engine interruption requires a new private ctrs root")
    child = engine.proc
    if child is None or child.poll() is not None:
        raise ValueError("recovery engine is not a live owned child")
    path = engine.dir / "run/docker.sock"
    if engine.socket != f"unix://{path}":
        raise ValueError("recovery engine socket is outside its private root")
    manifest = ownership.discover("ctrs", path, engine.dir)
    roles = recovery_trace.owned_ctrs_processes(manifest, str(path), child.pid, binary_sha)
    disk = (engine.dir / "data/vm/data.img").stat()
    return roles, (disk.st_dev, disk.st_ino)


def _w10_crash_engine(engine, before, deadline):
    child = engine.proc
    if child is None or child.pid != before["daemon"]["pid"] or child.poll() is not None:
        raise ValueError("recovery daemon identity changed before interruption")
    if time.monotonic() >= deadline:
        raise TimeoutError("load deadline expired before the planned interruption")
    child.kill()
    if child.wait(timeout=max(0, deadline - time.monotonic())) != -signal.SIGKILL:
        raise ValueError("owned daemon did not exit from the planned kill")
    engine.proc = None
    while time.monotonic() < deadline:
        current = ownership.process_table().get(before["vm"]["pid"])
        if current is None or current["start_identity"] != before["vm"]["start_identity"]:
            return
        time.sleep(.05)
    raise TimeoutError("old owned VM helper did not exit after interruption")


def _w10_auth_digest(engine, db, *, sync_startup=False):
    command = 'sha256sum "$PGDATA/pg_hba.conf"'
    if sync_startup:
        command = 'sync "$PGDATA/pg_hba.conf"\n' + command
    output = engine.sh(["exec", db, "sh", "-ec", command], timeout=15).stdout.split()
    if len(output) != 2 or not re.fullmatch(r"[0-9a-f]{64}", output[0]):
        raise ValueError("W10 database authentication file digest unavailable")
    return output[0]


def trial_w10(ctx, engine: Engine, state: str,
              duration: float = 20.0, concurrency: int = 8,
              write_ratio: float = 0.3, seed: int = 1,
              kill_at: float = 6.0, down_for: float = 3.0, *,
              interrupt_service: str = "api", fixture_version: str = W10_FIXTURE_VERSION) -> dict:
    """Interrupt one owned service during persistent load and verify recovery."""
    if fixture_version != W10_FIXTURE_VERSION:
        raise ValueError("W10 fixture version mismatch")
    if interrupt_service == "queue":
        if not all(math.isfinite(value) and value > 0 for value in (duration, down_for)) or concurrency <= 0:
            raise ValueError("W10 queue recovery requires positive duration, downtime and worker count")
        return trial_w4(ctx, engine, state, workers=(concurrency,), fixture_version=W4_LATENCY_VERSION,
                        queue_interruption=QueueInterruption(down_for, duration))
    if interrupt_service not in ("api", "db", "engine"):
        raise ValueError("W10 interrupt service must be api, db, queue or engine")
    crash_engine = interrupt_service == "engine"
    if crash_engine and (engine.name != "ctrs" or getattr(engine, "recovery_root", None) is None):
        raise ValueError("engine interruption requires a new private ctrs root")
    if (not all(math.isfinite(value) for value in (duration, kill_at, down_for, write_ratio))
            or concurrency <= 0 or not 0 <= write_ratio <= 1
            or kill_at <= 0 or down_for <= 0 or duration <= kill_at + down_for):
        raise ValueError("W10 load must cover both sides of a positive outage")
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    cenv = {"NP_API_PORT": str(port), "NP_API_TAG": API_TAG}
    trial_dir = ctx.trial_dir(engine.name, "W10", state)
    rec = ctx.new_record(engine, "W10", state, trial_dir)
    proj = project_name(hashlib.sha256(rec["trial_id"].encode()).hexdigest()[:16], engine.name, "W10")
    override = trial_dir / "pinned-compose.json"
    checks = rec["correctness"]["checks"]
    rec["metrics"].update(fixture_version=fixture_version, interrupt_service=interrupt_service)
    sampler = trace = None
    stop = threading.Event()
    attempts, probes, timeline = [], [], {}
    stack_owned = False
    t0 = time.monotonic()
    if crash_engine:
        rec.update(measurement_valid=False, measurement_invalidation="owned ctrs engine recovery diagnostic")

    def compose(args, timeout=300):
        return engine.compose(proj, args, env_extra=cenv, timeout=timeout, override=override)

    def service_id(service):
        found = compose(["ps", "-q", service], timeout=30)
        ids = found.stdout.split()
        if found.returncode or len(ids) != 1:
            raise ValueError(f"cannot establish the owned {service} container identity")
        return ids[0]

    def load(worker, deadline):
        client = recovery_client.ProbeClient("127.0.0.1", port)
        rng = random.Random(seed * 1000 + worker)
        sequence = 0
        try:
            while not stop.is_set() and time.monotonic() < deadline:
                if rng.random() < write_ratio:
                    name = f"w10-{seed}-{worker}-{sequence}"
                    attempt = client.write(name, hashlib.sha256(name.encode()).hexdigest())
                else:
                    attempt = client.query("read")
                attempts.append(attempt)
                sequence += 1
        finally:
            client.close()

    def wait_for_exact_read(deadline):
        client = recovery_client.ProbeClient("127.0.0.1", port)
        try:
            while time.monotonic() < deadline:
                attempt = client.query("read")
                probes.append(attempt)
                if attempt["ok"]:
                    return attempt["ended_ns"]
                time.sleep(.01)
        finally:
            client.close()
        raise TimeoutError("W10 did not recover before the load deadline")

    try:
        engine.ensure_up()
        if crash_engine and (engine.proc is None or engine.proc.poll() is not None):
            raise ValueError("initial recovery daemon was not launched by this run")
        layout = WORK / "inputs/w8-portfolio-v5/layout" if crash_engine else None
        _, rec["inputs"] = prepare_pinned_stack(engine, override, layout=layout)
        stack_owned = True
        if not crash_engine:
            sampler, trace = start_sampler(engine, trial_dir)
        up = compose(["up", "-d", "--no-build", "--pull", "never"])
        if up.returncode:
            raise RuntimeError(f"compose up failed: {(up.stderr or up.stdout)[-300:]}")
        ready, _ = wait_health(base, HEALTH_DEADLINE_S)
        if ready is None:
            raise RuntimeError("stack never became healthy")
        rec["metrics"]["setup_seconds"] = time.monotonic() - t0

        db = service_id("db")
        target = db if interrupt_service == "db" else service_id("api")
        if crash_engine:
            auth = rec["database_startup_auth"] = {"before": _w10_auth_digest(engine, db, sync_startup=True)}
            binary_sha = sha256_file(CTRS_BIN)
            before, disk_before = _w10_engine_identity(engine, binary_sha)
            (trial_dir / "engine-before.json").write_text(json.dumps({
                "processes": before, "disk": disk_before, "socket": engine.socket,
            }, indent=2))
        with nullcontext() if crash_engine else resource_phase(engine, rec, "recovery_workload"):
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
                load_t0 = time.monotonic()
                try:
                    futures = [pool.submit(load, worker, load_t0 + duration)
                               for worker in range(concurrency)]
                    time.sleep(max(0, load_t0 + kill_at - time.monotonic()))
                    timeline["kill_command_begin_ns"] = time.monotonic_ns()
                    if crash_engine:
                        _w10_crash_engine(engine, before, load_t0 + duration)
                    else:
                        engine.sh(["kill", target], timeout=30)
                    timeline["kill_command_returned_ns"] = time.monotonic_ns()
                    time.sleep(down_for)
                    timeline["start_command_begin_ns"] = time.monotonic_ns()
                    if crash_engine:
                        remaining = load_t0 + duration - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError("no time remains to recover the owned engine")
                        engine.ensure_up(timeout=remaining)
                        if engine.proc is None or engine.proc.poll() is not None:
                            stack_owned = False
                            raise ValueError("recovery daemon was not launched by this run")
                        remaining = load_t0 + duration - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError("owned engine did not return before the load deadline")
                        restored = compose(["up", "-d", "--no-build", "--pull", "never"], timeout=remaining)
                        if restored.returncode:
                            raise RuntimeError(f"owned stack recovery failed: {(restored.stderr or restored.stdout)[-300:]}")
                    else:
                        engine.sh(["start", target], timeout=120)
                    timeline["start_command_returned_ns"] = time.monotonic_ns()
                    if crash_engine:
                        auth["after"] = _w10_auth_digest(engine, db)
                        if auth["after"] != auth["before"]:
                            raise ValueError("W10 database authentication file changed across VM restart")
                        checks["database_startup_auth_preserved"] = True
                    timeline["first_success_ns"] = wait_for_exact_read(load_t0 + duration)
                    for future in futures:
                        future.result()
                finally:
                    stop.set()

        interrupted = timeline["kill_command_begin_ns"]
        recovered = timeline["first_success_ns"]
        failures = recovery_trace.classify_failures([*attempts, *probes], interrupted, recovered)
        if crash_engine:
            after, disk_after = _w10_engine_identity(engine, binary_sha)
            (trial_dir / "engine-after.json").write_text(json.dumps({
                "processes": after, "disk": disk_after, "socket": engine.socket,
            }, indent=2))
            recovery_trace.verify_ctrs_restart(before, after, disk_before, disk_after)
            if service_id("db") != db or service_id("api") != target:
                raise ValueError("owned stack containers were replaced during recovery")
            checks["owned_engine_restarted"] = True
        (trial_dir / "request-validation.json").write_text(json.dumps(failures, indent=2) + "\n")
        rec["metrics"].update(expected_outage_errors=len(failures["expected_outage_errors"]),
                              unexpected_errors=len(failures["unexpected_errors"]),
                              retries_until_recovery=len(probes) - 1)
        checks["request_failures_explained"] = failures["host_client_valid"] and not failures["unexpected_errors"]
        acknowledged = [attempt["write"] for attempt in attempts if attempt["kind"] == "write" and attempt["ok"]]
        uncertain = [attempt["write"] for attempt in failures["expected_outage_errors"] if attempt["kind"] == "write"]
        result = engine.sh(["exec", db, "psql", "-X", "-U", "app", "-d", "app", "-At", "-c",
            "SELECT coalesce(json_agg(json_build_array(id,name,payload) ORDER BY id),'[]'::json) FROM items"],
            timeout=60)
        (trial_dir / "persisted-items.json").write_text(result.stdout)
        persisted_uncertain = recovery_trace.verify_persisted_items(json.loads(result.stdout), acknowledged, uncertain)
        checks["exact_persisted_items"] = True
        rec["metrics"].update(acknowledged_writes=len(acknowledged), persisted_uncertain_writes=persisted_uncertain)
        tails = recovery_trace.workload_metrics(attempts, interrupted, recovered,
                                               require_reads=write_ratio < 1, require_writes=write_ratio > 0)
        checks["complete_load_phases"] = True
        if checks["request_failures_explained"]:
            rec["metrics"].update(recovery_s=recovery_trace.recovery_intervals(timeline)["command_and_ready_s"], **tails)
        rec["correctness"]["ok"] = all(checks.values())
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(str(exc))
    finally:
        def cleanup_stack():
            if stack_owned:
                down = compose(["down", "-v", "--remove-orphans"], timeout=90)
                if down.returncode:
                    raise RuntimeError((down.stderr or down.stdout)[-300:])

        for label, action in (
                ("sampler shutdown", lambda: stop_sampler(sampler) if sampler is not None else None),
                ("owned stack cleanup", cleanup_stack)):
            try:
                action()
            except Exception as exc:
                rec["correctness"]["ok"] = False
                rec["validation_errors"].append(f"{label}: {exc}")
        (trial_dir / "timeline.json").write_text(json.dumps(timeline, indent=2) + "\n")
        with (trial_dir / "attempts.jsonl").open("w") as output:
            for attempt in sorted([*attempts, *probes], key=lambda value: value["started_ns"]):
                output.write(json.dumps(attempt) + "\n")
        rec["resources"].update(summarize_trace(trace) if trace else {})
        if trace:
            rec["resources"]["trace"] = _trace_ref(trace)
    return rec


def http_json_write(url: str, obj: dict, timeout: float = 10.0):
    req = urllib.request.Request(
        url, data=json.dumps(obj).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:300]
    except Exception as e:
        return 0, {"transport_error": str(e)}


def trial_w11(ctx, engine: Engine, state: str,
              duration: float = 300.0, window: float = 30.0,
              concurrency: int = 8, write_ratio: float = 0.3,
              seed: int = 1, churn_jobs: int = 8,
              churn_every: int = 4) -> dict:
    """W11: sustained-operation soak — the W1 stack under repeated
    load windows interleaved with container-churn bursts until the
    duration deadline. Gates: engine answers `docker version` at the
    end (no unplanned death), every load window has zero errors,
    every churn job exits 0. The resource sampler runs for the whole
    trial so RSS/CPU growth is captured. v1 pilot default is 300 s;
    the campaign target is 12-24 h via --duration."""
    case_id = "W11"
    proj = project_name(ctx.run_id, engine.name, case_id)
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    cenv = {"NP_API_PORT": str(port), "NP_API_TAG": API_TAG}
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    trial_dir.mkdir(parents=True, exist_ok=True)
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    checks = rec["correctness"]["checks"]
    sampler = trace = None
    t0 = time.monotonic()
    deadline = t0 + duration
    try:
        engine.ensure_up()
        compose_down(engine, proj)
        sampler, trace = start_sampler(engine, trial_dir)
        up = engine.compose(proj, ["up", "-d"], env_extra=cenv, timeout=300)
        if up.returncode != 0:
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append(
                f"compose up rc={up.returncode}: "
                f"{(up.stderr or up.stdout)[-300:]}")
            return rec
        t_ready, _ = wait_health(base, HEALTH_DEADLINE_S)
        if t_ready is None:
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append("stack never became healthy")
            return rec
        rec["metrics"]["setup_seconds"] = round(t_ready - t0, 3)

        total_req = total_ok = total_err = total_writes = windows = churn_done = 0
        churn_fail = version_fail = invalid_windows = 0
        wseed = seed
        while time.monotonic() < deadline:
            windows += 1
            wseed += 1
            out = trial_dir / f"load-{windows:03d}.json"
            window_duration = min(window, max(0.0, deadline - time.monotonic()))
            load = subprocess.run(
                [sys.executable, str(LOAD_PY), "--url", base,
                 "--concurrency", str(concurrency),
                 "--duration", str(window_duration),
                 "--write-ratio", str(write_ratio),
                 "--seed", str(wseed), "--out", str(out)],
                capture_output=True, text=True,
                timeout=window_duration + 120)
            if out.exists():
                s = json.loads(out.read_text())
                total_req += s["requests"]
                total_err += s["errors"]
                total_writes += s["writes_ok"]
                total_ok += s["reads_ok"] + s["writes_ok"]
                if load.returncode != 0 or s["requests"] <= 0:
                    invalid_windows += 1
                    rec["validation_errors"].append(
                        f"window {windows}: invalid load result (rc={load.returncode})")
            else:
                invalid_windows += 1
                rec["validation_errors"].append(
                    f"window {windows}: load driver no summary: "
                    f"{load.stderr[-200:]}")
            cp = engine.sh(["version", "--format", "{{.Server.Version}}"],
                           timeout=15, check=False)
            if cp.returncode != 0:
                version_fail += 1
            if windows % churn_every == 0 and time.monotonic() < deadline:
                with concurrent.futures.ThreadPoolExecutor(
                        max_workers=churn_jobs) as ex:
                    futs = [
                        ex.submit(engine.sh,
                                  ["run", "--rm", W11_CHURN_IMAGE, "python3",
                                   "-c", W11_CHURN_WORK, str(i)],
                                  timeout=180, check=False)
                        for i in range(churn_jobs)
                    ]
                    outs = [f.result() for f in futs]
                churn_done += sum(
                    1 for c in outs
                    if c.returncode == 0 and "ok" in c.stdout)
                churn_fail += sum(1 for c in outs if c.returncode != 0)
                churn_fail += sum(1 for c in outs
                                  if c.returncode == 0 and "ok" not in c.stdout)

        rec["metrics"].update({
            "soak_seconds": round(time.monotonic() - t0, 3),
            "windows": windows,
            "requests": total_req,
            "requests_ok": total_ok,
            "errors": total_err,
            "error_pct": round(100.0 * total_err / max(total_req, 1), 4),
            "writes_ok": total_writes,
            "rps_mean": round(total_ok / max(
                time.monotonic() - t0 - rec["metrics"]["setup_seconds"], 1), 1),
            "churn_jobs_completed": churn_done,
            "churn_failures": churn_fail,
            "engine_version_check_failures": version_fail,
            "invalid_load_windows": invalid_windows,
        })
        status, stats = http_json(f"{base}/stats", timeout=10)
        expected_items = 500 + total_writes
        got_items = stats.get("items") if isinstance(stats, dict) else None
        checks["item_count"] = {
            "expected": expected_items, "got": got_items,
            "ok": status == 200 and got_items == expected_items}
        checks["engine_alive"] = version_fail == 0
        checks["errors_zero"] = total_err == 0
        checks["load_windows_valid"] = (
            windows > 0 and total_ok > 0 and invalid_windows == 0
            and total_req == total_ok + total_err)
        checks["churn_all_ok"] = churn_fail == 0
        rec["correctness"]["ok"] = all(
            v is True or (isinstance(v, dict) and v.get("ok"))
            for v in checks.values())
        return rec
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(f"exception: {exc}")
        return rec
    finally:
        compose_down(engine, proj)
        if sampler is not None:
            stop_sampler(sampler)
        rec["resources"].update(summarize_trace(trace) if trace else {})
        if trace:
            rec["resources"]["trace"] = _trace_ref(trace)


def _holdout_api(base: str, method: str, path: str, body: dict | None = None,
                 timeout: float = 15.0):
    """One Gitea API call with admin basic auth; returns (status, json)."""
    url = f"{base}/api/v1{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization",
                   "Basic " + base64.b64encode(
                       f"{HOLDOUT_USER}:{HOLDOUT_PASSWORD}".encode()).decode())
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return e.code, {}


def trial_holdout(ctx, engine: Engine, state: str,
                  ops: int = 240, repos: int = 8, issues: int = 5,
                  clones: int = 4, seed: int = 1) -> dict:
    """Holdout gate: a real third-party application (Gitea + Postgres)
    that was never tuned against — different language, framework and
    data model from the W1 fixture. Seeds repos/issues over the REST
    API, serves a timed read workload through the published port, and
    finishes with real `git clone` smart-HTTP operations. Run once per
    engine at milestone/final gates; not a scored W-cell."""
    case_id = "HOLDOUT"
    proj = project_name(ctx.run_id, engine.name, case_id)
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    cenv = {"NP_GITEA_PORT": str(port)}
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    trial_dir.mkdir(parents=True, exist_ok=True)
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    checks = rec["correctness"]["checks"]
    sampler = trace = None
    t0 = time.monotonic()
    try:
        engine.ensure_up()
        compose_down(engine, proj, HOLDOUT_COMPOSE)
        sampler, trace = start_sampler(engine, trial_dir)
        t_up = time.monotonic()
        up = engine.sh(
            ["compose", "-f", str(HOLDOUT_COMPOSE), "-p", proj,
             "up", "-d"], env_extra=cenv, timeout=600, check=False)
        rec["metrics"]["setup_seconds"] = round(time.monotonic() - t_up, 3)
        if up.returncode != 0:
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append(
                f"compose up rc={up.returncode}: "
                f"{(up.stderr or up.stdout)[-300:]}")
            return rec

        # /api/healthz answers once Gitea finished its first-boot schema
        # setup against Postgres.
        deadline = time.monotonic() + HEALTH_DEADLINE_S
        healthy = False
        while time.monotonic() < deadline:
            status, body = http_json(f"{base}/api/healthz", timeout=3)
            if status == 200:
                healthy = True
                break
            time.sleep(POLL_INTERVAL_S)
        rec["metrics"]["time_to_health_s"] = round(
            time.monotonic() - t_up, 3)
        checks["healthz"] = healthy
        if not healthy:
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append("gitea never became healthy")
            return rec

        # First boot with INSTALL_LOCK still leaves the instance without
        # an admin; create one through the image's own CLI.
        t_admin = time.monotonic()
        adm = engine.sh(
            ["compose", "-f", str(HOLDOUT_COMPOSE), "-p", proj,
             "exec", "-T", "--user", "git", "gitea", "gitea",
             "admin", "user", "create",
             "--username", HOLDOUT_USER, "--password", HOLDOUT_PASSWORD,
             "--email", "np@bench.local", "--admin",
             "--must-change-password=false"],
            timeout=60, check=False)
        checks["admin_created"] = adm.returncode == 0
        if not checks["admin_created"]:
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append(
                f"admin create rc={adm.returncode}: "
                f"{(adm.stderr or adm.stdout)[-300:]}")
            return rec
        rec["metrics"]["admin_s"] = round(time.monotonic() - t_admin, 3)

        # Seed: real REST writes — repos with auto_init, then issues.
        t_seed = time.monotonic()
        repo_ok = issue_ok = 0
        for i in range(repos):
            name = f"repo-{i:02d}"
            st, _ = _holdout_api(
                base, "POST", "/user/repos",
                {"name": name, "private": False, "auto_init": True,
                 "default_branch": "main",
                 "description": f"holdout repo {i}"})
            if st in (200, 201):
                repo_ok += 1
            for j in range(issues):
                st, _ = _holdout_api(
                    base, "POST", f"/repos/{HOLDOUT_USER}/{name}/issues",
                    {"title": f"issue-{j}", "body": f"seeded {j}"})
                if st in (200, 201):
                    issue_ok += 1
        rec["metrics"]["seed_s"] = round(time.monotonic() - t_seed, 3)
        rec["metrics"]["repos_created"] = repo_ok
        rec["metrics"]["issues_created"] = issue_ok
        checks["repos_exact"] = repo_ok == repos
        checks["issues_exact"] = issue_ok == repos * issues
        if not (checks["repos_exact"] and checks["issues_exact"]):
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append(
                f"seed incomplete: {repo_ok}/{repos} repos, "
                f"{issue_ok}/{repos * issues} issues")
            return rec

        # Timed read workload over the published port: rotate repo get,
        # issue list and repo list calls; every 8th op also lists
        # branches (a second table join in Gitea).
        t_w = time.monotonic()
        api_errors = 0
        for i in range(ops):
            repo = f"repo-{i % repos:02d}"
            if i % 8 == 7:
                st, _ = _holdout_api(
                    base, "GET", f"/repos/{HOLDOUT_USER}/{repo}/branches")
            elif i % 3 == 0:
                st, _ = _holdout_api(
                    base, "GET",
                    f"/repos/{HOLDOUT_USER}/{repo}/issues"
                    "?state=all&limit=50")
            elif i % 3 == 1:
                st, _ = _holdout_api(
                    base, "GET", f"/repos/{HOLDOUT_USER}/{repo}")
            else:
                st, _ = _holdout_api(
                    base, "GET", "/user/repos?limit=50")
            if st != 200:
                api_errors += 1
        rec["metrics"]["workload_s"] = round(time.monotonic() - t_w, 3)
        rec["metrics"]["ops"] = ops
        rec["metrics"]["api_errors"] = api_errors
        rec["metrics"]["ops_per_s"] = round(
            ops / max(rec["metrics"]["workload_s"], 1e-6), 1)
        checks["workload_zero_errors"] = api_errors == 0

        # Real git smart-HTTP: shallow clones through the published port,
        # credentials in the URL exactly as a user would type them.
        t_c = time.monotonic()
        clone_ok = 0
        for c in range(clones):
            repo = f"repo-{c % repos:02d}"
            dest = trial_dir / f"clone-{c}"
            url = (f"http://{HOLDOUT_USER}:{HOLDOUT_PASSWORD}"
                   f"@127.0.0.1:{port}/{HOLDOUT_USER}/{repo}.git")
            cp = subprocess.run(
                ["git", "clone", "--depth", "1", "--quiet", url,
                 str(dest)], capture_output=True, text=True, timeout=120)
            if cp.returncode == 0 and (dest / "README.md").exists():
                clone_ok += 1
        rec["metrics"]["clone_s"] = round(time.monotonic() - t_c, 3)
        rec["metrics"]["clones"] = clones
        checks["clones_exact"] = clone_ok == clones

        checks["all"] = all(
            v for k, v in checks.items() if k != "all")
        rec["correctness"]["ok"] = bool(checks["all"])
        rec["metrics"]["wall_seconds"] = round(time.monotonic() - t0, 3)
        return rec
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(f"exception: {exc}")
        rec["metrics"]["wall_seconds"] = round(time.monotonic() - t0, 3)
        return rec
    finally:
        compose_down(engine, proj, HOLDOUT_COMPOSE)
        if sampler is not None:
            stop_sampler(sampler)
        rec["resources"].update(summarize_trace(trace) if trace else {})
        if trace:
            rec["resources"]["trace"] = _trace_ref(trace)


class RunContext:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.results_dir = RESULTS / run_id
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl = self.results_dir / "trials.jsonl"
        self.host_id = socket.gethostname()
        self.arch = os.uname().machine
        self.git_sha = git_sha()
        self._seq = 0
        self.engines: dict[str, Engine] = {}
        manifest = validate_manifest()
        self.provenance = {
            key: value for key, value in manifest.items() if key.endswith("sha256")}
        self.provenance.update({
            "runner_sha256": sha256_file(Path(__file__)),
            "build_outputs": {"ctrs_binary_sha256": sha256_file(CTRS_BIN),
                              **guest_provenance()},
            "sampler_sha256": sha256_file(COLLECT),
            "ownership_collector_sha256": sha256_file(BENCH / "ownership.py"),
            "counter_module_sha256": sha256_file(BENCH / "macos_counters.py"),
            "worktree_dirty": bool(subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=normal"],
                cwd=REPO, capture_output=True, text=True).stdout.strip()),
        })
        self.workload_params: dict = {}
        self.workload_id = f"{run_id}:standalone"
        # "paired" = cross-engine A/B trial; "noise-control" = same-engine
        # slot repeat used only to size measurement noise, never scored
        # as engine performance.
        self.design = "paired"
        self.resource_lane = "matched"

    def trial_dir(self, engine: str, case: str, state: str) -> Path:
        self._seq += 1
        d = (self.results_dir / "trials"
             / f"{self._seq:03d}-{engine}-{case}-{state}")
        d.mkdir(parents=True, exist_ok=True)
        return d

    def new_record(self, engine: Engine, case: str, state: str,
                   trial_dir: Path) -> dict:
        return {
            "schema": 1,
            "trial_id": f"{self.run_id}-{trial_dir.name}",
            "run_id": self.run_id,
            "case": case,
            "engine": engine.name,
            "engine_server_version": "not-observed",
            "state": state,
            "pair_id": None,
            "order_index": None,
            "slot": None,
            "design": self.design,
            "host_id": self.host_id,
            "arch": self.arch,
            "git_sha": self.git_sha,
            "evidence_status": "pilot",
            "provenance": dict(self.provenance),
            "workload_params": dict(self.workload_params),
            "workload_id": self.workload_id,
            "started_utc": utcnow(),
            "metrics": {},
            "correctness": {"ok": True, "checks": {}},
            "resources": {},
            "validation_errors": [],
            "notes": [],
        }

    def write(self, rec: dict) -> None:
        rec["finished_utc"] = utcnow()
        with open(self.jsonl, "a") as f:
            f.write(json.dumps(rec) + "\n")


def git_sha() -> str:
    cp = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                        capture_output=True, text=True)
    return cp.stdout.strip() or "unknown"


def safe_version(engine: Engine) -> str:
    try:
        return engine.server_version()
    except Exception:
        return "unreachable"


def safe_engine_info(engine: Engine) -> dict | None:
    """`docker info` NCPU/MemTotal for the engine's VM/host allocation —
    recorded per trial so resource asymmetries are visible in results."""
    try:
        cp = engine.sh(["info", "--format", "{{.NCPU}} {{.MemTotal}}"],
                       timeout=20, check=False)
        if cp.returncode != 0:
            return None
        ncpu_s, mem_s = cp.stdout.split()
        return {"ncpu": int(ncpu_s), "mem_total_bytes": int(mem_s)}
    except Exception:
        return None


def run_one(ctx: RunContext, engine_name: str, case_id: str, state: str,
            cold: bool = False, pair_id: int | None = None,
            order_index: int | None = None, keep_warm: bool = False,
            slot: str | None = None, **kw) -> dict:
    trials = {"W1": trial_w1, "W2": trial_w2, "W3": trial_w3,
              "W4": trial_w4, "W5": trial_w5, "W6": trial_w6,
              "W7": trial_w7, "W8": trial_w8, "W9": trial_w9,
              "W10": trial_w10, "W11": trial_w11, "W12": workspace.trial_w12,
              "W12-watch": workspace.trial_w12_watch, "W13": trial_w13,
              "HOLDOUT": trial_holdout}
    if case_id not in trials:
        raise ValueError(f"case {case_id} not implemented")
    trial = trials[case_id]
    if case_id == "W4":
        kw.setdefault("fixture_version", W4_LATENCY_VERSION)
    if case_id == "W2" and pair_id is not None:
        kw["pinned_stack"] = True
    defaults = {name: parameter.default
                for name, parameter in inspect.signature(trial).parameters.items()
                if parameter.default is not inspect.Parameter.empty}
    ctx.workload_id = workload_id(ctx.run_id, case_id, pair_id, ctx._seq + 1)
    ctx.workload_params = {
        name: value.value if isinstance(value, Enum) else value
        for name, value in {"cold": cold, **defaults, **kw}.items()
    }
    ctx.workload_params["resource_lane"] = ctx.resource_lane
    if case_id == "W10" and kw.get("interrupt_service") == "engine":
        if engine_name != "ctrs" or cold or keep_warm:
            raise ValueError("engine interruption requires a standalone ctrs recovery run")
        engine = Engine.for_recovery(ctx.run_id)
        stop = True
    elif cold:
        # Socket paths must stay under SUN_LEN (~104): keep cold engine
        # dirs short and outside the deep results tree.
        short = f"{engine_name}-cold-{ctx.run_id[-6:]}-{time.time_ns() % 100000:05d}"
        engine = Engine(engine_name, ctx.run_id,
                        fresh_dir=WORK / "engines" / short,
                        resource_lane=ctx.resource_lane)
        stop = True
    else:
        # Warm trials share one daemon/VM per engine for the whole batch so
        # "warm" means hot engine on both sides (OrbStack's daemon is
        # always hot; ctrs must not be restarted per trial).
        engine = ctx.engines.get(engine_name)
        if engine is None:
            engine = Engine(engine_name, ctx.run_id, resource_lane=ctx.resource_lane)
            ctx.engines[engine_name] = engine
        stop = not keep_warm
    try:
        rec = trial(ctx, engine, state, **kw)
        rec["pair_id"] = pair_id
        rec["order_index"] = order_index
        rec["slot"] = slot
        # The trial starts the engine. Sampling before ensure_up() records
        # a false version change on the first cold/stopped-engine trial.
        rec["engine_server_version"] = safe_version(engine)
        if rec["engine_server_version"] == "unreachable":
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append("engine unreachable after trial")
        info = safe_engine_info(engine)
        if info is not None:
            df = engine.system_df()
            if df:
                info["system_df"] = df
            rec["resources"]["engine"] = info
        ctx.write(rec)
        return rec
    finally:
        if stop:
            engine.stop()


def cmd_preflight(args) -> int:
    failures = []
    warnings = []
    report = {"utc": utcnow(), "host_id": socket.gethostname(),
              "arch": os.uname().machine}

    if os.uname().sysname != "Darwin":
        failures.append("this campaign requires a macOS host")
    if os.uname().machine != "arm64":
        failures.append("host is not arm64; macOS lane requires Apple Silicon")
    for path, label in (
            (CTRS_BIN, "ctrs binary"),
            (REPO / "guest" / "out" / "Image", "guest kernel"),
            (REPO / "guest" / "out" / "initramfs.cpio", "initramfs"),
            (REPO / "guest" / "out" / "data.img", "data disk")):
        if not path.exists():
            failures.append(f"missing {label}: {path}")
    report["ctrs_binary"] = str(CTRS_BIN)

    try:
        v = subprocess.run([DOCKER, "version"], capture_output=True,
                           text=True, timeout=30)
        report["docker_cli_raw"] = v.stdout.strip().splitlines()[:2]
        if v.returncode != 0:
            failures.append("docker version failed")
    except Exception as e:
        failures.append(f"docker CLI: {e}")
    try:
        v = subprocess.run([DOCKER, "compose", "version"],
                           capture_output=True, text=True, timeout=30)
        report["compose_version"] = v.stdout.strip()
    except Exception as e:
        failures.append(f"docker compose: {e}")

    orb = Engine("orbstack", "preflight")
    try:
        orb.ensure_up()
        report["orbstack"] = {
            "socket": orb.socket,
            "server_version": orb.server_version(),
        }
    except Exception as e:
        failures.append(f"orbstack unreachable: {e}")

    report["python"] = sys.version.split()[0]
    la = os.getloadavg()
    report["loadavg"] = list(la)
    if la[0] > os.cpu_count() * 2:
        warnings.append(f"high load average {la[0]:.1f}; trials may be noisy")
    st = os.statvfs(WORK)
    report["work_free_gb"] = round(st.f_bavail * st.f_frsize / 1e9, 1)
    if report["work_free_gb"] < 20:
        failures.append("less than 20 GB free under .work/")

    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"preflight-{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    out.write_text(json.dumps({"checks": report, "failures": failures,
                               "warnings": warnings}, indent=2) + "\n")
    print(json.dumps({"failures": failures, "warnings": warnings,
                      "report": str(out)}, indent=2))
    return 1 if failures else 0


def save_w8_portfolio(updates):
    if PORTFOLIO_FILE.is_symlink():
        raise ValueError("W8 portfolio must be an owned regular file")
    try:
        existing = json.loads(PORTFOLIO_FILE.read_text())
    except FileNotFoundError:
        existing = {}
    if not isinstance(existing, dict):
        raise ValueError("W8 portfolio must contain engine sections")
    existing.update(updates)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=PORTFOLIO_FILE.parent,
                                         prefix=".w8-portfolio-", delete=False) as out:
            temporary = Path(out.name)
            json.dump(existing, out, indent=2)
            out.write("\n")
        os.replace(temporary, PORTFOLIO_FILE)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def cmd_prepare(args) -> int:
    scratch = WORK / "tmp"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch, prefix="w5-common-") as temporary:
        return prepare_engines(args, Path(temporary) / "marked.tar")


def prepare_engines(args, w5_image_archive: Path) -> int:
    """Untimed setup: pull service images and build the fixture API image
    on each selected engine."""
    engines = args.engines.split(",")
    ctx = RunContext(f"prep-{datetime.now().strftime('%Y%m%dT%H%M%S')}")
    for pin in W6_SOURCES.values():
        ensure_pinned_source(pin, W6_DIR)
    summary = {}
    portfolio = {}
    for name in engines:
        engine = Engine(name, ctx.run_id)
        try:
            engine.ensure_up()
            for img in SERVICE_IMAGES + [REGISTRY_IMAGE]:
                engine.sh(["pull", img], timeout=600)
            # --load: ctrs's buildx docker-container driver otherwise
            # leaves results in the build cache only.
            engine.sh(["build", "--load", "-t", f"np-fixture-api:{API_TAG}",
                       str(API_DOCKERFILE_DIR)], timeout=900)
            ids, arches = {}, {}
            for img in SERVICE_IMAGES + [f"np-fixture-api:{API_TAG}"]:
                cp = engine.sh(
                    ["image", "inspect", "-f",
                     "{{.Id}} {{.Architecture}} {{json .RepoDigests}}", img],
                    check=False, timeout=30)
                parts = cp.stdout.split(None, 2)
                ids[img] = cp.stdout.strip() or cp.stderr.strip()
                if len(parts) >= 2:
                    arches[img] = parts[1]
            summary[name] = {"images": ids, "architectures": arches}
            odd = {img: a for img, a in arches.items() if a != "arm64"}
            if odd:
                print(f"{name}: WARNING non-arm64 images: {odd}")

            w4_dir = FIXTURES / "w4"
            engine.sh(["build", "--load", "--platform", "linux/arm64", "-t", W4_LATENCY_IMAGE,
                       "-f", str(w4_dir / "Dockerfile.latency"), str(w4_dir)], timeout=300)
            w5_source = watch_loop.contract()["source"]
            w5_archive = ensure_pinned_source({"file": f"marked-{w5_source['version']}.tar.gz",
                "url": w5_source["url"], "sha256": w5_source["sha256"]}, WORK / "inputs")
            watch_loop.prepare_shared_image(engine, w5_archive, w5_image_archive)

            # W8: local registry + relocated-image portfolio. Builds load
            # locally (buildkit inside the VM cannot reach the host-side
            # registry), then the engine pushes and every local ref is
            # dropped again. Layer/content caches may remain: these
            # warm-engine pilots do not prove an empty-store pull.
            port = ensure_registry(engine)
            reg = f"127.0.0.1:{port}"
            engine_portfolio = {}
            for spec in W8_IMAGES:
                local = f"npw8/{spec['name']}:v1"
                ref = f"{reg}/npw8/{spec['name']}:v1"
                # --load: ctrs's buildx docker-container driver otherwise
                # leaves results in the build cache only.
                engine.sh(["build", "--load", "-q", "-t", local,
                           str(W8_DIR / spec["dir"])], timeout=900)
                engine.sh(["tag", local, ref], timeout=60)
                engine.sh(["push", ref], timeout=900)
                cp = engine.sh(
                    ["image", "inspect", "-f",
                     "{{index .RepoDigests 0}}", ref], timeout=30)
                digest = cp.stdout.strip().rsplit("@", 1)[-1]
                for drop in (local, ref):
                    engine.sh(["rmi", "-f", drop], check=False, timeout=60)
                engine_portfolio[spec["name"]] = {
                    "pull_ref": f"{ref.rsplit(':', 1)[0]}@{digest}",
                    "tag_ref": ref,
                    "local_ref": local,
                    "digest": digest,
                    "verify": spec["verify"],
                    "expect": spec["expect"],
                }
            portfolio[name] = engine_portfolio
            print(f"{name}: prepared {len(ids)} images + "
                  f"{len(engine_portfolio)} W8 portfolio images")
        finally:
            engine.stop()
    out = ctx.results_dir / "prepare.json"
    out.write_text(json.dumps(summary, indent=2) + "\n")
    save_w8_portfolio(portfolio)
    print(f"wrote {out} and {PORTFOLIO_FILE}")
    return 0


def cmd_run(args) -> int:
    ctx = RunContext(f"run-{datetime.now().strftime('%Y%m%dT%H%M%S')}-"
                     f"{random.randint(0, 0xffff):04x}")
    kw = {}
    if args.case in ("W2", "W8", "W10", "W11"):
        kw = {"concurrency": args.concurrency, "duration": args.duration,
              "write_ratio": args.write_ratio, "seed": args.seed}
    if args.case == "W9":
        kw["image_ref"] = args.image_ref
    if args.case == "W2":
        kw["operations"] = getattr(args, "operations", None)
        kw["request_rate"] = getattr(args, "request_rate", None)
        if getattr(args, "client_location", None) is not None:
            kw["client_location"] = args.client_location
    if args.case == "W10" and getattr(args, "interrupt_service", None) is not None:
        kw["interrupt_service"] = args.interrupt_service
    if args.case in ("W6", "W7"):
        kw = {"driver": getattr(args, "driver", "default")}
    if args.case == "W6" and getattr(args, "build_cache", None) is not None:
        kw["build_cache"] = args.build_cache
    if args.case == "W8" and getattr(args, "under_load", False):
        kw["under_load"] = True
    rec = run_one(ctx, args.engine, args.case, args.state,
                  cold=args.cold, **kw)
    m = rec["metrics"]
    print(json.dumps({"trial_id": rec["trial_id"], "ok": rec["correctness"]["ok"],
                      "metrics": m, "errors": rec["validation_errors"]},
                     indent=2))
    return 0 if rec["correctness"]["ok"] else 1


def cmd_baseline(args) -> int:
    ctx = RunContext(f"base-{datetime.now().strftime('%Y%m%dT%H%M%S')}-"
                     f"{random.randint(0, 0xffff):04x}")
    ctx.design = ("noise-control" if getattr(args, "noise_control", False)
                  else "paired")
    ctx.resource_lane = getattr(args, "resource_lane", "matched")
    a, b = args.a, args.b
    rng = random.Random(args.seed)
    failed = False
    try:
        for pair in range(1, args.pairs + 1):
            # Slots identify the configured A/B position, not the engine:
            # noise-control runs put the same engine in both slots.
            sides = [(a, "a"), (b, "b")]
            order = sides if (pair % 2 == 1) else sides[::-1]
            if args.randomize:
                order = [sides[0], sides[1]]
                rng.shuffle(order)
            for idx, (eng, slot) in enumerate(order):
                kw = {}
                if args.case in ("W2", "W8", "W10", "W11"):
                    kw = {"concurrency": args.concurrency,
                          "duration": args.duration,
                          "write_ratio": args.write_ratio,
                          "seed": args.seed + pair * 10}
                if args.case == "W9":
                    kw["image_ref"] = args.image_ref
                if args.case == "W2":
                    kw["operations"] = getattr(args, "operations", None)
                    kw["request_rate"] = getattr(args, "request_rate", None)
                    if getattr(args, "client_location", None) is not None:
                        kw["client_location"] = args.client_location
                if args.case == "W10" and getattr(args, "interrupt_service", None) is not None:
                    kw["interrupt_service"] = args.interrupt_service
                if args.case in ("W6", "W7"):
                    kw = {"driver": getattr(args, "driver", "default")}
                if args.case == "W6" and getattr(args, "build_cache", None) is not None:
                    kw["build_cache"] = args.build_cache
                if args.case == "W8" and getattr(args, "under_load", False):
                    kw["under_load"] = True
                if args.case == "W12":
                    kw = {"layout": args.workspace_layout}
                if args.case == "W12-watch":
                    kw = {"mount": args.watch_mount, "edits": args.watch_edits}
                if args.case == "W13":
                    kw = {"path": args.transfer_path, "direction": args.direction,
                          "streams": args.streams, "size_bytes": args.size_bytes,
                          "repeats": args.repeats}
                rec = run_one(ctx, eng, args.case, args.state,
                              cold=args.cold and eng == "ctrs",
                              pair_id=pair, order_index=idx, keep_warm=True,
                              slot=slot, **kw)
                ok = rec["correctness"]["ok"]
                failed = failed or not ok or bool(rec.get("validation_errors"))
                wall = rec["metrics"].get("wall_seconds")
                print(f"pair {pair} {eng} {'OK' if ok else 'FAIL'} "
                      f"wall={wall}", flush=True)
    finally:
        for engine in ctx.engines.values():
            engine.stop()
    print(f"results: {ctx.jsonl}")
    return 1 if failed else 0


def cmd_holdout(args) -> int:
    """Independent holdout check (campaign gate f): the frozen real-app
    fixture runs once per engine — never tuned against, never part of
    the scored baseline."""
    ctx = RunContext(f"holdout-{datetime.now().strftime('%Y%m%dT%H%M%S')}-"
                     f"{random.randint(0, 0xffff):04x}")
    kw = {"ops": args.ops, "repos": args.repos, "issues": args.issues,
          "clones": args.clones, "seed": args.seed}
    failed = False
    try:
        for eng in [e.strip() for e in args.engines.split(",") if e.strip()]:
            rec = run_one(ctx, eng, "HOLDOUT", "warm", **kw)
            m = rec["metrics"]
            failed = failed or not rec["correctness"]["ok"] or bool(
                rec.get("validation_errors"))
            print(f"{eng}: ok={rec['correctness']['ok']} "
                  f"health={m.get('time_to_health_s')}s "
                  f"seed={m.get('seed_s')}s "
                  f"ops/s={m.get('ops_per_s')} "
                  f"clone={m.get('clone_s')}s "
                  f"errors={rec['validation_errors']}", flush=True)
    finally:
        for engine in ctx.engines.values():
            engine.stop()
    print(f"results: {ctx.jsonl}")
    return 1 if failed else 0


def cmd_noop(args) -> int:
    args.a = args.b = args.engine
    args.pairs = args.pairs
    args.randomize = False
    args.noise_control = True
    args.case = args.case or "W1"
    args.state = args.state or "warm"
    args.cold = False
    args.seed = args.seed or 1
    if args.case == "W2":
        args.concurrency = args.concurrency or 8
        args.duration = args.duration or 15.0
        args.write_ratio = args.write_ratio if args.write_ratio is not None else 0.3
        args.seed = args.seed or 1
    return cmd_baseline(args)


def bootstrap_ci(vals: list[float], iters: int = 2000,
                 seed: int = 7) -> tuple[float, float]:
    from reporting import bootstrap_ci as paired_median_ci
    return paired_median_ci(vals, iters, seed)


def cmd_report(args) -> int:
    # The standalone module also works without Docker, VM assets or macOS:
    # python3 bench/native/reporting.py --match '<exact-run-id>'
    from reporting import (analyze, analyze_noise, invalid_noise_report,
                           invalid_report, load_records, render_markdown,
                           render_noise_markdown)
    files = sorted(RESULTS.glob(f"{args.match or '*'}/trials.jsonl"))
    records, issues = load_records(files)
    if not records and not issues:
        print("no trial records found")
        return 1
    if getattr(args, "noise", False):
        report = analyze_noise(records, issues)
        print(render_noise_markdown(report), end="")
        return int(invalid_noise_report(report))
    report = analyze(records, issues)
    print(render_markdown(report), end="")
    return int(invalid_report(report))


def run_component_check(component: str, timeout: int = CHECK_TIMEOUT_SECONDS,
                        run=None) -> int:
    """Run a bounded, exact native unittest selection without engine setup."""
    if run is None:
        run = subprocess.run
    modules = CHECK_COMPONENTS[component]
    command = [sys.executable, "-m", "unittest", "-v", *modules]
    print("check selection: " + ", ".join(modules), flush=True)
    try:
        result = run(command, cwd=BENCH, text=True, capture_output=True,
                     timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        print(f"component check timed out after {timeout}s: {exc.cmd}",
              file=sys.stderr)
        if exc.stdout:
            print(exc.stdout, file=sys.stderr)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        return 1
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    summary = re.search(r"^Ran (\d+) tests? in ", result.stderr + result.stdout,
                        flags=re.MULTILINE)
    if summary is None:
        print("component check did not produce a unittest completion summary",
              file=sys.stderr)
        return 1
    count = int(summary.group(1))
    if count == 0:
        print("component check selected zero tests", file=sys.stderr)
        return 1
    skipped = re.search(r"\bskipped=(\d+)\b", result.stderr + result.stdout)
    if skipped and int(skipped.group(1)):
        print(f"component check has {skipped.group(1)} required skipped test(s)",
              file=sys.stderr)
        return 1
    if result.returncode:
        print(f"component check failed with exit code {result.returncode}",
              file=sys.stderr)
        return 1
    print(f"component check passed: {count} tests, 0 skips")
    return 0


def main() -> int:
    global DOCKER
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("preflight")
    sub.add_parser("validate-manifest", help="offline contract syntax/hash check; no Docker required")

    p = sub.add_parser("prepare")
    p.add_argument("--engines", default="ctrs,orbstack")

    p = sub.add_parser("run")
    p.add_argument("--case", required=True, choices=["W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8", "W9", "W10", "W11", "W12", "W12-watch", "W13"])
    p.add_argument("--engine", required=True, choices=["ctrs", "orbstack"])
    p.add_argument("--image-ref", help="W9: preinstalled pinned common Marked digest reference")
    p.add_argument("--state", default="warm", choices=["warm", "cold"])
    p.add_argument("--cold", action="store_true",
                   help="ctrs only: fresh CTRS_DATA_DIR (engine-cold)")
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--duration", type=float, default=20.0)
    p.add_argument("--operations", type=int, default=None, help="W2 fixed total useful operations; omitted = saturation")
    p.add_argument("--request-rate", type=float, default=None, help="W2 fixed offered requests per second; requires --operations")
    p.add_argument("--write-ratio", type=float, default=0.3)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--under-load", action="store_true",
                   help="W8: serve W2-style load while images pull")
    p.add_argument("--driver", default="default",
                   choices=["default", "dc"],
                   help="W6/W7: dc pins matching BuildKit images in "
                        "isolated per-engine builders (attribution "
                        "control for builder topology)")

    p = sub.add_parser("baseline")
    p.add_argument("--case", required=True, choices=["W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8", "W9", "W10", "W11", "W12", "W12-watch", "W13"])
    p.add_argument("--a", required=True, choices=["ctrs", "orbstack"])
    p.add_argument("--b", required=True, choices=["ctrs", "orbstack"])
    p.add_argument("--image-ref", help="W9: preinstalled pinned common Marked digest reference")
    p.add_argument("--pairs", type=int, default=3)
    p.add_argument("--state", default="warm", choices=["warm", "cold"])
    p.add_argument("--cold", action="store_true")
    p.add_argument("--randomize", action="store_true")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--duration", type=float, default=20.0)
    p.add_argument("--operations", type=int, default=None, help="W2 fixed total useful operations; omitted = saturation")
    p.add_argument("--request-rate", type=float, default=None, help="W2 fixed offered requests per second; requires --operations")
    p.add_argument("--write-ratio", type=float, default=0.3)
    p.add_argument("--resource-lane", choices=RESOURCE_LANES, default="matched",
                   help="matched: ctrs gets OrbStack's vCPUs/memory; installed-default: "
                        "ctrs product defaults, no CTRS_CPUS/CTRS_MEMORY_MIB")
    p.add_argument("--under-load", action="store_true",
                   help="W8: serve W2-style load while images pull")
    p.add_argument("--driver", default="default",
                   choices=["default", "dc"],
                   help="W6/W7: dc pins matching BuildKit images in "
                        "isolated per-engine builders")
    for command in ("run", "baseline"):
        sub.choices[command].add_argument("--client-location", choices=("host", "guest"),
                                         help="W2 client placement (default: published port from host)")
        sub.choices[command].add_argument("--build-cache", choices=("uncached", "warm"),
                                         help="W6 build-cache condition (default: uncached); warm primes the same context")
        sub.choices[command].add_argument("--interrupt-service", choices=("api", "db", "queue", "engine"),
                                         help="W10 target (default: api); engine requires a standalone ctrs run")
    p = sub.choices["baseline"]
    p.add_argument("--workspace-layout", choices=("full-bind", "bind-source-volume-deps", "all-volume"),
                   default="full-bind", help="W12 layout")
    p.add_argument("--watch-mount", choices=("bind", "volume"), default="bind", help="W12-watch mount")
    p.add_argument("--watch-edits", type=int, default=60, help="W12-watch edit events per trial (at least 60)")
    p.add_argument("--transfer-path", choices=("published-port", "container-to-container", "container-to-mac"),
                   default="published-port", help="W13 network path")
    p.add_argument("--direction", choices=("upload", "download"), default="upload", help="W13 direction")
    p.add_argument("--streams", type=int, choices=(1, 4), default=1, help="W13 parallel streams")
    p.add_argument("--size-bytes", type=int, default=1 << 30, help="W13 bytes per transfer")
    p.add_argument("--repeats", type=int, default=3, help="W13 transfers per trial")

    p = sub.add_parser("w8-baseline", description="Resource-matched resident W8 control using one derived artifact per pair. The owned ctrs daemon uses CTRS_IDLE_SECS=0; product defaults are unchanged.", epilog="Example: runner.py w8-baseline --layout /path/to/w8-portfolio-v5/layout --ctrs-binary /path/to/signed/ctrs --pairs 10")
    p.add_argument("--layout", type=Path, required=True, help="original pinned W8 v2 common OCI source layout")
    p.add_argument("--ctrs-binary", type=Path, required=True, help="signed candidate ctrs binary")
    p.add_argument("--pairs", type=int, default=10, help="number of pairs (1 to 100)")
    p.add_argument("--under-load", action="store_true", help="run fixed background application work during pulls")
    p.add_argument("--seed", type=int, default=1, help="integer incorporated into unique per-pair seeds")
    p.add_argument("--diagnostic", action="store_true", help="functional checks only; timings are invalid")
    p.add_argument("--orbstack-storage-file", type=Path, action="append", default=[],
                   help="diagnostic only: explicit backing file open by OrbStack; repeat for multiple files")

    p = sub.add_parser("w8-cancel", help="verify interrupted W8 delivery and retry on one engine")
    p.add_argument("--layout", type=Path, required=True, help="original pinned W8 v2 common OCI source layout")
    p.add_argument("--ctrs-binary", type=Path, required=True, help="signed candidate ctrs binary")
    p.add_argument("--engine", choices=("ctrs", "orbstack"), required=True, help="engine for this functional check")
    p.add_argument("--content", choices=("retained", "derived"), required=True,
                   help="reuse original layers except the interrupted layer, or derive every layer")

    p = sub.add_parser("noop")
    p.add_argument("--engine", default="ctrs", choices=["ctrs", "orbstack"])
    p.add_argument("--image-ref", help="W9: preinstalled pinned common Marked digest reference")
    p.add_argument("--case", default="W1", choices=["W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8", "W9", "W10", "W11"])
    p.add_argument("--pairs", type=int, default=2)
    p.add_argument("--state", default="warm")
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--duration", type=float, default=15.0)
    p.add_argument("--write-ratio", type=float, default=0.3)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--under-load", action="store_true")

    p = sub.add_parser("holdout")
    p.add_argument("--engines", default="ctrs,orbstack")
    p.add_argument("--ops", type=int, default=240)
    p.add_argument("--repos", type=int, default=8)
    p.add_argument("--issues", type=int, default=5)
    p.add_argument("--clones", type=int, default=4)
    p.add_argument("--seed", type=int, default=1)

    p = sub.add_parser("report")
    p.add_argument("--match", default="*",
                   help="only result dirs matching this glob, e.g. "
                        "base-2026* for frozen baselines")
    p.add_argument("--noise", action="store_true",
                   help="report same-engine A/B slot noise control from "
                        "noop runs; never cross-engine scores")

    p = sub.add_parser("check", help="bounded offline native tests for one component")
    p.add_argument("component", choices=tuple(CHECK_COMPONENTS),
                   help="component to check")
    p.add_argument("--timeout", type=int, default=CHECK_TIMEOUT_SECONDS,
                   help=f"whole check timeout in seconds (1 to 300; default {CHECK_TIMEOUT_SECONDS})")

    args = ap.parse_args()
    if getattr(args, "client_location", None) is not None and args.case != "W2":
        ap.error("--client-location requires W2")
    if getattr(args, "build_cache", None) is not None and args.case != "W6":
        ap.error("--build-cache requires W6")
    if getattr(args, "interrupt_service", None) is not None and args.case != "W10":
        ap.error("--interrupt-service requires W10")
    if getattr(args, "interrupt_service", None) == "engine" and (
            args.cmd != "run" or args.engine != "ctrs" or args.cold or args.state != "warm"):
        ap.error("engine interruption requires run --case W10 --engine ctrs with a warmed private stack")
    if getattr(args, "operations", None) is not None:
        if args.case != "W2" or args.operations <= 0:
            ap.error("--operations requires W2 and a positive value")
    if getattr(args, "request_rate", None) is not None:
        if args.case != "W2":
            ap.error("--request-rate requires W2")
        try:
            planned_span(args.operations, args.request_rate)
        except ValueError as exc:
            ap.error(str(exc))
    try:
        manifest = validate_manifest()
    except (OSError, ValueError, KeyError) as exc:
        ap.error(f"invalid benchmark manifest: {exc}")
    if args.cmd == "validate-manifest":
        print(json.dumps(manifest, indent=2))
        return 0
    if args.cmd == "check":
        if not 1 <= args.timeout <= 300:
            ap.error("--timeout must be between 1 and 300 seconds")
        return run_component_check(args.component, args.timeout)
    if args.cmd == "report":
        return cmd_report(args)
    if getattr(args, "case", None) == "W8" and args.cmd in ("run", "baseline", "noop"):
        ap.error("legacy W8 proxy is not scoreable; use w8-baseline --layout PATH --ctrs-binary PATH")
    if args.cmd in ("w8-baseline", "w8-cancel"):
        if args.cmd == "w8-baseline" and not 1 <= args.pairs <= 100:
            ap.error("--pairs must be between 1 and 100")
        if args.cmd == "w8-baseline" and args.orbstack_storage_file and not args.diagnostic:
            ap.error("--orbstack-storage-file requires --diagnostic")
        if os.uname().sysname != "Darwin" or os.uname().machine != "arm64":
            ap.error(f"{args.cmd} requires native ARM64 macOS")
        global CTRS_BIN
        CTRS_BIN = args.ctrs_binary.resolve()
        if not CTRS_BIN.is_file():
            ap.error("--ctrs-binary must name an existing signed binary")
        sys.modules["runner"] = sys.modules[__name__]
        import diagnostic_signals
        DOCKER = find_docker()
        RESULTS.mkdir(parents=True, exist_ok=True)
        diagnostic_signals.install_cleanup_signals()
        if args.cmd == "w8-cancel":
            import w8_cancel
            return w8_cancel.run_cancel(args)
        import w8_benchmark
        return w8_benchmark.run_batch(args)
    if getattr(args, 'case', None) == 'W9':
        try:
            ci_jobs.validate_image_ref(getattr(args, 'image_ref', None) or '')
        except ValueError as exc:
            ap.error('--image-ref: ' + str(exc))
    elif getattr(args, 'image_ref', None):
        ap.error('--image-ref applies only to W9')
    for name in ("duration", "pairs", "concurrency", "ops", "repos", "issues", "clones"):
        value = getattr(args, name, None)
        if value is not None and value <= 0:
            ap.error(f"--{name} must be positive")
    if hasattr(args, "write_ratio") and not 0 <= args.write_ratio <= 1:
        ap.error("--write-ratio must be between 0 and 1")
    if hasattr(args, "engines"):
        engines = [name.strip() for name in args.engines.split(",")]
        if (not engines or any(name not in ("ctrs", "orbstack") for name in engines)
                or len(set(engines)) != len(engines)):
            ap.error("--engines requires distinct ctrs and/or orbstack entries")
        args.engines = ",".join(engines)
    if getattr(args, "cold", False) or getattr(args, "state", "warm") == "cold":
        if (args.cmd != "run" or args.engine != "ctrs" or not args.cold
                or args.case == "W8"):
            ap.error("engine-cold is only supported by run --engine ctrs --cold "
                     "(except W8); a shared OrbStack cold comparison is unavailable")
        args.state = "cold"
    if args.cmd != "preflight" and os.uname().sysname != "Darwin":
        ap.error("runtime commands require macOS; use validate-manifest/report offline")
    DOCKER = find_docker()
    RESULTS.mkdir(parents=True, exist_ok=True)
    if args.cmd == "preflight":
        return cmd_preflight(args)
    if args.cmd == "prepare":
        return cmd_prepare(args)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "baseline":
        return cmd_baseline(args)
    if args.cmd == "noop":
        return cmd_noop(args)
    if args.cmd == "holdout":
        return cmd_holdout(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
