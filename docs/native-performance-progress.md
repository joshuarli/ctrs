# macOS performance campaign: progress and continuation

**ACTIVE — measurements need qualification; OrbStack leadership unproven.**
Owner steering: 2026-11-15. Contract:
[`campaign-native-performance.md`](campaign-native-performance.md).
Maintain this file in place as the single queue/checkpoint. Append compact
experiment outcomes to `docs/evidence/native-performance.md`, not a second
queue or turn-by-turn status diary.

## Resume here

**Current task:** NP-04 — default-driver build→load→first-use path.
**E2E-verified and committed `3b5f5ba` (2026-11-15):**
`docker buildx build --builder default --load` on the warm ctrs
socket now uses the **docker driver** end-to-end — h2c `/grpc`
(HPACK relayed verbatim, flow-control windows honored), `/session`
bytes spliced through `Control.Session` with the client's
`X-Docker-Expose-Session-*` headers forwarded as gRPC metadata, and
the lone `moby`/`docker`/`image` exporter rewritten to a mirror push
with retag-on-trailers/discard-on-reset. Smoke `np-smoke:test`
landed in `docker images` with no tarball/archive load; W7
pairs-1 smoke `base-20261115T123903-a5ff` all-green on both engines
(ctrs warm/incr roughly half of OrbStack's). Runtime fixes folded
in: buildkitd listens on unix+TCP (buildctl probe kept), the first
client DATA frame per h2 stream is now actually buffered for the
SolveRequest rewrite (was unreachable), buildx's deprecated
exporter fields 3/4 no longer fail the rewrite closed, and the
benchmark's isolated buildx config had a stray docker-container
`default` builder removed so `default` resolves to the docker
driver exactly like OrbStack's. `cargo test -p ctrs` 174/174.

**Mirror retag bug found and fixed `10cfff4` (2026-11-15):**
first baseline rerun `base-20261115T125538-2dc3` finished W6 10/10
pairs all-correct, but W7 ctrs pairs failed `*_note` correctness —
warm/incr rebuilds produce content-identical manifests whose PUTs
buildkit skipped because `manifests_ref` resolved `sha256:` digest
refs against a process-global map (a digest pushed under an earlier
build's repo answered GETs for every repo). Result: nothing recorded
per-repo, `take_pushed` dropped everything, user tags stayed stale.
Fix: `PUSH_REPO_MANIFESTS` tracks digests PUT per repo; `sha256:`
GETs 404 for repos that never received the PUT, forcing buildkit to
re-PUT and record. Verified: two consecutive W7 default-driver
trials pass with retags succeeding on identical rebuilds
(`run-20261115T131124-7962`, `run-20261115T131147-d5f1`).

**Qualified results (2026-11-15, commit `c9a5852` tree):**
- W7 `base-20261115T133627-c5f9`: 10/10 valid pairs, all correctness
  green. Strict wins on 5/6 cells (hyperfine warm 0.536, incr 0.537,
  httpie uncached 0.836, warm 0.520, incr 0.550); hyperfine_uncached
  non-inferior 0.955 [0.892, 0.983]. Both previously inconclusive
  httpie cells resolved to strict wins.
- W6 `base-20261115T134715-7cc9`: 10/10 valid pairs. zlib strict-win
  0.586 [0.521, 0.699] — prior 1.222 default-driver loss eliminated.
  rust inconclusive 0.963 [0.944, 1.059] — upper CI exceeds the 1.03
  gate bound, so a 20-pair W6 run is in flight to tighten it.
- One transient observed: a single buildx `/session` RST ~100 ms
  into a zlib solve (pair 7 of `base-20261115T131324-d1cc`, 1 in ~40
  session streams; buildkitd logged client-side context canceled).
  Not reproduced since; watch recurrence.

**Intermittent build failure under investigation (2026-11-15):**
~1/150 default-driver builds fails with buildx reporting
`Canceled: context canceled` / `error reading from server`. Two
distinct causes found so far:
1. Mirror manifest PUT dropped the conn (EOF) when a manifest
   referenced blobs still committing from a concurrent push —
   buildkitd logged `Put .../manifests/sha256:...: EOF` and retried
   ~15x before failing the solve. Fixed `f3adade`: record_manifest
   now waits up to 20s for config+layer blob presence (atomic-rename
   commits make presence proof) and the PUT arm answers a proper
   `400 BLOB_UNKNOWN` registry response instead of EOF.
2. `/session` stream RST_STREAM error code 3 (h2 FLOW_CONTROL_ERROR)
   from buildkitd ~100ms into a solve — seen at 21:21, 22:12, 22:14,
   22:37, 22:45 UTC and again 2026-11-16T00:15:56 (clean W6 pair 6),
   across W6/W7 trials including non-concurrent baseline patterns.
   NOT yet root-caused. Instrumentation in tree: GOAWAY/RST error
   codes on both relay directions, per-frame session rx debug,
   send-window overdraw warnings, and (newest commit) a cumulative
   sent-byte counter + window snapshot logged on session RST —
   distinguishes oversend vs protocol violation. The newest binary is
   built+signed but NOT yet deployed: the in-flight clean baseline
   must finish first; restart the warm daemon with
   `CTRS_LOG=debug` afterward to catch the next occurrence.

**Final clean baselines — results (2026-11-16):** W7
`base-20261115T163439-18ee` QUALIFIED-clean: 10/10 valid, all six
metrics strict-win (hyperfine 0.890/0.399/0.438, httpie
0.785/0.414/0.457). W6 `base-20261115T160823-a303`: 18/20 valid —
pairs 6+16 ctrs failed on the `/session` RST code-3 flake (zlib
build canceled); ratios on valid pairs strict-win (rust 0.924,
zlib 0.545) but correctness failures disqualify. Evidence recorded.

**ROOT CAUSE FOUND + FIXED (2026-11-16):** the `/session` RST code-3
flake was our h2 flow-window accounting, not buildkitd. Forensic run
caught it live: `session stream reset code=3 sent=785951
conn_win=69800 stream_win=53317` — windows still positive, i.e. we
had NOT overdrawn per our own books. Reading grpc-go
(`internal/transport/http2_server.go:813`, `flowcontrol.go`)
showed buildkitd's grpc layer resets a stream when its inFlow
`pendingData+pendingUpdate > limit+delta`, and its limit tracks
BDP-driven SETTINGS updates. Our `Win::settings()` reset the
default window AND cleared per-stream state on every
SETTINGS_INITIAL_WINDOW_SIZE change; per RFC 7540 §6.9.2 an
existing stream's window must shift by the delta. With BDP growth
mid-stream we over-counted by bytes already sent → overdraw →
RST_STREAM code 3. Fixed: `settings()` now applies the delta to
each tracked stream window. Also fixed a session sender race:
it now stops once the builder ends its side (`peer_done`), with a
dead-aware `wait_dead` so a parked sender can't hang; every exit
path sets both flags before `join()`.

Debug hunt `base-20261115T165554-d81a` (20/20 valid, strict wins)
was diagnostic-only (CTRS_LOG=debug). Post-fix clean W6 20-pair
`--driver default` in flight — log
`.work/native-perf/logs/np04-w6-postfix-20261115T173857.log`,
daemon clean (no CTRS_LOG) on the fixed binary; RST forensics
still warn-level. Prior clean W7 `base-20261115T163439-18ee`
stands: 10/10 valid, all six strict-win.

**Next executable action:** when the postfix log finishes, verify
20/20 valid pairs and zero `session stream reset` warns in
`.work/native-perf/engines/ctrs-warm/daemon-manual.log`; report via
`python3.14 bench/native/runner.py report --match '<run-id>'`.
If clean, record final W6 numbers in
`docs/evidence/native-performance.md` — W6+W7 default-driver cells
then qualified pending resource cells. Then: ≥2 strict wins among
W1/W2/W5/W8 and the W11 12 h reliability leg; resource cells
(peak_total_rss_kb, cpu_seconds_est, physical memory, allocated
storage) still unmeasured.

**Landed 2026-11-15:** checksum-pinned source fetch
(`ensure_pinned_source`, `6446af0`), the real W6 fixture (`f755f6d`),
and the real W7 fixture (`67759ce`): two real apps per build —
hyperfine v2.0.0 (Rust, `cargo build --release --locked` →
debian:bookworm-slim) and httpie 3.2.4 (PyPI sdist → pip wheel →
offline install → python:3.13-slim). Both W7 app Dockerfiles were
validated end-to-end on OrbStack (builds succeed, `hyperfine 2.0.0`
and `http 3.2.4` probes pass, note marker readable). W7 keeps
uncached/warm/incremental per app → 6 metrics
(`{hyperfine,httpie}_{uncached,warm,incr}_s`).

**Baseline status 2026-11-15:** first W6+W7 `--driver default`
baselines (`base-20261115T094322-097d`, `base-20261115T095725-0e1d`)
completed 10/10 pairs each with all correctness green, but **every
pair was rejected** by the reporter's 1% resource-budget gate:
ctrs guest MemTotal was ~934 MB below OrbStack because the pinned
guest kernel reserves ~891 MiB that the configured ceiling did not
account for. Fixed in `4d0bb1a` (`CTRS_GUEST_RESERVE_MIB=950`,
verified guest MemTotal within 0.1%); the rejected runs remain
visible historical records. A 1-pair W7 validation
(`base-20261115T100858-6ee7`) now pairs cleanly.

**Qualified baseline landed 2026-11-15:** W6 `base-20261115T100955-dd6b`
and W7 `base-20261115T102429-e057` — 10/10 valid pairs each, all
correctness green, resource budgets matched. Headline: ctrs wins
hyperfine warm/incr and httpie uncached (strict-win), non-inferior on
hyperfine uncached and W6 rust build; **loss on W6 zlib C build
(ratio 1.22, CI [1.06,1.36])** — worst qualified cell; httpie
warm/incr inconclusive. Full table in
`docs/evidence/native-performance.md`.

**dc control landed 2026-11-15:** `base-20261115T104041-95ab` (W6) +
`base-20261115T105554-3c75` (W7), 10/10 valid pairs each. With the
builder pinned identical, **ctrs is equal-or-faster on every cell** —
strict wins on all six W7 metrics and zlib (0.78). The whole
remaining default-driver deficit is the build→load path (~0.2–0.6 s
per build; flips zlib to a loss and httpie warm/incr to
inconclusive). Full comparison table in
`docs/evidence/native-performance.md`.

**Superseded 2026-11-15:** the e2e verification and baseline re-run
above already happened — see "Resume here". The zlib default-driver
loss remains the acceptance cell to flip; results pending in
`np04-default-baseline-20261115T124001.log`.

**NP-01 qualified on the Mac (2026-11-15):** all three harness checks
pass on `sentry` (41/41 unit tests, clean preflight), guest/binary
provenance hashes are recorded per trial, image architectures are
captured by `prepare`, and a real three-pair same-engine noise control
ran (`base-20261115T092425-9b5d`, W1 warm ctrs: 3/3 valid slot pairs,
median ratios 0.986–0.997). Evidence:
`docs/evidence/native-performance.md` → "NP-01 measurement
qualification executed on the Mac".

**Soak disposition:** `run-20261115T073817` died with its launching
session ~08:48 PST after ~70 min of the 12 h ctrs leg; no runner or
engine processes remain. Its partial records are preserved under
`.work/native-perf/results/run-20261115T073817-00b8/` as historical
observations only — they do not qualify W11. A fresh 12 h-per-engine
W11 belongs to NP-07 after a candidate freezes; do not relaunch it now.

## Work queue

`ready` means begin when the relevant host/resources are free. Dependencies
are per-slice: do not wait for every fixture before profiling one qualified
build workload. A task is done only with the evidence in its row.

| ID | State | Task and exit evidence |
| --- | --- | --- |
| NP-01 | **done 2026-11-15 (Mac)** | Qualify measurement: offline regression tests; no global prune/context edits; actual Mac/guest/image native architecture; running binary/guest identity, builder endpoint and parameters; failures fail commands/reports; exclusive measurement ownership; three-pair no-op noise control |
| NP-02 | **ready after relevant NP-01 checks** | Freeze digest/source/dataset/tool inputs; real W6/W7 first, then W4/W5/W8/W9; prove clean compile and warm reuse, paired input equality and equivalent outputs; version changed fixtures; fetch missing assets with verified checksums |
| NP-03 | **ready per qualified fixture** | ≥10 complete balanced paired baselines for default-user experience; separate resource-/BuildKit-matched controls; loss-first matrix includes missing cells, failures, declared loads/cache states and exact run IDs; no historical pooling |
| NP-04 | **next optimization after W6/W7 baseline** | Profile and close default build→load→first-use cost; implement bounded slices from `buildkit-driver.md` or a better measured approach; default builds achieve parity then strict wins, preserving output/cancel/auth/tag/digest behavior |
| NP-05 | **ready independently** | Qualify Mac CPU/physical-memory/idle/storage and durability: owned process/VM attribution, cumulative CPU, equal completed work, allocated bytes, numerical growth budgets, cache/user-volume persistence; unknown metrics stay unqualified |
| NP-06 | **continuous** | Work worst qualified cell: bind watch/edit, service tails, concurrent build/deploy interference, recovery, idle/wake, reclaim or cleanup; one profile/hypothesis/change/decision, no synthetic victory |
| NP-07 | **after candidate freeze** | Fresh build, full relevant conformance, independent confirmation batches, held-out app/data on both engines, one 12-hour W11 per engine with job identity/deadline; zero unexpected errors/deaths and bounded resources |
| NP-08 | **after all gates** | Reproducible complete scorecard meets parity/leadership bounds; disclose rejected experiments and limitations, report measured scope and rank remaining opportunities |

NP-04 is implementation work. “BuildKit gap documented,” “needs
h2/protobuf,” and “matched driver wins” do not close it. A long soak
running does not make every queue item blocked.

## Evidence and fixture debts

- **Scoring:** old reports mixed `pair_id` across runs, admitted failed
  trials, used a mean bootstrap interval with a median label, and
  substituted zero for missing resources. Recompute from complete raw
  records when possible; never reconstruct pairs from prose medians.
  The patched reporter remains descriptive until qualification.
- **Noise control:** resolved 2026-11-15 — records now carry explicit
  A/B `slot` identity plus `design: "noise-control"`; the cross-engine
  reporter excludes them (`noise_excluded`) and `report --noise`
  renders a separate same-engine slot-pair report. First real run:
  `base-20261115T092425-9b5d` (W1 warm ctrs, 3 pairs).
- **Inputs:** `assets.lock` explicitly remains pilot and service images
  use mutable tags. W8 independently builds each engine's portfolio;
  freeze one identical multi-layer portfolio and independent local
  registry. Verify actual image architecture and digests.
- **W6:** the old cache stamp was only `run_id`, so later pairs could
  reuse compilation. Per-pair identity and uncached work remove that
  shortcut, but the zlib tarball is absent in a fresh checkout and needs
  a checksum-pinned fetch path. A 64-character hash string is not proof
  of equivalent or expected output. Real Rust CI remains missing.
- **W4/W5/W7/W9:** Redis-cli hashing, generated arithmetic modules,
  compileall/random bytes and a 0.6-second hash loop are diagnostics,
  not the promised app/CI/developer matrix. Use pinned upstream sources,
  fixed completed work, full outputs and meaningful correctness checks.
- **W8 state:** removing fixture references does not prove content-store
  eviction. Keep retained-content cache labeling; do not restore global
  image pruning to manufacture a cold state. Include guest install and
  healthy application startup, not only pull/version-command timings.
- **W10:** old throughput counted errors, making fast failures look like
  wins. Score successful work, verified recovery and recovered tails;
  distinguish expected injected-outage failures. A container restart
  does not prove engine/VM or durable-volume recovery.
- **W11:** old short pilots and counters cannot qualify 12-hour behavior.
  Missing windows must fail; slopes/budgets still need implementation.
  Instrumented historical daemon deaths are diagnosable, not resolved.
- **Resources/durability:** broad regexes include unrelated helpers;
  watch plus soak contaminates measurements. RSS is not physical
  footprint; sampled `%CPU` is not reliable CPU-seconds. Audit persistent
  VZ disk flushing before claiming transaction superiority.
- **Primary lane:** old matched 17-vCPU/~43-GiB trials alone do not
  establish normal default-settings behavior. Keep default and
  resource-/BuildKit-controlled evidence separate.

## Finite long-job checkpoint

Replace these historical placeholders with observed facts on the Mac.
Never infer a live PID, successful exit or current counters from prose.

| Field | Observed 2026-11-15 ~09:12 PST |
| --- | --- |
| Run | `run-20261115T073817-00b8`; only trial `001-ctrs-W11-warm` exists — the planned orbstack leg never started |
| PID and process start | None — runner and both ctrs daemon/VM processes are gone; soak died with its session ~08:48 PST |
| Binary/guest/input hashes | Recoverable only for the harness side (`runner_sha256` etc. absent — records predates provenance fields); mark unqualified |
| Start and fixed deadline | Started 07:38 PST; fixed 12 h deadline would have been ~19:38 PST; process exited ~70 min in |
| Logs/results/exit status | `.work/native-perf/results/run-20261115T073817-00b8/` — 137 load windows + `resources.jsonl` through 08:47; no summary/exit record; preserved as historical, not a W11 result |
| Work while waiting | N/A — job is closed; NP-02 fixture work proceeds normally |
| Completion action | Recorded above; next ready task is NP-02 |

## Checkpoint format

Update `Current task` and `Next executable action` at each substantive
boundary. Record concise evidence, not turn-by-turn chatter:

```text
Experiment ID / task:
Status: working | measured | accepted | rejected | externally blocked
Source base/candidate and actual binary/guest hashes:
Fixture/lock version, host, OrbStack/config and default/control lane:
Case/state/load, observed loss, hypothesis and predicted effect:
Commands, planned pair count, run IDs and raw-output checksums:
Correctness, ratios + CI, resources, failed/incomplete trials:
Decision and code commit (or reason changes were discarded):
Next executable action (command or files/change, not “continue”):
External blocker, alternatives tried, independent work remaining:
```

Before context or `/goal` turn boundaries, checkpoint source changes,
job identity and exact next action. Automatic continuation depends on
the initiating harness's supported configuration; this repository cannot
disable its 50-turn pause. A pause is operational state, not successful
completion. Upon resume, execute the saved action immediately.
