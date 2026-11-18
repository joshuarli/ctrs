# Bounded mixed-cycle working state, 2026-11-17

Candidate83ba0d1 versions the mixed fixture as
`w11-v3-bounded-working-set`. The earlier v2 fixture retains all acknowledged
items and serializes the complete history after every cycle. Its verification
and evidence volume grow quadratically with completed cycles. This is a source
property, not a measured product slowdown or a leak diagnosis.

V3 keeps the same pinned API, PostgreSQL, Redis, queue-worker and Marked images.
Each cycle performs5000 API operations alongside200 queue jobs and16 real
build/test jobs. Every acknowledged item must exist with its exact payload
before cleanup. Duplicate, missing, corrupt or extra rows fail verification.
Explicit cleanup returns every deleted row for comparison with acknowledged
writes. The500 exact seed rows must remain afterward.

The committed `mixed-committed=exact-v3` database/cache witness and named volume
persist across cycles. Both are checked before and after transient-item cleanup.
Service and engine identities must remain unchanged. Final owned cleanup removes
the fixture. This policy measures a bounded retained working set with real
database deletion, rather than indefinite application-data accumulation.
PostgreSQL allocation may still grow. Resource budgets remain hard requirements.

Setup, concurrent work, verification, transient-data cleanup and final fixture
cleanup have separate CPU boundaries. The aggregate write count is an integer.
Each cycle retains its own exact-state evidence without rewriting older rows.
Historical v2 results stay separate. Recover v2 source with
`git show 83ba0d1^:bench/native/mixed_cycle.py` if needed for diagnostics.

Six focused mixed-cycle tests pass, zero skips. Negative controls reject missing,
duplicate and corrupt deleted rows, damaged seed state and retained transient
data. A two-cycle consumer check verifies bounded retained state and stable
service identities. Fault injection reproduces the earlier error-masking path:
sampler shutdown replaced the workload failure. The candidate retains both and
saves the failed result while propagating the original failure.

## Short native admission

The finite job is `.work/tmp/w11-v3-functional-20261117/job`, with a20-minute
deadline and frozen interpreter, source, layouts, signed binary and boot inputs.
It runs two cycles per engine:20,000 API operations,800 queue jobs,
51,200 queue events,1600 exact artifacts and64 build/test jobs in total.
The native ctrs root is new and disposable. The shared OrbStack daemon and
unrelated resources remain untouched. Reproduce using prepared pinned layouts:

```sh
CTRS_GUEST_DIR=/path/to/verified/guest-assets CTRS_CPUS=2 CTRS_MEMORY_MIB=8192 \
  TMPDIR=$PWD/.work/tmp python3.14 bench/native/diagnostics/mixed_pilot.py \
  --portfolio-layout .work/native-perf/inputs/w8-portfolio-v2/layout \
  --worker-layout .work/native-perf/inputs/w11-worker-v1/layout \
  --ctrs-binary .work/tmp/readiness-main-target/release/ctrs \
  --ctrs-root .work/tmp/new-short-mixed-root --cycles 2 --engines ctrs,orbstack
```

The runtime hashes and reconstruction recipe remain in the progress file.
The common portfolio and worker pins are validated before engine work.
This is functional evidence only. The foreign host workload prevents timing
qualification. No12-hour leg, frozen-candidate qualification, bounded-growth
verdict or durability improvement is inferred. Independent review and the
terminal native result are required before accepting this slice.

## Native outcome

Job `0a89d8f85f2145f4bb07488ec1ec824a` exits0 with complete local cleanup.
Results are `w11-mixed-20261117T105538-5e64`. Both engines complete both cycles.
Every cycle verifies1531 acknowledged writes, then explicitly deletes exactly
those1531 rows and verifies all500 seed rows. The committed database/cache
witness, named-volume identity, service IDs and running artifacts remain valid.
All20,000 API operations,800 queue jobs,1600 artifacts and64 build/test jobs pass.
Both periodic traces have complete owned CPU/physical coverage with no resource
errors. All172 frozen input receipts recheck before the next source edit.

The loaded signed host has the accepted db20b210 hash. The booted kernel and
initrd match35087713 and6ae4d3ab respectively. Parent verifies that the private
daemon and VM identities are gone and its files have no open consumers.
The disposable `m3-20261117` store is removed, preserving all source and results.
Its allocated-size sum was2,046,116KiB, not a unique APFS reclamation measurement.

Independent reviewer `usrw_cdfedc1d-409f-4980-a6cc-257913f60d51` reviews83ba0d1
and relevant callers read-only. It reports no demonstrated defect and passes
the six mixed-cycle tests, zero skips. Its completed checkout is retired.

Parent subsequently reproduces one existing producer/consumer mismatch: the
mixed record's empty correctness-check map makes the reporter reject completed
work.9310dbc publishes completed-cycle exact-state and bounded-retention checks.
The actual reporter consumer fails before that metadata correction and passes
afterward. The corrected W2 component gate passes105 tests, zero skips.
The native proof above covers83ba0d1's workload behavior. The later metadata
change has focused consumer verification, not another native run. Original raw
records stay unchanged and retain their historical reporting limitation.

Result SHA-256 receipts are
`fcd35a47803a007c347f7dacf31ee4c64e2d0b7723cfbf395606b6f810bc1d26`
for ctrs and
`52debc5a4e9947de616bdc809125c2a3d42ca2f2192c4c8c87ef44c7663164ad`
for OrbStack. The bounded working-state slice is accepted. W11 resource-growth
accounting, frozen readiness and the12-hour legs remain open.


## W11 v4 post-cleanup observations

Job `a9856e75b2144596af2c5415301eee49` exited 0 using parked
`campaign/w11-required-cells-20261117` at `8aa9b65`. Both engines
completed two exact mixed cycles. Across both engines the trial verified
20,000 API operations, 800 queue jobs, 1,600 artifacts and 64 build/test jobs.
Every cycle kept the 500 seed rows, committed witness and named-volume identity.
Both resource traces have v4 ownership and complete CPU counters. All 181
frozen receipts rechecked unchanged. The ctrs ownership receipt confirms the
accepted loaded kernel and initramfs.

Each cycle recorded a 30-second post-cleanup interval. All four process
footprint and file-descriptor observations were valid. Both ctrs private
disk allocation observations were valid. OrbStack allocated bytes remained
unknown because the job supplied no identified open backing file. Two cycles
leave the five post-warmup observations required for a resource-growth
verdict unsatisfied. The proof does not close either 12-hour leg.

The separate readiness correction `0c0e10a` rejects declarations that place
W11 correctness, persistence, durability, growth or reliability solely in
other workloads. The new counterexample was admitted by `5bcf48a` and
rejected after the correction. All 12 readiness tests pass. The branch stays
parked pending the complete cell contract and actual frozen qualification inputs.

Reproduce from `8aa9b65` with the short native command above, absolute paths
to the prepared layouts and binary, and `--resource-observation-seconds 30`.
Use a new private ctrs root. The versioned observer keeps the v3 functional
records separate. Raw run ID is `w11-mixed-20261117T134730-e2bd`.
Trial receipt SHA-256
`4bae89bb68c67b49f3bb6b96c8eccecda445dfbd4aacf7e74b97dbe1b0dc84ff`.
Job status SHA-256
`bebd27db56322dd26c657fbbe7cad6f4e2892b735d843321556f2fb96164c39b`.


## Qualification evidence binding

Parked `campaign/w11-bind-completed-cycles` at `5ae0da9` binds one
resource observation to each completed, indexed cycle and its phase
clocks. The producer records the monotonic work-loop exit before
cleanup. Qualification checks the 12-hour deadline against that
clock. The observer and mixed-work phase rows must be ordered.

Eleven malformed records passed the previous gate and fail the
regression after `4d2e88c`. Both archived native v4 records agree
with the new cycle and phase structure. The short records still fail
the growth and duration criteria. Commit `5ae0da9` also rejects a
changed cell contract with a freshly matching review unless the
canonical SHA-256 matches `freeze.cell_contract_sha256` in
`assets.lock`. Compute the digest from sorted, compact JSON using
the same serialization as the readiness validator. An independent
review checked both changes and the producer's phase order.

In the parked checkout, run `PYTHONPATH=bench/native python3.14 -m unittest
test_qualification test_mixed_cycle test_mixed_resources`. All 26
tests pass. The actual asset lock remains a pilot. A complete frozen
cell contract and both native qualification legs remain open.

## Complete workload counts

Parked `campaign/w11-bind-completed-cycles` at `d82e3db` now requires every
cycle to report 5,000 successful API operations, 200 queue jobs, 12,800 queue
events, 400 exact artifacts and 16 build/test jobs. Queue totals come from
the verified W4 runner and the expected build count comes from the W9 job
specification. The earlier gate admitted all 12 counterexamples with a
missing, zero or boolean queue, event, artifact or build count. The updated
gate rejects each with the cycle index and field. Both archived native v4
records pass the resulting count and phase checks for all four cycles.

From the parked checkout, run `PYTHONPATH=bench/native python3.14 -m unittest
test_qualification test_mixed_cycle test_mixed_resources test_w4
test_w4_lifecycle test_ci_jobs`. All 43 tests passed without starting an engine.

## W11 cell plan

Use `w11-v4-post-cleanup-resources` with a warm persistent stack, a four-worker
queue and build concurrency four. `bench/native/w11-cells.json` on
`campaign/w11-bind-completed-cycles` defines the seven cells below in the
readiness validator's format. The admissions review must still account
for the rest of the W1–W11 matrix.

| Dimension | Metric and required evidence |
| --- | --- |
| Correctness | Zero incomplete or incorrect mixed cycles. Each cycle verifies the complete workload counts and exact outputs. |
| Persistence | Zero losses or changes to the 500 seed rows, the committed database/cache witness or the named volume identity across cycles. |
| Durability | Zero lost acknowledged durable writes under the comparable failure model declared at freeze. The short retention proof leaves this cell unmeasured. |
| Resource growth | Separate post-cleanup cells for physical footprint, file descriptors and active backing-file allocation. Use one baseline cycle and at least five subsequent observations of at least 30 seconds each. Their respective growth and return budgets are 16 MiB, 16 descriptors and 16 MiB. OrbStack allocation needs a stable backing-file scope verified against owned open descriptors. |
| Reliability | At least 12 hours of mixed-cycle exposure per engine with zero unexplained deaths or unexpected errors, exact durable data and passing resource-growth cells. |

## Finite frozen launcher

Parked revision `f41ba83` checks the seven W11 cells before admission and
requires the matrix to name each one. The growth cells have distinct identities
for footprint, descriptor count and allocated bytes. The launcher and child
validate the same declared artifacts, pinned tools and workload inputs. The
launcher passes the readiness receipt to the finite supervisor, which checks it
before starting the child. The child rechecks readiness after the work.

From the parked checkout, run the focused offline checks:

```sh
PYTHONPATH=bench/native python3.14 -m unittest \
  test_mixed_job test_qualification test_mixed_cycle test_mixed_resources test_durable_job
```

All 45 tests passed. They exercise the supervisor handoff and rejection before
launch when readiness fails. A native 12-hour leg still needs frozen assets,
the full reviewed matrix, comparable durability evidence and an admissible
host window. For OrbStack, identify and verify each owned backing file before
admission. The launcher takes one engine per invocation and adds separate drain
and cleanup deadlines. Example for the eventual ctrs leg, with 30 minutes of
setup allowance in the work cutoff:

```sh
python3.14 bench/native/mixed_job.py --qualification --readiness "$READINESS" \
  --job "$JOB" --duration 45000 --engine ctrs --ctrs-binary "$CTRS_BINARY" \
  --portfolio-layout "$PORTFOLIO_LAYOUT" --worker-layout "$WORKER_LAYOUT" \
  --compose-plugin "$COMPOSE_PLUGIN"
```

Use the configured `CTRS_GUEST_DIR` and keep the job directory short enough for
its private Unix socket. For OrbStack, choose `--engine orbstack` and repeat
`--orbstack-storage-file` for the covered backing files. Admit each leg with
its own fresh host-conditions review and a new job directory.

## Qualification coverage

Parked `campaign/w11-bind-completed-cycles` at `c068fba` adds 342 mandatory
W1–W10 cell identities in `bench/native/qualification-cells.json`. Together
with `bench/native/w11-cells.json`, the admission gate requires 349 cells.
Each identity specifies a workload, state, load, metric, dimension and unit.
Use the actual pinned fixture version in each readiness cell. Keep additions
such as extra offered-rate levels in the same reviewed, hashed contract. The
status matrix must cover every identity. Set unsupported or unrun conditions
to `unmeasured` and retain any evidence about why they remain open.

| Workload | Evidence still needed before the review can freeze the contract |
| --- | --- |
| W1 | Equivalent engine-cold setup on both engines and verified read/write after restart. |
| W2 | Pinned offered rates and full published-port and container-to-container coverage. Admit the observer and resource-cycle policy on the same workloads. |
| W3 | Per-transaction p95, exact persisted rows and a comparable durability contract. |
| W4 | Queue latency tails for 1, 4 and 16 workers with exact job and artifact verification. |
| W5 | Paired bind and named-volume conditions with pinned inputs and phase resource receipts. |
| W6 | Warm build-cache runs and proof of compilation in uncached runs. Both artifact hashes are pinned. |
| W7 | Buildx import and first-use evidence for both apps and all three cache states. |
| W8 | Retained and derived deployment, cancellation and owned allocation in both engines. |
| W9 | Individual job completion times and fixed work at all four concurrency levels. |
| W10 | Extend the API interruption proof to the database, queue and owned engine recovery conditions. Keep expected outage errors visible. |
| W11 | Comparable durable-write evidence, owned storage scope and each finite 12-hour leg. |

The tests remove individual W2, W6, W8 and W10 cells while leaving the workload
and dimension represented elsewhere. Admission rejects each omission. The
focused command above passes 46 tests on `c068fba`. The readiness lock remains
in pilot status. The inventory can expose missing evidence and producers
before the host is available for qualification.

## Qualification branch refresh

Merge `3d3f3fb` brings main through `90491bf` into
`campaign/w11-bind-completed-cycles`. It retains the interleaved W2
observer controls and the current W4 timing fixture. Qualification keeps
the pinned W11 worker and requires receipts for the shared runner's
fixed-rate W2 and W4 timing imports.

Run `python3.14 bench/native/runner.py check w11` from the parked checkout.
All 47 tests passed with zero skips. The check covers qualification
admission, mixed cycles, resource observations, and the finite
supervisor. The pilot asset status still prevents qualification launch.

The next refresh brings main through `a06632d` into the parked branch.
Admission now requires the workload fixture versions declared in
`cases.toml`. W2 offered-rate and W8 cancelled-delivery cells require
their own producer versions. A stale version fails even when every
cell for that workload repeats it. The required input list also includes
the W5 mounted-input probe.

The refreshed W11 component check passed 49 tests with zero skips.
The adjacent runner, reporting, W1, W5, W9 and registry checks passed
81 tests. The 349-cell contract still requires a reviewed asset lock
and comparison evidence before either long leg can launch.
