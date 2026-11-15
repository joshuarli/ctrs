#!/usr/bin/env python3
"""Native-workload benchmark runner for the ctrs performance campaign.

Drives real application fixtures (bench/native/fixtures) against two
engines — ctrs (fresh Virtualization.framework guest per data root) and
OrbStack (the pinned macOS competitor) — through the same docker CLI,
records one JSONL trial per run under .work/native-perf/, and never
touches user engine state: every resource is project-scoped and removed
after each trial.

Requires Python >= 3.11 (tomllib). See README.md.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import random
import re
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
W7_DIR = FIXTURES / "w7"
W9_IMAGE = "python:3.13-slim"
W3_IMAGE = "postgres:17-alpine"
W5_DIR = FIXTURES / "w5"
W6_IMAGE = "gcc:14.2.0-bookworm"
W6_DIR = FIXTURES / "w6"
# Attribution control (campaign Phase B.2): a docker-container BuildKit
# builder usable on *both* engines, so W6/W7 can separate engine runtime
# from builder topology. The image is ctrs's pinned buildkit digest so
# both sides run the same BuildKit version.
DC_BUILDER = "np-dc"
DC_BUILDER_IMAGE = ("moby/buildkit@sha256:"
                    "aa632b921ef07411d2cb77292cd34213d4f7b384001d6fceef1e1f25bf9752bb")
W4_IMAGE = "redis:7-alpine"
W4_JOBS = 200
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


DOCKER = find_docker()


def api_tag() -> str:
    h = hashlib.sha256()
    for name in ("Dockerfile", "app.py", "requirements.txt"):
        h.update((API_DOCKERFILE_DIR / name).read_bytes())
    return f"np1-{h.hexdigest()[:12]}"


API_TAG = api_tag()


def load_cases() -> dict:
    with open(CASES_FILE, "rb") as f:
        return tomllib.load(f)


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


def compose_down(engine: Engine, project: str) -> None:
    engine.compose(project, ["down", "-v", "--remove-orphans"], timeout=90)
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

        # Untimed: drop every local reference and the engine's content
        # store so each trial performs a real fetch+install, not a dedup
        # hit. OrbStack/containerd releases content on `image prune`;
        # ctrs keeps unreferenced layers until the next VM boot, so its
        # daemon is restarted (untimed) to reach the same cold store.
        for item in portfolio.values():
            for ref in {item["pull_ref"], item["tag_ref"],
                        item.get("local_ref", "")}:
                engine.sh(["rmi", "-f", ref], check=False, timeout=60)
        if engine.name == "orbstack":
            engine.sh(["image", "prune", "-f"], check=False, timeout=120)
        else:
            engine.stop()
            engine.ensure_up()

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
    """Create the shared docker-container BuildKit builder on this engine
    if absent (untimed setup). Both engines get the same pinned BuildKit
    image so `--driver dc` isolates builder topology from engine runtime."""
    cp = engine.sh(["buildx", "inspect", DC_BUILDER], timeout=30,
                   check=False)
    if cp.returncode == 0:
        return
    engine.sh(
        ["buildx", "create", "--name", DC_BUILDER,
         "--driver", "docker-container",
         "--driver-opt", f"image={DC_BUILDER_IMAGE}", "--bootstrap"],
        timeout=600)


def build_args(driver: str, extra: list[str]) -> list[str]:
    """`docker buildx build --load` argv; `driver="dc"` pins the shared
    docker-container builder on both engines."""
    args = ["buildx", "build", "--load", *extra]
    if driver == "dc":
        args += ["--builder", DC_BUILDER]
    return args


def trial_w7(ctx, engine: Engine, state: str,
             driver: str = "default") -> dict:
    """W7: native image build — empty/warm/incremental build-cache states
    on a multi-stage offline Dockerfile, then a run-time correctness
    probe. The build cache is pruned before the empty build; warm
    repeats the identical context; incremental bumps stamp/note.txt so
    only the last layer of stage 1 re-executes."""
    case_id = "W7"
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    tag = f"npw7/app:{ctx.run_id[-6:]}"
    checks = rec["correctness"]["checks"]
    try:
        engine.ensure_up()
        if driver == "dc":
            ensure_dc_builder(engine)
        rec["metrics"]["builder_driver"] = driver
        # Assemble the build context in the trial dir so the incremental
        # stamp never dirties the fixture tree.
        ctx_dir = trial_dir / "ctx"
        shutil.copytree(W7_DIR / "src", ctx_dir / "src")
        shutil.copytree(W7_DIR / "stamp", ctx_dir / "stamp")
        shutil.copy(W7_DIR / "Dockerfile", ctx_dir / "Dockerfile")

        def build_ctx(note: str) -> Path:
            (ctx_dir / "stamp" / "note.txt").write_text(note + "\n")
            return ctx_dir

        def build(context: Path, timeout: float = 900) -> tuple[float, bool]:
            tp = time.monotonic()
            cp = engine.sh(
                build_args(driver, ["-q", "-t", tag,
                                    "-f", str(context / "Dockerfile"),
                                    str(context)]),
                timeout=timeout, check=False)
            return round(time.monotonic() - tp, 3), cp.returncode == 0

        prune = ["buildx", "prune", "-af"]
        if driver == "dc":
            prune += ["--builder", DC_BUILDER]
        cp = engine.sh(prune, timeout=300, check=False)
        rec["metrics"]["prune_ok"] = cp.returncode == 0

        s, ok = build(build_ctx("incremental-0"))
        rec["metrics"]["build_empty_s"] = s
        checks["build_empty"] = ok

        s, ok = build(build_ctx("incremental-0"))
        rec["metrics"]["build_warm_s"] = s
        checks["build_warm"] = ok

        s, ok = build(build_ctx("incremental-1"))
        rec["metrics"]["build_incr_s"] = s
        checks["build_incr"] = ok

        run = engine.sh(["run", "--rm", tag, "cat", "/out/note.txt"],
                        timeout=60, check=False)
        note_ok = run.returncode == 0 and "incremental-1" in run.stdout
        checks["run_note"] = note_ok
        smoke = engine.sh(["run", "--rm", tag], timeout=60, check=False)
        checks["run_smoke"] = (smoke.returncode == 0
                               and "npw7-ok" in smoke.stdout)
        rec["correctness"]["ok"] = all(
            checks.get(k) for k in
            ("build_empty", "build_warm", "build_incr",
             "run_note", "run_smoke"))
        return rec
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(f"exception: {exc}")
        return rec


def trial_w6(ctx, engine: Engine, state: str,
             driver: str = "default") -> dict:
    """W6: compiled-app CI — one timed `docker build` of vendored zlib
    1.3.1 (configure -> make -j -> make check) on gcc:14.2.0-bookworm,
    then a run probe that sha256s the produced libz.a. The base image is
    pulled untimed in setup if absent (prepare also pulls it)."""
    case_id = "W6"
    trial_dir = ctx.trial_dir(engine.name, case_id, state)
    rec = ctx.new_record(engine, case_id, state, trial_dir)
    tag = f"npw6/zlib:{ctx.run_id[-6:]}"
    checks = rec["correctness"]["checks"]
    try:
        engine.ensure_up()
        if driver == "dc":
            ensure_dc_builder(engine)
        rec["metrics"]["builder_driver"] = driver
        cp = engine.sh(["image", "inspect", W6_IMAGE], timeout=30,
                       check=False)
        if cp.returncode != 0:
            engine.sh(["pull", W6_IMAGE], timeout=900)
        # Per-trial context: stamp.txt busts the layer cache so every
        # timed build is a real compile, not a cache hit.
        ctx_dir = trial_dir / "ctx"
        ctx_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(W6_DIR / "Dockerfile", ctx_dir / "Dockerfile")
        shutil.copy(W6_DIR / "zlib-1.3.1.tar.gz",
                    ctx_dir / "zlib-1.3.1.tar.gz")
        (ctx_dir / "stamp.txt").write_text(f"{ctx.run_id}\n")
        tp = time.monotonic()
        build = engine.sh(
            build_args(driver, ["-q", "-t", tag,
                                "-f", str(ctx_dir / "Dockerfile"),
                                str(ctx_dir)]),
            timeout=1800, check=False)
        rec["metrics"]["build_s"] = round(time.monotonic() - tp, 3)
        checks["build"] = build.returncode == 0
        if build.returncode != 0:
            rec["validation_errors"].append(
                f"build rc={build.returncode}: "
                f"{(build.stderr or build.stdout)[-400:]}")
        probe = engine.sh(
            ["run", "--rm", tag, "sha256sum", "/src/libz.a"],
            timeout=120, check=False)
        sha = probe.stdout.split()[0] if probe.returncode == 0 else ""
        rec["metrics"]["artifact_sha256"] = sha
        checks["artifact"] = (probe.returncode == 0
                              and len(sha) == 64)
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

            # Volume iteration: same test against the named volume.
            t0 = time.monotonic()
            cp = engine.sh(
                ["run", "--rm", "-v", f"{vol}:/repo:ro", "-w", "/repo",
                 W5_IMAGE, "python3", "run_tests.py"],
                timeout=120, check=False)
            vol_times.append(round(time.monotonic() - t0, 3))
            ok = (cp.returncode == 0 and "npw5-ok" in cp.stdout)
            checks[f"vol_iter_{i}"] = ok

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
    end (no unplanned death), aggregate error rate stays under 1%,
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

        total_req = total_err = total_writes = windows = churn_done = 0
        churn_fail = version_fail = 0
        wseed = seed
        while time.monotonic() < deadline:
            windows += 1
            wseed += 1
            out = trial_dir / f"load-{windows:03d}.json"
            load = subprocess.run(
                [sys.executable, str(LOAD_PY), "--url", base,
                 "--concurrency", str(concurrency),
                 "--duration", str(window),
                 "--write-ratio", str(write_ratio),
                 "--seed", str(wseed), "--out", str(out)],
                capture_output=True, text=True,
                timeout=window + 120)
            if out.exists():
                s = json.loads(out.read_text())
                total_req += s.get("requests", 0)
                total_err += s.get("errors", 0)
                total_writes += s.get("writes_ok", 0)
            else:
                total_err += 1
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

        rec["metrics"].update({
            "soak_seconds": round(time.monotonic() - t0, 3),
            "windows": windows,
            "requests": total_req,
            "errors": total_err,
            "error_pct": round(100.0 * total_err / max(total_req, 1), 4),
            "writes_ok": total_writes,
            "rps_mean": round(total_req / max(
                time.monotonic() - t0 - rec["metrics"]["setup_seconds"], 1), 1),
            "churn_jobs_completed": churn_done,
            "churn_failures": churn_fail,
            "engine_version_check_failures": version_fail,
        })
        status, stats = http_json(f"{base}/stats", timeout=10)
        expected_items = 500 + total_writes
        got_items = stats.get("items") if isinstance(stats, dict) else None
        checks["item_count"] = {
            "expected_min": expected_items, "got": got_items,
            "ok": got_items is not None and got_items >= expected_items}
        checks["engine_alive"] = version_fail == 0
        checks["error_rate"] = total_err <= max(1, total_req // 100)
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
            "engine_server_version": safe_version(engine),
            "state": state,
            "pair_id": None,
            "order_index": None,
            "host_id": self.host_id,
            "arch": self.arch,
            "git_sha": self.git_sha,
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
            **kw) -> dict:
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
        if case_id == "W1":
            rec = trial_w1(ctx, engine, state)
        elif case_id == "W2":
            rec = trial_w2(ctx, engine, state, **kw)
        elif case_id == "W8":
            rec = trial_w8(ctx, engine, state, **kw)
        elif case_id == "W7":
            rec = trial_w7(ctx, engine, state,
                           driver=kw.get("driver", "default"))
        elif case_id == "W9":
            rec = trial_w9(ctx, engine, state)
        elif case_id == "W4":
            rec = trial_w4(ctx, engine, state)
        elif case_id == "W6":
            rec = trial_w6(ctx, engine, state,
                           driver=kw.get("driver", "default"))
        elif case_id == "W3":
            rec = trial_w3(ctx, engine, state)
        elif case_id == "W5":
            rec = trial_w5(ctx, engine, state)
        elif case_id == "W10":
            rec = trial_w10(ctx, engine, state, **kw)
        elif case_id == "W11":
            rec = trial_w11(ctx, engine, state, **kw)
        else:
            raise ValueError(f"case {case_id} not implemented")
        rec["pair_id"] = pair_id
        rec["order_index"] = order_index
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
            ids = {}
            for img in SERVICE_IMAGES + [f"np-fixture-api:{API_TAG}"]:
                cp = engine.sh(
                    ["image", "inspect", "-f",
                     "{{.Id}} {{json .RepoDigests}}", img],
                    check=False, timeout=30)
                ids[img] = cp.stdout.strip() or cp.stderr.strip()
            summary[name] = {"images": ids}

            # W8: local registry + relocated-image portfolio. Builds load
            # locally (buildkit inside the VM cannot reach the host-side
            # registry), then the engine pushes and every local ref is
            # dropped again; each trial's store-cold reset makes the pull
            # a real fetch+install regardless.
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
    a, b = args.a, args.b
    rng = random.Random(args.seed)
    try:
        for pair in range(1, args.pairs + 1):
            order = [a, b] if (pair % 2 == 1) else [b, a]
            if args.randomize:
                order = [a, b]
                rng.shuffle(order)
            for idx, eng in enumerate(order):
                kw = {}
                if args.case in ("W2", "W8", "W10", "W11"):
                    kw = {"concurrency": args.concurrency,
                          "duration": args.duration,
                          "write_ratio": args.write_ratio,
                          "seed": args.seed + pair * 10 + idx}
                if args.case in ("W6", "W7"):
                    kw = {"driver": getattr(args, "driver", "default")}
                if args.case == "W8" and getattr(args, "under_load", False):
                    kw["under_load"] = True
                rec = run_one(ctx, eng, args.case, args.state,
                              cold=args.cold and eng == "ctrs",
                              pair_id=pair, order_index=idx, keep_warm=True,
                              **kw)
                ok = rec["correctness"]["ok"]
                wall = rec["metrics"].get("wall_seconds")
                print(f"pair {pair} {eng} {'OK' if ok else 'FAIL'} "
                      f"wall={wall}", flush=True)
    finally:
        for engine in ctx.engines.values():
            engine.stop()
    print(f"results: {ctx.jsonl}")
    return 0


def cmd_noop(args) -> int:
    args.a = args.b = args.engine
    args.pairs = args.pairs
    args.randomize = False
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
    if len(vals) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(vals)
    means = []
    for _ in range(iters):
        means.append(sum(vals[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


def cmd_report(args) -> int:
    files = sorted(RESULTS.glob("*/trials.jsonl"))
    records = []
    for fp in files:
        for line in fp.read_text().splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    if not records:
        print("no trial records found")
        return 1
    groups: dict[tuple, list[dict]] = {}
    for r in records:
        groups.setdefault((r["case"], r["state"]), []).append(r)

    print("# Native performance report (generated)\n")
    print("| case | state | engine | n | ok | wall_s median | "
          "p95_ms med | rps med | peak_rss_mb med | cpu_s med |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for (case, state), rs in sorted(groups.items()):
        for eng in sorted({r["engine"] for r in rs}):
            ers = [r for r in rs if r["engine"] == eng]
            ok = sum(1 for r in ers if r["correctness"]["ok"])
            walls = sorted(r["metrics"].get("wall_seconds", 0)
                           for r in ers if r["metrics"].get("wall_seconds"))
            p95 = sorted(r["metrics"]["p95_ms"] for r in ers
                         if r["metrics"].get("p95_ms") is not None)
            rps = sorted(r["metrics"]["rps"] for r in ers
                         if r["metrics"].get("rps") is not None)
            rss = sorted(r["resources"].get("peak_total_rss_kb", 0) / 1024
                         for r in ers)
            cpu = sorted(r["resources"].get("cpu_seconds_est", 0)
                         for r in ers)
            med = lambda xs: xs[len(xs) // 2] if xs else None
            print(f"| {case} | {state} | {eng} | {len(ers)} | {ok} | "
                  f"{med(walls)} | {med(p95)} | {med(rps)} | "
                  f"{med(rss)} | {med(cpu)} |")

    print("\n## Paired ratios (ctrs / orbstack; <1 favors ctrs)\n")
    for (case, state), rs in sorted(groups.items()):
        by_pair: dict[int, dict] = {}
        for r in rs:
            if r.get("pair_id") is None:
                continue
            by_pair.setdefault(r["pair_id"], {})[r["engine"]] = r
        for metric in ("wall_seconds", "p95_ms", "rps"):
            ratios = []
            for pair, d in sorted(by_pair.items()):
                if "ctrs" in d and "orbstack" in d:
                    a = d["ctrs"]["metrics"].get(metric)
                    b = d["orbstack"]["metrics"].get(metric)
                    if a and b:
                        ratios.append(a / b if metric != "rps" else b / a)
            if ratios:
                lo, hi = bootstrap_ci(ratios)
                med = sorted(ratios)[len(ratios) // 2]
                print(f"- {case}/{state} {metric}: median={med:.3f} "
                      f"CI95=[{lo:.3f},{hi:.3f}] n={len(ratios)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("preflight")

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
                   help="W6/W7: dc pins the shared docker-container "
                        "BuildKit builder on both engines (attribution "
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
                   help="W6/W7: dc pins the shared docker-container "
                        "BuildKit builder on both engines")

    p = sub.add_parser("noop")
    p.add_argument("--engine", default="ctrs", choices=["ctrs", "orbstack"])
    p.add_argument("--case", default="W1", choices=["W1", "W2", "W3", "W4", "W5", "W6", "W7", "W8", "W9", "W10", "W11"])
    p.add_argument("--pairs", type=int, default=2)
    p.add_argument("--state", default="warm")
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument("--duration", type=float, default=15.0)
    p.add_argument("--write-ratio", default=0.3)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--under-load", action="store_true")

    sub.add_parser("report")

    args = ap.parse_args()
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
    if args.cmd == "report":
        return cmd_report(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
