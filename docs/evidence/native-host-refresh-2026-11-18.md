# 2026-11-18: New-host reconstruction and refreshed-pin gate (M1 Max)

The development host moved macOS machines on 2026-11-17 (fresh clone; all
`.work/` state and VM assets on the old host were deleted). This record covers
the 2026-11-18 reconstruction on the new host and the decision to version the
common portfolio as a new fixture instead of re-pointing v2 pins. All prior
benchmark ratios are historical and specific to the old host; no measurement
from before 2026-11-18 transfers.

## New host

- MacBook Pro (Apple M1 Max), 10 logical CPUs, 64 GiB (68,719,476,736 bytes),
  macOS 27.2.1 (26B131), Darwin 27.2.0. OrbStack 2.2.5 (bf842321…, unchanged),
  server API 29.8.2, docker 29.8.2, buildx, Compose v5.5.0. Python 3.15.1
  (docs invoke `python3.14`; the code requires ≥ 3.11 and the suite passes on
  3.15). Old host: 18 CPUs, 48 GiB, macOS 27.2 (26B123), OrbStack 2.2.5.
- An unrelated user PGO build (`rust-cpython` perf lane, `--jobs 8`) ran
  during the early hours and exited on its own before any measurement was
  taken (log: `/tmp/pgo_build1.log`, final line `OK perf CPython 3.16.0a1+dev
  … 343s`). No campaign measurement in this record ran while it was active.

## Reconstruction (verified 2026-11-18)

- Guest initramfs rebuilt from pinned source: SHA256
  `6ae4d3abfb3be1f4dcc1edf200261a29e22ad96c922c2d677d5874df21abc8b2` — exact
  match with the accepted pin.
- Guest kernel rebuilt from pinned source/config/patches (linux 6.18.58,
  allnoconfig, 2026-11-18): 18,800,648 bytes (same size as the accepted
  image), SHA256 `ea4853411fa057bc9a1ea164dbf2198d6a4f0e2590277eff2d4d86426cb4d589`.
  Hash differs from the accepted `35087713…` because kernel builds embed a
  build timestamp; identical size and pinned inputs. Not a qualification
  substitution — the accepted hash was unrecoverable by construction.
- `data.img` template recreated (sparse 1 TiB ext4, `cargo xtask disk`);
  smoke unpacked it successfully.
- Signed host binary rebuilt from main at `08cdce8` (includes c7b4b90 W8
  transport fix): `.work/tmp/readiness-main-target/release/ctrs`, SHA256
  `be929fe2a81b960d0b4e2d3a02da864d91349eb9d1438cd74cd24be13795e9f2`,
  6,617,104 bytes, ad-hoc signed with the virtualization entitlement,
  `codesign --verify --strict` clean. Differs from the old host's `db20b210…`
  as expected (c7b4b90 landed after that artifact was accepted).
- Offline harness: full Python discovery 318 tests, 0 skips (with
  `TMPDIR=$PWD/.work/tmp`; the durable-job supervisor requires it).
  `runner.py check w2` (117), `check w8` (76), `check resources` (110) all
  pass. Component results match the old host's counts.
- `conformance/smoke.sh`: 21 pass, 0 fail (host build+sign, per-instance
  lifecycle, VM boot, API 1.47, image pull cold/hot, exec/logs/rm, published
  port, SIGTERM shutdown, host hygiene). First run hit the missing data
  template; fixed by `cargo xtask disk`, second run green.

## Common portfolio refreshed as `w8-v5` (never pool with v2)

The v2 artifacts were not recoverable (locally built API/Marked images;
moving `python:3.13-slim`). Per fixture rules the pins were versioned, not
re-pointed:

- `np-v5/postgres` and `np-v5/redis` are **bit-identical to the v2 pins**
  (pulled by the pinned manifest digests; DiffIDs and config digests match
  the v2 contract exactly).
- `np-v5/api` rebuilt from `bench/native/fixtures/w1/api` with the
  digest-pinned base `python@sha256:e48f59cd…`. Base OS layers bit-identical;
  pip/app layers differ. `/app/app.py` and `/app/requirements.txt` verify
  against the unchanged pins (`d160d030…`, `b9775ff8…`).
- `np-v5/marked` rebuilt from pinned marked v15.0.12 + `fixtures/w5-v2` with
  digest-pinned `node@sha256:557e52a0…` and `npm ci` from the pinned
  lockfile. Node base layers bit-identical; npm layers differ. Tools verify:
  node v22.15.0, npm 10.9.2, esbuild 0.25.3.
- Fixture input hashes (`seed.sql`, `load.py`, API files) unchanged.
  `marked_artifact_sha256` `0823c396…` carried over and **verified identical
  on both engines** in the functional gate below.
- Layout: `.work/native-perf/inputs/w8-portfolio-v5/layout`, `portfolio.tar`
  SHA256 `a875e1ed3c7e6b3d68432d1cc0b97c0f90682ad5f5c4a6d4cf8aa57cc6279197`.
  `prepare_pinned_portfolio` validated all four selections. The validator
  now accepts the two in-tree common-portfolio versions
  (`w8-v2-common-portfolio`, `w8-v5-common-portfolio`); all code references
  moved to v5 (docs/evidence history untouched).
- 2026-11-18 commit `19c3fc8` ("bench: re-pin common portfolio as w8-v5 for
  the new host").

Functional gate (`registry_pilot.py`, both engines, results in
`.work/native-perf/results/w8-common-20261118T035359-037f/`):

- ctrs: healthy, 1,000 requests (688 reads / 312 writes), runtime versions
  exact (Python 3.13.18, PostgreSQL 17.12, Redis 7.4.12), API file hashes
  match, Marked artifact `0823c396…` matches pin, output HTML exact.
- orbstack: same, correctness true (images already resident from the digest
  pulls/build; pulls were HEAD-only).

## Refreshed baseline (this host)

First current-host baseline: W2 fixed work, matched resources.

```sh
python3 bench/native/runner.py baseline --case W2 --a ctrs --b orbstack \
  --pairs 10 --operations 50000 --concurrency 8 --write-ratio 0.3 --seed 7
```

Run ID `base-20261118T040927-4162` (results `.work/native-perf/results/base-20261118T040927-4162/trials.jsonl`).
Source `19c3fc8`. Warm state; published-port host client; AB/BA alternation;
seed per pair. Resources: OrbStack VM 9 of 10 CPUs, MemTotal 63,157,620,736 B;
ctrs VM 9 vCPUs with a 61,181 MiB ceiling (the runner's OrbStack parity defaults:
OrbStack MemTotal plus the ~950 MiB guest reserve). The pinned stack was
installed and verified in both stores first (ctrs warm root
`.work/native-perf/engines/ctrs-warm`, pull-through loopback registry; OrbStack
tags resident from the build/pull steps).

All 20 trials correct, 0 errors, paired ratios (ctrs/orbstack; bootstrap 95%
CI, 2000 iters):

| Metric | Median | 95% CI | Pilot assessment |
| --- | ---: | --- | --- |
| rps | 0.7439 | [0.7342, 0.7547] | strict win (≈1.34× throughput) |
| p50_ms | 0.7474 | [0.7426, 0.7541] | strict win |
| p95_ms | 0.6640 | [0.6496, 0.6728] | strict win |
| p99_ms | 0.6114 | [0.6010, 0.6204] | strict win |
| cpu_seconds_per_success | 1.0851 | [1.0519, 1.1233] | **loss** (≈8.5% more CPU/success) |
| peak_total_rss_kb | 0.2185 | [0.2132, 0.2341] | strict win |
| peak_phys_footprint_bytes | 0.3592 | [0.3422, 0.3777] | strict win |

The CPU-per-success loss matches the old host's system-CPU direction at the
API boundary. This is a refreshed **pilot** comparison, not qualification
evidence:

- Co-resident, unattributed user load was disclosed during the window:
  this session's own stray greps saturated both cores for ~16 minutes before
  the batch (killed before it started), the user's python-build analysis
  (`inject.py`, then `gate_controls.py`) ran at 100% CPU before and during
  the batch, and OrbStack Helper (`vmgr -handoff`) has pinned 100% CPU for
  6+ hours (unverified attribution, left running). AB/BA interleaving limits
  but does not eliminate the bias.
- Missing qualification metadata: `provenance.ctrs_binary_sha256`,
  `provenance.guest_kernel_sha256`, `provenance.guest_initramfs_sha256`,
  `provenance.guest_data_sha256` (the runner does not record them). Source
  hash is recorded; signed-binary and guest-asset hashes are in this doc.
- A quiet-window confirmation batch is required before these numbers feed the
  promotion gates, together with the provenance fix or manual hash recording.

## Open items introduced on the new host

- The accepted guest kernel hash cannot be re-verified; the rebuilt kernel is
  functional evidence only (smoke boot, pinned source/config).
- Installed-default ctrs lane (2 vCPUs) vs OrbStack (9 vCPUs on 10) is a
  separate cell and has not been measured; qualification baselines must not
  pool it with the resource-matched lane (`CTRS_CPUS=9`, matching OrbStack's
  9-of-10).
- Every previously measured paired ratio is invalid on this host; only
  w8-v5-pinned, 2026-11-18 results are current.
