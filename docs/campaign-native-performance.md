# Campaign: beat OrbStack on macOS

**Owner steering: 2026-11-15. ACTIVE, unattended, not complete.** This is
the current execution contract. It supersedes the previous campaign's
Linux requirements, 30-candidate stop, and monitoring-driven closeout.
On every resume read `AGENTS.md`, this document, and
[`native-performance-progress.md`](native-performance-progress.md).
The progress file is the single work queue and continuation checkpoint;
`docs/evidence/native-performance.md` is the historical experiment log.

## Objective and current position

Make normal headless ctrs workflows on **Apple Silicon macOS** meet and
exceed **OrbStack on the same Mac**, using native `linux/arm64`
containers. Improve completed useful work per second and time to correct
results without materially regressing resources, durability, correctness,
or reliability. Include the default build/export/import/first-use path.
A matched-builder control cannot substitute for the default experience.

“96 windows, zero errors” and “29,776 churns, zero deaths” are reliability
observations, not optimization iterations. The 2026-11-15 audit found
scoring defects, unfrozen assets, proxy workloads, and an unresolved
default-builder gap. Earlier “all win or tie except W6/W7” statements are
**historical pilot observations**, not qualification. Read the correction
at the top of [`evidence/native-performance.md`](evidence/native-performance.md).

**Execution scope is macOS only.** Linux performance/runtime qualification,
WSL, emulation (QEMU/FEX/Rosetta/binfmt), cross-ISA builds, UI, Kubernetes,
and other competitors are out of this campaign. Preserve portable code
contracts and existing tests, but never wait for Linux hardware or add
Linux acceptance dependencies. Hardware virtualization of ARM64 Linux
on Apple Silicon is intended. No VMM rewrite without a demonstrated
application bottleneck that requires it.

## Productive loop

One coordinator owns the queue and integration. Delegate independent
implementation, fixture and review tasks in separate worktrees. Only one
job owns measured host workloads. Builds, extra engines, watch churn,
and other benchmarks must not contend with a scored run.

1. **Resume the checkpoint.** Read the current task, experiment, blockers
   and exact next action. Inspect any existing long job once for identity,
   status and deadline. Do not duplicate it or spend the next turn
   repeating its counters.
2. **Choose work.** First fix a reproduced correctness/harness defect;
   next close missing representative workloads or measurements;
   otherwise choose the largest credible OrbStack loss or smallest
   margin. Work a vertical slice: fixture → baseline → profile → code →
   comparison. Full coverage is required for final victory, not before
   starting any useful optimization.
3. **Write one hypothesis before editing.** Name the case, metric,
   observed cost, suspected cause, expected effect, side effects and
   planned paired batch. Profile actual application work to separate
   engine, builder, polling, cache and load-generator costs. Architecture
   notes are hypotheses, not proof of an unavoidable ceiling.
4. **Implement and evaluate.** Build an identified release binary in an
   isolated worktree; compare baseline ctrs, candidate ctrs and frozen
   OrbStack on the same host/workload. Use planned sample counts and
   retain failures. A code diff is not a performance win.
5. **Decide.** Accept a verified material gain or reproduced correctness
   fix passing the regression budget. Otherwise discard only the
   experiment's changes, record why, and select another hypothesis.
   Do not accumulate speculative optimizations on main.
6. **Checkpoint and continue.** Record files/commit, exact commands,
   binary/input hashes, run IDs, results and next executable action.
   Commit useful source and compact evidence directly to main after
   review and relevant verification. Continue authorized work without
   asking whether to proceed.

Every working session must leave a substantive artifact: a validated
fixture, harness repair, measured/profiled experiment, implemented slice,
or concrete blocker with alternatives tried. Larger counters, repeated
health summaries and renaming a known gap do not qualify. There is no
commit-per-turn quota; split large work into reviewable milestones.

**Anti-stall rule:** after one status-only turn, select the first ready
queue item. After three failed/neutral hypotheses on a bottleneck,
change approach: profile another boundary, obtain independent review,
evaluate a bounded architectural slice, or work another cell. Three
failures and 30 candidates are **review checkpoints, never stop
conditions**. Missing buildx support is implementation work, not an
environment blocker. Inconclusive results get one predeclared larger
batch or a noise investigation, not reruns until they win.

## Finish criteria: coverage, parity, leadership

Freeze workload versions, metrics, resource budgets and statistical
procedure before optimization. Normalize cost as `ctrs / OrbStack` and
successful throughput as `OrbStack / ctrs`, so smaller always favors
ctrs. These are engineering targets, not current performance claims.

| Gate | Required evidence |
| --- | --- |
| Coverage | W1–W10 use pinned representative inputs and asserted outputs; both engines complete identical work at all declared states/loads; no omitted failed, unsupported or unmeasured cell |
| Meet OrbStack | Every predeclared critical timing, tail-latency, CPU, physical-memory and allocated-storage cell has paired 95% upper confidence bound ≤1.03; correctness/recovery gates pass |
| Exceed OrbStack | Equal-family W1–W10 primary-performance geometric-mean ratio has upper 95% bound ≤0.90; strict ≥5% normalized improvements in **W6 and W7 default builds** and at least two of W1/W2/W5/W8; no losing critical cell hidden by the mean |
| Reliability | Frozen candidate and OrbStack each complete one 12-hour W11 mixed-workload qualification: zero unexplained deaths, zero unexpected errors, correct durable data and bounded resource growth |
| Reproducibility | Fresh signed release build and isolated roots reproduce results; independent held-out app/workload passes; commands, hashes, failures, CIs, limitations and evidence locations recorded |

Keep pursuing every remaining comparable weakness. Claim universal
superiority only if every declared comparable cell is a strict win.
Claim “meets and exceeds on this macOS matrix” only after **all** gates
pass. Unknown measurements are **unqualified**, not zero, ties or
optional omissions. A statistical label alone does not qualify a fixture.

## Workloads and metrics

Retain W IDs for traceability. Changed inputs, assertions, cache semantics
or metrics start a new fixture/baseline version; never pool history.
Current proxies remain pilots until upgraded.

| ID | Complete user task | Primary outcomes and integrity |
| --- | --- | --- |
| W1 | Compose up API + Postgres + Redis | Command-to-health and verified read/write; persisted data after restart; startup failures |
| W2 | API reads/writes at fixed offered load and saturation | Successful requests/s; end-user p50/p95/p99; exact accepted records; published-port and container-to-container paths |
| W3 | Migrate/seed database, transact, checkpoint, restart | Fixed successful transactions/s, p95, recovery, exact data and allocated bytes; equivalent durability |
| W4 | API ingest → queue → 1/4/16 real workers → artifacts | Fixed batch completion, queue tails, no lost/duplicate outputs; shell hashing is diagnostic only |
| W5 | Edit → watch/rebuild → test a pinned upstream TS/JS app | Host-bind and named-volume latency separately; real dependencies, change propagation, tests/checksums |
| W6 | Compile/test/package a pinned Rust app plus another language | Clean/warm CI duration, successful tests and equivalent artifacts; CPU/memory; clean trials actually compile |
| W7 | Default buildx → loaded runnable images for two real apps | Uncached/warm/one-file incremental completion; contents and behavior; export/import/first-use included |
| W8 | Deploy identical multi-layer images from independent local registry | Pull-to-healthy including guest install; digests; app latency under load; cancellation/cleanup |
| W9 | 1/4/8/16 parallel real fixed-work build/test jobs as capacity allows | Valid jobs/min, p95 completion, artifacts, networks/volumes, logs, teardown/leaks; no timed busy loop |
| W10 | Interrupt/recover real service/database/queue work | Verified recovery, exact committed data, retries, recovered p99, cleanup; errors are not throughput |
| W11 | 12-hour mixed app/DB/queue/build/teardown qualification | No unexplained deaths/errors; complete outputs; memory/FD/disk trends; no raw churn-count speed claim |

Collect total engine CPU-seconds per unit of successful work, peak/steady
physical footprint, idle CPU/footprint and allocated storage where
meaningful. Count daemon, VM/VZ helper, guest, managed builder and owned
services. Add startup, idle wake, shutdown and reclaim-to-next-use cells;
do not trade a smaller idle screenshot for slower next-use.

`collect.py` uses native proc_pid_rusage CPU, actual ri_phys_footprint and kernel
start identity with explicit required-process coverage. Socket and dedicated VM
disk ownership plus unchanged open executable/boot assets identify the running
engine; build outputs alone do not. The subprocess sampler failed overhead
calibration and is retired from scored sampling. Native v3 passed short median
observer budgets on both engines; noisy individual pairs require stronger final
qualification. Historical resource wins remain superseded. Freeze numerical
idle/reclamation/storage/growth budgets before candidate selection.

## Measurement rules

- **Pin and enforce inputs.** Parse `cases.toml` and `assets.lock` before
  work; the latter remains pilot until digest/source/dataset/tool locks
  are enforced. Record host/OS, power/thermal/load state, actual image
  architecture, OrbStack/config, CLI/Compose/buildx/BuildKit versions,
  source and executable hashes, guest assets, fixture hash, cache state,
  workload parameters and sampler version. Identify the actual running
  binary, including adopted daemons; HEAD alone is insufficient.
- **Separate the lanes.** Primary = normal installed/default user
  experience, with configuration disclosed. Controlled = equal resources
  and pinned identical BuildKit/driver to attribute costs. Neither lane
  substitutes for the other. Default W6/W7 losses remain red when the
  docker-container control wins. Do not credit BuildKit version changes
  to ctrs. An upgrade after freeze starts a new comparison version.
- **Same work and state.** Paired trials share seeds, bytes, requested
  load and cache semantics. Alternate AB/BA or use balanced randomized
  order. Cache-busting identity differs between pairs, not A/B engines.
  Assert clean build steps executed and warm reuse is correct. Use one
  identical multi-layer portfolio and independent local registry. WAN
  timing and independent per-engine rebuilds do not qualify.
- **Preserve user state.** Dedicated ctrs roots/sockets; unique owned
  containers/networks/volumes/builders/ports; explicit Docker endpoint;
  verified builder endpoint. No global image/build/system prune, context
  changes, shared-daemon restart, user container stop, or security/privacy
  changes. Cleanup verifies ownership, not merely an `np*` prefix.
  `--no-cache` measures uncached work, not an empty store or cold engine.
  Unavailable equivalent cold states remain missing.
- **Exclusive measurements.** Capture then stop only identified
  campaign-owned watch/churn jobs before scoring; never run them with
  W11. Quiesce campaign-owned non-tested load. User activity invalidates
  affected pairs or requires another window; do not kill it. Idle
  resident engines require a frozen policy that measures background
  activity and prevents cross-attribution. Never rebuild or replace a
  binary/asset underneath a running trial or soak.
- **Correctness first.** Nonzero exits, malformed/missing summaries,
  mismatched inputs, duplicate/incomplete pairs and integrity failures
  remain visible; failed runs exit nonzero. They cannot produce favorable
  ratios. Preserve failure counts and coverage denominators. Errors are
  not throughput; missing resources are not zero. Planned W10 outage
  errors must be distinguished from unexpected errors/recovery failures.
- **Consistent statistics.** Three pairs are pilots. Require at least
  ten valid complete pairs per qualified cell, identified by run and
  configuration plus pair ID. Display the median paired ratio and 95%
  bootstrap interval of that same median over whole pairs. Strict win:
  upper bound ≤0.95. Non-inferior: upper bound ≤1.03. Loss: lower bound
  >1.03, or a hard correctness failure. Otherwise inconclusive. Failure
  to show significance is not proof of parity. W11 has a separate
  reliability gate, not an ordinary ten-pair speed requirement.
- **No selection bias.** Freeze counts, invalidation rules, primary
  metrics and equal family weights before tuning. Confirm selected
  changes with fresh independent batches. For family/aggregate CIs,
  resample whole paired batches, preserving related-metric dependence.
  Never average away a loss. If a holdout failure guides tuning, retire
  it as a holdout and freeze a fresh independent case for confirmation.

The corrected reporter is a descriptive audit aid, not an implementation
of every qualification gate above. A “strict win” statistical label does
not establish representative inputs, durability or physical accounting.

## Immediate implementation priorities

Follow the single ordered queue in `native-performance-progress.md`: bounded
measurement repair and clean calibration first; normalized fixed-work W2 and
causal application profiling next, with independent acceptance-fixture and
idle/storage work. Preserve successful default docker-driver work. Investigate
W10 separately with a recovery trace before selecting a change. The combined
HZ_1000/PREEMPT/LSE candidate was rejected; guest kernels remain hypotheses.
Unpinned futex results, guest idle counters and process names do not establish
cross-vCPU equivalence, host halt behavior or OrbStack’s VM implementation.

Use short affected-case diagnostics and predeclared confirmations. CPU efficiency
is CPU-seconds per successful operation over the same workload phase, computed
from paired raw records; fixed work/offered load and saturation are distinct.
Do not multiply published median ratios to create a corrected measurement.

The bounded [W2 resource-cycle pilot](../bench/native/diagnostics/resources.md)
predeclares numerical idle, wake, footprint, next-use and allocation budgets.
Its explicit active-disk scope leaves exclusive allocation and build-cache size
unknown; short or contaminated pilots cannot close resource acceptance cells.

Other candidates must follow current profiles: bulk/control interference,
parallel installs, real host-bind loops, published-port tails, builder
lifecycle and memory reclaim. Several transport/install optimizations
already landed; do not repeat old queued work blindly. Resolve persistent
VZ disk flushing and cache-versus-authoritative-volume policy before
claiming database/storage superiority. Never weaken durability to win.

## Finite reliability jobs and continuation

Short pilots unblock development. Full 12-hour-per-engine W11 belongs
once a candidate is frozen for qualification. A job has a run ID, binary/
input hashes, PID/start identity, fixed start/deadline, logs, results and
saved exit status. Preserve exit codes; never pipe launches through
`tail` and confuse an empty log with a running job. Do not extend/restart
a healthy soak just to fill turns. Rerun for a demonstrated failure or
an explicitly new candidate's qualification.

While W11 owns the Mac, do review, source/fixture work or implementation
on noncontending resources without changing the job's binary/assets.
If nothing independent remains, wait for its completion event/deadline
through the execution harness instead of spending model turns polling.
Record one outcome, close the job and take the next queue item. A watch
that survived its finite budget is finished; more `alpine true` churn
cannot improve this scorecard.

**“Goal paused after 50 turns” is an external execution-harness limit.**
Repository text cannot disable it. Use supported persistence/continuation
configuration when available; do not invent `/goal` flags or bypass an
imposed limit. Save the checkpoint and exact next action before a
boundary. Resume that action without another monitoring loop. If the
harness cannot continue automatically, report that operational blocker;
do not describe the campaign as complete.

Stop only for verified finish criteria, explicit owner stop, or a specific
external blocker preventing **all** remaining authorized work. A blocked
case does not stop independent work. Record the failed command, diagnosis,
safe alternatives tried, unfinished cells and minimal missing access/
hardware/permission. Missing Mac access permits source/harness work with
runtime validation pending; never fabricate results.

## Promotion and deliverables

Use `cargo check --workspace`, `cargo test --workspace`, focused
regressions, and applicable macOS `conformance/smoke.sh`, `tests/e2e.sh`,
`conformance/failure.sh` and `conformance/isolation.sh`. Run relevant gates
per slice and full applicable gates at milestones, not unchanged suites
to occupy time. `conformance/run.sh` plans/skips and Linux-root fixtures
are not macOS execution evidence. Preserve socket locality, isolation,
extraction limits, durability, bounded queues, secrets and wire/on-disk
contracts.

Deliver source/fixtures/locks and lean executable harness; a complete
loss-first scorecard with commands, versions, hashes, counts and CIs;
accepted/rejected experiments; current progress/next action; and fresh
reproduction/limitations. Large traces stay in `.work/native-perf/` with
compact checksummed references. Direct verified commits are authorized;
tags, releases and workstation reconfiguration are outside this campaign.

### Resume prompt

> Continue `docs/campaign-native-performance.md`. Read
> `docs/native-performance-progress.md` and execute the first ready task.
> Establish existing job status once, then implement, measure, decide,
> checkpoint and continue. Healthy soak/watch counters are not progress.
> Qualify real workloads and attack default W6/W7 builds using profiles
> and paired evidence. Stay native ARM64/macOS, preserve correctness,
> durability and user resources, land verified slices directly, and
> continue until the stated gates or a specific external blocker. Save
> exact continuation before a harness limit; a pause is not completion.
