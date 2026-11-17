# macOS performance campaign: progress and continuation

## Status

**WINDING DOWN 2026-11-17 — explicit owner stop; campaign not complete.**
Launch no experiments or lanes. Preserve unfinished source and finish the reboot audit.
Accepted integration HEAD is4fc901b: reviewed W11 v3, local growth capability81e51d2 and counter-window correction.
Latest product remains2f37d02. Default builder work stays accepted and unchanged.
Native W11 job0a89d8f8 passes20,000 API operations,800 queue jobs and64 build/test jobs;172 inputs unchanged.
No native job remains active. No W2 batch started after the owner accepted some background noise.
Unfinished guard/tool-provenance changes will park on `campaign/w11-admission-20261117`; review and native v4 proof remain pending.
Existing parked branches and retained checkouts are listed in [the inventory](native-performance-retained.md#after-cleanup-2026-11-17).
Owner now accepts some noise: use disclosed interleaved W2 diagnostics, preserve unrelated workloads and keep invalid cells explicit.
On resume, first run `codex-campaign-closeout.py cancel`, then read this file and inspect the parked branch.
Prioritize normalized W2 reproduction/profiling over further qualification tooling. Full qualification remains unready.

## Accepted and verified

- Native accounting uses actual ri_phys_footprint and complete owned daemon/VM
  counters, kernel start identity and loaded executable/boot hashes. v4 adds
  shutdown acknowledgment. [Measurement evidence](evidence/native-sampler-lifecycle-2026-11-17.md)
  retains the defects, focused checks and original v3 on/off calibration limits.
- W2 fixed useful work, exact persisted payloads, normalized CPU/success,
  fixed-offered-rate diagnostics and separate saturation are implemented.
  Matched same/distinct-CPU futex controls reject the old unpinned contrast as
  proof of a VZ ceiling. Counts and on-CPU/wait profiles remain distinct.
- Real W4 queue/artifacts, pinned Marked W5 watch/test, common/derived W8,
  fixed-build W9 and representative short W11 fixtures pass functional proofs.
  [Historical evidence](evidence/native-performance.md) preserves versions and
  failures; these are not final acceptance or 12h reliability results.
- Resource-cycle source declares idle/reclaim/next-use/growth budgets. Physical
  allocation is scoped to explicit files; exclusive APFS extents and isolated
  build-cache size remain unknown. [Current cycles](evidence/native-resource-cycles-2026-11-17.md).
- W10 v2 persistent clients and recovery tracing pass exact-data functional
  checks. The50ms refusal-cache candidate remains parked;250ms default stays.
- Persistent-mount guard, data-preserving disk expansion, image DiffID/label
  repairs and balloon accounting are integrated. Restart/daemon-interruption
  proofs do not establish host power-loss durability; Full sync is unpromoted.
- Readiness reuse passes both buildx/Rust and classic C callers. Compression,
  scheduler, affinity and quiet-policy candidates remain rejected/unqualified;
  their [build](evidence/native-build-boundaries-2026-11-16.md), [W2](evidence/native-w2-boundaries-2026-11-16.md)
  and [preemption](evidence/native-preemption-2026-11-17.md) records preserve the decisions.

## Exact next action

Implement the missing W11 growth observations and readiness admission using
the bounded v3 working set. Reuse existing native counters and explicit backing-
file allocation helpers. Declare observation points, warmup exclusion, numerical
budgets and minimum coverage before running. Keep unknown allocation/cache
scope and incomplete data unknown. Never infer bounded growth from a short
cycle count or a successful process exit. Then require a frozen candidate/input
identity and a complete per-cell prerequisite matrix before `--qualification`
can admit the owner-requested12-hour jobs. Existing refusal cites missing
prerequisites, not missing owner authority.

W11 v3's reviewed short proof is complete:
[exact results and command](evidence/native-mixed-retention-2026-11-17.md).
No native job or source lane remains active. The20,000-operation result is not
the12-hour leg and does not close growth, timing or durability gates.

The final c3775ce functional job13731c9782f64101a2425063857ddf49 exits0 with
all four1000-operation trials correct,708 reads/292 writes each, complete phase
CPU and both periodic traces. Teardown is verified and all155 inputs rechecked.
Later failure-path corrections use offline regressions, not another identical
normal-path run. [Exact command and scope](evidence/native-sampler-lifecycle-2026-11-17.md).

After functional acceptance, the first timed action is a separately predeclared
exclusive W2 observer/equal-work batch. Require scalar gates AND actual saved
process/guest snapshots. Ordinary gate0 has coexisted with hot Niceforge work;
the unrelated `bctl-r7-qualify` VM also prevents attribution of OrbStack's helper.
Do not stop unrelated work. The `-s` swap advisory is lane admission, not a
performance gate. If exclusivity is absent, continue the next independent queue
item; do not rerun neutral matrices or poll counters to fill turns.

W8 receipt validation is integrated at df1f418. Its source investigation and
remaining [content-state limits](evidence/native-w8-content-state-2026-11-17.md)
are explicit: new compressed identities/DiffIDs plus full delivery and runnable
contents do not establish guest-cache or page-cache absence. Preserve the66-test
component result and successful validation of two actual37-layer receipts.

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

1. Add W11 post-warmup resource-growth observations and fail-closed frozen-
   readiness admission. Keep bounded v3 state, exact-data oracles and explicit
   unknown cells. Short functional proofs never substitute for qualification.
2. In a genuinely exclusive window, confirm W2 CPU/success at equal useful work
   and observer budgets, then profile actual API user/system CPU, synchronization,
   scheduling and network costs. Separate fixed work/offered load, saturation,
   on-CPU samples and off-CPU/wake latency. Commands/budgets:
   `bench/native/diagnostics/w2-counters.md` and `w2-fixed-rate.md`.
3. W8: strengthen comparable retained/content-absent evidence and complete
   exclusive paired acceptance. Keep the identity guard, shared per-pair inputs,
   AB/BA order, actual transfer/deployment and source-state unknowns explicit.
   Never treat a deleted tag as a cold store or pool incompatible fixtures.
4. Interleave resource-cycle acceptance with W2/W10: declared5 post-warmup cycles,
   30s idle/reclaim minima, next-use cost and real allocation/growth. Commands:
   `bench/native/diagnostics/resources.md`. Unknown cache/exclusive allocation
   stays unknown; do not count sparse nominal capacity as physical reclamation.
5. Resolve Cached+Fsync/Full, guest flush and promised persistence guarantees
   before storage leadership claims. Full and50ms refusal-cache branches need
   separate exclusive confirmations. Preserve250ms/default Fsync meanwhile.
6. Resolve known correctness gaps, freeze candidate/inputs and a complete
   per-cell status matrix. Implement actual frozen-readiness/resource-growth
   qualification admission; existing short W11 proofs must not be repeated as
   substitutes. Then execute the owner-requested full paired comparison,
   independent batch, fresh held-out app and finite12h W11 for each engine.

All work stays native ARM64/macOS. Installed-default behavior, disclosed
resource-matched default-driver results and identical-builder controls stay
separate. No mean may hide a CPU, memory, storage, recovery, tail, correctness or
durability loss. Full/workspace suites remain deliberate named manual gates;
qualification is conditional on the prerequisites above, never an automatic
check-command fallback. Continue until measured goals, explicit owner stop or
a specific blocker of all remaining authorized work.
