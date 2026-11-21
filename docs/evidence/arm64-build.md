# ARM64 builds on AMD64 Linux — evidence

Date: 2026-11-14–2026-11-15. Verdict: **P0 done; S1 done; S2 done; S3 done; S4 done; S5
done; S6 done; S7 done (Linux release prep; Ultrareview run; handler-free
and hosted-CI proofs remain Needs environment). Native cross-compilation builds both reference workloads
faster than emulation in every measured cell on this host (rust cold
5.30 s vs 77.79 s; c-cpp cold 35.26 s vs 104.92 s; medians, 5 valid
samples per path/state, rotated), the A↔B pin upgrade is
performance-neutral, and no memory penalty applies to crossing. The
managed builder now reconciles a stopped stale builder to the frozen
v0.35.0 pin (fresh provisioning, cache preserved), refuses actionably on
stale running/paused and foreign same-name containers, reports
desired/actual/tag/upgrade diagnostics (capability now observed from the
running builder), and platform requests are normalized to one canonical
path with config verification before any record is published. The
identity suite (40 checks), the platform suite (14 checks), the
lifecycle suite (35 checks) and the cross suite (25 checks) are green.
Handler-free (binfmt-independent) proof is unavailable on this host: one
global binfmt_misc instance serves every namespace, so BuildKit treats
arm64 as "supported" and no isolated namespace can be emptied. That
proof remains Needs environment.**

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

## S2 — managed identity, safe reconciliation, diagnostics (2026-11-14, landed)

`bash tests/arm64-build.sh --case identity` is **green** (40 checks,
~45–60 s after provisioning, warm cache): fresh install; first-build
provisioning; matching stop/restart reuse (container id unchanged, cache
reused); stale tag record detected and never consulted; stale *stopped*
builder replaced by the next build; cache volume sentinel preserved across
replacement and across remove-and-recreate (interrupted replacement); old
(stale) container ids unresolvable after replacement; a stale tag, a stale
stopped container, a foreign same-name container (refused actionably by
build, start and exec with `dev.ctrs.builder` named), failed pull on upgrade
(stale builder preserved, pull error surfaced to the caller), DNS-blackhole
restore verified, two simultaneous callers producing exactly one builder,
buildx against the reconciled builder, host/harness docker contexts
unchanged, and a final `GET /ctrs/builder` reporting `matches_desired:true`,
`upgrade:"none"`. `--case compatibility` re-verified **24/24** on the S2
artifacts; `cargo test -p ctrs daemon` **131 passed**; `cargo check
--workspace` clean.

The upgrade drift a previous release would have produced is simulated in the
runner by forging the builder's record in the engine's state store
(`containers.json`) while the harness daemon is stopped, then restarting it:
the next build sees a stale-stopped owned builder and reconciles it. This is
the only drift state plantable through public means, and it is honest about
what it is. Not plantable end-to-end, and covered by unit tests instead:

- **Stale running/paused refused with live work.** A record whose container
  died is reconciled to `exited` at daemon boot (`was_running → Exited`,
  `exit 255`, `vm_stopped`), and `paused` is not persisted, so a stale
  running/paused builder cannot exist across the only transition that
  produces stale images (a ctrs upgrade). The refusal paths
  (`before_start`, `exec_session_gate`, build admission) exist and fire
  before any mutation; the classifier matrix for them is unit-tested
  (`assessment_matrix`, including paused and foreign), and the e2e run
  asserts the refusal text for the stopped-builder exec gate and for the
  foreign build/start/exec gates. Nothing in this tree stops, pauses or
  removes a running/paused stale builder; sessions drain.

Findings (S2 scope):

- **Provisioning re-verifies the pin under the lifecycle boundary before
  any remove/create**, purely locally (record triple + config-blob hash +
  os/arch); registry I/O never happens under `ENSURE`. `desired_image`
  re-pulls a record that fails verification instead of erroring on it
  forever (a pre-review defect: every build would have failed the same
  way). `create_locked` refuses to create without local verification.
- **A failed pull on upgrade leaves the previous state untouched.** With
  the pin record removed (`docker rmi` by digest) and DNS blackholed inside
  the harness, the build failed citing the pin's digest; the stale builder
  and the cache volume were intact; restoring DNS let the next build pull
  and reconcile. ctrs does not create the replacement before the pin
  verifies.
- **`docker restart` gates before mutating.** A paused foreign or stale
  builder is refused with no stop, unpause, or signal sent (previously the
  stop ran first; a stale running builder would have been SIGTERMed,
  replaced and reported 409). A stale stopped builder replaces with the
  pin behind a 409 "not applied — retry" boundary; a removed id is never
  reported as restarted. A nonexistent id maps to NotFound (404) by the
  error table.
- **buildx against a stale running/paused builder gets the actionable
  error at create time** (not a bare "name in use"), in addition to the
  start- and exec-gate refusals; the classic path self-heals a stale
  stopped builder (next build replaces it).
- **Diagnostics** (`GET /ctrs/builder`, read-only, never pulls/starts/
  mutates): `desired` (pin triple + source provenance), `actual` (present,
  name, short id, state, paused, owned, image_ref, image_id,
  `matches_desired`, `buildkit_version`, `emulator_version`, `created`),
  `tag` (`moby/buildkit:buildx-stable-1` record vs pin:
  `matches_pin` — the stale-tag detector; observed `false` on this host,
  provisioning unaffected), `upgrade`/`upgrade_detail`
  (`none`/`pending`/`conflict`), `capability` (`unknown` with reason;
  advertised platforms are not verification). Version strings are
  cryptographic observations of the verified image id (the frozen pin),
  else `unknown`.
- **Diagnostics hygiene**: request-failure lines now carry method, path
  and (re-encoded) query on 4xx/5xx; a rejected builder create logs the
  error and the builder name (the client body is not logged; ctrs's own
  internal create logs its fixed template body). Query values can no
  longer forge log fields. This is the fix for the S1-flagged transient
  first-create 400 diagnostics gap — the root cause is still open, but
  the next occurrence will carry the query.
- **The VM-sleep path now only pauses/stops ctrs-owned builders**
  (`dev.ctrs.builder=1`); a foreign same-name builder is treated as an
  ordinary container (never frozen, stopped or paused by ctrs's idle
  watcher). User-owned buildx builders on a ctrs engine lose idle-pause
  and will keep the VM awake — the conservative choice, recorded as an
  owner-visible trade-off.
- **Independent review** (read-only, uncommitted S2 diff): three High
  defects (provisioning dead-end after a corrupt record; restart
  mutating before the ownership gate; reconcile creating without local
  verification under the boundary), two Medium, three Low — all fixed and
  re-verified; nothing else held up.
- The failed-pull phase surfaced two harness defects (cp onto the
  bind-mounted `/etc/resolv.conf` — fixed by write-through restore with a
  post-restore check; stale-digest-rmi ordering after the forge — fixed),
  no product defects.

## S3 — accurate platform requests and image metadata (2026-11-14, landed)

`bash tests/arm64-build.sh --case platform` is **green** (14 checks,
~20–40 s warm): focused regression suites (`ctrs-image registry::tests`,
`ctrs-image archive::tests`, `daemon::builder::tests`), an arm64
single-platform image built via classic `/build`, docker-format
save/rmi/load round trip with `Architecture: arm64` after reload,
create-with-platform mismatch refused by the daemon at the API
(`No such image: … for linux/amd64`), a matching create accepted, a
two-platform OCI export whose index carries linux/amd64 and linux/arm64
manifest entries whose configs both report the right os/architecture
(nested-index layout from buildx handled), and the multi-platform OCI
tarball refused on load with `not an image archive: no manifest.json`
(no partial record published). Digest-pinned base, host binfmt handler
visible (unchanged fingerprint behavior as for S2). Compatibility
re-verified on the S3 artifacts; identity re-verified as well.

What changed:

- **One canonical platform parser at the request boundary**
  (`registry::Platform::parse`): trimmed, lowercased; aliases
  (`x86_64`, `x86-64`, `intel` → `amd64`; `aarch64` → `arm64`;
  `i386`, `i686` → `386`); `linux/arm64/v8` and `linux/aarch64/v8` are
  the baseline `linux/arm64`; bare `arm64`/`amd64` mean `linux/<arch>`;
  the closed set is `linux/{amd64, arm64, 386}`; an unknown variant, an
  extra component, a non-Linux OS, or an unsupported architecture is
  refused, never dropped. `os` must be `linux`.
- **Index entry selection** matches on normalized os/architecture;
  attestation entries (no `platform`) are skipped; `linux/arm64`
  requests match `linux/arm64/v8` entries (v8 equivalence).
- **Downloaded config is verified against the selection before any
  record is published.** os and architecture are required; a mismatch
  or an absence fails the pull (fast: the check runs inside the config
  download, ahead of layer completion) and the previous tag record is
  left intact — `put_image` is never reached.
- **Archive load**: absent `os`/`architecture` is the documented legacy
  fallback (os `linux`, the host's architecture; a load fallback, never
  confused with registry validation); aliases normalize on load;
  present-but-invalid values (non-string or empty `os`/`architecture`)
  fail the load; a foreign-OS archive loads as a foreign record, not
  relabeled as linux.
- **Create/pull request validation**: `platform=` malformed on pull →
  HTTP 400; malformed on `POST /containers/create` → 400 (mismatch on a
  well-formed request → `No such image: … for <platform>` as before);
  malformed on classic `POST /build` → 400 with the same message text as
  buildx accepts; normalization matches buildx (`arm64/v8` → `arm64`).
- `docker image inspect` reports the right `Architecture` by
  construction (records are normalized).

Honest limits: an explicit request for an architecture ctrs cannot run
(`linux/ppc64le`) is refused at the boundary, not accepted and then
silently unrunnable; archive loads of foreign architectures are a
tolerance (records to inspect, never to run), not support. The
"conflicting archive metadata" case has no second platform-bearing field
in the docker-save layout (manifest.json carries none); the load-path
checks reject missing/empty/wrong-typed metadata, and the fallback is
coded separately from registry validation.

## S4 — host-native compilers and explicit target output (2026-11-14, landed)

`bash tests/arm64-build.sh --case cross` is **green** (25 checks):
xtask `--arch` refusals (`banana`, conflicting flag, missing value) exit 2
before Docker is spawned; a bare `cargo xtask linux` on this AMD64 host
builds x86-64 artifacts (`e_machine 0x3e00`); `cargo xtask linux --arch
arm64` builds AArch64 artifacts (`e_machine 0xb700`); both
`examples/cross/*` fixtures cross-build on the build platform with the
intended target (`host=x86_64-unknown-linux-gnu target=aarch64-unknown-linux-musl`
in the rust fixture's build-script output; `build platform linux/amd64;
target linux/arm64; triple aarch64-unknown-linux-musl` in both build
logs); the final images run and inspect as `linux/arm64`; the release
artifacts (`target/linux/release/{ctrs,ctrs-init}`) are static AArch64
EXEC ELFs with no INTERP program header (readelf inside the pinned
toolchain container); cargo caches are per architecture
(`ctrs-cargo-aarch64-musl` introduced, `ctrs-cargo-amd64` kept), and the
example Dockerfiles select the target via `TARGETARCH`. No speed claim is
made — this slice proves the mechanism and its outputs; the
equivalent-work comparison is S6, on a qualifying host.

What changed:

- **One typed `Arch`, one `--arch` flag** in `xtask/src/main.rs`
  (`arm64`/`aarch64`/`amd64`/`x86_64`/`x86-64`/`intel`), validated before
  any task dispatch and before any Docker spawn; an unknown value, a
  missing value, or a conflicting repetition exits 2. macOS keeps its
  intentional ARM64 default; Linux follows the host. `guest`, `host`,
  `linux` and `all` share the parser. Unknown flags are errors, not
  silently ignored.
- **The ARM64 Linux build uses a pinned cross toolchain on the build
  platform, never under a target emulator.**
  `messense/rust-musl-cross:aarch64-musl@sha256:02e790506c5f15a533bc05b3af8719b16a8a2314480f6f0fdc0166432035d9b4`
  (rustc 1.96.1, gcc 12.4.0, aarch64 musl 1.2.x, CRT sysroot; MIT;
  transferred to the `rust-cross` org on GitHub, pushed 2026-10, digest is
  the live `aarch64-musl` index digest). Compilation, build scripts and
  proc macros run natively; only the linker output is AArch64.
  `CARGO_TARGET_AARCH64_UNKNOWN_LINUX_MUSL_LINKER` is passed at the
  container boundary, leaving `.cargo/config.toml` (guest `rust-lld`)
  untouched. The ring C objects compile through the cross gcc.
- **The container ignores the repo's `rust-toolchain.toml`**
  (`RUSTUP_TOOLCHAIN=stable`): the image ships only its stable (the
  requested nightly-2026-11-09 has no musl std there), and that stable
  carries `aarch64-unknown-linux-musl` preinstalled. The host build
  itself keeps the pinned nightly.
- **Artifact layout preserved**: ARM64 `target/linux/release/{ctrs,ctrs-init}`
  (built with `--target aarch64-unknown-linux-musl` under
  `CARGO_TARGET_DIR=target/linux`, then copied out of the triple
  subdirectory inside the container, which owns `target/linux` as root);
  AMD64 `target/linux-x86_64/release/` (native, unchanged; static-PIE
  x86-64, e_machine `0x3e00`).
- **`examples/cross/rust-musl` and `examples/cross/c-cpp-musl`**:
  build-only fixtures proving the pattern — native BUILDPLATFORM
  toolchain, `$TARGETOS`/`$TARGETARCH`/`$TARGETVARIANT` selection,
  `ARG BUILDER_IMAGE` before FROM, static output, final stage on the
  target platform. The Rust fixture includes a proc-macro crate and a
  build.rs compiling a real C object statically; the build script prints
  its host/target pair (asserted by the runner). The C++ fixture links a
  C translation unit. Both run under the foreign target stage and print
  their expected line; images inspect as `linux/arm64`.
- **AMD64 base pin unified**: `rust:1.100.0-alpine@sha256:de1e0058543a81ed7b046629167db587c67a94bdf37cce14eb27f0ec83baaffb`
  — per-arch variant digests identical to the previously pinned
  `rust:1-alpine@sha256:2ccc…` (verified against the registry), now with a
  self-describing tag. The root `Dockerfile` (release.yml's Linux builder
  image) pins the same digest instead of the mutable `rust:1.100.0-alpine`
  tag; its comment now states the actual constraint (rust-lld cannot find
  the musl CRT objects in that image).
- **`tonistiigi/xx` pilot — run, and not chosen.** Both charter-prescribed
  pilots (30-minute box each) of the xx arrangement with the Rust fixture:
  (A) manual `rust-std-1.100.0-aarch64-unknown-linux-musl.tar.xz`
  download and install — `tar -xJ` is broken in the image (fails on a
  sha256-verified tarball; `xz -dc | tar -x` works), and `install.sh`
  requires bash; (B) `rustup target add` — passes end to end (static
  AArch64 EXEC, runs under qemu, expected line). Either way the arrangement
  needs the xx helper plus a native toolchain plus a target-std download at
  build time plus `xx-apk musl-dev` — five moving components to messense's
  one preinstalled pin, with the C-compile path silently relying on the
  cc-crate/clang `--target` fallback rather than an explicit target
  compiler. Fewer external components wins the charter's tie-break;
  messense stays. Pilot Dockerfiles were session scratch, not committed.
- Re-verified on the S4 tree: `--case platform` 14/14,
  `--case identity` 40/40, `--case compatibility` 24/24,
  `tests/linux-host.sh` 28/28, `cargo test -p ctrs daemon` 131,
  `cargo test -p ctrs-image` 46, `cargo test -p xtask` 5/5.

Honest limits: the image-run checks execute the target images under the
host binfmt handler (same caveat as compatibility; compilation itself is
never emulated). The cross toolchain compiles with stable 1.96.1, not the
repo's nightly — a future workspace dependency on nightly-2026-11-era std
would break the cross path first. Only the messense arrangement was
qualified for the full ctrs/ctrs-init workspace (ring included); xx was
exercised on the fixture. macOS keeps its intentional ARM64 default; the
root `Dockerfile` and release.yml were pinned but not re-exercised here
(release builds belong to S7 and the macOS/CI environments).

## S5 — lifecycle hardening and CI parity (2026-11-14, landed)

`bash tests/arm64-build.sh --case lifecycle` is **green** (35 checks):

- **Concurrent builds, distinct architecture tags** — classic builds of
  amd64 and arm64 in parallel, both green, both image metadata correct.
- **Cancellation** via `POST /build/cancel?id=` — the RUN step's
  `sleep 20` process is observed, then cancelled; no build process
  remains within the 60 s deadline (1 s observed); the cancelled build
  publishes no image (asserted two ways: no tag, and BuildKit's
  completion marker `arm64-qualification-slow-done` absent from the
  client stream); the engine keeps answering; a subsequent build
  succeeds.
- **Worker failure** — `docker stop` of the managed builder mid-build:
  the build fails (exit 1), the builder record is kept, and
  `ensure_running` reuses the stopped matching builder; the rebuild
  succeeds.
- **Failed target execution** — `RUN exit 23` surfaces exit code 23
  through the classic build's error; no image is published; native
  amd64 builds remain functional.
- **Daemon restart** — the harness engine is fully restarted; it answers
  within 60 s; the rebuild succeeds and hits the build cache (`CACHED`).
- **Emulator diagnostics (fault injection)** — missing / non-executable
  / corrupt bundled emulator, injected only into the disposable harness
  builder, restored after each fault: `GET /ctrs/builder` reports
  `absent` / `absent` / `unusable` with the remediation text; native
  amd64 builds stay functional; restore round-trips to `ok`.

Mutation verification (restored after each, nothing committed):

- **Cancellation** (product mutation: SIGINT/pkill removed from
  `cancel()` in `daemon/builder.rs`) — the case failed on
  "build ran to completion despite the cancel (slow-done marker present)"
  and "cancelled build published …", twice, including once against the
  corrected marker fixture.
- **Worker-failure recovery** (product mutation: the `Matching` arm of
  `ensure_running` refusing to reuse the stopped matching builder) —
  the case failed immediately in the concurrent reuse path; caught
  before the worker-failure section, on the same mechanism. (No
  narrower line-level seam exists — `ensure_running`'s Matching arm is
  also the fresh-provisioning path.)
- **Emulator diagnostics** (product mutation: corrupt reported as `ok`) —
  the case failed on "diagnostics for the corrupt emulator do not report
  unusable" and "diagnostics lack the remediation text".
- Failed target execution, concurrency, restart/cache — no one-line
  product mutation isolates those assertions (BuildKit owns the cache;
  the exit-code assertion is pinned to the observed error shape); they
  were verified end to end, not mutation-verified.
- The first version of the completion-marker check false-fired on
  BuildKit's step description (the Dockerfile text contains the marker);
  the fixture now splits the marker so the description never matches.

What changed:

- **`GET /ctrs/builder` `capability` is now observed** from the running
  managed builder instead of a static `unknown`: a read-only probe
  (presence, executability, ELF magic of the bundled emulator) reports
  `ok` / `absent` (missing or non-executable, with remediation naming
  the owned builder's rebuild) / `unusable` (not an ELF binary) /
  `unknown` (builder stopped, or probe inconclusive). The probe never
  pulls, starts or mutates anything; the parser is unit-tested
  (`daemon::builder::tests`, 132 passed).
- **One AMD64→ARM64 CI job** (`arm64-compat`, `ubuntu-26.04`) in
  `.github/workflows/ci.yml` builds the AMD64 engine
  (`cargo xtask linux --arch amd64`) and invokes the same qualification
  runner (`--case environment compatibility platform cross identity
  lifecycle`). QEMU binfmt handlers are registered on the ephemeral
  runner via the digest-pinned `docker/setup-qemu-action` (v4.4.0,
  `99012661954931238ded8c8b007157a8430204e1`). This is the
  emulator-present happy path, not handler independence, and it has
  **never been executed** — no push was authorized by this campaign.
  Anonymous Docker Hub pulls can 429 the job (the pin cannot be mirrored
  without changing digests).
- Docs: `docs/development.md` (layout + verification) updated;
  `docs/architecture.md` unchanged (its builder line stays accurate).

Handler-free proof remains Needs environment (binfmt isolation probe
reports `shared` on this host — one global binfmt_misc instance serves
every namespace). `--require-no-binfmt` fails closed. The lifecycle
emulator-injection assertions cover diagnostics and native-build
functionality only, not "arm64 RUN fails without the emulator".

The first green run reported 34 checks; the completion-marker check was
added after it. Its first version false-fired on BuildKit's step
description (the Dockerfile text contains the marker); the fixture now
splits the marker (`arm64-qualification-slow-""done`) so the description
never matches. Re-verified on the final S5 tree (mutation-restored):
`--case environment` ok; `--case compatibility` 24/24; `--case identity`
40/40; `--case platform` 14/14; `--case cross` 25/25; `--case lifecycle`
35/35; `bash tests/arm64-build.sh --all` **160/160**; `tests/linux-host.sh`
**28/28**; `cargo test --workspace` as root in the CI image
(`rust:1.100.0-alpine@sha256:de1e0058543a81ed7b046629167db587c67a94bdf37cce14eb27f0ec83baaffb`,
`CI=true`, linux/amd64): **296 passed, 0 failed**. On the unprivileged
host, 6 `ctrs-init` tests fail (`linux::layers::*`, `linux::dns::*`):
chown to uid/gid 0 is not permitted for this user; pre-existing,
unrelated to this slice; CI (root) is the authority.

## S6 — measured optimization (2026-11-15, landed)

Fixtures (frozen; `bench/arm64/{rust-workload,c-cpp-workload}/`):

- **Rust workload** (CPU-heavy): a proc-macro crate (path dep, zero
  deps), a `build.rs` compiling a real C object with the target-aware
  compiler (`aarch64-unknown-linux-musl-gcc` / `cc`), `ring` (the same
  C-heavy dependency family ctrs carries), ~870 unrolled mixing rounds.
  Dependencies compile against a dummy `main` first so the real app's
  layer carries only the app rebuild.
- **C/C++ workload** (process-heavy): 120 C translation units + an
  extern-C link from `main.cpp`, static musl output, built by 120
  sequential compiler invocations plus the C++ link. Per-TU layers make
  the incremental state exactly one TU + link.

Paths: **A** old pin
`moby/buildkit:buildx-stable-1@sha256:c5f8862f52499773af85bc07695b2379ef08e8002352b0df2c4864c91d78dabe`
(v0.34.2 content — the actual old default pin), **B** qualified pin
`moby/buildkit@sha256:aa632b921ef07411d2cb77292cd34213d4f7b384001d6fceef1e1f25bf9752bb`,
**C** the same qualified builder with `BUILD_PLATFORM=linux/amd64`
(identical toolchain, flags and Dockerfile; only the builder stage's
platform differs). Per-phase isolated builders (fresh per
(workload, state, path) phase; ctrs's managed builder and every user
builder untouched; removed on exit; provisioning measured separately in
`provisioning.tsv`, never inside a sample). Five valid samples per
(path, state) in rotated order (A/B/C, B/C/A, C/A/B). Source inputs
frozen (`SHA256SUMS` verified at run start); goldens pinned per fixture
(`GOLDENS`); every sample ELF-checked (`b700`), image-checked
(`linux/arm64`) and output-checked for the golden line.

Method notes: perf-gate-ready runs before and -1 after every timed
group and before and after every sample; samples overlapping foreign
load are discarded (recorded as `busy`), and the run fails closed with
"insufficient valid samples per (workload, path, state)" rather than
report from a loaded host. Cold samples include registry downloads
(phase-fresh builders; no shared cargo cache); layer-hit amortizes
BuildKit's frontend cost identically across paths (the c-cpp fixture's
250 steps dominate its layer-hit state uniformly across A/B/C). The
client cannot observe the build's user/sys time (compilation happens in
the builder), so the recorded tree cost is wall + the phase's cgroup
`memory.peak` (builder cgroup, fresh per phase; idle baseline recorded
at creation). **No product change ships in S6**; the daemon's idle RSS
and all other existing budgets are unaffected.

Host for measurements (`bench/results/20261115T011929Z/machine.txt`):
AMD Ryzen 9 9950X (32 cores), Linux 7.2.9-2-stable, load 1.91 at start,
docker 29.9.0 (cgroupfs v2) on `/var/run/docker.sock`, buildx v0.38.0,
`qemu-aarch64` binfmt handler enabled (POCF) — the emulated paths were
served by the host handler on this host, not by a proven-independent
namespace. Provisioning (`provisioning.tsv`): all 18 per-phase builders
created in ~1 s each; A from `buildx-stable-1@c5f8862f…` (buildkitd
v0.34.2 `8c57943…`), B and C from the qualified pin (buildkitd v0.35.0
`f55949d…`). Idle peaks ~49–72 MB.

### Measured results (5 valid samples per cell; median [min–max])

| workload | path | state | median s | min | max |
| --- | --- | --- | --- | --- | --- |
| c-cpp-workload | A | cold | 96.034 | 78.612 | 120.492 |
| c-cpp-workload | A | incremental | 2.395 | 2.228 | 146.483 |
| c-cpp-workload | A | layer-hit | 0.396 | 0.375 | 117.160 |
| c-cpp-workload | B | cold | 104.924 | 84.691 | 156.285 |
| c-cpp-workload | B | incremental | 2.366 | 2.218 | 112.179 |
| c-cpp-workload | B | layer-hit | 0.402 | 0.394 | 129.863 |
| c-cpp-workload | C | cold | 35.264 | 10.381 | 57.630 |
| c-cpp-workload | C | incremental | 0.649 | 0.624 | 36.699 |
| c-cpp-workload | C | layer-hit | 0.404 | 0.396 | 60.921 |
| rust-workload | A | cold | 77.868 | 77.714 | 106.589 |
| rust-workload | A | incremental | 6.403 | 6.369 | 104.498 |
| rust-workload | A | layer-hit | 0.204 | 0.197 | 110.627 |
| rust-workload | B | cold | 77.789 | 77.552 | 101.390 |
| rust-workload | B | incremental | 6.389 | 6.355 | 111.192 |
| rust-workload | B | layer-hit | 0.208 | 0.196 | 97.230 |
| rust-workload | C | cold | 5.295 | 5.242 | 19.840 |
| rust-workload | C | incremental | 0.467 | 0.464 | 25.475 |
| rust-workload | C | layer-hit | 0.203 | 0.193 | 28.700 |

Samples: 90 recorded, 90 valid (golden output + ELF `b700` +
`linux/arm64`), 0 rejected; all gate checks passed. The layer-hit
`max` values are round 1 of each phase (fresh builder, caches empty by
design); the medians reflect cached rounds 2–5, which is the correct
interpretation of a layer-hit state. The outlier in B/c-cpp-cold (r4,
156.3 s) is one slow sample inside an otherwise-valid cell, kept and
reported (not discarded — the host was not busy enough to trip the
gate; it stays visible in the table).

### Verdict

- **Native cross-compilation (C) is faster than emulation (B) on
  equivalent successful work on this host**, in every measured cell:
  rust cold 5.30 s vs 77.79 s (≈14.7×), c-cpp cold 35.26 s vs 104.92 s
  (≈3.0×), incremental rebuilds 0.47–0.65 s vs 2.37–6.39 s. The gap
  exceeds the observed spread in both workloads (C `max` < B `min` for
  rust cold 19.8 < 77.6 and for c-cpp cold 57.6 < 84.7). This is a
  **cross vs emulation** result, not a transparent-emulator result; it
  says nothing about FEX or full-system emulation.
- **The managed pin upgrade (A→B) is performance-neutral here**: the
  old pin (v0.34.2) and the qualified pin (v0.35.0) measure within
  spread of each other in every cell (rust cold A 77.87 [77.71–106.59]
  vs B 77.79 [77.55–101.39]; c-cpp A 96.03 vs B 104.92 with overlapping
  ranges 78.6–120.5 vs 84.7–156.3). A is retained as the negative
  baseline; it neither wins nor loses on this workload.
- **Native cross-compilation is not a layer-hit regression risk**: the
  fully-cached state is indistinguishable across paths (0.19–0.40 s).
- **No memory penalty for crossing**: phase peaks span 3.36–4.85 GB for
  every path including the C phases (4.00–4.28 GB); the cgroup peak
  includes BuildKit, the cargo registry downloads and the compilers;
  C is comparable to A/B, not larger.
- The **performance objective is met for these workloads on this
  host** — with the stated scope: AMD64 Linux, this CPU, qemu-POCF on
  this host, these two bounded fixtures, and this BuildKit/buildx
  version set. It is not a claim about every host, every emulator, or
  the ctrs API path.
- The A↔B noise (r1 tails at 101–120 s) and the outlier show host
  drift across the run; the rotation order spreads it evenly across
  cells and the medians are unaffected.
- Static artifact size/memory increases: none introduced — S6 ships no
  product change, so the 5% binary-size and 20% RSS thresholds are not
  implicated. BuildKit v0.34.2 (A) built with the same bundled emulator
  as B (QEMU 10.2.3).

## S7 — final qualification, release prep, ultrareview (2026-11-15, landed)

What landed at this milestone:

- **The aarch64 release row now consumes the qualified cross path.**
  `.github/workflows/release.yml`: the aarch64 row builds on
  `ubuntu-26.04` (AMD64) with the pinned cross toolchain
  (`messense/rust-musl-cross:aarch64-musl@sha256:02e790506c5f15a533bc05b3af8719b16a8a2314480f6f0fdc0166432035d9b4`,
  rustc 1.96.1, gcc 12.4.0) — the same path as `cargo xtask linux
  --arch arm64`; no qemu is registered on that row. Native ARM64 test
  coverage stays with ci.yml's `linux-musl` job (`ubuntu-26.04-arm`,
  every push). The x86_64 row and every dispatch-only/publication gate
  are unchanged (default-branch recheck ×3, tag-existence check fails
  closed on non-404, 2×x86_64 + 2×aarch64 static ELF gate, exact
  per-zip artifact sets, SHA256SUMS self-check). The aarch64 row no
  longer runs `cargo test`: its binaries cannot execute without an
  emulator, and qemu execution would not be a native ARM64 result. The
  workflow was never dispatched; both Linux rows' exact step commands
  were reproduced on this host (see `docs/evidence/release.md`).
- **Release artifacts prepared locally** (Linux only; macOS is Needs
  environment): the four musl-static binaries, built from this tree
  with the release-workflow `dist` profile (fat LTO), no INTERP/NEEDED
  (verified in the builder and on the packaged copies), byte-identical
  across the from-scratch rebuilds; zips + `SHA256SUMS` verified with
  `sha256sum -c`. Actual AMD64 startup/build behavior of the packaged
  dist artifacts: `BIN="$PWD/.work/release/20261115/check/bin" bash
  tests/linux-host.sh` → **28 passed, 0 failed** (isolated
  prefix/ports/config, per-run unique name). Full artifact table,
  commands and dependency/emulator provenance: `docs/evidence/release.md`
  (S7 section). No emulator bundle is included; the aarch64 binaries
  are native ARM64 code.
- **Qualification runner**: `bash tests/arm64-build.sh --all` on the
  final source → **160 passed, 0 failed**. The path here was: green
  160/160 twice, then 158/160 on two runs, both for environment
  reasons, each re-proven: (1) the cross case's `cargo test -p xtask`
  check died on root-owned `target/debug` left by this session's
  root-in-container workspace test (CI is unaffected; `target/debug`
  is untracked scratch) — removed through the pinned builder, 5/5
  re-pass; (2) the lifecycle case's worker-failure rebuild hit a
  transient Docker Hub 404 on the alpine digest — the digest is intact
  (verified from this host), the case re-ran green standalone, and the
  final `--all` is 160/160 with zero leaked harness resources (see the
  harness repair above). Registry pulls on this host intermittently
  fail with 404/h12tiny connect errors — treat a registry-dependent
  miss as suspect until the digest is re-checked.
- **Workspace tests** (root, pinned builder image, final source):
  `cargo test --workspace --lib --tests --no-fail-fast` →
  **297 passed, 0 failed** (exit 0). Host run: 6 pre-existing
  `ctrs-init` failures (chown to uid/gid 0) remain; unrelated, CI is
  the authority. `cargo test -p ctrs-image`: 47/47 including the new
  capped-reader test. `cargo test -p xtask`: 5/5.
- **Ultrareview** (installed `~/.agents/skills/ultrareview`, run under
  the campaign's granted review authority; four read-only lanes:
  daemon, guest/runtime, tests, build/release). **No P1 findings.
  Two P2 findings, both fixed and re-proven:**
  - `docker load` ingested blobs with no size cap
    (`ctrs-image::archive::load`): a crafted archive could fill the
    host disk. A per-blob 64 GiB cap now fails the ingest with
    `InvalidData` (mirrors the guest's expansion ceiling); the
    partial blob is unlinked by `Ingest`'s drop guard; unit test
    `capped_reader_fails_past_the_limit` added (47/47 green).
    Residual: there is still no total-archive budget — filed as
    CTRS-5 (P4).
  - `xtask kernel`/`xtask disk` used the mutable `debian:trixie` tag:
    now pinned to the verified index digest
    `sha256:9c6e381421d0f48d1b8133e573f33c185ee16cbf505eda9c4a8a4791b25ea8a6`
    and recorded in `docs/evidence/release.md`.
  P3/P4 findings were filed as CTRS-1…CTRS-10 in `TODO.md` (not fixed
  in this slice). The tests lane flagged identical `image_id`s across
  incremental rounds as a possible invalid measurement; the
  blast-radius probe shows the incremental state genuinely re-executes
  the compile (`Compiling workload-app` present in the probe log;
  comment-only markers change no compiled bytes, so byte-identical
  output images are the expected result, and emulated incremental
  runs at 2.2–6.4 s vs ~0.2–0.4 s for layer hits). S6's incremental
  numbers stand; no fixture change was made.
- **Harness/bench repairs from the review**: per-case `ISO_PRESERVE`
  reset (`--all` leak fix); **per-case release of the isolated engine**
  (`iso_release` in `tests/lib/isolated-env.sh`, called by `run_case`)
  after finding that every `--all` run leaked its compat/identity/
  platform harness containers as running processes; the bench's trailing
  perf-gate failure now exits 75 (deferred, never passed) instead of
  silently exiting 0 — the header's exit-code contract now holds.
  Affected proofs re-run.
- **Legacy-consumer sweep**: `main.rs` module comment no longer names
  deleted modules (`scan`, `tools`, `cli_pins`); the
  `examples/cross/rust-musl` fallback comment now names the unified
  `rust:1.100.0-alpine` pin; `docs/evidence/release.md` SBOM scope and
  toolchain provenance match the files (the x86_64 Linux artifacts
  build with the repo-pinned nightly auto-installed in the builder;
  the aarch64 artifacts with the messense stable — now stated);
  `docs/install.md` matches the host-follow default; `docs/development.md`
  already matched. The Rosetta x86-64 exception is retained (its
  supported environment). The `tonistiigi/xx` pilot remains recorded as
  a rejected alternative; no consumer remains for the old
  `rust:1-alpine` pin outside historical evidence notes.
- **Release.yml verification of the aarch64 step commands**: the exact
  commands run green on this host (fat-LTO dist profile; static ELFs;
  machine AArch64; no INTERP/NEEDED; 52 s warm, ~1m41s from scratch).
  CI YAML parses (`jaq`), matrix conditions traced per row. The
  workflow has never been dispatched and must not be from this
  campaign; hosted CI (including `arm64-compat`) remains unobserved.

## Needs environment (statuses at P0–S7)

| Proof | Prerequisite and command | status |
| --- | --- | --- |
| Live-drain of a stale running/paused builder end-to-end | A stale builder with live sessions kept running across a ctrs upgrade — unreachable on this host: a dead "running" record reconciles to exited at daemon boot (exit 255), and `paused` is not persisted. The refusal gates fire before any mutation; the classifier matrix is unit-tested (`assessment_matrix`) | **Unreachable end-to-end with today's product semantics (see S2 findings); unit matrix only** |
| AMD64 Linux ctrs runtime | Root-capable isolated namespaces/cgroup environment; `BIN="$PWD/target/linux-x86_64/release" bash tests/linux-host.sh` | **passed 2026-11-14, twice, 28/28; and 2026-11-15 with the packaged dist artifacts (`BIN=.work/release/20261115/check/bin`), 28/28** |
| No foreign host handlers | Fresh dedicated AMD64 host or proven independent binfmt namespace; `bash tests/arm64-build.sh --case compatibility --require-no-binfmt`; runner must fail closed if any foreign handler can service the test | **Unavailable on this host (2026-11-14): one global binfmt_misc instance serves every namespace; a fresh private-mount instance still shows `qemu-aarch64` POCF. The ordinary compatibility case passed with a host handler visible (and says so per backend). `--require-no-binfmt` fails closed, exit 1, creating nothing. The bundled-emulator path was never exercised here — it needs a dedicated host or VM without a foreign handler** |
| macOS regression | Apple Silicon macOS; `cargo test --workspace`, `cargo xtask all`, `conformance/smoke.sh` | **not available on this host** |
| Performance | Idle AMD64 machine passing both perf-gate checks; `bash bench/arm64-build.sh --samples 5 --all-states` | **Measured 2026-11-15** (bench/results/20261115T011929Z/): 90 samples, 90 valid, 0 rejected, gates quiet before and after (load 1.91 at start). Cross (C) vs emulation (B) gap outruns spread in every cell; A (old pin) neutral vs B; no memory penalty for crossing. Numbers are host-specific (this CPU, qemu-POCF, BuildKit v0.35.0) — a dedicated idle host would strengthen but not change the direction of these results |
| Hosted CI result | Separately authorized push/run | **not authorized by this campaign** |
| Actual publication | Separately authorized release dispatch | **not authorized by this campaign** |

## Parity register (in progress)

| deliverable | case / command | status |
| --- | --- | --- |
| native AMD64; ARM64 musl/glibc via both entry points | `--case compatibility` (S1) | **passing 2026-11-14 (24 checks; 6 builds + process evidence; host handler visible, unproven independent)** |
| managed identity, reconciliation, ownership | `--case identity` (S2) | **passing 2026-11-14 (40 checks; fresh install, matching reuse, stale tag, stale stopped replace, failed pull, interrupt recovery, simultaneous callers, foreign conflict, cache sentinel, buildx path; host/harness contexts unchanged)** |
| pull/build/export/load/inspect metadata | `--case platform` (S3) | **passing 2026-11-14 (14 checks; aliases/v8, disagreement and single-manifest pulls fail closed, save/load round trip, OCI export descriptors, multi-platform load refusal)** |
| native compilers, static AArch64 output | `--case cross` (S4) | **passing 2026-11-14 (25 checks; xtask aliases/refusals, default AMD64 execution, explicit ARM64 output, host-native builds of both fixtures, target execution, static AArch64, per-arch outputs/caches)** |
| cancel/failure/cleanup, emulator diagnostics | `--case lifecycle` (S5) | **passing 2026-11-14 (35 checks; concurrency, cancellation, worker failure, failed target execution, daemon restart + cache reuse, emulator fault injection; mutation-verified)** |
| equivalent-work benchmark | `bench/arm64-build.sh --samples 5 --all-states` (S6) | **measured 2026-11-15 (90 samples, 0 rejected; host Ryzen 9 9950X; load 1.91 at start). C (cross) beats B (emulated) in every cell: rust cold 5.30 s vs 77.79 s; c-cpp cold 35.26 s vs 104.92 s. A (old pin) is neutral vs B. Objective met for these workloads on this host; not a general claim** |
| static binaries, checksums, local manifest | S7 commands; `docs/evidence/release.md` (S7 section) | **done 2026-11-15 (Linux only): four static musl ELFs (2×x86_64 PIE, 2×AArch64 EXEC), zips + SHA256SUMS verified, hashes committed there; macOS row not rebuilt here** |
| environment prerequisites | `--case environment` | **passing 2026-11-14 (22 ok, 0 missing, 0.2–1 s)** |

## CI qualification failure investigation (2026-11-20)

The last green main workflow run was [43645921846](https://github.com/joshuarli/ctrs/actions/runs/43645921846), SHA `d61e9ff1372da00f395ae15b0011f65d9a53cefb`; it had no ARM64 qualification job. The first subsequent main run, [43674689893](https://github.com/joshuarli/ctrs/actions/runs/43674689893), SHA `9386f70868d0ed2a42e8332e71f6945697f87d29`, failed that job. There is no green qualification run to bisect against. `git log --oneline d61e9ff..9386f70` includes `90bee60`, which introduced the job with `--case environment compatibility platform cross identity lifecycle`. The first run's failing step was **Run the ARM64 qualification runner**:

```text
Run bash tests/arm64-build.sh --case environment compatibility platform cross identity lifecycle
unknown argument: compatibility
Process completed with exit code 2.
```

The parser accepts one name per `--case` (`tests/arm64-build.sh:43-52`). `b721aa9` corrected the workflow arguments, exposing further failures. In [run 44853584973](https://github.com/joshuarli/ctrs/actions/runs/44853584973) at `d5625e903f16289787b4cd0f9cd94a671b1399a7`, the same step reported:

```text
MISS kache (rustc wrapper not on PATH)
ok   two-platform OCI export built
MISS OCI index does not carry both entries: {"schemaVersion":2,"mediaType":"application/vnd.oci.image.index.v1+json","manifests":[{"mediaType":"application/vnd.oci.image.index.v1+json", ...}]}
tests/arm64-build.sh: line 728: jaq: command not found
MISS OCI amd64 manifest config is /
MISS OCI arm64 manifest config is /
MISS builder did not answer after docker restart
runner: 130 passed, 7 failed
```

The first counted failure is the missing `kache`: the environment case explicitly requires it and increments `FAIL`. The platform case invokes `jaq` to descend into a nested index; its first invocations suppress errors, so without `jaq` it inspects the outer index and reports the misleading missing-entries message. Subsequent invocations expose `jaq: command not found`. The workflow installs neither tool. These observations establish missing runner prerequisites, not an ARM64 image metadata defect. They do not establish that the nested index contains correct platform entries: that check never executed successfully.

Proposed workflow change, before **Run the ARM64 qualification runner** (after Rust installation), install both pinned executables into the runner's Cargo bin directory and verify them on `PATH`:

```yaml
      - name: Install qualification tools
        run: |
          cargo install --locked --git https://github.com/joshuarli/kache --rev 88537005c6c5d90968c6064585ec51a7096093e5 kache
          cargo install --locked --git https://github.com/01mf02/jaq --rev 0ee33bbcf44aed00c91748071e5031e8a5410339 jaq
          command -v kache
          command -v jaq
```

This proposal has not been executed on the hosted image; validate the pinned installs and rerun the job. It does not promise a green job: the separate identity failure follows `docker restart` with one immediate `buildctl debug workers` call, whose stderr is suppressed (`tests/arm64-build.sh:352-356`); its cause remains unproven. Preserve the isolated harness logs and capture that command's stderr on an AMD64 Linux host with Docker and QEMU binfmt to investigate. The deslop closeout's DSLP-8, now CTRS-13 in `TODO.md`, recorded the platform case as needing evidence; the missing `jaq` explains the reported platform failure, but a successful platform qualification and handler-free proof remain outstanding. The hosted run reports a visible `qemu-aarch64` binfmt handler and therefore cannot prove handler independence.

### Resolution (2026-11-21)

The job went green after four fixes: the workflow installs pinned kache and jaq; `inspect_oci_export` reports jaq failures instead of turning them into empty values; `wait_builder_ready` replaces the single immediate probe after `docker restart` (stock Docker with the same pinned BuildKit also failed that probe, because `restart` returns before buildkitd's socket exists); and `case_compatibility` compares `FAIL` against its count on entry, since the earlier kache MISS had skipped the whole case. Once compatibility and identity ran, the `g-foreign` refusal sometimes reached the CLI as `write: broken pipe`. The daemon closed the connection while the build context was still uploading, and 11 of 50 local probes lost the response. `http::lingering_close` now shuts down the write half and drains up to 256 KiB for at most 500 ms before closing, and `early_build_error_survives_an_unfinished_upload` covers it. With these fixes the qualification run reports `runner: 162 passed, 0 failed`. The hosted run still has a visible `qemu-aarch64` handler, so it does not prove handler independence.
