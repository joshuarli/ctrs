# bench/native — native-workload benchmark harness

Pilot harness for `docs/campaign-native-performance.md`.
Paired trials, explicit correctness checks and JSONL records, no dashboards.
Python ≥ 3.11 standard library + the docker CLI only (use `python3.14`).

**Qualification is incomplete.** Read
`docs/native-performance-progress.md` for the next task. Mutable image
tags, several synthetic proxy fixtures, environment isolation and physical
resource accounting still need qualification. Historical “frozen” wins
are superseded by the correction in `docs/evidence/native-performance.md`.
Healthy soak/watch counters are not hillclimb progress.

## Offline checks (no Docker or macOS required)

```sh
python3.14 bench/native/runner.py validate-manifest
python3.14 bench/native/runner.py check w2
python3.14 bench/native/runner.py check w8
python3.14 bench/native/runner.py check resources
python3.14 -m unittest discover -s bench/native -p test_checks.py -v
python3.14 -m unittest discover -s bench/native -p 'test_*.py' -v
```

Manifest validation checks syntax/identity and records hashes. It does
not assert that assets are digest-locked or that every fixture is ready.
All runtime commands validate the manifest before engine access.

`check` requires exactly one component (`w2`, `w8`, or `resources`); a
missing/unknown component, including `full`, is an error and never falls back
to broad discovery. It runs the listed native unittest modules directly,
including `test_safety` as a shared harness boundary, with a 60-second whole
command timeout (adjustable only from 1 to 300 seconds). Import/discovery errors,
zero tests, any skip, timeout, or failing test return nonzero. When editing a
test, run that test directly as well; the `test_checks.py` command above is the
direct command for this gate's own contract tests.

### Verification ceilings and cost

| Tier | Allowed evidence | Cost ceiling / authority |
| --- | --- | --- |
| Edit | Exact changed module and `test_checks.py` with native unittest | One local Python process; no Docker or engine. |
| Change | One explicit `runner.py check {w2,w8,resources}` plus changed tests | One selected module set, 60 seconds by default (hard maximum 300); no build or engine setup. |
| Scenario | Named native benchmark scenario | Exact scenario, engines, inputs, and resource budget authorized separately before execution. |
| Full | Full Python discovery, workspace Rust tests/builds, broad conformance/qualification, or W11 | Manual-only, one exact workload per explicit authorization; no automatic fallback or prerequisite. |

Observed before this gate: the full Python discovery run took 13.477 seconds
for 201 tests; benchmark infrastructure accumulated 10 commits over 72 minutes.
The first W2 check ran 32 tests in 1.630 seconds on this host. W8/resources
timings and timeout adequacy are unknown; no build is part of `check`, and no
benchmark cost is claimed from these figures.

Full/manual commands remain available and unchanged: full Python discovery is
the last command in the offline block; Rust unit suite is `cargo test
--workspace`; release/guest build is `CARGO_ENCODED_RUSTFLAGS="" cargo xtask
all`; broad API conformance is `conformance/run.sh`. The ARM64 qualification
matrix remains `tests/arm64-build.sh` with one named `--case` from its documented
matrix. The 12-hour W11 qualification is a separate named per-engine workload;
authorize that exact engine, frozen binary/input receipt, fixed deadline, and
command through the finite-job procedure in
[`diagnostics/durable-job.md`](diagnostics/durable-job.md). None is reachable
from `check`; do not substitute a short W11 pilot for qualification.

## Engines

| name | what it is | isolation |
| --- | --- | --- |
| `ctrs` | `target/release/ctrs daemon` (Virtualization.framework guest) | dedicated `CTRS_DATA_DIR` + `CTRS_SOCKET` under `.work/native-perf/`; `--cold` uses a fresh data root per trial (true engine-cold) |
| `orbstack` | the user's running OrbStack via `~/.orbstack/run/docker.sock` | **shared daemon** — every resource is compose-project-scoped (`np<run><case>`) and removed after each trial; no `system prune`, no context changes |

OrbStack cannot offer a true engine-cold cell without disturbing user
state. Paired cold comparisons are refused; ctrs-only `run --cold` is
diagnostic. W7 `--no-cache` means uncached build work with retained base
images/stores. W8 removes only fixture refs and retains engine content.
Neither is an empty-store comparison.

## Usage

```sh
python3.14 bench/native/runner.py preflight          # fail-closed G0 checks
python3.14 bench/native/runner.py prepare            # pull images + build fixture API on both engines (untimed)
python3.14 bench/native/runner.py baseline --case W1 --a ctrs --b orbstack --pairs 3
python3.14 bench/native/runner.py baseline --case W2 --a ctrs --b orbstack --pairs 3 --duration 20
python3.14 bench/native/runner.py noop --engine ctrs --pairs 3   # same-engine A/B slot noise control
python3.14 bench/native/runner.py report --noise --match '<run-id>'  # noise report, never engine scores
python3.14 bench/native/runner.py holdout                       # independent real-app gate (once per engine)
python3.14 bench/native/runner.py report --match '<exact-run-id>'
```

Run these on the Mac after NP-01's isolation/provenance checks. Three
pairs are a pilot. The current harness uses resource-matched ctrs VM
settings; a separately implemented default-settings lane remains required
by the campaign. Preflight is an initial check, not full G0 qualification.

W2 baselines require the [common pinned ARM64 stack](fixtures/w8-v2/README.md)
preinstalled on both endpoints. Before each trial the runner verifies the
image IDs, layer identities, seed and API files and primes the VM. The
paired report requires matching input receipts from both endpoints.

`run --case W1 --engine orbstack --state warm` executes a single trial.
Baseline order alternates AB/BA per pair (`--randomize` for seeded
shuffle); `pair_id`/`order_index` are recorded per trial. A/B uses the
same workload seed and per-pair identity. A failed baseline or holdout
returns nonzero. Avoid hiding that exit status with a pipe through `tail`.

The reporter separates run/configuration cohorts, rejects duplicate,
incomplete, failed or mismatched pairs, and preserves missing metrics.
It bootstraps the same paired median it displays, with at least ten
valid pairs before any statistical classification. Every result remains
**descriptive/pilot**, even a statistical `strict-win`, until campaign
qualification. Holdouts and W11 counters do not become speed claims.
It can also run independently:

```sh
python3.14 bench/native/reporting.py --match '<exact-run-id>'
```

## What a trial records

One JSON line per trial (`schema.json`): wall time to *verified*
completion, correctness checks, p50/p95/p99 where the case loads the
service, and an engine-ecosystem resource trace (`collect.py` samples
`ps` CPU/RSS of matched processes plus host loadavg every 0.2 s).
New records include executed workload parameters, paired workload identity,
manifest/fixture/runner/binary hashes and explicit pilot status. This
does not yet verify an adopted daemon's executable or guest asset identity.

Resource accounting caveats: RSS sums double-count shared pages and do
not see compressed/swapped memory; `cpu_seconds_est` integrates sampled
`pcpu`/cumulative cputime deltas. `peak_phys_footprint_bytes` sums the
per-process `phys_footprint:` field reported by `/usr/bin/footprint`
(the Activity Monitor memory metric) over name-matched processes; the
category-table `Footprint:` total is a different, smaller number and is
only a fallback. On macOS the guest lives inside the `ctrs` process and
its VZ XPC helper, so guest memory is included there; OrbStack's VM
shows up under OrbStack helper processes matched by name. phys_footprint
is sampled at ~1 s, so peaks between samples are missed — treat totals
as approximations, not billing-grade numbers. Records written before the
phys_footprint parser fix (2026-11-16) hold the smaller category total
and must not be compared against later runs.

## Isolation behavior and remaining qualification

- Same `docker` CLI binary for both engines via `DOCKER_HOST`; ctrs's
  own delegation semantics are preserved (`DOCKER_CONTEXT` stripped).
- Unique compose project per trial → unique containers, networks,
  volumes, and the published port is a free ephemeral localhost port.
- `compose down -v --remove-orphans` after every trial, plus a
  prefix-scoped `ps`/`rm` sweep. Nothing outside the `np*` project
  namespace is ever touched.
- Workload trials are sequential and paired; warm daemons may remain
  resident. An additional watch/soak/compile process is **not** excluded
  automatically. Use one measurement owner and quiesce only identified
  campaign-owned competing work. Never stop user services to get a score.
- No global image/build/system prune. Buildx configuration is scoped to
  the benchmark engine endpoint, and controlled builders verify their
  endpoint/driver/image. Only remove specifically owned fixture resources.

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
  digests in `.work/native-perf/w8-portfolio.json`. Preparing one engine
  atomically updates its section while preserving the other engine’s state;
  malformed existing metadata fails explicitly. Trials `rmi` the
  refs, pull each by digest (digest string must appear in pull output),
  and run the image's own smoke command. `--under-load` serves the W1
  stack + W2 load driver while pulls run (the EXP-1 responsiveness
  probe). Engine content is retained on both sides; dedup may avoid
  fetch/install entirely. Per-engine construction does not guarantee
  identical assets. NP-02 replaces this with one pinned multi-layer
  portfolio served by an independent registry before qualification.

## Known limitations (pilot phase)

- Cold cells pull fixture/third-party images over WAN inside the timed
  region until fixtures move onto the W8 local registries.
- OrbStack `warm` reuses its long-lived VM and build cache; ctrs `warm`
  likewise. `cold` is ctrs-only as described above; W8 has no cold cell
  because the registry and portfolio live on the warm engine.
- The API fixture is purpose-built for the harness (deterministic,
  checksum-verifiable); it is a real FastAPI/Postgres/Redis app, not a
  microbenchmark, but it is not a third-party application.
- W4's Redis-cli hashing, W5's generated modules, W7's compileall/random
  bytes and W9's historical timed hash loop are diagnostic proxies. Keep
  their records separate from the representative workloads.
- Successful requests determine load throughput; attempted requests and
  errors are separate. W11 requires zero errors, nonempty valid windows
  and exact accepted writes, but duration alone does not establish leak,
  durability or whole-engine recovery qualification.

## Holdout

`runner.py holdout --engines ctrs,orbstack` runs the independent
holdout once per engine (campaign gate f): Gitea 1.24.7 + Postgres —
a real third-party app never used for tuning. It seeds repos/issues
over the REST API, times a read workload through the published port,
and finishes with real `git clone` smart-HTTP operations. Results land
in `.work/native-perf/holdout-*/` like any trial but are excluded from
the scored matrix; parameters are frozen in `cases.toml` — do not tune
against its failures.

W9 v2 runs 16 fixed Marked build/test jobs at each declared concurrency, using the
pinned common W8 image. Supply --image-ref for run/baseline/noop; see
[the fixture contract](fixtures/w9-v2/README.md). Old timed-loop W9 records are not
pooled with the new metrics. W11's remaining timed churn is still a diagnostic.

Canonical W8 paired pilots use `w8-baseline --layout <original-v2-layout>
--ctrs-binary <signed-ctrs>`. See [the W8 fixture guide](fixtures/w8-v3/README.md)
for prerequisites, measurement boundaries and diagnostic mode. The generic W8
proxy commands are retired from scoring.
