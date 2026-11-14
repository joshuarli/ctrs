# Decisions

Binding decisions made during execution that a later slice depends on. Campaign-level decisions live in `docs/campaign-headless-kiri.md` (Decisions section, owner/prescribed/delegated); this file records the slice-level ones with dates. Append only; never rewrite history here.

## 2026-11-13

- **Import method (CTRS-01, P1):** file-tree copy at the pin, no `.github/`, no `__pycache__`; byte-identical to upstream otherwise. Recorded in `docs/upstream.md`.
- **rustix 1.1.5 → 1.1.6 (CTRS-02, b96e7e3):** RUSTSEC-2026-0486 unsoundness in zero-length xattr queries, reachable via `kiri-image` tar unpack. Other audit findings (`glib`, `proc-macro-error`) delete with the UI in CTRS-07.
- **Musl cross-link env (CTRS-03):** the user's global cargo config injects `-B/usr/local/libexec/mold` into every target and no mold exists on this host (nor the path). musl builds must run with `CARGO_ENCODED_RUSTFLAGS=""`, which overrides all config rustflags; project `.cargo/config.toml` keeps upstream's `rust-lld` linker choice and documents the quirk. Do not "fix" by editing the global config.
- **Guest kernel build via OrbStack (CTRS-03, Decision O2):** only `cargo xtask kernel|disk` (debian:trixie, `kiri-kbuild` volumes). June 2026 owner answer: no Linux verification this run; OrbStack used solely for the kernel/disk build.
