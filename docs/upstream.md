# Upstream: Kiri import record

- **Upstream:** https://github.com/libracoder/kiri
- **Pinned commit:** `99b63c07fc003d3dcd8e03c76891ba747b5c984f` ("UI: Settings → Appearance", 2026-11-14T01:03:20Z)
- **Imported:** 2026-11-13, as the initial ctrs commit after `eda9170` (see CTRS-01; preflight `bfff994`).
- **Method:** file-tree copy of the pinned snapshot. No `.git`, no submodule, no history join. Verification at import: `diff -r` against a fresh `git fetch --depth 1 <sha>` checkout matches except the files listed under *Exclusions* and the ctrs `README.md`.
- **Pins are immutable.** Re-pinning is a deliberate, recorded decision here, never incidental.

## Exclusion manifest

Everything upstream at the pin is imported except:

| Path | Why |
| --- | --- |
| `.github/` (7 files: two issue templates + feature template + PULL_REQUEST_TEMPLATE.md + workflows codeql/perf/ui-tests) | Upstream CI proves nothing at runtime and could auto-run on this public repo. |
| `scripts/__pycache__/ui-test.cpython-315.pyc` | Committed bytecode; not source. |
| `.git/` | Never imported (method). |

`git ls-files` after import = upstream tree − those exclusions. Any other deviation is a bug: file its own commit.

## What upstream is, at this pin

- Workspace: `crates/{kiri,kiri-init,kiri-proto,kiri-vmm,kiri-image,kiri-win,kiri-share-proto}` + `xtask`; edition 2024; release profile `lto="fat"`, `codegen-units=1`, `panic="abort"`. Identifiers were renamed to `ctrs*` in the CTRS-23 rebrand (see `docs/decisions.md`).
- Guest agent: `crates/kiri-init`, target `aarch64-unknown-linux-musl` (rust-lld); runs as root in the guest (and on a Linux host); hand-encodes rtnetlink + nf_tables in `src/linux/netlink.rs` (no `nft`/`ip` helpers required at runtime).
- Host VMM: `crates/kiri-vmm` — `apple.rs` (macOS, Virtualization.framework; builds `VZNATNetworkDeviceAttachment`, see `apple.rs:443`) and `process.rs` (Linux native; agent as a root child, vsock→unix sockets in `/run`).
- Image/OCI: `crates/kiri-image`, registry client is `h12tiny-client-sync` (CTRS-16 pilot found it slower than the incumbent; the owner overrode the verdict 2026-11-14 and ordered h12tiny everywhere, with the feature work to close the perf gap in laputa-systems/smolith).
- Docker Engine API 1.47 over a local Unix socket: `crates/kiri/src/daemon/http.rs` hand-writes HTTP/1.1 (chunked, upgrades for `attach`; API version `1.47`).
- `kiri run`/`ps`/… delegate to the external `docker` CLI against Kiri's socket (`crates/kiri/src/docker.rs`); the engine itself is the daemon. Not to be described as Docker-independent.
- `tests/e2e.sh` expects a `kiri` docker context and a `~/Kiri` Finder folder (both absent in the headless fork; adapted in CTRS-08). `tests/linux-host.sh` requires a Linux host (Needs environment N-1).
- Guest kernel: `6.18.58` (see `guest/kernel/build.sh`), uncompressed arm64 `Image`, patches `guest/kernel/patches/000{1..4}-*.patch`, config `guest/kernel/kiri.config` at the pin, `guest/kernel/ctrs.config` after the CTRS-23 rebrand; GPL-2.0-only; source offer in `guest/kernel/SOURCE_OFFER.md`. macOS boot asset TBD in CTRS-03 (built via `cargo xtask kernel`, which needs a container engine; allowed via Decision O2 in `docs/campaign-headless-ctrs.md` only for that build).
- `docs/features.md` ("What works") is the parity oracle.
- Known pre-existing red at import: `dead_code` warning `parse_ipam` at `crates/kiri/src/daemon/network.rs:472`.

## Third-party inventory (host engine, after Cargo.lock resolution)

150 locked packages (`Cargo.lock`); license histogram (via `cargo metadata`): 89× `MIT OR Apache-2.0`, 21× `MIT`, 8× `Apache-2.0 OR MIT`, 8× `Apache-2.0`, 6× `Zlib OR Apache-2.0 OR MIT`, 4× `MIT/Apache-2.0`, 3× `Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT`, 2× `ISC`, and one each of 0BSD/MIT/Apache-2.0, Unlicense/MIT, MIT/Zlib/Apache-2.0, Apache-2.0 AND ISC, Apache-2.0/ISC/MIT, BSD-3-Clause, Unicode-3.0 AND MIT/Apache-2.0, CDLA-Permissive-2.0, Zlib. **No GPL/LGPL enters the host engine.** The guest Linux kernel is a separate GPL-2.0-only work (see above). `NOTICE` carries the upstream texts; new ctrs code is `Copyright 2026 Laputa Systems`, Apache-2.0.

## Evaluating upstream security fixes

1. Do not float the pin. When a Kiri security advisory or release appears, compare `main`/tags against this pin by reading the diff; record the candidate bump in this file with date, SHA, and reason.
2. Re-run the exclusion manifest and `cargo tree` diff for a candidate; adopt only deliberate fixes (own commits) or a deliberate full bump.
3. `cargo audit` per milestone (installed); unreviewed advisories are listed in `docs/decisions.md`, never silently ignored.
4. Trademarks: Kiri's name and logo are not Apache-2.0 and never ship in ctrs distributions. The CTRS-23 rebrand has removed upstream identifiers from the tree; attribution to Kiri remains only in legal notices (`NOTICE`), this file, and the parity oracle (`docs/features.md`).
