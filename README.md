# ctrs

An experimental, fast container engine for macOS and Linux, with no UI and
no system service required. The daemon serves the Docker Engine API on a
local Unix socket, so the Docker CLI, Compose and buildx work unchanged.

On macOS a small Linux guest runs under Apple's Virtualization.framework;
on Linux the agent runs directly on the host kernel.

## Build

For a fresh Alpine, Ubuntu or Debian development setup, see the
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

## Bind mounts and volumes on macOS

Bind mounts (`-v ./src:/app`) share Mac files with the guest through Apple's
virtiofs. Every file operation crosses the VM boundary, which costs roughly
0.1–0.4 ms more than on the Mac's own disk. That is unnoticeable for source,
config files, sockets and build outputs. Trees with tens of thousands of
small files, such as `node_modules`, package caches and build caches, are
much slower on a bind. A Kutt `npm ci` measured 2.1× slower on a bind than
on a named volume.

Keep the source on a bind mount so the Mac and the container see the same
files, and give dependency and cache directories a named volume:

```yaml
services:
  app:
    volumes:
      - .:/app
      - node_modules:/app/node_modules
volumes:
  node_modules:
```

With this layout the measured Kutt install, build and test workflow matched
OrbStack. The Mac does not see files written into the volume; use
`docker cp` or another mount if you need them on the Mac.

## Help

Run `ctrs --help` for the native command reference, examples, and Docker
compatibility routes. Docker defines the arguments and nested commands for
those routes; consult Docker help for their complete syntax. Command-specific
help is available with `ctrs COMMAND --help` without starting the engine.

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
