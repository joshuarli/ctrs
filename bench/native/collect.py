#!/usr/bin/env python3
"""Sample verified ARM64 macOS engine processes using native rusage counters.

The kernel ri_phys_footprint field is the physical accounting signal; category
Footprint output never substitutes for it. Required processes carry kernel start
identity. Missing/changed processes remain errors. CPU boundary calls use the
same cheap native API without waiting for external footprint commands.
"""

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

from macos_counters import Counters

FP_PID_RE = re.compile(r"^.*\[(-?\d+)\]:\s+(?:(?:32|64)-bit\s+)?Footprint:")
FP_PHYS_RE = re.compile(r"^\s*phys_footprint:\s+(\d+)\s*B")
SAMPLER_VERSION = "4-native-rusage"


def stop_receipt_path(trace):
    return Path(trace).with_suffix('.stop.json')


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
    required = {p["pid"]: p for p in identity.get("required_processes", [])}
    return native_sample(Counters(), required)


def native_sample(counters, required):
    result = {"started_monotonic": time.monotonic(),
              "method": "proc_pid_rusage V0; Mach timebase conversion",
              "procs": [], "errors": []}
    if not required:
        result["errors"].append("no verified ownership manifest")
    for pid, expected in required.items():
        try:
            proc = counters.read(pid)
            if proc["kernel_start_identity"] != expected.get("kernel_start_identity"):
                raise ValueError(f"process start identity changed: {pid}")
            proc.update({k: expected[k] for k in ("comm", "start_identity")})
            result["procs"].append(proc)
        except Exception as exc:
            result["errors"].append(f"required process {pid}: {exc}")
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
    ap.add_argument("--match", help="discovery hint; never establishes ownership")
    ap.add_argument("--interval", type=float, default=0.25)
    ap.add_argument("--ownership", help="verified process identity manifest")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.interval <= 0:
        ap.error("interval must be positive")

    ownership = json.loads(Path(args.ownership).read_text()) if args.ownership else {}
    required = {p["pid"]: p for p in ownership.get("required_processes", [])}
    stop = False
    stop_requested = None

    def _term(*_):
        nonlocal stop, stop_requested
        if stop_requested is None:
            stop_requested = time.monotonic()
        stop = True

    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)

    counters = Counters()
    sampler_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    counter_sha256 = hashlib.sha256(Path(__file__).with_name("macos_counters.py").read_bytes()).hexdigest()
    with open(args.out, "w") as out:
        while not stop:
            tick = time.monotonic()
            sample = native_sample(counters, required)
            values = {p["pid"]: p["footprint_bytes"] for p in sample["procs"]}
            rec = {
                "t": time.time(), "monotonic": tick,
                "cpu_sample_ended_monotonic": sample["ended_monotonic"],
                "sampler_version": SAMPLER_VERSION, "sampler_sha256": sampler_sha256,
                "counter_module_sha256": counter_sha256,
                "ownership_verified": bool(required) and not sample["errors"],
                "ownership_errors": sample["errors"],
                "required_processes": list(required.values()),
                "ownership_method": ownership.get("method"),
                "footprint": {"required_pids": list(required), "values": values,
                    "method": "rusage_info_v0.ri_phys_footprint",
                    "started_monotonic": sample["started_monotonic"],
                    "ended_monotonic": sample["ended_monotonic"],
                    "missing_pids": sorted(set(required) - values.keys()),
                    "error": "; ".join(sample["errors"]) or None},
                "loadavg": list(os.getloadavg()), "procs": sample["procs"],
            }
            out.write(json.dumps(rec) + "\n")
            out.flush()
            time.sleep(max(0.0, args.interval - (time.monotonic() - tick)))
    stop_receipt_path(args.out).write_text(json.dumps({
        "sampler_version": SAMPLER_VERSION, "pid": os.getpid(),
        "stop_requested_monotonic": stop_requested}) + "\n")


if __name__ == "__main__":
    main()
