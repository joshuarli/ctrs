# macOS performance campaign: progress and continuation

**ACTIVE — resumed from reviewed 94f19a8; native ARM64 macOS only.**
[Contract](campaign-native-performance.md). One coordinator owns Mac runs.
This is the single queue; history lives in [evidence](evidence/native-performance.md).
No new product performance win is qualified. Current source main d3e4384 plus
this checkpoint. Default build-driver behavior and W6/W7 wins are preserved;
eventual frozen-candidate confirmation and known correctness debt remain open.

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

Next executable W2 action: add a separate low-rate per-API-thread on-CPU profile
mode to the existing bounded pilot. Preserve raw off/on controls, exact input/
data checks, loss checks and task identity. Estimate cost/op only from that
profile's own CPU/sample records. Require >=25% of the contemporaneous exclusive
CPU-per-success gap for a material mechanism, with 5% observer confirmation and
off-CPU wait separate. Current sync handlers share one psycopg connection; trace
their worker/GIL/connection lock boundary. No fixture or kernel policy change.
Exclusive 50k confirmation remains deferred by unrelated hot Niceforge work.

Independent source lane: durable finite job supervisor, worker
usrw_48734034-7dd2-4df7-aae6-2a6a83bc4df9 in `.work/wt/np-durable-job`,
base d3e4384, watch exec23369. Owns durable_job.py/test and durable-job.md only.
No engine/12h job; bounded disposable child tests. Do not duplicate or edit it.

Storage candidate `.work/wt/np-full-sync` changes only VZ Cached+Fsync→Cached+Full,
base d3e4384. Private signed host `.work/tmp/full-sync-target/release/ctrs` SHA
12d48b6a0b9b63a2411934e22de60b209fac6a8d64fb7128ee750e481d4f0860;
6,613,856 bytes, equal to baseline. No main/runtime policy change. Next storage
action: owned guest block-flush observation and committed-prefix/named-volume
survival across an owned VM interruption, then paired W3/W2/resource validation
in an exclusive window. SDK contract is stronger; host power-loss remains untested.
No measured Mac job is active.

## Ready queue

1. W2 low-rate on-CPU application profile and observer controls above.
   Representative fixture upgrades no longer block this investigation.
2. W2: low-overhead tagged wake/futex/network syscall counts with profiler-on/off
   controls, then aligned 50k application profiling in a genuinely exclusive host
   window. Existing scheduler command:
   `TMPDIR=$PWD/.work/tmp python3.14 bench/native/diagnostics/scheduler_pilot.py --tools-archive .work/tmp/w2-profile/native-tools.tar.gz`.
   Last proof 015213; input fingerprints 014544 match. No kernel/backend candidate
   from short instrumented counts. Boundary plan `.work/tmp/w2-scheduler-trace-plan.md`.
3. Interleave resource cycles, freeze inputs and collect declared five-cycle/
   30s minima with exclusive host use. Command and budgets:
   `bench/native/diagnostics/resources.md`. Unknown cache/allocation stays unknown.
4. W8 content-absent/retained design, portable artifact reproduction and scored
   phase integration. No proxy history pooled with common portfolio.
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
7. Implement durable finite W11 supervision before qualification. Resolve known
   correctness failures; freeze candidate and per-cell matrix.
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
