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
- W2 resource-cycle pilot now integrates complete idle CPU/wakes, sampled
  steady/peak footprint, reclamation/next use, explicit active-disk allocation
  before/after work and cleanup, and post-warmup growth. Numerical budgets
  predeclared. Short both-engine pilots pass exact data/counter coverage;
  timings invalid under foreign Niceforge/fz work. Final acceptance remains
  open: five-cycle/30s design, interleaving, freeze and exclusivity. Exclusive
  APFS allocation and build-cache size stay unknown.
- Successful default build-driver behavior and W6/W7 wins are preserved.
  Frozen-candidate confirmation and known correctness debt remain required.

## Active work and exact next action

W10 hooks and traces are landed at 579dbeb, keeping 250ms TTL. Source now
preserves host errno, failure validation, run identity/timeline and separate
healthy/outage/post CPU boundaries. All 93 harness regressions pass.
Final baseline-only functional pilot `w10-trace-20261116T011249` passes. Timings
are invalid because saved gate diagnostics show unrelated hot host work.

50ms candidate is PARKED, not selected. Diagnostic three-pair gains are invalid
for timing, as is confirmation `w10-ttl-confirm-20261116T010356`: gate exit0
only checks aggregate load while logs show hot Niceforge/Tailscale work. Stress
pair9 candidate additionally failed with 149 host EADDRNOTAVAIL errors and
unexpected timeouts; exact committed data survived. Original and annotated
records retained, no failed pair omitted. Idle CPU/wake verdict also invalid;
actual footprint/counter coverage remains complete. Do not retry to green.
Candidate saved at local branch campaign/np-refusal-ttl, commit54c6a00; clean
worktree `.work/wt/np-refusal-ttl` retired. Recreate from that branch only when
retry conditions hold. Isolated
binaries `.work/tmp/w10-{target,candidate-target}/release/ctrs`, hashes/plans
under `w10-ttl-confirm-20261116T010356`. Revisit only after bounded versioned
client protocol and an exclusive host window. Preserve 250ms default.

W2 scheduler adapter/parser now works on both guests: run
`w2-scheduler-20261116T015213`, exact 2k operations and persisted data, stable
namespace/global TID joins, complete closed off-CPU cycle coverage. Overlapping
waking-before-switch-out is handled explicitly. Scheduled/wake elapsed time is
not mislabeled CPU. Task CPU uses every required thread and actual clock ticks;
short-run quantization bound is explicit. SIGTERM cleanup proof014803 passes.
Runtime code/interpreter/libc/package fingerprints match (reconcile014544).
All timing remains unqualified: busy host and profiler overhead not calibrated.

Next W2 action: low-overhead tagged wake/futex/network syscall counts and
on/off controls, then 50k aligned actual-API tracing in an exclusive window.
Executable: `TMPDIR=$PWD/.work/tmp python3.14 bench/native/diagnostics/scheduler_pilot.py --tools-archive .work/tmp/w2-profile/native-tools.tar.gz`.
Do not choose a kernel/backend candidate from the short traced counts.
The detailed profiling boundary is `.work/tmp/w2-scheduler-trace-plan.md`.

Persistent mount data-loss guard landed at3fa2f01. Baseline owned repro
`disk-mount-bad-2243934f` fsyncs a volume on tmpfs after an ext4 error, then loses
the exact bytes across VM restart with unchanged volume identity. The fix aborts
before serving the agent. New native proofs `disk-guard-c5651b1d` and earlier
fb537399 reject invalid media without changing its SHA/identity, and preserve
exact ext4 bytes plus named-volume metadata through old→new guest upgrade and
new→new restart. No data/wire format or Fsync policy change. All103 harness
tests pass, including cleanup-before-original-signal-death regression.

The tested initramfs eb0ef32667a4d0560d23482cab670f0fa7693bbd013b0484d27fb1d349cf42c7
is atomically published at guest/out after no open users were found. Kernel
unchanged; no daemon restarted. Variants preserved under
`.work/native-perf/guest-variants/{mount-guard,pre-mount-guard}`. The historical
fallback baseline is diagnostic-only, unsafe for new qualification. Proof command:
`TMPDIR=$PWD/.work/tmp python3.14 bench/native/diagnostics/disk_mount_pilot.py --candidate-guest-dir guest/out --baseline-guest-dir .work/native-perf/guest-variants/pre-mount-guard --proof-binary .work/tmp/disk-mount-proof/proof`.

Resource pilot implemented: `w2-resources-20261116T041130` has 10 exact trials,
5,200 operations and30 complete phases on both engines; follow-up041443 confirms
allocation snapshots outside phase CPU and preserves source copies/hashes.
041549 confirms full-work warmup on ctrs. All 110 regressions pass. Short windows
and foreign jobs mean no resource/timing acceptance. Actual guard guest identity
was measured. Read `bench/native/diagnostics/resources.md` for predeclared budgets.
Command: `TMPDIR=$PWD/.work/tmp python3.14 bench/native/diagnostics/resource_pilot.py --orbstack-storage-file '/Users/josh/Library/Group Containers/HUAQ24HBR6.dev.orbstack/data/data.img.raw' --orbstack-storage-file '/Users/josh/Library/Group Containers/HUAQ24HBR6.dev.orbstack/data/swap.img'`.
Do not compare aged absolute disk sizes or call shared extents exclusive.
The two completed mount-guard worktrees were retired; variants/review preserved.

W10 client v2 is implemented and baseline-verified on both engines in
`w10-trace-20261116T041907`. Per-worker persistent HTTP, no hidden retry,
200ms timeout, bounded workers/pairs, connect/open/reuse counts and native errno.
Exact committed DB/cache state survives; no unexpected or host-address errors.
Each engine has ten successful-request connection opens across restart; other
successful requests reuse sockets. Outage failures remain visible. Timings still
invalid due unrelated Niceforge/fz jobs. All 112 regressions pass. Product TTL 250ms
unchanged, 50ms candidate still parked. Read diagnostics/recovery-client.md before
future trials; do not pool old fresh-connection and v2 records.

Next executable source task while timing is unavailable: finish W8 common
portfolio production/state/healthy-deployment proof in the existing np-w8-v2
worktree. Inspect its retained file-backed registry slice before integrating.
No duplicate worker. Coordinator owns any runtime preparation. W2 low-overhead
on/off profiling and resource confirmation need an exclusive host window; source
flush-path/Full synchronization and disposable expansion audit remain ready.

Independent source-only W8 lane `.work/wt/np-w8-v2`, branch campaign/np-w8-v2,
base7cc2c5bee01b86b47173b60e00279b49431b9b2f. Bridge session
usrw_33359635-6dd3-4277-b443-f540defbef7c, watch exec7404. It owns only
fixtures/w8-v2, registry_portfolio.py and its test. No engine/server/build work.
Worker is terminal incomplete (watch7404). It delivered only layout validation
and pull-only server scaffolding with three mocked HTTP tests; portfolio/state/
health integration remains absent. Review before accepting any narrow sub-slice.
Parent added file-backed streaming/mutation and real loopback tests (4 pass).
No common portfolio/state/health integration. Parent owns runtime proof. No duplicate worker.

Regression: `TMPDIR=$PWD/.work/tmp python3.14 -m unittest discover -s bench/native -p 'test_*.py'`.
W5 source tree `.work/wt/np-w5` and W4/resource trees retain worker provenance.
Retire only after final integration proof. No measured Mac job is active.

## Ordered queue

1. Finish resource qualification design: interleave the integrated W2 resource
   pilot, freeze inputs, obtain an exclusive host window and collect declared
   five-cycle/30s minima. Unknown cache/exclusive allocation stays unknown.
   Do source work below while foreign host jobs prevent valid timing.
2. W2: low-overhead wake/syscall counts and profiler on/off controls, then clean
   50k application profiles with task CPU and off-CPU waits kept separate. Add
   vCPU/load controls without reconfiguring shared OrbStack. No speculative VMM.
3. Complete W8 common portfolio/independent registry, W9 fixed real build/test
   jobs and W11 service/database/queue/build/cleanup activity. Version fixtures
   and baselines. Never pool proxy history or call ten pilots frozen acceptance.
4. Disposable-state disk expansion/migration preserving named-volume contents
   and identity. Audit Cached+Fsync, guest flush and supported failure guarantees.
   Separate authoritative volumes from caches. No power-loss claim from restart.
5. Revisit parked W10 only after a bounded versioned client protocol and an
   exclusive window. Retain command cost, exact committed data and full errors.
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
