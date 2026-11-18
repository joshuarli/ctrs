# Host migration handoff (2026-11-17)

The ctrs development host moved to a new macOS machine via a fresh clone.
This records what was deleted, what must be reconstructed, and where the
campaign state lives. Read
[native-performance-progress.md](native-performance-progress.md) for the exact
next campaign action and [native-performance-retained.md](native-performance-retained.md)
for the branch retention ledger; neither is duplicated here in full.

## What changed on the old host

- Every local branch (52 that were not on origin, including the parked
  qualification and experiment branches) was pushed to origin on 2026-11-17.
  A fresh clone now carries all source work. No branch was merged into main:
  none qualified (each is patch-equivalent, parked, rejected, or unreviewed
  W11 admission work), and the retention ledger forbids merging to empty
  checkouts. Main was unchanged except for this document.
- All 26 checkouts under `.work/wt/` were removed after their ignored files
  were inspected and discarded (Python `__pycache__`, `target/`, `guest/out/`
  per worktree). Each branch, including parked and rejected ones, survives on
  origin; a checkout is recreated with `git worktree add .work/wt/<name> <branch>`.
  `worktree-retire` refused every one as "not integrated into main", which is
  expected for deliberately parked lanes; inspection and the pushes above are
  what make the removal lossless.
- `.work/` was deleted outright: VM engines (~21 GB), raw benchmark results
  (~13 GB), W8 portfolio inputs (~3.6 GB), tmp fixtures and scratch (~22 GB),
  worktree build artifacts (~4.2 GB) and the unrelated `stuf89` checkout.
  Nothing under `.work/` can be restored. The written record in
  `docs/evidence/` is unaffected.
- `resume.md` (untracked checkpoint) was folded into this document and removed.

## Reconstructing on the new host

1. `git clone` the repository. Confirm `git log --oneline origin/main -1`
   matches this document's base commit.
2. `/guest/out/` is gitignored and does not move. Rebuild the guest assets
   with `CARGO_ENCODED_RUSTFLAGS='' CARGO_NET_OFFLINE=true CARGO_BUILD_JOBS=4 cargo xtask guest`.
   Verify against the pinned hashes in native-performance-progress.md
   (kernel `35087713…`, accepted initrd `6ae4d3ab…`); do not substitute other
   artifacts.
3. Reconstruct the signed host binary per the commands in
   native-performance-progress.md (accepted source `2f37d02`; signed binary
   SHA256 `db20b210…`). `.work/release/` and all prior signed binaries are gone.
4. Scored W2/W11 runs need an exclusive window and `perf-gate-ready` before
   sampling; the 49 Hz leaf-only observer validation is the exact next action
   (branch `experiment/w2-leaf-49hz` at `4bf9107`, on origin).
5. Recreate working directories as needed: `mkdir -p .work/wt .work/tmp`.
   `.git/info/exclude` already ignores `.work/`.

## Not recoverable without re-measurement

- Raw trial receipts and engine/VM state under `.work/native-perf/` and
  `.work/tmp/` (CPU/wall/attribution data behind every W-series claim).
  Summaries and decisions live in `docs/evidence/`; re-running is the only
  way back to raw data.
- The pinned W8 portfolio artifacts (`portfolio.tar` SHA256 `99dbbad6…`,
  extracted OCI layout, inspections, export receipt). Regeneration path is
  documented in [bench/native/fixtures/w8-v2/README.md](../bench/native/fixtures/w8-v2/README.md):
  pull the source images by the exact IDs in tracked `portfolio.json`, re-save
  through an explicit Unix endpoint under a new owned tag namespace, extract
  with `tarfile.extractall(filter='data')`, and validate with
  `registry_portfolio.prepare_pinned_portfolio`. Publication/reproduction on
  another host was already open before deletion.
- The W8 portfolio was also on disk in OrbStack's shared store on the old
  host; the new host needs the re-export. Pinned manifests are in
  `bench/native/fixtures/w8-v2/portfolio.json`.

## Campaign state at the move

- W2: pinned fixed-work verification complete on both engines and both paths;
  paired API system-CPU ratio 2.020 at 17 vCPUs; OrbStack completed all
  10,000-request paths but missed the pacing budget on two offered-rate
  trials. Prime the VM before sampling; preserve the 10 ms budget and both
  failed receipts. Next: leaf-only observer validation in an exclusive window
  (see exact next action in the progress file).
- W4: both engines verified 200 jobs and 400 exact artifacts at 1, 4 and 16
  workers; all 45 focused tests passed.
- W11: parked branch `campaign/w11-bind-completed-cycles` (f0250a9, pushed)
  includes main through 99ca94d. The refreshed branch and its 49 admission
  tests pass; the reviewed evidence matrix, comparable durability proof and
  both 12-hour runs remain open. `campaign/w11-required-cells-20261117`
  (8aa9b65, pushed) holds the reliability-dimension continuation;
  `campaign/w11-admission-20261117` (5bcf48a, pushed) is the parked admission
  tree. Do not merge any of them before review and the native v4 proof.
- W1 engine-cold parity and W10 whole-engine recovery still need an isolated
  OrbStack target. Scored W3/W4/W6/W7/W9 remain open.
- `perf/zstd-load`, `experiment/np-lse-only`, `experiment/np-preempt-full`,
  `experiment/np-gzip-backend` and `campaign/np-sched-mc` are rejected
  candidates (see progress file and ledger); their branches are preserved for
  provenance, not for promotion.
