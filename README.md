# ctrs

An experimental, aggressively headless macOS/Linux container-engine project based on the core of [Kiri](https://github.com/libracoder/kiri), with planned integration of [crabtables](https://github.com/laputa-systems/crabtables) and [smolith](https://github.com/laputa-systems/smolith).

**Status: architecture/campaign only.** No container runtime has been imported or built here yet.

Read [the implementation campaign](docs/campaign-headless-kiri.md) before importing or modifying upstream code. The campaign defines the executable milestones, compatibility/security gates, and Lima/smolvm research experiments.

The initial implementation may temporarily retain `kiri` command, crate, or protocol identifiers for compatibility during development. The repository is not affiliated with the Kiri project; its name and logo are not licensed by Apache-2.0. Do not reuse Kiri logos or publicly distribute a rebranded product under its trademark. The eventual product name and CLI are `ctrs`.

The upstream Kiri code is Apache-2.0, with third-party notices and Linux guest-kernel GPL-2.0 source obligations that must be preserved when importing the runtime.
