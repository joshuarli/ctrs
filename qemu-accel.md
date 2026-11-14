# ARM64 builds on AMD64 Linux

## Status

- Goal: reliable ARM64 builds, with native cross-compilation for substantial compilation work and QEMU for target execution.
- Last inspected revision: `753a18db7de0ee49bfd8552297ab547977158b17`. Last accepted: S1 (2026-11-14, on `602f5c5`).
- Accepted slices: P0 (baseline, isolated Linux harness, environment runner, pin candidate), S1 (foreign builds through both entry points; managed builder provisions from the pin's digest reference). Known red: S2–S7 gates unrun, not passing.
- Parked branches: none. Next: S2, using one writer.
- Start only on a separate execution request. First command: `git status --short`.
- Local completion and release qualification are distinct. Keep unavailable proofs under **Needs environment**; never report them as passed.

## Charter

Execute within the owner's execution grant. This document alone grants no implementation, destructive action, or publication authority. Decide within the bounds below and keep going. Record only decisions that later slices depend on.

Use one writer. All slices run serially because they share verification infrastructure, image semantics, or build contracts. Follow the installed `orchestrate` skill and its campaign reference at `/home/josh/usr/dotfiles/base/.agents/skills/orchestrate/references/campaigns.md`, including the parent steering checkpoint after each accepted slice, on resume, and after two failures. Do not duplicate its lane protocol here.

Before writing scratch, exclude `.work/` through `.git/info/exclude`. Use `.work/tmp/qemu-accel` for temporary files, logs, isolated state, and TMPDIR. Worktrees, if needed, belong in `.work/wt/<slice>`. Do not use system temporary directories for host scratch. Existing BuildKit-internal temporary paths are outside this host-scratch rule.

Land only green slices, as Conventional Commits with scope `build`, `platform`, or `cross` and the slice ID in the body. Commit only campaign work. Never push, create release tags, dispatch workflows, publish packages, or install globally. Preserve unrelated dirty work.

Use the narrowest decisive test on the integrated tree. Announce full suites, container toolchain builds, and benchmarks before starting them. Do not run formatters or change the pinned Rust toolchain. Release builds belong to final verification and benchmarks.

Each failing slice gets two materially different, cause-driven repair attempts, at most 90 minutes total. Preserve the failing command, first error, established cause or falsified hypotheses, and retry condition on its parked branch. Never retry unchanged to green. Park dependents and continue independent work. A shared environment blocker has one owner: the parent.

Repair an encountered defect immediately only if it blocks a listed proof or violates a hard invariant. An execution-loop command exceeding 5 minutes after provisioning gets at most one 30-minute repair attempt to restore a <=5-minute focused loop. Other performance work waits until S6. Unrelated defects become findings, not scope expansion.

## Decisions

### Owner-decided

- **2026-11-14 (P0):** Freeze the BuildKit pin candidate to `moby/buildkit:v0.35.0` — index `sha256:aa632b921ef07411d2cb77292cd34213d4f7b384001d6fceef1e1f25bf9752bb`, linux/amd64 manifest `sha256:a521fc1fd903a46c611c733dd692548512232fba2e0386d6055846a903d05a71`, linux/arm64 manifest `sha256:7dc61a9fab7c7f5a50b1cdbbefa4180829e68c6c0172206eb54ad934de097ddf`; bundled emulator QEMU 10.2.3 (`buildkit-qemu-aarch64` sha256 `239ff153cde81b6a6ab2c48eef9cff234751caa8e9d841363eace8db51e000e8`, x86-64); buildkitd v0.35.0 from tag v0.35.0 commit `f55949dea4f03bb9d85b73e9afc9a609291289db` (GitHub Actions run 43069750854, Dockerfile target `release`, base alpine 3.24 / golang 1.27-alpine3.24). Fallback on a demonstrated v0.35.0 release defect: `moby/buildkit:v0.34.2` (newest stable patch of the preceding supported line). Not yet qualified: S1 proves the candidate end to end.

- **2026-11-14:** Enforce the managed pin. A manually retagged image is not a supported managed-image override. Custom images use a separate user-selected buildx builder. Preserve that selection; do not add a managed override setting.
- The source brief requires compatibility builds and an explicit cross-compilation path on AMD64 Linux, particularly Alpine/musl, Rust, and C/C++. It excludes FEX, a full-system ARM VM, mandatory remote builders, and silent Dockerfile rewriting.

### Executor decisions (2026-11-14, S1)

- **Provisioning uses the digest reference, never the tag.** buildx re-resolves `moby/buildkit:buildx-stable-1` on every builder init and the store replaces a tag's record by name; on this host (tag = v0.34.2 today) that silently displaced the v0.35.0 pin before any build ran. `create_body()` now sets `Image` to the pin's `moby/buildkit@sha256:aa632b…`; the tag record is kept for visibility only. S2 owns the full identity reconciliation this exposed (index/manifest/config verification, stale-tag detection, pending-upgrade reporting).
- **On hosts with a working foreign binfmt handler, BuildKit's `SupportedPlatforms` probe treats the target as "supported" and argv-wrapping never happens; RUN steps are serviced by the host's handler, not the bundled emulator.** The runner records which backend served each build (`emulator-mount` marker), asserts `no` for AMD64, and fails closed under `--require-no-binfmt`. Handler-free proof is unavailable on this host (single global binfmt_misc instance) and stays Needs environment.
- **Plain `docker build` silently selects a default docker-container builder on the moving `buildx-stable-1` tag.** Everything ctrs-mediated must either pin `--builder ctrs-build` (buildx) or force `DOCKER_BUILDKIT=0` (classic `/build`). Digest-pinned qualification must never rely on a default-named builder.
- **First `/containers/create` per builder returns 400, retry succeeds** (both intercept and plain paths, reproducible). Not tag-displacement; root cause open; the request-failure WARN line logs neither query nor body. Do not treat the log line as proof of failure; S2 owns the create/start boundary and should carry the query string and body in the WARN line.

### Prescribed

- Reuse BuildKit's bundled emulator. Its availability is proven below; its execution through ctrs still requires S1. A separately distributed QEMU package and general foreign `run`/`exec` are outside this campaign. A demonstrated gap parks the affected build capability with evidence instead of authorizing a second runtime architecture.
- Keep one `ctrs-build` container and its existing named cache volume. Preserve lazy provisioning, idle **pause/resume**, cancellation, and native builds. The current idle watcher pauses rather than shuts down the builder; retain that behavior.
- Canonical image identity belongs in `daemon/builder.rs`. Compare index digest to index digest, selected manifest to selected manifest, and config digest to container image ID. These digests are not interchangeable. A tag or version string alone never proves identity.
- Reconcile only a stopped ctrs-owned builder. Neither `BUILDS == 0` nor an absence of execs proves a running BuildKit has no sessions. For a stale running or paused builder, report current/desired identities and a pending upgrade; keep its active sessions intact. New work requiring the new pin fails actionably until an explicit maintenance stop. Never silently run that work on a stale version.
- Reconciliation must cover classic and buildx entry points. A buildx client may hold the old container ID: either preserve that ID safely or return a retryable conflict and require reinspection; never return success for a removed ID. Do not replace an unlabeled same-name container automatically. Report the conflict and preserve it.
- Do not delete cache volumes, alter image-store or container-record schemas, change `vm.json` or the wire protocol, or touch host binfmt handlers. Recreate only a stopped container carrying the ctrs ownership label, within the execution grant. If that grant does not cover replacement, park reconciliation.
- Linux `xtask linux` defaults to the native host architecture. macOS retains its intentional ARM64 default, including guest tasks. Support `arm64`/`aarch64` and `amd64`/`x86_64`/`x86-64`/`intel` consistently. Reject unknown, missing, or conflicting `--arch` values before spawning Docker. Retain existing output locations `target/linux/release` for ARM64 and `target/linux-x86_64/release` for AMD64; separate Cargo target triples and compiler caches beneath them.
- Normalize `linux/arm64/v8` to baseline `linux/arm64`; accept baseline ARM64 with no variant. Preserve existing supported non-baseline platform behavior where it is genuinely implemented. Reject extra components and unsupported variants rather than dropping them. Preserve the classic build API's existing case normalization. Omitted platform still means the host; malformed explicit platform never means the host.
- Preserve one platform per local tag and the existing on-disk platform string contract. Use separate AMD64 and ARM64 fixture tags. Support single-platform load; qualify multi-platform OCI export independently. Do not advertise multi-platform local load.
- Extend `GET /ctrs/builder` and existing diagnostics with desired identity, actual image/container identity, running BuildKit/emulator versions, upgrade status, and separately observed build capability. Diagnostics must not pull, start, or mutate the builder. Report unobserved capability as unknown, with reason; advertised platforms alone do not mean verified.
- No new runtime Rust dependency or toolchain framework. Build-only pinned images/helpers are permitted after maintenance, license, transitive-weight, and provenance checks. Apply the performance gates in S6. Never bypass TLS, digest checks, host seccomp, or existing ordinary-container security policy.

### Delegated within bounds

- P0 selects one stable supported BuildKit release from official upstream releases. Qualify at most two candidates: the first chosen release, then its newest stable patch if a demonstrated release defect requires it. Freeze the exact version and immutable index digest before S2. Record selected AMD64/ARM64 manifest digests, bundled emulator version/checksum, and upstream source/patch provenance. Failure of both candidates parks upgrade; it does not permit an arbitrary renamed QEMU binary.
- Prefer a pinned `tonistiigi/xx` build-only stage with native Rust plus Clang/LLD and the ARM64 musl sysroot. Compare this with explicit pinned Clang/LLD configuration against correct C linkage, host-native build scripts, maintenance, and image weight. Allow one 30-minute pilot of each; choose the simpler passing arrangement, with fewer external components as the tie-break. No new compiler framework. Record why the chosen arrangement wins and its removal conditions if a workaround is needed.
- The executor may adjust private helpers and slice boundaries while preserving acceptance and serial ownership. A new public API, persistence schema, runtime privilege, general foreign execution, or publication action parks that item for authority.

## Baseline and foundation

Inspected on 2026-11-14 at the revision in Status:

| Observation | Evidence and limit |
| --- | --- |
| AMD64 Linux host | `uname -a`: Alpine `7.2.9-2-stable`, x86_64; user is not root |
| Outer Docker available | `docker version`: client/server `linux/amd64`, version `29.9.0`; this is tooling, not ctrs qualification |
| Foreign host handler exists | `/proc/sys/fs/binfmt_misc/qemu-aarch64` enabled, interpreter `/usr/bin/qemu-aarch64`, flags `POCF`; leave untouched |
| Bundled native emulator exists | Read-only probes of existing **unrelated** `buildx_buildkit_musl-publish0`: BuildKit `v0.34.2`, QEMU `10.2.3`; ELF machine bytes `3e 00` for both executables prove AMD64 tools |
| Observed outer image | `moby/buildkit:buildx-stable-1`, local ID/repository digest `sha256:c5f8862f52499773af85bc07695b2379ef08e8002352b0df2c4864c91d78dabe`; not a selected campaign pin |
| Upgrade defect | `ensure_image()` returns a tagged local image before checking `PINNED`; existing containers bypass image provisioning too |
| Cross-build defect | `linux_build()` uses the output architecture for `docker run --platform`, invokes Cargo without a target, and defaults to ARM64 even on AMD64 |
| Metadata defects | `Platform::parse()` ignores remaining components; pull's `ImageConfig` lacks OS/architecture; explicit malformed pull/create requests can fall back silently; inspect takes the last platform component |
| Store contract | `Store::put_image()` replaces by name, independent of architecture |
| Rosetta boundary | Linux `ctrs-vmm/src/process.rs::rosetta_installed()` returns false; existing hiding targets only `buildkit-qemu-x86_64` |

Single-run loop timings, elapsed seconds: `docker version` 0.13; `docker ps` 0.05; image inspect 0.04; BuildKit version 0.17; emulator version 0.03; combined ELF probe 0.03; `bash -n tests/linux-host.sh tests/e2e.sh bench/suite.sh` <0.01. These are command checks, not benchmark claims.

No local `target/` existed. Rust compilation, ctrs runtime, clean-binfmt builds, upgrades, and workload performance were not tested. No known baseline test failures have been established. P0 must run and time the first focused Rust checks; do not treat absence of results as green. The executable probe proves native bundled-emulator availability only, not BuildKit integration or nested foreign execution.

## Sequence

All paths below describe existing ownership or explicitly planned files. The proposed runner and examples do not exist yet. Build proof alongside each capability; do not build a general evaluator before delivering S1. Each runner group must reject zero selected cases and return nonzero on failure or unmet prerequisites. `--all` reports passes, failures, and unavailable environments separately; a required skipped case cannot count as release qualification.

### P0 — establish a reproducible baseline (small; no prerequisites)

Own `tests/linux-host.sh`, initial `tests/arm64-build.sh`, and baseline portions of `docs/evidence/arm64-build.md`. Capture revision, CPU/model/core count, kernel, load, toolchain, Docker/buildx, ctrs/ctrs-init ELF architecture, BuildKit identities, emulator, and binary handlers. Inspect existing tooling before pulling anything. Preserve the unchanged source revision as the runnable performance reference.

Change the Linux harness to accept explicit `BIN` and unique resource prefix, validate both input executables as AMD64, and use isolated Docker config, ctrs state, socket, network, ports, containers, and volumes. Validate the endpoint before mutation. Cleanup traps remove only recorded test resources on success, failure, and INT/TERM; preserve failure logs. Do not run its current broad fixed-name removal against a shared engine.

Run narrow tests `cargo test -p ctrs-image --lib registry::tests` and `cargo test -p ctrs --lib daemon::builder::tests`, with repo-local TMPDIR, Rust `kache`, and Linux musl `mold`. Time them; preserve failures and causes. Never run package installation or privileged host changes to repair the environment automatically.

Choose/freeze the BuildKit candidate under Decisions. Record provenance without assuming that the unrelated host builder matches ctrs's pin. Add an environment-only runner group; it performs no builds or shared-host mutations.

Acceptance: `bash tests/arm64-build.sh --case environment` validates all available prerequisites, reports exact missing ones, and never starts or upgrades a builder. Size target: <=2 minutes after binaries exist.

### S1 — foreign builds through both existing entry points (medium; P0)

Own the runner, `tests/fixtures/arm64-build/`, and only required repairs in `daemon/builder.rs` and `builds.rs`. Use the frozen candidate in disposable test state. Implement the substantive pilot first: real ARM64 Alpine shell, separate ELF child, and shebang script invoked from a child, through buildx and classic `POST /build`/managed buildctl. Include a native AMD64 control.

Prove which interpreter executed each target: capture BuildKit invocation/progress and inspect live processes or executable identity. Validate target ELF architecture, computed results, child exit status, and loaded image metadata. Platform advertisements and `uname` are supplementary only. Preserve default security settings for ordinary containers; do not pass ARM64 syscall numbers through AMD64 seccomp.

Use a fresh privileged test environment with independently isolated binfmt state only if isolation is demonstrable. Read registrations from both host and test namespace before/after. Never unmount, disable, reset, or register handlers on the shared host. If independence cannot be proved, run the ordinary integration cases, explicitly mark handler-free proof unavailable, and place that proof under Needs environment.

Acceptance: `bash tests/arm64-build.sh --case compatibility` covers native AMD64, ARM64 musl, and ARM64 glibc shell/child/script execution through both entry points. Each case <=5 minutes after image provisioning; shard by entry point if necessary. Positive outcomes alone on this host do not prove independence from binfmt.

### S2 — reproducible managed identity and safe reconciliation (medium; S1)

Own `daemon/builder.rs`, required builder lifecycle call sites in `daemon/api.rs`, `daemon/ops.rs`, `daemon/engine.rs`, `builds.rs`, existing diagnostic reporting, and identity/lifecycle runner cases. Search the actual create/start/exec routes before changing them; names in this ownership list do not imply those routes are already reconciled.

Put the immutable pin and release identity in one canonical definition. Verify fetched index/manifest/config relationships, actual container image ID, and platform before provisioning. Detect a stale local tag, stale container, and changed desired pin independently. Pull/validate replacement before removing any stopped owned container. Retain the exact cache volume and Docker selection files. Never hold the lifecycle lock across registry I/O. Recheck container status and ownership under the lifecycle serialization boundary before replacement. Start/create and reconciliation must share that boundary. Gate new buildx dial-stdio sessions and classic build admission against desired identity too; inspecting only create/start misses an already-running stale builder. Existing sessions drain without interruption.

Running or paused stale builders remain intact and report pending upgrade as specified in Decisions. Extend safe stopped start/create boundaries for classic and buildx; handle old container IDs explicitly. A failed pull leaves the previous state usable and does not fall back silently. A crash after removal but before recreation must recover on the next request from the pin and preserved cache. Do not invent a durable reconciliation journal.

Acceptance: `bash tests/arm64-build.sh --case identity` checks fresh install; matching restart; stale tag; stale stopped container; stale running/paused container with live work; ownership conflict; failed pull; interrupted replacement; simultaneous callers; old-ID behavior; same cache content after restart/upgrade; and unchanged user builder selection. Run affected builder/diagnostic unit tests too.

### S3 — accurate platform requests and image metadata (medium; S2)

Own `ctrs-image/src/registry.rs`, `archive.rs`, affected `store.rs` tests, `daemon/api.rs`, classic build option validation in `daemon/builder.rs`, and platform fixtures. Keep the existing storage format and single-tag replacement semantics.

Use one canonical normalization path for explicit requests and metadata validation. Check selected index entry, single-manifest digest pull, and downloaded config OS/architecture/variant consistently. Preserve digest verification. Reject missing required registry platform metadata and mismatches before publishing a store record. Preserve existing archive compatibility when metadata is absent, but distinguish that fallback from registry validation; explicitly conflicting archive metadata fails. A malformed request returns HTTP 400; valid unavailable platform follows existing no-platform/error transport. Failed operations leave the previous tag record intact and do not label blobs as a successful image.

Test baseline aliases, ARM64 v8 equivalence, invalid variants/components, missing/empty values, malformed explicit input, config/index disagreement, single-manifest conflict, archive round trips, inspect architecture, and create mismatch. Ensure classic build option normalization and buildx requests agree. Preserve native/macOS cases and any supported non-target platforms; do not introduce a new variant field in persisted records.

Acceptance: `bash tests/arm64-build.sh --case platform` runs focused image/API regression tests and a real ARM64 export/load/inspect round trip. Separate single-platform load from two-platform OCI export, inspecting each output's descriptors/configs. Multi-platform local load must fail clearly if unsupported.

### S4 — host-native compilers and explicit target output (medium; S3)

Own `xtask/src/main.rs`, `Dockerfile`, `.cargo/config.toml`, `examples/cross/`, target-toolchain fixtures, and runner cross cases. This is feature implementation, not a speed claim.

Separate typed execution architecture, target triple, output directory, and cache identity. Share validated argument parsing instead of booleans and independently scanned flags. Preserve macOS defaults and artifact locations. Use native `$BUILDPLATFORM` compiler stages and `$TARGETOS`/`$TARGETARCH`/`$TARGETVARIANT` for target selection. Pin toolchain/helper images by digest and record package/toolchain provenance. Keep build scripts and proc macros native; configure target-specific compiler, linker, sysroot, and C dependency library discovery. Do not globally set a target compiler for host dependencies.

Add copyable Rust musl and C/C++ musl Dockerfiles. Both compile with native tools, prove static AArch64 output with ELF inspection, and execute representative results through a foreign target stage. Include a Rust build-script/proc-macro host check and real C linkage, not only a dependency-free hello world. Ensure caches differ for AMD64 and ARM64 outputs; layer-cache keys include target inputs. Final image metadata must be ARM64.

Acceptance: `bash tests/arm64-build.sh --case cross` covers aliases and invalid arguments without spawning Docker; default Linux AMD64 execution; explicit ARM64 output; both examples; static/linker checks; host-native build tools; target execution; target-specific output/cache separation. Use small debug fixtures for the local loop. Build actual release ctrs/ctrs-init outputs only at S7.

### S5 — lifecycle hardening and CI parity (medium; S4)

Own runner lifecycle cases, required lifecycle repairs, `.github/workflows/ci.yml`, and correctness sections of development/architecture/diagnostic docs. Preserve current native AMD64, ARM64-native, and macOS checks. Add one AMD64-to-ARM64 job invoking the same qualification runner. No CI service/framework migration.

Use distinct architecture tags and controlled signals/barriers to test concurrent builds, cancellation, worker failure, failed target execution, restart, cache reuse, and cleanup. Verify no orphan exec/context remains after cancellation and that a subsequent build succeeds. Fail within a 60-second cancellation deadline after the signal. Inject missing/non-executable/corrupt emulator only in disposable test builder state; diagnostics name the missing capability and remediation, and native builds remain functional. Restore or discard that test state.

Acceptance: `bash tests/arm64-build.sh --case lifecycle` passes the cases above. At this parity milestone run `cargo test --workspace` and the complete build runner, plus existing `tests/linux-host.sh` against its isolated fixture. Record explicit environment gaps. Verify one meaningful mutation per proof area makes its regression case fail, then restore it; do not commit mutations.

### S6 — measured optimization (medium; S5)

Own `bench/arm64-build.sh`, workload fixtures under `bench/arm64/`, performance sections of `docs/evidence/arm64-build.md`, and only bottleneck-driven repairs in earlier owned files. Extend the existing shell-based infrastructure; no new benchmark framework or unrelated benchmark cleanup.

Compare A: unchanged preparation revision and its actual old pin; B: qualified pinned emulation; C: native cross-compilation of the same workload/output. A missing/failing old path is a negative baseline, not a zero-duration build or speedup denominator. Run it in separate state; never swap a shared live builder's image. Record all versions, flags, host resources, digests, cache policy, errors, and output tests. Explain intentional platform-correctness differences without calling them performance regressions.

Use a bounded Rust workload with proc macros/build scripts plus C linkage for CPU-heavy compilation, and a C/C++ multi-file workload with >=100 compiler/child invocations for process-heavy work. Freeze source inputs, checksums, result tests, worker count, and compiler settings before comparison. Use a real owner workload only if already available and reproducible; no owner response is required.

Measure five valid samples per path/state in rotated order A/B/C, B/C/A, C/A/B. Separate provisioning/downloads, cold compilation, one-file incremental rebuild, Docker layer hits, and compiler-cache hits. Explicitly invalidate the intended cache layer per mode. A compiler-cache mode without an actual compiler cache is unavailable, not a hit. Do not assume persistent QEMU translation caching. Keep profiling outside measured samples; identify the limiter and verify work/results in the measured interval.

Collect wall/user/system time and peak memory for the complete build process tree via its isolated cgroup (`memory.peak`), not only the docker client RSS. Save individual samples, medians, range/spread, errors, and machine metadata. Read the global performance instructions; run `perf-gate-ready` before and `perf-gate-ready -1` after timed groups. Discard overlapping-load runs. Host-busy gates defer qualification, never become passes.

Initial product speed/size numbers are observations until this slice. Accept a speed improvement only when the median gap exceeds observed spread on equivalent successful work. Native controls must not regress beyond spread. Preserve existing applicable repository budgets, including the smoke harness daemon idle RSS limit of 30 MB; thresholds below do not waive them. Memory increases >20% and static artifact size increases >5% require a concrete resource justification; otherwise reject the optimization. Dependency changes additionally report clean build-time, image weight, startup, and binary-size deltas. Retain negative results and improvements benefiting unchanged consumers. Do not gate every repair on an impossible speedup, or exclude newly exposed baseline debt from reporting.

Acceptance: `bash bench/arm64-build.sh --verify` checks workload completion, cache-mode distinctions, sample accounting, process-tree memory collection, and report generation with a short pilot. Then announce/run `bash bench/arm64-build.sh --samples 5 --all-states` as the expensive milestone. If no measurable end-to-end improvement is demonstrated, label the performance objective unmet; never attribute native compilation gains to faster transparent emulation.

### S7 — close and prepare release artifacts (medium; S6 local work)

Own final docs, `docs/evidence/arm64-build.md`, `docs/decisions.md`, `docs/third-party.md` if build-only materials change, relevant release instructions, and necessary `.github/workflows/release.yml` adjustments to consume the qualified cross path. Preserve the existing dispatch-only publication and static ELF/checksum gates. Do not dispatch it.

Run final workspace tests, complete ARM64 build runner, existing native Linux/e2e/API conformance relevant to touched code, and available macOS checks at this milestone. Preserve missing-platform proofs under Needs environment. Audit suspect legacy argument scans/toolchain paths and remove only ones with no remaining code/script/doc consumers; retain the Rosetta x86 emulator exception on its supported environment.

Build final AMD64 and ARM64 Linux ctrs/ctrs-init with the qualified native toolchain; verify both static musl artifacts, architecture, version, checksums, and actual AMD64 startup/build behavior. ARM64 execution on AMD64 is emulator evidence, not native hardware proof. Prepare the existing release artifact manifest locally. Include dependency/emulator provenance and legal materials required for what is actually redistributed; no separate emulator bundle is planned.

Run the installed `ultrareview` procedure within the granted review authority, fix P1/P2 findings, and repeat only affected proofs. If a required review route is unavailable, record it as an open qualification gate. Retire only completed campaign worktrees under the orchestrate lifecycle; preserve parked branches/evidence.

Acceptance: `bash tests/arm64-build.sh --all` plus `cargo test --workspace` and verified local release manifest/checksums. Commit the concise report with working paths, actual versions/digests, commands, benchmark verdict, compatibility limits, commits/artifacts, and outstanding environment/release gates. Local completion may retain explicit Needs environment items; feature verification and release claims require their applicable proofs. No published artifact reference exists until a separately authorized publication actually succeeds.

## Acceptance and commands

The runner groups above are the acceptance commands to implement, not claims of existing tooling. Their fixtures form the parity register in `docs/evidence/arm64-build.md`: reference behavior/input, expected result or intentional difference, named case/command, and evidence. Use baseline ctrs for native workflows and stable storage/CLI behavior; use the selected upstream BuildKit on identical pinned contexts for foreign execution. Verify errors and side effects, not just output text.

| Deliverable | Proof |
| --- | --- |
| Native AMD64 unchanged; ARM64 musl/glibc shell/child/script execution | `bash tests/arm64-build.sh --case compatibility` through both entry points |
| Desired/actual pin; safe upgrades and ownership; cache/selection preserved | `bash tests/arm64-build.sh --case identity` |
| Pull/build/export/load/inspect/create metadata and failure behavior | `bash tests/arm64-build.sh --case platform` |
| Native Rust/C/C++ compilers, AArch64 static output, target execution | `bash tests/arm64-build.sh --case cross` |
| Cancel/failure/cleanup, concurrent tags, cache reuse, emulator diagnostics | `bash tests/arm64-build.sh --case lifecycle` |
| Equivalent work and honest speed/resource claims | S6 pilot and full measured command |
| Packaged static binaries/checksums; all local checks | S7 commands and local manifest |

Documentation must supply runnable compatibility and cross-compilation commands, including explicit `--platform linux/arm64`, `--builder ctrs-build`, isolated socket/Docker configuration, and single-platform `--load`. Explain buildx default-load when exporting multi-platform OCI output. Include classic API reproduction, active builder/emulator inspection via the existing report, benchmark reproduction, and the Linux default change. No general foreign `docker run`/`exec` support claim follows from build success.

## Needs environment

At execution, replace each conditional row with exact status and recorded evidence; do not erase an unmet requirement.

| Proof | Prerequisite and command | Status (evidence: `docs/evidence/arm64-build.md`) |
| --- | --- | --- |
| AMD64 Linux ctrs runtime | Root-capable isolated Linux namespaces/cgroup environment and explicitly AMD64 artifacts; `BIN="$PWD/target/linux-x86_64/release" bash tests/linux-host.sh` after P0 isolation support | **Passed twice 2026-11-14 (28/28)** on isolated runs: fresh prefix, isolated DOCKER_CONFIG, per-run ports, preserved failure logs; refusal and SIGTERM paths verified |
| No foreign host handlers | Fresh dedicated AMD64 Linux host or proven independent binfmt namespace; `bash tests/arm64-build.sh --case compatibility --require-no-binfmt`; runner must fail closed if any foreign handler can service the test | Unavailable on the baseline host (measured 2026-11-14): one global binfmt_misc instance; a fresh private mount still shows `qemu-aarch64` POCF. The ordinary compatibility case passed (host handler visible; per-backend report in output). `--require-no-binfmt` verified fail-closed (exit 1, no resources created). Handler-free qualification needs a dedicated host or VM, or BuildKit's bundled-emulator argv-wrapping path demonstrated on such an environment |
| macOS regression | Apple Silicon macOS with signing/Virtualization.framework; `cargo test --workspace`, then `CARGO_ENCODED_RUSTFLAGS="" cargo xtask all` and `conformance/smoke.sh` using isolated state | Not available on this host; unverified |
| Performance | Idle AMD64 machine passing both perf-gate checks; `bash bench/arm64-build.sh --samples 5 --all-states` | Unavailable (S6; this host is a loaded workstation, load ~3–19 / 32 cores); unverified |
| Hosted CI result | Separately authorized push/run; local workflow changes and tests do not prove GitHub CI passed | Not authorized by this campaign |
| Actual publication | Separately authorized default-branch release dispatch after all release gates; follow existing release workflow; verify downloaded checksums and artifacts. Do not dispatch from this campaign | Not authorized by this campaign |

## Execution boundary and non-goals

The present request authorizes editing this plan only. A later execution request may authorize source, tests, docs, local fixture resources, local green commits, and release preparation within the boundaries above. It must cover stopped owned-builder replacement before that destructive operation. Otherwise park that proof; never infer permission from the plan itself.

Contract changes to surface in implementation reviews: managed tag now enforces the pin; stale running builders report pending upgrade; additive builder diagnostics distinguish unknown/verified capability; explicit malformed platforms fail; metadata conflicts fail before store publication; Linux build default follows host architecture. Preserve Docker builder-selection state, local Unix socket control, image/store formats, cache volume, and security policy. No migration is planned.

Do not introduce FEX, QEMU full-system VMs, remote-control TCP, mandatory remote ARM builders, host binfmt changes, a general ARM64 runtime, a multi-platform local store, desktop/Kubernetes surfaces, arbitrary Dockerfile translation, unrelated refactors, or global installs. Docker remains build/test tooling, not an engine runtime dependency. ctrs, ctrs-init, BuildKit, and compiler tools execute natively on AMD64 during the required qualification.

“Ship” in the source brief is bounded here to local release preparation: the skill forbids pushing, and publication needs its own authorization. Hardware-dependent and hosted-service proofs remain release requirements, even when local campaign work closes. No performance promise is inferred from correctness or compilation.

## Reference

- [Development](docs/development.md), [architecture](docs/architecture.md), [release evidence](docs/evidence/release.md), and [third-party materials](docs/third-party.md).
- `crates/ctrs/src/builds.rs`: buildx builder provisioning; `buildwith.rs`: user Docker/buildx selection state.
- `crates/ctrs/src/daemon/builder.rs`: pin, managed lifecycle, classic buildctl path, diagnostics, Rosetta emulator hiding.
- `crates/ctrs-image/src/registry.rs`, `store.rs`, `archive.rs`: platform resolution, digest/store identity, archive import/export.
- `crates/ctrs/src/daemon/api.rs`: pull/create/inspect platform boundaries; `crates/ctrs-init/src/linux/`: native runtime security boundary.
- `xtask/src/main.rs`, `Dockerfile`, `.cargo/config.toml`: build architecture/linking; `tests/linux-host.sh`, `tests/e2e.sh`, `conformance/`, `bench/`: existing harnesses.
- [BuildKit multi-platform documentation](https://github.com/moby/buildkit/blob/master/docs/multi-platform.md), [official releases](https://github.com/moby/buildkit/releases), and [xx cross-compilation helpers](https://github.com/tonistiigi/xx). Read the selected release's exact source/recipe when recording provenance; these moving references are not immutable pins.
