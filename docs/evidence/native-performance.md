# Evidence: native-workload performance vs OrbStack (macOS lane)

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

## Scorecard — pilot results (2026-11-14, warm daemon both sides)

**Methodology correction:** an earlier pilot (superseded, raw data
deleted) restarted the ctrs daemon per trial while OrbStack's stayed hot,
mixing conditions. All numbers below come from runs where each engine's
daemon/VM stayed up for the whole batch (`keep_warm` in `runner.py`).

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
| W3–W11 | declared in `bench/native/cases.toml`, not yet implemented |
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
