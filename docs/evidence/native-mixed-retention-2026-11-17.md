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
