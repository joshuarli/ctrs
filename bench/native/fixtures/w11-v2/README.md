# Run short mixed application cycles

Use the pinned W8 multilayer portfolio and worker OCI layout. The worker archive
is a read-only export of the verified W4 image. `worker-pin.json` records its
manifest, config, diff IDs and application hash. Preparation preserves both
engines' existing images and shared daemons.

```sh
TMPDIR=$PWD/.work/tmp CTRS_CPUS=2 CTRS_MEMORY_MIB=4096 \
python3.14 bench/native/diagnostics/mixed_pilot.py \
  --portfolio-layout .work/native-perf/inputs/w8-portfolio-v2/layout \
  --worker-layout .work/native-perf/inputs/w11-worker-v1/layout \
  --ctrs-binary .work/tmp/disk-expand-target/release/ctrs --cycles 2
```

The pilot accepts one to three cycles. Each cycle starts three activities:

- 5,000 fixed API operations with four persistent HTTP clients and 30% writes.
- 200 real queue jobs, four workers, 12,800 events and 400 exact artifacts.
- 16 real Marked TypeScript build and CLI-test jobs at concurrency four.

The API, PostgreSQL and Redis containers persist across cycles. The unchanged
pinned W2 client uses disjoint worker IDs each cycle, producing unique write
names. Verification checks the exact cumulative multiset of seeded and
acknowledged values, the committed DB/cache record and named-volume identity.
Queue and build cleanup run each cycle; persistent stack cleanup runs at the end.
A timed-out queue verifier retains its owned name for explicit cleanup.

Results preserve each activity's actual begin/end, exact job outputs, cumulative
rows, native resource phases, required process/start identity and loaded artifacts.
Image digests, diff IDs, application inputs and tools match the common portfolio.
The sampler includes setup, mixed work, verification and cleanup after a disclosed
boot warmup. API work has a 60-second deadline; child engine commands are bounded.
The entire pilot has no durable external deadline or saved supervisor exit receipt.

These are functional diagnostics. Concurrent tasks finish at different times;
recorded overlap does not imply uniform load throughout a cycle. The pilot does
not close the 12-hour reliability, resource-growth or performance gates. A frozen
candidate, durable finite supervisor and full resource acceptance remain required.
Legacy request-window/churn records are separate and cannot be pooled with v2.

A single-engine, unqualified duration diagnostic can be launched with
`python3.14 bench/native/mixed_job.py --job /absolute/path/under/.work/job
--duration 120 --engine ctrs --portfolio-layout /absolute/layout
--worker-layout /absolute/worker-layout --ctrs-binary /absolute/ctrs
--compose-plugin /absolute/docker-compose`. The job directory must be new and
its parent must already exist. The launcher records receipts for the sources,
fixture files, layouts, interpreter, Docker, Compose plugin, candidate and,
for ctrs, the selected guest assets. Supply any additional host executables or
assets with `--input`; the operator must ensure the specified Compose plugin is
actually selected. The supervisor rechecks receipts before execution. The raw
guest template uses an explicit sparse-extent content receipt; ordinary files
and packed templates use full SHA-256. Generated Python caches are excluded.

The finite work deadline stops admission of new cycles; an admitted cycle has
up to 900 seconds to drain. Another 900 seconds precedes the supervisor's hard
deadline for cleanup. A failed or unfinished cycle is a failed diagnostic, and
the supervisor's terminal status and cleanup result must be inspected. The
work interval includes setup; too short an interval can admit no cycles and
fails. The duration is limited to one hour and remains unqualified. Both entry
points refuse `--qualification`: a frozen candidate, assets, workload, final
matrix and a readiness evidence schema and proof are not available. The full
12-hour legs are not authorized by this diagnostic.
