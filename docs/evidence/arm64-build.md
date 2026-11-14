# ARM64 builds on AMD64 Linux — evidence

Date: 2026-11-14. Verdict: **P0 done; S1 done. The managed builder now runs
the frozen v0.35.0 candidate and the compatibility suite is green (both
entry points, AMD64 control, ARM64 musl/glibc). Handler-free (binfmt-
independent) proof is unavailable on this host: one global binfmt_misc
instance serves every namespace, so BuildKit treats arm64 as "supported"
and no isolated namespace can be emptied. That proof remains Needs
environment.**

This file is the parity register for the slices in `qemu-accel.md`. Rows
name the case, the proof command and the evidence. Nothing here is a claim
of release qualification.

## Machine and toolchain (2026-11-14, this host)

- AMD64 Linux: Alpine `7.2.9-2-stable`, kernel `7.2.9-2-stable #3-Alpine SMP
  PREEMPT_DYNAMIC`, `AMD Ryzen 9 9950X 16-Core Processor` x 32, load average
  3.61 at inspection (`/proc/loadavg`). User `josh` (not root; in `docker`).
- `docker version`: client/server 29.9.0, `linux/amd64`. buildx v0.38.0
  (0dbe87f36ed4). Outer endpoint: local unix socket `/var/run/docker.sock`.
  The outer engine is tooling, not ctrs qualification.
- `/proc/sys/fs/binfmt_misc/qemu-aarch64`: enabled, interpreter
  `/usr/bin/qemu-aarch64`, flags `POCF`, offset 0. Left untouched. The host
  is NOT binfmt-clean; no result on this host proves handler independence.
- Rust: `rustc 1.102.0-nightly (5b7b37aef 2026-11-08)`, channel
  `nightly-2026-11-09` (pinned, unchanged). `cargo 1.102.0-nightly
  (c07ac2c4d 2026-11-06)`. `kache 1.0.0` (rustc wrapper, present). musl
  target links through `clang` + `mold` (`/home/josh/.local/bin/mold`,
  v3.0.0); `aarch64-unknown-linux-musl` links through `rust-lld` with
  `CARGO_ENCODED_RUSTFLAGS=""` (the global `-B/usr/local/libexec/mold` path
  exists: `/usr/local/libexec/mold/ld`).
- AMD64 Linux artifacts built and ELF-validated (`cargo xtask linux --arch
  amd64`, `rust:1-alpine`, native x86-64, crates cached in the
  `ctrs-cargo-amd64` volume, finished in ~57 s): `target/linux-x86_64/
  release/ctrs` (10,437 KiB) and `ctrs-init` (4,025 KiB), both static-pie
  x86-64 (`e_machine 0x3e`).
- N-1 (AMD64 Linux host engine in a privileged container) **passed 28/28,
  2026-11-14** on two independent isolated runs (before and after the
  harness fix below): `BIN=$PWD/target/linux-x86_64/release bash
  tests/linux-host.sh`. Checks covered server, run, env, network
  (bridge DNS, IPv6, host-NAT), volumes, seccomp, memory limits, cp,
  stats, builds (`DOCKER_BUILDKIT=0 docker build --add-host hgw:host-gateway`)
  and the privileged/ptmx cases. Failure path verified: SIGTERM mid-run
  preserves `daemon.log`/`inspect.json` under `.work/tmp/qemu-accel/`,
  removes only the run's own container and volumes, exits 143. Refusal
  paths verified: a PREFIX naming an existing container exits 2 before any
  mutation (nothing created, nothing read from the foreign container); a
  non-AMD64 or missing BIN exits 2 before any mutation.

## Baseline (unchanged revision `753a18db7de0ee49bfd8552297ab547977158b17`)

Single-run timings (elapsed, command checks — not benchmark claims):
`docker version` 0.13 s; `docker ps` 0.05 s; image inspect 0.04 s;
`buildctl debug workers` 0.17 s; emulator `--version` 0.03 s; ELF probe
0.03 s; `bash -n tests/linux-host.sh tests/e2e.sh bench/suite.sh` < 0.01 s.

Narrow test loops, run on 2026-11-14 with `TMPDIR=$PWD/.work/tmp/qemu-accel`
(repo-local scratch), kache and the pinned nightly; timings are whole-command
wall:

| command | result | wall |
| --- | --- | --- |
| `cargo test -p ctrs-image --lib registry::tests` | 15 passed, 0 failed (9.07 s test time) | 9.17 s |
| `cargo test -p ctrs daemon::builder::tests` | 7 passed, 0 failed (0.00 s test time) | 0.06 s |

Note: `ctrs` is a binary package, so the campaign's earlier shorthand
`--lib daemon::builder::tests` selects nothing; the working form is
`cargo test -p ctrs daemon::builder::tests` (bin target). No baseline test
failures are known. No `target/` existed before this session; host Rust and
ctrs runtime were built fresh during it.

Known defects (unfixed; assigned to slices):

- `ensure_image()` returns a tagged local image before checking `PINNED`
  (stale-tag defect; S2). Existing containers bypass image provisioning.
- `linux_build()` uses the output architecture for `docker run --platform`,
  invokes Cargo without a target, and defaults to ARM64 even on AMD64 (the
  cross-build defect; S4).
- Metadata: `Platform::parse()` ignores remaining components; pull's
  `ImageConfig` lacks OS/architecture; malformed explicit pull/create can
  fall back silently; inspect takes the last platform component (S3).
- `Store::put_image()` replaces by name, independent of architecture (S3).
- `GET /ctrs/builder` reports the tag, not the desired/actual digests or
  upgrade state (S2).

## Pin decision (P0)

Chosen candidate: **`moby/buildkit:v0.35.0`** (released 2026-11-11,
`[Latest]`, stable). Source: `github.com/moby/buildkit` tag `v0.35.0`
commit `f55949dea4f03bb9d85b73e9afc9a609291289db`,
`Dockerfile` target `release`, built by GitHub Actions run `43069750854`
(started 2026-11-11T17:37Z) from the `v0.35.0` tag; base images
`alpine@3.24` (`sha256:f59abe…`) and `golang:1.27-alpine3.24`
(`sha256:eb61c3…`); frontend `docker/dockerfile-upstream@master` at build
time `sha256:dfd24d…`; binfmt helper `tonistiigi/binfmt@buildkit-v10.2.3-66`
(`sha256:6014c1…`). SLSA provenance:
`buildkit-v0.35.0.linux-amd64.provenance.json` (invocationId
`kjbz7aallovd76inj0eycrks9`).

Image identity (recorded 2026-11-14 from the registry, no tag trust):

| item | digest |
| --- | --- |
| index (`docker buildx imagetools inspect --raw moby/buildkit:v0.35.0`) | `sha256:aa632b921ef07411d2cb77292cd34213d4f7b384001d6fceef1e1f25bf9752bb` |
| linux/amd64 manifest | `sha256:a521fc1fd903a46c611c733dd692548512232fba2e0386d6055846a903d05a71` |
| linux/arm64 manifest | `sha256:7dc61a9fab7c7f5a50b1cdbbefa4180829e68c6c0172206eb54ad934de097ddf` |

Bundled emulator (from the amd64 image, 2026-11-14):
`buildkit-qemu-aarch64` **QEMU 10.2.3** (`v10.2.3`), sha256
`239ff153cde81b6a6ab2c48eef9cff234751caa8e9d841363eace8db51e000e8`,
x86-64 static-pie ELF (BuildID `0fa55245…`). `buildkitd`/`buildctl`
x86-64 static ELFs (`buildkitd` sha256 `e0975842…`, `buildctl`
`d91bb05b…`), version string `github.com/moby/buildkit v0.35.0
f55949dea4f03bb9d85b73e9afc9a609291289db`. The arm64 image's emulators are
ARM64 builds of the same QEMU 10.2.3 (binfmt helper pinned to
`buildkit-v10.2.3-66` on both); per-platform checksums were not extracted.

Fallback candidate (only on a demonstrated v0.35.0 release defect):
**`moby/buildkit:v0.34.2`** (2026-11-03; fixes GHSA-2fqp-xg6f-v7gj,
GHSA-w26x-xg27-7qjc) — the newest stable patch of the preceding supported
line; no `v0.35.x` patch exists yet. The observed unrelated host builder
`buildx_buildkit_musl-publish0` (BuildKit v0.34.2, QEMU 10.2.3, running; not
ctrs-owned, not a pin source) was probed read-only and left alone.

`moby/buildkit:buildx-stable-1` (the historical tag) points at
`sha256:c5f8862f52499773af85bc07695b2379ef08e8002352b0df2c4864c91d78dabe`
today (v0.34.2 content; the tag lags v0.35.0). A pull-by-tag of the moving
tag can never durably represent the frozen pin.

The managed image identity will be defined once in `daemon/builder.rs`
(index-to-index, manifest-to-manifest, config-to-image-ID), per S2. A tag or
version string alone never proves identity. Provisioning no longer depends
on the tag (see S1 below).

## S1 — foreign builds through both entry points (2026-11-14, landed)

`bash tests/arm64-build.sh --case compatibility` is **green** (39 s after
provisioning, 24 checks): AMD64 native control and ARM64 musl/glibc
shell/child/script via **buildx** (`--builder ctrs-build`, default-load)
and via ctrs's **classic POST /build** (`DOCKER_BUILDKIT=0 docker build`).
All six builds executed the fixture's guest script; computed
`sha256("ctrs-arm64-qualification\n")` matched the fixture contract in
every build; child exit status propagated (a nonzero child fails the
build); the loaded image's `/bin/busybox` (musl) and `/bin/dash` (glibc)
ELFs report `e_machine 0xb7` (ARM64) for the ARM64 images and `0x3e` for
AMD64; loaded image metadata reports `linux/arm64` / `linux/amd64`.
Live-process evidence during a deliberately slow marker RUN captured
`/usr/bin/qemu-aarch64 /bin/sh … arm64-qualification-slow-marker` in the
host process table. Host binfmt registrations were fingerprinted
before/after every run and were unchanged. The managed builder is
`v0.35.0 f55949de` (asserted via `buildkitd --version` inside it).

Findings that S2/S3 must deal with (not fixed in S1):

- **Provisioning no longer reads the tag.** `ensure_image()` used to
  return a tagged local image before considering `PINNED`, and the store
  replaces a tag's record by name — while buildx re-resolves the moving
  `buildx-stable-1` tag on every builder init. On this host that silently
  displaced the pin (first S1 runs qualified v0.34.2, not v0.35.0). The
  managed builder now provisions from the pin's digest reference; the tag
  record is kept for visibility only. `create_body` uses the digest
  reference as well, so the container always carries pin content.
- **First create per builder gets a transient 400, then buildx's retry
  succeeds** (both the intercepted and the plain path, reproducible). The
  tag pull completes and 1 ms later the first `POST /containers/create`
  is rejected; the immediate retry is accepted. Root cause not yet
  established; the request-failure WARN line logs neither query nor body,
  which is a diagnostics gap (see S2). It does not corrupt anything, but
  it makes every fresh builder bring-up log a spurious 400.
- **`docker build` without a builder flag silently selects a default
  docker-container builder** pulling `moby/buildkit:buildx-stable-1` (the
  moving tag), bypassing `ctrs-build`. Plain builds must pin
  `--builder ctrs-build`; classic must force `DOCKER_BUILDKIT=0`.
- **BuildKit's `SupportedPlatforms` probes binfmt support** (it chroots a
  small static foreign binary). On hosts with a working qemu-aarch64
  registration — like this one — BuildKit considers `linux/arm64`
  "supported" and serves RUN steps directly through the host handler, no
  argv-wrapping, **bundled emulator unused**. The `emulator-mount`
  marker (`yes`/no) distinguishes the two backends in every build log; the
  runner asserts `no` for amd64 and records which backend served arm64.
- **binfmt_misc is one global instance on this host.** A fresh private
  mount namespace mounting a new binfmt_misc still shows the host's
  registrations (`qemu-aarch64`); the shared handler services every
  namespace. Handler-free qualification is unavailable here and is
  reported as such by `--require-no-binfmt` (which fails closed).
- `docker cp` of a file behind merged-`/usr` symlinks (`/bin/dash` →
  `/usr/bin/dash`) logs one 400 GET-archive before succeeding. Benign;
  noted for S2/S3 diagnostics.
- `buildx-stable-1` today is v0.34.2 content; v0.35.0 is newer and the
  tag lags upstream `[Latest]`. Record when re-checking the pin.

## Harness: `tests/linux-host.sh` (P0 change)

Rewritten 2026-11-14: explicit `BIN` (default
`target/linux-x86_64/release`) and `PREFIX` (default unique per run,
`ctrs-lh-<pid>-<rand>`); both executables validated as 64-bit x86-64 ELFs
(`e_machine 0x3e`) before anything is created; the Docker endpoint must be
a local unix socket serving `linux/amd64` (else exit 2 before any mutation);
isolated `DOCKER_CONFIG` and unset `DOCKER_CONTEXT`; per-run unique
container, two volumes and three probe-verified loopback ports; pre-existing
prefix resources are refused, never removed; failure logs (`daemon.log`,
`inspect.json`) are preserved under `.work/tmp/qemu-accel/` on failure,
success or INT/TERM, with only the run's own recorded resources removed. The
prior broad `docker rm -f ctrs-linux-host` against a shared engine is gone.
Two runs: 28/28 passed (see above). Harness defect found and fixed during
P0: privilege-refusal paths previously allowed the EXIT trap to act on a
by-name container the run had not created; refusal now clears names and
removes only the run's own scratch before the trap is installed, and every
pre-ownership `die` is side-effect free.

## Needs environment (statuses at P0)

| Proof | Prerequisite and command | status |
| --- | --- | --- |
| AMD64 Linux ctrs runtime | Root-capable isolated namespaces/cgroup environment; `BIN="$PWD/target/linux-x86_64/release" bash tests/linux-host.sh` | **passed 2026-11-14, twice, 28/28** (isolated prefix/ports/config; SIGTERM log preservation verified) |
| No foreign host handlers | Fresh dedicated AMD64 host or proven independent binfmt namespace; `bash tests/arm64-build.sh --case compatibility --require-no-binfmt`; runner must fail closed if any foreign handler can service the test | **Unavailable on this host (2026-11-14): one global binfmt_misc instance serves every namespace; a fresh private-mount instance still shows `qemu-aarch64` POCF. The ordinary compatibility case passed with a host handler visible (and says so per backend). `--require-no-binfmt` fails closed, exit 1, creating nothing. The bundled-emulator path was never exercised here — it needs a dedicated host or VM without a foreign handler** |
| macOS regression | Apple Silicon macOS; `cargo test --workspace`, `cargo xtask all`, `conformance/smoke.sh` | **not available on this host** |
| Performance | Idle AMD64 machine passing both perf-gate checks; `bash bench/arm64-build.sh --samples 5 --all-states` | **unavailable here** (S6; host is loaded actively-used workstation; also macOS CI-only gates not applicable) |
| Hosted CI result | Separately authorized push/run | **not authorized by this campaign** |
| Actual publication | Separately authorized release dispatch | **not authorized by this campaign** |

## Parity register (in progress)

| deliverable | case / command | status |
| --- | --- | --- |
| native AMD64; ARM64 musl/glibc via both entry points | `--case compatibility` (S1) | **passing 2026-11-14 (24 checks; 6 builds + process evidence; host handler visible, unproven independent)** |
| managed identity, reconciliation, ownership | `--case identity` (S2) | not implemented |
| pull/build/export/load/inspect metadata | `--case platform` (S3) | not implemented |
| native compilers, static AArch64 output | `--case cross` (S4) | not implemented |
| cancel/failure/cleanup, emulator diagnostics | `--case lifecycle` (S5) | not implemented |
| equivalent-work benchmark | `bench/arm64-build.sh` (S6) | not implemented |
| static binaries, checksums, local manifest | S7 commands | not implemented |
| environment prerequisites | `--case environment` | **passing 2026-11-14 (22 ok, 0 missing, 0.2–1 s)** |
