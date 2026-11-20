Prefix: DSLP
Next: 12

Deslop campaign backlog ([plan](https://github.com/laputa-systems/stuff/blob/main/docs/campaigns/deslop.md), tier C). One agent works this file with the `deslop` skill: take the lowest-numbered open ticket whose area does not start with `Needs owner ·`. After DSLP-5, work the open P1 and P2 findings, then fill in `## Report` below.

## Report

Ground (DSLP-1, base ddaf012): code lines Rust 34.6k (`ctrs` 24k, `ctrs-init` 12k, `ctrs-image` 3.5k, `ctrs-proto` 1.5k), Python 23.8k (`bench/native`); no vendored trees. `make test` (new Makefile target, run by CI `macos` on pull requests) exits 0: cold 4m41s, warm 50s-1m52s on a busy host (observations only; the global `kache` rustc wrapper makes cold partial). `make lint` is red in `crates/ctrs` (DSLP-6). Fixed with obvious causes: bench tests that assumed their working directory (`test_w12.py`) or a quiet disk (`test_resource_cells.py`), two clippy sites in `ctrs-image`. Linux-only and privileged checks are Needs environment; the unit-level ones run in CI `linux-musl`.

Diagnose (DSLP-2): reviewed layer and `docker cp` extraction, host archive load, whiteout and symlink handling; process lifecycle and container setup were not reviewed in depth. Filed DSLP-7 (P1, reproduced in a Linux container): the xattr call after layer extraction follows a symlink. The path checks themselves held for symlink parents, symlink-then-file, hardlink-to-outside-then-file and symlink-then-directory entries.

Types (DSLP-3): clippy candidate scan exited 0 with 28 wildcard-enum, 20 redundant-clone, 39 needless-pass-by-value, 636 unwrap/expect (including test targets), and numerous cast warnings; no rule adopted without a verified defect witness. The single-variant wildcard candidate produced no diagnostic. Ruff 0.17.5 reported 2,855 diagnostics across ANN, ANN401, PGH003, TC, B and RET (2,727 ANN, 122 B, 6 RET); no candidate adopted. ty 0.0.104 reported 400 diagnostics with the three proposed rules enabled; 13 were unsound-return and 104 missing-type-argument or unused-ignore diagnostics. These are leads, not verified defects. Rust escape-hatch matching lines: 1,276; Python: 0 (the literal scan is a lower bound). Linux-only ctrs-init was not checked by the macOS clippy run. The separate unsafe-code candidate scan produced 99 diagnostics on macOS and was not adopted. No type contracts or escape hatches changed.

Tests (DSLP-4): finite boundary inventory: CLI delegation is guarded by `docker::tests::delegates_argv_and_env_to_a_stub_docker`, but flag/exit semantics lack an engine e2e run; HTTP/API by `daemon::api` and `daemon::http` units, full conformance needs a running engine; `vm.json` by its round-trip test, image records and archives by store/archive tests, container records have no direct test; host/guest wire by round-trip and malformed-input tests; extraction and isolation by Linux-only ctrs-init tests, Needs environment on macOS. Benchmark manifest, parsing, pairing and safety have offline Python tests. Conformance selection had a false pass: an unmatched selector returned 0; the new test failed against that fault and passes after the runner returns 1. The cross-compiled Linux test binary passed all 78 tests in a root container using tmpfs; a first run on the macOS-shared mount failed the xattr case because that filesystem did not retain the capability xattr. Engine e2e remains Needs environment. Coverage and mutation were not run: the requested scope excludes a mutation lane and cargo-llvm-cov is unavailable.

Dead code (DSLP-5): `cargo rustc` force-warn scans exited 0 on macOS for all five crates: ctrs has 469 unreachable-public visibility warnings and one `parse_release` warning (used by Linux kernel-version handling); ctrs-image has 9 and ctrs-proto 52 unreachable-public warnings; ctrs-init and ctrs-vmm have none on this target. Visibility warnings are retained: the items are reachable inside private modules (including protocol frame constants); narrowing visibility is not dead-code removal. The ARM64 Linux scan also reported 251 unreachable-public warnings and 25 dead-code warning groups, concentrated in the unused typed firewall policy; its optional build feature is retained pending DSLP-11. Ruff F401/F811/F841 found 15 unused imports or bindings; 13 removed while retaining the side-effecting registry call. Two unused fixture imports remain allowlisted to preserve fixture identity and performance comparability. Entrypoints are the native harness, diagnostics and fixtures; `make test` passed with the candidate. `cargo-machete` and debloat are Needs environment. No dependency removed.

Bench (DSLP-9): the existing pyramid has Edit, Change, Scenario and Full tiers and explicit preflight. Edit passed both harness tests and manifest validation; W1 Change preflight passed after building the signed host, initramfs, kernel and disk. A case-insensitive scratch directory collided kernel headers; a case-sensitive worktree-local APFS image fixed the build. The final `perf-gate-ready` returned 75 on a busy host, so the timed Change workload is deferred and the ticket remains open. No Full workload was run.

## Tickets

### DSLP-9 · P2 · Bench: audit and prove the pyramid

- **Area:** deslop · bench
- **Where:** bench/native/pyramid.py
- **Problem:** Edit passed and W1 Change preflight passes after building host, initramfs, kernel and disk, but perf-gate-ready exits 75 on the busy host, so no timed Change run is qualified.
- **Recommendation:** When perf-gate-ready exits 0, run python3.14 bench/native/pyramid.py run --tier change --name w1-stack, check the gate again immediately after, and close only if the run and gate pass.
- **Fix with:** deslop
- **Effort:** M

### DSLP-6 · P3 · make lint is red: 51 clippy errors in crates/ctrs

- **Area:** deslop · ground
- **Where:** crates/ctrs/src/daemon/{engine,api,ports,mirror,buildgrpc,proxy,builder}.rs, builds.rs, guest.rs, service.rs, diag/report.rs
- **Problem:** At base ddaf012 `make lint` (clippy --workspace --all-targets -D warnings, nightly-2026-11-09) fails in `ctrs` (bin) with 50 errors, 51 in its test build: 35 collapsible_if (edition 2024 let chains), 6 type_complexity, 2 too_many_arguments (8/7), and one each of single_match-class, useless_format, unnecessary_lazy_evaluations, needless_borrows_for_generic_args, redundant_closure, manual_range_contains, print_literal, unnecessary_cast, double_ended_iterator_last. Ground fixed the two sites in ctrs-image (a single_match in archive.rs and an unused test variable in registry.rs); ctrs-proto, ctrs-vmm, xtask and Linux ctrs-init (checked in a rust:1.100.0-bookworm container) are clean. CI does not run clippy, so nothing gates it.
- **Recommendation:** Apply the machine-fixable lints with `cargo clippy --fix` per file and review each diff (let-chain collapses must keep evaluation order); give the six complex types names and the two eight-argument functions a parameter struct or a reasoned allow. Accept: `make lint` exits 0, `make test` unchanged. Then decide whether CI should run `make lint`.
- **Fix with:** deslop
- **Effort:** M

### DSLP-8 · P3 · ARM64 qualification platform case fails under emulation

- **Area:** Needs environment · ARM64 qualification
- **Where:** .github/workflows/ci.yml ARM64 qualification job; tests/arm64-build.sh --case platform
- **Problem:** After fixing the job's --case arguments (PR #7), the AMD64-to-ARM64 qualification runner executes its cases on the hosted runner. The platform case fails ("MISS platform case failed", logs under .work/tmp/qemu-accel/isolated-ctrs-platform-*) right after the multi-platform OCI load check. The job was already red on main (argument parsing), so this case had never run in CI. The other qualification cases (arch refusal, build scripts not emulated, failed pull surfaced) pass. Run 44770575746.
- **Recommendation:** Download the preserved failure logs from a rerun with an artifact upload, or reproduce with tests/arm64-build.sh --case platform on an x86-64 Linux host with QEMU binfmt, then fix the case or the runner.
- **Fix with:** root-cause
- **Effort:** M

### DSLP-10 · P3 · Kache hashes the sparse guest disk during Rust builds

- **Area:** Needs environment · build wrapper
- **Where:** guest/out/data.img; kache rustc wrapper
- **Problem:** After cargo xtask disk creates a 1 TiB sparse image, kache reads it during an unrelated ctrs-proto compilation, delaying the build; lsof showed the wrapper reading guest/out/data.img.
- **Recommendation:** Exclude generated guest assets from the wrapper input walk; restore the disk before running the engine.
- **Fix with:** root-cause
- **Effort:** S

### DSLP-11 · P3 · Decide the unused firewall policy and optional backend

- **Area:** Needs owner · firewall feature
- **Where:** crates/ctrs-init/src/linux/firewall.rs; crates/ctrs-init/Cargo.toml
- **Problem:** The Linux force-warn scan reports the typed firewall policy and transaction API unused by production; its crabtables backend is feature gated and used by its own tests. The live networking path uses netlink.rs.
- **Recommendation:** Decide whether to wire the optional backend into production or remove the feature and policy together; preserve the existing build feature until that decision.
- **Fix with:** dead-code-archaeology
- **Effort:** M
