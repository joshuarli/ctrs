#!/usr/bin/env python3
"""Resource sampler for bench/native trials.

Samples host process table entries whose comm matches --match, plus host
load average, one JSON object per line to --out. Runs until SIGTERM/SIGINT.

RSS is per-process resident size in KB as reported by ps; summing matched
processes double-counts shared pages and misses compressed/swapped memory,
so consumers must treat totals as approximations (see README).
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", required=True, help="regex on process comm")
    ap.add_argument("--interval", type=float, default=0.25)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rx = re.compile(args.match, re.IGNORECASE)
    stop = False

    def _term(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)

    with open(args.out, "w") as out:
        while not stop:
            t0 = time.time()
            try:
                ps = subprocess.run(
                    ["ps", "-axo", "pid=,pcpu=,rss=,time=,comm="],
                    capture_output=True, text=True, timeout=5,
                )
                procs = []
                for line in ps.stdout.splitlines():
                    parts = line.split(None, 4)
                    if len(parts) < 5:
                        continue
                    try:
                        pid, pcpu, rss = int(parts[0]), float(parts[1]), int(parts[2])
                    except ValueError:
                        continue
                    cputime_s = parse_cputime(parts[3])
                    comm = parts[4].strip()
                    if rx.search(comm):
                        procs.append({"pid": pid, "comm": comm,
                                      "pcpu": pcpu, "rss_kb": rss,
                                      "cputime_s": cputime_s})
            except Exception as exc:
                procs = []
                sample_error = str(exc)
            else:
                sample_error = None
            rec = {
                "t": round(t0, 3),
                "loadavg": list(os.getloadavg()),
                "procs": procs,
            }
            if sample_error:
                rec["error"] = sample_error
            out.write(json.dumps(rec) + "\n")
            out.flush()
            time.sleep(max(0.0, args.interval - (time.time() - t0)))


if __name__ == "__main__":
    main()
