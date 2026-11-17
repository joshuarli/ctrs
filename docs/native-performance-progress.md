# macOS performance campaign: progress and continuation

## Status

**Paused 2026-11-17 at the owner's request; campaign not complete.**
Resume prompt: `resume the performance campaign (see HEAD)`.
First command: `codex-campaign-closeout.py cancel`, then read this file and the [contract](campaign-native-performance.md).
Last accepted product: `2f37d02122c0fd06d744f03d91093a096e85a88a`, already pushed; 14 builder tests pass, zero ignored.
Seven native lifecycle cases and 156 correct comparison jobs pass; fresh main release matches the tested signed binary.
**Perf gate deferred: host busy.** Full suites, held-out app, qualification matrix and both 12h W11 legs remain open/manual-only.
No campaign workload, build, worker, cron or wakeup remains active; workstation jobs remain untouched.
Next slice: bounded classic-builder C caller proof described below; it has not started.
Parked branches, exact revisions, causes and retry conditions: [retained inventory](native-performance-retained.md#winddown-inventory-2026-11-17).
`campaign/np-full-sync` and `campaign/np-refusal-ttl` need exclusive confirmation; defaults remain unchanged.
`experiment/w2-fixed-rate` preserves an unverified, superseded proposal; review against current source before any retry.
Compression and kernel candidates are rejected; diagnostic branches are preserved for source provenance, never promoted by cleanup.
Retained checkouts are named in the inventory for the explicitly requested follow-on cleanup; unrelated `fix/stuf89-help` stays owned by its original task.
All required conclusions and reconstruction commands are tracked here and in linked evidence; `.work/` contains optional regenerable artifacts.

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

After an explicit resume, verify readiness reuse through the classic Docker
builder caller using an isolated root and a small native C application. This
proof has not started. Use a fresh owned tag/context and the normal default
builder path with `DOCKER_BUILDKIT=0`; verify the resulting executable and its
exact stdout through `docker run`. Exercise cold, warm, external pause/unpause
and restarted-builder cases, retaining failures. Do not change source unless
this caller demonstrates a defect. Never use an existing user builder or root.
The current buildx/Rust evidence does not substitute for this caller proof.

Reconstruct the accepted runtime from the repository, without retaining scratch:

```sh
codex-campaign-closeout.py cancel
CARGO_ENCODED_RUSTFLAGS='' CARGO_NET_OFFLINE=true CARGO_BUILD_JOBS=4 cargo xtask guest
CARGO_TARGET_DIR="$PWD/.work/tmp/readiness-main-target" \
  CARGO_ENCODED_RUSTFLAGS='' CARGO_NET_OFFLINE=true CARGO_BUILD_JOBS=4 \
  cargo build --offline --locked --release -p ctrs --bin ctrs
codesign --force --sign - --entitlements crates/ctrs/ctrs.entitlements \
  .work/tmp/readiness-main-target/release/ctrs
codesign --verify --strict --verbose=2 .work/tmp/readiness-main-target/release/ctrs
```

These are resume instructions, not winddown jobs. Keep the repository's pinned
compiler and cached dependencies. The signed host at accepted source `2f37d02`
is 6,615,920 bytes, SHA256
`db20b2106a9faadf8760e65a11357155166b2ed77fb6de784d63defe0ddbaada`.
The fresh main build already reproduced the exact tested candidate. The stock
kernel is 18,800,648 bytes, SHA256
`35087713fd7b1b152b1ac0333e42edbcee482c82c6e695f27a8f126c271eee43`;
accepted guest initrd is 4,349,700 bytes, SHA256
`6ae4d3abfb3be1f4dcc1edf200261a29e22ad96c922c2d677d5874df21abc8b2`.
Verify all hashes before use; do not substitute old `target/release` or installed
assets. The guest build reproduced this initrd earlier; the primary checkout's
pre-existing `guest/out` was not overwritten during winddown. No deployment was
performed. Sparse guest disks require sparse receipts, never whole-1TiB hashing.

The [readiness evidence](evidence/native-builder-readiness-2026-11-17.md) records
source invariants, native cases, comparison scope, binary identity and the
preserved C1 outlier. The [build boundary record](evidence/native-build-boundaries-2026-11-16.md)
records rejected gzip/zstd/default-build experiments, including the zstd expansion
limit failure; do not relax the unpack bound. The [uprobe record](evidence/native-python-uprobes-2026-11-17.md)
and [preemption record](evidence/native-preemption-2026-11-17.md) preserve the W2
counts and rejected kernel change. The [resource-cycle record](evidence/native-resource-cycles-2026-11-17.md)
records the rejected quiet policy. These outcomes are diagnostic, not qualified
speed claims. Earlier detailed checkpoints remain recoverable with
`git show 2f37d02:docs/native-performance-progress.md`; do not execute obsolete
next-action paragraphs from that historical revision.

## Ready queue

1. Complete the bounded affected classic-builder caller proof for readiness reuse.
   Keep W2 CPU attribution and observer controls open after the completed count
   capture. Do not repeat rejected scheduling, pacing or quiet-policy matrices.
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
4. W8 representative paired execution and reporting now pass the functional proofs
   above, including shared inputs, AB/BA order, resident control, complete native
   scopes and deliberate invalidation of diagnostic timing. Next: exclusive
   paired acceptance and guest pre-content-state accounting. Installed-default
   coverage remains separate. Do not pool common, derived or older proxy histories.
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

Affected gate: `PYTHONDONTWRITEBYTECODE=1 python3.14 bench/native/runner.py check uprobes`.
Comprehensive discovery and full qualification remain manual-only.
Before scored work, remove only verified campaign-owned diagnostics and certify
exclusivity. Gate exit 0 is insufficient: saved snapshots show hot Niceforge/fz
jobs despite aggregate-load success. Do not stop unrelated work. Installed-default,
resource-matched default-driver and identical-builder controls stay distinct.
Report wins/parity/losses/inconclusive/invalid/unmeasured per dimension; no geometric
mean may hide CPU, memory, storage, recovery, tail, correctness or durability loss.
Continue until demonstrated goals, explicit owner stop, or a blocker of ALL work.
