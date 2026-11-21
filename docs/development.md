# Development

Building ctrs from source, running it, and how it fits together.

## Linux development setup

On Alpine, Ubuntu 24.04, Debian or Ubuntu 26.04, from a fresh clone run:

```sh
./scripts/setup-dev
export PATH="$HOME/.local/share/ctrs-dev/bin:$HOME/.cargo/bin:$PATH"
make test
make lint
```

As a non-root user the setup escalates with `sudo` or `doas`. It installs
the distribution packages below, the pinned Rust nightly
(`rust-toolchain.toml`) and the locked Cargo dependencies. Then it runs
`scripts/dev-tools.py` through `bootstrap/buildlib-run`, which is vendored
from [laputa-systems/buildlib](https://github.com/laputa-systems/buildlib/blob/main/docs/bootstrap.md)
at `50d8081`. The shim fetches the pinned CPython 3.15 and the
laputa-buildlib wheel (`bootstrap/python.lock`) and checks each one's size
and SHA-256 before using it. CPython comes from python-build on macOS,
Alpine, and glibc hosts with musl 1.2.5 or newer (Debian 13, Ubuntu 26.04).
With older musl (Ubuntu 24.04) it comes from the pinned uv. `dev-tools.py`
then uses buildlib to fetch the Node pinned in `sources.lock.json`, and
links `python3` and `node` into `~/.local/share/ctrs-dev/bin`. Where the
pinned Node cannot run, it uses the distribution's `node` and says so.
Both steps are safe to repeat. Run the setup again after clearing
`~/.cache/laputa-buildlib`, since the linked `python3` lives there. On an
Apple Silicon Mac, run `sh bootstrap/buildlib-run -- scripts/dev-tools.py`
on its own.

| Package | Consumer |
| --- | --- |
| build-essential / build-base, make | Rust native dependencies and `make test` |
| ca-certificates, curl, tar, xz | rustup and the verified downloads |
| git | clone and Git dependencies |
| bash (Alpine) | `conformance/run.sh` and the shell scripts `make test` runs |
| musl (Debian, Ubuntu) | loader for the pinned musl Python and Node, where musl is 1.2.5 or newer |
| nodejs (Debian, Ubuntu; Alpine on ARM64) | JavaScript fixture tests when the pinned Node cannot run or has no build for the host |
| docker.io / docker (only when `docker` is missing) | guest asset builds (`cargo xtask`) and engine integration tests |

To change the Node version, edit its entries in `sources.lock.json`, in the
[build repository lock format](https://github.com/laputa-systems/stuff/blob/main/docs/build-repos.md#pinned-inputs).
To change Python or buildlib, copy `bootstrap/` again from buildlib.

On a Linux host, as opposed to a container, `ctrs-init`'s
`dns::tests::every_forwarded_query_has_its_own_port_and_its_answer_goes_back`
binds `127.0.0.2:53`, so it needs root or
`net.ipv4.ip_unprivileged_port_start` at 53 or lower. Docker containers
already allow it.

Measured 2026-11-21 in a pristine `alpine:3.22` x86_64 container on a
busy 8-core host (cold, as root): setup 65 s, `make test` 225 s, then
`make lint` and a clean `git status`. The uv path on `ubuntu:24.04` and the
python-build path on `debian:13` were proven for the shim only. Their
full gates, and the non-root container runs, were cut short by a registry
outage and have not been rerun.

The musl cross-build also needs a Rust musl target; install it with
`rustup target add` for your architecture. No compiler cache or custom
linker is required for the default host tests.

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
CTRS_SOCKET=/var/run/docker.sock tests/e2e.sh             # Linux Docker baseline; use an idle test daemon
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
| `bench/arm64-build.sh` | the ARM64 build benchmark (equivalent-work A/B/C comparison; `--verify`, `--samples N --all-states`) |
| `tests/arm64-build.sh` | the ARM64-on-AMD64 qualification runner (`environment`, `compatibility`, `identity`, `platform`, `cross`, `lifecycle` cases) |
| `tests/linux-host.sh` | the Linux host build, driven in a privileged container |
| `xtask` | build tasks |

## Verification

The benchmark suite has one entrypoint, `python3 bench/native/pyramid.py`
(`list`, `check`, `run --tier edit|change|scenario` or `--name`, `--dry-run`);
full workloads run only when named. See `bench/native/README.md`
("Entrypoint"). For native performance iteration, use the explicit offline
component checks before broad suites:

```sh
python3.14 bench/native/runner.py check w2
python3.14 bench/native/runner.py check w8
python3.14 bench/native/runner.py check resources
python3.14 -m unittest discover -s bench/native -p test_checks.py -v
```

Choose only the component whose contracts changed, and run changed test modules
directly with native `unittest`. `runner.py check` rejects missing, unknown, or
`full` components. Each selection includes its component modules and the shared
`test_safety` boundary, requires a nonempty run with zero skips, and fails on
imports/discovery errors, test failures, or a 60-second timeout (maximum 300).
The gate does no build or engine setup. Full discovery previously took 13.477
seconds for 201 tests. The first W2 selection ran 32 tests in 1.630 seconds;
W8/resources costs and timeout adequacy remain unmeasured.

`make test` runs the Rust workspace tests and full Python discovery, as CI does on
pull requests; `make lint` runs clippy over all targets. The ceilings below govern
iteration inside a lane, not that gate.

Verification ceilings: **Edit** is a changed module plus `test_checks.py`;
**Change** is one explicit component check plus changed tests (60 seconds,
maximum 300); **Scenario** requires a named benchmark workload and separate
input/engine/resource authorization; **Full** requires explicit authorization
for the particular full workload. Full Python discovery, `cargo test
--workspace`, `CARGO_ENCODED_RUSTFLAGS="" cargo xtask all`,
`conformance/run.sh`, and the `tests/arm64-build.sh` qualification matrix stay
manual-only. W11 means the full 12-hour qualification per named engine after
candidate freeze, with an exact command, immutable inputs and binary receipts,
run ID, and fixed deadline authorized through
[`bench/native/diagnostics/durable-job.md`](../bench/native/diagnostics/durable-job.md).
Short cycles and check selections do not authorize or qualify W11. These full
workloads are not prerequisites or fallbacks for `runner.py check`.

`python3.14 conformance/image-labels.py --ctrs-binary /path/to/signed/ctrs`
loads tiny disposable image archives and checks populated, empty and absent
labels plus adjacent config fields through an isolated engine socket. It needs
no registry, guest boot or containers; results stay under `.work/tmp`.

For balloon-accounting edits, `cargo test -p ctrs balloon_target_tests` checks
reserve/rounding boundaries. The dependency-free guest parser can be checked
on macOS with `kache "$(command -v rustc)" --test --edition=2021
crates/ctrs-init/src/linux/memory.rs -o .work/tmp/ctrs-memory-tests`, then
`.work/tmp/ctrs-memory-tests` (create `.work/tmp` first). Cross-check the actual
guest component with `CARGO_ENCODED_RUSTFLAGS="" cargo check --offline -p
ctrs-init --target aarch64-unknown-linux-musl`. These select three host-target
and three parser tests, rather than the full suites. The native budget proof
and affected W2/W6 checks are recorded in
[`evidence/native-balloon-2026-11-16.md`](evidence/native-balloon-2026-11-16.md).

On native ARM64 macOS, `conformance/vm-stop.py --ctrs-binary /path/to/signed/ctrs
--portfolio-archive /path/to/portfolio.tar` checks idle sleep, wake, injected VM
loss and recovery, and normal daemon shutdown using an isolated engine. It
checks the pinned common portfolio and saves results under `.work/tmp`.

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
`bench/arm64-build.sh --verify` runs the short benchmark pilot;
`--samples 5 --all-states` is the full equivalent-work comparison
(envelope: median gap must exceed observed spread on equivalent
successful work before any speed claim; overlapping-load samples are
discarded; the host must be quiet).
`binfmt` handler-free proof is unavailable on hosts where the handlers
are global; the runner fails closed under `--require-no-binfmt`.
