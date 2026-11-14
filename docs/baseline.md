# Baseline — unmodified upstream import at the pin

Measured 2026-11-13 on macOS 27.2 (Apple Silicon), rustc 1.99.1 stable. Commands are given with each number; raw logs are in `.work/tmp/` (not committed).

## Pinned inputs

- Snapshot: Kiri `99b63c07fc003d3dcd8e03c76891ba747b5c984f` (see `docs/upstream.md`).
- Workspace: `cargo metadata --no-deps` OK. `Cargo.lock` resolves to 150 packages, 183 lines of `cargo tree --locked` output.
- Known red at import (pre-existing, `cargo check --workspace`): one warning — dead code `parse_ipam`, `crates/kiri/src/daemon/network.rs:472`.

## Loop timings (recorded, not gating until parity work lands)

| Command | Result | Wall |
| --- | --- | --- |
| fetch + checkout at pin (`--depth 1`) | ok | ~2 s |
| `cargo check --workspace` | ok (1 warning above) | 13.98 s |
| `cargo test --workspace` | **exit 0 — 359 tests passed, 12 suites, 0 failed** | 57 s |
| `cargo build --release -p kiri` | ok; binary 13,187,664 bytes (~12.6 MiB); build 1 m 09 s; one pre-existing warning | 69 s |

Follow-up commits: `b96e7e3` bumps rustix 1.1.5 → 1.1.6 (RUSTSEC-2026-0486); `cargo audit` afterwards reports only the two GTK-side advisories deleted in CTRS-07.

## Security audit at the pin (`cargo audit`, DB fetched 2026-11-13)

Three advisories, all on dependencies that are removed or fixed by the campaign:

| Advisory | Crate | Path | Disposition |
| --- | --- | --- | --- |
| RUSTSEC-2024-0370 (unmaintained) `proc-macro-error` | — | GTK/UI-side (lock-file only, absent from this host's build graph) | deleted with UI in CTRS-07 |
| RUSTSEC-2024-0429 (unsound) `glib` VariantStrIter | — | GTK/UI-side | deleted with UI in CTRS-07 |
| RUSTSEC-2026-0486 (unsound) `rustix` `getxattr*` zero-length buffer | rustix 1.1.5 → 1.1.6 (`b96e7e3`) | bumped in its own commit after baseline recording |

`cargo deny` is not installed; license inventory was done manually from `Cargo.lock` (all permissive; see `docs/upstream.md`).

## Notes

- `cargo test --workspace` passing upstream on this host is expected — upstream CI runs the same surface — but it is the floor for every later slice, not a parity signal.
- Guest asset build (`cargo xtask guest`, `cargo xtask kernel`, `cargo xtask disk`) and the signed Apple Silicon smoke are CTRS-03/CTRS-04 and recorded here when they land.
