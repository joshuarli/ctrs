# macOS performance campaign: progress and continuation

**ACTIVE — resumed from reviewed 94f19a8; native ARM64 macOS only.**
[Contract](campaign-native-performance.md). One coordinator owns Mac runs.
This is the single queue; history lives in [evidence](evidence/native-performance.md).
No new product performance win is qualified. Current source main 95c318f plus
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
  restart/old→new guest upgrade proofs pass. Actual workspace guest initramfs
  eb0ef32667a4d0560d23482cab670f0fa7693bbd013b0484d27fb1d349cf42c7
  is published; kernel unchanged. No daemon restart or Fsync policy change.
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
  All 117 Python harness tests pass. No final fixture/qualification claim.

## Exact next action

Review and finish the source-only W9 lane, then run its functional native pilots.
Worktree `.work/wt/np-w9-v2`, branch campaign/np-w9-v2, originally 96297f7 and now
fast-forwarded to 95c318f. Bridge session
usrw_794c2b37-4b03-48b9-88a6-580f5982a4aa, watch exec3416 is terminal succeeded;
worker_status confirms only ci_jobs.py/test_ci_jobs.py/fixtures/w9-v2/jobs.json
changed, no commits or out-of-scope paths, six mocked tests pass. Parent reviewed
source; runtime still unverified. No duplicate worker or resume needed.

Before integration, enforce the exact W8 Marked manifest, reuse W8/W5 pin facts
instead of duplicate tool/lock/artifact constants, add internal child deadlines
and explicit pending-future cancellation. Keep all 16 fixed jobs at each 1/4/8/16
concurrency; exact CLI outputs and bundle hash must match. Verify all jobs and
owned cleanup on both engines using the common Marked reference from W8 result.
Integrate with runner.trial_w9 and version cases.toml; keep old 0.6s loop diagnostic
or remove its obsolete acceptance path. Use separate setup/workload/cleanup
boundaries. Foreign host work permits functional proof, never a timing win.

W8 runtime command (uses the tested signed metadata-fix binary):
`TMPDIR=$PWD/.work/tmp python3.14 bench/native/diagnostics/registry_pilot.py --layout .work/native-perf/inputs/w8-portfolio-v2/layout --ctrs-binary .work/tmp/image-diffids-target/release/ctrs`.
Cold/retained proof and interleaved resource timing remain open. Preserve shared
OrbStack state. Never remove user images/content to manufacture cold pulls.

## Ready queue

1. Finish/integrate W9 above. Add W11 representative service/database/queue/
   build/cleanup activity; request windows plus trivial churn are insufficient.
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
5. Persistent-disk expansion/migration on disposable state, exact named-volume
   contents/identity. Audit Cached+Fsync, guest flush, Full synchronization and
   promised failure guarantees. Normal restart/upgrade proof is not power-loss
   durability. Sparse 1 TiB capacity is not reclaim, migration or full-disk proof.
6. W10: only resume 50ms candidate after an exclusive host window and v2 protocol
   baseline/control. Keep 250ms default. Parked local branch campaign/np-refusal-ttl
   at 54c6a00; binaries `.work/tmp/w10-{target,candidate-target}/release/ctrs`.
   Prior confirmation 010356 has a preserved host EADDRNOTAVAIL failure and invalid
   timing; no retry-to-green, no omitted failed pair. New short v2 proof alone does
   not establish every stress condition fixed.
7. Resolve known correctness failures; freeze candidate and per-cell matrix.
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
