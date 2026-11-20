# macOS performance campaign: progress and continuation

## Status

**Active 2026-11-18 after new-host migration.** The development host moved to
a MacBook Pro (Apple M1 Max), 10 cores, 64 GiB (68,719,476,736 bytes), macOS
27.2.1 (26B131), Darwin 27.2.0. OrbStack 2.2.5 (bf842321…) is unchanged.
All raw results and VM assets from the old host are unrecoverable; every
pre-2026-11-18 measurement is historical to that host.

Reconstruction evidence is in [native-host-refresh-2026-11-18.md](evidence/native-host-refresh-2026-11-18.md).
Rebuilt and verified 2026-11-18: guest initramfs with the exact accepted
hash (`6ae4d3ab…`); guest kernel from pinned source/config/patches (`ea485341…`,
18,800,648 bytes, same size as accepted; `35087713…` is unrecoverable by
construction because builds embed a timestamp); sparse 1 TiB `data.img`;
signed host binary `be929fe2…` from main at `19c3fc8` (includes c7b4b90);
`conformance/smoke.sh` 21/21; offline Python discovery 318 tests OK with
`TMPDIR=$PWD/.work/tmp`, 0 skips.

The W8 common portfolio was refreshed as fixture **`w8-v5`** (never pool with
v2): `np-v5/postgres` and `np-v5/redis` are bit-identical to the v2 pins;
`np-v5/api` and `np-v5/marked` were rebuilt from the pinned fixtures with
digest-pinned bases; fixture input hashes and the Marked artifact hash are
unchanged (verified on both engines, 1,000 requests, exact payloads and
HTML). `assets.lock` records the new host, tools (python 3.15.1, docker
29.8.2, Compose v5.5.0), engines and rebuilt guest assets. Two stray
100%-CPU benchmark-harness greps from an earlier session turn were found and
killed on 2026-11-18; the user's own python-build session and OrbStack
Helper (`vmgr -handoff`, 100% CPU for 6+ hours) were left running and are
disclosed on every affected measurement. All code references now use w8-v5;
docs/evidence history was not rewritten.

The 2026-11-18 refreshed W2 matched-resource baseline
(`base-20261118T040927-4162`, 10 pairs, 50,000 ops, C8, seed 7, AB/BA) is in
[native-host-refresh-2026-11-18.md](evidence/native-host-refresh-2026-11-18.md#refreshed-baseline-this-host):
all 20 trials correct, zero errors; ctrs wins every latency/footprint cell
(rps 0.744, p99 0.611, footprint 0.359 vs OrbStack) but loses ~8.5% on
cpu_seconds_per_success (1.085, [1.052, 1.123]) — same direction as the old
host's system-CPU finding. Pilot quality, not qualification: disclosed
co-resident user load and a dirty worktree at launch; a quiet-window
confirmation batch from a clean tree is required before promotion use. The
earlier "missing provenance" note was a reporter defect (it ignored
`provenance.build_outputs`), fixed 2026-11-18; the trials carry all binary
and guest-asset hashes. The installed-default ctrs lane was 2 vCPUs until `148136f`; it is now half the Mac's cores. No campaign-owned measured job is active.

Later 2026-11-18 ([W2 IPI evidence](evidence/native-w2-ipi-2026-11-18.md)):
the quiet-window matched confirmation `base-20261118T081857-9b61` keeps all
latency/throughput/footprint cells as strict wins. CPU per success is
inconclusive (1.045 [1.015, 1.085]). An idle campaign `bootcheck2` daemon
was co-resident during both matched batches and is disclosed there. The
whole CPU gap is guest API system CPU, and new W2 guest counters (`7e88096`)
show 4.4× more call-function IPIs per success than OrbStack. SCHED_MC was
re-tested with those counters and rejected again: it raises the IPI count.
The first declared installed-default lane batch (`5e42acb`,
`base-20261118T090126-7b92`, ctrs 2 vCPUs vs OrbStack 9) is a strict win
on every W2 cell, including CPU/success 0.874 [0.824, 0.883] (pilot).

## Accepted and verified

All items below were measured on the old host (2026-11-15…17) and are not
portable to the 2026-11-18 host; they remain as design/outcome history.
See [native-host-refresh-2026-11-18.md](evidence/native-host-refresh-2026-11-18.md).

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

**Current (2026-11-19, second steering: coherence, then guest→host):**
live kernel k17 = patches 0001–0011 plus a new 0012 (echo proof and
rescan; the old two-second echo window, 0013 and 0014 are removed),
protocol 9, host binary and agent from `bf2ea2b`, e2e 508/508. Done this round:

- Filesystem coherence: an echo is skipped only when proven to be the
  guest's own change; FSEvents drop/must-scan/root-change flags, failed
  sends and agent-queue overflow become rescans with a bounded
  reconciliation walk; stream replacement replays from the last event id.
  Contract and regressions: `docs/design-bind-notify.md`.
- Keep/revert: 0013/0014 reverted (no paired W12 benefit).
- Admission: W12-watch misses/stale fail the trial; W13 claims are capped
  when the favored side was tool-limited; W13/W14 pair on pinned image
  identity (older cohorts flagged unverified); W13 ctrs trials record
  connections per transport (`GET /ctrs/relays`). The latest W2 records
  were saturation runs (no `--operations`).
- Guest→host: the NAT host relay (`3351ba9`) and published-port legs
  (`ad22161`) cut container→Mac upload to 2.23× (was 7.0×) and
  published-port download to 1.64× (was 5.1×), paired, 10 pairs, every
  connection over NAT. Leg-only regressed published-port upload to 1.14×;
  `439b14e` moves client bytes back to vsock (unmeasured). One NAT flow
  caps near 1.9 GB/s here. Evidence: "Guest→host transfer attribution".

- W14 CPU: the agent busy-looped while a container connect was pending
  (1.35 s agent CPU in one streaming run; 0.05 s after `bf2ea2b`).
  Host-bound split (Mac bytes over vsock) built and rejected: no gain.

Measured since (all D lane, 10 pairs unless noted; evidence
`evidence/native-w12-w13-2026-11-18.md`, matrix rows W2, W3-v4, W12,
W12-watch, W13, W14):

- Host-bound download over NAT 0.99 tool-limited (no regression);
  published-port upload on the split 0.96 inconclusive, CPU/GiB 1.17
  loss; published-port download still a ~1.7× loss (two invalid cohorts).
- W14 after the spin fix: streaming CPU 0.28 win; reconnect p99 0.42 and
  CPU 0.30 wins; persistent latency non-inferior (1.025), CPU 0.61 win;
  idle-resume CPU 0.15 win, latency inconclusive; fresh p50 5.6 loss is
  an admission confound (completion inconclusive), CPU 1.15 loss.
- W2 50k fixed work: latency/rps wins, CPU/success 1.03 inconclusive.
- W3-v4: every timing a win, not claimed until flush contracts are
  shown equal (bound recorded in the matrix row).
- W12 full-bind still a loss (~1.3); W12-watch 5-pair pilot 0.92.

Harness changes this round: `pyramid.py` entrypoint (README
"Entrypoint"); W13-overlap pairs on verified identity (`8b5709d`) and
carries resources (`689b63f`); admission on CPU busy outside the engine
and harness (`d211cae`, `886774f`), with a pre-pair idle-CPU wait.

Guest→host intervention (2026-11-20): on a quiet host the NAT network
carried a direct container→Mac flow at 3.9–5.3 GB/s and the relayed one
at 1.5–3.1, so the agent's copy loop was the limit. The agent now splices
bulk relay bytes (`4fdff1d`, e2e 508/508). Paired on that build:
published-port download 0.93 and container→Mac upload 0.95 (were 1.7×
and 2.2× losses), published-port upload 0.69, all tool-limited on both
engines, with ctrs's own time 0.56× / 0.43× / 0.77× its previous build
and OrbStack unchanged. Container→Mac download (Mac→container) looked
worse (8 clean pairs 1.27) in a cohort partly contaminated by a tool
edit; a held probe put the splice's cost there near 6 %.

Since: the NAT host-bound Mac→container direction went back to the copy
loop (`ade0b80`; download 1.21 spliced → 1.06, pre-splice 1.04); on that
guest (`e217587c…`, e2e 508/508) published-port download 0.92,
container→Mac upload 0.94, published-port upload 0.72, all tool-limited.
Two W13 tool rewrites were reverted (`a68248e` memoryview compare,
`60f6036` no in-trial gain): Mac single-flow loopback caps the tool.
W13-overlap is a scored loss (p99 1.70) attributed to guest CPU at the
5-vCPU default. Scored: W12-watch p50 0.90, W14 cancel wins. Ranked list:
`evidence/native-w12-w13-2026-11-18.md` "Ranked measured deficits".

Since (2026-11-20, later): W14 fresh scored on `completion_seconds`
(1.00, inconclusive; `base-20261120T052835-f228`); W12 mixed layout
(bind source, volume deps) 1.027 inconclusive (`-045710-1dc3`); the
W3-v4 flush probe recorded each engine's `fdatasync` cost (OrbStack
p50 0.6–2.0 ms, ctrs 0.26 ms; VZ offers only `Fsync` or `Full`).
buildx 0.37's docker-driver `--load` sent `prefer-image-digest`, which
ctrs's build gRPC rewrite rejected; `d692709` drops it (e2e 508/508),
restoring W6/W7. Change-tier pilots W1, W6, W7, W10 pass; costs are in
the `pyramid.py` registry.

Third steering (2026-11-20): default builds, the vCPU default as a
measured decision, watcher recovery after loss, then full-bind.

Done so far: the matrix is reconciled (`1e45fc1`); W4/W5 inputs build
alone (`runner.py prepare --only W4,W5`) and W9 finds its pinned image
(`bc996cf`); W4, W5, W9 one-pair pilots are correct on both engines;
concurrent builds each hold measured pairs (`.work/tmp/holds/<name>`,
`bf8512f`); a same-engine CPU candidate design (`--candidate-cpus N`,
`reporting.py --candidate`, pyramid `<cell>:cpus9`; `83a3315`,
`98eb949`) clones the default warm engine copy-on-write; ctrs CPU is
marked incomplete in machine-readable output when the Mac's NAT carried
the trial's connections (`adf2f67`). Watcher regression
`tests/watch-recovery.sh` (branch `fix/watch-recovery`, `a00f3d6`) fails
on main for both host loss and guest overflow; the fix is in progress
on that branch.

Next, in order:

1. Queue `.work/tmp/queue.sh` (log `.work/native-perf/matrix/q1.log`),
   serial: `w13-overlap:cpus9` (primary decision test), `w2-api:cpus9`
   + `w14-idle-resume:cpus9`, `w12-full-bind:cpus9` + `w6-build:cpus9`,
   then `w6-build:cohort` + `w7-buildx:cohort`. Report each with
   `reporting.py --candidate --match <run>`. Decide the default from the
   overlap tail plus the W2 CPU/success, idle-resume CPU, footprint and
   next-use budgets (`resource_cycles.BUDGETS`); if adopted, change
   `default_cpus`, record policy and candidate identity in
   `docs/decisions.md`, and re-run the D-lane cohorts at the new default.
2. Watcher recovery landed (`f291b04`, kernel patches 0013–0016,
   lane kernel `3e1b55bd…`, host `b2b1679f…`; e2e 508/0/0,
   watch-recovery.sh passes with and without dropped caches). Not yet
   deployed to `guest/out`: install it (`cargo xtask kernel`, then
   `cargo xtask all`) only after the measurement queue drains, then
   re-run W12-watch (a rescan now raises one event per uncached
   retained name; review note D3) and record the asset change.
3. Full-bind boundary: a two-virtiofs-device probe
   (`exp/fs-devices`, `CTRS_EXP_SHARE_DEVICES=2`, a noisy first run
   showed 1.2–2.5× more files/s split across two devices) tests whether
   the Virtualization.framework server serializes per device. Rerun in a
   quiet window before drawing a conclusion.
4. W6/W7: profile the largest confirmed losing build phase once the
   cohorts report.

Kernel experiments build in a labeled copy of `ctrs-kbuild`
(`ctrs-kbuild-exp-*`, label `dev.ctrs.campaign.run=bind-notify`) and are
tried with `CTRS_GUEST_DIR` pointing at a guest dir made with `cp -c`
(`data.img` is 1 TB sparse; never checksum it).

Tooling: `kache` hung debug test builds for over 20 minutes on 3 small
crates. Workaround: `RUSTC_WRAPPER="" CARGO_TARGET_DIR=.work/tmp/target-nowrap`.
The ownership resolver (`laputa-systems/stuff/repomod/which.py`) is not
present on this host, so no ticket was filed.

**Earlier (2026-11-18 afternoon, after `19d4eb2`):** the frozen first
comparison matrix is running serially on the Mac. Live assets are main's
`d9465bc2…` binary and `f3ab7344…` initramfs (half-close fix). Every cell is
10 AB/BA pairs, warm, `--resource-lane installed-default`, run from the repo
root with `TMPDIR=$PWD/.work/tmp`:

```sh
python3 bench/native/runner.py baseline --a ctrs --b orbstack --pairs 10 \
  --resource-lane installed-default --case W13 \
  --transfer-path {published-port|container-to-container|container-to-mac} \
  --direction {upload|download} --streams {1|4}
python3 bench/native/runner.py baseline --a ctrs --b orbstack --pairs 10 \
  --resource-lane installed-default --case W12 \
  --workspace-layout {full-bind|all-volume}
```

Frozen D-lane cells, in order: W13 published-port upload/1, download/1,
container-to-container upload/1, container-to-Mac upload/1 and download/1,
published-port upload/4; W12 full-bind and all-volume. W12 needs
`.work/tmp/kutt.tar.gz` and `.work/tmp/w12-image.tar` from
`bench/native/fixtures/w12/prepare.py`. Next: report each cell with
`reporting.py`, then rerun the M lane for the losing W13 path(s) and W12
all-volume to separate the 2-vCPU default from engine cost, then rank the
deficits in the matrix. Expand only to answer a concrete question.

**Earlier (2026-11-18, owner steering):** W2 tuning is parked. Status per cell
lives in [native-acceptance-matrix.md](native-acceptance-matrix.md). Next
milestone: one trustworthy W12 shared-workspace comparison and one W13
bulk-transfer comparison on this host, then a ranked deficit list. Then W14
connection lifecycle and the W3-v4 storage extension. Fixture work runs in
parallel worktrees, and measured jobs run serially on the Mac. Freeze a
small representative matrix before tuning.

### Superseded W2 next action

**Current (2026-11-18, after `5e42acb`):** attack the matched-lane W2
CPU/success gap at its measured boundary. Collect a wakeup-placement trace
on both engines at 9 vCPUs: per `sched_wakeup`/`sched_waking` target CPU,
whether the target was idle, and the waker/wakee API TIDs. Use the
existing profiler plumbing (`bench/native/diagnostics/w2-counters.md`,
`sched_trace.py`) and one matched block with exact 50,000-op C8 work. Then
choose between a scheduler-side guest candidate (for example, a newer
stable kernel's wake placement) and a VMM-side idle/IPI candidate. Do not
repeat SCHED_MC, LSE or HZ/PREEMPT. In parallel, re-baseline the other
cells (W1, W3–W10) on this host in both resource lanes, starting with W8
paired acceptance (queue item 3). Before launching any measured job, run
`pgrep -fl "ctrs daemon"`. A leftover campaign daemon silently serves
adopted trials.

### Earlier next action (2026-11-18 morning, partly superseded)

2026-11-18 host is reconstructed and the refreshed W2 matched-resource
baseline is recorded (see evidence doc). Before any qualification claim, the
entire per-cell matrix must be re-measured on this host against w8-v5 pins;
only then do the 2026-11-17 decisions (e.g. the leaf-only 49 Hz observer
validation plan at `experiment/w2-leaf-49hz` `4bf9107`) become actionable,
again in an exclusive window:

Use the [leaf-only command and paired plan](evidence/native-w2-equal-work-2026-11-17.md#leaf-only-observer-preparation)
from `experiment/w2-leaf-49hz` at `4bf9107`. First validate the guest
capture in one matched block using 50,000 exact C8 operations per cell.
Require every API thread, valid native samples and zero loss. Collect a
fresh paired overhead batch before using the profile for product selection.
All commands now reference `w8-v5` inputs (`.work/native-perf/inputs/w8-portfolio-v5/layout`).

The [W8 backing-allocation diagnostic](evidence/native-w8-content-state-2026-11-17.md#backing-allocation-during-deployment)
verified the three owned-file snapshots in a native diagnostic pair.
The [W8 cancellation diagnostic](evidence/native-w8-content-state-2026-11-17.md#interrupted-delivery-and-retry)
passed both native OrbStack conditions. Native ctrs reproduced a stalled
registry body read after the last pull client disconnected. The transport
fix wakes that read and passes the production-deadline regression with
the published 0.9.0 source plus the shutdown backport. Both native ctrs
cancellation and retry conditions now pass on the signed candidate.
[W5 mounted-input and phase-resource receipts](evidence/native-performance.md#w5-v3-mounted-inputs-and-resource-receipts)
pass native correctness on both engines. The [W1 warm restart proof](evidence/native-performance.md#w1-pinned-startup-and-database-restart)
passed on both engines with pinned images, exact writes and reads, and
the same owned database container and volume across the restart. Engine-cold
parity still requires an isolated OrbStack environment.
The [W10 recovery proofs](../bench/native/diagnostics/recovery-client.md)
passed API, database and queue interruption on both engines. The private
ctrs engine diagnostic passed with pinned images, a durable startup auth
file and exact acknowledged rows after the daemon and VM restarted.
The [W6 warm and uncached producers](evidence/native-build-boundaries-2026-11-16.md#w6-build-cache-conditions)
passed native compile-cache and artifact checks on the default builders.
The [W7 import and first-use producer](evidence/native-build-boundaries-2026-11-16.md#w7-per-build-first-use-receipts)
now proves compile and note cache behavior. Both engines passed all three
conditions for both apps with pair-specific note bytes.
The [W3 pinned transaction proof](evidence/native-performance.md#w3-commit-latency-and-persisted-rows)
passed all 300 commit receipts and exact persisted rows on both engines.
The [W9 fixed-work diagnostic](evidence/native-performance.md#w9-job-completion-measurement)
passed all four concurrency conditions per engine.
The parked W11 qualification branch `f0250a9` includes main through
`99ca94d` and verifies the declared fixture revisions against the case
manifest. Its [bounded checks](evidence/native-mixed-retention-2026-11-17.md#qualification-branch-refresh)
passed 49 W11 tests and 117 W2 tests. The asset lock remains in pilot status.
[W2 placement](../bench/native/diagnostics/w2-fixed-rate.md#native-placement-proof)
verified exact persisted work on the published port and guest network
in all twelve pinned trials. The two OrbStack offered-rate trials
completed all operations but exceeded the scheduling-lag budget.
W2 baselines now require the same pinned stack and prime the VM before
sampling. Both engines and both paths verified exact fixed work again
with matching input receipts and complete phase counters. Repeat pacing
admission in an exclusive window with the pinned baseline. Preserve the
10 ms budget and both failed receipts.
The [W4 v4 queue diagnostic](evidence/native-performance.md#w4-queue-latency)
verified the job and timing receipts at 1, 4 and 16 workers on both engines.
An equivalent [W10 engine interruption](../bench/native/diagnostics/recovery-client.md#owned-engine-recovery)
still requires an isolated OrbStack target.
Scored W3, W4, W6, W7 and W9 runs remain open.
The [qualification coverage inventory](evidence/native-mixed-retention-2026-11-17.md#qualification-coverage)
lists the next fixture gaps. Keep `assets.lock` in pilot status until the
contract, fixture versions and evidence are reviewed.

The reduced observer proof is complete. Source `7184d42` remains on
`experiment/w2-wake-entry-only`. Use the evidence record for its verified
probe coverage, scope and perturbation. A new run requires a distinct
observer policy or an exclusive confirmation window. The completed profiles
do not establish exclusive-store retry counts and give no basis for
repeating the rejected LSE or affinity candidates.

W11 v3's reviewed short proof is complete:
[exact results and command](evidence/native-mixed-retention-2026-11-17.md).
The 20,000-operation result leaves the 12-hour, growth, timing and durability gates open.

The final c3775ce functional job13731c9782f64101a2425063857ddf49 exits0 with
all four1000-operation trials correct,708 reads/292 writes each, complete phase
CPU and both periodic traces. Teardown is verified and all155 inputs rechecked.
Later failure-path corrections use offline regressions, not another identical
normal-path run. [Exact command and scope](evidence/native-sampler-lifecycle-2026-11-17.md).

Save pre/post gates and actual process, guest, power and thermal snapshots.
Ordinary gate0 has coexisted with hot Niceforge work. The owner subsequently
accepted some noise; a perfectly quiet window is no longer a prerequisite for
diagnostic W2 progress. Preserve unrelated work and disclose interference.
Keep inconclusive or structurally contaminated resource cells explicit. The
`-s` swap advisory is lane admission, not a performance gate.

W8 receipt validation is integrated at df1f418. Its source investigation and
remaining [content-state limits](evidence/native-w8-content-state-2026-11-17.md)
are explicit: new compressed identities/DiffIDs plus full delivery and runnable
contents do not establish guest-cache or page-cache absence. Preserve the66-test
component result and successful validation of two actual37-layer receipts.

Reconstruct the runtime from the repository. On the 2026-11-18 host the
reconstruction is done; the commands below reproduce it. Do not substitute
old `target/release` artifacts for the verified ones. Note: `cargo xtask
guest` rebuilds only the initramfs (hash must match `6ae4d3ab…`);
`cargo xtask kernel` rebuilds the kernel (expect a *different* hash — builds
embed a timestamp — but the same 18,800,648-byte size); `cargo xtask disk`
creates the sparse 1 TiB `data.img` from Docker. The bench suite needs
`TMPDIR=$PWD/.work/tmp`, and inline runner scripts must set
`runner.DOCKER = runner.find_docker()` before creating an `Engine`.

```sh
codex-campaign-closeout.py cancel
CARGO_ENCODED_RUSTFLAGS='' CARGO_BUILD_JOBS=4 cargo xtask guest
CARGO_ENCODED_RUSTFLAGS='' CARGO_BUILD_JOBS=4 cargo xtask kernel
cargo xtask disk
CARGO_TARGET_DIR="$PWD/.work/tmp/readiness-main-target" \
  CARGO_ENCODED_RUSTFLAGS='' CARGO_BUILD_JOBS=4 \
  cargo build --locked --release -p ctrs --bin ctrs
codesign --force --sign - --entitlements crates/ctrs/ctrs.entitlements \
  .work/tmp/readiness-main-target/release/ctrs
codesign --verify --strict --verbose=2 .work/tmp/readiness-main-target/release/ctrs
```

The 2026-11-18 signed host binary at main `19c3fc8` is SHA256
`be929fe2a81b960d0b4e2d3a02da864d91349eb9d1438cd74cd24be13795e9f2`
(6,617,104 bytes). The 2026-11-17 accepted binary (`2f37d02`,
`db20b210…`) and accepted kernel (`35087713…`) are unrecoverable history.
The guest initramfs hash is exact; the kernel hash is not asserted (see the
refresh evidence doc). Sparse guest disks require sparse receipts, never
whole-1TiB hashing.

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

Note (2026-11-18): queue items below were written against the old host.
None of their timing/reliability evidence transfers; every cell in the
qualification matrix must be re-measured against w8-v5 before item 6 can
close. The 2026-11-18 W2 matched-resource baseline batch is the first
current-host baseline. Fixture commands now reference w8-v5
(`.work/native-perf/inputs/w8-portfolio-v5/layout`).

1. Resolve W2 observer overhead using the exact next action above. Separate fixed work/offered load, saturation, on-CPU samples
   and off-CPU/wake latency. Commands and observer budgets:
   `bench/native/diagnostics/w2-counters.md` and `w2-fixed-rate.md`.
2. Parked `campaign/w11-bind-completed-cycles` binds the contract digest to
   `assets.lock` and validates the complete mixed workload and resource
   observation per cycle. The archived
   [native v4 proof](evidence/native-mixed-retention-2026-11-17.md#w11-v4-post-cleanup-observations)
   passed on both engines, with 181 frozen receipts unchanged. Complete
   the fixture producers, conditions and evidence needed to freeze the
   proposed cell contract. The parked
   `mixed_job.py` uses the finite supervisor for admitted qualification
   legs. Launch the two 12-hour legs after their admission requirements
   are satisfied.
3. W8: retained-image pin checks are integrated and pass 68 component
   tests. The eight archived native inspections agree with the pins.
   Complete exclusive paired acceptance. Keep the identity guard, shared per-pair inputs,
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
7. Benchmark-suite audit (2026-11-19), ranked by risk of a missed or false
   regression, then by wasted iteration. The entrypoint
   (`bench/native/pyramid.py`, README "Entrypoint") replaced the scratch
   queue scripts; the rest is open:
   1. Done: `reporting.py --anchor A --match B` compares each engine with
      itself across runs of the same workload and host. First use:
      container→Mac download vsock (`base-20261118T142833-063e`) against
      NAT (`base-20261119T133649-3bc7`) moved both engines 0.90 in step,
      so that cell's change is host drift, not the transport.
   2. Load admission (`f366b36`) judged the 1-minute load, which counts
      each engine's own vCPU threads: OrbStack's W12 trials ended at loads
      up to 11.8 from the same start as ctrs's, so pairs were rejected for
      the engine's behavior. `d211cae` records, per resource phase, cores
      busy outside the engine and harness (host_statistics busy minus the
      engine's counters minus the harness's rusage) and rejects above 2;
      records without it keep the load rule. Open: confirm on the first
      cohorts that the outside-CPU figure is near zero and alike for both
      engines on a quiet host (an engine process missing from the match
      would inflate its own figure). First cohort: quiet trials 0.9–1.4
      cores, ctrs about 0.2 above OrbStack in every W13 NAT pair, which
      points at host kernel networking charged to no engine process; the
      CPU metric undercounts ctrs on NAT paths until that is attributed.
   3. Metrics that do not measure what they name: W14 fresh p50 measures
      how many clients each engine admits at once (completion time is not
      a reported metric); W13 cells above half the loopback control are
      tool-limited on both engines; W14 reports every mode's metrics, most
      as "unmeasured". W13-overlap rejected every pair until `8b5709d`.
   4. A cohort with one load-rejected pair is invalid and reruns whole;
      on 2026-11-19 four of nine cohorts were lost that way. Topping up
      pairs was rejected: excluding pairs by their own end-of-trial load
      would drop the pairs where ctrs used the most CPU and bias toward
      ctrs. Instead `baseline --pair-quiet-load L` holds each pair until
      the 1-minute load is below L (decided before the pair runs); the
      scenario tier passes 4. Mid-pair foreign bursts are still rejected.
   5. Guest attribution: W13 already has an in-tree per-process guest CPU
      diagnostic (`diagnostics/w13_guest_cpu.py`, /proc snapshots around
      each transfer); use it for the remaining published-port download
      gap. Only the W14 agent syscall trace (tracefs, `common_pid==1`) was
      scratch; it diagnosed the spin fixed in `bf2ea2b`, so promote it
      only if W14 CPU (fresh 1.15×) needs it.
   6. W12 inputs (`kutt.tar.gz`, `w12-image.tar`) live in disposable
      `.work/tmp`; preflight fails when they are missing and names the
      rebuild (`fixtures/w12/prepare.py`, pinned by sha256 in its README).
      Open: W1, W4–W10 and W8 have no trial records on this host, so their
      costs are estimates until each runs once.

All work stays native ARM64/macOS. Installed-default behavior, disclosed
resource-matched default-driver results and identical-builder controls stay
separate. No mean may hide a CPU, memory, storage, recovery, tail, correctness or
durability loss. Full/workspace suites remain deliberate named manual gates;
qualification is conditional on the prerequisites above, never an automatic
check-command fallback. Continue until measured goals, explicit owner stop or
a specific blocker of all remaining authorized work.
