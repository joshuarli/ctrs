# macOS performance campaign: progress and continuation

**ACTIVE — resumed from reviewed 94f19a8.** Native ARM64 macOS only.
Contract: [campaign-native-performance.md](campaign-native-performance.md).
One coordinator owns measured Mac runs; this is the single current queue.
Historical checkpoints and superseded claims are in
[evidence/native-performance.md](evidence/native-performance.md).

## Current slice and exact continuation

Bounded collector/scoring repair is in progress. Strict fields reject category
fallback and incomplete counters. Process attribution now uses the exact open
Unix socket and dedicated ctrs VM data disk, plus PID/start identity. Open
executable and guest asset inode/mtime checks prevent hashing replaced files
as running artifacts. Build-output hashes are separately labeled. 56 offline
regression tests pass. OrbStack 4-second collection pilot produced 20 CPU ticks,
complete required-process counters, one complete phys_footprint sample and no
errors. This is collection validation, not scored performance or overhead proof.
Raw pilot: `.work/native-perf/results/strict-ownership-pilot/`.

Next executable action: safely restart only daemon 7487 after revalidating its
socket/start identity. Its VM helper 7488 holds the dedicated campaign disk;
open guest Image was modified after VM start, so boot identity is unverified.
Current owned engine inventory: registry `3fe7a64ed767` (npw8-reg-ctrs) and
builder `1408fcf96f83` (dev.ctrs.builder=1); no diagnostic load found. Preserve
all disks/volumes. Relaunch with existing dedicated data/state/socket paths,
CTRS_CPUS=17 and CTRS_MEMORY_MIB=45091; rerun ownership.discover. Then finish
explicit workload CPU boundaries and asynchronous terminal footprint records,
run short ctrs pilot, and sampler-on/off comparison after worker completion and
pre/post perf-gate-ready. No scored W2 until this calibration is sound.

Independent W4 fixture worker owns `.work/wt/np-w4` on `campaign/np-w4`, base
0f5724f. Bridge session `usrw_6b9afa4c-6459-4baa-b303-25dc5df1b657`;
watch exec session 17037. It may only edit fixtures/w4/ and test_w4.py, with
offline checks, no engine/build/measurement actions. Inspect status and review
before integrating. Integration worktree is the repo root on main.

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
