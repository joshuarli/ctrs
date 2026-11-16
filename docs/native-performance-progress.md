# macOS performance campaign: progress and continuation

**ACTIVE — resumed from reviewed 94f19a8.** Native ARM64 macOS only.
Contract: [campaign-native-performance.md](campaign-native-performance.md).
One coordinator owns measured Mac runs; this is the single current queue.
Historical checkpoints and superseded claims are in
[evidence/native-performance.md](evidence/native-performance.md).

## Current slice and exact continuation

Bounded collector/scoring repair is in progress. First slice removes category
fallback and partial-total qualification, separates footprint subprocesses
from CPU ticks, exposes missing data/errors/timing and records sampler hash.
52 offline regression tests pass. Preflight passed with no warnings.
Resource scoring deliberately remains unmeasured for name-discovered processes.
No clean calibration or overhead comparison yet. Preserve default build-driver
implementation and W6/W7 pilot wins; reconfirm on the eventual frozen candidate.

Next executable action: inspect daemon 7487 and VM helper 7488 (verify current
PID/start identity before use) and the warm socket under
`.work/native-perf/engines/ctrs-warm`; establish ownership without adopting all
VirtualMachine processes. Inspect executable/boot metadata paths in runner.py
and daemon startup. Bind actual running executable and booted guest hashes to
that identity; add explicit required-process coverage. Do not hash current
build outputs as proof of an adopted daemon. Then run a short unscored Mac
collector pilot and sampler-on/off calibration with pre/post perf-gate-ready.
Run `TMPDIR=$PWD/.work/tmp python3.14 -m unittest discover -s bench/native -p
 'test_*.py'` after edits (join the wrapped command).

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
