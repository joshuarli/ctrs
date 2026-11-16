# macOS performance campaign: progress and continuation

**ACTIVE — resumed from reviewed 94f19a8.** Native ARM64 macOS only.
Contract: [campaign-native-performance.md](campaign-native-performance.md).
One coordinator owns measured Mac runs; this is the single current queue.
Historical checkpoints and superseded claims are in
[evidence/native-performance.md](evidence/native-performance.md).

## Current slice and exact continuation

Bounded collector/scoring repair is in progress. Strict fields reject category
fallback and incomplete counters. Socket/dedicated disk ownership and PID/start
identity are verified. Open executable/guest inode and mtime checks reject
changed artifacts; build-output hashes are separately labeled. Explicit W2
setup/workload/cleanup CPU boundaries and terminal footprint preservation are
implemented. 58 offline tests pass.

Owned ctrs daemon/VM restarted without replacing disk or deleting state; all
86 volume names survived. This checks identities, not contents/durability.
Raw restart inventory: `.work/native-perf/results/ownership-restart/`.
Short W2 collection pilot `run-20261115T220707-31a0` passed: 7,753 successful
requests, zero errors, exact item count 2,799; 34 CPU ticks, complete footprint,
no resource errors. CPU phase totals setup/workload/cleanup 0.88/5.55/0.09 s.
Pre/post perf-gate-ready passed. This is a collection/phase pilot, not an engine
comparison or overhead acceptance. CPU ps resolution is 0.01 s; per-boundary
collection takes ~37 ms and is explicitly recorded outside operation wall time.

Next executable action: sampler-on/off calibration with a prepared W2 stack,
3 alternating pairs, same duration/concurrency/seed, recording raw successful
work and CPU phase cost in both modes; predeclare acceptable median throughput
impact <=3% and CPU/operation inflation <=5%, otherwise reduce observer work.
Run pre/post perf-gate-ready. Keep reported total sampled CPU separate from
W2 workload-phase CPU. Then implement fixed-work W2, exact persisted payload
checks, per-success raw normalization and saturation as a separate mode; obtain
clean cgroup deltas and causal application profile before selecting candidates.

Independent W4 fixture worker owns `.work/wt/np-w4` on `campaign/np-w4`, base
0f5724f. Bridge session `usrw_6b9afa4c-6459-4baa-b303-25dc5df1b657`;
watch exec session 17037. Worker succeeded with offline checks. Parent review
found the output is still tiny synthetic hash artifacts; it needs representative
content processing and durable artifact outputs before acceptance integration.
Keep this tree parked pending that correction; it is not W4 coverage. Integration worktree is the repo root on main.

Regression command: `TMPDIR=$PWD/.work/tmp python3.14 -m unittest discover -s
bench/native -p 'test_*.py'` (join the wrapped command).

## Ordered queue

1. Finish measurement repair: verified process/start ownership, actual running
   executable and boot guest provenance, fast explicit phase boundaries,
   complete counters, short-trial behavior and clean Mac overhead calibration.
   Inventory diagnostic containers by verified ownership; remove only owned
   diagnostic workloads. Disclose/reschedule unrelated host contamination.
2. W2 v2: successful read/write counts and exact persisted state; fixed work
   or fixed offered load separately from saturation. Compute CPU per successful
   operation directly from each paired raw workload-phase record. Reproduce
   the ~19.95 vs 13.59 API cgroup CPU observation; profile user/system CPU,
   syscalls, sync, scheduling and network; separate off-CPU waits/wake latency.
3. Independent fixture worktrees: W4 ingest/queue/workers/artifacts; W5 pinned
   TS/JS watch/test app; W8 identical multilayer independent-registry portfolio
   and state-preserving prepare; W9 fixed real build/test jobs; W11 representative
   mixed activity. Version changed fixtures/baselines, enforce pinned assets.
4. W10 independent trace: command begin/end, service process/ready, port ready,
   first success, refusal-cache hits, failures/retries. Keep end-to-end startup
   cost and committed-data checks. Select code change only after attribution.
5. Resource cells: idle CPU/wakes, steady/peak actual footprint, reclamation
   and next use, actual host allocated bytes before/after/cleanup, repeated-cycle
   growth, persistent-volume restart/upgrade survival. Declare absolute and
   ratio budgets before selecting candidates. Unknown cache size stays unknown.
6. Disposable-state disk expansion/migration preserving volume identity/data;
   audit Cached+Fsync, guest flush and promised failure model. Establish comparable
   durability; container restart does not demonstrate power-loss safety.
7. If W2 profile supports wake-path investigation: identical pinned binary/work/
   clock, same CPU and distinct CPU affinity on both engines, actual placement/
   migrations, discriminating vCPU/load conditions and host thermal/power state.
   Reject busy-spin idle regressions. Predeclare application benefit before any
   supported VZ/guest candidate or bounded alternative-backend experiment.
8. Freeze candidate/per-cell matrix only after correctness, fixtures, resource
   accounting and durability gates exist. Affected confirmation batches first;
   full paired qualification, independent confirmation, fresh held-out app and
   durable finite 12-hour W11 per engine last. Preserve all losses/unknowns.

After three neutral/failed hypotheses on one bottleneck, obtain independent
review or change profiling boundary while advancing another ready item.
Installed-default, resource-matched default-driver and identical-builder controls
remain separate. No full W1–W10 sweep before the bounded repair/calibration.
