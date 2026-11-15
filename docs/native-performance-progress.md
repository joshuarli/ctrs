# macOS performance campaign: progress and continuation

**ACTIVE — measurements need qualification; OrbStack leadership unproven.**
Owner steering: 2026-11-15. Contract:
[`campaign-native-performance.md`](campaign-native-performance.md).
Maintain this file in place as the single queue/checkpoint. Append compact
experiment outcomes to `docs/evidence/native-performance.md`, not a second
queue or turn-by-turn status diary.

## Resume here

**Current task:** NP-02 — freeze digest/source/dataset/tool inputs and
build the real W6/W7 fixtures, then measure that vertical slice.

**NP-01 qualified on the Mac (2026-11-15):** all three harness checks
pass on `sentry` (41/41 unit tests, clean preflight), guest/binary
provenance hashes are recorded per trial, image architectures are
captured by `prepare`, and a real three-pair same-engine noise control
ran (`base-20261115T092425-9b5d`, W1 warm ctrs: 3/3 valid slot pairs,
median ratios 0.986–0.997). Evidence:
`docs/evidence/native-performance.md` → "NP-01 measurement
qualification executed on the Mac".

**Next executable action:** start NP-02. Freeze `assets.lock` beyond
pilot status (digest-pinned sources, datasets, tool versions), then
implement the real W6 pinned-Rust-app fixture — including the
checksum-pinned zlib tarball fetch path — and the real W7 two-app
buildx fixture per `cases.toml`/`buildkit-driver.md`. Measure the
W6/W7 vertical slice with `baseline --driver default` (primary lane)
before any optimization work in NP-04.

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
