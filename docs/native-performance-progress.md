# macOS performance campaign: progress and continuation

**ACTIVE — measurements need qualification; OrbStack leadership unproven.**
Owner steering: 2026-11-15. Contract:
[`campaign-native-performance.md`](campaign-native-performance.md).
Maintain this file in place as the single queue/checkpoint. Append compact
experiment outcomes to `docs/evidence/native-performance.md`, not a second
queue or turn-by-turn status diary.

## Resume here

**Current task:** NP-01, finish qualifying the measurement path on the
actual Mac. The reorientation repairs offline-verifiable harness defects;
it is not a new macOS benchmark result.

Offline reorientation verification: **34 stdlib regression tests passed**,
manifest validation passed without Docker, and patch whitespace checks
passed. A dedicated offline CI job now runs those checks. Mac runtime
and hosted CI results remain to be observed.

**Next executable action:** on the Mac, record the current source/binary
and any already-running W11/watch job identities, inspect their status
once, then run:

```sh
python3.14 bench/native/runner.py validate-manifest
python3.14 -m unittest discover -s bench/native -p 'test_*.py' -v
python3.14 bench/native/runner.py preflight
```

Use Python ≥3.11; verify the interpreter (historical default `python3`
was 3.9). Apply the campaign's ownership and exclusive-measurement rules
before engine workloads. Preserve existing soak output as historical
observations. Stop only identified campaign-owned watch/churn load; never
run it beside scored trials. An old-binary soak can finish its fixed
deadline if useful, but cannot qualify a newer candidate or block
independent source/review work.

**Then:** close NP-01's remaining environment/provenance gaps, start NP-02
with real W6/W7 fixtures, and measure that vertical slice. Do not rerun
the entire old proxy matrix to reaffirm its headline.

**Environment limit for this reorientation:** prepared in a Linux
workspace without the Mac, OrbStack or its raw `.work/native-perf/`
records. Runtime results and long-job status require observation on that
Mac; no new speed, stability or physical-memory result is claimed.

## Work queue

`ready` means begin when the relevant host/resources are free. Dependencies
are per-slice: do not wait for every fixture before profiling one qualified
build workload. A task is done only with the evidence in its row.

| ID | State | Task and exit evidence |
| --- | --- | --- |
| NP-01 | **ready; safeguards partly landed** | Qualify measurement: offline regression tests; no global prune/context edits; actual Mac/guest/image native architecture; running binary/guest identity, builder endpoint and parameters; failures fail commands/reports; exclusive measurement ownership; three-pair no-op noise control |
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
- **Noise control:** the existing `noop` command records two slots of
  the same engine, while the corrected cross-engine reporter rejects
  duplicate engine records. Add explicit A/B slot identity and a separate
  noise-control report; do not weaken duplicate detection or present
  same-engine noise observations as OrbStack performance wins.
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

| Field | Last known information |
| --- | --- |
| Historical run | `run-20261115T073817` was reported as 12h ctrs then 12h OrbStack; its completion was not inspected during this reorientation |
| PID and process start | Unknown; inspect once on the Mac |
| Binary/guest/input hashes | Recover from launch record or mark unqualified |
| Start and fixed deadline | Recover actual metadata; never reset the clock to keep watching |
| Logs/results/exit status | Locate existing run under `.work/native-perf/`; preserve final record and process exit status |
| Work while waiting | NP-02 source/fixture work and NP-04 implementation/review on noncontending resources; no parallel performance run |
| Completion action | Record one outcome, close the job, execute next ready task; do not extend a healthy soak |

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
