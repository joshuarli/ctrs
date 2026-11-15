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

import argparse
import base64
import concurrent.futures
import hashlib
import inspect
import json
import os
import random
import re
import shlex
import shutil
import signal
import statistics
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
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

MATCH_PATTERNS = {
    "ctrs": r"(^|/)ctrs$|ctrs-init|virtualization",
    "orbstack": r"orbstack|orb-|virtualization",
}

SERVICE_IMAGES = ["postgres:17-alpine", "redis:7-alpine", "python:3.13-slim",
                  "gcc:14.2.0-bookworm"]
W1_DIR = FIXTURES / "w1"
API_DOCKERFILE_DIR = W1_DIR / "api"
COMPOSE_FILE = W1_DIR / "compose.yaml"
LOAD_PY = FIXTURES / "w2" / "load.py"
W8_DIR = FIXTURES / "w8"
W9_IMAGE = "python:3.13-slim"
W3_IMAGE = "postgres:17-alpine"
W5_DIR = FIXTURES / "w5"
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
W4_IMAGE = "redis:7-alpine"
W4_JOBS = 200
# Holdout: a real third-party app never used for tuning — Gitea +
# Postgres. REST API seed/read workload plus git smart-HTTP clones over
# the published port. Executed once per engine at gates via the
# `holdout` subcommand; excluded from the scored W-matrix.
HOLDOUT_DIR = FIXTURES / "holdout"
HOLDOUT_COMPOSE = HOLDOUT_DIR / "compose.yaml"
HOLDOUT_IMAGE = "gitea/gitea:1.24.7"
HOLDOUT_USER = "npadmin"
HOLDOUT_PASSWORD = "npadmin-pass-123"
# One worker container: pop jobs until the list is empty, store
# md5(payload) under npw4:res:<payload>. `(nil)` ends the loop. $1 is
# the queue container's DNS name on the trial network.
W4_WORKER = (
    "while j=$(redis-cli -h \"$1\" RPOP npw4:jobs | head -1); do "
    "case \"$j\" in ''|'(nil)') break;; esac; "
    "h=$(printf %s \"$j\" | md5sum | cut -d' ' -f1); "
    "redis-cli -h \"$1\" SET \"npw4:res:$j\" \"$h\" >/dev/null; done"
)
W5_IMAGE = "python:3.13-slim"
W5_VOL = "npw5-repo"
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
    return (f"BEGIN; INSERT INTO npw3_events(k,v) VALUES ({i}, 'v{i}');"
            f" UPDATE npw3_meta SET n = n + 1 WHERE k = 'txs'; COMMIT;\n")
# ~0.6 s of CPU work inside the container, deterministic across engines
# (same image, same interpreter); argv[1] is the job marker.
W9_WORK = (
    "import sys,time,hashlib\n"
    "end=time.monotonic()+0.6\n"
    "h=hashlib.sha256()\n"
    "i=0\n"
    "while time.monotonic()<end:\n"
    "    h.update(str(i).encode());i+=1\n"
    "print('npw9-'+sys.argv[1]+'-ok-'+h.hexdigest()[:12])\n"
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


def guest_provenance() -> dict:
    """Hashes of the guest kernel/initramfs/data disk — the guest-side
    identity behind `ctrs_binary_sha256`. data.img is a 64 GiB sparse
    file (~27 s to hash), so results are cached by stat signature and
    only rehashed when the asset is rebuilt."""
    assets = {"guest_kernel_sha256": "Image",
              "guest_initramfs_sha256": "initramfs.cpio",
              "guest_data_sha256": "data.img"}
    cache_path = WORK / "guest-asset-hashes.json"
    try:
        cache = json.loads(cache_path.read_text())
    except Exception:
        cache = {}
    out, dirty = {}, False
    for key, name in assets.items():
        path = REPO / "guest" / "out" / name
        entry = cache.get(name)
        st = path.stat() if path.is_file() else None
        if (st is not None and isinstance(entry, dict)
                and entry.get("size") == st.st_size
                and entry.get("mtime_ns") == st.st_mtime_ns):
            out[key] = entry["sha256"]
            continue
        digest = sha256_file(path)
        out[key] = digest
        if st is not None:
            cache[name] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns,
                           "sha256": digest}
            dirty = True
    if dirty:
        try:
            cache_path.write_text(json.dumps(cache, indent=2))
        except OSError:
            pass
    return out


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

    def __init__(self, name: str, run_id: str, fresh_dir: Path | None = None):
        if name not in ("ctrs", "orbstack"):
            raise ValueError(f"unknown engine {name!r}")
        self.name = name
        self.run_id = run_id
        self.proc: subprocess.Popen | None = None
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
                timeout: float = 300) -> subprocess.CompletedProcess:
        return self.sh(
            ["compose", "-f", str(COMPOSE_FILE), "-p", project, *args],
            env_extra=env_extra, timeout=timeout, check=False)

    def server_version(self) -> str:
        cp = self.sh(["version", "--format", "{{.Server.Version}}"],
                     timeout=30)
        return cp.stdout.strip()

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
        res = orbstack_resources()
        if res is not None:
            env.setdefault("CTRS_CPUS", str(res[0]))
            env.setdefault("CTRS_MEMORY_MIB", str(res[1]))
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


def start_sampler(engine: Engine, trial_dir: Path):
    trace = trial_dir / "resources.jsonl"
    proc = subprocess.Popen(
        [sys.executable, str(COLLECT), "--match", MATCH_PATTERNS[engine.name],
         "--interval", "0.2", "--out", str(trace)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc, trace


def stop_sampler(proc: subprocess.Popen) -> None:
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def summarize_trace(trace: Path) -> dict:
    if not trace.exists():
        return {"samples": 0}
    peak_rss = 0
    cpu_seconds = 0.0
    prev_t = None
    samples = 0
    pids: dict[int, float] = {}
    for line in trace.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        samples += 1
        t = rec.get("t", 0.0)
        dt = (t - prev_t) if prev_t is not None else 0.0
        prev_t = t
        total_rss = 0
        for p in rec.get("procs", []):
            total_rss += p.get("rss_kb", 0)
            cpu_seconds += p.get("pcpu", 0.0) / 100.0 * dt
        peak_rss = max(peak_rss, total_rss)
    return {
        "samples": samples,
        "peak_total_rss_kb": peak_rss,
        "cpu_seconds_est": round(cpu_seconds, 2),
        "method": "ps pcpu/rss sum over matched comms; shared pages "
                  "double-counted, compressed memory not visible",
    }


def compose_down(engine: Engine, project: str,
                 compose_file: Path = COMPOSE_FILE) -> None:
    engine.sh(["compose", "-f", str(compose_file), "-p", project,
               "down", "-v", "--remove-orphans"], timeout=90, check=False)
    # Belt and braces: remove anything the project prefix left behind.
    for args in (["ps", "-aq", "--no-trunc", f"--filter", f"name={project}"],):
        cp = engine.sh(args, check=False, timeout=30)
        for cid in cp.stdout.split():
            engine.sh(["rm", "-f", cid], check=False, timeout=30)


def wait_health(base: str, deadline_s: float):
    """Poll /health; return (monotonic_time, body) or (None, last)."""
    end = time.monotonic() + deadline_s
    last = None
    while time.monotonic() < end:
        status, body = http_json(f"{base}/health", timeout=3)
        last = (status, body)
        if status == 200 and isinstance(body, dict) and body.get("ok"):
            return time.monotonic(), body
        time.sleep(POLL_INTERVAL_S)
    return None, last


def trial_w1(ctx, engine: Engine, state: str) -> dict:
    """W1: compose up -> verified healthy + DB/cache roundtrip; then a
    persistence check across a database restart."""
    case_id = "W1"
    proj = project_name(ctx.run_id, engine.name, case_id)
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    cenv = {"NP_API_PORT": str(port), "NP_API_TAG": API_TAG}
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    trial_dir.mkdir(parents=True, exist_ok=True)
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    sampler = trace = None
    t0 = time.monotonic()
    try:
        engine.ensure_up()
        compose_down(engine, proj)
        sampler, trace = start_sampler(engine, trial_dir)
        up = engine.compose(proj, ["up", "-d"], env_extra=cenv, timeout=300)
        rec["validation_errors"].append(
            f"compose up rc={up.returncode}: {(up.stderr or up.stdout)[-300:]}"
            if up.returncode != 0 else "")
        rec["validation_errors"] = [e for e in rec["validation_errors"] if e]
        if up.returncode != 0:
            rec["correctness"]["ok"] = False
            return rec

        t_health, health_body = wait_health(base, HEALTH_DEADLINE_S)
        if t_health is None:
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append(
                f"health deadline; last={health_body}")
            return rec
        rec["metrics"]["time_to_health_s"] = round(t_health - t0, 3)

        status, rt = http_json(f"{base}/roundtrip", timeout=10)
        ok_rt = (status == 200 and isinstance(rt, dict) and rt.get("ok")
                 and isinstance(rt.get("db_row"), dict)
                 and rt["db_row"].get("name") == "item-1")
        rec["metrics"]["wall_seconds"] = round(time.monotonic() - t0, 3)
        rec["metrics"]["time_to_roundtrip_s"] = rec["metrics"]["wall_seconds"]
        rec["correctness"]["checks"]["roundtrip"] = ok_rt
        if not ok_rt:
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append(f"roundtrip bad: {rt}")
            return rec

        # Persistence: write a record, restart the db container, read back.
        key = f"keep-{ctx.run_id}-{engine.name}"
        _, wr = http_json_write(f"{base}/records",
                                {"key": key, "value": "persist-ok"})
        db_id = engine.compose(proj, ["ps", "-q", "db"], timeout=30
                               ).stdout.strip()
        persist_ok = False
        detail = {}
        if db_id:
            engine.sh(["restart", db_id], timeout=120)
            t_ready, _ = wait_health(base, HEALTH_DEADLINE_S)
            if t_ready is not None:
                st, got = http_json(f"{base}/records/{key}", timeout=10)
                persist_ok = (st == 200 and isinstance(got, dict)
                              and got.get("value") == "persist-ok"
                              and got.get("cache_match") is True)
                detail = {"status": st, "body": got}
        else:
            detail = {"error": "db container id not found"}
        rec["correctness"]["checks"]["persist_after_db_restart"] = persist_ok
        rec["correctness"]["checks"]["persist_detail"] = detail
        rec["correctness"]["ok"] = bool(
            rec["correctness"]["ok"] and persist_ok)
        return rec
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(f"exception: {exc}")
        return rec
    finally:
        rec["metrics"]["wall_seconds"] = round(time.monotonic() - t0, 3)
        compose_down(engine, proj)
        if sampler is not None:
            stop_sampler(sampler)
        rec["resources"].update(summarize_trace(trace) if trace else {})
        if trace:
            rec["resources"]["trace"] = str(trace.relative_to(WORK))


def trial_w2(ctx, engine: Engine, state: str, concurrency: int,
             duration: float, write_ratio: float, seed: int) -> dict:
    """W2: seeded stack up (untimed), then sustained mixed load timed."""
    case_id = "W2"
    proj = project_name(ctx.run_id, engine.name, case_id)
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    api = f"{base}"
    cenv = {"NP_API_PORT": str(port), "NP_API_TAG": API_TAG}
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    trial_dir.mkdir(parents=True, exist_ok=True)
    load_out = trial_dir / "load.json"
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    sampler = trace = None
    t0 = time.monotonic()
    try:
        engine.ensure_up()
        compose_down(engine, proj)
        sampler, trace = start_sampler(engine, trial_dir)
        up = engine.compose(proj, ["up", "-d"], env_extra=cenv, timeout=300)
        if up.returncode != 0:
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append(
                f"compose up rc={up.returncode}: {(up.stderr or up.stdout)[-300:]}")
            return rec
        t_ready, _ = wait_health(base, HEALTH_DEADLINE_S)
        if t_ready is None:
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append("stack never became healthy")
            return rec
        rec["metrics"]["setup_seconds"] = round(t_ready - t0, 3)

        load = subprocess.run(
            [sys.executable, str(LOAD_PY), "--url", api,
             "--concurrency", str(concurrency), "--duration", str(duration),
             "--write-ratio", str(write_ratio), "--seed", str(seed),
             "--out", str(load_out)],
            capture_output=True, text=True, timeout=duration + 120)
        if load_out.exists():
            summary = json.loads(load_out.read_text())
            rec["metrics"].update({
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

        status, stats = http_json(f"{base}/stats", timeout=10)
        expected_items = 500 + summary["writes_ok"]
        got_items = stats.get("items") if isinstance(stats, dict) else None
        count_ok = got_items == expected_items
        rec["correctness"]["checks"]["item_count"] = {
            "expected": expected_items, "got": got_items, "ok": count_ok}
        rec["correctness"]["checks"]["load_errors_zero"] = (
            summary["errors"] == 0)
        rec["correctness"]["ok"] = bool(count_ok and summary["errors"] == 0)
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
            rec["resources"]["trace"] = str(trace.relative_to(WORK))


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
            rec["resources"]["trace"] = str(trace.relative_to(WORK))


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
W7_APPS = {
    "hyperfine": {
        "builder_image": W6_RUST_IMAGE,
        "runtime_image": W7_DEBIAN_IMAGE,
        "source": W6_RUST_SOURCE,
        "dockerfile": W7_DIR / "hyperfine" / "Dockerfile",
        "probe": ["hyperfine", "--version"],
        "expect": "hyperfine 2.0.0",
    },
    "httpie": {
        "builder_image": W7_PYTHON_IMAGE,
        "runtime_image": W7_PYTHON_IMAGE,
        "source": W7_HTTPIE_SOURCE,
        "dockerfile": W7_DIR / "httpie" / "Dockerfile",
        "probe": ["http", "--version"],
        "expect": "3.2.4",
    },
}


def trial_w7(ctx, engine: Engine, state: str,
             driver: str = "default") -> dict:
    """W7: default buildx -> loaded runnable images for two real apps
    (hyperfine 2.0.0 Rust, httpie 3.2.4 Python). Per app: uncached (--no-cache)
    / warm (identical context) / incremental (one-file stamp bump)
    builds, then run probes for version output and the note marker.
    Base images pull untimed in setup; stores remain warm."""
    case_id = "W7"
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    checks = rec["correctness"]["checks"]
    try:
        engine.ensure_up()
        if driver == "dc":
            ensure_dc_builder(engine)
        rec["metrics"]["builder_driver"] = driver
        sources = {name: ensure_pinned_source(spec["source"], W7_DIR)
                   for name, spec in W7_APPS.items()}
        for spec in W7_APPS.values():
            for image in (spec["builder_image"], spec["runtime_image"]):
                cp = engine.sh(["image", "inspect", image], timeout=30,
                               check=False)
                if cp.returncode != 0:
                    engine.sh(["pull", image], timeout=900)

        rec["metrics"]["cache_mode"] = "no-cache-base-images-retained"
        rec["notes"].append("--no-cache bypasses layer reuse; "
                            "engine/content stores remain warm")
        for name, spec in W7_APPS.items():
            tag = f"npw7/{name}:{ctx.run_id[-6:]}"
            ctx_dir = trial_dir / f"ctx-{name}"
            ctx_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(spec["dockerfile"], ctx_dir / "Dockerfile")
            shutil.copy(sources[name],
                        ctx_dir / spec["source"]["file"])
            (ctx_dir / "stamp").mkdir(exist_ok=True)

            def build_ctx(note: str) -> Path:
                (ctx_dir / "stamp" / "note.txt").write_text(note + "\n")
                return ctx_dir

            def build(context: Path, uncached: bool = False,
                      timeout: float = 1800) -> tuple[float, bool]:
                tp = time.monotonic()
                cp = engine.sh(
                    build_args(engine, driver,
                               (["--no-cache"] if uncached else [])
                               + ["-q", "-t", tag, "-f",
                                  str(context / "Dockerfile"),
                                  str(context)]),
                    timeout=timeout, check=False)
                return round(time.monotonic() - tp, 3), cp.returncode == 0

            s, ok = build(build_ctx("incremental-0"), uncached=True)
            rec["metrics"][f"{name}_uncached_s"] = s
            checks[f"{name}_uncached"] = ok
            if not ok:
                rec["validation_errors"].append(
                    f"{name} uncached build failed")
                continue
            s, ok = build(build_ctx("incremental-0"))
            rec["metrics"][f"{name}_warm_s"] = s
            checks[f"{name}_warm"] = ok
            s, ok = build(build_ctx("incremental-1"))
            rec["metrics"][f"{name}_incr_s"] = s
            checks[f"{name}_incr"] = ok

            ver = engine.sh(["run", "--rm", tag, *spec["probe"]],
                            timeout=60, check=False)
            checks[f"{name}_version"] = (ver.returncode == 0
                                         and spec["expect"] in ver.stdout)
            note = engine.sh(["run", "--rm", tag, "cat", "/out/note.txt"],
                             timeout=60, check=False)
            checks[f"{name}_note"] = (note.returncode == 0
                                      and "incremental-1" in note.stdout)
        rec["correctness"]["ok"] = all(checks.values())
        return rec
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(f"exception: {exc}")
        return rec


def trial_w6(ctx, engine: Engine, state: str,
             driver: str = "default") -> dict:
    """W6: compiled-app CI — two timed `docker build`s per trial on
    pinned upstream sources: hyperfine 2.0.0 (Rust: cargo build
    --release --locked + cargo test on rust:1.100.0-bookworm) and zlib
    1.3.1 (C: configure -> make -j -> make check on
    gcc:14.2.0-bookworm). Each build ends with a run probe that sha256s
    the produced binary/lib. Base images are pulled untimed in setup if
    absent (prepare also pulls them)."""
    case_id = "W6"
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    tag_zlib = f"npw6/zlib:{ctx.run_id[-6:]}"
    tag_rust = f"npw6/hyperfine:{ctx.run_id[-6:]}"
    checks = rec["correctness"]["checks"]
    try:
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

        def build_one(name: str, dockerfile: Path,
                      sources: list[tuple[Path, str]],
                      tag: str, probe: list[str],
                      metric: str, timeout: float = 1800) -> None:
            # Per-trial context: stamp.txt busts the layer cache so every
            # timed build is a real compile, not a cache hit.
            ctx_dir = trial_dir / f"ctx-{name}"
            ctx_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(dockerfile, ctx_dir / "Dockerfile")
            for src, fname in sources:
                shutil.copy(src, ctx_dir / fname)
            (ctx_dir / "stamp.txt").write_text(f"{ctx.workload_id}\n")
            tp = time.monotonic()
            build = engine.sh(
                build_args(engine, driver, ["--no-cache", "-q", "-t", tag,
                                            "-f", str(ctx_dir / "Dockerfile"),
                                            str(ctx_dir)]),
                timeout=timeout, check=False)
            rec["metrics"][metric] = round(time.monotonic() - tp, 3)
            checks[f"build_{name}"] = build.returncode == 0
            if build.returncode != 0:
                rec["validation_errors"].append(
                    f"{name} build rc={build.returncode}: "
                    f"{(build.stderr or build.stdout)[-400:]}")
                return
            run = engine.sh(["run", "--rm", tag, *probe],
                            timeout=120, check=False)
            out = run.stdout.strip()
            sha = out.split()[0] if run.returncode == 0 else ""
            rec["metrics"][f"artifact_{name}_sha256"] = sha
            checks[f"artifact_{name}"] = (
                run.returncode == 0
                and re.fullmatch(r"[0-9a-f]{64}", sha) is not None)

        rec["metrics"]["cache_mode"] = "no-cache-base-images-retained"
        build_one(
            "rust", W6_DIR / "rust" / "Dockerfile",
            [(rust_src, W6_RUST_SOURCE["file"])],
            tag_rust,
            ["sha256sum", "/src/target/release/hyperfine"], "build_rust_s")
        build_one(
            "zlib", W6_DIR / "Dockerfile",
            [(zlib_src, W6_ZLIB_SOURCE["file"])],
            tag_zlib,
            ["sha256sum", "/src/libz.a"], "build_zlib_s")
        rec["correctness"]["ok"] = all(checks.values())
        return rec
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(f"exception: {exc}")
        return rec


def trial_w9(ctx, engine: Engine, state: str,
             jobs: tuple = (1, 4, 8, 16)) -> dict:
    """W9: parallel container churn — J concurrent `docker run` jobs, each
    doing ~0.6 s of CPU work in python:3.13-slim and printing a marker.
    Wall time per job count is the metric; every marker must appear."""
    case_id = "W9"
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    checks = rec["correctness"]["checks"]
    try:
        engine.ensure_up()
        all_ok = True
        for j in jobs:
            t0 = time.monotonic()
            with concurrent.futures.ThreadPoolExecutor(max_workers=j) as ex:
                futs = [
                    ex.submit(engine.sh,
                             ["run", "--rm", W9_IMAGE, "python3", "-c",
                              W9_WORK, str(i)],
                             timeout=180, check=False)
                    for i in range(j)
                ]
                outs = [f.result() for f in futs]
            wall = round(time.monotonic() - t0, 3)
            rec["metrics"][f"jobs_{j}_s"] = wall
            ok = all(
                cp.returncode == 0
                and f"npw9-{i}-ok-" in cp.stdout
                for i, cp in enumerate(outs))
            checks[f"jobs_{j}"] = ok
            all_ok = all_ok and ok
        rec["correctness"]["ok"] = all_ok
        return rec
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(f"exception: {exc}")
        return rec


def trial_w4(ctx, engine: Engine, state: str,
             workers: tuple = (1, 4, 16)) -> dict:
    """W4: worker queue — N deterministic jobs pushed onto a Redis list in
    a dedicated container on a private bridge network; W worker containers
    drain it with RPOP and store md5(payload) per job. Drain wall time per
    worker count; afterwards every result key must exist and a
    deterministic sample must match the runner-computed digest."""
    case_id = "W4"
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    checks = rec["correctness"]["checks"]
    proj = project_name(ctx.run_id, engine.name, case_id)
    net = f"npw4-{''.join(c if c.isalnum() else '-' for c in ctx.run_id)}-{engine.name}"
    q = f"{proj}-q"
    jobs = [f"job-{i:04d}-npw4" for i in range(W4_JOBS)]

    def redis(*args: str, timeout: float = 60) -> subprocess.CompletedProcess:
        return engine.sh(["exec", q, "redis-cli", *args],
                         timeout=timeout, check=False)

    try:
        engine.ensure_up()
        engine.sh(["network", "create", net], timeout=60)
        engine.sh(["run", "-d", "--name", q, "--network", net,
                   W4_IMAGE, "redis-server", "--save", "",
                   "--appendonly", "no"], timeout=120)
        deadline = time.monotonic() + 60
        while True:
            cp = redis("ping", timeout=15)
            if cp.returncode == 0 and "PONG" in cp.stdout:
                break
            if time.monotonic() > deadline:
                raise TimeoutError("redis queue did not become ready")
            time.sleep(0.5)
        all_ok = True
        for w in workers:
            redis("FLUSHALL")
            cp = redis("RPUSH", "npw4:jobs", *jobs, timeout=120)
            if cp.returncode != 0:
                rec["validation_errors"].append(
                    f"RPUSH rc={cp.returncode}: {(cp.stderr or cp.stdout)[-200:]}")
                checks[f"workers_{w}"] = False
                all_ok = False
                continue
            t0 = time.monotonic()
            with concurrent.futures.ThreadPoolExecutor(max_workers=w) as ex:
                futs = [
                    ex.submit(engine.sh,
                              ["run", "--rm", "--network", net,
                               W4_IMAGE, "sh", "-c", W4_WORKER,
                               "worker", q],
                              timeout=300, check=False)
                    for _ in range(w)
                ]
                outs = [f.result() for f in futs]
            wall = round(time.monotonic() - t0, 3)
            rec["metrics"][f"workers_{w}_s"] = wall

            nres = redis("--scan", "--pattern", "npw4:res:*")
            got = len([l for l in nres.stdout.splitlines() if l.strip()])
            sample = [jobs[i] for i in
                      range(0, W4_JOBS, max(1, W4_JOBS // 16))][:16]
            want = {j: hashlib.md5(j.encode()).hexdigest() for j in sample}
            mget = redis("MGET", *[f"npw4:res:{j}" for j in sample])
            vals = mget.stdout.splitlines()
            bad = [j for j, v in zip(sample, vals) if v.strip() != want[j]]
            ok = (all(cp.returncode == 0 for cp in outs)
                  and got == W4_JOBS and not bad)
            checks[f"workers_{w}"] = ok
            if not ok:
                rec["validation_errors"].append(
                    f"workers_{w}: rc={[c.returncode for c in outs]} "
                    f"results={got}/{W4_JOBS} bad_md5={bad[:3]}")
            all_ok = all_ok and ok
        rec["metrics"]["jobs"] = W4_JOBS
        rec["correctness"]["ok"] = all_ok
        return rec
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(f"exception: {exc}")
        return rec
    finally:
        engine.sh(["rm", "-f", q], check=False, timeout=60)
        engine.sh(["network", "rm", net], check=False, timeout=60)


def trial_w3(ctx, engine: Engine, state: str) -> dict:
    """W3: persistent transactional Postgres — real migrations, a
    deterministic 300-transaction mix, CHECKPOINT, `docker restart`,
    then exact row-count verification on the persisted volume."""
    case_id = "W3"
    proj = project_name(ctx.run_id, engine.name, case_id)
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    checks = rec["correctness"]["checks"]
    name = f"{proj}-db"
    vol = f"{proj}-pgdata"

    def psql(sql_file: str, timeout: float = 300) -> tuple[float, bool]:
        tp = time.monotonic()
        cp = engine.sh(
            ["exec", name, "sh", "-c",
             f"psql -U postgres -d postgres -f {sql_file} >/dev/null"],
            timeout=timeout, check=False)
        s = round(time.monotonic() - tp, 3)
        if cp.returncode != 0:
            rec["validation_errors"].append(
                f"psql {sql_file} rc={cp.returncode}: "
                f"{(cp.stderr or cp.stdout)[-300:]}")
        return s, cp.returncode == 0

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

    try:
        engine.ensure_up()
        engine.sh(["rm", "-f", name], check=False, timeout=30)
        engine.sh(["volume", "rm", "-f", vol], check=False, timeout=30)

        t0 = time.monotonic()
        run = engine.sh(
            ["run", "-d", "--name", name,
             "-e", f"POSTGRES_PASSWORD={W3_PASSWORD}",
             "-v", f"{vol}:/var/lib/postgresql/data", W3_IMAGE],
            timeout=120, check=False)
        checks["db_start"] = run.returncode == 0
        ready = wait_ready() if checks["db_start"] else None
        rec["metrics"]["up_s"] = round(time.monotonic() - t0, 3)
        checks["db_ready"] = ready is not None
        if ready is None:
            raise RuntimeError("postgres never became ready")

        mig = trial_dir / "migrate.sql"
        mig.write_text(W3_SQL)
        tx = trial_dir / "txmix.sql"
        tx.write_text("".join(_w3_tx_sql(i) for i in range(W3_TXS))
                      + "SELECT 'done';\n")
        for f in (mig, tx):
            cp = engine.sh(["cp", str(f), f"{name}:/tmp/{f.name}"],
                           timeout=60, check=False)
            if cp.returncode != 0:
                rec["validation_errors"].append(
                    f"docker cp {f.name} rc={cp.returncode}: "
                    f"{(cp.stderr or cp.stdout)[-300:]}")

        s, ok = psql("/tmp/migrate.sql")
        rec["metrics"]["migrate_s"] = s
        checks["migrate"] = ok

        s, ok = psql("/tmp/txmix.sql", timeout=600)
        rec["metrics"]["txmix_s"] = s
        rec["metrics"]["tx_tps"] = round(W3_TXS / s, 1) if s else None
        checks["txmix"] = ok

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
            ["exec", name, "psql", "-U", "postgres", "-d", "postgres",
             "-tA", "-c",
             "SELECT count(*), COALESCE(sum(k),0), "
             "(SELECT n FROM npw3_meta WHERE k='txs') FROM npw3_events"],
            timeout=60, check=False)
        expected_k = sum(range(W3_TXS))
        want = f"{W3_TXS}|{expected_k}|{W3_TXS}"
        checks["verify_rows"] = (out.returncode == 0
                                 and want in out.stdout.replace(" ", "|"))
        rec["correctness"]["ok"] = all(
            checks.get(k) for k in
            ("db_start", "db_ready", "migrate", "txmix", "checkpoint",
             "restart_ready", "verify_rows"))
        return rec
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(f"exception: {exc}")
        return rec
    finally:
        engine.sh(["rm", "-f", name], check=False, timeout=60)
        engine.sh(["volume", "rm", "-f", vol], check=False, timeout=60)


def trial_w5(ctx, engine: Engine, state: str,
             iters: int = 5) -> dict:
    """W5: monorepo edit-test loop — the same 60-module repo tested via
    `docker run` on (a) a host bind mount and (b) a named volume, kept
    as separate metrics per the campaign. Between bind iterations the
    host edits edited.txt; run_tests.py prints the marker so output
    proves host→guest write coherence through the mount."""
    case_id = "W5"
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    checks = rec["correctness"]["checks"]
    repo = W5_DIR / "repo"
    edited = repo / "edited.txt"
    orig = edited.read_text()
    vol = f"{W5_VOL}-{ctx.run_id[-6:]}"
    try:
        engine.ensure_up()
        engine.sh(["volume", "rm", "-f", vol], check=False, timeout=30)
        # Populate the volume once (untimed): copy the fixture repo in.
        cp = engine.sh(
            ["run", "--rm", "-v", f"{vol}:/dst",
             "-v", f"{repo}:/src:ro", W5_IMAGE, "sh", "-c",
             "cp -r /src/. /dst/"],
            timeout=120, check=False)
        checks["volume_seed"] = cp.returncode == 0
        if cp.returncode != 0:
            rec["validation_errors"].append(
                f"volume seed rc={cp.returncode}: "
                f"{(cp.stderr or cp.stdout).strip()[-300:]}")

        bind_times, vol_times = [], []
        for i in range(iters):
            # Bind iteration: host edit, then timed test run.
            edited.write_text(f"iter-{i}\n")
            t0 = time.monotonic()
            cp = engine.sh(
                ["run", "--rm", "-v", f"{repo}:/repo:ro", "-w", "/repo",
                 W5_IMAGE, "python3", "run_tests.py"],
                timeout=120, check=False)
            bind_times.append(round(time.monotonic() - t0, 3))
            ok = (cp.returncode == 0 and "npw5-ok" in cp.stdout
                  and f"iter-{i}" in cp.stdout)
            checks[f"bind_iter_{i}"] = ok
            if not ok:
                rec["validation_errors"].append(
                    f"bind iter {i} rc={cp.returncode}: "
                    f"{(cp.stderr or cp.stdout).strip()[-200:]}")

            # Volume iteration: same test against the named volume.
            t0 = time.monotonic()
            cp = engine.sh(
                ["run", "--rm", "-v", f"{vol}:/repo:ro", "-w", "/repo",
                 W5_IMAGE, "python3", "run_tests.py"],
                timeout=120, check=False)
            vol_times.append(round(time.monotonic() - t0, 3))
            ok = (cp.returncode == 0 and "npw5-ok" in cp.stdout)
            checks[f"vol_iter_{i}"] = ok
            if not ok:
                rec["validation_errors"].append(
                    f"vol iter {i} rc={cp.returncode}: "
                    f"{(cp.stderr or cp.stdout).strip()[-200:]}")

        rec["metrics"]["bind_iters_s"] = bind_times
        rec["metrics"]["volume_iters_s"] = vol_times
        rec["metrics"]["bind_median_s"] = round(
            statistics.median(bind_times), 3)
        rec["metrics"]["volume_median_s"] = round(
            statistics.median(vol_times), 3)
        rec["correctness"]["ok"] = all(
            v for k, v in checks.items() if k != "volume_seed"
        ) and checks.get("volume_seed", False)
        return rec
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(f"exception: {exc}")
        return rec
    finally:
        edited.write_text(orig)
        engine.sh(["volume", "rm", "-f", vol], check=False, timeout=60)


def trial_w10(ctx, engine: Engine, state: str,
              duration: float = 20.0, concurrency: int = 8,
              write_ratio: float = 0.3, seed: int = 1,
              kill_at: float = 6.0, down_for: float = 3.0) -> dict:
    """W10 (pilot): kill the API container mid-load, restart it, and
    verify the stack recovers with no lost committed writes. Metrics:
    recovery time, errors in the kill window, and post-restart health.
    Engine-level kill is out of scope for this cell (OrbStack's shared
    daemon makes an engine restart non-comparable)."""
    case_id = "W10"
    proj = project_name(ctx.run_id, engine.name, case_id)
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    cenv = {"NP_API_PORT": str(port), "NP_API_TAG": API_TAG}
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    trial_dir.mkdir(parents=True, exist_ok=True)
    load_out = trial_dir / "load.json"
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    sampler = trace = None
    load_proc = None
    t0 = time.monotonic()
    try:
        engine.ensure_up()
        compose_down(engine, proj)
        sampler, trace = start_sampler(engine, trial_dir)
        up = engine.compose(proj, ["up", "-d"], env_extra=cenv, timeout=300)
        if up.returncode != 0:
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append(
                f"compose up rc={up.returncode}: {(up.stderr or up.stdout)[-300:]}")
            return rec
        t_ready, _ = wait_health(base, HEALTH_DEADLINE_S)
        if t_ready is None:
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append("stack never became healthy")
            return rec
        rec["metrics"]["setup_seconds"] = round(time.monotonic() - t0, 3)

        load_t0 = time.monotonic()
        load_proc = subprocess.Popen(
            [sys.executable, str(LOAD_PY), "--url", base,
             "--concurrency", str(concurrency), "--duration", str(duration),
             "--write-ratio", str(write_ratio), "--seed", str(seed),
             "--out", str(load_out)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Let load reach steady state, then kill the API container.
        time.sleep(kill_at - (time.monotonic() - load_t0))
        api_id = engine.compose(proj, ["ps", "-q", "api"],
                                timeout=30).stdout.strip()
        checks = rec["correctness"]["checks"]
        checks["api_found"] = bool(api_id)
        tk = time.monotonic()
        kill = engine.sh(["kill", api_id], timeout=30, check=False) \
            if api_id else None
        checks["kill_rc"] = kill is not None and kill.returncode == 0
        rec["metrics"]["kill_at_load_s"] = round(
            time.monotonic() - load_t0, 3)

        time.sleep(down_for)
        ts = time.monotonic()
        start = engine.sh(["start", api_id], timeout=120, check=False) \
            if api_id else None
        checks["start_rc"] = start is not None and start.returncode == 0
        # Recovery = docker start returned -> /health ok again.
        t_rec, _ = wait_health(base, HEALTH_DEADLINE_S)
        rec["metrics"]["recovery_s"] = (
            round(t_rec - ts, 3) if t_rec is not None else None)
        checks["recovered"] = t_rec is not None

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
                "load_writes_ok": summary["writes_ok"],
                "load_p95_ms": summary["latency_ms"]["p95"],
                "load_p99_ms": summary["latency_ms"]["p99"],
            })
            # Errors clustered in the kill window are expected; what
            # matters is that the stack came back and no committed write
            # was lost (got >= 500 + acked writes).
            status, stats = http_json(f"{base}/stats", timeout=10)
            expected = 500 + summary["writes_ok"]
            got = stats.get("items") if isinstance(stats, dict) else None
            rec["metrics"]["items_expected_min"] = expected
            rec["metrics"]["items_got"] = got
            checks["no_lost_writes"] = (
                isinstance(got, int) and got >= expected)
        rec["correctness"]["ok"] = all(
            checks.get(k) for k in
            ("api_found", "kill_rc", "start_rc", "recovered",
             "no_lost_writes"))
        return rec
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(f"exception: {exc}")
        return rec
    finally:
        if load_proc is not None and load_proc.poll() is None:
            load_proc.kill()
            load_proc.wait(timeout=10)
        compose_down(engine, proj)
        if sampler is not None:
            stop_sampler(sampler)
        rec["resources"].update(summarize_trace(trace) if trace else {})
        if trace:
            rec["resources"]["trace"] = str(trace.relative_to(WORK))


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
                                  ["run", "--rm", W9_IMAGE, "python3",
                                   "-c", W9_WORK, str(i)],
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
            rec["resources"]["trace"] = str(trace.relative_to(WORK))


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
            rec["resources"]["trace"] = str(trace.relative_to(WORK))


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
            "ctrs_binary_sha256": sha256_file(CTRS_BIN),
            **guest_provenance(),
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
              "W10": trial_w10, "W11": trial_w11, "HOLDOUT": trial_holdout}
    if case_id not in trials:
        raise ValueError(f"case {case_id} not implemented")
    trial = trials[case_id]
    defaults = {name: parameter.default
                for name, parameter in inspect.signature(trial).parameters.items()
                if parameter.default is not inspect.Parameter.empty}
    ctx.workload_id = workload_id(ctx.run_id, case_id, pair_id, ctx._seq + 1)
    ctx.workload_params = {"cold": cold, **defaults, **kw}
    if cold:
        # Socket paths must stay under SUN_LEN (~104): keep cold engine
        # dirs short and outside the deep results tree.
        short = f"{engine_name}-cold-{ctx.run_id[-6:]}-{time.time_ns() % 100000:05d}"
        engine = Engine(engine_name, ctx.run_id,
                        fresh_dir=WORK / "engines" / short)
        stop = True
    else:
        # Warm trials share one daemon/VM per engine for the whole batch so
        # "warm" means hot engine on both sides (OrbStack's daemon is
        # always hot; ctrs must not be restarted per trial).
        engine = ctx.engines.get(engine_name)
        if engine is None:
            engine = Engine(engine_name, ctx.run_id)
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


def cmd_prepare(args) -> int:
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
    PORTFOLIO_FILE.write_text(json.dumps(portfolio, indent=2) + "\n")
    print(f"wrote {out} and {PORTFOLIO_FILE}")
    return 0


def cmd_run(args) -> int:
    ctx = RunContext(f"run-{datetime.now().strftime('%Y%m%dT%H%M%S')}-"
                     f"{random.randint(0, 0xffff):04x}")
    kw = {}
    if args.case in ("W2", "W8", "W10", "W11"):
        kw = {"concurrency": args.concurrency, "duration": args.duration,
              "write_ratio": args.write_ratio, "seed": args.seed}
    if args.case in ("W6", "W7"):
        kw = {"driver": getattr(args, "driver", "default")}
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
                if args.case in ("W6", "W7"):
                    kw = {"driver": getattr(args, "driver", "default")}
                if args.case == "W8" and getattr(args, "under_load", False):
                    kw["under_load"] = True
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


def main() -> int:
    global DOCKER
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("preflight")
    sub.add_parser("validate-manifest", help="offline contract syntax/hash check; no Docker required")

    p = sub.add_parser("prepare")
    p.add_argument("--engines", default="ctrs,orbstack")

    p = sub.add_parser("run")
    p.add_argument("--case", required=True, choices=["W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8", "W9", "W10", "W11"])
    p.add_argument("--engine", required=True, choices=["ctrs", "orbstack"])
    p.add_argument("--state", default="warm", choices=["warm", "cold"])
    p.add_argument("--cold", action="store_true",
                   help="ctrs only: fresh CTRS_DATA_DIR (engine-cold)")
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--duration", type=float, default=20.0)
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
    p.add_argument("--case", required=True, choices=["W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8", "W9", "W10", "W11"])
    p.add_argument("--a", required=True, choices=["ctrs", "orbstack"])
    p.add_argument("--b", required=True, choices=["ctrs", "orbstack"])
    p.add_argument("--pairs", type=int, default=3)
    p.add_argument("--state", default="warm", choices=["warm", "cold"])
    p.add_argument("--cold", action="store_true")
    p.add_argument("--randomize", action="store_true")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--duration", type=float, default=20.0)
    p.add_argument("--write-ratio", type=float, default=0.3)
    p.add_argument("--under-load", action="store_true",
                   help="W8: serve W2-style load while images pull")
    p.add_argument("--driver", default="default",
                   choices=["default", "dc"],
                   help="W6/W7: dc pins matching BuildKit images in "
                        "isolated per-engine builders")

    p = sub.add_parser("noop")
    p.add_argument("--engine", default="ctrs", choices=["ctrs", "orbstack"])
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

    args = ap.parse_args()
    try:
        manifest = validate_manifest()
    except (OSError, ValueError, KeyError) as exc:
        ap.error(f"invalid benchmark manifest: {exc}")
    if args.cmd == "validate-manifest":
        print(json.dumps(manifest, indent=2))
        return 0
    if args.cmd == "report":
        return cmd_report(args)
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
