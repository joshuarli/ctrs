# ctrs

An experimental, fast container engine for macOS and Linux, with no UI and
no system service required. The daemon serves the Docker Engine API on a
local Unix socket, so the Docker CLI, Compose and buildx work unchanged.

On macOS a small Linux guest runs under Apple's Virtualization.framework;
on Linux the agent runs directly on the host kernel.

## Build

For a fresh Ubuntu or Debian development setup, see the
[Linux development instructions](docs/development.md#linux-development-setup).

Needs Rust (see `rust-toolchain.toml`). The guest kernel and disk template
also need a Docker engine to build (any engine works); see
[docs/development.md](docs/development.md).

```sh
CARGO_ENCODED_RUSTFLAGS="" cargo xtask all   # guest assets + signed host binary
```

## Run

```sh
./target/release/ctrs daemon &
DOCKER_HOST=unix://$HOME/.local/share/ctrs/run/docker.sock docker run --rm alpine echo hello
```

Data (image store, VM disk) goes to `~/.local/share/ctrs`; override with
`CTRS_DATA_DIR`. The socket defaults to `~/.local/share/ctrs/run/docker.sock`;
override with `CTRS_SOCKET`. Logs live under the data root. Nothing is
installed system-wide. Build and run details, including the optional
launchd example: [docs/development.md](docs/development.md) and
[docs/launchd.md](docs/launchd.md).

## Help

Bug reports and questions: <https://github.com/joshuarli/ctrs/issues>.
Developer docs are indexed in [AGENTS.md](AGENTS.md).

## License and attribution

ctrs is licensed under Apache-2.0. It is a derived work of the
[Kiri](https://github.com/libracoder/kiri) project, imported at commit
`99b63c07fc003d3dcd8e03c76891ba747b5c984f`, Copyright its authors, licensed
under Apache-2.0. The ctrs repository is not affiliated with Kiri, and
Kiri's name and logo are not used in ctrs. The guest Linux kernel
(`guest/kernel/`) is a separate GPL-2.0-only work; its source offer is in
`guest/kernel/SOURCE_OFFER.md` and must travel with any distribution of the
guest assets.
