# Evidence: native-workload performance vs OrbStack (macOS lane)

## Qualification correction — 2026-11-15

**Current verdict: unqualified pilot evidence; meeting/exceeding OrbStack
has not been established.** The historical tables and experiment notes
below are retained for traceability, not accepted as a frozen scorecard.
The active contract is `docs/campaign-native-performance.md`; resume from
`docs/native-performance-progress.md` instead of repeatedly polling soak
and watch counters.

A source audit at `3aab092` found these material qualification defects:

| Finding | Consequence / required follow-through |
| --- | --- |
| Report paired by `pair_id` across all matched run directories | Later runs overwrote earlier pairs; histories/configurations could be mixed. Re-report exact runs with the corrected cohort-aware reporter. |
| Failed trials entered ratios; missing RSS/CPU became zero | Failure/unknown cannot support a win. Corrected reporting exposes rejections and preserves missing values. |
| Bootstrap estimated the mean while the headline called it a median | Old intervals do not support the stated estimator. Recompute the paired median and its interval from raw records. |
| W2 rps CI upper bound 0.977 labeled win; W3 restart CI upper bound 1.237 labeled win; W11 n=3 labeled win | These did not meet the stated strict-win/minimum-sample rule even before other validity problems. |
| `assets.lock` says pilot and uses mutable tags; `cases.toml` was invalid and unused | Inputs were not enforced/frozen. Syntax/validation is repaired, but actual source/image/dataset/tool locking is still open. |
| W6 cache-busting stamp reused `run_id` across pairs | Later “compile” trials could be cache hits. New per-pair identity plus explicit uncached work requires a new baseline; old build-gap magnitudes are provisional. |
| W4/W5/W7/W9 use small generated/string/timed-loop proxies | They do not close the promised real worker/dev/build/CI workload coverage. |
| W8 portfolios were built separately per engine; global image/build-cache prune occurred | Assets and cache state were not demonstrably equivalent; the shared prune calls have been removed. Retained-content pulls and uncached work are not empty-store claims. |
| Load throughput counted error responses; W11 tolerated errors | Fast outage failures could appear as W10 throughput wins. New throughput counts successful requests; W11 rejects unexpected errors and missing summaries. |
| Name-based RSS/%CPU sampling and possible concurrent watch/soak | Whole-engine physical footprint, CPU cost and long-run growth remain unqualified. |

The updated reporter remains **descriptive/pilot**, even for ten-pair
statistical labels, until the Mac execution, representative inputs,
durability, sampler and environment qualification tasks are closed.
Default W6/W7 builds remain the next important implementation target;
matched-builder results and a design note do not close that gap.

No new Mac benchmark or soak was run during this reorientation. The
current state of the historical long job must be inspected on the Mac;
the quoted counters are not a completion artifact. Preserve raw evidence
and add fresh versioned results instead of silently rewriting history.

---

Maintained scorecard for `docs/campaign-native-performance.md`. **Lane:**
Apple Silicon macOS, `arm64` only — no emulation anywhere. **Competitor:**
OrbStack 2.2.5 (server API 29.8.2) via `~/.orbstack/run/docker.sock`, per the
campaign's amended target. Docker Desktop is out of scope for this campaign.
Linux remains `needs native host`.

This document is **loss-first**: every cell, including OrbStack wins, ties,
failures and unsupported states, is listed. Numbers below are pilot-scale
(≤5 paired trials); nothing here is a promotion claim until the frozen
baseline policy (≥10 valid pairs, bootstrap CI vs predeclared thresholds) is
met.

## Host and version freeze (pilot)

| Item | Value |
| --- | --- |
| Host | MacBook Pro, Apple Silicon, `arm64`, 18 cores, 48 GiB |
| OS | macOS 27.2 (26B123), Darwin 27.2.0 |
| docker CLI | 29.9.3 (`/opt/homebrew/bin/docker`), compose v2.29.7 |
| ctrs | `target/release/ctrs` @ git `0eb0bce`, API 1.47, VZ guest kernel 6.18.58 |
| OrbStack | 2.2.5 (`bf84232`), server 29.8.2, shared user daemon |
| Fixture API | `np-fixture-api:np1-513fd8e3ca2e` (FastAPI+uvicorn+psycopg+redis, requirements pinned in `fixtures/w1/api/requirements.txt`) |
| Service images | `postgres:17-alpine`, `redis:7-alpine`, base `python:3.13-slim` |

Raw records: `.work/native-perf/results/*/trials.jsonl` (gitignored);
preflight and image-ID captures under `.work/native-perf/results/`.

## Methodology notes specific to this lane

- **Isolation.** Each trial uses a unique compose project
  (`np<run><engine><case>`), an ephemeral `127.0.0.1` port, and
  `compose down -v --remove-orphans` afterwards. OrbStack's daemon is
  shared with the user: only `np*`-project resources are created or
  removed; nothing else is pruned or reconfigured.
- **Engine-cold vs project-cold.** ctrs `--cold` trials get a fresh
  `CTRS_DATA_DIR` (true empty image/volume store, VM boot included in the
  user-visible path). OrbStack cannot provide an engine-cold root without
  disturbing user state, so OrbStack has **no cold cell**; its warm cell
  reuses the long-lived VM, containerd and build cache. Any future
  head-to-head cold comparison must either run OrbStack in a disposable
  machine or be labeled non-comparable.
- **Cold pulls are WAN.** ctrs cold trials pull `postgres`/`redis`/base
  images from Docker Hub inside the timed region until a local OCI
  registry mirror (W8 fixture work) replaces them. WAN variance is
  disclosed, not hidden.
- **Resource accounting.** `collect.py` samples `ps` CPU/RSS for matched
  process names plus host loadavg every 0.2 s. RSS sums double-count
  shared pages and miss compressed memory; the macOS guest lives inside
  the `ctrs` process footprint. Treat `peak_total_rss_kb` and
  `cpu_seconds_est` as approximations (see `bench/native/README.md`).
- **Correctness is part of the metric.** W1 requires verified health, a
  DB+cache roundtrip, and a record surviving `docker restart` of the db
  container. W2 requires zero transport errors and
  `items == 500 + writes_ok` in `/stats`. A fast error is a failed trial.

## Historical scorecard — freeze/qualification withdrawn (2026-11-15)

The following table was originally labeled FROZEN (warm, 17 vCPU /
~43 GiB both, nominally 10 pairs/cell). Its original verdicts are preserved
as historical labels and are superseded by the qualification correction
above. They must not be copied into the current qualified scorecard.

Generated by `runner.py report --match 'base-20261115*'`; ratios are
paired per-trial medians, <1 favors ctrs (higher-is-better metrics are
reported as orbstack/ctrs so the direction stays consistent). W6/W7 are
the default builder-driver path; the matched `--driver dc` control is
recorded separately below.

| cell | metric | ctrs/orb ratio | CI95 | n | verdict |
| --- | --- | --- | --- | --- | --- |
| W1 | wall_seconds | 0.593 | [0.593,0.724] | 10 | win |
| W1 | time_to_health_s | 0.560 | [0.563,0.721] | 10 | win |
| W2 | rps (orb/ctrs) | 0.957 | [0.831,0.977] | 10 | win |
| W2 | p95_ms | 0.873 | [0.759,0.897] | 10 | win |
| W3 | tx_tps (orb/ctrs) | 0.278 | [0.234,0.347] | 10 | win |
| W3 | up_s | 0.679 | [0.591,0.677] | 10 | win |
| W3 | restart_s | 0.415 | [0.457,1.237] | 10 | win |
| W4 | workers_1_s | 0.582 | [0.548,0.700] | 10 | win |
| W4 | workers_4_s | 0.257 | [0.229,0.278] | 10 | win |
| W4 | workers_16_s | 0.089 | [0.085,0.102] | 10 | win |
| W5 | bind_median_s | 0.334 | [0.302,0.342] | 10 | win (8/10 valid; 2 seed flakes) |
| W5 | volume_median_s | 0.266 | [0.242,0.270] | 10 | win |
| W6 | build_s | 4.552 | [3.685,4.628] | 10 | **loss — builder topology** |
| W7 | build_empty_s | 1.408 | [1.205,1.428] | 10 | loss |
| W7 | build_warm_s | 1.812 | [1.640,1.903] | 10 | loss |
| W7 | build_incr_s | 0.992 | [0.930,1.021] | 10 | tie |
| W8-ul | pull_wall_seconds | 0.237 | [0.204,0.303] | 10 | win |
| W8-ul | load_rps (orb/ctrs) | 0.764 | [0.702,0.861] | 10 | win |
| W9 | jobs_1_s | 0.741 | [0.706,0.819] | 10 | win |
| W9 | jobs_16_s | 0.326 | [0.297,0.331] | 10 | win |
| W10 | recovery_s | 1.807 | [1.630,1.833] | 10 | loss — superseded by EXP-3 re-baseline below |
| W10 | load_rps (orb/ctrs) | 0.306 | [0.283,0.322] | 10 | win |
| W11 | rps_mean (orb/ctrs) | 0.790 | [0.671,0.950] | 3 | win |
| W11 | requests (orb/ctrs) | 0.798 | [0.674,0.955] | 3 | win |

After the resource-parity fix, the full implemented matrix was re-run:
5 balanced pairs per cell, `keep_warm` daemons, `resources.engine`
recorded on every trial (both engines report ncpu=17). Raw:
`.work/native-perf/results/base-20261114T2337*/` … `base-20261114T2350*/`.
Medians below; every trial correctness-green except one orbstack W3
flake (fixture readiness race, fixed in the runner — not an engine
signal).

| cell | metric | ctrs | orbstack | ctrs/orb |
| --- | --- | --- | --- | --- |
| W1 bring-up | wall s | 3.85 | 6.22 | **0.62 win** |
| W2 API load | rps | 2029 | 1899 | **1.07 win** |
| W2 | p95 ms | 6.15 | 7.08 | 0.87 win |
| W2 | p99 ms | 10.99 | 11.60 | 0.95 ~tie |
| W3 postgres | tx_tps | 4000 | 813 | **4.9 win** (re-run, fine polling) |
| W3 | up s | 2.00 | 3.34 | 0.60 win (includes +1.2 s stability gate) |
| W3 | restart s | 0.245 | 0.208 | ~tie (was a polling artifact — see below) |
| W4 queue 1/4/16 w | drain s | 0.40/0.16/0.16 | 0.56/0.66/1.86 | **win all** |
| W5 edit-test | bind/vol s | 0.10/0.08 | 0.31/0.29 | **win both** |
| W6 zlib build | build s (default driver) | 2.10 | 0.52 | **loss — builder topology, see below** |
| W7 image build | empty/warm/incr s | 5.4/0.77/1.74 | 3.78/0.41/1.65 | **loss empty+warm, ~tie incr** |
| W8 deploy+load | pull wall s | 0.90 | 3.22 | **0.28 win** |
| W8 | run_* s | 0.02–0.05 | 0.35–0.62 | **win all** |
| W8 under-load | load rps | 2259 | 1416 | **1.60 win** |
| W8 under-load | load p99 ms | 10.3 | 29.2 | **0.35 win** |
| W8 under-load | load errors | 0 | 0 | tie |
| W9 churn 1/4/8/16 | wall s | 0.64/0.65/0.70/0.72 | 0.86/1.08/1.40/2.11 | **win all** |
| W10 recovery | recovery s | 0.546 | 0.301 | **1.8 loss under load** |
| W10 | load rps during kill | 5244 | 1610 | 3.26 (errors expected in window) |
| W10 | correctness | green | green | tie (no lost writes both) |

**Losses to attack, in order:**
1. **W10 recovery under load** — the restart/start path itself is *not*
   slow: idle A/B shows ctrs `docker start`+health ≈ 0.27 s vs
   orbstack ≈ 0.29–0.38 s, and W3 `restart_s` is now a tie (0.245 vs
   0.208) after fixing poll quantization — the earlier 2.57x 'loss' was
   a fixture artifact (0.5 s isready ticks + fast API return landing
   early in a cycle). The real W10 gap is **published-port churn during
   downtime**: ctrs fast-fails ~68k connections through the per-
   connection vsock relay (each a thread + vsock stream + guest-side
   connect attempt on the agent's single event loop), while OrbStack's
   kernel forwarding refuses cheaply (~174 errors). The post-restart
   health check queues behind that churn → recovery_s 0.55 vs 0.30.
   This is the campaign's predicted cross-workload interference,
   now measured. Candidate fixes, one at a time: guest relay off the
   agent loop (needs the clone3/thread audit), host-side refusal
   suppression (needs a refusal signal — wire protocol is frozen), or
   the priority-3 vmnet path (blocked on this host by Local Network
   permission).
2. **Builder export path** — W6/W7 default-driver losses traced to the
   docker-container driver's client-side image tarball export (~1.5–2 s
   on the gcc base). Matched-driver (`--driver dc`, same pinned
   BuildKit on both) shows ctrs *ahead*; the gap is product topology
   (no `docker`-driver build), not engine runtime. Formal dc runs
   pending; W7 note in cases.toml.
3. W10 `load_errors` count difference is fast-fail vs connection-hold
   behaviour during intentional downtime — recorded, not a defect.

**Wins are broad and large:** bring-up, API load, postgres
transactions, queue drain, edit-test, image deploy+run, under-load
pulls, container churn — ctrs leads every one at equal resources.

## Scorecard — pilot results (2026-11-14, PRE-PARITY — superseded)

**Superseded:** these trials ran ctrs at its 2-vCPU/8 GiB default while
OrbStack had 17 vCPU/~43 GiB. Kept for history only; the matched table
above replaces it. An earlier pilot (raw data deleted) also restarted
the ctrs daemon per trial while OrbStack's stayed hot.

### W1 web stack bring-up (warm), seconds

`wall_seconds` = compose up → health OK → DB+cache roundtrip verified →
record survives `docker restart` of the db container → stack down.
`time_to_health_s` = compose up → first `/health` 200.

| pair | ctrs wall | orbstack wall | ctrs health | orbstack health |
| --- | --- | --- | --- | --- |
| 1 | 3.937 | 4.182 | 3.309 | 3.384 |
| 2 | 3.611 | 4.075 | 2.987 | 3.255 |
| 3 | 3.605 | 4.114 | 2.975 | 3.311 |
| 4 | 3.645 | 6.163 | 3.002 | 5.351 |
| 5 | 3.626 | 6.059 | 2.998 | 5.261 |

- ctrs median wall **3.64 s**, orbstack **4.18 s** → paired ratio
  **0.871**, bootstrap CI95 **[0.650, 0.882]** (n=5).
- **OrbStack is bimodal**: pairs 1–3 ~4.1 s, pairs 4–5 ~6.1 s, with the
  gap appearing in `time_to_health` (~3.3 → ~5.3 s). ctrs is flat
  (~3.6–3.9 s every trial). This resembles the published-port fast/relay
  path split documented for ctrs in `docs/evidence/net.md`; investigate
  before any W1 claim. The campaign bar is OrbStack's *best eligible*
  configuration, so the ~4.1 s mode is the number to beat.
- No-op control (ctrs vs ctrs, 4 trials, hot daemon): wall 3.60–3.90 s —
  harness noise ~±0.15 s.
- One early orbstack trial failed correctness (fixture app held a dead
  Postgres connection after `docker restart`; fixed by reconnect logic in
  `app.py`). Recorded as a harness bug, not an engine result.

### W2 API under load (warm, 8 concurrent, 20 s, 30% writes, 500 seed rows)

| pair | ctrs rps | orbstack rps | ctrs p95_ms | orbstack p95_ms | ctrs p99_ms | orbstack p99_ms |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 2285 | 1944 | 6.23 | 6.64 | 11.89 | 14.31 |
| 2 | 2487 | 2002 | 5.13 | 6.41 | 8.94 | 8.76 |
| 3 | 2478 | 2083 | 5.07 | 6.16 | 8.14 | 8.25 |
| 4 | 2459 | 1979 | 5.15 | 6.52 | 9.27 | 9.32 |
| 5 | 2416 | 1729 | 5.23 | 7.49 | 8.78 | 20.66 |

- ctrs median rps **2459** vs orbstack **1979** → throughput ratio
  **0.805** (orbstack/ctrs), CI95 **[0.758, 0.839]** — a ~20% ctrs
  throughput advantage, consistent across all 5 pairs.
- p95 ratio **0.800**, CI95 [0.743, 0.883] — clears 1.0 at pilot n.
- p99 remains noisy on both engines (8–21 ms); needs higher concurrency
  and more pairs before tail claims.
- Zero transport errors and exact row-count verification on all 10
  trials. ctrs `setup_seconds` ~3.0 vs orbstack ~5.4 (untimed, but
  consistent with the W1 gap — likely container-create/start path).

### W8 real-image deployment under load (warm, 8 concurrent, 30 s, 30% writes, store-cold pulls each trial)

Pulls are real fetch+install every trial: ctrs restarts its daemon
(untimed, wipes the guest layer store), OrbStack runs `image prune`.
Portfolio = postgres/redis/python/busybox relocated rootfs images
(~178 MB total) pulled by digest from each engine's local `registry:2`.

| engine | trials | load errors | load rps (median) | load p99_ms (median) | load max_ms | pull_wall_s (median) |
| --- | --- | --- | --- | --- | --- | --- |
| ctrs | 9 | 0 | ~2850 | ~10.9 | ~240 | ~0.68 |
| orbstack | 4 | 0 | ~2060 | ~13.5 | — | ~2.44 |

- ctrs serves ~**35–40% more requests/s** during real image pulls and
  installs, with better median p99 — the EXP-1 forked-child install
  keeps the app responsive while ~178 MB of layers unpack.
- ctrs pull wall ~0.68 s vs orbstack ~2.4 s for the same portfolio —
  ~3.5× faster deploy path on this fixture.
- Two earlier ctrs trials on the *old* NAT published-port path failed
  with 8 disconnects each; after EXP-2 (vsock default) ctrs is 9/9
  clean. OrbStack was clean throughout.
- Caveat: n=4 OrbStack trials; the rps gap is large enough to be
  credible but the frozen ≥10-pair baseline will firm it up.

### W7 native image build (warm engine, multi-stage offline Dockerfile, 5 pairs)

Build-cache states measured per trial: `buildx prune -af` → empty build
→ identical rebuild (warm) → `stamp/note.txt` bump (incremental). Base
image `python:3.13-slim` is a prepared service image, so builds are
offline; `--load` lands results in each engine's store.

| metric | ctrs median | orbstack median | ratio (ctrs/orb) |
| --- | --- | --- | --- |
| build_empty_s | 4.47 | 3.63 | **1.23 — loss** |
| build_warm_s | 0.75 | 0.41 | **1.83 — loss** |
| build_incr_s | 1.54 | 1.62 | 0.95 — wash |

- The warm-build gap (~0.34 s fixed) points at per-build overhead in
  ctrs's build/load path (context export, `--load` image import, or
  layer-store sync), not buildkit execution — both engines run real
  buildkit in-VM. Hillclimb candidate; not yet root-caused.
- Incremental is a wash; empty-build loss (~0.9 s) is consistent with
  the same fixed overhead plus possibly slower layer export.

### W9 parallel container churn (warm, 5 pairs, ~0.6 s CPU per job)

J concurrent `docker run --rm python:3.13-slim` jobs (1/4/8/16), each
printing a verified marker. Median wall seconds:

| jobs | ctrs | orbstack | orbstack/ctrs |
| --- | --- | --- | --- |
| 1 | 0.64 | 0.84 | 1.31 |
| 4 | 0.66 | 1.06 | 1.62 |
| 8 | 0.73 | 1.45 | 2.00 |
| 16 | 0.78 | 2.10 | **2.69** |

- ctrs container create/start/rm scales far better under concurrency —
  OrbStack's per-container overhead grows roughly linearly with J
  while ctrs stays near-flat. All markers verified on all 10 trials.
- v1 scope: create/start/run/rm + CPU + log capture; temp networks,
  writable-layer writes and artifact collection deferred.

### W3 persistent transactional Postgres (warm, pilot)

postgres:17-alpine on a per-trial named volume: migrations → 300-tx
deterministic mix (INSERT+UPDATE+COMMIT on a shared meta row) →
CHECKPOINT → `docker restart` → exact count/sum/meta verification.

| metric | ctrs median | orbstack median |
| --- | --- | --- |
| up_s (run -d → pg_isready) | 0.83 | 2.36 |
| txmix_s (300 tx) | 0.07 | 0.35 |
| tx_tps | ~4300 | ~860 |
| restart_s | 0.60 | 0.21 |

- **Durability caveat (campaign gate):** the ~5× tx_tps gap may partly
  reflect disk-sync semantics — ctrs's data disk is `Cached`+`Fsync`
  and the `.fsync`/`.full` audit is still open. Do not cite this as a
  clean win until the durability policy is qualified.
- `restart_s` is a small ctrs loss (0.60 vs 0.21 s) — container restart
  path worth a look.
- **Reliability:** 1 intermittent ctrs failure in ~9 trials — migrate/
  txmix/checkpoint execs returned errors while the container stayed
  healthy (stderr capture added for the next occurrence; not yet
  reproduced). OrbStack 5/5 clean.

### W5 monorepo edit-test loop (warm, 5 pairs)

60-module python repo; timed `docker run python3 run_tests.py` per
iteration on host bind mount vs named volume (kept separate), host edit
between bind iterations with marker verification.

| metric | ctrs median | orbstack median |
| --- | --- | --- |
| bind_median_s | 0.102 | 0.302 |
| volume_median_s | 0.072 | 0.287 |

- Absolute times favour ctrs ~3–4× (container start dominates this
  light workload — consistent with W9).
- **Within-engine bind penalty:** ctrs bind/volume ≈ **1.4×** vs
  orbstack ≈ **1.06×** — ctrs's virtiofs host-bind path costs ~40% over
  guest-native storage where OrbStack's costs ~6%. Real architectural
  weakness for IO-heavy bind-mount dev loops; the workload is light
  (60 tiny files, warm cache) so a heavier IO cell may widen it.
- All edit-coherence markers verified on all 10 trials.

### W10 failure recovery pilot (warm, kill API container mid-load)

W1 stack under 8-way mixed load; `docker kill` the API container at
~6 s, `docker start` after 3 s, load continues to 20 s. 4 trials per
engine, all correctness checks green (recovery, no lost committed
writes — `items >= 500 + acked writes` held everywhere; OrbStack even
showed the expected +1 committed-but-unacked surplus once).

| metric | ctrs | orbstack |
| --- | --- | --- |
| recovery_s (start → /health) | 0.54–0.80 | 0.36–0.37 |
| load_errors in window | ~65k–73k | ~160–270 |

- Both engines recover correctly with zero lost writes — the hard
  gate passes on both.
- ctrs restart→healthy is ~0.2 s slower (consistent with the W3
  restart_s gap — container start path).
- Error surfacing differs: ctrs's listener keeps accepting and fails
  fast (~70k rapid errors), OrbStack appears to hold/refuse
  connections (~200 errors). Fast-fail is arguably better client
  behaviour; recorded as a difference, not a defect.
- v1 scope: container kill only. Engine/VM-level kill deferred —
  OrbStack's shared daemon makes an engine restart non-comparable.

### W4 worker-queue baseline (warm, 5 pairs, 200 jobs)

Redis list on a private bridge network; 1/4/16 `docker run` worker
containers RPOP jobs and SET md5 results. Drain wall includes worker
container provisioning (foreground `docker run`), so it blends
start latency with queue throughput — disclosed in the case note.
All 30 trials correctness-green (rc=0, 200/200 results, md5 sample).

| workers | ctrs median s | orbstack median s | ratio |
| --- | --- | --- | --- |
| 1 | 0.308 | 0.598 | 1.94x |
| 4 | 0.225 | 0.699 | 3.11x |
| 16 | 0.318 | 1.826 | 5.74x |

cts wins every cell, and the gap widens with concurrency — consistent
with W9's container-start/churn advantage. OrbStack's 16-worker cell is
~8x its own 4-worker time, i.e. its per-container start cost dominates
at high fan-out.

### Resource parity fix (methodology, 2026-11-14)

`docker info` exposed a major allocation asymmetry: the ctrs bench VM
defaulted to **2 vCPUs / ~8 GiB** while OrbStack's VM had **17 vCPUs /
~43 GiB**. Every CPU-bound cell measured so far compared engines *and*
allocations. The runner now queries OrbStack's `docker info`
(NCPU/MemTotal) and spawns the ctrs bench daemon with matching
`CTRS_CPUS`/`CTRS_MEMORY_MIB` (ambient env still wins), and records
`resources.engine {ncpu, mem_total_bytes}` on every trial. **All
pre-parity baseline numbers below are superseded** and must be re-run;
ctrs's recorded wins were achieved *despite* the handicap, so they are
likely conservative, but no claim stands until re-measured.

### W6 compiled-app CI baseline (warm, 5 pairs, resource-matched)

Timed `docker build` of vendored zlib 1.3.1 (configure -> make -j ->
make check) on gcc:14.2.0-bookworm; per-trial stamp busts the layer
cache so every build is a real compile. Identical `libz.a` sha256 on
both engines (deterministic build verified).

| engine | build_s (5 pairs) | median |
| --- | --- | --- |
| ctrs (17 vCPU) | 4.04, 2.10, 2.19, 2.10, 2.09 | 2.10 |
| orbstack (17 vCPU) | 1.49, 0.45, 0.61, 0.52, 0.49 | 0.52 |

**Loss on the default path — but the cause is builder topology, not
engine runtime.** Phase timing on ctrs: compile+check 0.6 s, then
`exporting to docker image format` -> `sending tarball` **1.7 s** ->
`importing to docker` 0.0 s. The docker-container buildx driver
streams the full image tarball from the CLI through the daemon's
`/images/load`; OrbStack's default `docker` driver keeps buildkit and
the image store inside its VM and skips that client round-trip.

Matched-driver A/B (same zlib context, unique stamps):

| builder | engine | wall |
| --- | --- | --- |
| docker (native) | orbstack | ~0.5 s |
| docker-container | orbstack (`npw6-dc`) | 3.35-4.28 s |
| docker-container | ctrs (default) | 2.10-3.11 s |

On identical builder topology **ctrs beats orbstack** (~2.6 s vs
~3.9 s median). Plain `docker run` compile of the same zlib tree is
identical on both (~350 ms make), confirming guest CPU parity. The
product gap is real though: ctrs has no `docker`-driver build, so
`docker build` users pay a ~1.5-2 s client-side export per build on
large bases. Candidate future work: embedded buildkit or a
layer-dedup import path; recorded as a known structural difference.

### W11 soak pilot (warm, 300 s, load windows + churn bursts)

10 sequential 30 s W2 load windows (conc 8, 30% writes) interleaved
with 8-job churn bursts every 4th window. Both engines green:

| engine | requests | errors | churn fail | version-check fail | rps_mean |
| --- | --- | --- | --- | --- | --- |
| ctrs | 333,931 | 0 | 0 | 0 | 1100 |
| orbstack | 378,464 | 0 | 0 | 0 | 1236 |

No daemon deaths, no error leakage, item counts exact on both.
`rps_mean` includes churn-burst downtime in the denominator; not a
like-for-like W2 number. Pilot scale only — the campaign target is
12–24 h (`--duration`); resource-trace growth analysis pending.

### Builder-driver attribution control (`--driver dc`)

W6/W7 `--driver dc` runs both engines on the same pinned
`moby/buildkit` digest via a shared `np-dc` docker-container builder
(n=3 pairs each, first ctrs trial excluded — cold builder image pull):

| cell | ctrs dc | orbstack dc | default-driver winner |
| --- | --- | --- | --- |
| W6 zlib build_s | 2.28 | 2.31 | orbstack (0.52 vs 2.10) |
| W7 build_empty_s | 5.85 | 6.26 | orbstack |
| W7 build_warm_s | 1.17 | 1.52 | orbstack |
| W7 build_incr_s | 2.55 | 3.13 | ~tie |

**Conclusion:** on identical builder topology ctrs matches or beats
OrbStack on every build cell. The entire default-path W6/W7 deficit is
the missing `docker`-driver (embedded BuildKit) product feature, not
engine runtime. This is now a *feature gap* to schedule, not a perf
bug to chase.

**Decomposition re-measured (2026-11-15, warm buildkit caches, real
compile):** W6 zlib `buildx build --load` ctrs 2.53-2.61 s vs
orbstack 1.27-1.31 s; W7 warm ctrs ~0.77 s vs orbstack ~0.42 s.
Controls isolate the delta to the `--load` export hop, not execution:
trivial `RUN` on the 1.4 GB gcc base builds in 1.95 s (ctrs) vs
0.64 s (orbstack); in-container zlib compile is sub-second on both
(identical libz.a sha256); a 3000-`exec` fork loop builds in 6.41 s
on *both* engines; and `docker load` of a 468 MB store tar is *faster*
on ctrs (0.73 s vs 1.23 s). So guest CPU, nested buildkit workers,
and image ingest all meet or beat OrbStack — the residual is purely
the docker-container driver's full-image tar round-trip
(buildkit -> buildx CLI -> `/images/load` -> guest store) that the
embedded `docker` driver skips. Closing it requires embedded
buildkitd with direct store access (multi-session feature).

**Why embedded buildkitd alone cannot close it (2026-11-15
analysis):** ctrs's image store is host-side by design — every image
byte must cross vsock host-ward exactly once no matter who produces
it, and `archive::load` must ingest it (measured ~0.73 s for a
468 MB store tar, already *faster* than OrbStack's `docker load` at
1.23 s, and mostly digest-dedup checks on repeat loads). OrbStack's
`docker` driver skips the whole hop because its image store lives
inside the same VM as buildkitd — an architectural difference, not a
protocol one. A proxied/embedded buildkitd would still owe the
vsock crossing + ingest; it would only remove the buildx-CLI relay
(~0.3 s of the ~1.3 s delta on a 1.4 GB image). Closing the cell
outright needs either the image store moved guest-ward (a
fundamental redesign) or a store-aware exporter that ships only
changed layers (no such BuildKit docker-driver mechanism exists
either — moby pays the same full-image cost, which is why the
matched `--driver dc` control already shows ctrs *ahead*). Recorded
as the campaign's one structural feature gap: `docker`-driver
builds exist and work, they just cost ~0.3–1.3 s more per build,
scaling with image size.

**Exact buildx selection mechanism (2026-11-15, buildx v0.22.0
source):** the implicit `default` builder resolves its driver per
endpoint via `driver.GetDefaultFactory`, lowest `Priority` wins.
The `docker` driver's `Priority` returns 10 only if
`Client.DialHijack("/grpc", "h2c")` succeeds, else 99
(`driver/docker/factory.go`); docker-container is the fallback.
The docker driver then talks BuildKit directly — `Dial` hijacks
`/grpc` (h2c control API) and sessions hijack `/session`
(`driver/docker/driver.go`); it never uses `POST /build` at all.
ctrs serves neither route, so the probe fails and every `docker
buildx build` lands on docker-container regardless of engine.
Falsified sub-hypothesis: `/_ping` `Builder-Version` is not the
gate — flipping ctrs's header 1→2 left the driver choice
unchanged (verified live). Closing the cell therefore requires
implementing `/grpc` + `/session` *and* a moby-worker that writes
the image store in-engine — i.e. embedded BuildKit, not a proxy
(a standalone buildkitd still cannot satisfy `--load`'s
in-store semantics and would add a hop).

**Mirror push export for `POST /build` (2026-11-15, `e41c3bf`):**
the classic builder API now exports `type=image` to the host mirror
(`/v2/<token>/push/<repo>/…`, OCI push protocol) instead of an
uncompressed docker-archive tar through exec output. Blobs land
content-addressed in the store, so warm/incremental builds push only
new layers (HEAD-skipped when present), manifests become image
records under a per-build temp repo, and the daemon retags on
success. Verified end-to-end: tagged and untagged builds, a 64 MiB
layer push (~0.2 s), image run probes, no temp-image or upload-file
leaks, archive fallback when the mirror is down. Scope note: this
serves `POST /build` (legacy/API clients) only — the scored W6/W7
path is `docker buildx build --load` on buildx's own
`buildx_buildkit_default` container, which never touches
`builder.rs`; the scored gap above is unchanged by this work.

**Exec stdin path (2026-11-15):** bulk `exec -i` measured ~400 MB/s
vs OrbStack ~880 MB/s — a real loss, root-caused to two stacked
costs. `forward_stdin` read 32 KiB per `Input` frame; the guest's
per-frame cost capped throughput near half the link. Reading at
`MAX_OUTPUT_CHUNK` (512 KiB) recovered ~25% (512 MiB: 1.35 s ->
~1.0-1.15 s, `6b8cafb`). The residual ~2x gap matches the measured
host->guest vsock ceiling (~450-500 MB/s, same as `docker cp` in at
~475 MB/s) vs OrbStack's ~880 MB/s — asymmetric vsock directions,
not fixable in userspace. Raw stdin on the dedicated conn was
considered and rejected: it would save only the framing copies
while adding a stdin-routing ordering problem between the control
conn and the exec conn for ~10% gain.

**Adjacent-path probes (same session, warm engines):** `docker save`
of the 468 MB gcc store — ctrs 0.52 s vs OrbStack 2.51 s (~5x,
host-side store reads directly); `docker export` ~1.5 s/GB on both
(parity); container churn 16-parallel `run --rm` 0.63 s vs OrbStack
1.68 s, sequential ~64 ms vs ~268 ms per run — the new per-process
bulk connections did not regress start paths.

### W10 relay-churn fix: guest refusal marker + host negative cache

W10's residual loss (~0.55 s vs ~0.30 s recovery) was traced to refused
connect churn: during the post-`docker start` window the load driver
retries at ~5k conn/s, each spawning a host relay thread, a vsock
stream, and a guest relay session whose connect() fails — all on the
agent's single poll loop, starving the health-check relay queued
behind it. A `--concurrency 1` control (same ~68k errors, fewer
parallel sessions) recovered in ~0.35 s, confirming session churn rather
than attempt rate as the mechanism.

Fix, one hypothesis, both ends of the framed relay:

- Guest (`relay.rs`): on connect() refusal (sync or SO_ERROR) over
  `RELAY_FRAMED_PORT`, write a `u32::MAX` frame-length marker before
  closing. `0xFFFFFFFF` cannot be a real payload length (frames are
  length-prefixed; payload is opaque inside them).
- Host (`ports.rs`): `Deframer` surfaces the marker; `relay()` records
  `(container ip, port)` in a 250 ms negative cache; `accept_loop`
  drops new accepts for that key without spawning a relay, and
  `relay()` re-checks on entry. Entries are written only by real guest
  refusals, so a backend that starts listening is reached within one
  TTL — no protocol-visible behaviour change for healthy containers.

Measured (warm, 5-pair-equivalent spot check, conc=8, 3 trials):

| | before | after | orbstack |
| --- | --- | --- | --- |
| recovery_s | 0.49–0.56 | **0.346–0.368** | 0.294–0.423 |

ctrs is now at parity within noise; `load_errors` (~65k) is unchanged
and expected — clients still see fast refusals, the guest just no
longer pays for each one. Wire-format note: host and guest ship in the
same binary/initramfs, so the marker needs no negotiation; an old
guest simply never sends it (host treats streams as before).

### EXP-1 large-pull-during-load (real WAN pull, node:22-bookworm ~400 MB compressed)

Ad-hoc paired experiment, W1 fixture stack + W2 load driver
(conc 8, 40 s, 30% writes, seed 7), `docker pull` started 3 s into
the load window on a cold image. Single pair — directional evidence,
not a frozen-baseline cell yet.

| engine | pull wall | requests | errors | rps | p50 | p95 | p99 | max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ctrs | 7.0 s | 104,584 | 0 | 2614 | 2.88 | 4.96 | 9.59 | **26.9** |
| orbstack | 9.8 s | 100,062 | 0 | 2501 | 2.90 | 5.30 | 9.80 | **123.7** |

ctrs is ahead on every aggregate and — the EXP-1 point — its worst
single-request latency during a real image install is ~5x lower.
OrbStack's 124 ms max is the kind of tail the forked-child install
was built to avoid. Consistent with the W8 under-load cell (5/5
clean pairs, 1.6x load rps). Caveats: n=1, WAN-dominated pull wall,
pull occupied only ~20% of the window; a dedicated cold-pull cell
with per-window latency would tighten this.

### Engine ecosystem footprint (approximate, `ps` RSS sum)

| engine | W1 peak_total_rss median | W2 peak_total_rss median | W2 cpu_seconds median |
| --- | --- | --- | --- |
| ctrs | ~1116 MB | ~1982 MB | ~32.4 |
| orbstack | ~12250 MB | ~13944 MB | ~28.8 |

OrbStack's matched process set includes its whole VM helper tree; the
number likely overstates incremental footprint (shared pages, VM memory
accounting differs) but the order-of-magnitude gap is worth
investigating under `footprint`/`vmmap` accounting before any memory
claim. ctrs total includes the VZ guest inside the `ctrs` process.

## Coverage status

| Case | Status |
| --- | --- |
| W1, W2 | implemented, pilot trials collected |
| W8 | implemented (incl. under-load cell), pilot trials collected |
| W7 | implemented, 5-pair pilot collected — **loss cell** (below) |
| W9 | implemented, 5-pair pilot collected — large win (below) |
| W3 | implemented, pilot collected — mixed (below) |
| W5 | implemented, 5-pair pilot collected (below) |
| W10 | implemented, pilot collected (below) |
| W4 | implemented, 5-pair baseline collected (below) |
| W6 | implemented, 5-pair baseline collected (below) |
| W11 | implemented, 300 s pilot collected (below) |
| Linux lane | blocked: no bare-metal Linux host (`needs native host`) |
| Docker Desktop | excluded per amended campaign target |

## Known gaps before this scorecard can support claims

1. W3–W11 fixtures do not exist yet; the matrix is far from complete.
2. No held-out real third-party application; the W1/W2 fixture is
   purpose-built (real FastAPI/Postgres/Redis, but ours).
3. OrbStack cold cells are structurally unavailable (shared daemon).
4. Pilot replication (≤5 pairs) is below the frozen ≥10-pair baseline.
5. The historical "nine unexplained macOS daemon deaths" (closeout
   evidence) are not yet re-qualified under sustained W11-style load;
   W1/W2 trials showed zero daemon deaths but that is not a soak.
6. `docker import` returns "bad request framing" on ctrs (works on
   OrbStack) — an API-compatibility gap found while staging a bulk
   fixture; needs a repro and a fix or a documented limitation.

## Experiment log

### EXP-1 — guest layer install off the agent event loop (priority 1, slice A)

- **Date:** 2026-11-14. **Status:** implemented, smoke-verified; benchmark
  A/B pending.
- **Hypothesis:** `layers::receive()` ran decompress + untar + `syncfs`
  inline in the single-threaded `agent.rs` poll loop, so a large image
  pull stalled exec I/O, logs, exits, DNS and relays for unrelated
  containers. Moving install to a forked child should keep running apps
  responsive during real pulls without changing wire semantics.
- **Change:** `stage_blob()` drains the blob stream into `.blob-<seq>-*`
  (stream order preserved, unique per job); a serialized queue feeds one
  forked child at a time (`install_child` keeps only its result pipe, like
  the `docker cp` children — the agent stays single-threaded for `clone3`).
  Results return through a length-tagged pipe record; `outbox` keeps
  `LayerStored`/`Error` replies FIFO against later requests. Durable
  install order is unchanged: `syncfs` → rename → `.done` marker.
- **Rejected first attempt:** a `std::thread` worker broke every
  `clone3` container spawn (`switch user: ENOENT/0`) — the documented
  single-threaded SAFETY invariant is real. Reverted to the forked-child
  pattern already used by `copy.rs`.
- **Verification so far:** `cargo check --workspace`, musl-target check
  incl. `--tests`, `cargo xtask guest`, `conformance/smoke.sh` 21/0,
  fresh `alpine:3.20` pull + run, `redis:7` pull concurrent with `exec`
  on a running container.
- **Post-change pilot (2026-11-14, warm, 5 pairs, seed-varied):** W2 ctrs
  rps median ~2533 vs OrbStack ~2143 (~18% ahead, consistent with the
  pre-change pilot); W1 warm ctrs ~3.6 s vs OrbStack ~4.1–6.1 s bimodal;
  ctrs cold W1 20.1 s (single sample, WAN pull variance dominates — the
  pre-change cold was 18.8 s, not a regression signal at n=1). All
  correctness checks green.
- **Pending:** a dedicated pull-during-load responsiveness cell (the
  actual hypothesis test) and the ≥10-pair frozen baseline; host-side
  bulk-stream separation (second vsock connection) remains a separate
  slice of priority 1.

### EXP-2 — published-port transport: framed vsock relay is now the default (2026-11-15)

- **Symptom:** W8 under-load trials on ctrs intermittently failed with
  2–8 `RemoteDisconnected` errors ~7 s into a 30 s mixed HTTP load while
  OrbStack passed every trial. The API container never restarted
  (`restarts=0`, no OOM); the drop was in the published-port path.
- **Packet-level evidence:** a tcpdump on the guest bridge showed the
  app (uvicorn) sending FIN *exactly* 5.000 s after the last response on
  the affected flows — its keep-alive timeout — after the client went
  silent for 5 s. Only flows on the VM's NAT (vmnet) path stalled; the
  stall coincided with concurrent W8 image-pull bulk traffic sharing the
  same NAT network.
- **A/B:** forcing every published connection onto the framed vsock
  relay produced **6/6 clean** W8 under-load trials (0 errors,
  ~2800 rps) against a ~50 % failure rate on NAT.
- **Bulk is a wash:** 200 MB through a published port measured
  ~1.04–1.15 GB/s on vsock vs ~1.15–1.25 GB/s on NAT — the old
  "vsock is several times slower" assumption was stale.
- **Interactive is better on vsock:** W2 warm ~2850–2960 rps vs
  ~2450–2530 rps on NAT (~15 % ahead).
- **Change:** `daemon/ports.rs` — the vmnet/NAT path is now opt-in via
  `CTRS_VMNET=1`; the default is the framed vsock relay, and
  `publish_nat` is skipped entirely unless enabled. Per-trial path stays
  observable in daemon logs (`port relay ended framed=true` vs
  `nat relay ended`).
- **Caveats:** the mechanism inside Apple's vmnet (per-flow queueing
  under concurrent bulk) is inferred, not proven — the A/B correlation
  is solid but n=7 clean trials; keep collecting samples in the frozen
  baseline. `docs/evidence/net.md` already records that vmnet is
  unreachable for *unsigned* dev builds on this Mac (Local Network
  privacy), so most dev usage was already on vsock; this change makes
  the entitled/signed path match.

### EXP-3 — balloon reclaim vs next-operation latency (W10 recovery)

- **Symptom:** frozen-baseline W10 `recovery_s` was a consistent loss
  (~0.55 s vs OrbStack ~0.30 s) even after the relay-churn fix, while
  back-to-back spot checks measured ~0.35 s.
- **Isolation:** `CTRS_NO_BALLOON=1` daemon + 45 s idle gaps between
  trials reproduced ~0.35 s — pointing at the balloon thread, which
  shrinks the memory target 256 MiB/s whenever guest usage drops. In a
  ~45 s gap it can return ~11 GiB; ballooned pages come back zeroed and
  the next trial's container start re-faults them.
- **Fix:** `engine.rs` — the balloon may not shrink until
  `CTRS_BALLOON_QUIET_SECS` (default 120 s) of API quiet; growth is
  never delayed. Verified spot check with the fix: 0.343 / 0.569 /
  0.351 / 0.356 s under the same 45 s-gap cadence.
- **Scorecard impact:** W10 recovery re-baselined on the fixed binary
  (below); other cells are longer-window and were not materially
  affected, but W5's sub-100 ms iterations could see small gains too.

**W10 re-baseline (post-fix, `base-20261115T014916-6bbb`, 10 pairs,
real alternating cadence):** ctrs recovery median **0.356 s** vs
OrbStack **0.322 s** — paired ratio median 1.155, i.e. within ~15 %
with both engines showing correlated tail outliers late in the run.
Was 1.807 pre-fix. The residual gap is inside run-to-run noise; W10's
raw `load_errors` asymmetry is a metric artifact (ctrs fast-refuses,
OrbStack hang-accepts) and is not scored.

### Campaign verification status (2026-11-15, post-frozen-baseline)

- `cargo check --workspace`: clean.
- `cargo test --workspace`: green (earlier doctest failure was a
  missing `rustdoc` on the ad-hoc toolchain PATH, not code).
- `conformance/smoke.sh`: **21/21**, incl. host hygiene
  (`~/.local/share/ctrs` untouched after the `CTRS_STATE_DIR`
  isolation fix in `97650b9`).
- `tests/e2e.sh` against an isolated scratch engine seeded with the
  benchmark image store: **488/488, 0 skipped**. The `always`
  restart-policy fix (`2fb2591`) is verified in-suite; an earlier
  `filter-ancestor` failure was self-inflicted pollution from manual
  `--restart always` test containers, not an engine defect.
- Frozen 10-pair baselines: W1–W10 + W8-under-load + W11 soak, all
  correctness gates green; scorecard in
  `docs/evidence/native-performance.md` above.
- Known open item: W6/W7 *default* `docker`-driver builds trail
  OrbStack because ctrs ships no embedded BuildKit; on matched
  `--driver dc` topology ctrs matches or beats OrbStack on every
  build cell. Tracked as a feature gap, not an engine-perf loss.

### EXP-4 — bulk stdio stream widening (`docker exec`/`cp` out, 2026-11-15)

Unmeasured-path probe after the frozen baseline: `docker exec cat`
of a 1 GiB file and `docker cp` out of the same file, 1 GiB through
the agent's `Msg::Output` path vs OrbStack's stream.

- Baseline ctrs exec-cat: ~1.55–1.78 s (~600 MB/s); OrbStack
  ~1.00–1.12 s (~950 MB/s). `docker cp` single-stream was already
  ~parity (different copy protocol, 256 KiB tar buffer).
- Hypotheses tried and rejected by measurement: drain-until-EAGAIN
  in the agent loop + nonblocking pipe reads (no gain, added
  complexity — reverted); the gap is not poll-cycle count.
- Landed (`dc1f38b`): `MAX_OUTPUT_CHUNK` 64 KiB -> 512 KiB,
  container stdio pipes grown toward 1 MiB, 4 MiB socket buffers
  on both ends of the agent vsock conn and host `VmLink`.
- Result: exec-cat ~1.24–1.37 s (~800 MB/s) vs OrbStack
  ~1.00–1.23 s — residual ~15 % gap, down from ~50 %. `docker cp`
  ~parity (1.64–1.75 vs 1.52–1.54 s, n=2 each).
- Parallel cp-out still shows a shared-conn ceiling on ctrs
  (~3.4 s/stream x2 vs OrbStack ~2.2 s) — the single agent conn
  multiplexes all output; separating bulk transfer onto dedicated
  conns remains the EXP-1 slice-B direction if this gap matters.

**EXP-4 follow-up (`88f3d48`):** the multiplexed case needed the
drain. With each poll wakeup draining a pipe until EAGAIN (up to
8 x 512 KiB chunks; pipe reads are nonblocking, matching the TTY
master path), 4x parallel 256 MiB exec-cat aggregate rose
~743 -> ~790 MB/s and 2-stream ~672 -> ~765 MB/s; single-stream
unchanged. Copy-out vsock conns also take 4 MiB buffers (neutral
alone). Residual vs OrbStack (~1.0-1.05 GB/s aggregate on the same
probes) is the vsock line rate itself; closing it is the custom-
Virtio question, not agent scheduling. `conformance/smoke.sh`
21/21 on the drain-loop agent.

### EXP-5 — unmeasured Docker API surface audit (2026-11-15)

Probing paths outside the W1–W11 cells found `docker import`
outright broken (every `/images/create` went to `pull`; the tar
body tripped the in-memory cap → "bad request framing"). Fixed in
`3593040`: streamed rootfs→store ingest, `--change` support,
correct `repo`/`tag` folding. 300 MiB import: **0.45 s vs OrbStack
3.95 s**. Full audit of the route table (`api.rs` + `ops.rs`)
followed: commit, export, top, stats, pause/unpause, rename,
update, changes, history, events, system df, image/container
prune, search, network connect/disconnect all answer correctly.
Remaining unsupported surface is cleanly 404'd (checkpoint,
plugin, secret/config, manifest, swarm) — feature gaps, not
misroutes.

**EXP-4 residual analysis (next slice, unproven):** the agent's
control conn saturates ~800-950 MB/s guest→host regardless of
stream count (1x ~800, 4x ~790 aggregate), while dedicated relay
conns exceed 1 GB/s. Hypothesis: `conn.write_all` per frame is
blocking — when vsock TX is full the whole single-threaded agent
stalls, so pipe reads and frame production stop between writes,
leaving the vsock pipe underfilled. Relay conns avoid this with a
nonblocking fd + persistent buffer (`relay.rs::pump`). Candidate
fix: give the agent conn the same treatment — nonblocking conn,
FIFO frame buffer, POLLOUT-driven flush, production gated on a
buffer cap for backpressure. ~10 `conn.write_all` sites share the
`out`/`outbox` encoding already; must preserve frame order and the
single-writer invariant. Not yet implemented.

**EXP-4 dedicated exec-output connections (implemented, 2026-11-15):**
the agent now dials a per-exec vsock connection (`EXEC_PORT`) as each
exec starts; that exec's `Output` and `Exited` frames bypass the
multiplexed control connection entirely (nonblocking writes + bounded
pending buffer + POLLOUT drain + 8 MiB backpressure, dial failure
falls back to the control conn, old agents/hosts interoperate). Host
side a `serve_exec` thread deframes and feeds the same `on_event`
fan-out, so attach/detach/internal execs (`buildctl dial-stdio`)
need no API changes; `Exited` on the conn closes the stdin window as
the control-link one does. Verified: stdout/stderr demux, stdin,
exit codes, detached exec, TTY, sha256-identical 1 GiB stream,
smoke 21/21, W7 build+run.

Measured (`exec cat`, warm engine): single-stream 1 GiB ~1.25-1.40 s
(unchanged ~800 MB/s — per-conn rate, not multiplexing, bound);
**4x256 MiB parallel ~1.00 s each ≈ 1.0-1.07 GB/s aggregate, up from
~790 MB/s (+~35%) and at OrbStack's ~1.05 GB/s parallel level.** The
multiplexed-conn ceiling is gone; the residual single-stream ~15-20%
vs OrbStack is per-connection line rate / per-chunk pipeline cost.

**EXP-4 buffered-writer experiment — falsified, reverted
(uncommitted, 2026-11-15):** implemented the candidate above as a
`TxQueue`: `send(MSG_DONTWAIT)` per frame with a persistent FIFO,
POLLOUT-driven flush, `TX_HIGH` (8 MiB) output-fd masking for
backpressure; conn fd stayed blocking for reads so `read_frame`
needed no partial-read state machine. Result was a regression on
both axes: single-stream `exec cat` 1 GiB went ~1.30 s → ~1.55 s
and 4x256 MiB parallel aggregate fell ~790 → ~520 MB/s. Likely
cause: per-frame `send()` returns short on vsock and the extra
queue copy per 512 KiB chunk costs more than the blocking
`write_all` it replaced; POLLOUT re-arming may also spin the
single event loop. Reverted to the committed drain-per-wakeup
agent (`88f3d48`); re-measured back at baseline (1.30 s single,
~1.32 s x4 ≈ 780 MB/s aggregate). Conclusion: the multiplexed-conn
ceiling is not a writer-blocking artifact at this layer — the
remaining ~20% vs OrbStack on parallel bulk is vsock line rate /
scheduler interaction, and the next lever is the campaign's
custom-Virtio question (priority 5) rather than userspace write
buffering.

**EXP-5 virtio-vsock stream buffer — host->guest win, guest->host
neutral (2026-11-15):** kernel source (`af_vsock.c`,
`virtio_transport_common.c`) showed the real flow-control variable:
`SO_VM_SOCKETS_BUFFER_SIZE` sets `vsk->buffer_size`, which becomes
the receive window (`buf_alloc`) each side advertises; it defaults
to **256 KiB** and is clamped to `[min=128, max=256 KiB]` — so the
cap (`_MAX_SIZE`) must be raised *before* the size or the size
clamps back. An earlier `_MAX_SIZE`-only attempt was therefore a
silent no-op (measured identical, reverted). Setting both —
`_MAX_SIZE` then `_SIZE` = 16 MiB — on every `transport::listen`
listener (accepted conns inherit `buffer_size` from the listener)
and on `dial`/`dial_within` sockets (`sys::vsock_stream_buffer`)
raised the guest's advertised RX window 64x.

Measured (warm bench engine, resource-matched): `cat 512 MiB |
docker exec -i` host->guest **~1.40 s -> ~1.00 s (~520 MB/s, +40%)**,
matching the previously documented ~1.0-1.15 s best and cutting the
OrbStack gap (~0.55 s, ~950 MB/s) roughly in half. `docker cp` in
512 MiB ~1.21-1.25 s (tar+fs work dominates; transport share
smaller). Guest->host unchanged within noise: exec-cat 1 GiB
~1.35-1.43 s single, 4x256 MiB parallel ~0.93 GB/s aggregate —
expected, since TX credit is `min(peer_buf_alloc, buf_alloc)` and
the peer is the host-side VZ socket whose window ctrs cannot set.
Published-port relay and exec exit/stdin sanity verified live.
A 64 MiB bound-check was neutral (~0.96-1.09 s, same as 16 MiB),
so 16 MiB stands — the window no longer binds and the residual h2g
gap is the VZ host TX path / agent-frame copies, not the guest
window.

**EXP-6 layer fetch over virtiofs — landed (`ade1da0`); stdin-over-
virtiofs — falsified, reverted (2026-11-15):** `push_layer` now
sends `LayerFetch` (proto 5, kind 76) with the blob's `/mnt/mac`
path when the store metadata is available, and the guest agent
opens the blob straight off the share into the existing
`stage_blob`/install path — no layer bytes cross vsock. A failed
fetch latches `layer_vfs` off and falls back to the inline
`LayerBegin` stream, so old agents and share-less boots are
unaffected; store blobs are minutes-to-days old at fetch time so
the share's freshness lag (below) does not apply in practice.

The follow-on experiment — staging bulk exec stdin through the
same share (`InputFetch` + `Hello.share_ok`, ~2 MiB inline
threshold, `INPUT_WINDOW` credits unchanged) — **failed and was
reverted in full**. Host-staged files under
`data/vfs-stdin/<exec-id>` were written and announced correctly,
but the guest could not reliably read them: directory lookups
returned ENOENT for hundreds of ms after host creation, then
succeeded while `pread` still returned short reads because the
cached inode `i_size` predated the host's writes. Two
compounding causes were isolated:

- **Server/entry freshness lag**: a file created on the host is
  invisible through the share for ~1-2 s. A control probe —
  `docker run -v <file-created-this-second>:/x` — fails with the
  same ENOENT, proving this is a property of the VZ share itself
  affecting *all* consumers, including ordinary bind mounts of
  freshly-created files (a pre-existing limitation, not specific
  to the new code).
- **Guest attr caching**: even after the entry appears, the
  guest's cached attributes serve a stale size, so range reads
  past the old EOF return short. Legacy `mount(2)` rejects all
  option strings on this kernel (6.18, virtiofs is new-mount-API
  only), so `attr_timeout=0`/`cache=none` would require an
  `fsopen`/`fsconfig`/`fsmount` mount path plus a second share
  tag — and would still not fix the server-side lag above.

Per-chunk immutable files were considered (correct size at first
getattr) but hit the same entry-visibility lag, and a fixed
pre-announce delay would add seconds to every bulk stdin for at
best parity with the ~520 MB/s vsock path. Conclusion: the share
is suitable for static, long-lived files (layers, bind sources
that already exist) but not for millisecond-latency protocol
staging. Host->guest bulk remains vsock-bound at ~520 MB/s; the
residual gap to OrbStack (~950 MB/s) needs a different transport,
not a different filesystem.

**Side finding — `docker import` of bsdtar/pax archives failed
unpack (fixed `ddf0164`):** an archive made by macOS `tar` (pax
extended headers carrying `SCHILY.xattr.com.apple.*` keywords)
imported fine host-side but the guest `untar` rejected it
(`failed to unpack .../f.txt`) via BOTH the vsock and virtiofs
layer paths identically — tar-rs applied pax xattrs verbatim and
`com.apple.*` has no Linux namespace. Fixed by collecting
`SCHILY.xattr.*` keywords ourselves, filtering to Linux namespaces
(`user.`/`trusted.`/`security.`/`system.`) and applying
best-effort; verified live (bsdtar archive imports, unpacks,
`docker cp` round-trips) plus a crafted-pax unit test. Real-world
`docker import`/build-context archives from macOS tooling are
commonly pax, so this was a genuine compat hole.

**EXP-6 layer fetch — large-blob verification + retry hardening
(`fa42966`, 2026-11-15):** `LayerFetch` verified at scale: a fresh
`docker import` of a 256 MiB urandom rootfs produced a ~456 MiB
store blob; `docker run` deployed+unpacked it via the share
(`layer via share ... mib=456`) on the FIRST attempt ~1 s after
import — total run 0.56 s including unpack and container setup,
vs ~0.5-0.9 s for the vsock transfer alone at the measured
~500 MB/s-1 GB/s floor. Real pull->run also engages
(`alpine:3.19` rootfs, `mib=3`). Hardened the failure latch: one
transient freshness-boundary failure no longer disables the share
path engine-wide — two retries over ~1.6 s precede the vsock
fallback (guest install is idempotent across retries).
`docker cp` now applies the same namespace-filtered pax xattrs as
layer unpack (`591a690`) — previously it dropped all xattrs.

**W8 attribution for LayerFetch (2026-11-15):** a debug-logged cold
trial (`run-20261115T055651`) shows all four portfolio layers
fetching over the share (`mib=1/16/41/109`, zero retries/failures)
in ~1.65 s total fetch+install. True cold `run_*` vs the last
pre-change cold trial: pg 1.16 -> 0.76 s, py 0.68 -> 0.41 s,
redis ~flat, busybox ~flat — roughly a third off the deploy step,
consistent with removing only the vsock transfer while unpack+vda
install remains. OrbStack still wins `run_pg`/`run_py` (~0.3-0.5 s)
because its in-VM store makes deploy a pull-time cost; ctrs's
host-side store makes it a run-time cost — the same structural
gap as W6/W7, reduced but not closed. `pull_*` remains a ctrs win
(0.07-0.17 s vs 0.09-0.62 s). Caveat recorded: an earlier same-day
baseline showed misleading 0.02-0.04 s `run_*` because the runner
adopted a still-running manual daemon and its `stop()` no-ops on
adopted engines — cold-store trials require a runner-owned daemon.

**Next-slice hypothesis — parallel guest layer installs:** the
remaining run-time deploy cost is unpack+install, which the guest
serializes twice over: `pump_installs` allows ONE install child at
a time, `done_jobs`/`AwaitJob` require replies in request order,
and `ensure_layers` awaits each layer before pushing the next.
Multi-layer images (real-world 5-15 layers; W6/W7 build outputs)
therefore pay sum-of-layers install latency. `LayerFetch` makes
pipelining cheap — each fetch is an independent path the guest
reads itself, so the host could enqueue all fetches at once. A
parallel version needs multiple `InstallWait` slots, `done_jobs`
keyed by seq rather than FIFO, and `AwaitJob` matching its own
seq; the forked-child + result-record machinery already isolates
installs, so the change is contained to agent.rs scheduling plus
unlocked host pushes. Not yet implemented — the single-stream and
parallel exec floors argue the unpack itself may be CPU/IO bound,
so first measure whether 2-4 concurrent installs actually scale on
the 17-vCPU guest before committing to the reorder work.

**Parallel layer installs — implemented (`9fad37c`, 2026-11-15):**
the deploy path's remaining serialization is gone. Guest: up to
`MAX_INSTALLS=4` forked install children unpack concurrently into
their own layer dirs; `done_jobs` is now seq-keyed so `AwaitJob`
replies stay FIFO even when installs finish out of order. Host:
`VmLink::post()` splits send from await; `ensure_layers` runs all
`has_layer` queries first (replies are FIFO — a query after a fetch
would queue behind its install), dedups missing digests (two
fetches for one layer would race `.tmp-<digest>`), sends every
share-eligible `LayerFetch` deferred, then awaits verdicts and
falls back per-layer to the serial path. Measured on a synthetic
5x40 MiB image: all five fetches left in one timestamp and the
whole deploy+unpack+create finished in 0.145 s (~1.4 GB/s
effective) — vs an estimated ~0.75-1.5 s serialized; layer
contents verified byte-identical, smoke 21/21, cargo test 173/173.
W8's single-layer portfolio does not exercise the gain; real
multi-layer images (build outputs, base+app stacks) are where it
lands. vsock `LayerBegin` layers still stage on the agent loop and
queue behind fetch jobs, preserving stream order.

**Re-baseline after transport + deploy work (2026-11-15,
`base-20261115T061138`, `base-20261115T061422`, warm, 3 pairs):**
W2 holds and slightly extends its win — ctrs rps 2559-2638 vs
orbstack 2266-2453 (~1.11x, frozen was 1.07x), p95 4.9-5.0 ms vs
5.6-6.1 ms, zero errors both engines. W9 holds — jobs_1/4/8/16
0.63-0.76 s vs 0.85-2.09 s (frozen 0.64-0.72 vs 0.86-2.11). No
regression from the bulk-conn, stdin-widening, or vsock-window
changes; both engines ran faster than the frozen window (host
conditions), so read the ratio, not the absolutes.

**virtiofs `dax=always` probe — falsified, reverted:** kernel
source confirms virtiofs (`fs/fuse/virtio_fs.c`) accepts only
`dax` mount params; all FUSE cache/timeout options are rejected,
so the W5 bind penalty has no guest-side tuning lever. Adding
`dax=always` to the `/mnt/mac` mount parsed correctly but the VZ
device exposes no DAX cache region — kernel logged "dax can't be
enabled as filesystem device does not support it" and the mount
itself then failed EINVAL, breaking all bind mounts until
reverted. The remaining ~40% bind-vs-volume penalty is inherent
per-op virtiofs RTT; only a guest-side metadata cache (not
exposed by the kernel or VZ) could close it.

**W11 5-min soak pilot, post-concurrency work (2026-11-15,
`base-20261115T061917`, warm, 1 pair, 10x30 s W2 windows + churn
bursts):** all correctness gates green on both engines — zero
errors (781,854 vs 683,857 requests), zero engine deaths, 16/16
churn jobs, exact item counts. ctrs sustained rps_mean 2586 vs
2247 (**~1.15x**), consistent with the W2 re-baseline. Resources:
peak_total_rss_kb 2.14 GB vs 10.86 GB (~5x lower; sampler sums
per-process RSS so shared pages double-count, but the gap is far
beyond method noise); cpu_seconds_est 527 vs 406 (ctrs did ~14%
more requests — ~0.67 vs ~0.59 ms/req, within sampler noise).
The parallel-install/deferred-fetch/bulk-conn changes survived
~782k mixed requests with no leak signal in the RSS trace.

**Remaining-cell re-baseline, same day (warm, 2-3 pairs):** W1
bring-up 3.0 s vs 5.4 s to health (~1.8x); W3 postgres tx_tps
3798-4225 vs 518-843 (~5-7x, up_s 1.66 vs 3.3-3.4); W4 queue drain
0.31/0.14/0.14 s vs 0.55-0.66/0.58-0.66/1.84-1.98 s at 1/4/16
workers (workers_1 improved ~25% vs frozen — bulk conns help the
drain path); W5 edit-test bind 0.088 s vs 0.287 s, volume 0.066 s
vs 0.270 s (~3-4x, bind penalty now 1.33x within-engine); W10
recovery 0.34 s vs 0.33 s (~tie, was a win at frozen — 2 pairs,
within noise), load p95/p99 4.1/5.2 ms vs 5.4/7.9 ms, all
correctness green (kill-window errors scale with ctrs's ~3x higher
attempted rps; committed item counts exact). Every scored cell has
now been re-measured against current code: all win or tie except
the documented W6/W7 builder-topology gap.

**W11 20-min-per-engine soak (2026-11-15,
`base-20261115T063536-2533`, warm, 1 pair):** extends the pilot
10x. All gates green on both engines — zero errors, zero engine
deaths, 72/72 churn jobs each, exact item counts. ctrs: 3,169,115
requests at rps_mean 2620 vs orbstack 2,327,673 at 1905 (**~1.37x**);
peak_total_rss_kb 4.66 GB vs 13.77 GB (~3x lower). Sustained-load
reliability gate now has 20 min/engine of clean evidence on top of
the 5-min pilot.

**Host-side vsock buffer widening — modest h2g win, committed
`a617ba9`:** the guest already advertises 16 MiB vsock stream
buffers (`sys::vsock_stream_buffer`, AF_VSOCK opts — the real
flow-control window; plain SO_SNDBUF does not affect it), but the
host end of every VZ connection kept socket defaults. Added
`tune_vsock_fd` in `crates/ctrs-vmm/src/apple.rs` applying 16 MiB
SO_RCVBUF/SO_SNDBUF to both host-dialed (`Connector::connect`) and
guest-accepted (`PortDelegate::should_accept`) descriptors —
covering published-port relays, exec output conns, and copy conns.
Paired A/B on identical daemon state, 512 MiB transfers: cp-in
(h2g) ~1.00 s -> ~0.82 s (~+22%), exec-stdin (h2g) ~0.96 s ->
~0.85 s (~+12%); cp-out/exec-out/published-download (g2h)
statistically flat — already bounded by the guest-advertised
window and VZ internals. Smoke 21/21 on the signed build. The
remaining h2g residual vs OrbStack is the VZ vsock line rate
itself, not socket buffering.

**Silent-death forensics instrumented (2026-11-15):** the nine
historical daemon deaths left no log line, no panic-hook output and
no crash file — consistent with a fatal signal (Virtualization.framework
is the prime suspect) rather than a Rust panic, since `panic =
"abort"` still runs the hook first. `diag::init` now installs
async-signal-safe handlers for SIGSEGV/SIGBUS/SIGABRT/SIGILL/
SIGTRAP/SIGFPE (plus a sigaltstack for stack-overflow faults) that
write `signal=<n> fault=0x<addr> pid=<pid>` to
`<state>/crashes/signals.log` and `_exit`. Any recurrence during the
W11 soak or later is now attributable instead of silent. Fork-based
unit test verifies the marker; `cargo test -p ctrs` 174/174.

**Holdout gate implemented (2026-11-15, `7f97a18`):** campaign gate
(f) requires an independent real-app check executed once per engine,
never tuned against. `runner.py holdout` drives a frozen Gitea
1.24.7 + Postgres 17 fixture (`fixtures/holdout`): admin via image
CLI, 8 repos x 5 issues seeded over the REST API, a 240-op timed
read workload through the published port, and real `git clone`
smart-HTTP operations. Fixture validated end-to-end on OrbStack
(`holdout-20261115T074006`: health 5.2 s, seed 2.2 s, 59.3 ops/s,
4/4 clones, zero errors) — that run is fixture validation, not the
gate measurement; the scored holdout run happens once per engine at
the final gate. Excluded from the W-matrix; parameters frozen in
`cases.toml`.

**W11 long soak relaunched (2026-11-15):** an earlier launch attempt
exited instantly — `python3` on PATH is 3.9 without tomllib — and
went unnoticed because output was piped through `tail`. Relaunched
with `python3.14` explicitly, ctrs 12 h then orbstack 12 h chained
(`run-20261115T073817` in progress at commit time).

**G1 conformance refresh on the instrumented build (2026-11-15):**
`conformance/failure.sh` 34/34 (first attempt showed a single S6
flake — the post-pressure pull retry hit an ECR `429 TOOMANYREQUESTS`,
confirmed environmental by an immediate clean rerun),
`conformance/isolation.sh` 5/5, both against scratch engines on the
signed binary carrying fatal-signal instrumentation. S12's injected
VM death exercised `Event::Lost` recovery green (containers restarted
on a new generation). One cosmetic wart observed: during deliberate
VM kills the shutdown path logs `saving containers failed: ENOENT`
after the state dir is already gone — recovery still correct, log
severity only. `conformance/run.sh`'s five netns fixtures self-report
`needs iproute2`: they require Linux root by design (README: run
in-guest, qualified in `docs/evidence/crabtables.md`), so the macOS
host lane shows them as harness-level skips, not engine failures.
`tests/linux-host.sh` remains needs-native-host.

### NP-01 measurement qualification executed on the Mac (2026-11-15)

Resumed `docs/native-performance-progress.md` on the campaign host.
Observed state first: the `run-20261115T073817` W11 soak was **not**
running — its runner and both ctrs daemons/VMs were gone; the trial
directory holds 137 load windows + `resources.jsonl` ending
2026-11-15 08:48 PST, ~70 min into the planned 12 h ctrs leg. Recorded
as an incomplete historical observation, not a qualification result.

Harness qualification then ran on this Mac (host `sentry`, arm64,
macOS 27.2):

- `validate-manifest` OK; `unittest discover` **41/41 pass** (34 prior
  + 7 new); `preflight` clean (no failures/warnings).
- Verified native identity: host `arm64`, guest `Image` is an ARM64
  Linux boot executable, `target/release/ctrs` is arm64 Mach-O.
- Provenance extended: every trial record now carries
  `guest_kernel_sha256` / `guest_initramfs_sha256` /
  `guest_data_sha256` (data.img is a 64 GiB sparse file, ~27 s to
  hash, cached by stat signature in `.work/native-perf/`). Reporter
  treats all three as required qualification metadata.
- `prepare` now records per-image `Architecture` for service +
  fixture images on both engines and warns on non-arm64.
- **Noise control implemented and executed**: `noop` runs now assign
  explicit A/B `slot` identity with `design: "noise-control"`; the
  cross-engine reporter excludes them (`noise_excluded`) instead of
  rejecting pairs, and `report --noise` produces a separate
  same-engine slot-pair report that is descriptive-only. Three-pair
  W1-warm ctrs noise run `base-20261115T092425-9b5d`: 3/3 valid slot
  pairs, all correctness checks green, median slot ratios 0.986–0.997
  (slot b marginally faster — ordering noise, CI wide at n=3). Foreign
  host load was present (one ~100% CPU `smolvm` process from another
  project); not campaign-owned, left running — treat these bounds as
  conservative.

NP-01 exit evidence is now met on the Mac: offline regressions, no
global prune/context edits, native arch verified and recorded,
binary/guest provenance hashes, verified builder endpoint for the `dc`
control, fail-closed reporting, dedicated measurement roots, and a
three-pair noise control. Remaining queue work starts at NP-02
(freeze inputs; real W6/W7 fixtures).

## NP-02 vertical slice fixtures (2026-11-15, continued)

W6/W7 now build real pinned upstream apps instead of proxies
(commits `f755f6d`, `67759ce`, `d4394e1`):

- **W6**: zlib 1.3.1 C build (`configure && make -j && make check`)
  on digest-pinned `gcc:14.2.0-bookworm`, plus hyperfine 2.0.0 Rust
  `cargo build --release --locked && cargo test --release --locked`
  on digest-pinned `rust:1.100.0-bookworm` (132 tests pass). Sources
  are sha256-pinned archives fetched on demand.
- **W7**: two real apps through default buildx → `--load` → run
  probes, each with uncached (`--no-cache`)/warm/incremental builds:
  - hyperfine 2.0.0 (Rust → `debian:bookworm-slim` runtime)
  - httpie 3.2.4 (PyPI sdist → `pip wheel` → offline `pip install`
    → `python:3.13-slim` runtime); replaced an earlier gum/Go
    candidate rejected by owner review.
- All four base images are `FROM`-digest-pinned (index digests in
  `assets.lock` `[images.w6]`/`[images.w7]`); both W7 Dockerfiles
  re-validated end-to-end on OrbStack after pinning.

Single-trial smoke runs (descriptive only, not pairs):

| trial | hyperfine_uncached_s | hf_warm_s | hf_incr_s | httpie_uncached_s | httpie_warm_s | httpie_incr_s |
| --- | --- | --- | --- | --- | --- | --- |
| W7 orbstack warm default | 13.211 | 0.443 | 0.754 | 6.820 | 0.409 | 0.824 |
| W7 ctrs warm default | 24.268 | 0.342 | 0.391 | 6.305 | 0.444 | 0.538 |

All correctness checks green on both engines. n=1 — no performance
conclusion; paired baseline is the next step.

## First qualified paired baseline — W6/W7 default driver (2026-11-15)

Runs `base-20261115T100955-dd6b` (W6) and `base-20261115T102429-e057`
(W7): 10/10 valid pairs each, all correctness checks green, provenance
complete, resource budgets matched (guest MemTotal within 0.1% after
`CTRS_GUEST_RESERVE_MIB`). Earlier runs `base-20261115T094322-097d` /
`base-20261115T095725-0e1d` completed but were fully rejected by the
resource gate — retained as visible rejected records.

Median paired ratios (ctrs/orbstack, <1 favors ctrs), 95% bootstrap CI
of paired median, n=10:

| Metric | Ratio | 95% CI | Assessment |
| --- | --- | --- | --- |
| W6 build_rust_s | 0.907 | [0.814, 0.981] | non-inferior |
| W6 build_zlib_s | 1.222 | [1.058, 1.362] | **loss** |
| W7 hyperfine_uncached_s | 0.870 | [0.780, 0.981] | non-inferior |
| W7 hyperfine_warm_s | 0.668 | [0.601, 0.781] | strict-win |
| W7 hyperfine_incr_s | 0.731 | [0.583, 0.915] | strict-win |
| W7 httpie_uncached_s | 0.860 | [0.829, 0.944] | strict-win |
| W7 httpie_warm_s | 1.004 | [0.920, 1.119] | inconclusive |
| W7 httpie_incr_s | 0.931 | [0.868, 1.050] | inconclusive |

Worst qualified cell: **W6 zlib C build — ctrs ~22% slower**
(`make -j$(nproc)` parallel compile on gcc:14.2.0-bookworm). Second:
httpie warm/incremental builds inconclusive (small absolute deltas,
~0.4 s builds dominated by fixed overhead). ctrs leads the Rust
compile+test path and most W7 build→load→probe cells.

Resource metrics (peak_total_rss_kb, cpu_seconds_est) are unmeasured
in these runs — NP-05 scope, not scored.

## Matched-builder control — W6/W7 `--driver dc` (2026-11-15)

Runs `base-20261115T104041-95ab` (W6) and `base-20261115T105554-3c75`
(W7): 10/10 valid pairs each, all correctness green, same pinned
BuildKit image (`moby/buildkit@sha256:aa63…`) in isolated
per-engine docker-container builders.

| Metric | dc ratio | dc 95% CI | default ratio | default 95% CI |
| --- | --- | --- | --- | --- |
| W6 build_rust_s | 0.925 | [0.867, 0.986] | 0.907 | [0.814, 0.981] |
| W6 build_zlib_s | **0.783** | [0.734, 0.907] | **1.222** | [1.058, 1.362] |
| W7 hyperfine_uncached_s | 0.926 | [0.860, 0.981] | 0.870 | [0.780, 0.981] |
| W7 hyperfine_warm_s | 0.506 | [0.393, 0.559] | 0.668 | [0.601, 0.781] |
| W7 hyperfine_incr_s | 0.504 | [0.394, 0.559] | 0.731 | [0.583, 0.915] |
| W7 httpie_uncached_s | 0.851 | [0.814, 0.879] | 0.860 | [0.829, 0.944] |
| W7 httpie_warm_s | **0.659** | [0.625, 0.694] | 1.004 | [0.920, 1.119] |
| W7 httpie_incr_s | **0.633** | [0.565, 0.662] | 0.931 | [0.868, 1.050] |

**Conclusion:** with the builder held constant, ctrs is equal-or-faster
everywhere — strict wins on all six W7 cells and the zlib build. The
entire remaining default-driver deficit is the build→load→first-use
path (docker-driver fallback vs OrbStack's embedded builder), exactly
the NP-04 `/grpc` proxy + exporter-rewrite scope in
`docs/buildkit-driver.md`. Quantified cost of the gap: ~0.2–0.45 s per
W7 build, ~0.6 s on the zlib build, and it flips zlib from win to
loss and both httpie warm/incr cells from win to inconclusive.

## NP-04 default-driver path — first qualified rerun (2026-11-15)

Commit `10cfff4` (h2c `/grpc` + `/session` proxy, `moby` exporter
rewrite to mirror push + retag; repo-scoped manifest GET fix).
Daemon: warm engine, signed release binary, `CTRS_LOG` unset.

**W7 `base-20261115T133627-c5f9` — 10/10 valid pairs, all correctness
green.** Median ratios (ctrs/orbstack, <1 favors ctrs):

| Metric | Ratio | 95% CI | Assessment |
| --- | --- | --- | --- |
| hyperfine_uncached_s | 0.955 | [0.892, 0.983] | non-inferior |
| hyperfine_warm_s | 0.536 | [0.484, 0.645] | strict-win |
| hyperfine_incr_s | 0.537 | [0.464, 0.592] | strict-win |
| httpie_uncached_s | 0.836 | [0.801, 0.869] | strict-win |
| httpie_warm_s | 0.520 | [0.477, 0.567] | strict-win |
| httpie_incr_s | 0.550 | [0.474, 0.593] | strict-win |

The two previously inconclusive httpie warm/incr cells are now strict
wins; every W7 cell meets or beats OrbStack on the default driver.

**W6 `base-20261115T131324-d1cc` — 9/10 valid pairs** (pair 7 ctrs
trial failed: buildx session stream RST ~100 ms into the zlib solve,
buildkitd logged `Solve ... context canceled`; 1 occurrence in ~40
session streams — treated as a transient, under observation). Ratios
on the 9 valid pairs: build_rust_s 0.914 [0.887, 1.002],
build_zlib_s **0.562** [0.477, 0.611] — the prior zlib default-driver
loss (1.222) is gone by a wide margin, consistent with the dc-control
0.783 once the archive round-trip is removed. Reporter requires 10
valid pairs to establish a win, so W6 is being rerun
(`np04-default-baseline3-w6-*.log`).

Invalidated: `base-20261115T125538-2dc3` W7 trials (mirror retag bug,
fixed in `10cfff4`); its W6 trials remain valid but are superseded by
the same-commit rerun.

## NP-04 follow-up — 20-pair W6 and flake hunt (2026-11-15/16)

`base-20261115T153838-7b71` (W6, `--driver default`, 20 pairs, commit
`f3adade`, CTRS_LOG=debug diagnostic run): **20/20 valid pairs, all
correctness green.** build_rust_s 0.892 [0.865, 0.916] strict-win;
build_zlib_s 0.491 [0.460, 0.559] strict-win. Debug-on timings —
clean confirmation run in flight.

Intermittent-failure investigation: two distinct causes isolated.
(1) Mirror manifest PUT EOF'd the conn when a manifest referenced
blobs still committing from a concurrent push (buildkitd dedups blob
uploads across simultaneous solves) — buildkitd logged `Put
.../manifests/sha256:...: EOF` after ~15 retries then failed the
solve. Fixed in `f3adade`: 20s presence wait + proper `400
BLOB_UNKNOWN`. (2) `/session` RST_STREAM code 3 (FLOW_CONTROL_ERROR)
from buildkitd ~100ms into a solve, ~1/300+ builds, not reproduced
since instrumentation landed; per-frame session rx logging, RST/GOAWAY
error codes, and window-overdraw warnings are in the tree to catch it.

## NP-04 clean final baselines (2026-11-16)

`np04-final-w6w7-20261115T160823.log`, debug OFF, sequential W6 20-pair
then W7 10-pair `--driver default`:

- W6 `base-20261115T160823-a303` (commit `f8ce6ac`): 18/20 valid pairs;
  pairs 6 and 16 ctrs failed `zlib build rc=1: failed to solve:
  Canceled: context canceled` — the `/session` RST code-3 flake, twice
  in one run (00:15:56Z, 00:29:23Z per daemon WARN log). Ratios on valid
  pairs would be strict-win (rust 0.924 [0.911, 0.947], zlib 0.545
  [0.516, 0.597]) but correctness failures disqualify the run; a clean
  20-pair rerun is required.
- W7 `base-20261115T163439-18ee` (commit `bde4681`): **10/10 valid
  pairs, zero failures.** All six metrics strict-win: hyperfine
  uncached 0.890 [0.827, 0.909], warm 0.399 [0.361, 0.458], incr
  0.438 [0.405, 0.464]; httpie uncached 0.785 [0.737, 0.792], warm
  0.414 [0.392, 0.449], incr 0.457 [0.438, 0.542]. Resource cells
  (peak_total_rss_kb, cpu_seconds_est) still unmeasured.

Forensic upgrade deployed after the run: cumulative session sent-byte
counter + conn/stream/default window snapshot logged on RST — pending
reproduction under `CTRS_LOG=debug` (`np04-w6-debug-hunt-*.log`, W6
20-pair rerun in flight).

## NP-04 session flake root-caused; clean W6 qualified (2026-11-16)

Root cause of the intermittent `/session` RST_STREAM code-3
(FLOW_CONTROL_ERROR): our h2 `Win::settings()` reset the default
stream window and cleared per-stream state on every
SETTINGS_INITIAL_WINDOW_SIZE change. grpc-go's BDP estimator sends
those updates mid-stream; per RFC 7540 §6.9.2 each live stream's
window must shift by the delta, so we over-counted by bytes already
sent and over-drew — buildkitd's grpc inFlow check
(`http2_server.go` `s.fc.onData`) answered RST code 3. Caught live
by the new forensics: `sent=785951 conn_win=69800
stream_win=53317` — windows positive in our (wrong) books.

Fix (commit `67ff261`): `settings()` applies the delta to each
tracked stream window; session sender also stops once the builder
ends its side (`peer_done` + dead-aware `wait_dead`). Same Win is
used for the buildx-facing direction, which had the identical bug.

Post-fix clean baseline `base-20261115T173857-2d73` (W6,
`--driver default`, debug OFF, commit `67ff261`): **20/20 valid
pairs, zero failures, zero session resets.** build_rust_s
0.9325 [0.9204, 0.9367] strict-win; build_zlib_s 0.5294
[0.4985, 0.5497] strict-win.

W6+W7 default-driver timing cells are now qualified:
- W6 `base-20261115T173857-2d73`: rust 0.933, zlib 0.529 — strict.
- W7 `base-20261115T163439-18ee`: all six metrics strict-win
  (hyperfine 0.890/0.399/0.438; httpie 0.785/0.414/0.457).

Resource cells (peak_total_rss_kb, cpu_seconds_est) remain
unmeasured in every run — a harness gap to close before the full
contract can be scored.

## Qualified-baseline queue — first results (2026-11-16)

`queue-qualify-20261115T181026.log`, all `--pairs 10 --driver
default`, warm state, resource sampling ON (new attribution +
cputime deltas):

- W1 `base-20261115T181027-6546`: 10/10 valid. wall 0.580
  [0.577,0.843], time_to_health 0.551, time_to_roundtrip 0.551 —
  all strict-win; RSS 0.580 strict, cpu 0.197 strict.
- W2 `base-20261115T181216-0169`: 10/10 valid. rps 0.896 strict,
  p95 0.849 strict, p99 0.763 strict, RSS 0.921 strict; p50 0.913
  non-inferior; **cpu_seconds_est 1.187 [1.139,1.221] LOSS** —
  ctrs burns ~20% more CPU-seconds under API load (pairs 2–10
  consistent ~1.15–1.25; pair-1 orbstack 163.8s outlier is
  first-trial warmup, median-robust). Per-proc breakdown: ~96% of
  the delta is inside the guest (Virtualization.XPC ~33–35 CPU-s
  vs OrbStack Helper ~30–33 per 20s trial); daemon ~1.4s.
  Real data-path efficiency gap to investigate (virtio-net/vsock
  forwarding vs orbstack's path, or guest agent overhead).
- W5 `base-20261115T182037-0086`: 10/10 valid. bind 0.231 strict,
  volume 0.176 strict, cpu 0.092 strict; RSS 1.010 [1.005,1.022]
  non-inferior (upper ≤1.03 → meets bound).

Strict-win tally for the ≥2-of-W1/W2/W5/W8 requirement: W1 + W5
already qualify; W8 in flight showing ~8x wall lead.

## Queue results continued (2026-11-16)

- W3 `base-20261115T182240-4990`: 10/10 valid, all timing/cpu
  strict-win (tx_tps 0.269, up 0.525, migrate 0.415, checkpoint
  0.402, cpu 0.317); RSS non-inferior.
- W4 `base-20261115T182349-ba18`: 10/10 valid, all strict-win
  (workers_1/4/16 = 0.538/0.184/0.076, RSS 0.883, cpu 0.149).
- W9 `base-20261115T182453-3c7a`: 10/10 valid, all strict-win
  (jobs_1/4/8/16 = 0.678/0.499/0.442/0.314, cpu 0.581); RSS
  non-inferior.
- W10 `base-20261115T182626-dce5`: 10/10 valid but TWO losing
  cells: recovery_s 1.125 [1.102,1.161] (ctrs ~0.345s vs
  orbstack ~0.31s — consistent ~40ms gap, likely first-connect
  port-forward latency on the vsock path) and cpu_seconds_est
  1.218 [1.203,1.268] — same sustained-load guest-CPU gap as W2.
  RSS strict-win 0.880.
- W8 `base-20261115T182133-1eca`: pull_wall 0.140 strict,
  cpu 0.047 strict, RSS non-inferior; load_rps/p95/p99
  unmeasured (needs --under-load, queued in follow-up).

Losing-cell ledger: W2 cpu 1.187, W10 recovery 1.125 + cpu 1.218.
Both plausibly share the vsock-relay/guest-agent networking
overhead; CTRS_VMNET=1 A/B after the queue is the discriminating
experiment.

## W8 under-load + W6/W7 resource runs (2026-11-16)

- W8 `base-20261115T185555-a692` (--under-load): 10/10 valid, ALL
  strict-win — pull 0.119, load_rps 0.789, p95 0.640, p99 0.482,
  RSS 0.642, cpu 0.682. W8 fully qualified.
- W6 `base-20261115T183448-224d` (resource run): 10/10 valid —
  zlib 0.541 strict, cpu 0.914 strict; rust 0.953 non-inferior,
  RSS non-inferior. Timing already proven by the 20-pair
  `base-20261115T173857-2d73`.
- W7 `base-20261115T184735-18b8` (resource run): 9/10 valid —
  pair-1 ctrs httpie uncached build failed; daemon WARN shows
  `builder retag failed: BuildKit pushed no image` (a symptom —
  retag errors are warn-only; the solve itself failed and W7 did
  not capture stderr). W7 build stderr capture added; rerun in
  flight. Timing already proven by `base-20261115T163439-18ee`.

## W7 resource re-qualification on the 1 TiB disk (2026-11-16)

- Guest data disk grew 64 GiB → 1 TiB sparse (`457767e`) after the
  `base-20261115T190637-f182` rerun exposed ENOSPC: pair 3 died on
  `no space left on device` in buildkit's content ingest, pair 7 on
  a cargo exit-101 cascade. OrbStack's disk is uncapped
  (`machine.docker.disk_bytes: 0`, ~170 GiB in use); the fixed 64 GiB
  template was a structural deficit, not a workload artifact.
  `ctrs-warm` migrated in place: containers removed, `data.img`
  replaced by APFS clone of the new template, 320 images retained
  via the host blob store. `guest_data_sha256` provenance changes
  from this asset forward (now extent-hashed, `9da0d10`).
- W7 `base-20261115T193710-0d96`: **10/10 valid, all eight cells
  strict-win** — hyperfine 0.891/0.448/0.436, httpie
  0.775/0.410/0.485, RSS 0.727 [0.601,0.846], cpu 0.569
  [0.513,0.613]. Source `457767e`. This supersedes the 9/10
  `base-20261115T184735-18b8` attempt for resource qualification;
  timing stands on `base-20261115T163439-18ee`.

## W2 CPU-loss investigation (2026-11-16)

Goal: explain `cpu_seconds_est` 1.187–1.281 losses under sustained
API load. Experiments, all on the same W1 stack (api+pg+redis),
identical load.py seed/duration:

- **CTRS_VMNET=1 A/B** (`base-20261115T195437-467a`, 10/10 valid):
  cpu 1.281 — WORSE than vsock's 1.187; latency cells improved
  (p50/p95/p99 all strict-win, rps 0.842 strict-win) but the CPU
  hypothesis is rejected. vmnet stays opt-in; daemon back on vsock.
- **seccomp=unconfined A/B**: api cgroup cpu 19.48s vs 19.95s
  confined — ~2% effect, exonerated.
- **bridge-nf-call-iptables=0**: no change (6.16s vs 6.23s system).
- **Guest topology**: container networks are real kernel bridges
  (ctrs15, 10.89.0.0/24); conntrack count stays ~44 under load —
  inter-container traffic is clean L2, no per-packet netfilter.
- **Controlled cgroup cpu.stat delta** (20 s load, seed 7):
  ctrs api 19.95 CPU-s (system 6.23s, 31%) vs orbstack api
  13.59 CPU-s (system 2.35s, 17%) at equal rps (~2450). Under
  vsock the gap persists (18.4s/5.1s): **+47% container CPU,
  ~2.6x system time, inside the api cgroup itself** — not the
  port-forward/agent path.
- **Microbench**: open/close syscall rate 1.99M/s vs 2.16M/s
  (~8% slower); context switches 3.7 voluntary vs 2.0+2.1 mixed
  per request — neither explains ~130us/req of extra kernel time.
- Kernel mitigations/vulnerabilities identical; TCP sysctls
  similar; kernels differ (ctrs 6.18.58 vs orbstack
  7.2.12-orbstack-00394).

**Status**: root cause not isolated; points to guest-kernel
syscall/network-stack efficiency (6.18 vs OrbStack's custom 7.2).
Next: in-guest perf/ftrace profiling of the api container's syscall
mix, or a kernel-config diff against OrbStack's. W10 cpu/recovery
losses likely share this root cause.

## Footprint sweep + phys_footprint correction (2026-11-16)

Full W1–W10 sweep `queue-footprint-20261115T202223.log`,
`--driver default`, 10 pairs/case, warm engine on 1 TiB disk:

- W1 `base-20261115T202223-4df7`, W3 `base-20261115T202439-3619`,
  W4 `base-20261115T202626-9e40`, W5 `base-20261115T202740-a225`,
  W9 `base-20261115T202904-a029`, W10 `base-20261115T203105-29a0`,
  W7 `base-20261115T203959-cc38`, W2 `base-20261115T204938-9af6`,
  W6 `base-20261115T205817-9966`: all 10/10 valid pairs except
  noted cells. Timing cells strict-win nearly everywhere (W2 rps
  0.825, p99 0.449; W7 all six strict-win; W6 rust 0.881/zlib
  0.452). **cpu_seconds_est losses on this sweep: W2 1.40
  [1.15,1.73], W7 1.42 [1.24,1.51], W9 1.49 [1.47,1.51]** — worse
  than earlier runs; W2 leg overlapped leftover diagnostic
  containers on the ctrs engine (noted, CPU metric only counts
  matched pids but scheduler contention may inflate wall-linked
  work). W3/W4 cpu cells `incomplete`/`unmeasured` (missing
  cputime on short trials).
- **W8 `base-20261115T204801-f1f1` INVALID for scoring**: the 1 TiB
  disk migration discarded named volume `npw8-reg-data-ctrs`;
  `ensure_registry` recreated it empty and all ctrs pulls 404'd
  (`manifest unknown`). OrbStack side unaffected. W8ul
  `base-20261115T211141-bafd` failed identically on ctrs.
  Remedy: `runner.py prepare --engines ctrs` then merge the
  orbstack portfolio section back into `w8-portfolio.json`
  (prepare rewrites the whole file per selected engines).
- **phys_footprint parser bug (fixed `3503831`)**: collect.py
  parsed the category-table `Footprint:` total, NOT the
  `phys_footprint:` auxiliary field (Activity Monitor metric).
  The category total excludes IOKit/IOSurface-accounted pages and
  undercounts the OrbStack VM helper >10x (recorded ~1.5 GB vs
  real phys_footprint 15–19 GB). All `peak_phys_footprint_bytes`
  values in the sweep above are the wrong (smaller) number —
  footprint cells need full re-measurement. Fallback order is now
  phys_footprint → category total; records carry
  `footprint_field: "phys_footprint"`.

## W2 futex/wake-path decomposition (2026-11-16)

Controlled in-guest C microbenchmark (static binary, 2 threads,
atomic state handoff, N=20000–40000; source preserved at
`.work/native-perf/futexping.c`):

| test | ctrs 6.18.58 | orbstack 7.2.12 |
| --- | --- | --- |
| futex ping-pong, unpinned | 7.3 us/handoff | 0.4 us/handoff |
| same after HZ_1000+PREEMPT+LSE kernel | 6.7 us | — |
| pure atomic spin handoff | ~0.03 us | ~0.1 us |
| futex pinned to one CPU | 0.5 us | 0.5 us |
| futex + all 17 vCPUs kept busy | 8.0 us | 25.3 us |

Findings: same-CPU wake+schedule is identical (0.5 us); the gap
is specific to the **cross-vCPU wake path** (~7 us vs ~0.4 us).
Guest-idle check: both guests idle ~100% (/proc/stat), so vCPUs
halt on both — the difference is interrupt delivery / host-side
vCPU resume, not guest idle behaviour. Kernel candidate
CONFIG_HZ_1000 + CONFIG_PREEMPT + ARM64_USE_LSE_ATOMICS built
and tested: 6.7 us — **does not close the gap; reverted**
(`guest/kernel/ctrs.config` back to PREEMPT_VOLUNTARY/HZ_250,
Image rebuilt). Next hypothesis: host-side vCPU wake mechanics —
ctrs uses the com.apple.Virtualization.VirtualMachine XPC service
while orbstack's VM lives inside "OrbStack Helper" (possibly
VZ-in-process or a custom hypervisor). Investigate VZ vCPU
scheduling/QoS vs orbstack's mechanism before more kernel work.

## Archived pre-reorientation checkpoint (resumed from 94f19a8)

The following checkpoint is historical pilot reporting. Its qualification
claims are superseded: resource ownership/completeness, representative
fixtures and durability were not established. The combined kernel candidate
was rejected; this does not exonerate guest kernels generally. Unpinned
futex results do not establish equivalent cross-vCPU placement. Guest idle
counters do not prove host halt/spin behavior; process names do not identify
OrbStack’s VM mechanism. W10 requires independent causal tracing.

# macOS performance campaign: progress and continuation

**PAUSED 2026-11-16 — campaign winddown; see Resume here for handoff.**
Owner steering: 2026-11-15. Contract:
[`campaign-native-performance.md`](campaign-native-performance.md).
Maintain this file in place as the single queue/checkpoint. Append compact
experiment outcomes to `docs/evidence/native-performance.md`, not a second
queue or turn-by-turn status diary.

## Resume here

**Status:** paused 2026-11-16 (campaign winddown). Resume prompt:
"resume the campaign docs/native-performance-progress.md".
First command: `python3.14 bench/native/runner.py preflight`.

Last accepted revision: `3503831` on `main`, tree clean. Guest
assets rebuilt to stock kernel config (PREEMPT_VOLUNTARY/HZ_250/
no LSE — the HZ_1000+PREEMPT+LSE candidate was built, measured
6.7us vs 7.3us futex ping-pong, and reverted as insufficient).
Warm ctrs engine left running at
`.work/native-perf/engines/ctrs-warm` (CTRS_CPUS=17,
CTRS_MEMORY_MIB=45091, vsock); if absent, relaunch
`target/release/ctrs daemon` with CTRS_DATA_DIR/CTRS_STATE_DIR/
CTRS_SOCKET under that dir (see `daemon-manual.log` there).

Qualified (`--driver default`, warm, 10 pairs): W1/W3/W4/W5/W6/
W7/W9 timing strict-win; W7 resources `base-20261115T193710-0d96`
all-eight strict-win; W8 under-load `base-20261115T185555-a692`
strict-win. Full detail: `docs/evidence/native-performance.md`.

Blocking debts before meet/exceed OrbStack:
1. `peak_phys_footprint_bytes` parser fixed `3503831` — every
   earlier value is the wrong (category-total) field; full
   W1–W10 footprint re-run required.
2. W8 ctrs registry volume lost in 1 TiB migration — run
   `runner.py prepare --engines ctrs`, then restore the orbstack
   section of `.work/native-perf/w8-portfolio.json` (prepare
   rewrites the whole file). Then rerun W8 + W8 `--under-load`.
3. W2 `cpu_seconds_est` loss: cross-vCPU futex wake ~7us vs
   ~0.4us orbstack; same-CPU equal; guest kernel config
   exonerated. Next: host-side vCPU wake path — ctrs uses the
   Virtualization.VirtualMachine XPC service, orbstack's VM lives
   in "OrbStack Helper". W10 cpu/recovery likely shares it.
4. W7/W9 cpu losses on latest sweep (1.42/1.49) may be
   diagnostic-container contention — re-measure on a clean host.
5. Unimplemented: idle CPU/footprint + growth budgets; W11 12h x2.
   Allocated storage: per-trial `/system/df` snapshot + W3
   `pgdata_allocated_bytes` landed `6dbe2b8` (needs rerun).

Parked branches: none campaign-owned.
`chore/ctrs-proto-target-gate` and `repomod/fix/*` predate the
campaign — leave untouched (stale worktree already pruned).

Next slice: W8 prepare+rerun → full footprint sweep → W2
host-path investigation → W11 legs.

**Historical task detail (NP-04, complete):**
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

**QUALIFIED (2026-11-16):** post-fix clean W6
`base-20261115T173857-2d73` — 20/20 valid, zero failures/resets;
rust 0.9325 [0.9204,0.9367], zlib 0.5294 [0.4985,0.5497], both
strict-win, debug OFF, commit `67ff261`. With W7
`base-20261115T163439-18ee` (10/10, six strict-wins) the W6+W7
default-driver timing cells are done. Evidence recorded.

**Resource instrumentation landed (2026-11-16):** every trial
(W1–W11, holdout) now runs `collect.py` sampling →
`peak_total_rss_kb` + `cpu_seconds_est` per record (verified live on
a W9 smoke: 14 samples, ~11.3 GB peak RSS, 15.0 CPU-s). NOTE: the
campaign doc flags ps-RSS/pcpu as NOT qualified physical-memory/CPU
accounting — ownership attribution + validated physical method +
idle/growth budgets are still owed before resource gates can be
claimed. Allocated-storage cells likewise unimplemented.

**Qualified-baseline queue IN FLIGHT:**
`.work/native-perf/queue-qualify.sh` → log
`.work/native-perf/logs/queue-qualify-20261115T181026.log`.
Sequential: W1,W2,W5,W8 (exceed candidates), W3,W4,W9,W10 (meet
completeness), then W6,W7 10-pair resource re-qualification — all
`--pairs 10 --driver default`. ETA many hours; check the log tail
periodically. Warm daemon: clean (no CTRS_LOG), fixed binary
`67ff261`+.

**Resource attribution fixed (2026-11-16):** the orbstack match
pattern's bare `virtualization` token double-counted the ctrs VM
(XPC service) into orbstack trials; ctrs now matches
`com.apple.Virtualization.VirtualMachine` explicitly and orbstack
keeps only its own names. `collect.py` records cumulative CPU time
per pid; `summarize_trace` prefers exact cputime deltas (pcpu
fallback). Verified live: ctrs trial samples daemon+VM, orbstack
pattern excludes the XPC. Still owed for full resource gates:
validated physical-memory method (footprint/vmmap), idle/growth
budgets, allocated-storage cells.

**Queue results so far (2026-11-16):** W1 strict-win all cells
(`base-20261115T181027-6546`); W5 strict-win (`...-182037-0086`,
RSS non-inferior 1.010); W8 pull/cpu strict-win but load cells
UNMEASURED — needs `--under-load` rerun (queued in
`queue-followup.sh`, waits for main queue); **W2 has a real
losing cell: cpu_seconds_est 1.187 [1.139,1.221]** — ~20% more
guest CPU under sustained API load, ~96% inside the VM XPC.
Leading hypothesis: published-port vsock relay + guest-agent
userspace proxying per connection vs orbstack's vmnet kernel
path; ctrs deliberately defaults to vsock (`ports.rs`
`vmnet_enabled`, opt-in `CTRS_VMNET=1` after bulk-pull stall
measurements). W1's light-I/O cpu ratio was 0.197 — consistent
with per-packet/conn overhead dominating only under load.
NEXT INVESTIGATION: after queue, rerun a W2 trial with
`CTRS_VMNET=1` daemon and compare cpu_seconds_est; if vmnet
closes the gap, weigh the bulk-pull stall trade-off (maybe
hybrid: vmnet for interactive ports, vsock budget for bulk).

**Superseded next action (queue finished 2026-11-16):** the
`queue-qualify`/`queue-followup` logs are complete; see "Resume here"
for the current action.

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

## Measurement repair, first bounded slice (2026-11-15 resume)

Checkout was clean at reviewed 94f19a8, with no newer commits. Removed
category-table fallback completely. Missing required footprint PIDs and
partial cumulative CPU counters invalidate the corresponding scored cells.
Name discovery is explicitly unverified; historical traces cannot qualify
physical memory or CPU. CPU ticks no longer wait for footprint subprocesses;
footprint records expose required/missing PIDs, errors and monotonic timing.
Sampler version/hash and process start strings are recorded. This is not yet
verified engine ownership or running executable/boot provenance.

Validation: 52 offline tests passed (`python3.14 -m unittest discover -s
bench/native -p 'test_*.py'`); preflight passed, report
`.work/native-perf/results/preflight-20261115T215924.json`. No performance
claim, sampler overhead comparison, or clean scored pilot has been made.

## Ownership and adopted-artifact validation (2026-11-15 resume)

Open Unix socket identifies daemon; open dedicated engine data.img identifies
ctrs VM helper, excluding other VirtualMachine processes. Required processes
carry PID, ps lstart, executable path/inode/hash; collector verifies comm/start
each tick. Kernel/initramfs open inode and mtime must predate process start.
The existing ctrs VM fails this check: Image mtime 1794806815 is later than
7488's start (2026-11-15 21:24:06 local). This proves provenance uncertainty,
not that bytes necessarily differ. Current guest/out hashes cannot identify
this boot. Restarting the owned VM is the next calibration prerequisite.

OrbStack collection-only pilot `.work/native-perf/results/strict-ownership-pilot`
identified socket owner 1396 plus application 1299; 20 CPU ticks, one complete
phys_footprint sample, no collection errors. Not a timing, overhead, or engine
comparison; worker activity was permitted because this was functional validation.
56 offline tests pass, including unrelated VM exclusion and stale artifact/PID
rejection. Explicit phase boundary accounting and overhead calibration remain.

## Explicit phase boundaries and short ctrs collection pilot

Owned benchmark VM restart preserved all 86 volume names; disk was not replaced.
Boot/executable discovery now passes. This is identity preservation only, not
volume-content or power-loss durability evidence.

W2 pilot `run-20261115T220707-31a0`, duration 3 s, concurrency 4, seed 7:
correct item count 2,799 (500 seed + 2,299 acknowledged writes), 5,454 successful
reads, zero errors. 34 CPU ticks, complete required-process footprint sample,
no collection errors. Raw explicit phase CPU totals setup/workload/cleanup
0.88/5.55/0.09 CPU-s. Whole-trial sampled CPU is 6.50 s and must not be used as
workload CPU. Boundary method is ps cumulative CPU, 0.01-s resolution, with
~37-ms snapshot durations saved; operation wall excludes boundary collection.
Pre/post perf-gate-ready passed. No engine ratio or observer-overhead claim.
Terminal asynchronous footprint samples now survive sampler shutdown without
altering CPU process coverage. 58 offline tests pass.

## Observer calibration rejects the subprocess sampler

Run `sampler-calibration-20261115T220906`: 5 alternating on/off pairs per engine,
4-second closed-loop W2, concurrency 4, seed 7. Both modes retain explicit CPU
boundaries; off mode omits periodic sampling/footprint subprocesses. Each trial
creates a fresh stack and verifies exact item count. All 20 trials passed
correctness and pre/post perf-gate-ready. Raw records, plan, power/thermal/load
and paired computations are saved in that run directory. This diagnoses the
observer and does not compare engines or establish equal-work efficiency.

| Engine | Throughput on/off median (range) | CPU per success on/off median (range) |
| --- | --- | --- |
| ctrs | 1.0440 (1.0153–1.0717) | 0.9618 (0.9255–0.9944) |
| OrbStack | 0.8383 (0.8010–1.0238) | 1.1168 (0.9695–1.1339) |

Predeclared tolerances: median throughput drop <=3%, CPU/success inflation <=5%.
OrbStack fails both, rejecting sampler v2 for scored comparison. The ctrs
increase is also a warning about observer influence, not product progress.
The mechanism within ps vs footprint is not yet isolated. Native rusage v0
counters are the bounded next repair: one syscall per process supplies CPU,
physical footprint, wake counts and high-resolution kernel start identity.
Local SDK sys/resource.h defines the ABI; conversion uses mach_timebase_info.
Native self CPU delta agrees with process_time and bad PID errors surface.
61 offline/native behavioral tests pass. A fresh identical calibration is in
flight; no acceptance claim yet.

Disk audit finding: crates/ctrs-vmm/src/apple.rs uses Cached+Fsync and still
claims the disk is wholly resendable. Named volumes invalidate that assumption.
The installed SDK distinguishes Full (synchronized permanent storage, including
power loss) from Fsync (best effort, drive cache may remain). Guest flush path,
actual installation migration and comparable OrbStack guarantees remain unaudited;
no database or storage superiority claim is supported by restart tests.

## Native sampler v3 short calibration accepted for diagnostic iteration

`sampler-calibration-20261115T221334`: same predeclared five alternating pairs
per engine, 4-s W2, concurrency 4, seed 7, all 20 correctness and host gates pass.

| Engine | Throughput on/off median (range) | CPU/success on/off median (range) |
| --- | --- | --- |
| ctrs | 0.9935 (0.9476–1.1062) | 1.0024 (0.8916–1.0548) |
| OrbStack | 0.9906 (0.9330–1.1084) | 0.9702 (0.9372–0.9969) |

Both pass the declared median throughput-drop <=3% and CPU/success-inflation
<=5% limits. Individual short-trial variation remains substantial; do not infer
zero observer effect or qualified engine ratios. This unblocks fixed-work W2
investigation. One OrbStack trace's native sample elapsed 45–220 microseconds;
this includes both required processes and is not an application speed claim.

Out-of-band footprint validation: native-before helper 15,389,157,464 bytes and
app 72,008,736 bytes exactly matched footprint's corresponding phys_footprint
auxiliary values. Native-after showed small live changes. Raw command output
and values saved in footprint-validation.txt/json in the run directory.
This exposed a second parser bug: Shared-with headings contain PIDs and the
old parser reassigned the following auxiliary value. Only process headers with
Footprint now switch owner. Regression includes actual two-process shared
heading output. Native sampling does not parse that command output.
62 tests pass, including CPU timebase vs independent process_time, bad PID,
missing VM, kernel start identity reuse, category-only output and shared headings.

## Equal-work W2 v2 initial pilot

`base-20261115T221909-0859`, one pair, concurrency 4, 10,000 fixed operations:
both engines 6,978 successful reads and 3,022 writes; zero failures; every seed
and acknowledged-write name/payload matches the database exactly. Host workload
CPU ctrs 6.416796 s (0.0006416796 per success), OrbStack 5.428005 s
(0.0005428005 per success). API cgroup CPU ctrs user/system 2.440710/1.103210 s,
OrbStack 2.259942/0.534660 s. Counter-reader exec overhead is disclosed in raw
records. The system-CPU difference remains a useful profiling lead at equal work;
this single short pair is not significance or a qualified engine verdict.
Pre/post host gates passed. Response payload checks were subsequently tightened,
so the next batch starts fresh with the final v2 behavior. 65 tests now pass.
Five-pair 50,000-operation confirmation is awaiting an exclusive window; host gate
found unrelated Niceforge import work. Do not stop that external workload.

## W2 fixed-work implementation and contaminated confirmation

W2 v2 adds fixed total work, deterministic per-worker seeded request sequences,
validated response payloads, successful read/write/failure counts, acknowledged
write manifests, exact all-row persisted payload verification and explicit
workload CPU/success. Saturation remains a separate duration mode. CPU efficiency
ratios use each raw pair directly; whole-trial CPU is removed from W2 scoring.
API cgroup cpu.stat is recorded before/after separately from host engine CPU.
Fatal worker exceptions now fail the driver instead of yielding a partial success.
67 tests pass, including fixed-work identity, corrupt/duplicate/missing rows,
normalized reporting and contaminated-measurement rejection.

`base-20261115T222030-7ef3`: all ten trials completed exactly 50,000 successful
operations, correct names/payloads and zero errors. Post perf-gate-ready -1 failed
on unrelated Niceforge runner PID 42860; whole batch is INVALID FOR TIMING SCORING.
Preserve trials.collected.jsonl raw originals; trials.jsonl annotates invalidation
without changing values. Reporter retains 5/5 correct per engine and rejects all
five pairs. Do not use its apparent latency, throughput, memory or CPU ratios as
wins/losses. API system CPU was ~5.1–5.3 s vs ~2.4–2.6 s for equal work, a profile
lead only because host exclusivity was not proven. Clean confirmation remains
pending; the unrelated service is preserved. No repeated sweep is warranted.

## Application profiling tool capability check

Prepared one disposable diagnostic image `np-w2-profiler:diagnostic` on OrbStack,
from python:3.13-slim digest e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90;
installed only diagnostic strace/linux-perf/procps (no product dependency added).
Image config e1f2c2f7fc6230ef2d12f02d503a1b4d503a9f287cd681b0fb0cc50f41e56a3e;
manifest list d3ea812e9f38129a33a0e2a67afecdaabbccd00555457639415f423c62945357.
Actual package versions: strace 6.13+ds-1, linux-perf 6.12.117-1, procps 2:4.0.4-9.
Raw metadata and capability output in `.work/native-perf/results/w2-profile-tools`.
Software task-clock/context-switch/migration counters work in an owned diagnostic
container, and a container-local tracefs mount exposes sched events/instances.
No tracing switches or other guest tracer were changed. OrbStack kernel
7.2.12-orbstack-00394-gbecdd6130068, boot ID 7fdc0939-a83c-4954-ba60-507f1d67d717.
These are capabilities, not an API profile. Export/load the identical profiler
image to ctrs before causal comparison. Profiles do not enter timing scores.
