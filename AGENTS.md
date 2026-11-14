# AGENTS.md

Router for ctrs development. ctrs is a headless, Docker Engine API
compatible container engine for macOS (Virtualization.framework guest) and
Linux (namespaces/cgroups directly). Keep this file short; detail lives in
`docs/`.

## Commands

```sh
cargo check --workspace            # fast type check
cargo test --workspace             # unit/integration suite
conformance/smoke.sh               # engine round-trip (boots the VM)
conformance/run.sh                 # API conformance fixtures (plan runner)
tests/e2e.sh                      # Docker CLI e2e against a running engine
CARGO_ENCODED_RUSTFLAGS="" cargo xtask all   # guest assets + signed host binary
```

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
| Dated slice decisions (append-only) | `docs/decisions.md` |
| Measurement evidence | `docs/evidence/` |
| Experiments (smolvm, microVM) | `docs/experiments/` |
| Remaining campaign slices (CTRS-22/23) | `docs/campaign-headless-ctrs.md` |
