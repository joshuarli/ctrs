Prefix: CTRS
Next: 17
### CTRS-11 · P2 · Bench: audit and prove the pyramid

- **Area:** bench
- **Where:** bench/native/pyramid.py
- **Problem:** Edit passed and W1 Change preflight passes after building host, initramfs, kernel and disk, but perf-gate-ready exits 75 on the busy host, so no timed Change run is qualified.
- **Recommendation:** When perf-gate-ready exits 0, run python3.14 bench/native/pyramid.py run --tier change --name w1-stack, check the gate again immediately after, and close only if the run and gate pass.
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

### CTRS-16 · P3 · Pin the guest kernel source and bench inputs in sources.lock.json

- **Area:** build inputs
- **Where:** guest/kernel/build.sh:19, scripts/ci/kernel-source.sh:15, bench/native/assets.lock (`w6_zlib`, `w7_httpie`), bench/install-ubuntu.sh
- **Problem:** The guest kernel tarball (`linux-6.18.58.tar.xz`) is downloaded with no checksum by both the kernel build and the release source-archive step, and its version lives only in `build.sh`. Bench source inputs keep their own pins in `assets.lock` and shell `fetch_verified` calls. `sources.lock.json` and laputa-buildlib now pin the development tools only.
- **Recommendation:** Add the kernel tarball (version, URL, sha256, size, `license: GPL-2.0-only`) to `sources.lock.json`. Fetch it on the host with `buildlib.locks.fetch_input` and mount it into the kernel build container, and read KVER from the lock in `build.sh` and `kernel-source.sh`. Move the bench source pins the same way. Accept: `cargo xtask kernel` and the release workflow's source archive build from the verified tarball, and a corrupted tarball fails with buildlib's size or hash error. The release workflow changes need the owner's go-ahead.
- **Fix with:** single-source-of-truth
- **Effort:** M
