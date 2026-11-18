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
negative persisted-state and response checks.

Native database diagnostic `w10-db-native-0beb30700799` passed on ctrs
and OrbStack. It used the signed W8 cancellation candidate, the W1 seed and
three preinstalled common W8 v2 portfolio images. The diagnostic
overrode the Compose service image references with the verified engine
image IDs and disabled builds and pulls. It ran four clients for 20
seconds with seed 7, a 30% write mix and a three-second database outage
after six seconds of load. All acknowledged rows were exact and both
engines reported zero unexpected errors. The counts below describe
the retained correctness receipts.

| Engine | Acknowledged writes | Interrupted writes that persisted | Expected outage errors |
| --- | ---: | ---: | ---: |
| ctrs | 11,953 | 20 | 60 |
| OrbStack | 7,210 | 28 | 65 |

The independent diagnostic used a pinned Compose override. The normal
W10 entry point still uses fixture tags. Native v3 API and owned-engine
interruption remain open.

## Queue-service recovery

`runner.py run` and `baseline` also accept `--interrupt-service queue`.
Run `prepare` to build the W4 v4 image. Queue mode uses `--concurrency`
workers. Here `--duration` is the restart verification deadline in seconds
and the planned Redis downtime is three seconds. The API/database workload
mix options apply to those two conditions.

```sh
python3.14 bench/native/runner.py baseline --case W10 --a ctrs --b orbstack \
  --interrupt-service queue --concurrency 4 --pairs 10
```

The fixture enables Redis AOF with `appendfsync always` and a fresh named
volume. It accepts all 200 jobs before interrupting the owned Redis
container. After restart it requires the same FIFO contents, including every
job payload and enqueue timestamp. Workers then process the recovered jobs.
Verification checks all 400 artifacts and binds each completion receipt
to the original backlog. A fresh 200-job batch on the recovered service
supplies post-recovery p99. The recovered backlog latency is retained
separately because it includes the outage.

Run `PYTHONPATH=bench/native python3.14 -m unittest test_w4_lifecycle
test_w4 test_mixed_cycle test_recovery_client test_recovery_trace
test_reporting`. The focused suite passed 59 tests. They include the
local RESP snapshot, a simulated Redis restart, a corrupted backlog,
owned-volume cleanup, and signed monotonic offset normalization.

Native diagnostic `w10-queue-native-97a04ef1fe7e` retained an exact
OrbStack backlog across Redis restart, then failed when all four workers
rejected the ingest container's time-namespace ID. Three independent
probes on the same OrbStack boot showed distinct time-namespace IDs
and zero monotonic offsets. ctrs passed with a shared time namespace.

The v4 image converts `CLOCK_MONOTONIC` readings to the initial namespace
clock by subtracting each container's kernel-reported offset. It requires
a common boot ID and rejects unavailable or malformed monotonic offsets.
Keep v3 and v4 timing cohorts separate. [Linux time namespaces](https://www.man7.org/linux/man-pages/man7/time_namespaces.7.html)

Native diagnostic `w10-queue-clock-924f5c21bb55` passed on both engines.
The worker image came from one ARM64 build of `Dockerfile.latency`, exported
once and loaded into ctrs. Both sides verified image DiffIDs and used the
pinned W8 v2 Redis image. The export SHA256 was
`04ad40c6bda62546bcf9e48dc1c86b650febf3a2a274952d20bc8e2340585249`.
Each four-worker trial verified 200 recovered backlog jobs, 200 new jobs,
and all 800 artifacts. These runs are correctness evidence.

## Owned-engine recovery

The `engine` target is a standalone ctrs diagnostic. The runner creates its
own data root and socket, then warms the stack before the interruption.
It proves the socket belongs to the launched daemon and the VM holds the
private guest disk. It sends SIGKILL only to its own daemon child and waits
for both old processes to exit before restarting.

```sh
python3.14 bench/native/runner.py run --case W10 --engine ctrs \
  --interrupt-service engine --duration 90
```

The runner restores the original Compose project without rebuilding or
pulling images. The recovery receipts require new daemon and VM process
identities, the same loaded executables and boot artifacts, and the same
guest disk and API/database container identities. The exact PostgreSQL
row check and post-recovery load checks still apply. Results stay in the
private run directory. They carry no comparative timing or CPU verdict.

Run `PYTHONPATH=bench/native python3.14 -m unittest test_recovery_client
test_recovery_trace test_w4_lifecycle test_safety test_reporting`. All 74
focused tests passed. They cover a simulated engine interruption on the
local HTTP fixture, identity and artifact rejection, refusal to signal a
foreign daemon, and waiting for the old VM. Native crash validation and
an isolated OrbStack interruption target remain open.
