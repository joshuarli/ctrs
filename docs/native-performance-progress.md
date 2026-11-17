# macOS performance campaign: progress and continuation

## Status

**ACTIVE 2026-11-17 — owner authorized resume from HEAD. Campaign not complete.**
`codex-campaign-closeout.py cancel` returned “Campaign closeout is not active”.
**Current action:** test owned load-generator QoS after fixed-rate admission failures.
The [fixed-rate evidence](evidence/native-fixed-rate-2026-11-17.md) preserves
source fixes and all admission outcomes; no fixed-rate CPU comparison is admitted.
The W2 observer job c8051c089948484b9de838819d6812fe exited 1 before its first
block on the strict host gate. The attribution probe found active guest rustc
processes; OrbStack also reports a running unrelated Linux machine. An empty
Docker container list did not establish exclusivity. Preserve that work and
the original deferred job; do not restart or replace its failed blocks.
Client-path and native core/QoS investigations selected no policy change; see
[the W2 boundary evidence](evidence/native-w2-boundaries-2026-11-16.md).

The [build boundary evidence](evidence/native-build-boundaries-2026-11-16.md)
records three complete C build pairs with identical artifacts and no export/load
loss to pursue in this diagnostic. Its job exits 1 because ownership cleanup
correctly refused four images whose labels were omitted by ctrs inspection.
Fix 241c4c9 is pushed: stored labels are now projected and the config is read/
parsed once. The native regression fails on baseline and passes populated,
empty and absent labels on candidate 58f64738…; one affected Rust test passes.
Four exact-label-owned tags were recovered separately. Original failure retained.

Offline Rust job 51736a130ca44d35abe1a6cbd0337453 exits 0, owned cleanup complete:
six real uncached builds, 132 tests each, all native version/executable assertions
pass and all 81 input receipts remain unchanged. Raw/evidence above preserves
the three balanced pairs and busy-host limits. Exporting layers consumes roughly
five seconds, substantially more than the observed push status in the first pair;
this motivates a compression screen, not a conclusion that compression alone
causes the cost. The vendored variant does not qualify the original WAN-capable
Rust fixture. Its 134 packages/6,333 checked files are frozen in archive
58eae402daaf4823c6038c54386575b0c1c0c42c1b4cd92cfb2cfb8f9839067f.

Compression v2 job 3b197f66… is terminal exit 0, all nine builds/132 tests each
and identical executable assertions pass, cleanup complete, all 83 inputs
unchanged. Both lower gzip levels are REJECTED for the default: added layer
bytes grow 10.13% (level 1) and 4.53% (level 3), above the declared 3% budget.
CPU/wall signals are also noisy. No compression default changed. See the linked
build evidence for every round, raw sizes, physical growth and hashes.
The first screen dff9fcb… stopped after its default build on a scratch-accounting
KeyError: store layers have digest/size/media_type, not diff_id. It exits 1 with
clean owned teardown and remains separate. v2 verifies the base diff-ID prefix
through inspect, then counts following store layers; the saved accounting-repair
receipt recomputes the first run's added bytes from its retained records.

The [balloon evidence](evidence/native-balloon-2026-11-16.md) records the accepted
combined accounting repair from private source 4ecd599 and 45fd902. The host
includes boot reserve and SDK MiB rounding; the guest derives its target budget
from total minus available minus actual balloon memory. This is a target-budget
reading, not a physical-footprint metric. Quiet/growth/sleep settings, native
Linux-host cgroup calculation and wire/on-disk formats are preserved.

Fresh AB/BA job dbf8b674… passes all four exact 2GiB payload checks. Both baseline
headroom checks fail with available memory zero; both complete candidates retain
about 270MB and pass the unchanged practical oracle. All 89 inputs rechecked.
The host-only candidate's native failure 34664b99… remains preserved, not promoted
by itself. The first post-idle W2 profile 58659a68… also remains failed because
API TIDs change; it establishes no complete CPU-profile coverage. Separate fixed-
work W2 application proof 11b5fb9f… passes 5,000 operations, 1,486 exact writes,
1,986 persisted items and post-idle available memory 280,031,232 bytes. Affected
build proof 67e67a28… passes actual Rust/132 tests and C/make-check with identical
prior artifact hashes, no OOM kills/counter fallback, clean teardown and 102
unchanged receipts. The three host and three guest-parser tests pass; actual
Linux guest build and independent host/guest source reviews pass. Full suites
remain manual-only. No measured timing or global resource qualification follows.

Source trees `.work/wt/np-balloon-reserve` and `np-balloon-used` preserve original
commits and artifacts; all their workers/reviewers are terminal. Native candidate
host `.work/tmp/balloon-reserve-target/release/ctrs` is fda6246703f48c42a126fb0b63ecc246619e03760598cd569e6d0760207681f6,
6,613,968 bytes (+112). Private initrd is 6ae4d3abfb3be1f4dcc1edf200261a29e22ad96c922c2d677d5874df21abc8b2,
4,349,700 bytes, under `.work/tmp/balloon-model-assets`; kernel remains 35087713….
Main guest assets were not overwritten. Source integration has identical tested
files; deployment/release and final fresh-build reproducibility remain separate.

The combined accounting repair is pushed as **42b2b7d**, with the identical
source tested in the private branches above. W7 offline multi-stage profile
`.work/tmp/w7-offline-rust-profile-20261117/job`, ID
`f371a2bb92c04d2ea2128b9ad6b14ae3`, is terminal exit 0: all 18 builds/probes,
correct compile cache states, exact executable/version/note and owned cleanup
pass. Its shared-host timings remain ineligible and select no avoidable ctrs
export/load loss. Do not repeat this completed matrix or claim default parity.
Raw `analysis.json` separates build and verified-run commands; it is not an
inclusive command-to-run latency metric. See build evidence for limitations.

Compaction job f2313a753f744fca90698cd4ddb646c3 is terminal exit0 with clean
owned teardown and correct bytes. Its two additional-reclaim deltas are about
-9.6MB and1.7MB, missing the declared512MiB minimum: hypothesis REJECTED.
No product compaction/protocol change. All memory-policy pressure/installed-
default resource gates remain open. The latest timing preflight reported hot
unrelated Niceforge work and the OrbStack Linux machine remains running; timing
is deferred, never a pass. Preserve user work.

Resource source worker `usrw_25d0ca4b-7cd8-4e5c-9708-1bbf4520ccd5` is terminal
with accepted scoped commits f33ed41 and 0783b43, integrated as e974f63/44901ff.
Parent reviewed the initial diff and correction, including clean scope and proof.
Pinned images/API/binary and owned warmup are enforced; discovery follows lazy
VM boot. Shared Compose fallback now checks exact project labels/container IDs
(22ef421). Bounded `runner.py check resources` passes 63 tests/zero skips in
1.670s, including the new pin and cleanup regressions; full suites remain manual.

The [resource evidence](evidence/native-resource-cycles-2026-11-17.md) records
native job 0431cc8761244eb6950637c7736a01fb: exit0, clean teardown, complete
counter/application coverage for two 3-second cycles, all 87 receipts unchanged.
It deliberately leaves growth unknown below five cycles. Explicit 2CPU/8192MiB
and default sleep/quiet settings use candidate host fda62467/initrd6ae4d3ab;
the existing isolated image/build cache is retained and disclosed.

Five-cycle job bc957b41… is terminal exit0/clean cleanup, complete counters/data
and all87 inputs unchanged. Run `w2-resources-20261117T005046` FAILS unchanged
footprint budgets: post-warmup growth21,741,592B, return difference46,186,568B,
each over16MiB. Active-disk growth98,304B passes; exclusive/cache size unknown.
See [resource evidence](evidence/native-resource-cycles-2026-11-17.md).
Its pre/post simple host gate exits0, but unrelated running OrbStack Linux
machine/exclusive qualification remains unresolved. Preserve the failed cells.

Attribution job1b5e52c1… is terminal exit0/clean cleanup, all87 receipts unchanged.
All12 fixed-work trials/8,000 operations pass; guest OOM counts stay0 and no
fallback. Constant probe distinguishes this fixture. Native VM footprint grows
about29MB while guest cache stays flat. Explicit cache release frees184MiB guest
cache but only48KiB native footprint: no useful reclaim. Default60s sleep closes
the disk and removes the old helper; wake checks actual new VM/assets/API and
passes another exact W2 stack. Transition CPU/wake timing/persisted recovery
remain unqualified. Feature admission c8d90a49… exits0/clean; actual balloon has
neither negotiated hinting nor reporting. No guest-only reporting experiment or
product cache/idle change. Resource evidence above retains exact results/hashes.

W9 job18475b48… is terminal exit0/clean:384 exact build/test jobs in3 AB/BA/AB
pairs, concurrency1/4/8/16, complete native counters and89 unchanged receipts.
No declared ctrs contention loss selected. W3 WAL jobda7234e1… also exits0/clean:
6,000 committed transactions, exact all-row checks before/after6 DB restarts,
1,000 syncs/320,607 WAL bytes per leg, complete resources and89 unchanged inputs.
Both retain17CPU/45091MiB resident controls and shared-host limits; no win claimed.

[CI/WAL evidence](evidence/native-ci-wal-2026-11-17.md) records the actual cost
boundary: fresh paired Fsync/Full job1198bea5… exits0/clean with all94 inputs
unchanged. Full WAL sync costs3.7–3.9s per1,000 commits versus Fsync0.09–0.11s.
Their contracts differ; this is not equivalent-durability speed credit. Both
fresh signed artifacts are6,613,984B; actual binary/boot hashes checked.
Private Full be06882 is unmerged. Uncached+Full b030772 is REJECTED by job
4240274e… (all6 correctness/resource proofs pass,97 inputs unchanged) because
the predeclared10% wall improvement/every-pair lead are absent. Main stays Cached+
Fsync. Original Full branch/proofs remain parked; host power loss remains unknown.

Read-only scout `usrw_140c29f3-0a3f-4add-a8a3-54747a939f23` is terminal,
zero changes, source review only: it did not inspect raw JSON at the supplied
worktree paths; parent inspected the actual main-checkout records. It found no
per-commit engine RPC and recommends guest syscall/block timing. No host trace
was run: `sudo -n /usr/bin/true` requires a password; preserve host settings.

Helper worker usr w_cd854af3 is terminal; scoped source integrated through d209805.
Parent reviewed initial/correction diffs and added pre-mutation ownership checks,
stock10-byte rwbs validation and monotonic per-instance clock. Bounded resource
selection passes70 tests/zero skips; narrow helper7 tests pass. Native v1/v2
admission failures are preserved separately: isolated PID view, then rwbs width.
Trace-v3 job3225b0d7264d4a21b1fb4490f667911f exits0/clean: exactly1,000 successful
fdatasync pairs and1,000 block flush issue/completion pairs; zero misses and all
17 CPU loss stats zero. Exact data survives checkpoint/restart, all95 receipts
unchanged. Block wait is98.585% of syscall wait; no per-commit RPC remedy selected.
Direct owned-file job92ce290a552747238e0fb9c7b9766707 exits0/clean, all96 inputs
unchanged: three Full-sync phases already take about3.1–3.4s/1,000 calls versus
the guest block total3.664s. This boundary probe does not establish a hard floor
or permit subtracting unlike workloads into a VZ overhead estimate. Evidence:
[CI/WAL record](evidence/native-ci-wal-2026-11-17.md). No source/native job active.

**Exact continuation:** finite native job
`70b5083650a94878b2641d5498a6afe9` is active under
`.work/tmp/w2-rate-c128-cpu-20261117/job`. It owns the native workload. First stage
requires six alternating engine admission legs at C128/2,000req/s/2,000ops; only
zero misses/errors/incomplete work allows the second-stage six-pair CPU matrix.
That matrix rotates closed-loop/500/2,000req/s with 10,000ops each, matching seeds
within pairs and varying between pairs. Source and all relevant inputs are frozen.
Do not modify them while the job runs. First invalid cell stops the matrix;
retain partial data and never replace it. Consume terminal status once, verify
all frozen receipts, then run prepared matrix/analyze.py and decide next cause.

Source worker 7611c2e2… is terminal succeeded. Initial/full correction diffs and
scope reviewed; parent bounded W2 check passes56 tests/zero skips. Source integrated
as cae881b/ab78613, original v2 unchanged. C16 native admission f569a927… exits0/
clean with all12,000 operations on time and95 unchanged inputs. First C16 CPU
matrix d71f8067… exits1/clean at round1 ctrs 2,000/s: all10,000 operations correct
but52 late starts, all explained by preceding same-client response queues. It
stops with three records, no replacement. New C64 control's32ms per-client interval
exceeds observed21.586ms maximum service. C64 job8570347e… then fails admission
on final OrbStack leg with1197 response-queued starts, max service47.383ms; all97
inputs unchanged, exact application/counters/cleanup pass, larger matrix never
launched. New C128 interval64ms is the final capacity control; no further count
escalation on failure. All conditions share its partition.
Canonical v3.2 is used. No product or workstation policy changes, no win claimed.

Timer-only jobs a7d66088… and bf483e8f… are terminal exit0/clean. Mach absolute
wait retains misses. Kqueue candidate delivers all slots on time across six
alternating pairs versus every sleep control missing delivery. This isolates a
client timer admission boundary, not an engine CPU win. See fixed-rate evidence.

QoS job 895a24ed… is terminal exit0/clean, all 99 receipts unchanged. All 24,000
application operations and native counter checks pass, actual worker QoS21/25
matches conditions, but every elevated-QoS leg misses delivery. Reject this
policy; do not repeat its matrix. Failed initial coordinator 7445817a… remains
separate exit1/clean. No product/workstation policy changed. Evidence linked above.

Source worker f628bac1 is terminal incomplete; parent reviewed/took over its
proposal and landed separate v3 rate client e01c298 and absolute-deadline fix
fcf5468. Original v2 and its portfolio hash are unchanged. Bounded W2 selection
passes 53 tests/zero skips. Priming admission 949ea73c… and client-capacity
admission 2dad081d… both complete all exact application/counter checks but fail
rate admission. Preserve every invalid leg; do not repeat either matrix.

Seek consistent >=10% API cgroup CPU-per-op contrast from pacing across all six
rounds; inspect both engines and the relative contrast. Timings remain diagnostic
without exclusive host and observer qualification. Full qualification and
comprehensive suites remain manual-only; no W11 soak is running.

Do not stop user containers or silently adopt wrong binary/assets. Preserve
default-sleep/identity unknowns, active-disk ownership and installed-default
versus resident controls. Full qualification remains manual-only.
Canonical W2 observer confirmation still needs a genuinely exclusive window.
Do not repeat completed W7/build/compression/compaction matrices or unchanged
short W11 proofs. Keep `/private/tmp/ctrs-w6-vendor-20261116` for provenance.

Affinity diagnostics completed;
[evidence](evidence/native-affinity-2026-11-16.md) retains all nine blocks.
The subsequent [LSE-only experiment](evidence/native-lse-2026-11-16.md) is REJECTED
for promotion: three complete pairs/600k correct operations and valid actual-boot
and runtime-LSE audits, but no required API/engine CPU reduction. All 84 input
receipts remained unchanged. Raw job `7edd9d98fb3648d38b4750e8b955801d` is terminal
exit 0, cleanup complete. Private kernel branch/assets are retained, unmerged;
do not repeat or expand this weak candidate into resource/full-build confirmation.
The earlier serial-audit failure remains separate and preserved in the evidence.

Completed native job `.work/tmp/w2-client-path-explore-20261116/job`, durable ID
`20c045e9e8f84ccbaf4c7fe98a4fc7a3`, exits 0, cleanup complete. Six blocks rotate host
and guest clients over three rounds, both engines and off/on modes, 50k operations
per phase (all 24 phases/1.2M operations correct). Default affinity, stock live Image,
17 vCPUs, 45,091MiB and host binary 37bec61b… stayed fixed. Frozen inputs are
unchanged. The guest variant includes client
CPU in aggregate engine totals, so host-to-guest engine-CPU ratios are invalid.
Host Python 3.14 versus guest pinned 3.13.18 and changed delivery cadence also
prevent treating this as pure forwarding-CPU isolation. All timings are unqualified.

Guest-client source worker `usrw_cf2ef94c-a637-4d5a-b396-3da171e46bde` is terminal
succeeded, original f2d394c retained in `.work/wt/np-w2-client-path`; integrated
6b62edd with parent fixes e271003. Sixteen focused tests and bounded W2's 48 tests
pass. Native v2 proof `w2-guest-client-cpu-20261116T195940-69a3` passes all four
5k phases, exact payloads and cleanup on both engines. The initial v1 proof cdfc
passes ctrs but fails OrbStack's tmpfs source-copy visibility before work; it is
preserved, not pooled. Both engines now use live exec streams outside measurement
for bounded tmpfs transfers; source hashes are verified and guest v2 is distinct.
Native cancellation a41c, driver/receipt `.work/tmp/w2-guest-cancel-20261116{.py,/}`,
waits for the actual peer load process then sends TERM to its identified child.
Original exit -15 is preserved, cleanup has no errors and the owned VM disk is
closed. No kernel or affinity runtime policy has been promoted.

Resume steering: storage repair, pinned W8 warmup, service-resource coverage and
fixed under-pull work are accepted below. W8 paired execution/reporting is
integrated as 2769bd0 with parent repairs through 78c9145. Source worker
`usrw_93079a50-48c8-474d-a095-65c3791b64c5` is terminal succeeded. Its retained
tree `.work/wt/np-w8-paired` preserves the original bfcf4a9 source for review.
Under-load diagnostic pair `w8-paired-5db1bf25cd77` passes both legs,
24 complete scopes, identical paired inputs, actual candidate/guest hashes and
readiness before background drain. Reporter has no metadata gaps and correctly
rejects all diagnostic timings (zero ratios). Command SIGTERM proof
`w8-paired-281d436905d4` preserves -15, client -15, owned stack cleanup and a partial
1/2-record receipt; interruption is now distinct from ordinary failure.
Two-pair default-mode proof `w8-paired-9e18895467fc` completes real AB/BA order,
21 scopes each and exact outputs, but does NOT prove continuous hot residency:
daemon PID 26527 persists while VM 26530 becomes 27136. The owned daemon log
records normal `VM asleep` at 02:15:45 UTC, idle_s=60; source
`Engine::start_sleeper`/`sleep_if_idle` confirms no runtime defect is established.
Resident proof `w8-paired-f8cf4ddcd42e` then passes all four real AB/BA legs and
21 complete scopes each. The ctrs daemon and VM kernel-start identities remain
unchanged across a 100.553-second between-trial gap. Shared inputs match within
each pair and differ between pairs. `resident-proof.json` captures those facts.
Only the owned benchmark daemon uses `CTRS_IDLE_SECS=0`. Caller environment is
restored, adopted daemons with unknown idle policy are refused, and identity
drift fails validation. This is a **resource-matched resident control**, not the
installed-default lane. Product idle policy and idle/wake/reclaim cells are open.
Both diagnostic reports reject all timings and produce no ratios. Planned and
completed record counts, source and actual running binary hashes, raw workflow
boundaries, nested scopes, host snapshots and reports are retained per run.
Native `w8-image-id-guard-20261116` accepts unseen IDs and rejects cached variants
on both engines using the correct store-specific ID kind. Failed engine discovery
cannot be hidden by fixture counters. All 201 harness tests pass.

Command: `TMPDIR=$PWD/.work/tmp python3.14 bench/native/runner.py w8-baseline --layout .work/native-perf/inputs/w8-portfolio-v2/layout --ctrs-binary .work/tmp/disk-expand-target/release/ctrs --pairs 2 --diagnostic`.
Add `--under-load` for the distinct fixed-work mode. Generic proxy W8 scoring
entry points now refuse with this replacement command. CLI/sampler footprints,
allocated storage, sub-API guest-cache absence, frozen observer acceptance,
installed-default comparisons and full qualification remain unproved.

Completed job `.work/tmp/w2-affinity-explore-20261116/job` exits 0 with cleanup
complete: nine blocks, 36 correct phases, 1.8 million operations, all affinities
verified and 81 unchanged input receipts. All timings and qualification remain
ineligible. The linked evidence preserves every round, contention and raw profile
counts. Private kernel experiments may proceed under the owner's extra-experiment
steering; exclusive observer confirmation and all resource/regression gates remain
required before promotion or speed claims. Do not repeat the completed matrix.

The preceding stock exploratory batch stopped on its first block
`w2-cpu-20261116T185652-c15a`: an analyzer falsely interpreted the valid kernel
symbol `blkcg_maybe_throttle_current` as a perf throttle diagnostic. Fix 2756b7f
distinguishes parsed frames from diagnostic text while still rejecting raw
loss/throttle records. Twelve focused CPU tests pass. Reanalysis is saved beside
the original failed receipt; the aborted batch is not silently converted into
completed pairs. Niceforge/OrbStack contention remains recorded and unqualified.

Shutdown classification fix ae7b63e sets the existing expected-stop flag only
immediately before intentional VM shutdown; a crash during container grace still
uses the unexpected-loss path. Native `conformance/vm-stop.py` exercises idle,
wake, injected loss/recovery and SIGTERM. Baseline 37bec61b… FAILS with unexpected
count 1→2; signed candidate 6f4dff55… PASSES with 1→1. Both clean up successfully.
Receipts: `.work/tmp/vm-stop-dg57yw9k/` and `vm-stop-821ch53a/`. Candidate size
6,651,912 bytes versus baseline 6,613,856; this is a correctness repair, not a
performance promotion. `cargo check -p ctrs` and the isolated two-job release
build pass. No guest, durability or installed-default idle policy changed.

Bounded offline commands now require an explicit component:
`python3.14 bench/native/runner.py check w2|w8|resources`. Missing/full selections,
zero tests, skips, import errors, failures and timeout fail closed. Parent checks:
7 selector contract tests; W2 44 tests in 1.612s; W8 62 and resources 56 tests
pass. Full discovery/workspace/conformance/qualification remain manual-only;
see `bench/native/README.md`. Do not repeat completed W8 or short W11 proofs.
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
W8 under-pull source e59d6f9 plus parent fixes passes native
`w8-unique-20261116T172543-a4b5` on both engines. Fixture version
`w8-v4-under-pull` uses the unchanged pinned W2 worker in a separate instrumented
client: 50,000 operations (35,159 reads/14,841 writes) each, zero errors, all
accepted DB payloads exact, every pull interval contains successful completion
callbacks, all 23 engine+fixture resource phases complete. Full variant transfer,
markers, foreground application, Marked artifact and retained image checks pass.
Both legs exit 0 and fixtures clean up. Client sequence numbers reject duplicate
completion records; truncated journals cannot skip cancellation ownership receipts.
Source worker `usrw_cb21055c-727d-4113-aa37-a48adb70df80` is terminal succeeded;
its scoped diff was parent-reviewed. Four local HTTP/fault regressions, 16 variant
tests and all 191 harness tests pass. Layout
`.work/native-perf/inputs/w8-portfolio-v4-pinned-20261116/`, seed
`ctrs-w8-v4-pinned-proof-20261116-1`. Parent/native helper hashes match the recorded
client/controller receipts. No timing or tail-latency performance claim.

Retain failed `w8-unique-20261116T172040-cd89` (legacy API tag correctly rejected,
zero pulls) and partial `172130-2195` (ctrs passed, OrbStack rejected config-ID
lookup). Small metadata probes proved the current stores resolve different
immutable IDs: config on ctrs, manifest on OrbStack, with identical pinned DiffIDs.
The background stack now selects those exact IDs and records the kind; identity
checks were not weakened. These failed/partial runs are not pooled or replaced.
Native SIGTERM proofs `w8-cancel-20261116T172850-ctrs` and
`w8-cancel-20261116T172854-orbstack` each preserve child/parent signal 15, report
complete cleanup, no receipt error and zero remaining project containers. Driver
`.work/tmp/w8-underpull-cancel.py` enters the real baseline context, signals itself
after readiness, then verifies the saved project filter before stopping its engine.

Warmup legacy-tag dependency is removed at 612441e. The background stack and
warmup share `baseline_image_reference`, which selects the verified immutable ID
kind for each store. Native `w8-warm-pin-20261116T173929` passes both engines;
ctrs uses a NEW isolated root containing only the common API manifest, explicitly
rejects inspection of the absent legacy tag, verifies pinned DiffIDs, completes
the guest warmup and leaves zero owned containers. OrbStack uses its immutable
manifest ID without tag changes. Twenty focused tests pass. Driver
`.work/tmp/w8-pinned-warm-proof.py`, receipts under the run's engine directories.
Startup/preconditioning remains outside warm resource cells.

Next executable source action: connect the v3/v4 path to a canonical W8 paired
command and the existing reporting record format. Prepare one unique immutable
artifact before each pair, alternate engine order, retain warmed engine ownership
across the batch, record whole-workflow resources without summing nested phases,
and include per-pair artifact receipt checks. Move foreground readiness before
background drain so pull-to-health does not include an artificial join. Keep the
pinned W2 driver unchanged and histories separate; retire scoreable proxy entry
points once the replacement is usable. Diagnostic mode must explicitly invalidate
timings; host-busy runs cannot produce favorable statistical ratios.
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

Regression: `TMPDIR=$PWD/.work/tmp python3.14 -m unittest discover -s bench/native -p 'test_*.py'`.
Before scored work, remove only verified campaign-owned diagnostics and certify
exclusivity. Gate exit 0 is insufficient: saved snapshots show hot Niceforge/fz
jobs despite aggregate-load success. Do not stop unrelated work. Installed-default,
resource-matched default-driver and identical-builder controls stay distinct.
Report wins/parity/losses/inconclusive/invalid/unmeasured per dimension; no geometric
mean may hide CPU, memory, storage, recovery, tail, correctness or durability loss.
Continue until demonstrated goals, explicit owner stop, or a blocker of ALL work.
