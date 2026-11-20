# AGENTS.md

Router for ctrs development. ctrs is a headless, Docker Engine API
compatible container engine for macOS (Virtualization.framework guest) and
Linux (namespaces/cgroups directly). Keep this file short; detail lives in
`docs/`.

## Active performance campaign

For performance/hillclimb work, first read
`docs/campaign-native-performance.md` and
`docs/native-performance-progress.md`, then execute the saved next action.
The current lane is native ARM64 macOS versus OrbStack. Healthy soak/watch
counters are not progress: do not repeat monitoring turns or stop at an
arbitrary candidate count. Persist an exact continuation before an external
turn limit; the campaign remains active until its measured gates pass.

## Commands

```sh
cargo check --workspace            # fast type check
cargo test --workspace             # unit/integration suite
conformance/smoke.sh               # engine round-trip (boots the VM)
conformance/run.sh                 # API conformance fixtures (plan runner)
tests/e2e.sh                      # Docker CLI e2e against a running engine
CARGO_ENCODED_RUSTFLAGS="" cargo xtask all   # guest assets + signed host binary
```

## Verification

- `make test` = `make test-rust` (workspace `--lib --tests`) + `make test-bench` (benchmark manifest
  and Python unittest discovery, 398 tests); CI runs it in `macos` (PRs). Costs on a busy M-series
  Mac (load 14-24): cold 4m41s, warm 50s-1m52s; the Python half about 40s. ctrs-init is
  Linux-only, so macOS runs 0 of its ~80 tests: CI `linux-musl` (x86_64, ARM64) runs them as root.
- `make lint` (clippy, all targets, `-D warnings`): red at base, 51 errors in `crates/ctrs`
  (DSLP-6); the other crates and Linux ctrs-init are clean. 28s warm. CI does not run it.
- CLI flags and exit codes: none (`docker::tests::delegates_argv_and_env_to_a_stub_docker` covers
  delegation only). API: `daemon::api` and `daemon::http` unit tests; `conformance/run.sh` and
  `tests/e2e.sh` need a running engine (Needs environment; no CI job).
- `vm.json`: `config::tests::vm_json_round_trip`. Image records, blobs, archives: `ctrs-image`
  store and archive tests. Container records: none.
- Host/guest wire: `ctrs-proto::tests::round_trip`, `rejects_oversized_unknown_and_truncated`.
- Layer and `docker cp` extraction, isolation: `ctrs-init` `layers::tests` and `copy`/`inroot`
  tests (CI `linux-musl`). Privileged `tests/linux-host.sh`, `tests/kernel-features.sh`,
  `conformance/smoke.sh`, `isolation.sh`, `seccomp`: Needs environment (VM or privileged
  Linux container; no CI job). `arm64-compat` (QEMU) runs `tests/arm64-build.sh` cases.
- Performance: `bench/native/pyramid.py` (`check`, `run --tier edit|change`) over the workloads in
  `docs/campaign-native-performance.md`; hot paths are container lifecycle, image pull and bind IO.
  Scenario and full tiers need a named workload and an engine.
- Components (Rust lines): `ctrs` 24k host API/CLI/daemon, `ctrs-init` 12k Linux agent and runtime,
  `ctrs-image` 3.5k registry and store, `ctrs-proto` 1.5k wire, `ctrs-vmm` 0.8k, `xtask` 0.5k.
  Python: `bench/native` 24k. Vendored trees: none.

## Hard invariants

- Local Unix socket only; no remote TCP control plane.
- `ctrs run`/`ps`/… delegate to the external `docker` CLI with
  `DOCKER_CONTEXT` stripped; nothing in the tree creates or edits a docker
  context.
- macOS: ad-hoc signed binary with the
  `com.apple.security.virtualization` entitlement. Linux: agent runs as
  root on the host kernel. No QEMU/runc/dockerd dependency.
- On-disk formats (`vm.json`, image/container records) and the host↔guest
  wire protocol are stable contracts.
- Apache-2.0; the guest kernel is a separate GPL-2.0-only work.
- No desktop window, menu-bar app, updater, or Kubernetes surface — these
  were deliberately deleted and must not return.

## Map

| Topic | Doc |
| --- | --- |
| Build, run, layout, verification | `docs/development.md` |
| Code map, delegation audit, verification map | `docs/architecture.md` |
| Guest firewall (nftables) semantics and fixtures | `docs/firewall.md` |
| Threat model, seccomp differential, failure harness | `docs/security.md` |
| Optional launchd user service | `docs/launchd.md` |
| Install, uninstall | `docs/install.md` |
| Third-party SBOM (default build + feature-gated) | `docs/third-party.md` |
| Dated slice decisions (append-only) | `docs/decisions.md` |
| Campaign record (complete; CTRS-22/23 done) | `docs/campaign-headless-ctrs.md` |
| macOS OrbStack performance hillclimb (current contract) | `docs/campaign-native-performance.md` |
| Performance work queue and continuation checkpoint | `docs/native-performance-progress.md` |
| Performance acceptance matrix (status per cell) | `docs/native-acceptance-matrix.md` |
| Docker-driver buildx design (W6/W7 gap) | `docs/buildkit-driver.md` |
| Bind-mount change-notification design (proposal) | `docs/design-bind-notify.md` |
| Evidence: firewall qualification | `docs/evidence/crabtables.md` |
| Evidence: gate B | `docs/evidence/gate-b.md` |
| Evidence: h12tiny HTTP pilot | `docs/evidence/http.md` |
| Evidence: networking/vzNAT | `docs/evidence/net.md` |
| Evidence: registry client pilot | `docs/evidence/registry.md` |
| Evidence: security qualification | `docs/evidence/security.md` |
| Campaign closeout (Gate J, local) | `docs/evidence/closeout.md` |
| Release prep (artifact manifest) | `docs/evidence/release.md` |
| Experiment: smolvm-network analysis | `docs/experiments/smolvm-network.md` |
| Experiment: microVM isolation research | `docs/experiments/microvm-isolation.md` |
