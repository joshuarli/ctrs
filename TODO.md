Prefix: CTRS
Next: 16
### CTRS-11 · P2 · Bench: audit and prove the pyramid

- **Area:** bench
- **Where:** bench/native/pyramid.py
- **Problem:** Edit passed and W1 Change preflight passes after building host, initramfs, kernel and disk, but perf-gate-ready exits 75 on the busy host, so no timed Change run is qualified.
- **Recommendation:** When perf-gate-ready exits 0, run python3.14 bench/native/pyramid.py run --tier change --name w1-stack, check the gate again immediately after, and close only if the run and gate pass.
- **Fix with:** deslop
- **Effort:** M

### CTRS-12 · P3 · make lint is red: 51 clippy errors in crates/ctrs

- **Area:** ground
- **Where:** crates/ctrs/src/daemon/{engine,api,ports,mirror,buildgrpc,proxy,builder}.rs, builds.rs, guest.rs, service.rs, diag/report.rs
- **Problem:** At base ddaf012 `make lint` (clippy --workspace --all-targets -D warnings, nightly-2026-11-09) fails in `ctrs` (bin) with 50 errors, 51 in its test build: 35 collapsible_if (edition 2024 let chains), 6 type_complexity, 2 too_many_arguments (8/7), and one each of single_match-class, useless_format, unnecessary_lazy_evaluations, needless_borrows_for_generic_args, redundant_closure, manual_range_contains, print_literal, unnecessary_cast, double_ended_iterator_last. Ground fixed the two sites in ctrs-image (a single_match in archive.rs and an unused test variable in registry.rs); ctrs-proto, ctrs-vmm, xtask and Linux ctrs-init (checked in a rust:1.100.0-bookworm container) are clean. CI does not run clippy, so nothing gates it.
- **Recommendation:** Apply the machine-fixable lints with `cargo clippy --fix` per file and review each diff (let-chain collapses must keep evaluation order); give the six complex types names and the two eight-argument functions a parameter struct or a reasoned allow. Accept: `make lint` exits 0, `make test` unchanged. Then decide whether CI should run `make lint`.
- **Fix with:** deslop
- **Effort:** M

### CTRS-13 · P3 · ARM64 qualification platform case fails under emulation

- **Area:** Needs environment · ARM64 qualification
- **Where:** .github/workflows/ci.yml ARM64 qualification job; tests/arm64-build.sh --case platform
- **Problem:** After fixing the job's --case arguments (PR #7), the AMD64-to-ARM64 qualification runner executes its cases on the hosted runner. The platform case fails ("MISS platform case failed", logs under .work/tmp/qemu-accel/isolated-ctrs-platform-*) right after the multi-platform OCI load check. The job was already red on main (argument parsing), so this case had never run in CI. The other qualification cases (arch refusal, build scripts not emulated, failed pull surfaced) pass. Run 44770575746.
- **Recommendation:** Download the preserved failure logs from a rerun with an artifact upload, or reproduce with tests/arm64-build.sh --case platform on an x86-64 Linux host with QEMU binfmt, then fix the case or the runner.
- **Fix with:** root-cause
- **Effort:** M

### CTRS-14 · P3 · Kache hashes the sparse guest disk during Rust builds

- **Area:** Needs environment · build wrapper
- **Where:** guest/out/data.img; kache rustc wrapper
- **Problem:** After cargo xtask disk creates a 1 TiB sparse image, kache reads it during an unrelated ctrs-proto compilation, delaying the build; lsof showed the wrapper reading guest/out/data.img.
- **Recommendation:** Exclude generated guest assets from the wrapper input walk; restore the disk before running the engine.
- **Fix with:** root-cause
- **Effort:** S

### CTRS-15 · P3 · Decide the unused firewall policy and optional backend

- **Area:** Needs owner · firewall feature
- **Where:** crates/ctrs-init/src/linux/firewall.rs; crates/ctrs-init/Cargo.toml
- **Problem:** The Linux force-warn scan reports the typed firewall policy and transaction API unused by production; its crabtables backend is feature gated and used by its own tests. The live networking path uses netlink.rs.
- **Recommendation:** Decide whether to wire the optional backend into production or remove the feature and policy together; preserve the existing build feature until that decision.
- **Fix with:** dead-code-archaeology
- **Effort:** M
