# macOS performance campaign: progress and continuation

**ACTIVE — resumed from reviewed 94f19a8.** Native ARM64 macOS only.
Contract: [campaign-native-performance.md](campaign-native-performance.md).
One coordinator owns measured Mac runs; this is the single current queue.
Historical checkpoints and superseded claims are in
[evidence/native-performance.md](evidence/native-performance.md).

## Current slice and exact continuation

Bounded native-counter repair validated with 62 passing tests and short pilots.
The sampler uses proc_pid_rusage V0: Mach-converted CPU, actual ri_phys_footprint,
wake counts and kernel start identity. Socket/dedicated disk ownership and open
executable/boot-asset identity are verified; missing processes invalidate cells.
Build-output hashes are separate. W2 setup/workload/cleanup boundaries are saved.
Only the owned ctrs VM was restarted; 86 volume names survived (contents and
power-loss durability remain unverified).

Subprocess sampler v2 was rejected by overhead calibration; evidence contains
the failed batch. Native v3 batch `sampler-calibration-20261115T221334` completed
5 alternating pairs/engine, 4-s W2, concurrency 4, seed 7, all correctness and
pre/post host gates passed. Median throughput on/off ctrs 0.9935, OrbStack
0.9906; CPU/success 1.0024 and 0.9702. Passes predeclared median 3%/5% budgets,
but individual pairs are noisy; this is short calibration, not qualification.
Native physical footprint agrees with correctly attributed footprint auxiliary
output. That validation exposed/fixed Shared-with heading PID reassignment.
No jobs remain from calibration; exec sessions 29272/19202 are terminal.

Next executable action: apply `.work/tmp/upgrade-w2-load.py` and
`.work/tmp/upgrade-w2-runner.py`, review them, test fixed total operations,
acknowledged-write manifests, exact persisted row/payload checks and raw paired
CPU/success reporting. Add behavioral fixed-work tests and version cases.toml.
Keep saturation separate. Then run short fixed-work pilots and clean API cgroup
CPU deltas; profile actual application if the deficit persists. No full sweep.

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
