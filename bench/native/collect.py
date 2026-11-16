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
VM helpers by >10x. Per-process `footprint_bytes` lands on that tick's
records. RSS stays as a cheap approximation.
"""

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
FP_TOTAL_RE = re.compile(r"Footprint:\s+(\d+)\s*B")


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
    ap.add_argument("--footprint-interval", type=float, default=1.0,
                    help="seconds between footprint samples; 0 disables")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    rx = re.compile(args.match, re.IGNORECASE)
    stop = False
    next_fp = 0.0

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
            if (args.footprint_interval > 0 and procs
                    and t0 >= next_fp):
                next_fp = t0 + args.footprint_interval
                try:
                    fp = subprocess.run(
                        ["footprint", "-f", "bytes"]
                        + [str(p["pid"]) for p in procs],
                        capture_output=True, text=True, timeout=30)
                    # Sections are headed by `Name [pid]:`; each carries a
                    # `phys_footprint: N B` auxiliary line. Track the
                    # current pid and keep the LAST phys_footprint seen in
                    # its section. Fall back to the category `Footprint:`
                    # total only if no phys_footprint lines exist at all.
                    by_pid: dict[int, int] = {}
                    cur_pid = None
                    saw_phys = False
                    for line in fp.stdout.splitlines():
                        m = FP_PID_RE.search(line)
                        if m:
                            cur_pid = int(m.group(1))
                            continue
                        m = FP_PHYS_RE.match(line)
                        if m and cur_pid is not None:
                            by_pid[cur_pid] = int(m.group(1))
                            saw_phys = True
                            continue
                    if not saw_phys:
                        # Fallback: the `Footprint:` total sits on the same
                        # header line as the pid, so check both per line.
                        cur_pid = None
                        for line in fp.stdout.splitlines():
                            m = FP_PID_RE.search(line)
                            if m:
                                cur_pid = int(m.group(1))
                            t = FP_TOTAL_RE.search(line)
                            if (t and cur_pid is not None
                                    and cur_pid not in by_pid):
                                by_pid[cur_pid] = int(t.group(1))
                    for p in procs:
                        if p["pid"] in by_pid:
                            p["footprint_bytes"] = by_pid[p["pid"]]
                except Exception:
                    pass
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
