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
`w10-v4-recovery`. The default interrupts the owned API container.
The database condition interrupts only the database container from the
trial's Compose project. Both conditions use the preinstalled common
portfolio and the same persistent read and write workload. Compose uses
the verified image IDs with builds and pulls disabled. Use `--duration`
greater than the planned outage and warmup.

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

Engine CPU per success uses the recovery workload's boundary counters.
The denominator counts successful load responses and excludes readiness
probes and outage failures. For queue recovery it counts both batches'
verified jobs and sums the two measured worker phases. Missing boundary
counters leave this metric unmeasured.

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

The normal W10 entry point now produces the same pinned Compose override
used for the database diagnostic. Both native API trials in
`w10-pinned-native-28aed3bcf647` passed with this entry point, exact rows
and zero unexpected errors.

## Queue-service recovery

`runner.py run` and `baseline` also accept `--interrupt-service queue`.
Run `prepare` to build the W4 v4 image. Queue mode uses `--concurrency`
workers. Here `--duration` is the restart verification deadline in seconds
and the planned Redis downtime is three seconds. The API/database workload
mix options apply to those two conditions.

```sh
python3.14 bench/native/pyramid.py run --name w10-recovery:cohort \
  --name w10-db-recovery:cohort --name w10-queue-recovery:cohort
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
own data root and socket and seeds its private store from the validated
OCI layout at `.work/native-perf/inputs/w8-portfolio-v6/layout`. It then
warms the stack before the interruption.
It proves the socket belongs to the launched daemon and the VM holds the
private guest disk. It sends SIGKILL only to its own daemon child and waits
for both old processes to exit before restarting.

```sh
python3.14 bench/native/pyramid.py run --name w10-engine-recovery
```

The runner restores the original Compose project without rebuilding or
pulling images. The recovery receipts require new daemon and VM process
identities, the same loaded executables and boot artifacts, and the same
guest disk and API/database container identities. The exact PostgreSQL
row check and post-recovery load checks still apply. Results stay in the
private run directory. They carry no comparative timing or CPU verdict.

The first native trial `w10-engine-native-0fc25e6388b0` restarted the
owned processes and containers, then timed out waiting for the API.
Guest-local probes reached PostgreSQL. Application logs showed rejection
because the generated authentication rule was missing. In the control
`w10-engine-boundary-cae58a0bfe46`, the bytes of that rule at the end of
`pg_hba.conf` became zeros after the crash. Syncing only that file in
`w10-engine-boundary-a7bf0df9f908` preserved its bytes and restored reads.

The warmed fixture now syncs `pg_hba.conf` before the load starts and
requires identical SHA-256 digests before and after the restart. This
establishes durable startup configuration before the test begins.
The successful native engine leg in `w10-pinned-native-28aed3bcf647`
verified new daemon and VM identities, unchanged guest disk and auth
configuration, 18,925 exact acknowledged rows and zero unexpected
request errors. It ran for 30 seconds with two clients and seed 7.
The archived run precedes the fixture version label update.

Run `PYTHONPATH=bench/native python3.14 -m unittest test_recovery_client
test_recovery_trace test_w4_lifecycle test_w1 test_safety test_reporting
test_registry_portfolio test_w4`. All 91 focused tests passed. They cover
a simulated engine interruption on the local HTTP fixture, identity and
artifact rejection, refusal to signal a foreign daemon, and waiting for
the old VM. An equivalent OrbStack engine interruption still requires
a dedicated native target with the same interruption boundary. This Mac
uses OrbStack's shared Docker socket. OrbStack Linux machines share its
VM kernel, and `orb restart docker` acts on the Docker engine. Restarting
an OrbStack Linux machine supplies a machine-recovery result. A
Docker-engine restart on the shared socket affects other projects.
[OrbStack architecture](https://docs.orbstack.dev/architecture) and
[command-line controls](https://docs.orbstack.dev/headless).
