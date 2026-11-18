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
request does not reset later deadlines. An overdue request starts when its
worker becomes available; its original deadline and accumulated lag remain.
Recovery cannot erase an earlier late slot or make the entire run valid.
All planned operations are attempted.
Any late slot, failed request or incomplete work invalidates rate delivery and
returns failure. The client records planned/offered/delivered counts and every
slot's lag, completion latency and success.

For v3, primary `latency_ms` and runner p50/p95/p99 start at the scheduled slot,
including queued time. `service_latency_ms` retains issue-to-response latency.
Late backlog cannot appear as low latency merely because requests waited outside
the HTTP call. Successful-request latency excludes failures, which remain errors
and prevent a pass. Never pool v2 closed-loop or v3 paced records.
Version v3.1 removes v3's re-pacing after lateness: one delayed response plus
timer overshoot otherwise permanently shifted later requests. The regression
fails on v3 (four late slots) and passes on v3.1 (one late slot, still invalid).
Version v3.2 keeps those absolute slots and uses a Darwin `select.kqueue`
one-shot `EVFILT_TIMER` wait with `NOTE_NSECONDS` (`0x4`) and `NOTE_CRITICAL`
(`0x20`). The critical flag requests minimal timer coalescing; it does not
guarantee a wake time or qualify a speedup. The timer is armed for the remaining
monotonic interval and the deadline is rechecked after the event. The SDK
documents `NOTE_ABSOLUTE` deadlines in the `gettimeofday` clock domain, so v3.2
does not use that flag for monotonic scheduled slots. Other platforms retain
standard-library sleep waits. The kqueue call has a bounded timeout, and the
client rejects empty results, `EV_ERROR`, and events without a positive timer
expiration. v3.1 and v3.2 records are separate fixture versions and must not be
pooled. The native timer experiment is diagnostic evidence only; no speedup is
qualified by it.

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

`runner.py check w2` covers actual local HTTP counts and exact writes, a
deliberately delayed server's visible backlog, and controlled-clock pacing that
verifies later slots retain their absolute deadlines. A Darwin timer check
asserts only that the wait does not return early; it has no tight upper-time
assertion. Queue error and empty-result paths verify that owned queues close.
The native application proof remains separate, and this diagnostic fixture does
not establish a qualified speedup.

## Container-to-container load

`runner.py run` and `baseline` accept `--client-location guest` for W2.
The runner creates an owned peer on the application network from the
API's loaded image ID. It verifies that the peer uses the same image and
that the copied client matches the selected source hash. Health, workload
and count requests use the peer's direct connection to `api:8000`. The
published-port client remains the default.

```sh
python3.14 bench/native/runner.py run --engine ctrs --case W2 \
  --client-location guest --operations 10000 --concurrency 4 --request-rate 500
```

The same option works for fixed-work and saturation. Guest fixed-rate load
uses the client's portable timer path, while the macOS host uses kqueue.
Workload CPU accounts for the guest client inside the engine's VM. The API
cgroup counters still bound the application work, and the runner copies
receipts afterward. The final check still compares every acknowledged
write against PostgreSQL.

`runner.py check w2` passed 113 tests with zero skips. The offline placement
test covers all three modes, rejects a wrong client hash and a corrupt
persisted payload, and verifies owned peer cleanup.

### Native placement proof

Source `98b9445` ran all three modes on both engines and both client paths
with the common W8 v2 stack. The controller validated the preinstalled
image IDs, architecture, ordered DiffIDs and seed with
`runner.prepare_pinned_stack`. It supplied the resulting override to
`Engine.compose` and started each stack with `up -d --no-build --pull never`.
Reinstall the pinned inputs with the [portfolio instructions](../fixtures/w8-v2/README.md).

Use a distinct owned run ID and call `runner.trial_w2` with concurrency 4,
write ratio 0.3 and seed 7 for each engine and location. Use
`operations=10000, request_rate=500, duration=20` for offered rate,
`operations=10000, duration=5` for fixed work, and `duration=5` for
saturation. Save the trial record and the client and PostgreSQL receipts
for every outcome. These diagnostics used the signed host and guest
artifacts from the [W8 cancellation proof](../../../docs/evidence/native-w8-content-state-2026-11-17.md#interrupted-delivery-and-retry).

In `w2-placement-2026-11-18T013135640+0000`, each leg delivered all
10,000 requests with zero request errors. All four verified 6,987 reads,
3,013 writes and the exact 3,513 persisted rows. The PostgreSQL receipt
SHA-256 was identical across all legs,
`c748066181e937e6896f8eb4d59964ea9ea2b34b249cb0bfc4306de23b2b9f15`.
Both ctrs paths stayed within the 10 ms scheduling-lag budget.
OrbStack exceeded that budget for 367 slots on the published port and
3,447 slots on the guest path. Both OrbStack schedules failed rate
validation. The first ctrs trial began before the owned VM helper appeared
in process discovery, leaving its host resource receipt incomplete.

In `w2-closed-loop-placement-2026-11-18T013442483+0000`, both engines
passed exact-data verification on both paths in fixed-work and saturation
modes. All four fixed-work legs again delivered 10,000 requests and
verified 3,513 persisted rows. Each saturation leg verified its own
acknowledged writes and seed rows with zero request errors. The shared host
leaves the entire placement batch ineligible for scoring.
