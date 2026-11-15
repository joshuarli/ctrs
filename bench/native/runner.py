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

SERVICE_IMAGES = ["postgres:17-alpine", "redis:7-alpine", "python:3.13-slim"]
W1_DIR = FIXTURES / "w1"
API_DOCKERFILE_DIR = W1_DIR / "api"
COMPOSE_FILE = W1_DIR / "compose.yaml"
LOAD_PY = FIXTURES / "w2" / "load.py"
W8_DIR = FIXTURES / "w8"
W7_DIR = FIXTURES / "w7"
W9_IMAGE = "python:3.13-slim"
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
POLL_INTERVAL_S = 0.25


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
        env = os.environ.copy()
        env["CTRS_DATA_DIR"] = str(self.dir / "data")
        env["CTRS_SOCKET"] = str(self.dir / "run" / "docker.sock")
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


def trial_w7(ctx, engine: Engine, state: str) -> dict:
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
                ["build", "--load", "-q", "-t", tag,
                 "-f", str(context / "Dockerfile"), str(context)],
                timeout=timeout, check=False)
            return round(time.monotonic() - tp, 3), cp.returncode == 0

        cp = engine.sh(["buildx", "prune", "-af"], timeout=300,
                       check=False)
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
            rec = trial_w7(ctx, engine, state)
        elif case_id == "W9":
            rec = trial_w9(ctx, engine, state)
        else:
            raise ValueError(f"case {case_id} not implemented")
        rec["pair_id"] = pair_id
        rec["order_index"] = order_index
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
    if args.case in ("W2", "W8"):
        kw = {"concurrency": args.concurrency, "duration": args.duration,
              "write_ratio": args.write_ratio, "seed": args.seed}
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
                if args.case in ("W2", "W8"):
                    kw = {"concurrency": args.concurrency,
                          "duration": args.duration,
                          "write_ratio": args.write_ratio,
                          "seed": args.seed + pair * 10 + idx}
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
    p.add_argument("--case", required=True, choices=["W1", "W2", "W7", "W8", "W9"])
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

    p = sub.add_parser("baseline")
    p.add_argument("--case", required=True, choices=["W1", "W2", "W7", "W8", "W9"])
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

    p = sub.add_parser("noop")
    p.add_argument("--engine", default="ctrs", choices=["ctrs", "orbstack"])
    p.add_argument("--case", default="W1", choices=["W1", "W2", "W7", "W8", "W9"])
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
