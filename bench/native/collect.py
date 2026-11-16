#!/usr/bin/env python3
"""Resource sampler for bench/native trials.

Samples host process table entries whose comm matches --match, plus host
load average, one JSON object per line to --out. Runs until SIGTERM/SIGINT.

RSS is per-process resident size in KB as reported by ps; summing matched
processes double-counts shared pages and misses compressed/swapped memory,
so consumers must treat totals as approximations (see README).

Every --footprint-interval seconds the matched pids are also measured with
`/usr/bin/footprint -f bytes`. The qualified physical-memory signal is the
per-process `phys_footprint:` auxiliary field (Activity Monitor's memory
metric); the category-table `Footprint:` total is NOT phys_footprint — it
excludes IOKit/IOSurface and other accounted-elsewhere pages and undercounts
VM helpers by >10x. Asynchronous footprint records expose required PIDs,
missing PIDs, timing and errors. RSS stays as a cheap approximation.
"""

import concurrent.futures
import hashlib
from pathlib import Path
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time

FP_PID_RE = re.compile(r"\[(-?\d+)\]:")
FP_PHYS_RE = re.compile(r"^\s*phys_footprint:\s+(\d+)\s*B")
SAMPLER_VERSION = "2-strict-phys"


def parse_footprint(output: str) -> dict[int, int]:
    """Extract only the macOS phys_footprint auxiliary field by PID."""
    values = {}
    pid = None
    for line in output.splitlines():
        header = FP_PID_RE.search(line)
        if header:
            pid = int(header.group(1))
        value = FP_PHYS_RE.match(line)
        if value and pid is not None:
            values[pid] = int(value.group(1))
    return values


def measure_footprint(pids):
    started = time.monotonic()
    result = {"started_monotonic": started, "method": "footprint phys_footprint",
              "required_pids": pids, "values": {}, "error": None}
    try:
        cp = subprocess.run(["/usr/bin/footprint", "-f", "bytes", *map(str, pids)],
                            capture_output=True, text=True, timeout=30)
        result["values"] = parse_footprint(cp.stdout)
        if cp.returncode:
            result["error"] = f"exit {cp.returncode}: {cp.stderr[-1000:]}"
    except Exception as exc:
        result["error"] = str(exc)
    result["ended_monotonic"] = time.monotonic()
    result["missing_pids"] = sorted(set(pids) - result["values"].keys())
    return result


def parse_cputime(text: str) -> float | None:
    """ps `time` column ([[dd-]hh:]mm:ss[.cc]) -> cumulative CPU seconds."""
    try:
        days = 0.0
        if "-" in text:
            d, text = text.split("-", 1)
            days = float(d) * 86400.0
        parts = [float(x) for x in text.split(":")]
        secs = 0.0
        for p in parts:
            secs = secs * 60.0 + p
        # mm:ss or hh:mm:ss or dd-hh:mm:ss — the leftmost field is the
        # largest unit only when there are 3+ colon fields.
        if len(parts) == 2:
            secs = parts[0] * 60.0 + parts[1]
        elif len(parts) == 3:
            secs = parts[0] * 3600.0 + parts[1] * 60.0 + parts[2]
        elif len(parts) == 4:
            secs = (parts[0] * 86400.0 + parts[1] * 3600.0
                    + parts[2] * 60.0 + parts[3])
        return days + secs
    except (ValueError, IndexError):
        return None


def validate_processes(required, processes):
    observed = {p["pid"]: p for p in processes}
    errors = []
    for pid, expected in required.items():
        actual = observed.get(pid)
        if actual is None:
            errors.append(f"missing required process {pid}")
        elif any(actual.get(k) != expected.get(k) for k in ("comm", "start_identity")):
            errors.append(f"process identity changed: {pid}")
    if not required:
        errors.append("no verified ownership manifest")
    return errors


def cpu_boundary(identity):
    started = time.monotonic()
    required = {p["pid"]: p for p in identity.get("required_processes", [])}
    result = {"started_monotonic": started, "method": "ps cumulative CPU; 0.01s resolution",
              "procs": [], "errors": []}
    try:
        cp = subprocess.run(["ps", "-axo", "pid=,time=,lstart=,comm="],
                            capture_output=True, text=True, timeout=5, check=True)
        for line in cp.stdout.splitlines():
            parts = line.split(None, 7)
            if len(parts) == 8 and int(parts[0]) in required:
                result["procs"].append({"pid": int(parts[0]),
                    "cputime_s": parse_cputime(parts[1]),
                    "start_identity": " ".join(parts[2:7]), "comm": parts[7]})
        result["errors"].extend(validate_processes(required, result["procs"]))
    except Exception as exc:
        result["errors"].append(str(exc))
    result["ended_monotonic"] = time.monotonic()
    return result


def cpu_delta(before, after):
    errors = before["errors"] + after["errors"]
    old = {p["pid"]: p for p in before["procs"]}
    new = {p["pid"]: p for p in after["procs"]}
    total = 0.0
    if not old or old.keys() != new.keys():
        errors.append("CPU boundary process coverage differs")
    for pid, proc in new.items():
        prior = old.get(pid, {})
        a, b = prior.get("cputime_s"), proc.get("cputime_s")
        if (a is None or b is None or b < a or
                prior.get("start_identity") != proc.get("start_identity")):
            errors.append(f"missing or changed CPU boundary counter: {pid}")
        else:
            total += b - a
    return {"cpu_seconds": round(total, 6) if not errors else None,
            "errors": errors, "before": before, "after": after}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True, help="regex on process comm")
    ap.add_argument("--interval", type=float, default=0.25)
    ap.add_argument("--footprint-interval", type=float, default=1.0,
                    help="seconds between footprint samples; 0 disables")
    ap.add_argument("--ownership", help="verified process identity manifest")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rx = re.compile(args.match, re.IGNORECASE)
    ownership = json.loads(Path(args.ownership).read_text()) if args.ownership else {}
    required = {p["pid"]: p for p in ownership.get("required_processes", [])}
    stop = False
    next_fp = 0.0

    def _term(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    pending_fp = None
    sampler_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with open(args.out, "w") as out:
        while not stop:
            t0 = time.time()
            mono = time.monotonic()
            try:
                ps = subprocess.run(
                    ["ps", "-axo", "pid=,pcpu=,rss=,time=,lstart=,comm="],
                    capture_output=True, text=True, timeout=5,
                )
                if ps.returncode:
                    raise RuntimeError(f"ps exit {ps.returncode}: {ps.stderr}")
                procs = []
                for line in ps.stdout.splitlines():
                    parts = line.split(None, 9)
                    if len(parts) < 10:
                        continue
                    try:
                        pid, pcpu, rss = int(parts[0]), float(parts[1]), int(parts[2])
                    except ValueError:
                        continue
                    cputime_s = parse_cputime(parts[3])
                    comm = parts[9].strip()
                    if (pid in required if args.ownership else rx.search(comm)):
                        procs.append({"pid": pid, "comm": comm,
                                      "pcpu": pcpu, "rss_kb": rss,
                                      "cputime_s": cputime_s,
                                      "start_identity": " ".join(parts[4:9])})
            except Exception as exc:
                procs = []
                sample_error = str(exc)
            else:
                sample_error = None
            ownership_errors = validate_processes(required, procs)
            footprint = None
            if pending_fp is not None and pending_fp.done():
                footprint = pending_fp.result()
                pending_fp = None
            if (args.footprint_interval > 0 and procs and t0 >= next_fp
                    and pending_fp is None):
                next_fp = t0 + args.footprint_interval
                pending_fp = pool.submit(measure_footprint, [p["pid"] for p in procs])
            rec = {
                "t": t0,
                "monotonic": mono,
                "cpu_sample_ended_monotonic": time.monotonic(),
                "sampler_version": SAMPLER_VERSION,
                "sampler_sha256": sampler_sha256,
                "ownership_verified": bool(required) and not ownership_errors,
                "ownership_errors": ownership_errors,
                "required_processes": list(required.values()),
                "ownership_method": ownership.get("method", "comm discovery only"),
                "footprint": footprint,
                "loadavg": list(os.getloadavg()),
                "procs": procs,
            }
            if sample_error:
                rec["error"] = sample_error
            out.write(json.dumps(rec) + "\n")
            out.flush()
            time.sleep(max(0.0, args.interval - (time.time() - t0)))

        if pending_fp is not None:
            out.write(json.dumps({"record_type": "footprint_only",
                                  "footprint": pending_fp.result()}) + "\n")
            out.flush()
    pool.shutdown(wait=True)


if __name__ == "__main__":
    main()
