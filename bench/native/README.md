# bench/native — native-workload benchmark harness

Lean, reproducible harness for `docs/campaign-native-performance.md`.
Real application fixtures, paired trials, JSONL records, no dashboards.
Python ≥ 3.11 standard library + the docker CLI only (use `python3.14`).

## Engines

| name | what it is | isolation |
| --- | --- | --- |
| `ctrs` | `target/release/ctrs daemon` (Virtualization.framework guest) | dedicated `CTRS_DATA_DIR` + `CTRS_SOCKET` under `.work/native-perf/`; `--cold` uses a fresh data root per trial (true engine-cold) |
| `orbstack` | the user's running OrbStack via `~/.orbstack/run/docker.sock` | **shared daemon** — every resource is compose-project-scoped (`np<run><case>`) and removed after each trial; no `system prune`, no context changes |

OrbStack cannot offer a true engine-cold cell without disturbing user
state, so its `cold` state is unsupported; only `warm` (and ctrs-only
`cold`) are scored. This asymmetry is disclosed in every report.

## Usage

```sh
python3.14 bench/native/runner.py preflight          # fail-closed G0 checks
python3.14 bench/native/runner.py prepare            # pull images + build fixture API on both engines (untimed)
python3.14 bench/native/runner.py baseline --case W1 --a ctrs --b orbstack --pairs 3
python3.14 bench/native/runner.py baseline --case W2 --a ctrs --b orbstack --pairs 3 --duration 20
python3.14 bench/native/runner.py noop --engine ctrs --pairs 2   # harness noise control
python3.14 bench/native/runner.py report             # aggregate .work/native-perf/**/trials.jsonl
```

`run --case W1 --engine orbstack --state warm` executes a single trial.
Baseline order alternates AB/BA per pair (`--randomize` for seeded
shuffle); `pair_id`/`order_index` are recorded per trial.

## What a trial records

One JSON line per trial (`schema.json`): wall time to *verified*
completion, correctness checks, p50/p95/p99 where the case loads the
service, and an engine-ecosystem resource trace (`collect.py` samples
`ps` CPU/RSS of matched processes plus host loadavg every 0.2 s).

Resource accounting caveats: RSS sums double-count shared pages and do
not see compressed/swapped memory; `cpu_seconds_est` integrates sampled
`pcpu`. On macOS the guest lives inside the `ctrs` process, so its
footprint is included there; OrbStack's VM shows up under OrbStack
helper processes matched by name. Treat both as approximations, not
billing-grade numbers.

## Isolation rules (enforced)

- Same `docker` CLI binary for both engines via `DOCKER_HOST`; ctrs's
  own delegation semantics are preserved (`DOCKER_CONTEXT` stripped).
- Unique compose project per trial → unique containers, networks,
  volumes, and the published port is a free ephemeral localhost port.
- `compose down -v --remove-orphans` after every trial, plus a
  prefix-scoped `ps`/`rm` sweep. Nothing outside the `np*` project
  namespace is ever touched.
- Engines never run simultaneously; trials are sequential and paired.

## Fixtures

- `fixtures/w1/` — FastAPI + Postgres + Redis compose stack. Health
  requires both datastores; `/roundtrip` verifies a DB row and a Redis
  token; a `records` row must survive a `docker restart` of the db
  container. Seed: 500 deterministic rows via `seed.sql`.
- `fixtures/w2/load.py` — stdlib threaded load driver (keep-alive
  connections, seeded RNG, read/write mix). Correctness is verified by
  `/stats`: `items == 500 + successful writes`, zero transport errors.
- `fixtures/w8/` + per-engine `registry:2` — W8 real-image deployment.
  `prepare` builds four "relocated" images (`FROM scratch` +
  `COPY --from=<base> / /` of postgres:17-alpine, redis:7-alpine,
  python:3.13-slim, busybox) so pulls never dedup against cached base
  layers, pushes them to `127.0.0.1:<port>/npw8/*` on a per-engine
  registry container (`npw8-reg-<engine>`, named volume
  `npw8-reg-data-<engine>`, `--restart unless-stopped`), and records
  digests in `.work/native-perf/w8-portfolio.json`. Trials `rmi` the
  refs, pull each by digest (digest string must appear in pull output),
  and run the image's own smoke command. `--under-load` serves the W1
  stack + W2 load driver while pulls run (the EXP-1 responsiveness
  probe). Engine-internal layer dedup may still apply — disclosed.

## Known limitations (pilot phase)

- Cold cells pull fixture/third-party images over WAN inside the timed
  region until fixtures move onto the W8 local registries.
- OrbStack `warm` reuses its long-lived VM and build cache; ctrs `warm`
  likewise. `cold` is ctrs-only as described above; W8 has no cold cell
  because the registry and portfolio live on the warm engine.
- W3–W7, W9–W11 are declared in `cases.toml` but not yet implemented.
- The API fixture is purpose-built for the harness (deterministic,
  checksum-verifiable); it is a real FastAPI/Postgres/Redis app, not a
  microbenchmark, but it is not a third-party application. A held-out
  real app is still owed before promotion gates.
