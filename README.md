# ctrs

An experimental, aggressively headless macOS/Linux container-engine project based on the core of [Kiri](https://github.com/libracoder/kiri), with planned integration of [crabtables](https://github.com/laputa-systems/crabtables) and [smolith](https://github.com/laputa-systems/smolith).

**Status: extraction in progress.** The pinned Kiri runtime (Apache-2.0) is imported and being made headless at commit `99b63c07fc003d3dcd8e03c76891ba747b5c984f`; see [the import record](docs/upstream.md). Design and sequencing live in [the implementation campaign](docs/campaign-headless-kiri.md).

## Build and run

```sh
cargo xtask host      # target/release/kiri, signed with the virtualization entitlement
./target/release/kiri daemon &
DOCKER_HOST=unix://$HOME/.kiri/run/docker.sock docker run --rm alpine echo hello
```

The engine needs no installer, no docker context and no system service; see
[docs/development.md](docs/development.md) and [docs/launchd.md](docs/launchd.md).

Read [the implementation campaign](docs/campaign-headless-kiri.md) before importing or modifying upstream code. The campaign defines the executable milestones, compatibility/security gates, and Lima/smolvm research experiments.

The initial implementation may temporarily retain `kiri` command, crate, or protocol identifiers for compatibility during development. The repository is not affiliated with the Kiri project; its name and logo are not licensed by Apache-2.0. Do not reuse Kiri logos or publicly distribute a rebranded product under its trademark. The eventual product name and CLI are `ctrs`.

The upstream Kiri code is Apache-2.0, with third-party notices and Linux guest-kernel GPL-2.0 source obligations that must be preserved when importing the runtime.
