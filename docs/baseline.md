# Baseline — unmodified upstream import at the pin

Measured 2026-11-13 on macOS 27.2 (Apple Silicon), rustc 1.99.1 stable. Commands are given with each number; raw logs are in `.work/tmp/` (not committed).

## Pinned inputs

- Snapshot: Kiri `99b63c07fc003d3dcd8e03c76891ba747b5c984f` (see `docs/upstream.md`).
- Workspace: `cargo metadata --no-deps` OK. `Cargo.lock` resolved to 150 packages, 183 lines of `cargo tree --locked` output at the pin; after CTRS-06/07 deletions, 81 crate dependencies remain and the GTK/Share graph is gone.
- Known red at import (pre-existing, `cargo check --workspace`): one warning — dead code `parse_ipam`, `crates/kiri/src/daemon/network.rs:472`. **Deleted in CTRS-07** (`#[cfg(test)]` only); `cargo check --workspace` is now warning-free.

## Loop timings (recorded, not gating until parity work lands)

| Command | Result | Wall |
| --- | --- | --- |
| fetch + checkout at pin (`--depth 1`) | ok | ~2 s |
| `cargo check --workspace` | ok (1 warning above) | 13.98 s |
| `cargo test --workspace` | **exit 0 — 359 tests passed, 12 suites, 0 failed** | 57 s |
| `cargo build --release -p kiri` | ok; binary 13,187,664 bytes (~12.6 MiB) at the pin; post-CTRS-07 release size recorded at CTRS-22 | 69 s |

Follow-up commits: `b96e7e3` bumps rustix 1.1.5 → 1.1.6 (RUSTSEC-2026-0486); `cargo audit` afterwards reports only the two GTK-side advisories deleted in CTRS-07.

## Guest boot assets (CTRS-03, 2026-11-13)

`cargo xtask guest` (initramfs), `cargo xtask kernel` (kernel 6.18.58, patches 0001–0004, `allnoconfig` with `kiri.config`) and `cargo xtask disk` (sparse data disk):

| Artifact | Size | sha256 |
| --- | --- | --- |
| `guest/out/Image` (arm64, uncompressed) | 18,800,648 | `9366868ebefe668e22d9c6272fa0f42ff8c65895ff64a61c973642a914a33176` |
| `guest/out/initramfs.cpio` | 1,641,148 | `1c7da0308ac061b73415f240b8c56bc56d520253505e8679ec0788b49be4f7e1` |
| `guest/out/data.img` (sparse 64 GiB) | 68719476736 logical | `84214422e1abe985a279715fee101231c26e4a10ce8c7101f6eac67ff42ca824` |
| `guest/out/.config` | 78,549 | — |

Build method: `CARGO_ENCODED_RUSTFLAGS="" cargo xtask guest` (see decisions.md re: global mold rustflags). Kernel/disk built inside OrbStack's docker per Decision O2 — only `debian:trixie` containers with `--rm`; the user's `junior-*` containers were untouched; `docker ps -a`/`docker volume ls` before/after differ solely by the `kiri-kbuild` volume (kept for rebuilds; deleted at CTRS-23). `guest/out/` is gitignored.

The kernel was rebuilt after CTRS-07 removed the guest's USB passthrough block (`CONFIG_USB*`, vhci, evdev, HID): 2026-11-14, incremental build in the cached `kiri-kbuild` volume, OrbStack `junior-*` containers untouched (`Up 3 hours`, byte-identical before/after). The CTRS-03 `Image` hash applied to the kernel with USB support and is stale.

VM boot + smoke (CTRS-04, 2026-11-13, Apple Silicon): socket up 2 s after launch; `docker run --rm alpine true` 1 s; cold/hot `docker pull alpine` both <1 s; container exit codes propagate (`alpine false` → 1); exec/logs/rm green; published port maps `127.0.0.1:18080→80`; SIGTERM → daemon exit ≤2 s; no stale agent; OrbStack contexts byte-identical before/after; `~/.kiri` untouched during smoke and during `cargo test --workspace` (after test-isolation fix, `9a2b706`). Daemon idle RSS 10,896 KB. Smoke: `conformance/smoke.sh`, 15/15 checks.

Full VM cold/warm boot time and container create/start/remove percentiles: recorded at CTRS-17 (network bench) where the harness measures them properly.

## Security audit at the pin (`cargo audit`, DB fetched 2026-11-13)

Three advisories, all on dependencies that are removed or fixed by the campaign:

| Advisory | Crate | Path | Disposition |
| --- | --- | --- | --- |
| RUSTSEC-2024-0370 (unmaintained) `proc-macro-error` | — | GTK/UI-side (lock-file only, absent from this host's build graph) | deleted with UI in CTRS-07 |
| RUSTSEC-2024-0429 (unsound) `glib` VariantStrIter | — | GTK/UI-side | deleted with UI in CTRS-07 |
| RUSTSEC-2026-0486 (unsound) `rustix` `getxattr*` zero-length buffer | rustix 1.1.5 → 1.1.6 (`b96e7e3`) | bumped in its own commit after baseline recording |

`cargo deny` is not installed; license inventory was done manually from `Cargo.lock` (all permissive; see `docs/upstream.md`).

## Notes

- `cargo test --workspace` passing upstream on this host is expected — upstream CI runs the same surface — but it is the floor for every later slice, not a parity signal. After CTRS-07 the suite is **193 passing / 0 failed** (delta from the pin: tests of deleted subsystems — UI, Share, k8s, Windows/WSL, FS-view upload, crash-upload, scan).
- Guest asset build (`cargo xtask guest`, `cargo xtask kernel`, `cargo xtask disk`) and the signed Apple Silicon smoke are CTRS-03/CTRS-04 and recorded here when they land.
