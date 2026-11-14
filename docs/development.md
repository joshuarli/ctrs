# Development

Building ctrs from source, running it, and how it fits together.

## Build

Needs Rust. The guest kernel and disk template additionally need a Docker
engine (for the `debian:trixie` build container); any engine works.

```sh
CARGO_ENCODED_RUSTFLAGS="" cargo xtask guest   # guest/out/initramfs.cpio
CARGO_ENCODED_RUSTFLAGS="" cargo xtask kernel  # guest/out/Image      (needs a Docker engine)
CARGO_ENCODED_RUSTFLAGS="" cargo xtask disk    # guest/out/data.img   (needs a Docker engine)
cargo xtask host      # target/release/ctrs, signed with the virtualization entitlement
cargo xtask all       # guest + host
cargo xtask linux     # ctrs and ctrs-init as static musl binaries (Linux host build; see N-1 in docs/campaign-headless-ctrs.md)
```

`CARGO_ENCODED_RUSTFLAGS=""` is required on hosts whose global cargo config
injects `-B` flags for musl targets; see docs/decisions.md.

For Intel Macs add `--arch x86_64` to `kernel`, `guest`, `host`: an x86-64
guest in `guest/out/x86_64` (a `bzImage`, cross-compiled on Apple Silicon)
and the `x86_64-apple-darwin` host binary. The x86-64 kernel is cross-compiled
with the same container build.

## Use

```sh
./target/release/ctrs daemon &              # serves ~/.local/share/ctrs/run/docker.sock; boots on first use
DOCKER_HOST=unix://$HOME/.local/share/ctrs/run/docker.sock docker run --rm alpine echo hello
docker buildx create --name ctrs-build --driver docker-container \
  --driver-opt default-load=true unix:///absolute/path/to/run/docker.sock   # for docker build
SOAK=600 CTRS_SOCKET=.work/tmp/smoke.sock tests/e2e.sh    # full suite + 600-run leak soak
```

Docker's commands also work as `ctrs` commands, always against the daemon
socket whatever docker context is selected: `ctrs run`, `ctrs ps`, `ctrs
exec`, `ctrs logs`, `ctrs compose up`. They run the docker CLI with
`DOCKER_HOST=unix://…` and `DOCKER_CONTEXT` stripped. Nothing in the
daemon creates a docker context. A BuildKit builder is addressed by its
endpoint (`unix://…`), never by a context name.

Data goes to `~/.local/share/ctrs` (override with `CTRS_DATA_DIR`), logs to
`~/.local/share/ctrs/logs/` (the unit tests redirect them via `CTRS_STATE_DIR`), the
socket path defaults to `~/.local/share/ctrs/run/docker.sock` (override with
`CTRS_SOCKET`). The repository does not install anything system-wide
(`/usr/local/bin`, `launchd`, `/etc/resolver`); see docs/launchd.md for an
optional user service example.

## Architecture

```
docker CLI ─┐
compose ────┼─ ~/.local/share/ctrs/run/docker.sock ─► ctrs daemon ── vsock ──► guest agent (PID 1)
buildx ─────┘    Docker Engine API          owns the VM              clone3 → container
```

- **VM**: Apple's Virtualization.framework, driven from Rust through objc2.
  A custom 10 MB kernel (`guest/kernel/`) built from allnoconfig. Rosetta is
  shared in over virtiofs and registered with binfmt_misc.
- **Guest agent**: a static Rust binary that is PID 1. One `poll()`
  loop serves the host, reaps children, forwards container output and
  relays ports. `docker cp` runs in forked children so a large copy never
  stalls it.
- **Containers**: one `clone3` straight into new namespaces and the
  container's cgroup (`CLONE_INTO_CGROUP`), overlayfs over layers unpacked
  on an ext4 data disk, `pivot_root`, capabilities and a seccomp filter.
  Networking is set up with hand-written rtnetlink and nf_tables messages.
  No runc, no shim, no dockerd.
- **Images**: pulled and pushed on the host, streamed into the guest once
  and unpacked there.

## Layout

| Path | What |
|------|------|
| `crates/ctrs` | the `ctrs` binary: daemon, Docker API, CLI |
| `crates/ctrs-vmm` | Virtualization.framework VM |
| `crates/ctrs-init` | guest PID 1, agent and container runtime |
| `crates/ctrs-proto` | host ↔ guest wire protocol |
| `crates/ctrs-image` | image references, registry client, blob store, archives |
| `guest/kernel` | kernel config and patches |
| `conformance/` | `smoke.sh` (engine round-trip), `run.sh` (API fixtures) |
| `tests/e2e.sh` | the Docker compatibility suite, against a running engine |
| `tests/arm64-build.sh` | the ARM64-on-AMD64 qualification runner (`environment`, `compatibility`, `identity`, `platform`, `cross`, `lifecycle` cases) |
| `tests/linux-host.sh` | the Linux host build, driven in a privileged container |
| `xtask` | build tasks |

## Verification

`conformance/smoke.sh` boots the VM with scratch roots and round-trips a
container. `tests/e2e.sh` runs the full compatibility suite against a
running engine (see its header). `cargo test --workspace` runs the unit
suite (as root; the `ctrs-init` layers tests need chown to uid/gid 0, so
on unprivileged hosts run them in a root container — CI does this).
`tests/arm64-build.sh --case compatibility` runs the ARM64-on-AMD64
qualification suite in a disposable, isolated environment; `--case
lifecycle` covers concurrent builds, cancellation, worker failure, failed
target execution, daemon restart with cache reuse, and the bundled
emulator's diagnostics (see `docs/evidence/arm64-build.md`).
`binfmt` handler-free proof is unavailable on hosts where the handlers
are global; the runner fails closed under `--require-no-binfmt`.
