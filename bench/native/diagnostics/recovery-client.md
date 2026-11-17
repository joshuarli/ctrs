# W10 persistent probe protocol

`w10-client-v2-persistent` gives each health/read worker one HTTPConnection with
a 200ms timeout. A call makes exactly one HTTP attempt, consumes and validates the
whole response, and closes the connection on failure. The next scheduled call
may reconnect; there is no hidden retry. Normal responses reuse the connection.
Every attempt includes native errno, timing, connect attempts, connections opened
and whether a socket was reused. HTTP 200 with wrong payload is a failed request.

The diagnostic retains the 2ms health schedule, configured read schedule and 100Hz
TCP reachability probe. TCP acceptance alone does not establish guest readiness.
A fresh TCP probe is intentionally separate from persistent HTTP application work.
At most 32 readers plus one health worker and one TCP worker run. Pairs are finite
(1..10), socket waits bounded, and recovery polling has a 30s deadline. Driver
commands have individual 120s timeouts; this is not a 120s total execution deadline.
Shared termination handling performs owned cleanup before original signal death.

```sh
TMPDIR=$PWD/.work/tmp python3.14 bench/native/diagnostics/recovery_pilot.py \
  --ctrs-binary .work/tmp/w10-target/release/ctrs
```

Before a scored comparison, save gate/process/power/thermal conditions and certify
exclusivity. Successful gate exit alone is insufficient. This diagnostic still
marks performance unqualified and checks the actual loaded daemon hash against
the requested binary. Keep command cost in restart-to-correct-response intervals,
expected outage errors separate, and exact precommitted records intact.

Old fresh-connection traces remain v1 diagnostics, including the failed 149-error
stress run. Do not pool versions or reinterpret it as a product failure or a
passed comparison. v2 baseline functional proof must precede any resumed TTL
candidate comparison; the 250ms product default is unchanged.

## Exact API and database recovery

`runner.py run` and `baseline` accept `--interrupt-service api|db` for
`w10-v3-exact-recovery`. The default interrupts the owned API container.
The database condition interrupts only the database container from the
trial's Compose project. Both conditions use the same persistent read and
write workload. Use `--duration` greater than the planned outage and warmup.

```sh
python3.14 bench/native/runner.py baseline --case W10 --a ctrs --b orbstack \
  --interrupt-service db --pairs 10
```

Each write has a unique name and deterministic payload. The verifier checks
every seed row and each acknowledged write's ID, name, and payload directly
in PostgreSQL. If a write intersects the outage and its acknowledgement is
lost, its exact row may still appear. Missing acknowledged writes, unexpected
rows, duplicate identities and wrong payloads fail verification.

The runner retains every attempt and its outage classification. Malformed
success responses and client address exhaustion fail the trial even during
the outage. Recovery includes the start command and ends with the first
exact read. Only successful load requests started after that read enter
the recovered p99. Read and write coverage is required on both sides when
the configured workload includes both.

Run `PYTHONPATH=bench/native python3.14 -m unittest test_recovery_client
test_recovery_trace test_safety test_reporting`. All 64 tests passed,
including a local HTTP server with simulated database interruption and
negative persisted-state and response checks. Native API and database
trials, queue interruption, and owned-engine interruption remain open.
