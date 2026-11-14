# Contributing to ctrs

ctrs is an experimental, aggressively headless container engine extracted
from [Kiri](https://github.com/libracoder/kiri). See
[docs/campaign-headless-kiri.md](docs/campaign-headless-kiri.md) for how it
is built and what applies.

## Building and testing

```sh
cargo xtask host      # target/release/kiri, signed with the virtualization entitlement
cargo test            # unit tests
KIRI_SOCKET=.work/tmp/smoke.sock tests/e2e.sh   # needs a running engine, see docs/development.md
```

Use `cargo xtask host`, not plain `cargo build`, for a binary you run as the
daemon: without the virtualization entitlement the VM will not start. The
guest needs `cargo xtask guest` (initramfs), `cargo xtask kernel` and
`cargo xtask disk` once; see docs/development.md.

`tests/e2e.sh` only removes containers, networks and volumes it created, and
never touches docker contexts, OrbStack, or `~/.kiri`: it drives
`KIRI_SOCKET` directly.

## What applies here

- Changes stay small and fast; dependencies need a reason, not a reflex.
- `cargo check --workspace` must stay warning-free.
- No new Windows, UI or sharing code paths; the deleted subsystems are
  documented in docs/decisions.md.
- Kiri's name and logo are not used in distributions (docs/upstream.md).

By submitting a contribution you agree it is licensed under Apache-2.0.
