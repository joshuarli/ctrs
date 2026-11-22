# Run short mixed application cycles

Use the pinned W8 multilayer portfolio and worker OCI layout. The worker archive
is a read-only export of the verified W4 image. `worker-pin.json` records its
manifest, config, diff IDs and application hash. Preparation preserves both
engines' existing images and shared daemons.

If scratch was deleted, `worker-pin.json` retains the exact `source_image_id`.
Export that image from the shared store under a new owned tag whose suffix is
the recorded `layout_reference`. Extract its OCI archive with the data filter.
`registry_portfolio.prepare_layout(layout, {repository: layout_reference})` must
recover the pinned worker manifest, config and DiffIDs before a run. Missing
source bytes remain a preparation blocker or require a new version and baselines.

```sh
TMPDIR=$PWD/.work/tmp CTRS_CPUS=2 CTRS_MEMORY_MIB=4096 \
python3.14 bench/native/diagnostics/mixed_pilot.py \
  --portfolio-layout .work/native-perf/inputs/w8-portfolio-v6/layout \
  --worker-layout .work/native-perf/inputs/w11-worker-v1/layout \
  --ctrs-binary .work/tmp/disk-expand-target/release/ctrs --cycles 2
```

The pilot accepts one to three cycles. Each cycle starts three activities:

- 5,000 fixed API operations with four persistent HTTP clients and 30% writes.
- 200 real queue jobs, four workers, 12,800 events and 400 exact artifacts.
- 16 real Marked TypeScript build and CLI-test jobs at concurrency four.

The API, PostgreSQL and Redis containers persist across cycles. The unchanged
pinned W2 client uses disjoint worker IDs each cycle, producing unique write
names. The current v3 fixture verifies every acknowledged value before explicit
transient-item deletion, then checks all500 exact seed rows remain. The committed
DB/cache witness and named-volume identity persist across cycles. Queue and build
cleanup run each cycle; persistent stack cleanup runs at the end. Historical
cumulative v2 results remain separate.
A timed-out queue verifier retains its owned name for explicit cleanup.

Results preserve each activity's actual begin/end, exact job outputs, cumulative
counts, per-cycle exact rows, native resource phases, required process/start identity and loaded artifacts.
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
The running VM's actual open kernel/initrd identities must match the launcher's
frozen boot assets, including when an existing daemon is adopted.

The finite work deadline stops admission of new cycles; an admitted cycle has
up to 900 seconds to drain. Another 900 seconds precedes the supervisor's hard
deadline for cleanup. A failed or unfinished cycle is a failed diagnostic, and
the supervisor's terminal status and cleanup result must be inspected. The
queue/build cleanup commands use that separate cleanup budget after drain
expiry. Interruption grants the child up to 900 seconds, bounded by the hard
deadline, to remove Docker fixtures before process-group KILL. Local group
quiescence alone does not establish remote fixture cleanup; inspect workload
results and ownership receipts as well. A hard deadline can leave remote
fixtures requiring explicit owned cleanup and can never qualify reliability.
The work interval includes setup. A diagnostic that admits no cycles fails.
The diagnostic duration is limited to fifteen minutes.

For qualification, `mixed_job.py --qualification --readiness <reviewed-json>`
validates the frozen readiness declaration and `assets.lock` before launching
one engine. Set `CTRS_GUEST_DIR` to the frozen boot directory and provide a
duration covering setup plus twelve hours of work. The OrbStack leg also
requires explicit `--orbstack-storage-file` arguments for the owned backing
files used for allocation accounting. The [campaign admission
requirements](../../../../docs/campaign-native-performance.md#finite-reliability-jobs-and-continuation)
apply to both legs.
