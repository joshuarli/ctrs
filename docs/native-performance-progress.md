# macOS performance campaign: progress and continuation

## Status

**ACTIVE 2026-11-17 — owner requested resume after completed winddown and cleanup.**
Reviewed `94f19a8` is an ancestor of HEAD; subsequent measurement, fixture and product work is reconciled below.
Current slice: sampler exit repair passes focused/native checks; review and commit it before another application comparison.
43 existing tests pass; baseline crash reproduction retains falsely valid partial totals. The affected87-test selection passes after correction.
Sampler v4 requires a current stop acknowledgment; native normal/early0/SIGKILL and phase-cell cases pass. See [evidence](evidence/native-sampler-lifecycle-2026-11-17.md).
Last accepted product remains `2f37d02`: readiness reuse, 14 tests, seven lifecycle cases and156 correct diagnostic jobs.
No product, guest or build-driver default is being changed by this measurement repair.
**Perf gate deferred: host busy** (current gate exit75: swap threshold); no scored batch or W11 is running.
Cleanup is complete:28 retired checkouts, `.work`195.3→21.0GiB allocated-size sum; [resource record](evidence/native-cleanup-resources-2026-11-17.md).
Parked source and remaining trees: [inventory](native-performance-retained.md#after-cleanup-2026-11-17); no rejected candidate is promoted.
Next action: finish narrow lifecycle/native validation, then exclusive equal-work W2 observer/application confirmation; keep saturation separate.
Classic-builder C proof remains queued after measurement repair; it has not started.
Full qualification waits for frozen representative inputs, resource/durability gates and a complete per-cell matrix.
Resume first command is `codex-campaign-closeout.py cancel` (already run); execute the first ready queue item.

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

Finish the bounded sampler-lifecycle repair in `bench/native/runner.py` and
`test_collect.py`. Baseline reproduction exits the collector with status7 after
two valid samples: shutdown ignores the status and retains CPU3.0s and physical
footprint100100B with no error. Preserve the partial raw records, retain stderr
and invalidate CPU/physical acceptance cells after premature or forced collector
termination. Confirm graceful requested stop still preserves valid cells.
Run the named collector/ownership/reporter and affected lifecycle component tests;
then a short native collection-only proof with normal and intentionally early
collector exit. Read-only observation may run on a busy host, but it cannot
establish observer overhead or product performance.

After the repair, admit the predeclared exclusive equal-work W2 confirmation
only when both scalar gate and saved process/guest snapshots establish a clean
window. Current gate exit75 defers scoring. Prior v3 sampler-on/off calibration,
fixed-work implementations, pinned wake controls, real W4/W5/W8/W9 and short
representative W11 proofs are already complete; do not rebuild these as if absent.
Preserve all original failed/invalid batches. Investigate a new causal application
boundary after the rejected scheduling/quiet/compression hypotheses, rather than
rerunning their matrices. No full W1–W10 sweep is next.

The bounded classic-builder C caller proof remains pending: isolated owned root,
`DOCKER_BUILDKIT=0`, native executable with exact stdout, cold/warm, completed
external pause/unpause, and restarted-builder cases. Keep accepted default-driver
behavior. Do not substitute the existing buildx/Rust proof for this second caller.

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

Reuse the already verified artifacts when hashes match; rebuild only if missing. Keep the repository's pinned
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

1. Complete and land the bounded sampler lifecycle repair and native functional
   validation. Reuse the existing native-v3 accounting and ownership work; no
   harness replacement or observability system. Confirm observer overhead in a
   genuinely exclusive window; keep invalid runs visible.
2. Confirm equal useful W2 work and CPU/success on a clean host, then profile the
   actual API user/system CPU, synchronization, scheduling and network boundary.
   Fixed-work/offered-load and saturation stay separate. Use raw paired records;
   sampled on-CPU and off-CPU/wake latency remain distinct. Current commands:
   `bench/native/diagnostics/w2-counters.md` and the linked W2 boundary evidence.
3. Complete the bounded classic-builder C readiness caller proof above. Preserve
   the accepted default build driver and later reconfirm W6/W7 on the frozen
   candidate. Do not rerun rejected compression/kernel/quiet-policy matrices.
4. Complete resource-cycle/reclaim/growth acceptance with predeclared budgets in
   `bench/native/diagnostics/resources.md`; unknown exclusive allocation or
   build-cache size stays unknown. Existing-disk expansion and named-volume
   survival are proved; host-full, reclaim and power-loss guarantees remain open.
   Audit Cached+Fsync versus Full without weakening authoritative-data policy.
5. W8 representative paired execution/reporting and real W4/W5/W9 functional
   paths are implemented. Freeze acceptance inputs, close content-absence and
   resource-scope gaps, then run exclusive paired acceptance. Keep retained
   content, absent content and installed-default coverage separate.
6. W10 is independent. Use the existing recovery trace and bounded v2 persistent
   client; only reconsider `campaign/np-refusal-ttl`50ms after an exclusive v2
   baseline/control. Keep250ms default and original EADDRNOTAVAIL failure.
7. Resolve known correctness failures and freeze a complete per-cell status
   matrix, input set, candidate and durability/resource contract. Then execute
   the explicitly requested full paired qualification, independent confirmation,
   fresh held-out app and finite12-hour W11 leg per engine. Full workspace suites
   remain separately manual-only; no unchanged short-W11 rerun substitutes.

Before scored work, remove only identified owned diagnostics and certify actual
exclusivity. Aggregate gate exit0 alone is insufficient; never stop unrelated
work. Keep installed-default, disclosed resource-matched/default-driver and
identical-builder attribution evidence separate. Report measured win, parity,
loss, inconclusive, invalid and unmeasured per dimension. A geometric mean cannot
hide CPU, memory, storage, recovery, tails, correctness or durability losses.
