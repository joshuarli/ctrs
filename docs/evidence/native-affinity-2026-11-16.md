# Native W2 affinity diagnostic, 2026-11-16

The fixed nine-block experiment completed successfully. All 36 engine/mode
phases verified 50,000 operations, including 35,159 reads and 14,841 writes,
exact persisted payloads and owned cleanup: 1.8 million total operations,
zero workload/cleanup errors. All API threads had their effective affinity
checked at warm, phase-before and phase-after boundaries. All 81 frozen
input receipts remained unchanged after completion.

This is exploratory mechanism evidence. **Every timing and qualification cell
is ineligible.** Unrelated host/OrbStack work remained active; the last round
had particularly large contention. Whole-OrbStack CPU includes unrelated work
and cannot establish engine efficiency. Observer overhead is unqualified.

## Question and design

The stock profile had excess leaves at the task-reference decrement inside
`wake_up_q`. Does co-locating the actual API threads reduce its cross-vCPU
cost? This changes application scheduling solely for diagnosis; it selects
neither a product affinity policy nor a kernel configuration.

Three rounds rotate default/all, CPU0 and CPU0,1. Every block runs both engines
and profiler off/on, alternating engine/mode order. Source, pinned ARM64
application images, fixed work and guest assets remain identical. Explicit CPU
sets have separate fixture/profile identities and are not pooled with defaults.
The plan fixes nine blocks and stops on a failure without replacement.

Application CPU seconds from the **profiler-off** phases, in round order:

| API affinity | ctrs round 1 | round 2 | round 3 | OrbStack round 1 | round 2 | round 3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| inherited/all | 26.41 | 19.30 | 25.19 | 15.98 | 15.03 | 19.75 |
| CPU0 | 13.23 | 12.44 | 21.19 | 15.75 | 13.92 | 20.71 |
| CPU0,1 | 18.70 | 17.18 | 16.00 | 17.70 | 13.99 | 14.32 |

All three ctrs round contrasts point toward lower application CPU with fewer
API CPUs. Workload order and changing contention prevent attributing the entire
difference to affinity. The last-round variability is retained, not discarded.

Decoded profiler-on leaf observations, summed across the three blocks per set:

| API affinity | ctrs `wake_up_q` leaves / samples | OrbStack leaves / samples |
| --- | ---: | ---: |
| inherited/all | 418 / 3,422 | 69 / 2,022 |
| CPU0 | 22 / 2,556 | 12 / 2,395 |
| CPU0,1 | 179 / 2,484 | 46 / 2,149 |

These counts support investigating the atomic/wake boundary. They do not prove
exclusive-store retry counts, instruction latency or a qualified causal CPU
cost. No kernel probe was inserted inside the LL/SC reservation sequence.

## Reproduction and receipts

Source: 05a2db8, analyzer repair 2756b7f. A single block is:

```sh
TMPDIR=$PWD/.work/tmp python3.14 bench/native/diagnostics/syscall_pilot.py \
  --tools-archive .work/tmp/w2-profile/native-tools.tar.gz \
  --image-refs .work/native-perf/results/w11-mixed-20261116T063716-8565/ctrs-host/refs.json \
  --ctrs-binary .work/tmp/disk-expand-target/release/ctrs \
  --operations 50000 --profile-kind cpu --mode-order off,on \
  --engines ctrs,orbstack --api-cpus 0
```

Omit `--api-cpus` for inherited affinity; use `0,1` for two CPUs. Reverse
mode/engine orders on alternate blocks. The saved coordinator freezes the full
rotation and performs no substitution after a failure.

Baseline host SHA-256:
`37bec61b01dd61470e41176b1830115b81bf29c32c387881ad3d00f53d32f2e5`.
Loaded Image:
`35087713fd7b1b152b1ac0333e42edbcee482c82c6e695f27a8f126c271eee43`.
Initrd:
`71934e6d8e654d430f270d921d777ef54b4fd11462b6240c6cff4518372609c1`.

Coordinator, plan, frozen receipts, raw block outputs and complete analysis:
`.work/tmp/w2-affinity-explore-20261116/`. Durable job
`1e855e77f2ed4713ad5a714e3d0e28a7` exits 0 with cleanup complete.
SHA-256 receipts:

- `job/status.json`: `f9f107272b8f81d51615f8b5419008230c3ce8c10d252e794f3921a42b4e931b`
- `analysis.json`: `3479d043348bac482785babfc2fa69f1ee7fab15309e48ee0f94df2912007194`
- `plan.json`: `268476823e325edd564659ea032d561ec5447bd529dcfa6b2e0ae0823c145a7c`

The initial stock exploratory block `w2-cpu-20261116T185652-c15a` failed because
the old analyzer mistook `blkcg_maybe_throttle_current` for a perf diagnostic.
Its original failed receipt remains intact. Companion reanalysis at 2756b7f
passes raw/decoded event coverage. It is excluded from this nine-block batch.

## Next experiment

Prepare same-toolchain stock/LSE-only kernels in private assets, then compare
default-affinity fixed work in three balanced pairs. Keep it exploratory and
unpromoted. Owner-requested additional experiments do not waive exclusive
observer confirmation, idle/wake/reclaim, parallel-build, durability or full
qualification gates. No kernel configuration or application affinity policy
has been merged into the product from these observations.
