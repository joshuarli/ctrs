# Builder readiness reuse

The source change removes repeated `buildctl debug workers` execs for a builder
process that already passed readiness. Ownership and pin checks still run.
The proof includes container ID, nonzero PID, start time and an in-memory pause
generation. Unknown state or a failed probe clears the proof. Readiness retains
its existing cold-start loop. No disk format, wire message, dependency or default
resource setting changes.

The existing ensure mutex owns the proof. `Engine::pause` advances the generation
under the engine state mutex. Reading the fingerprint under that same mutex
covers a pause and resume completed between ensures. The idle watcher rechecks
last use after acquiring the ensure boundary. The source matches private
c484fa80011c1c0a81e20d4ece68536bfd870ac0, following worker c39d95f and the parent
pause correction. The signed candidate is6,615,920B,1,952B above baseline.
Its SHA256 isdb20b2106a9faadf8760e65a11357155166b2ed77fb6de784d63defe0ddbaada.

## Profiling and preserved failures

Single-build profile3791ec4bcfb042728215dae04dfce170 completes12 correct W7
Rust builds. Six worker probes consume about7.0% of warm command time and5.5%
of incremental command time. It misses its10% admission threshold and does not
advance. Raw root: `.work/tmp/builder-readiness-profile-20261117/`.

A distinct parallel-capacity profile tests six rounds each at concurrency1,4,8.
The first version f556e9a935974ea3931e0ec08ad81906 exits1/clean when its oracle
requires resolved compile metadata. Some concurrent solves instead report a
completed cached final COPY with unresolved ancestor metadata. The failure is
preserved under `.work/tmp/builder-parallel-profile-20261117/`.

Version2 requires a completed cached final target and exact actual executable.
It rejects executed or incomplete compilation and records unresolved ancestors
separately. Three deliberately corrupted progress fixtures fail the oracle:
missing target-cache proof, missing target completion and noncached compilation.
Job0bd26689f7f14a6b9133eab30799e402 completes78 correct builds and all95 frozen
receipts recheck. Median exclusive worker-probe fractions are6.68%,13.08%,16.12%
at concurrency1,4,8. Both parallel cells clear the unchanged10% threshold.
This profile establishes work to remove, without predicting speed by subtraction.
Raw root: `.work/tmp/builder-parallel-profile-v2-20261117/`.

## Source and lifecycle checks

Worker7f6f02ba changes builder.rs only. Parent reviews its full diff, then corrects
the pause/resume gap identified by independent reviewer b4ec14c1. The reviewer
checks the correction delta and reports no additional demonstrated defect.
Both review passes leave their checkout unchanged. The parent adds the generation
notification in engine.rs and removes two explanatory comments.

The exact selector passes14 tests, zero failures or ignored tests, on the final
private source and again on the integrated tree:

```sh
CARGO_ENCODED_RUSTFLAGS='' CARGO_NET_OFFLINE=true \
  cargo test --offline --locked -p ctrs --bin ctrs daemon::builder::tests --jobs 4
```

Native lifecycle job012ade9cda844a96b65d80885c022c59 exits0/clean and all97 receipts
recheck. A private audit binary differs from the candidate by two log statements.
Its source is24c4c920c1bbd5c875d795ca83c3ea4c3a12e14b. It is used only for
functional observation. No audit instrumentation is integrated.

| Case | Worker probes | Reused proofs |
| --- | ---: | ---: |
|Cold driver|2|1|
|Warm1|0|6|
|Warm2|0|6|
|Paused before ensure|1|5|
|Pause and unpause completed before ensure|1|5|
|Restarted|1|5|
|Warm after restart|0|6|

All six application builds return the exact c63f2e92 executable, native version
and expected note. The external-resume case retains the original ID, PID and
start time while requiring a new readiness proof. Source tests cover unknown
state, failed proof and incarnation changes during proof. Raw root:
`.work/tmp/builder-ready-lifecycle-20261117/`.

## Uninstrumented comparison

Job2884e2359c2a4b7797f77ebaee62c587 exits0/clean. All97 receipts recheck.
Six balanced pairs per concurrency complete156 real default build-and-run jobs.
All outputs, cached targets, prewarmed image IDs and native counters match.
Both sides use the same stock35087713 kernel,6ae4d3ab initrd,17CPUs and45091MiB,
with a fresh daemon and VM per binary leg. The retained builder and image cache
is shared. Each exact job config is prewarmed before measurement. The primary
interval includes build completion through the verified native executable.

| Concurrency | Median paired journey ratio | Engine CPU ratio | Screen |
| --- | ---: | ---: | --- |
|1|0.9050|0.8035|Pass|
|4|0.9273|0.7642|Pass|
|8|0.9311|0.7336|Pass|

All paired sampled physical peaks remain within the3% growth budget. The screen
requires5% median journey and CPU reductions at concurrency4 and8, and1.03 or
better at concurrency1. Every pair, including the1.357 C1 journey outlier, stays
in `analysis.json`. The source change clears this diagnostic screen.

**Perf gate deferred: host busy.** Niceforge activity and the unrelated OrbStack
machine leave timing ineligible. Six pairs and this controlled warm fixture do
not qualify the full performance matrix, installed defaults, cold content,
recovery, long builds or12-hour reliability. No qualified speedup is claimed.
Raw root: `.work/tmp/builder-ready-compare-20261117/`.
