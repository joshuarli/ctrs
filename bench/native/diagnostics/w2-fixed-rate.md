# Fixed offered-load W2 diagnostic

The v3 client adds fixed offered-rate work to the existing W2 request and exact
persisted-data oracle. It is a diagnostic fixture, not a timing qualification.
The v2 `fixtures/w2/load.py` remains byte-for-byte pinned for W11 and existing
workloads. Rate work uses `fixtures/w2/v3.py`, recorded by path and SHA-256.
The frozen clients intentionally keep independent versions.

Use `--request-rate` with positive `--operations` on W2 `run` or `baseline`.
Rates must be finite and positive, with a planned span no longer than one hour.
Invalid combinations fail before engine access. Existing fixed-work and duration
saturation modes keep their defaults and use the v2 client.

Each request has one absolute scheduled slot shared across the workers. A slow
request does not reset later deadlines. Once a worker exceeds the 10ms schedule
lag budget, it keeps pacing rather than bursting to catch up; original deadlines
and accumulated lag remain in every slot. All planned operations are attempted.
Any late slot, failed request or incomplete work invalidates rate delivery and
returns failure. The client records planned/offered/delivered counts and every
slot's lag, completion latency and success.

For v3, primary `latency_ms` and runner p50/p95/p99 start at the scheduled slot,
including queued time. `service_latency_ms` retains issue-to-response latency.
Late backlog cannot appear as low latency merely because requests waited outside
the HTTP call. Successful-request latency excludes failures, which remain errors
and prevent a pass. Never pool v2 closed-loop or v3 paced records.

Example exploratory command, using the runner's existing prepared engine inputs:

```sh
TMPDIR=$PWD/.work/tmp PYTHONDONTWRITEBYTECODE=1 python3.14 \
  bench/native/runner.py run --engine orbstack --case W2 \
  --operations 10000 --concurrency 4 --request-rate 500
```

That command alone does not freeze images, binary, residency or host ownership.
Campaign native diagnostics must additionally enforce digest-pinned Compose
inputs, checked API sources, actual signed binary/boot hashes and explicit
resource settings, as the resource-cycle pilot does. Host timing qualification
also requires pre/post readiness and genuine exclusivity.

`runner.py check w2` now passes 52 tests with zero skips. Actual local HTTP checks
verify exact writes/counts and a deliberately delayed server's visible backlog;
controlled-clock work verifies healthy rate admission without assuming the host
can always schedule a test within 10ms. The first native proof remains pending.
