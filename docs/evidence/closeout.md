# Closeout — the headless-extraction campaign (CTRS-23, 2026-11-14)

End state of the campaign: the repository began as an Apache-2.0 engine
imported at a pinned commit and ends as a self-contained, headless
container engine for macOS and Linux. Git history is the provenance
record; this file is the final report.

## Gate J (local)

- Rename landed (`6f26f23`); no upstream identifiers remain in the tree
  (`rg -i` clean outside `README.md`'s attribution block).
- Warnings = 0 on `cargo check --workspace` (macOS) and
  `--target aarch64-unknown-linux-musl --all-targets` (`e765875`,
  `d5f99d2`).
- Gate suite (all re-run on this build): `cargo test --workspace` 203/0;
  `conformance/smoke.sh` 21/21 (daemon idle RSS 8256 KB, inside the
  30 MB gate); `tests/e2e.sh` 488/488, 0 skipped; netns firewall fixtures
  5/5 green in-VM (KVER 6.18.58); `conformance/isolation.sh` 5/5
  (CTRS-21).
- Fresh clone: `cargo check --workspace` and `cargo build --workspace`
  green.
- Artifact: `.work/release/ctrs-aarch64-apple-darwin` (sha256 in
  `docs/evidence/release.md`); local ad-hoc only; not published (O3). The
  guest kernel/initramfs and the 64 GiB data disk build from source
  (`guest/kernel/`, `cargo xtask guest|kernel|disk`).
- OrbStack: `kiri-kbuild` (the CTRS-03 kernel-build cache, pre-rename
  name) deleted; `junior-*` containers and volumes untouched.
- Independent review (2026-11-14, read-only): verdict *request changes*;
  every finding fixed in `d5f99d2` (Linux test target) and `b6186cd`
  (release-evidence corrections, install uninstaller, launchd paths,
  doubled citations). The SBOM and attribution were endorsed.

## Found and fixed during closeout

- Stale guest initramfs (built pre-rename): the guest looked up virtiofs
  tag `kiri-mac` while the host passes `ctrs-mac` — bind mounts of Mac
  paths failed on every fresh engine. Rebuilt (`cargo xtask guest`,
  initramfs 4,330,644 B); re-verified (e2e 488/488, netns fixtures in-VM,
  bind-mount round-trip).
- `ctrs stop` taking the default 10 s grace is Docker semantics for a
  PID 1 without a handler (unhandled signals to a namespace init are
  dropped; SIGKILL at timeout) — not a defect; verified with a trapping
  PID 1 (stop returns in 0.5 s, exit 42).
- "~900 KB guest agent" doc claim was stale (current static binary
  4.3 MB); claim cut.

## Ships where

- Local ad-hoc artifact only. Public release (notarization, tags,
  registries, download feeds) is owner step **N-4**. macOS is the
  qualified platform; the Linux path is compile-tested only (N-1).
- Attribution: `LICENSE` and `NOTICE` were deleted at the owner's call
  (`9586721`, confirmed 2026-11-14). `README.md` carries the upstream
  attribution and the GPL-2.0-only guest kernel source offer
  (`guest/kernel/SOURCE_OFFER.md`) — that offer must travel with any
  distribution of the guest assets. **No license text ships anywhere in
  the tree; if N-4 (public release) is to proceed, the owner must decide
  whether to restore the Apache-2.0 text or accept shipping without it.**
  This is flagged, not resolved.
- SBOM: `docs/third-party.md` (104 third-party packages in the default
  build; 47 feature-gated lock-only packages documented; no
  GPL/LGPL/AGPL in the host engine).

## Needs the owner

- N-1 native Linux run-qualification; N-2 crabtables native qualification
  (guest-kernel half green; default stays the handwritten netlink path);
  N-3 Intel host smoke; N-5 Rosetta on macOS 15.x.
- N-4, and inside it the license-text question above.
- 9 silent daemon deaths — `conformance/watch.sh` records them; root
  cause unproven (Virtualization XPC helper); shipping as a known issue,
  not a fixed one.
- Parked experiments: h12tiny-server re-qualification (transport-neutral
  re-qualification precondition per the withdrawn verdict); crabtables
  cutover; CRAB-7 paired suite; vzNAT Local Network grant (needs-owner).

## For the release cutter

- Artifact manifest and measurements: `docs/evidence/release.md`.
- Uninstall: `docs/install.md` (checked on a scratch install).
- `.work/` is disposable scratch; nothing there is needed.
- `guest/out/` (Image/initramfs/data.img) is gitignored build output;
  rebuild with `CARGO_ENCODED_RUSTFLAGS="" cargo xtask guest|kernel|disk`.
