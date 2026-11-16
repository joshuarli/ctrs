# macOS performance campaign: progress and continuation

**ACTIVE — resumed from reviewed 94f19a8. Native ARM64 macOS only.**
[Contract](campaign-native-performance.md). One coordinator owns Mac runs.
This is the single queue. Historical results and rejected hypotheses live in
[evidence](evidence/native-performance.md). No new product win is qualified.

## Current checkpoint

- Native sampler v3 uses actual ri_phys_footprint, Mach-converted CPU, wake
  counters and kernel start identity. Required daemon/VM ownership comes from
  socket and dedicated disk, with actual open binary/boot hashes. Missing VM
  counters invalidate the cell. Native on/off calibration passed the declared
  median budgets on both engines; individual pairs remain noisy.
- W2 v2 supports equal fixed work, validated successful reads/writes and exact
  persisted payloads. CPU/success comes directly from workload-phase counters.
  Saturation remains separate. The 50k five-pair batch was contaminated and
  excluded from scoring. Actual-API profiles implicate wake/scheduling cost.
  Matched placement removes most system-CPU excess. Identical pinned futex
  controls reproduce ~0.4us same CPU and ~6us distinct CPUs on BOTH engines.
  The old unpinned contrast does not demonstrate a VZ wake ceiling.
- CONFIG_SCHED_MC-only candidate was rejected after three correct paired W2
  pilots: API CPU ~neutral, host CPU ~2% higher, no predicted benefit. Stock
  retained. `.work/wt/np-sched-mc` holds compiler-matched baseline/candidate
  assets under `.work/kernel-mc`; do not deploy the rejected kernel.
- W4 v2 real ingest/Redis/workers/artifact flow passed both engines at 1/4/16
  workers, exact 12,800 events and 400 artifacts per condition. Inputs enforced.
- W5 v2 Marked TypeScript persistent watch/rebuild/CLI test passed integrated
  runner pilots on both engines, fresh bind and volume sources, four edits
  each. Exact outputs, unchanged PID/start identity, owned cleanup and complete
  setup/edit/cleanup counters. Run `w5-v2-runner-20261116T004333`. Same exported
  image on both engines. Functional coverage only; final workload not frozen.
- W8 selected-engine preparation preserves the other valid section atomically.
  Identical multilayer independent-registry acceptance is still pending.
- Resource primitives validate complete intervals, numerical budgets, peak
  cleanup growth and actual explicit-file allocation. Exclusive APFS allocation
  remains unknown. Full idle/reclaim/storage/growth acceptance is not integrated.
- Successful default build-driver behavior and W6/W7 wins are preserved.
  Frozen-candidate confirmation and known correctness debt remain required.

## Active work and exact next action

W10 refusal-cache instrumentation is reviewed and copied to main, uncommitted.
Two focused cache tests pass, preserving 250ms TTL/capacity behavior. Isolated
release build `.work/tmp/w10-target/release/ctrs` succeeded (exec83402 terminal).
Next: ad-hoc sign with `crates/ctrs/ctrs.entitlements`, boot only the owned warm
ctrs root with CTRS_LOG=debug, then trace restart begin/return, process/readiness,
published port, first success and cache/refusal/retry events on both engines.
Do not replace the live default binary or change cache policy before attribution.

Independent source-only W8 lane `.work/wt/np-w8-v2`, branch campaign/np-w8-v2,
base7cc2c5bee01b86b47173b60e00279b49431b9b2f. Bridge session
usrw_33359635-6dd3-4277-b443-f540defbef7c, watch exec7404. It owns only
fixtures/w8-v2, registry_portfolio.py and its test. No engine/server/build work.
Inspect terminal status and source once; parent owns integration/runtime proof.

Regression: `TMPDIR=$PWD/.work/tmp python3.14 -m unittest discover -s bench/native -p 'test_*.py'`.
W5 source tree `.work/wt/np-w5` and W4/resource trees retain worker provenance.
Retire only after final integration proof. No measured Mac job is active.

## Ordered queue

1. Finish W10 trace and select a targeted recovery change from the evidence.
   Preserve command cost, exact committed data and expected/unexpected errors.
2. W2: isolated per-TID sched waking/wakeup/switch tracing and scheduler-domain
   inspection. Separate on-CPU cost from wait/wake latency. Add discriminating
   vCPU/load controls without reconfiguring shared OrbStack. Obtain independent
   review or change boundary after three neutral hypotheses. No speculative VMM.
3. Integrate idle CPU/wakes, steady/peak footprint, post-load reclaim/next-use,
   actual allocated storage before/after/cleanup, and repeated-cycle growth.
   Predeclare absolute and ratio budgets. Unknown cache/allocation stays unknown.
4. Complete W8 common portfolio/independent registry, W9 fixed real build/test
   jobs and W11 service/database/queue/build/cleanup activity. Version fixtures
   and baselines. Never pool proxy history or call ten pilots frozen acceptance.
5. Disposable-state disk expansion/migration preserving named-volume contents
   and identity. Audit Cached+Fsync, guest flush and supported failure guarantees.
   Separate authoritative volumes from caches. No power-loss claim from restart.
6. Resolve known correctness failures. Freeze candidate and complete per-cell
   status matrix only after fixtures/resources/durability gates exist. Run
   affected confirmations, then full paired qualification, independent batch,
   fresh held-out app and durable finite 12-hour W11 per engine.

Before scored work inventory/stop only verified campaign-owned diagnostics and
confirm exclusivity. Leave user workloads alone and invalidate contamination.
Installed-default, resource-matched default-driver and identical-builder controls
stay separate. Report wins/parity/losses/inconclusive/invalid/unmeasured explicitly.
No geometric mean may hide resource, recovery, durability or tail-latency losses.
Continue until demonstrated gates, owner stop or a blocker of all authorized work.
