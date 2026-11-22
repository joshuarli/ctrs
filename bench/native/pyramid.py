"""One entrypoint for the native benchmark suite: list, preflight, run by tier.

Tiers are ceilings: edit < change < scenario < full. Full workloads run only
when each one is named with --name; a tier ceiling never selects them.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from watch_loop import MIN_TAIL_EDITS

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
WORK = REPO / ".work"
RUNNER = HERE / "runner.py"
CTRS_BIN = REPO / "target/release/ctrs"
GUEST = REPO / "guest/out"
ORB_SOCKET = Path.home() / ".orbstack/run/docker.sock"
OUT = WORK / "native-perf/pyramid"
TIERS = ("edit", "change", "scenario", "full")
QUIET = {"load1": 4.0, "load5": 6.0}


@dataclass(frozen=True)
class Workload:
    name: str
    tier: str
    area: str
    purpose: str
    trial_seconds: float
    trials: int
    cost_basis: str
    requires: tuple[str, ...]
    argv: tuple[str, ...] = ()
    manual: str = ""
    report: bool = True
    cwd: Path = REPO
    design: str = "paired"

    @property
    def seconds(self) -> float:
        return self.trial_seconds * self.trials


def _baseline(*args: str, pairs: int) -> tuple[str, ...]:
    return ("baseline", "--a", "ctrs", "--b", "orbstack", "--pairs", str(pairs),
            "--resource-lane", "installed-default", *args)


ENGINES = ("macos-arm64", "docker-cli", "ctrs-binary", "guest-assets", "orbstack",
           "no-hold", "no-foreign-daemon", "free-disk")

# (name, area, purpose, runner args, observed seconds per trial or None, extra requirements)
CELLS: tuple[tuple[str, str, str, tuple[str, ...], float | None, tuple[str, ...]], ...] = (
    ("w1-stack", "api", "compose bring-up to verified health and restart persistence",
     ("--case", "W1"), 8, ("pinned-portfolio",)),
    ("w2-api", "api", "fixed-work API latency, throughput and CPU per request",
     ("--case", "W2", "--client-location", "host", "--operations", "50000",
      "--concurrency", "8"), 37, ("pinned-portfolio",)),
    *((f"w2-{path}-{mode}-c{clients}", "api",
       f"{path} API under {mode} at concurrency {clients}",
       ("--case", "W2", "--client-location", location, "--concurrency", str(clients),
        *(("--operations", "50000") if mode == "fixed-work" else ("--duration", "20"))),
       None, ("pinned-portfolio",))
      for path, location in (("published-port", "host"), ("container-to-container", "guest"))
      for mode in ("fixed-work", "saturation")
      for clients in (1, 4, 8, 16)
      if (location, mode, clients) != ("host", "fixed-work", 8)),
    *((f"w2-{path}-fixed-offered-rate", "api", f"{path} API at a fixed offered rate",
       ("--case", "W2", "--client-location", location, "--concurrency", "4",
        "--operations", "10000", "--request-rate", "500"), None, ("pinned-portfolio",))
      for path, location in (("published-port", "host"), ("container-to-container", "guest"))),
    ("w3-migration", "storage", "PostgreSQL migration, verified transactions, checkpoint and restart",
     ("--case", "W3"), None, ("pinned-portfolio",)),
    ("w3v4-storage", "storage", "pgbench fixed work on a named volume",
     ("--case", "W3-v4"), 14, ("pinned-portfolio",)),
    ("w4-pipeline", "pipeline", "HTTP ingest through Redis workers to exact outputs on volumes",
     ("--case", "W4"), 13, ("w4-image",)),
    ("w5-esbuild-watch", "watch", "persistent esbuild watch to exact CLI output after edits",
     ("--case", "W5"), 9, ("w5-source",)),
    ("w6-build", "build", "docker build of Rust and C projects with artifact hashes",
     ("--case", "W6"), 79, ()),
    ("w6-build-warm", "build", "primed-cache Docker builds of the W6 Rust and C projects",
     ("--case", "W6", "--build-cache", "warm"), None, ()),
    ("w7-buildx", "build", "buildx to loaded runnable images, uncached, warm and incremental",
     ("--case", "W7"), 72, ()),
    ("w9-jobs", "build", "16 fixed TypeScript build and test jobs at rising concurrency",
     ("--case", "W9"), 17, ("w9-image-ref",)),
    ("w10-recovery", "recovery", "interrupt the owned API and verify exact recovered work",
     ("--case", "W10"), 27, ("pinned-portfolio",)),
    ("w10-db-recovery", "recovery", "interrupt the owned database and verify exact recovered work",
     ("--case", "W10", "--interrupt-service", "db"), None, ("pinned-portfolio",)),
    ("w10-queue-recovery", "recovery", "interrupt the owned queue and verify backlog recovery",
     ("--case", "W10", "--interrupt-service", "queue", "--concurrency", "4"), None, ("w4-image",)),
    ("w12-full-bind", "workspace", "Kutt install, build, typecheck and tests on a bind mount",
     ("--case", "W12", "--workspace-layout", "full-bind"), 124, ("w12-inputs",)),
    ("w12-mixed", "workspace", "Kutt workspace with source bind-mounted and deps on a volume",
     ("--case", "W12", "--workspace-layout", "bind-source-volume-deps"), 124, ("w12-inputs",)),
    ("w12-all-volume", "workspace", "Kutt workspace wholly on a named volume",
     ("--case", "W12", "--workspace-layout", "all-volume"), None, ("w12-inputs",)),
    ("w12-watch-bind", "watch", "tsc --watch edit-to-rebuild latency on a bind mount",
     ("--case", "W12-watch", "--watch-mount", "bind"), 172, ("w12-inputs",)),
    ("w12-watch-volume", "watch", "tsc --watch edit-to-rebuild latency on a named volume",
     ("--case", "W12-watch", "--watch-mount", "volume"), None, ("w12-inputs",)),
    ("w13-pp-up", "transfer", "published-port upload goodput",
     ("--case", "W13", "--transfer-path", "published-port", "--direction", "upload"), 16, ("pinned-portfolio",)),
    ("w13-pp-down", "transfer", "published-port download goodput",
     ("--case", "W13", "--transfer-path", "published-port", "--direction", "download"), 21, ("pinned-portfolio",)),
    ("w13-c2m-up", "transfer", "container-to-Mac upload goodput",
     ("--case", "W13", "--transfer-path", "container-to-mac", "--direction", "upload"), 20, ("pinned-portfolio",)),
    ("w13-c2m-down", "transfer", "container-to-Mac download goodput",
     ("--case", "W13", "--transfer-path", "container-to-mac", "--direction", "download"), 22, ("pinned-portfolio",)),
    ("w13-c2c-up", "transfer", "container-to-container goodput",
     ("--case", "W13", "--transfer-path", "container-to-container", "--direction", "upload"), 17, ("pinned-portfolio",)),
    *((f"w13-{short}-{suffix}" + ("-s4" if streams == 4 else ""), "transfer",
       f"{path} {direction} goodput with {streams} streams",
       ("--case", "W13", "--transfer-path", path, "--direction", direction, "--streams", str(streams)),
       None, ("pinned-portfolio",))
      for short, path in (("pp", "published-port"), ("c2m", "container-to-mac"),
                          ("c2c", "container-to-container"))
      for suffix, direction in (("up", "upload"), ("down", "download"))
      for streams in (1, 4)
      if streams == 4 or (short, direction) == ("c2c", "download")),
    ("w13-overlap", "transfer", "API latency while a transfer runs",
     ("--case", "W13-overlap"), 110, ("pinned-portfolio",)),
    *((f"w14-{mode}", "connections", f"published-port connection lifecycle: {mode}",
       ("--case", "W14", "--lifecycle-mode", mode), seconds, ("pinned-portfolio",))
      for mode, seconds in (("fresh", 8), ("streaming", 8), ("cancel", 8), ("persistent", 8),
                            ("idle-resume", 34), ("reconnect", 8))),
)

UNMEASURED_TRIAL_SECONDS = 120.0

CPU_CANDIDATE = 9
MAX_PAIRS = 16
CPU_CANDIDATE_CELLS = ("w13-overlap", "w2-api", "w12-full-bind", "w6-build", "w14-idle-resume")


W9_REF = "$BENCH_W9_IMAGE_REF"


def resolved(argv: tuple[str, ...]) -> list[str]:
    return [w9_image_ref() or arg if arg == W9_REF else arg for arg in argv]


def w9_image_ref() -> str | None:
    """`BENCH_W9_IMAGE_REF`, else the OrbStack image whose repo digest is the
    pinned Marked manifest (the W8 portfolio installs it on both engines;
    the runner checks ctrs per trial)."""
    if os.environ.get("BENCH_W9_IMAGE_REF"):
        return os.environ["BENCH_W9_IMAGE_REF"]
    sys.path.insert(0, str(HERE))
    import ci_jobs
    docker = shutil.which("docker")
    if not docker or not ORB_SOCKET.exists():
        return None
    try:
        out = subprocess.run([docker, "-H", f"unix://{ORB_SOCKET}", "image", "ls", "--digests",
                              "--format", "{{.Repository}}@{{.Digest}}"],
                             capture_output=True, text=True, timeout=20).stdout
    except subprocess.TimeoutExpired:
        return None
    return next((line for line in out.split() if line.endswith("/np-v6/marked@" + ci_jobs.IMAGE_DIGEST)), None)


def registry(lane='macos-arm64') -> list[Workload]:
    if lane == 'linux-amd64':
        return [Workload(name, 'change', 'linux', 'native Linux pilot; never a macOS gate',
                         120, 2, 'estimated', ('python', 'docker-cli', 'linux-engines'),
                         argv=(sys.executable, str(RUNNER), '--lane', lane, 'baseline',
                               '--a', 'ctrs', '--b', 'dockerd', '--pairs', '1', '--case', case))
                for name, case in (('w2-api', 'W2'), ('w6-build', 'W6'),
                                   ('w7-buildx', 'W7'), ('w13-transfer', 'W13'))]
    items = [
        Workload("harness-tests", "edit", "harness", "the harness's parsing, pairing, gates and cleanup",
                 34, 1, "observed", ("python",),
                 argv=(sys.executable, "-m", "unittest", "discover", "-s", str(HERE), "-p", "test_*.py"),
                 report=False, cwd=HERE),
        Workload("manifest", "edit", "harness", "case registry syntax and recorded hashes",
                 2, 1, "estimated", ("python",),
                 argv=(sys.executable, str(RUNNER), "validate-manifest"), report=False),
    ]
    for name, area, purpose, args, seconds, extra in CELLS:
        basis = "observed" if seconds is not None else "estimated"
        per_trial = seconds or UNMEASURED_TRIAL_SECONDS
        image = ("--image-ref", W9_REF) \
            if "w9-image-ref" in extra else ()
        items.append(Workload(name, "change", area, purpose, per_trial, 2, basis, ENGINES + extra,
                              argv=(sys.executable, str(RUNNER), *_baseline(*args, *image, pairs=1))))
        cohort_args, cohort_seconds, cohort_basis = args, per_trial, basis
        if name == "w5-esbuild-watch":
            cohort_args = (*args, "--watch-edits", str(MIN_TAIL_EDITS))
            cohort_seconds, cohort_basis = 120, "estimated"
        items.append(Workload(f"{name}:cohort", "scenario", area, purpose + " (paired cohort)",
                              cohort_seconds, 20, cohort_basis, ENGINES + extra + ("quiet-host",),
                              argv=(sys.executable, str(RUNNER), *_baseline(*cohort_args, *image, pairs=10),
                                    "--pair-quiet-load", str(QUIET["load1"]), "--max-pairs", str(MAX_PAIRS))))
    for name, area, purpose, args, seconds, extra in CELLS:
        if name not in CPU_CANDIDATE_CELLS:
            continue
        items.append(Workload(
            f"{name}:cpus{CPU_CANDIDATE}", "scenario", area,
            f"{purpose}: ctrs at {CPU_CANDIDATE} vCPUs against its default, memory and assets fixed",
            seconds or UNMEASURED_TRIAL_SECONDS, 20, "observed" if seconds else "estimated",
            ENGINES + extra + ("quiet-host",),
            argv=(sys.executable, str(RUNNER), "baseline", "--a", "ctrs", "--b", "ctrs",
                  "--candidate-cpus", str(CPU_CANDIDATE), "--pairs", "10",
                  "--resource-lane", "installed-default", *args,
                  "--pair-quiet-load", str(QUIET["load1"]), "--max-pairs", str(MAX_PAIRS)),
            design="candidate"))
    items += [
        *(Workload(f"w6-build:memory{mib}", "scenario", "build",
                 f"W6 uncached builds with a {mib} MiB ctrs VM ceiling at fixed vCPUs",
                 79, 20, basis, ENGINES + ("quiet-host",),
                 argv=(sys.executable, str(RUNNER), "baseline", "--a", "ctrs", "--b", "ctrs",
                       "--resource-lane", "installed-default", "--case", "W6",
                       "--candidate-memory-mib", str(mib), "--pairs", "10",
                       "--pair-quiet-load", str(QUIET["load1"]), "--max-pairs", str(MAX_PAIRS)),
                 design="candidate")
          for mib, basis in ((6144, "observed"), (5120, "estimated"))),
        Workload("w12-full-bind-matched:cohort", "scenario", "workspace",
                 "Kutt workspace with ctrs given OrbStack's vCPUs and memory", 124, 20, "observed",
                 ENGINES + ("w12-inputs", "quiet-host"),
                 argv=(sys.executable, str(RUNNER), "baseline", "--a", "ctrs", "--b", "orbstack",
                       "--pairs", "10", "--resource-lane", "matched", "--case", "W12",
                       "--workspace-layout", "full-bind", "--pair-quiet-load", str(QUIET["load1"]), "--max-pairs", str(MAX_PAIRS))),
        *(Workload(f"w8-pull{load_name}{lane_name}{content_name}:cohort", "scenario", "pull",
                   f"pull and deploy {content} portfolio{load_text} with {lane_text}",
                   UNMEASURED_TRIAL_SECONDS, 20, "estimated", ENGINES + ("w8-layout", "quiet-host"),
                   argv=(sys.executable, str(RUNNER), "w8-baseline", "--layout",
                         str(WORK / "native-perf/inputs/w8-portfolio-v6/layout"),
                         "--ctrs-binary", str(CTRS_BIN), "--pairs", "10",
                         *content_flags, *lane_flags, *load_flags))
          for content, content_name, content_flags in (
              ("derived", "", ()), ("retained", "-retained", ("--content", "retained")))
          for lane_text, lane_name, lane_flags in (
              ("matched resources", "", ()),
              ("installed defaults", "-installed-default", ("--resource-lane", "installed-default")))
          for load_name, load_text, load_flags in (
              ("", "", ()), ("-under-load", " under concurrent API load", ("--under-load",)))),
        Workload("holdout", "full", "holdout", "Gitea + Postgres app never tuned against",
                 600, 2, "estimated", ENGINES,
                 argv=(sys.executable, str(RUNNER), "holdout", "--engines", "ctrs,orbstack"), report=False),
        Workload("w10-engine-recovery", "full", "recovery",
                 "verify recovery from interruption of an isolated ctrs engine",
                 UNMEASURED_TRIAL_SECONDS, 1, "estimated", ENGINES + ("w8-layout",),
                 argv=(sys.executable, str(RUNNER), "run", "--case", "W10", "--engine", "ctrs",
                       "--interrupt-service", "engine", "--duration", "90"), report=False),
        *(Workload(f"w8-cancel-{engine}-{content}", "full", "pull",
                   f"verify {content} pull cancellation and retry on {engine}",
                   UNMEASURED_TRIAL_SECONDS, 1, "estimated", ENGINES + ("w8-layout", "quiet-host"),
                   argv=(sys.executable, str(RUNNER), "w8-cancel", "--engine", engine, "--content", content,
                         "--resource-lane", "installed-default", "--layout",
                         str(WORK / "native-perf/inputs/w8-portfolio-v6/layout"), "--ctrs-binary", str(CTRS_BIN)),
                   report=False)
          for engine in ("ctrs", "orbstack") for content in ("retained", "derived")),
        Workload("w11-soak", "full", "soak", "12-hour sustained load and churn per engine",
                 43200, 2, "estimated", ENGINES,
                 manual="bench/native/diagnostics/durable-job.md (frozen inputs, fixed deadline, one engine per job)",
                 report=False),
    ]
    return items


def select(items: list[Workload], tier: str | None, names: list[str], areas: list[str],
           skips: list[str]) -> list[Workload]:
    known = {w.name for w in items}
    known_areas = {w.area for w in items}
    for name in names + skips:
        if name not in known:
            raise SystemExit(f"unknown workload {name!r}; see `pyramid.py list`")
    for area in areas:
        if area not in known_areas:
            raise SystemExit(f"unknown area {area!r}; areas: {', '.join(sorted(known_areas))}")
    if names:
        chosen = [w for w in items if w.name in names]
        if tier is not None:
            over = [w.name for w in chosen if TIERS.index(w.tier) > TIERS.index(tier)]
            if over:
                raise SystemExit(f"{', '.join(over)} exceed the --tier {tier} ceiling")
    else:
        if tier is None:
            raise SystemExit("choose a --tier ceiling or name workloads with --name")
        ceiling = min(TIERS.index(tier), TIERS.index("scenario"))
        chosen = [w for w in items if TIERS.index(w.tier) <= ceiling]
        if tier == "full":
            print("note: full workloads run only when named: "
                  + ", ".join(w.name for w in items if w.tier == "full"))
    if areas:
        chosen = [w for w in chosen if w.area in areas]
    chosen = [w for w in chosen if w.name not in skips]
    if not chosen:
        raise SystemExit("the selection matches no workload")
    return chosen


def _newest(paths) -> float:
    return max((p.stat().st_mtime for p in paths if p.is_file()), default=0.0)


def _foreign_daemons() -> list[str]:
    out = subprocess.run(["pgrep", "-fl", "^[^ ]*/ctrs daemon"], capture_output=True, text=True).stdout
    return [line for line in out.splitlines() if line.strip()]


def _orbstack_reachable() -> str | None:
    docker = shutil.which("docker")
    if not ORB_SOCKET.exists() or docker is None:
        return f"OrbStack socket {ORB_SOCKET} missing"
    try:
        cp = subprocess.run([docker, "-H", f"unix://{ORB_SOCKET}", "version", "--format", "{{.Server.Version}}"],
                            capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return "OrbStack did not answer `docker version` within 20 s"
    return None if cp.returncode == 0 else f"OrbStack `docker version` failed: {cp.stderr.strip()[:200]}"


def check_requirement(key: str) -> tuple[str, str]:
    """Return (status, message): status is ok, fail or warn."""
    if key == "python":
        return ("ok", sys.version.split()[0]) if sys.version_info >= (3, 11) else ("fail", "Python 3.11+ required")
    if key == 'linux-engines':
        if sys.platform != 'linux' or os.uname().machine != 'x86_64':
            return 'fail', 'linux-amd64 requires native x86_64 Linux'
        endpoints = [Path('/var/run/docker.sock'), Path(os.environ.get('CTRS_SOCKET', '/missing-ctrs-socket'))]
        return ('ok', '') if all(p.is_socket() for p in endpoints) else ('fail', 'start external ctrs and supply CTRS_SOCKET; dockerd must already be running')
    if key == "macos-arm64":
        u = os.uname()
        ok = u.sysname == "Darwin" and u.machine == "arm64"
        return ("ok", "") if ok else ("fail", f"needs macOS arm64, host is {u.sysname} {u.machine}")
    if key == "docker-cli":
        return ("ok", "") if shutil.which("docker") else ("fail", "docker CLI not on PATH; install it")
    if key == "ctrs-binary":
        if not CTRS_BIN.is_file():
            return "fail", f"{CTRS_BIN} missing; build with `CARGO_ENCODED_RUSTFLAGS=\"\" cargo xtask all`"
        newest = _newest((REPO / "crates").rglob("*.rs"))
        if newest > CTRS_BIN.stat().st_mtime:
            return "warn", f"{CTRS_BIN.name} is older than crates/ sources (stale or intentionally pinned)"
        return "ok", ""
    if key == "guest-assets":
        assets = [GUEST / n for n in ("Image", "initramfs.cpio", "data.img")]
        missing = [a.name for a in assets if not a.exists()]
        if missing:
            return "fail", f"guest/out missing {', '.join(missing)}; build with `cargo xtask all`"
        newest = _newest((REPO / "crates/ctrs-init").rglob("*.rs"))
        if newest > (GUEST / "initramfs.cpio").stat().st_mtime:
            return "warn", "initramfs.cpio is older than crates/ctrs-init sources (stale or intentionally pinned)"
        return "ok", ""
    if key == "orbstack":
        problem = _orbstack_reachable()
        return ("fail", problem + "; start OrbStack") if problem else ("ok", "")
    if key == "no-hold":
        holds = _holds()
        return ("fail", ", ".join(map(str, holds)) + ": a build owns the host; wait for it or remove the hold") \
            if holds else ("ok", "")
    if key == "no-foreign-daemon":
        found = _foreign_daemons()
        return ("fail", "a ctrs daemon is already running (" + "; ".join(found)[:200]
                + "); stop the one you own, never one you did not start") if found else ("ok", "")
    if key == "free-disk":
        WORK.mkdir(exist_ok=True)
        st = os.statvfs(WORK)
        gb = st.f_bavail * st.f_frsize / 1e9
        return ("ok", f"{gb:.0f} GB free") if gb >= 20 else ("fail", f"{gb:.0f} GB free under .work; need 20")
    if key == "pinned-portfolio":
        pin = HERE / "fixtures/w8-v6/portfolio.json"
        return ("ok", "pin contract present; runner checks installed images before pairing") if pin.is_file() \
            else ("fail", f"{pin} missing")
    if key == "w12-inputs":
        missing = [p.name for p in (WORK / "tmp/kutt.tar.gz", WORK / "tmp/w12-image.tar") if not p.is_file()]
        return ("fail", f".work/tmp missing {', '.join(missing)}; rebuild with `TMPDIR=$PWD/.work/tmp python3 bench/native/fixtures/w12/prepare.py`") if missing \
            else ("ok", "")
    if key == "w8-layout":
        layout = WORK / "native-perf/inputs/w8-portfolio-v6/layout"
        return ("ok", "") if layout.is_dir() else (
            "fail", f"{layout} missing; rebuild with `python3 bench/native/fixtures/w8-v6/prepare.py`")
    if key == "w4-image":
        docker = shutil.which("docker")
        found = docker and subprocess.run([docker, "-H", f"unix://{ORB_SOCKET}", "image", "inspect", "np-w4-events:v4"],
                                          capture_output=True, timeout=20).returncode == 0
        return ("ok", "present on OrbStack; ctrs is checked per trial") if found else \
            ("fail", "np-w4-events:v4 missing; build both engines' inputs with `python3 bench/native/runner.py prepare --only W4`")
    if key == "w5-source":
        sys.path.insert(0, str(HERE))
        import watch_loop
        version = watch_loop.contract()["source"]["version"]
        archive = WORK / "native-perf/inputs" / f"marked-{version}.tar.gz"
        return ("ok", "") if archive.is_file() else \
            ("fail", f"{archive.name} missing; fetch it with `python3 bench/native/runner.py prepare --only W5`")
    if key == "w9-image-ref":
        ref = w9_image_ref()
        return ("ok", ref) if ref else ("fail", "no image on OrbStack carries the pinned Marked digest; install the "
                                              "w8-v6 portfolio or set BENCH_W9_IMAGE_REF (fixtures/w9-v2/README.md)")
    if key == "quiet-host":
        return "ok", "waited for at run time (1-minute load < 4, 5-minute < 6, no hold)"
    raise ValueError(f"unknown requirement {key}")


def preflight(chosen: list[Workload]) -> tuple[bool, list[dict]]:
    needed: dict[str, list[str]] = {}
    for w in chosen:
        for key in w.requires:
            needed.setdefault(key, []).append(w.name)
    rows = []
    for key, users in needed.items():
        status, message = check_requirement(key)
        rows.append({"requirement": key, "status": status, "message": message, "workloads": users})
    manual = [w for w in chosen if w.manual]
    for w in manual:
        rows.append({"requirement": "manual-procedure", "status": "fail",
                     "message": f"{w.name} runs only through {w.manual}", "workloads": [w.name]})
    load = os.getloadavg()
    rows.append({"requirement": "host-load", "status": "info",
                 "message": f"load {load[0]:.1f} {load[1]:.1f} {load[2]:.1f} on {os.cpu_count()} CPUs; "
                            "pairs above the CPU count are rejected by the reporter", "workloads": []})
    return all(r["status"] != "fail" for r in rows), rows


def print_preflight(rows: list[dict]) -> None:
    for r in rows:
        users = f" [{', '.join(r['workloads'][:4])}{' …' if len(r['workloads']) > 4 else ''}]" if r["workloads"] else ""
        print(f"{r['status']:>4}  {r['requirement']}{users}{': ' + r['message'] if r['message'] else ''}")


def _holds() -> list[Path]:
    sys.path.insert(0, str(HERE))
    import runner
    return runner.held()


def wait_quiet(deadline: float) -> bool:
    while time.time() < deadline:
        load = os.getloadavg()
        if not _holds() and load[0] < QUIET["load1"] and load[1] < QUIET["load5"] \
                and not _foreign_daemons():
            return True
        time.sleep(30)
    return False


def judge(run_id: str, design: str = "paired") -> dict:
    sys.path.insert(0, str(HERE))
    import reporting
    files = sorted((WORK / "native-perf/results").glob(f"{run_id}/trials.jsonl"))
    records, issues = reporting.load_records(files)
    report = reporting.analyze(records, issues) if design == "paired" \
        else reporting.analyze_noise(records, issues, design)
    cohorts = []
    for c in report["cohorts"]:
        cohorts.append({
            "rejections": c["rejections"],
            "metrics": {m["metric"]: {"valid_pairs": m["valid_pairs"], "ratio": m["ratio_median"],
                                      "ci95": m["ci95"], "assessment": m["assessment"]}
                        for m in c["metrics"]},
        })
    return {"input_issues": report["input_issues"], "cohorts": cohorts}


def run(chosen: list[Workload], quiet_timeout: float) -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = OUT / stamp
    out.mkdir(parents=True)
    env = {**os.environ, "TMPDIR": str(WORK / "tmp"), "PYTHONDONTWRITEBYTECODE": "1"}
    (WORK / "tmp").mkdir(exist_ok=True)
    results = []
    for w in chosen:
        entry = {"name": w.name, "tier": w.tier, "area": w.area, "command": resolved(w.argv)}
        if "quiet-host" in w.requires and not wait_quiet(time.time() + quiet_timeout):
            entry.update(status="excluded", reason=f"host not quiet within {quiet_timeout:.0f} s")
            results.append(entry)
            continue
        log = out / f"{w.name.replace(':', '_')}.log"
        started = time.monotonic()
        with log.open("w") as fh:
            cp = subprocess.run(entry["command"], cwd=w.cwd, env=env, stdout=fh, stderr=subprocess.STDOUT)
        entry.update(status="ok" if cp.returncode == 0 else "failed", exit=cp.returncode,
                     seconds=round(time.monotonic() - started, 1), log=str(log))
        if w.report:
            run_ids = [line.split("/results/")[1].split("/")[0] for line in log.read_text().splitlines()
                       if line.startswith("results: ") and "/results/" in line]
            entry["runs"] = {rid: judge(rid, w.design) for rid in run_ids}
            if not run_ids:
                entry.update(status="failed", reason="no results line in the log")
        results.append(entry)
        print(f"{entry['status']:>8}  {w.name}  {entry.get('seconds', 0)} s", flush=True)
    summary = {"utc": stamp, "git": _git(), "workloads": results}
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (out / "summary.md").write_text(render(summary))
    print(f"summary: {out / 'summary.md'}")
    return 0 if all(r["status"] == "ok" for r in results) else 1


def _git() -> dict:
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True,
                                text=True).stdout.strip())
    return {"head": head, "dirty": dirty}


def render(summary: dict) -> str:
    lines = [f"# Bench run {summary['utc']}", "",
             f"Source `{summary['git']['head'][:12]}`{' (dirty tree)' if summary['git']['dirty'] else ''}.",
             "Ratios are paired cost medians. Below 1 favors ctrs in cross-engine runs and the",
             "candidate in same-engine runs. A verdict requires at least ten valid pairs.", "",
             "| Workload | Tier | Status | Seconds | Valid pairs | Rejected pairs | Verdicts |",
             "| --- | --- | --- | ---: | ---: | ---: | --- |"]
    for r in summary["workloads"]:
        valid = rejected = 0
        verdicts = []
        for judged in r.get("runs", {}).values():
            for c in judged["cohorts"]:
                rejected += len(c["rejections"])
                valid = max([valid] + [m["valid_pairs"] for m in c["metrics"].values()])
                verdicts += [f"{k} {m['assessment']}" for k, m in c["metrics"].items()
                             if m["assessment"] not in ("unmeasured", "invalid")]
        reason = f" ({r['reason']})" if r.get("reason") else ""
        lines.append(f"| {r['name']} | {r['tier']} | {r['status']}{reason} | {r.get('seconds', '')} | "
                     f"{valid if 'runs' in r else ''} | {rejected if 'runs' in r else ''} | "
                     f"{'; '.join(verdicts) or ('—' if 'runs' in r else '')} |")
    for r in summary["workloads"]:
        for run_id, judged in r.get("runs", {}).items():
            lines += ["", f"## {r['name']} `{run_id}`", ""]
            lines += [f"- input issue: {issue}" for issue in judged["input_issues"]]
            for c in judged["cohorts"]:
                lines += [f"- rejected pair {x['pair_id']}: {x['reason']}" for x in c["rejections"]]
                for metric, m in c["metrics"].items():
                    if m["ratio"] is not None:
                        ci = f" [{m['ci95'][0]:.3g}, {m['ci95'][1]:.3g}]" if m["ci95"] else ""
                        lines.append(f"- {metric}: {m['ratio']:.3g}{ci}, {m['valid_pairs']} pairs, {m['assessment']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--lane', choices=('macos-arm64', 'linux-amd64'), default='macos-arm64')
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("list", "check", "run"):
        p = sub.add_parser(name)
        p.add_argument("--tier", choices=TIERS, help="ceiling; full workloads also need --name")
        p.add_argument("--name", action="append", default=[], help="workload name (repeatable)")
        p.add_argument("--area", action="append", default=[], help="workload area (repeatable)")
        p.add_argument("--skip", action="append", default=[], help="workload name to leave out (repeatable)")
    sub.choices["run"].add_argument("--dry-run", action="store_true", help="print the plan; run nothing")
    sub.choices["run"].add_argument("--quiet-timeout", type=float, default=7200,
                                    help="seconds a scenario workload waits for a quiet host")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11):
        parser.error("native benchmarks require Python 3.11+")
    items = registry(args.lane)
    if args.command == "list":
        chosen = [w for w in items
                  if (args.tier is None or TIERS.index(w.tier) <= TIERS.index(args.tier))
                  and (not args.name or w.name in args.name)
                  and (not args.area or w.area in args.area) and w.name not in args.skip]
        print(f"{'name':<30} {'tier':<9} {'area':<12} {'est. cost':>14}  purpose")
        for w in chosen:
            cost = f"{w.seconds / 60:.0f} min {w.cost_basis[:3]}." if w.seconds >= 60 else f"{w.seconds:.0f} s {w.cost_basis[:3]}."
            print(f"{w.name:<30} {w.tier:<9} {w.area:<12} {cost:>14}  {w.purpose}")
        return 0
    chosen = select(items, args.tier, args.name, args.area, args.skip)
    ready, rows = preflight(chosen)
    print_preflight(rows)
    if args.command == "check":
        return 0 if ready else 1
    total = sum(w.seconds for w in chosen)
    print(f"plan: {len(chosen)} workloads, about {total / 60:.0f} min "
          f"(estimated: {', '.join(w.name for w in chosen if w.cost_basis == 'estimated') or 'none'})")
    for w in chosen:
        print(f"  {w.tier:<9} {w.name:<30} {' '.join(resolved(w.argv)) if w.argv else w.manual}")
    if not ready:
        print("preflight failed; nothing ran")
        return 1
    if args.dry_run:
        return 0
    return run(chosen, args.quiet_timeout)


if __name__ == "__main__":
    raise SystemExit(main())
