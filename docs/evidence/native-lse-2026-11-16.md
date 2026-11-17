# LSE-only W2 experiment, 2026-11-16

**Decision: reject for promotion.** The bounded experiment did not meet the
predeclared advance guards. Keep the product kernel configuration unchanged and
move profiling to another boundary. This busy-host diagnostic does not establish
a qualified regression or speedup.

## Hypothesis and control

Prior stock profiles sampled the LL/SC task-reference decrement in `wake_up_q`.
Affinity diagnostics suggested a cross-vCPU cost. Test whether kernel LSE atomics
reduce that cost while preserving default application affinity.

Private branch `experiment/np-lse-only`, f7ea791, adds only
`CONFIG_ARM64_USE_LSE_ATOMICS=y`. Both kernels use the same 6.18.58 source,
patches and compiler in a single bounded build. Generated configurations differ
only in that option and its derived `CONFIG_ARM64_LSE_ATOMICS=y` symbol.
Compiler SHA-256 before and after is
`fb051a6c58961fb6aec758acf50d7d0375eecff740d0706388092829e3fb7a41`.

| Asset | SHA-256 | Bytes |
| --- | --- | ---: |
| Fresh stock Image | `e6a8cdb290e6bbcfeb92c810886312d4b42a2c4154041d37ba5f41128d920d54` | 18,800,648 |
| LSE-only Image | `6555028c558a8dbb786c758498f512320bae5403831f71337182902eefd8d7d2` | 19,324,936 |

The host binary remains 37bec61b…; initrd/template and pinned application inputs
are unchanged. Both variants use 17 vCPUs, 45,091MiB and inherited API affinity.
This fresh stock control is distinct from the earlier installed Image; histories
are not pooled. The build exits 0 with its labelled container stopped.

## Native result

Three balanced pairs complete all 12 profiler-off/on phases: 600,000 operations,
exact payload checks, zero workload/cleanup errors. Every phase verifies the
actual loaded kernel/initrd hashes and guest atomics advertisement. The full
kernel log confirms LSE disabled for stock and enabled for the candidate.
All 84 frozen input receipts remain unchanged after completion.

Primary screening values below use profiler-off phases. Ratios are candidate /
fresh stock for the same pair; lower favors the candidate. They are descriptive
diagnostics without qualified confidence intervals.

| Pair | Stock API CPU seconds | LSE API CPU seconds | API CPU ratio | Engine CPU ratio | Wall ratio | p99 ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 18.50 | 22.56 | 1.219 | 1.212 | 1.288 | 2.084 |
| 2 | 18.02 | 20.31 | 1.127 | 1.131 | 1.146 | 1.397 |
| 3 | 17.81 | 18.42 | 1.034 | 1.052 | 1.040 | 1.204 |

The preregistered screen required at least 10% API CPU and 5% engine CPU reduction,
with no greater than 3% wall/tail increase. No off phase meets those guards.
Profiler-on API CPU ratios are 1.012, 1.008 and 0.994; none shows the required
reduction. Raw `wake_up_q` leaves remain frequent: 353/2,589 stock samples and
419/2,597 LSE samples. Function-level leaves alone cannot identify exclusive-store
retries or prove where atomic latency arose. Do not spend idle/resource/full-build
confirmation on this weak candidate. Resource and qualification gates stay open.

The initial audit batch is retained separately: its first pair completed correct
work but failed the LSE feature check because serial capture omitted early boot
messages. Repair 09fb5a0 reads the bounded full kernel ring through non-clearing
syslog actions. The replacement batch preserves the runtime feature requirement;
it does not relabel or pool the failed audit. A separate 5k off/on OrbStack proof,
`w2-cpu-20261116T195011-94d2`, also passes full-log capture and exact data/cleanup.

## Reproduction and continuation

Build recipe, compiler/config receipts and private assets:
`.work/wt/np-lse-only/.work/kernel-lse/`. Native coordinator and complete raw
analysis: `.work/tmp/w2-lse-explore-v2-20261116/`. The coordinator uses the existing
`diagnostics/syscall_pilot.py` with `CTRS_GUEST_DIR` selecting each private asset
directory, alternates stock/LSE order, and stops on audit/workload failure.
The fixed three-pair plan and every phase's latency/CPU/profile values are retained.

Durable native job `7edd9d98fb3648d38b4750e8b955801d` exits 0, cleanup complete.
SHA-256 receipts:

- `job/status.json`: `30789f09b3d79f05cce0d9ae4f6baadcb3a44caf86e90b88ef3ca3ccbe322836`
- `analysis.json`: `b4a892d89a0015c187f63292315490349c7ce40cec9035362ad45aa86f3b3050`
- `plan.json`: `3585bf6b936e568c3c5eb6657d8eec749ac227b2d5047c11be1a8c483cb1a320`

Next experiment: compare the published host-port path with a distinct client
container on the Compose bridge using identical fixed work. Keep API-thread CPU
separate from engine CPU that includes the guest client. This tests another
boundary rather than repeating rejected kernel-policy guesses.
