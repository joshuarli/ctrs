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

W2 v2 equal-work implementation is verified: deterministic total operation
quotas, separate saturation mode, HTTP response validation, acknowledged-write
manifests, exact persisted names/payloads, workload CPU/success, API cgroup CPU
deltas, visible fatal worker failures. 67 tests pass. Whole-trial W2 CPU is
excluded from efficiency scoring; normalized ratios use paired raw records.

Initial one-pair pilot `base-20261115T221909-0859`: 10,000 successes each,
6,978 reads/3,022 writes, zero errors, exact persisted state; pre/post host gates
passed. API user/system CPU ctrs 2.4407/1.1032 s vs OrbStack 2.2599/0.5347 s.
Diagnostic only, before final response validation; not qualification.

Five-pair `base-20261115T222030-7ef3` completed 50,000 exact operations per trial,
all ten trials correct, but the post host gate failed on unrelated Niceforge
runner PID 42860. ALL timing pairs are invalid for scoring. Original collected
records remain in trials.collected.jsonl; trials.jsonl adds measurement_valid=false
and the reason. Reporter preserves correctness counts and excludes all ratios.
Application system CPU difference remains a profiling hypothesis, not a confirmed
clean five-pair measurement. Run exec 98317 is terminal. No measured jobs active.

Profiling tools are prepared on OrbStack as `np-w2-profiler:diagnostic`, image
config sha256:e1f2c2f7fc6230ef2d12f02d503a1b4d503a9f287cd681b0fb0cc50f41e56a3e.
Raw image metadata and OrbStack capability check:
`.work/native-perf/results/w2-profile-tools/`. Same diagnostic image has strace
6.13+ds-1, linux-perf 6.12.117-1 and procps 2:4.0.4-9. Software task-clock,
context-switch and migration counters work; tracefs has sched events and instance
support. Temporary tracefs mount was inside a removed owned container; no guest
tracing state was modified. Guest boot ID/uname are recorded. No tool build job
remains (exec 13438 terminal).

Next executable action: export this ONE profiler image, load the same archive
into the owned ctrs engine and verify common image ID. Set up owned W2 stacks,
attach perf/strace to API PID namespace (never unrelated processes), collect
API task schedstat before/after plus isolated per-PID scheduling trace. Never
replace a shared guest tracer. Profile same fixed 50k mixed
work, concurrency 4, seed 7; distinguish syscall elapsed time from CPU and
runqueue wait. Require an explained cost >=25% of confirmed per-request excess
before a candidate. Scratch plan: `.work/tmp/w2-profile-plan.md`. Clean confirmation
must be rescheduled when host allows; no Niceforge/user process may be stopped.
Final driver includes stricter response/fatal-worker checks added after the batch;
revalidate the final behavior in the next pilot. Do not wait for other fixtures.

Independent W4 replacement worker owns `.work/wt/np-w4` on `campaign/np-w4`.
Prototype preserved on that branch at 7c92827, not integrated as coverage.
Completed bridge session `usrw_25f95b47-0f9b-4e7f-b5b1-197a268f51cd`, watch exec
55436; parent review/integration pending. Four offline tests passed after 22:28.
It replaces synthetic hashing with full HTTP-ingested event batches,
JSON validation/aggregation and exact filesystem gzip/summary artifacts. No
engine/build/measurement work. Tests delayed until after 22:28 local to avoid
confirmation contention. Parent reviews and runs proof before main integration.
Integration worktree is repo root on main. This is not yet W4 acceptance coverage.

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
