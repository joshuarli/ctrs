# macOS performance campaign: progress and continuation

**ACTIVE — resumed from reviewed 94f19a8; native ARM64 macOS only.**
[Contract](campaign-native-performance.md). One coordinator owns Mac runs.
This is the single queue; history lives in [evidence](evidence/native-performance.md).
No new product performance win is qualified. Current source main 380ca26 plus
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

W9 is integrated at be7f41d: same 16 real build/test jobs at each 1/4/8/16
concurrency, strict common image/tools/artifact/source pin, exact CLI goldens.
`w9-fixed-20261116T044711` and runner 045355 pass both engines; native timeout
cleanup 045624 passes both. Setup/job/cleanup counters complete. All 123 regressions
pass. Timings unqualified under foreign Niceforge work. CLI now requires
--image-ref for W9 run/baseline/noop; see fixtures/w9-v2/README.md. No historical
proxy metrics are pooled. W11 retains its old diagnostic until replaced.
Worker 794c2b37 is terminal and integrated, no resume/duplicate needed. Its worktree
`.work/wt/np-w9-v2` is retained for provenance pending bounded cleanup.

Next source task: representative W11 mixed cycles using the persistent real
API/database/cache stack, W4 queue/artifacts, W9 fixed builds, exact cumulative
persisted state and owned cleanup. First prove short cycles, then implement the
durable finite 12h runner; do not launch 12h qualification before the full freeze.
W11 source lane is terminal incomplete: `.work/wt/np-w11-v2`, base 847b1a7,
bridge usrw_d503a4bc-a057-421f-91aa-a8ba63937b14, watch exec45590 ended. Only
W4 image-reference plumbing, one mocked test and worker-pin.json were returned;
no mixed coordinator/CLI. Parent completes directly; no duplicate worker/retry.
First fix W4's untracked verifier container and cleanup's nonzero-inspect ambiguity.
Cumulative W2 writes need unique cycle identities (seed alone does not namespace
names), with affected fixture pins/version updated if shared load.py changes.
W4 common worker export/pin is `.work/native-perf/inputs/w11-worker-v1/`;
manifest f880c4ff... and archive a6f9cd32... verified against current app bytes.

Disk expansion 380ca26 is integrated (reviewed candidate 8b41bc2).
In-place probes 1→2→64→1024GiB preserve exact bytes, volume metadata, disk inode
and filesystem identity; final feasibility allocation delta 29,065,216 bytes.
Actual application upgrade `disk-expand-04b85cfe` passes 5,000 operations and
exact DB/cache data through automatic 64GiB→1TiB expansion and restart; actual
allocation increase 33,505,280 bytes (512MiB budget). No power-loss claim.
Host binary `.work/tmp/disk-expand-target/release/ctrs` SHA 37bec61b...;
guest variant `.work/native-perf/guest-variants/disk-expand`, initrd 71934e6d....
Workspace `guest/out/initramfs.cpio` now has that tested initrd. Main
target/release/ctrs remains older; use the explicit signed expansion host above.
Owned APFS low-space proof `disk-space-ff734318` passes with 535,040,000 bytes
free: refusal before disk size/inode/SHA changes; old engine reads exact data.
Independent scout review usrw_9d1f3dd3-251b-4b98-bc86-8712128068d4 is terminal
complete, no demonstrated findings, no edits. Parent native proofs above pass.
Source uses >=1GiB free-space preflight, full-syncs backing capacity, then resizes
ext4 before agent startup. Preflight is not a reservation/full-disk recovery proof.
Cached+Fsync durability audit remains open. Next source task is W11 cleanup and
mixed coordinator above; use unique worker IDs per cycle with the unchanged
pinned W2 loader to avoid changing W2/W8 inputs. No measured Mac job is active.

W8 runtime command (uses the tested signed metadata-fix binary):
`TMPDIR=$PWD/.work/tmp python3.14 bench/native/diagnostics/registry_pilot.py --layout .work/native-perf/inputs/w8-portfolio-v2/layout --ctrs-binary .work/tmp/image-diffids-target/release/ctrs`.
Cold/retained proof and interleaved resource timing remain open. Preserve shared
OrbStack state. Never remove user images/content to manufacture cold pulls.

## Ready queue

1. Implement/prove W11 representative mixed cycles above, then durable bounded
   execution support. Request windows plus trivial churn remain insufficient.
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
