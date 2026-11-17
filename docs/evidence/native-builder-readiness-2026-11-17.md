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

## Classic-builder C caller admission

After the sampler repair, run one bounded functional proof using the accepted
signed host `db20b210...` and unchanged stock kernel/initrd. Use a NEW isolated
root, 2 CPUs/8192MiB and idle timeout0; this is disclosed functional test policy,
not installed-default or resource-matched performance evidence. Classic
`DOCKER_BUILDKIT=0 docker build` must load a runnable native C image through the
existing default builder. The input is the pinned W6 zlib1.3.1 archive and GCC
14.2.0 manifest in the tracked Dockerfile. Keep one identical context for five
cases: cold, warm, paused, externally paused-and-resumed, and restarted builder.

Before each lifecycle mutation verify builder ownership/pin, record ID/PID/start
and state, then assert the expected changed/unchanged fingerprint. Every resulting
image must run both the native zlib example and native architecture check, and
return the identical static-library digest. Preserve the first failure; no retry
or favorable timing score. Assert owned cleanup and native process termination.
The finite job lives at `.work/tmp/classic-builder-c-20261117/job` with a fixed
20-minute deadline and frozen inputs, including explicit sparse-template receipt.
No shared Docker daemon, user store or context is modified. Source remains the
accepted product revision; no new candidate or instrumentation is introduced.

Version1 job `ca5e3b0c3f054b57a36ae1e1a42e09c3` exits1 before any build.
The base pull passes but does not boot the lazy VM. Ownership discovery rejects
an absent disk-owning helper; no native-stop proof is established. The original
failure and cleanup warning are preserved. This is a preparation defect, not an
application result or a product failure. No campaign process remains afterward.

Version2 adds an owned `gcc uname -m` bootstrap before ownership discovery and
requires exact `aarch64` output. This boots the VM without starting a builder,
so its first build remains builder-cold. It reuses only the stopped version1
root's pinned GCC image (empty container index, no open-file/process consumer),
not a previous build result. The five contexts and app checks are unchanged.
Version2 has its own inputs/job under `.work/tmp/classic-builder-c-v2-20261117/`;
never pool or replace the version1 receipt.

## Classic C caller result

Version2 job `7203a474ee4a4acf8b6f4d68eb126340` exits0 with clean owned teardown
and verified native daemon/VM termination. All88 frozen receipts recheck before
any subsequent source edit. All five cases build and execute zlib1.3.1 correctly
through `DOCKER_BUILDKIT=0 docker build`, including a genuine first compile and
`make check`. Every resulting image has config ID
`bc580c4ae387b6665f10e21b0c83701157cc46e899ce20e49b6e6aacfe88888c`.
Every static library SHA256 is
`6b6ba12f2f7ed1e8c7ebe08480e408394c8e66aebec862a10494fb2dc415914b`.
Native probes return exact identical `aarch64`, library hash and zlib example
outputs, including decompression, streaming, large-inflate and dictionary tests.

| Case | Builder process and result |
| --- | --- |
| Cold | Builder created; PID78; native app correct |
| Warm | Same ID/PID/start; native app and digest unchanged |
| Paused | Paused state observed before build; active afterward; app correct |
| External resume | Pause/unpause preserves original ID/PID/start; app correct |
| Restarted | New PID/start required and observed; same app and digest |

Sampler v4 covers82 records with both required native processes, no resource
errors and a matching requested-stop receipt. These are completeness observations,
not resource acceptance: no performance or observer-overhead claim is admitted
under foreign load. The public API does not expose hidden internal readiness
exec events; this proof does not invent probe counts. The earlier private audit
remains the evidence for warm reuse and pause-generation invalidation counts.
The signed host and actual booted assets match the earlier accepted fingerprints.

To reproduce from the repository, copy the tracked W6 Dockerfile and the archive
whose SHA256 is9a93b2b7dfdac77ceba5a558a580e74667dd6fede4585b91eefb60f03b72df23
into a new owned context with a fixed stamp. Add one exact ownership label. Use
a fresh isolated engine with the accepted signed host and boot assets, pull the
pinned GCC manifest, then first run an owned `uname -m` container to boot the VM.
Set `DOCKER_BUILDKIT=0` for each `docker build --network none -t <owned-tag> <context>`.
Run `sh -c 'set -e; uname -m; sha256sum /src/libz.a; /src/example'` from each
result with an owned, automatically removed container. Record and verify the
builder's ownership, immutable image, ID/PID/start around each of the five cases;
use explicit pause, unpause and restart on that owned builder only. Remove exact
label-owned outputs and stop the isolated engine. Keep any failure unchanged.

Raw version2 receipts remain optional under
`.work/tmp/classic-builder-c-v2-20261117/`; version1 remains a failed preparation
record. This closes the affected classic C caller proof and changes no product
source or default. Full W6/W7 qualification and installed-default coverage remain
open.
