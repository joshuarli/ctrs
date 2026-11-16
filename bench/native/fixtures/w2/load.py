#!/usr/bin/env python3
"""W2 load driver: sustained mixed read/write load against the W1 API.

Standard library only; identical binary behaviour for both engines.
Each worker keeps one keep-alive HTTP connection and issues GET /items
(reads) and POST /items (writes) in a seeded-ratio mix. --operations fixes
total work; omitting it runs saturation for --duration seconds. Prints a JSON summary on stdout and optionally --out.
"""

import argparse
import concurrent.futures
import http.client
import json
import random
import sys
import threading
import time
import urllib.parse


def pct(sorted_vals, q):
    if not sorted_vals:
        return None
    idx = min(len(sorted_vals) - 1, int(round(q * (len(sorted_vals) - 1))))
    return sorted_vals[idx]


def worker(wid, base, duration, write_ratio, rng_seed, latencies, counts, stop,
           error_log, t_start, operations=None, writes=None):
    rng = random.Random(rng_seed)
    host, port = base
    conn = http.client.HTTPConnection(host, port, timeout=10)
    seq = 0
    end = time.monotonic() + duration
    while ((seq < operations if operations is not None else time.monotonic() < end)
           and not stop.is_set()):
        write = rng.random() < write_ratio
        seq += 1
        t0 = time.monotonic()
        try:
            if write:
                body = json.dumps({"name": f"load-{wid}-{seq}", "payload": "x" * 64})
                conn.request("POST", "/items", body=body,
                             headers={"Content-Type": "application/json"})
            else:
                conn.request("GET", "/items?limit=25")
            resp = conn.getresponse()
            payload = resp.read()
            ok = 200 <= resp.status < 300
            if ok:
                data = json.loads(payload)
                if write:
                    ok = (type(data.get("id")) is int and data["id"] > 0
                          and data.get("name") == f"load-{wid}-{seq}")
                else:
                    ok = data.get("items") == [{"id": i, "name": f"item-{i}"} for i in range(1, 26)]
        except Exception as exc:
            ok = False
            kind = type(exc).__name__
            if len(error_log) < 200:
                error_log.append({
                    "t": round(time.monotonic() - t_start, 3),
                    "worker": wid, "kind": kind,
                    "detail": str(exc)[:160],
                })
            try:
                conn.close()
            except Exception:
                pass
            conn = http.client.HTTPConnection(host, port, timeout=10)
        lat = (time.monotonic() - t0) * 1000.0
        # Failed connection attempts are not useful work. Keep successful
        # request latency/throughput separate from the error counts, so a
        # fast-refusing engine cannot appear faster during W10 downtime.
        if ok:
            latencies.append(lat)
        with counts_lock:
            if ok:
                counts["writes" if write else "reads"] += 1
                if write and writes is not None:
                    writes.append({"name": f"load-{wid}-{seq}", "payload": "x" * 64})
            else:
                counts["errors"] += 1
    try:
        conn.close()
    except Exception:
        pass


counts_lock = threading.Lock()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="http://127.0.0.1:PORT")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--duration", type=float, default=20.0)
    ap.add_argument("--write-ratio", type=float, default=0.3)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--operations", type=int, default=None,
                    help="fixed total attempted operations; duration mode is saturation")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.concurrency <= 0 or args.duration <= 0 or (args.operations is not None and args.operations <= 0):
        ap.error("concurrency, duration and operations must be positive")
    if not 0 <= args.write_ratio <= 1:
        ap.error("write ratio must be in [0, 1]")
    u = urllib.parse.urlparse(args.url)
    base = (u.hostname, u.port or 80)

    latencies = []
    counts = {"reads": 0, "writes": 0, "errors": 0}
    stop = threading.Event()
    error_log = []
    writes = []
    t_start = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(
            worker, i, base, args.duration, args.write_ratio, args.seed * 1000 + i,
            latencies, counts, stop, error_log, t_start,
            operations=(args.operations // args.concurrency +
                        (i < args.operations % args.concurrency))
            if args.operations is not None else None, writes=writes)
            for i in range(args.concurrency)]
        try:
            for future in futures:
                future.result()
        except Exception:
            stop.set()
            raise
    elapsed = time.monotonic() - t_start

    latencies.sort()
    total = sum(counts.values())
    successful = counts["reads"] + counts["writes"]
    summary = {
        "fixture_version": "w2-v2-fixed-work",
        "mode": "fixed-work" if args.operations is not None else "saturation",
        "target_operations": args.operations,
        "duration_s": round(elapsed, 3),
        "concurrency": args.concurrency,
        "write_ratio": args.write_ratio,
        "requests": total,
        "requests_ok": successful,
        "reads_ok": counts["reads"],
        "writes_ok": counts["writes"],
        "errors": counts["errors"],
        "rps": round(successful / elapsed, 2) if elapsed else None,
        "attempted_rps": round(total / elapsed, 2) if elapsed else None,
        "latency_scope": "successful_requests",
        "latency_ms": {
            "p50": pct(latencies, 0.50),
            "p95": pct(latencies, 0.95),
            "p99": pct(latencies, 0.99),
            "max": latencies[-1] if latencies else None,
        },
    }
    text = json.dumps(summary)
    print(text)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")
        with open(args.out + ".writes.jsonl", "w") as f:
            for write in sorted(writes, key=lambda row: row["name"]):
                f.write(json.dumps(write) + "\n")
        with open(args.out + ".errors.jsonl", "w") as f:
            for e in error_log:
                f.write(json.dumps(e) + "\n")
    complete = args.operations is None or total == args.operations
    sys.exit(0 if counts["errors"] == 0 and successful > 0 and complete else 1)


if __name__ == "__main__":
    main()
