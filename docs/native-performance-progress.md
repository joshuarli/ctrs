# macOS performance campaign: progress and continuation

## Status

**ACTIVE 2026-11-16 — owner authorized resume from HEAD. Campaign not complete.**
`codex-campaign-closeout.py cancel` returned “Campaign closeout is not active”.
Resume steering: storage review repairs, real W8 content-unique validation and
20-phase native engine-resource accounting are accepted below. Measurement
exclusivity limits W2 acceptance. Continue W8 fixture-service resource accounting
and under-pull application-load coverage while foreign host work prevents timing.
No runtime policy change is accepted.
Read the [contract](campaign-native-performance.md), then inspect
`git show campaign/np-storage-space:bench/native/diagnostics/storage_space_pilot.py`.
Resumed source milestones: W8 bc6625f reviewed and integrated as 00ac842;
storage source restored as 3a87d61 with review fixes 97a6a69. Host guard now
checks between bounded 64MiB allocation attempts; snapshot failure cannot skip
shutdown, log closure or the result write attempt. Six focused storage tests
and all 173 harness tests pass. Native revised storage proof passes;
real W8 artifact generation and native full-transfer proofs pass below;
guest cache absence below the image API remains unqualified.
Other parked branches, retained trees and consumers are recorded in the
[retained-work inventory](native-performance-retained.md).
Storage worker `usrw_58efedef-31f1-4f36-be14-30c5c008481b` is terminal succeeded;
parent reviewed its scoped diff and independently ran the integrated suite.
W2 block `w2-cpu-20261116T163545-94e4` completed all four exact 50k phases,
852/582 native CPU samples, no errors or cleanup failures. Timing and observer
overhead are INVALID: ctrs/off/before-gate.json recorded Niceforge import PID
98721 at 100% CPU despite gate exit 0. The ten-block batch was interrupted after
block one; nine blocks were not started, with no replacement or pooled history.
Batch scratch: `.work/tmp/w2-observer-resume-20261116/`; parent exited 143 only
after its child completed. No W2 job remains. Re-establish genuine exclusivity
before a separately predeclared observer batch. Continue native storage correctness
and W8 preparation while timing is deferred; no runtime candidate is promoted.

Revised native storage runs `space-e793d5a5` (allocation) and `space-9c94d113`
(relation ENOSPC) both exit 0 for Fsync and Full. Each uses NEW owned roots,
the pinned common portfolio, baseline 37bec61b… and Full 12d48b6a… binaries,
unchanged guest assets and source 97a6a69. The allocation stage verifies exact
100-record contents and 64MiB unwritten extents. The ENOSPC stage verifies
relation SQLSTATE 53100, the exact 100-record prefix and 10 recovered commits;
filesystem/volume identities remain unchanged and cleanup reports no errors.
Reproduce both commands in `bench/native/diagnostics/storage-space.md` on main.
Raw receipts remain `.work/tmp/<run>/{fsync,full}/`. Zero endpoint host growth
is not a peak bound, exclusive allocation/reclaim or host-full/power-loss proof.
Full remains an unpromoted candidate. No campaign measurement job remains.

W8 real reproduction `.work/native-perf/inputs/w8-portfolio-v3-resume-20261116/`
produces identical receipts and verified compressed digests on two generations:
four images, 37 distinct layers. Native exploratory run
`w8-unique-20261116T164214-6676` passes on both engines. The reusable diagnostic
`bench/native/diagnostics/registry_variant_pilot.py` then passes fresh-source run
`w8-unique-20261116T164609-001c` with seed
`ctrs-w8-v3-integrated-source-20261116-1`, derived layout
`.work/native-perf/inputs/w8-portfolio-v3-source-20261116/`.
Each engine transfers every distinct layer completely, verifies every installed
marker payload, performs exactly 1,000 operations (688 reads/312 writes),
checks exact DB/cache state after API restart and the pinned Marked artifact,
and preserves all four original image IDs. Both exit 0, no errors, owned fixture
cleanup. Eight focused variant/transfer tests pass. The source diagnostic adds
strict missing-image error classification and labelled marker-container cleanup;
it rejects partial/HEAD transfers. Reproduction commands are in
`bench/native/fixtures/w8-v3/README.md`; use a fresh seed and destination because
derived images remain installed. No cold-store, sub-API guest absence, timing or
resource acceptance is implied. Do not repeat these completed functional proofs.
W8 phase integration 9b9f94b and parent repairs now pass native run
`w8-unique-20261116T165722-509c`: both engines, all 20 declared phases have
complete CPU/native sampled-footprint coverage, exact application/marker/retained
image checks, exit 0 and clean teardown. Source worker
`usrw_e60a38ea-7f97-4091-8fee-a5494e87b5e1` is terminal succeeded; parent reviewed
the diff and fixed resource-failure exit status, summary-failure shutdown, empty
coverage and lazy-boot preconditioning. Fifteen focused tests and all 183 harness
tests pass. The earlier `w8-unique-20261116T165508-08e9` remains FAILED: its app
checks passed but sampling began before the lazy ctrs VM booted; it has no valid
resource cells and exit 1. It is not pooled with the corrected proof.

The fixture now verifies an owned no-pull Python container on both engines before
sampling the declared warm-engine phases. Boot/preconditioning is explicitly
outside those cells; cold-engine/startup acceptance remains separate. Corrected
layout `.work/native-perf/inputs/w8-portfolio-v3-warm-phases-20261116/`, seed
`ctrs-w8-v3-warm-phase-proof-20261116-1`. Native traces, raw phase boundaries and
host snapshots are under the run's engine directories. All verdicts remain
functional: excludes registry/coordinator/CLI and active backing allocation;
sampled footprint is not a continuous peak. No timing claim under foreign load.
Registry/coordinator coverage now passes native
`w8-unique-20261116T170443-b0db` on both engines: all 20 phase summaries are
complete with the fixture's self PID, kernel start identity, loaded interpreter
and actual listener alongside the required engine processes. Scope version
`w8-engine-fixture-v1` includes this coordinator's registry thread and harness
work; do not pool old engine-only records. Missing engine discovery cannot be
hidden by a live fixture PID. Phase-aligned boundaries and sampled aggregate
footprint use the same native collector. Waited-child CPU deltas are separate
diagnostics, not phase-aligned all-client costs; CLI footprint, live children,
sampler overhead and allocated storage remain outside coverage. Both runs exit
0, exact app/marker/retained-image checks and clean fixture teardown.
Layout `.work/native-perf/inputs/w8-portfolio-v3-service-20261116/`, seed
`ctrs-w8-v3-service-proof-20261116-1`; all 187 harness tests pass.
Next executable source action: add fixed application load during pulls with
proven overlap, exact accepted payloads and complete teardown. Keep the pinned
W2 driver unchanged; use a distinct instrumented W8 fixture version for traces.
Preserve unique per-pair inputs shared by both engines. Keep v2 history separate
and require a new exclusive paired baseline before scoring v3. An async request
for a quiet host window is pending; this does not block independent source work.

## Accepted and verified

- Sampler v3 uses actual ri_phys_footprint, converted native CPU/wake counters,
  kernel start identity, exact socket/disk ownership and open binary/guest hashes.
  Missing daemon/VM/counters invalidate totals. Short phases have fast boundaries.
  Native on/off calibration passed median budgets; final confirmation still needed.
- W2 fixed work verifies successful reads/writes and every persisted payload.
  CPU/success comes from aligned raw workload counters. Saturation is separate.
  Matched pinned futex controls show both engines about 0.4us same CPU and 6us
  distinct CPUs. Old unpinned contrast does not establish a VZ wake ceiling.
  Scheduler parser joins guest namespace/global TIDs; task CPU and off-CPU/wake
  elapsed remain separate, with short-run quantization and unknown edges explicit.
- W4 real HTTP ingest/Redis/workers/artifact fixture passes both engines at 1/4/16
  workers. W5 real Marked persistent watch/rebuild/CLI loop passes bind and volume
  modes. Exact contents/outputs, pinned inputs, complete phase accounting.
- W2 resource-cycle pilot 4f21c82 measures idle CPU/wakes, sampled steady/peak
  physical footprint, reclamation/next use, explicit backing allocation and
  repeated-cycle growth. Budgets declared before collection. Native pilots
 041130/041443/041549 pass exact data and counter coverage. Short windows leave
  growth unknown; foreign host work invalidates performance verdicts. Exclusive
  APFS allocation and isolated build-cache size stay unknown.
- W10 client 96297f7 uses per-worker persistent HTTP, bounded workers/socket waits,
  no hidden retry and explicit connect/open/reuse/native errno. Baseline proof
 041907 passes exact committed DB/cache state on both engines; no unexpected or
  host-address failures. Timings invalid under foreign work. Never pool v1/v2.
- Persistent mount guard 3fa2f01 rejects ext4 errors before agent startup instead
  of acknowledging authoritative data on tmpfs. Native invalid-media/normal
  restart/old→new guest upgrade proofs pass. Preserved mount-guard initramfs
  eb0ef32667a4d0560d23482cab670f0fa7693bbd013b0484d27fb1d349cf42c7;
  workspace now uses the reviewed expansion guest 71934e6d... below. Kernel
  unchanged. No daemon restart or VZ Fsync policy change.
  Preserved variants: `.work/native-perf/guest-variants/{mount-guard,pre-mount-guard}`.
- RootFS metadata fix cdcbfb4 reports config diff IDs, not compressed blob hashes.
  All 177 ctrs tests and real common-image deployment pass. Signed test binary:
  `.work/tmp/image-diffids-target/release/ctrs`, SHA
  cd29f06cad1cd73bab4d6377ce535159ba08f081899cab3a4a8ec30aabae8126.
  Main target/release is older; do not assume it contains this fix.
- W8 common portfolio 95c318f pins API/PostgreSQL/Redis/Marked manifests, layers,
  tool versions and exact app/load/seed inputs. Independent host registry and
  healthy deployment pass both engines; exact 1,000 operations and same Marked
  artifact. Main proof `w8-common-20261116T044051-d3d5`; worktree proof 043656-23ec
  has full 389MB ctrs transfer versus retained OrbStack 0 bytes, explicitly NOT a
  comparable cold result. Old per-engine flattened fixtures stay diagnostic-only.
  Artifact/layout/export receipt: `.work/native-perf/inputs/w8-portfolio-v2/`.
  All 123 Python harness tests pass. No final fixture/qualification claim.

## Exact next action

W11 representative short cycles now pass both engines: run
`w11-mixed-20261116T063716-8565`, two cycles each, exact 10k operations/3,062
unique writes, 400 queue jobs/800 artifacts and 32 real build/test jobs per engine.
Complete six native resource phases, stable persistent data/volume/process/artifact
identity, owned cleanup. W4 native verifier-timeout cleanup 063825 passes both.
All 128 Python tests pass. Foreign Niceforge import invalidates timing. This is
not the 12h leg or a growth verdict; legacy W11 remains diagnostic-only.
Command/input details: `bench/native/fixtures/w11-v2/README.md`. Terminal incomplete
worker d503a4bc partials were completed directly; its original tree is retained.

Disk expansion is integrated at 380ca26 after independent review 9d1f3dd3 (terminal
complete, no demonstrated finding) and parent native proofs. `disk-expand-04b85cfe`
preserves exact 5k-operation DB/cache state, named volumes, FSUUID and inode across
64GiB→1TiB and restart, allocation +33,505,280 bytes against 512MiB budget.
Owned low-space `disk-space-ff734318` refuses before size/inode/SHA mutation, then
old engine reads exact data. Source/review trees retained; do not rerun completed
feasibility probes. Workspace guest initrd is 71934e6d...; explicit signed host
`.work/tmp/disk-expand-target/release/ctrs` SHA 37bec61b... contains expansion.
Main target/release remains older. No shared daemon restarted. Cached+Fsync audit
and full-disk recovery remain open; free-space preflight is not reserved capacity.

W2 matched stock-kernel counters are implemented in `diagnostics/syscall_pilot.py`.
`w2-count-065245-1ece` passes fresh 5k profiler-off/on controls on both engines;
`065510-8fb0` repeats at verified 17 CPUs and <0.1% MemTotal difference. All required
50 thread/event cells and exact data pass. SIGTERM fault `065808-e7a1` preserves
-15 and removes owned probes/project. All 131 Python tests pass. Short quantized
busy-host controls leave the declared 5% observer budget inconclusive. Details and
command: `bench/native/diagnostics/w2-counters.md`. No scored win.

The predicted >=20% futex/wake-frequency reduction from increasing ctrs 2→17 CPUs
did not occur. Do not select that remedy. At matched capacity, ctrs has 44.1926
futex calls/18.5824 API-generated wakes per successful op; OrbStack 21.3548/12.1268.
These are instrumented diagnostic counts under foreign load, not causal CPU cost.
ctrs API migrates only 3 times versus OrbStack 7,458; endpoint CPUs do not establish
residency. Keep the next boundary in the actual API's worker/GIL/futex operations.

Known-count ARM64 futex decoder now passes both engines at
`futex-decode-20261116T071630-9ccc`: exact 300 calls/200 WAIT/100 WAKE,
100 EAGAIN/timeout/zero returns, no misses, C exit 0, owned probes absent.
Source/binary pins and command: `diagnostics/w2-counters.md`. Perf tracepoint
aliases and chained mask comparisons are unsupported; verified ordered selectors
and explicit opcode comparisons work. This is not a latency/CPU verdict.

W2 counter v2 now passes `w2-count-20261116T072415-7488` on both engines:
90 complete cells, exact 5k off/on work, zero missed probes and owned cleanup.
SIGTERM 073005-b45b preserves -15 and removes return probes. All 134 tests pass.
Current raw WAIT/WAIT_BITSET/WAKE frequencies are roughly doubled in ctrs; EAGAIN
is 1.9458 versus 0.5596/op. CPU/observer timing remains unqualified. Definitions,
filters and ordering have one owner, `counter_specs.py`; do not pool v1/v2.
Failed 072115 cleanup is preserved, with its return-prefix parser cause fixed.

W2 separate on-CPU mode now passes native fixed-period pilot
`w2-cpu-20261116T082957-1e4f`: exact 5k off/on operations per engine, all five API
threads sampled, 93/55 samples, raw/decoded counts agree, no loss/throttle records
or cleanup errors. Adaptive-frequency feasibility `082819-3763` stays separate.
SIGTERM `083059-fc2b` preserves -15 and clean owned teardown. Native stacks include
unresolved frames; worker samples are sparse. No overhead or causal-cost verdict.
Commands and limitations: `bench/native/diagnostics/w2-counters.md`. Raw plan SHA
f325adb9220a5f9dac011e71f53c1874f36669586b51f5ce7f630eb2cb99fe07.
Independent worker review bd03fc07 is terminal succeeded, no source changes.
Its attachment-to-phase TID-reuse finding is fixed at e6bbb45 before workload
admission; both native captures' warm/phase identities match. Full 148-test suite
and then seven focused CPU tests pass. Source review tree retained at
`.work/wt/np-cpu-review` (branch `campaign/np-cpu-review`, no unique source).
Balanced mode/engine order is now executable; reverse-order native proof
`w2-cpu-20261116T083838-d073` passes exact 5k off/on work and clean teardown.
Each trial saves before/after host snapshots. Next W2 action: ten predeclared
exclusive interleaved 50k blocks as specified in `w2-counters.md`. Estimate
cost/op only from that profile's own CPU/sample
records; require >=25% of the contemporaneous CPU-per-success gap for a material
mechanism and <=5% CPU/wall observer overhead. Keep off-CPU wait separate. Current
sync handlers share one psycopg connection; trace worker/GIL/connection locks.
No runtime/fixture/kernel policy change. Recheck actual host load before timing;
previous Niceforge contamination does not establish current exclusivity.
At 08:33 local the gate rejected Niceforge PID 46238, an unrelated image import;
do not stop it. Reverse-order 08:38 trial gates passed, which does not establish
continued exclusivity. No scored batch is running.

Durable supervisor 4a4ad92 is integrated after worker 48734034, parent fixes and
independent review 527b2395. Eight real child lifecycle/ownership cases pass;
all 142 harness tests pass. Source/review trees retained, both lanes terminal.
Command: `bench/native/diagnostics/durable-job.md`. No engine/12h job launched.
W11 duration integration is accepted on main through 1a48731 (source lane
3109451). The worker 30624954 is terminal succeeded. Review c1b14f9a found drain
cleanup, group TERM and adopted-asset gaps; its receipt scope was incomplete and
attempt exhausted. Corrected-slice review 16a260b2 is terminal succeeded, no source
changes. Its parent-receipt aggregation finding is fixed at 1a48731 with a focused
regression. All 162 harness tests pass on main. No runtime binary was rebuilt.

`mixed_job.py` freezes inputs, including explicit sparse-content receipts for the
1TiB template, and runs persistent same-stack cycles under the accepted supervisor.
Work, drain and cleanup deadlines are separate. Owned queue/build cleanup retains
its own budget after drain expiry. Extended interruption grace signals the child
coordinator before group KILL so its engine remains available for teardown. Actual
open kernel/initrd identities must match frozen receipts. Qualification still
refuses before engine access: frozen candidate/final matrix/readiness proof are
missing. This is a functional source milestone, not a substitute for either 12h leg.

Final source normal proofs: `w11-mixed-20261116T090224-c24f` (ctrs, 11 cycles,
55k exact operations/16,841 unique writes) and `090314-a02b` (OrbStack, seven cycles,
35k operations/10,717 writes), each with exact queue/build artifacts and stable
service/volume/process identities. Both exit 0 with clean teardown. Raw results
remain in `.work/wt/np-w11-deadline/.work/native-perf/results/`. Their durable jobs
are `.work/tmp/w11-final-20261116T0905-ctrs` and `w11-final-20261116T0906-orbstack`.
Status SHA-256 respectively:
`f2c46456adefd10105ce6afee240178e673dddb9a7aac3f4295d9beba2ca62b1`,
`ef9e72bb12c075dcf532dcf68a30e9fb4b5a6f501f03fbf8142ddcabf11ae86e`.
These 45s diagnostics leave timing, growth and 12h reliability unqualified.

Native SIGTERM proof `085659-ee94`, durable job
`.work/tmp/w11-cancel-20261116T0900-ctrs`, preserves supervisor/child signal 15;
only expected SystemExit(143), all seven queue/build receipts clean, zero remaining
containers in its isolated root. Earlier `085259-0967` exposed premature daemon
TERM; its failed receipt is retained. Five owned resources (three containers,
network, volume) were explicitly recovered after label inspection; receipt/driver
`.work/tmp/w11-cancel-owned-cleanup.{json,py}`, receipt SHA
49b89e781f502f66217224718c9336673cf76358ff073a4d02128ea759f82997.
Failed isolated startup `085608-caa9` retains SUN_LEN failure; roots now use short
job-parent scratch paths. Earlier 90s/45s feasibility runs remain separate.
Source/review trees `np-w11-deadline`, `np-w11-review`, `np-w11-fix-review` are retained
with raw proofs; all lanes are terminal. No native W11 job is running. Do not
repeat these unchanged short proofs. Next W11 work is real frozen-readiness and
resource-growth acceptance after matrix/candidate freeze.

Storage candidate f536b6e in `.work/wt/np-full-sync` changes VZ Cached+Fsync→Full.
Signed host `.work/tmp/full-sync-target/release/ctrs` SHA
12d48b6a0b9b63a2411934e22de60b209fac6a8d64fb7128ee750e481d4f0860,
6,613,856 bytes, equal baseline size. Main/runtime default remains Fsync.
`sync-proof-ed045113` passes both modes in NEW owned roots: 100 observed guest
flush requests/100 exact acknowledged records, daemon Popen SIGKILL, helper disk
closure, PG WAL recovery, unchanged volume metadata and no cleanup errors.
No host power-loss claim. Actual allocation is recorded; reclaim/growth unqualified.
Source/plan/raw results: `.work/tmp/sync-proof-ed045113/`; driver
`.work/tmp/full-flush-pilot.py`. Do not repeat orderly restart as durability proof.
Unaccepted relation-ENOSPC experiment 538e2c3 is parked after owner winddown.
`space-32241aef` passes both binaries: actual relation SQLSTATE 53100, exact
100-record prefix, 10 new commits, unchanged filesystem/volume identity and owned
cleanup. Its supervisor job `.work/tmp/space-source-20261116T0935` exits 0.
The zero allocation delta is an endpoint observation, not a peak bound. Review
34112a16 found that the growth check occurs only after reservation and that a
cleanup snapshot write can skip shutdown/result persistence. Both fixes remain
open; the source was reverted from main and preserved on `campaign/np-storage-space`.
The [inventory](native-performance-retained.md) records raw paths and failed or
narrower prior cases. No root-reserve exhaustion, host-full storage, exclusive
reclaim or power-loss claim. After review fixes, continue allocation/reclaim and
paired W3/W2/resource confirmation of Full in an exclusive window. Keep host
metadata sync_all separate from guest data-disk policy; OrbStack policy is unknown.
No measured Mac job is active.

## Ready queue

1. W2 larger application profile and balanced observer controls above.
   Representative fixture upgrades no longer block this investigation.
2. W11 duration/cleanup integration is accepted. Freeze actual qualification
   readiness and resource-growth evidence with the final matrix/candidate; no
   12h launch yet. Do not repeat unchanged short cycles.
   Existing W2 scheduler diagnostic remains available:
   `TMPDIR=$PWD/.work/tmp python3.14 bench/native/diagnostics/scheduler_pilot.py --tools-archive .work/tmp/w2-profile/native-tools.tar.gz`.
   Last proof 015213; input fingerprints 014544 match. No kernel/backend candidate
   from short instrumented counts. Boundary plan `.work/tmp/w2-scheduler-trace-plan.md`.
3. Interleave resource cycles, freeze inputs and collect declared five-cycle/
   30s minima with exclusive host use. Command and budgets:
   `bench/native/diagnostics/resources.md`. Unknown cache/allocation stays unknown.
4. W8 content-unique preparation is integrated at 00ac842 and the real generation,
   full-transfer/marker/application proofs pass above. Next: scored phase/resource
   integration and guest pre-content-state accounting. No history is pooled with
   the common portfolio; API image absence is not complete guest-cache absence.
5. Existing-disk expansion is proved/integrated. Audit Cached+Fsync, guest flush,
   Full synchronization and
   promised failure guarantees. Normal restart/upgrade proof is not power-loss
   durability. Sparse 1 TiB capacity is not reclaim, migration or full-disk proof.
6. W10: only resume 50ms candidate after an exclusive host window and v2 protocol
   baseline/control. Keep 250ms default. Parked local branch campaign/np-refusal-ttl
   at 54c6a00; binaries `.work/tmp/w10-{target,candidate-target}/release/ctrs`.
   Prior confirmation 010356 has a preserved host EADDRNOTAVAIL failure and invalid
   timing; no retry-to-green, no omitted failed pair. New short v2 proof alone does
   not establish every stress condition fixed.
7. Resolve known correctness failures; freeze candidate and complete the per-cell
   matrix before qualification.
   Then affected confirmations, full paired qualification, independent batch,
   fresh held-out app and durable finite 12h W11 per engine.

CONFIG_SCHED_MC-only candidate was rejected after three neutral/costlier W2
pilots. `.work/wt/np-sched-mc` retains assets under `.work/kernel-mc`; do not deploy.
Other integrated W4/W5/resource/W8/source-fix worktrees retain provenance; retire
only after preserving useful artifacts and proving integration. The two completed
mount-guard trees were already retired. No measured Mac job is active.

Regression: `TMPDIR=$PWD/.work/tmp python3.14 -m unittest discover -s bench/native -p 'test_*.py'`.
Before scored work, remove only verified campaign-owned diagnostics and certify
exclusivity. Gate exit 0 is insufficient: saved snapshots show hot Niceforge/fz
jobs despite aggregate-load success. Do not stop unrelated work. Installed-default,
resource-matched default-driver and identical-builder controls stay distinct.
Report wins/parity/losses/inconclusive/invalid/unmeasured per dimension; no geometric
mean may hide CPU, memory, storage, recovery, tail, correctness or durability loss.
Continue until demonstrated goals, explicit owner stop, or a blocker of ALL work.
