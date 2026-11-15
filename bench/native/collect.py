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
                    ["ps", "-axo", "pid=,pcpu=,rss=,comm="],
                    capture_output=True, text=True, timeout=5,
                )
                procs = []
                for line in ps.stdout.splitlines():
                    parts = line.split(None, 3)
                    if len(parts) < 4:
                        continue
                    try:
                        pid, pcpu, rss = int(parts[0]), float(parts[1]), int(parts[2])
                    except ValueError:
                        continue
                    comm = parts[3].strip()
                    if rx.search(comm):
                        procs.append({"pid": pid, "comm": comm,
                                      "pcpu": pcpu, "rss_kb": rss})
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
