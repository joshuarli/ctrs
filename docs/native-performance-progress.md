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

Actual API profiles now exist. Diagnostic tools archive
`.work/tmp/w2-profile/native-tools.tar.gz` sha256
475ad5495772fa311084f9e15335c18aeffce3e8cb138c3d11e3f9a12b06883b is copied
into API /tmp; only profiler exec gets its library path/privileges. Both engines
use identical binaries and Python/direct application dependency versions.
Matched diagnostic compose adds seccomp=unconfined and SYS_PTRACE/PERFMON to
both APIs; normal product defaults are unchanged. No scores use these profiles.

COMPLETED: exec 48890, `.work/tmp/profile-w2-api.py`, results
`.work/native-perf/results/w2-api-inprocess-20261115T223951/`. ctrs perf/strace
and OrbStack perf/strace completed. Retain all exits/data; no profile jobs remain. Perf real target /proc/1/cmdline is verified uvicorn. Earlier
sidecar-PID and permission attempts are invalid, preserved as evidence.

Matched perf: 50k operations each, cpu-clock ~17.4848/12.9091 CPU-s, self sample
wake_up_q 15.25% ctrs /3.76% OrbStack, through futex wake and CPython
PyEval_SaveThread/pthread_cond_signal. Approximate same-profile wake cost
53.3/9.7 us per request (difference ~43.6 us, ~48% of sampled API CPU gap).
This is a material mechanism hypothesis, not a measured optimization or VZ/kernel
root-cause verdict. Strace perturbs futex traffic severely; do not use its syscall
time as on-CPU cost or its count as an uninstrumented request count.
CTRS task schedstat absent; unknown wait, not zero. Status/stat snapshots retained.

COMPLETED placement batch `w2-placement-20261115T225641` (exec 65599 terminal):
5 pairs/condition, exact 10k operations. Median paired system-CPU excess natural
55us/request, all threads CPU0 6us, main0/workers1 2us. Same-CPU prediction held;
distinct-CPU >=25us prediction rejected. Both pinned cases zero migrations.
Natural ctrs 2–50 migrations vs OrbStack 12.5k–15.3k; actual thread packing differs.
This is diagnostic evidence, not a default-product optimization/score.

COMPLETED pinned binary control `wake-pinned-20261115T230431` (exec 74687 terminal):
identical source/static binary, CLOCK_MONOTONIC_RAW, 80k handoffs/run, 5 pairs for
0/0, 0/1, 0/8, 8/16. Both ~0.4us same CPU, ~6us distinct, exact work, verified
affinity and zero migrations. Pre/post host gates pass. Old unpinned 18x contrast
is not reproduced under matched placement; no demonstrated VZ latency ceiling.
Guest topology captured; stock ctrs SCHED_MC is off and cache topology differs.

RUNNING guest build: `.work/wt/np-sched-mc`, branch campaign/np-sched-mc,
base 85e361a. Only source diff CONFIG_SCHED_MC=y. Docker-owned durable job
`np-sched-mc-build`, ID a42e49d9c721d47ddb18341acef6fd47fc9c17ef851e211d635e31578dc032bc,
started 2026-11-16T07:17:11Z, timeout 900s (deadline ~07:32:11Z). Wait exec 37901.
Job outputs/logs/plan/saved exit are in its `.work/kernel-mc/`; source/tool inputs
are hashed. Builds a clean stock baseline then MC candidate with the SAME compiler
container, original procedure minus repeated package installation. ctrs-kbuild
had no other user when admitted. Existing main guest/out is untouched. Both
variant asset dirs link the original initramfs and sparse template.

Next executable action: observe this exact build once for terminal state; require
saved exit-status=0, Docker State.ExitCode=0, both Images/configs, matching compiler
hashes and effective config diff limited to MC. Do not retry from observation
timeout. Select finished assets via CTRS_GUEST_DIR in owned warm engine, keeping
host binary/default driver/data disk fixed. Run affected fixed-work W2 and declared
idle/wake/footprint/storage/next-use guards before selection; W6 parallel-build
regression if credible. Hypothesis and numerical budgets are in latest evidence.
No VMM/backend experiment is justified by current matched wake data.

W8 prepare state-preserving update is repaired with four focused tests: selected
engine section merges atomically, other valid section remains untouched, malformed
metadata/failed replace/symlink cases preserve data. No manual JSON restoration
is needed for valid state. Independent identical multilayer portfolio remains
pending; do not call old W8 pilots acceptance coverage.

W4 v2 replacement is integrated and verified: 72 tests pass. Real-engine
correctness pilots passed all 1/4/16-worker conditions: OrbStack
`run-20261115T224539-837d`, ctrs `w4-v2-ctrs-20261115T224709`; final input-hash
check also passed OrbStack `run-20261115T224839-814a`. Each condition ingests
200 batches/12,800 events and verifies 400 exact gzip NDJSON/JSON artifacts,
empty queue, no duplicates/loss/corruption/extras, and owned cleanup. Same
exported fixture image on both engines (archive SHA256
a6f9cd32079b7980c268d3ad504174fa8af01654d7442026ae726f8a182809f7).
App hash is enforced before work; Python and Redis content digests pinned.
This establishes functional v2 coverage, not frozen acceptance/performance wins;
fixture size and all per-cell budgets still require freeze/qualification.
Old hash-only W4 results are incompatible diagnostics. Retire worker tree
`.work/wt/np-w4` only after useful final source is safely committed/integrated.

W5 v2 source lane: `.work/wt/np-w5`, branch campaign/np-w5, base 565c3e2.
Bridge worker usrw_6f9b0a5e-9e1f-4616-a10d-8c05803d73c3 (watch 33323) ended
incomplete as expected pending build clearance. Marked v15.0.12 real TS CLI,
archive/lock/Node/npm/image digests pinned; persistent rebuild + exact HTML test.
Three offline tests and source preparation passed. Parent must review files,
build and run bind/volume watch pilots after kernel build; do not claim W5 coverage.
No Docker/engine actions authorized in that lane while build owns Mac.

Resource-cell source lane: `.work/wt/np-resource-cells`, branch
campaign/np-resource-cells, base 85e361a. Bridge
usrw_4e78a6d8-998e-413d-ba63-7b7e435f0c34, watch exec 32535. Owns resource_cells.py/test_resource_cells.py only;
complete native intervals, idle CPU/wakes/steady+peak footprint, explicit budgets,
post-warmup growth, sparse host allocation with clone/volume uncertainty. No
engine/build or measured workloads. Parent integration/Mac pilot pending.

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
