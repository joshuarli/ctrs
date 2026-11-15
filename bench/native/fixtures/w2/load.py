#!/usr/bin/env python3
"""W2 load driver: sustained mixed read/write load against the W1 API.

Standard library only; identical binary behaviour for both engines.
Each worker keeps one keep-alive HTTP connection and issues GET /items
(reads) and POST /items (writes) in a seeded-ratio mix for --duration
seconds. Prints a JSON summary on stdout and optionally --out.
"""

import argparse
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
           error_log, t_start):
    rng = random.Random(rng_seed)
    host, port = base
    conn = http.client.HTTPConnection(host, port, timeout=10)
    seq = 0
    end = time.monotonic() + duration
    while time.monotonic() < end and not stop.is_set():
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
            resp.read()
            ok = 200 <= resp.status < 300
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
        latencies.append(lat)
        with counts_lock:
            if ok:
                counts["writes" if write else "reads"] += 1
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
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    u = urllib.parse.urlparse(args.url)
    base = (u.hostname, u.port or 80)

    latencies = []
    counts = {"reads": 0, "writes": 0, "errors": 0}
    stop = threading.Event()
    error_log = []
    t_start = time.monotonic()
    threads = [
        threading.Thread(
            target=worker,
            args=(i, base, args.duration, args.write_ratio,
                  args.seed * 1000 + i, latencies, counts, stop,
                  error_log, t_start),
            daemon=True,
        )
        for i in range(args.concurrency)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - t_start

    latencies.sort()
    total = sum(counts.values())
    summary = {
        "duration_s": round(elapsed, 3),
        "concurrency": args.concurrency,
        "write_ratio": args.write_ratio,
        "requests": total,
        "reads_ok": counts["reads"],
        "writes_ok": counts["writes"],
        "errors": counts["errors"],
        "rps": round(total / elapsed, 2) if elapsed else None,
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
        with open(args.out + ".errors.jsonl", "w") as f:
            for e in error_log:
                f.write(json.dumps(e) + "\n")
    sys.exit(0 if counts["errors"] == 0 else 1)


if __name__ == "__main__":
    main()
