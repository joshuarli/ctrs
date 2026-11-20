Prefix: DSLP
Next: 8

Deslop campaign backlog ([plan](https://github.com/laputa-systems/stuff/blob/main/docs/campaigns/deslop.md), tier C). One agent works this file with the `deslop` skill: take the lowest-numbered open ticket whose area does not start with `Needs owner ·`. After DSLP-5, work the open P1 and P2 findings, then fill in `## Report` below.

## Report

Ground (DSLP-1, base ddaf012): code lines Rust 34.6k (`ctrs` 24k, `ctrs-init` 12k, `ctrs-image` 3.5k, `ctrs-proto` 1.5k), Python 23.8k (`bench/native`); no vendored trees. `make test` (new Makefile target, run by CI `macos` on pull requests) exits 0: cold 4m41s, warm 50s-1m52s on a busy host (observations only; the global `kache` rustc wrapper makes cold partial). `make lint` is red in `crates/ctrs` (DSLP-6). Fixed with obvious causes: bench tests that assumed their working directory (`test_w12.py`) or a quiet disk (`test_resource_cells.py`), two clippy sites in `ctrs-image`. Linux-only and privileged checks are Needs environment; the unit-level ones run in CI `linux-musl`.

Diagnose (DSLP-2): reviewed layer and `docker cp` extraction, host archive load, whiteout and symlink handling; process lifecycle and container setup were not reviewed in depth. Filed DSLP-7 (P1, reproduced in a Linux container): the xattr call after layer extraction follows a symlink. The path checks themselves held for symlink parents, symlink-then-file, hardlink-to-outside-then-file and symlink-then-directory entries.

## Tickets

### DSLP-7 · P1 · A pulled layer can set xattrs on files outside the layer through a symlink entry

- **Area:** deslop · diagnose
- **Where:** crates/ctrs-init/src/linux/layers.rs:264-266 and 292-299 (untar, set_pax_xattr); same helper at crates/ctrs-init/src/linux/copy.rs:186-188
- **Problem:** Confirmed by reproduction. `untar` unpacks each entry with `unpack_in` (which refuses `..`, absolute paths and symlinked parents), then applies the entry's `SCHILY.xattr.*` pax records with `setxattr(2)`, which follows a symlink at the final component. A layer holding a symlink entry `link -> /any/host/file` (absolute, or `../..` relative, since the unpack directory is `<layers>/.tmp-<hex>`) preceded by a pax header `SCHILY.xattr.security.capability=<vfs cap blob>` makes the agent set that xattr on the link's target. `pax_xattrs` allows the `user.`, `trusted.`, `security.` and `system.` namespaces, so an image can write file capabilities (a local privilege escalation on a host binary; `security.capability` and `user.*` demonstrated below) on any file the agent can reach; `system.posix_acl_*` and `trusted.*` pass the same filter and were not exercised. The agent runs as root and, on Linux (no VM, `ctrs-init` on the host kernel; docs/architecture.md), that is the host filesystem; on macOS the target is the guest VM's own filesystem, inside the VM boundary. Evidence: a test copied from `layers::tests` into a scratch workspace (copy of crates/ctrs-init and ctrs-proto, Cargo.lock from the repo) built a tar with `PaxHeader.0/link` (`SCHILY.xattr.security.capability` = 20-byte VFS_CAP_REVISION_2 blob granting CAP_SETUID) followed by symlink `link -> /tmp/ctrs-layers-xattr-outside-N/victim`, called `untar` and read `victim` back with `lgetxattr`. Run in `rust:1.100.0-bookworm` (linux/arm64, root, overlayfs): `untar` returned Ok(0) and `victim` carried `security.capability` = [1,0,0,2,128,0,0,0,...] (the same with `user.pwned` on the same setup). Controls in the same harness: symlink-then-file `l`, hardlink-to-outside-then-file `h`, symlink-then-directory `d/` and symlink-parent `x/f` entries all stay confined (tar-rs refuses them: victim content and directory mode unchanged), so only the xattr call escapes. `copy_in` (docker cp) uses the same helper but runs chrooted into the container, so its targets stay inside the container root; the archive there also comes from the trusted host, so it is not part of the exposure.
- **Recommendation:** Apply layer and docker-cp xattrs with `lsetxattr` (no follow) so a symlink entry only ever labels the link itself, or skip xattrs on symlink entries; keep best-effort semantics. Add a Linux regression test next to `pax_xattrs_filtered_to_linux_namespaces` that unpacks a symlink entry with a `user.*` and a `security.capability` pax record aimed at a file outside the layer and asserts the target has no such xattr (it fails before the change: record the failing run), run by CI `linux-musl`. Update the confinement claim in docs/security.md (guest agent section). Accept: the test fails at base and passes after; `make test` unchanged; the Linux host proof (`tests/linux-host.sh`) is Needs environment.
- **Fix with:** os-boundaries
- **Effort:** S

### DSLP-3 · P2 · Types: strict profile and typing findings

- **Area:** deslop · types
- **Where:** type checker and lint configuration; Rust/Python sources
- **Problem:** The strict-profile candidates in the deslop skill's tools reference have not been measured here.
- **Recommendation:** Run the deslop Types step. Accept: clean at the adopted profile, escape hatches not increased, witnesses recorded.
- **Fix with:** deslop
- **Effort:** M

### DSLP-4 · P2 · Tests: coverage, boundary gaps, mutation

- **Area:** deslop · tests
- **Where:** test suites and CI
- **Problem:** Coverage and mutation results are unmeasured; no deslop mutation lane exists.
- **Recommendation:** Run the deslop Tests step. Accept: no undispositioned survivor in critical code, the test cost budget holds, and the lane is green where the tools are mirrored.
- **Fix with:** deslop
- **Effort:** L

### DSLP-5 · P2 · Dead code: tools and debloat

- **Area:** deslop · dead code
- **Where:** whole repository
- **Problem:** No dead-code scan has run.
- **Recommendation:** Run the deslop Dead code step. Accept: tools clean or allowlisted with reasons; walk-backs filed as Needs owner tickets.
- **Fix with:** deslop
- **Effort:** M

### DSLP-6 · P3 · make lint is red: 51 clippy errors in crates/ctrs

- **Area:** deslop · ground
- **Where:** crates/ctrs/src/daemon/{engine,api,ports,mirror,buildgrpc,proxy,builder}.rs, builds.rs, guest.rs, service.rs, diag/report.rs
- **Problem:** At base ddaf012 `make lint` (clippy --workspace --all-targets -D warnings, nightly-2026-11-09) fails in `ctrs` (bin) with 50 errors, 51 in its test build: 35 collapsible_if (edition 2024 let chains), 6 type_complexity, 2 too_many_arguments (8/7), and one each of single_match-class, useless_format, unnecessary_lazy_evaluations, needless_borrows_for_generic_args, redundant_closure, manual_range_contains, print_literal, unnecessary_cast, double_ended_iterator_last. Ground fixed the two sites in ctrs-image (a single_match in archive.rs and an unused test variable in registry.rs); ctrs-proto, ctrs-vmm, xtask and Linux ctrs-init (checked in a rust:1.100.0-bookworm container) are clean. CI does not run clippy, so nothing gates it.
- **Recommendation:** Apply the machine-fixable lints with `cargo clippy --fix` per file and review each diff (let-chain collapses must keep evaluation order); give the six complex types names and the two eight-argument functions a parameter struct or a reasoned allow. Accept: `make lint` exits 0, `make test` unchanged. Then decide whether CI should run `make lint`.
- **Fix with:** deslop
- **Effort:** M

