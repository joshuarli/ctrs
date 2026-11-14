# Third-party inventory

SBOM-style inventory of the packages the host engine links, generated from
`cargo metadata --locked` (source of truth: `Cargo.lock`). Regenerate with:

```sh
cargo metadata --format-version 1 --locked
```

Generated 2026-11-14. **110** packages in the default resolve graph: the 6
workspace members (`ctrs`, `ctrs-init`, `ctrs-proto`, `ctrs-vmm`,
`ctrs-image`, `xtask`) plus **104** third-party packages listed
below. `Cargo.lock` additionally pins **47** feature-gated packages that no
default build compiles — the experimental `crabtables` firewall-adapter
backend and the `h12tiny`-server pilot stack (see the end of this file).

## License summary

- 62× `MIT OR Apache-2.0`
- 14× `MIT`
- 4× `Apache-2.0 OR MIT`
- 3× `Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT`
- 2× `Zlib OR Apache-2.0 OR MIT`
- 2× `Apache-2.0 OR ISC OR MIT-0`
- 2× `Unlicense OR MIT`
- 2× `Apache-2.0 OR ISC OR MIT`
- 2× `ISC`
- 2× `Unlicense/MIT`
- 1× `0BSD OR MIT OR Apache-2.0`
- 1× `MIT/Apache-2.0`
- 1× `MIT OR Zlib OR Apache-2.0`
- 1× `MIT OR Apache-2.0 OR LGPL-2.1-or-later`
- 1× `Apache-2.0 AND ISC`
- 1× `BSD-3-Clause`
- 1× `(MIT OR Apache-2.0) AND Unicode-3.0`
- 1× `CDLA-Permissive-2.0`
- 1× `Zlib`

All licenses are permissive. `r-efi` offers `MIT OR Apache-2.0 OR
LGPL-2.1-or-later`; ctrs uses it under `MIT OR Apache-2.0` (it is a UEFI
type-definition crate with no code paths into the engine). **No GPL,
LGPL, or AGPL code is compiled into the host engine.** The guest Linux
kernel (`guest/kernel/`) is a separate GPL-2.0-only work; its source offer
is in `guest/kernel/SOURCE_OFFER.md` and must travel with any distribution
of the guest assets.

## Packages in the default build

| Package | Version | License | Source |
| --- | --- | --- | --- |
| `adler2` | 2.0.1 | 0BSD OR MIT OR Apache-2.0 | crates.io |
| `base64` | 0.23.1 | MIT OR Apache-2.0 | crates.io |
| `bitflags` | 2.13.2 | MIT OR Apache-2.0 | crates.io |
| `block-buffer` | 0.12.1 | MIT OR Apache-2.0 | crates.io |
| `block2` | 0.6.2 | MIT | crates.io |
| `bytes` | 1.12.1 | MIT | crates.io |
| `cc` | 1.10.0 | MIT OR Apache-2.0 | crates.io |
| `cfg-if` | 1.0.5 | MIT OR Apache-2.0 | crates.io |
| `combine` | 4.6.9 | MIT | crates.io |
| `const-oid` | 0.10.2 | Apache-2.0 OR MIT | crates.io |
| `core-foundation` | 0.10.1 | MIT OR Apache-2.0 | crates.io |
| `core-foundation-sys` | 0.8.7 | MIT OR Apache-2.0 | crates.io |
| `cpufeatures` | 0.3.1 | MIT OR Apache-2.0 | crates.io |
| `crc32fast` | 1.5.3 | MIT OR Apache-2.0 | crates.io |
| `crypto-common` | 0.2.2 | MIT OR Apache-2.0 | crates.io |
| `digest` | 0.11.3 | MIT OR Apache-2.0 | crates.io |
| `dispatch2` | 0.3.1 | Zlib OR Apache-2.0 OR MIT | crates.io |
| `errno` | 0.3.14 | MIT OR Apache-2.0 | crates.io |
| `filetime` | 0.2.29 | MIT/Apache-2.0 | crates.io |
| `find-msvc-tools` | 0.1.15 | MIT OR Apache-2.0 | crates.io |
| `flate2` | 1.1.10 | MIT OR Apache-2.0 | crates.io |
| `getrandom` | 0.2.17 | MIT OR Apache-2.0 | crates.io |
| `getrandom` | 0.4.3 | MIT OR Apache-2.0 | crates.io |
| `graviola` | 0.4.5 | Apache-2.0 OR ISC OR MIT-0 | crates.io |
| `h12tiny-client-normalize` | 0.9.0 | MIT | crates.io |
| `h12tiny-client-sync` | 0.9.0 | MIT | crates.io |
| `h12tiny-tls-system` | 0.9.0 | MIT | crates.io |
| `http` | 1.5.0 | MIT OR Apache-2.0 | crates.io |
| `hybrid-array` | 0.4.15 | MIT OR Apache-2.0 | crates.io |
| `itoa` | 1.0.18 | MIT OR Apache-2.0 | crates.io |
| `jni` | 0.22.4 | MIT OR Apache-2.0 | crates.io |
| `jni-macros` | 0.22.4 | MIT OR Apache-2.0 | crates.io |
| `jni-sys` | 0.4.1 | MIT OR Apache-2.0 | crates.io |
| `jni-sys-macros` | 0.4.1 | MIT OR Apache-2.0 | crates.io |
| `libc` | 0.2.191 | MIT OR Apache-2.0 | crates.io |
| `linux-raw-sys` | 0.12.1 | Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT | crates.io |
| `log` | 0.4.34 | MIT OR Apache-2.0 | crates.io |
| `memchr` | 2.8.3 | Unlicense OR MIT | crates.io |
| `miniz_oxide` | 0.9.1 | MIT OR Zlib OR Apache-2.0 | crates.io |
| `objc2` | 0.6.5 | MIT | crates.io |
| `objc2-encode` | 4.1.0 | MIT | crates.io |
| `objc2-foundation` | 0.3.2 | MIT | crates.io |
| `objc2-virtualization` | 0.3.2 | Zlib OR Apache-2.0 OR MIT | crates.io |
| `once_cell` | 1.21.4 | MIT OR Apache-2.0 | crates.io |
| `openssl-probe` | 0.2.2 | MIT OR Apache-2.0 | crates.io |
| `proc-macro2` | 1.0.107 | MIT OR Apache-2.0 | crates.io |
| `quote` | 1.0.47 | MIT OR Apache-2.0 | crates.io |
| `r-efi` | 6.0.0 | MIT OR Apache-2.0 OR LGPL-2.1-or-later | crates.io |
| `ring` | 0.17.14 | Apache-2.0 AND ISC | crates.io |
| `rustc-hash` | 2.1.3 | Apache-2.0 OR MIT | crates.io |
| `rustc_version` | 0.4.1 | MIT OR Apache-2.0 | crates.io |
| `rustix` | 1.1.6 | Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT | crates.io |
| `rustls` | 0.23.46 | Apache-2.0 OR ISC OR MIT | crates.io |
| `rustls-graviola` | 0.4.0 | Apache-2.0 OR ISC OR MIT-0 | crates.io |
| `rustls-native-certs` | 0.8.5 | Apache-2.0 OR ISC OR MIT | crates.io |
| `rustls-pki-types` | 1.15.1 | MIT OR Apache-2.0 | crates.io |
| `rustls-platform-verifier` | 0.7.1 | MIT OR Apache-2.0 | crates.io |
| `rustls-platform-verifier-android` | 0.2.0 | MIT OR Apache-2.0 | crates.io |
| `rustls-webpki` | 0.103.16 | ISC | crates.io |
| `ruzstd` | 0.9.1 | MIT | crates.io |
| `same-file` | 1.0.6 | Unlicense/MIT | crates.io |
| `schannel` | 0.1.30 | MIT | crates.io |
| `security-framework` | 3.7.0 | MIT OR Apache-2.0 | crates.io |
| `security-framework-sys` | 2.17.0 | MIT OR Apache-2.0 | crates.io |
| `semver` | 1.0.28 | MIT OR Apache-2.0 | crates.io |
| `serde` | 1.0.229 | MIT OR Apache-2.0 | crates.io |
| `serde_core` | 1.0.229 | MIT OR Apache-2.0 | crates.io |
| `serde_derive` | 1.0.229 | MIT OR Apache-2.0 | crates.io |
| `serde_json` | 1.0.154 | MIT OR Apache-2.0 | crates.io |
| `sha2` | 0.11.1 | MIT OR Apache-2.0 | crates.io |
| `shlex` | 2.0.1 | MIT OR Apache-2.0 | crates.io |
| `simd-adler32` | 0.3.10 | MIT | crates.io |
| `simd_cesu8` | 1.2.0 | Apache-2.0 OR MIT | crates.io |
| `simdutf8` | 0.1.5 | MIT OR Apache-2.0 | crates.io |
| `subtle` | 2.6.1 | BSD-3-Clause | crates.io |
| `syn` | 2.0.119 | MIT OR Apache-2.0 | crates.io |
| `syn` | 3.0.9 | MIT OR Apache-2.0 | crates.io |
| `tar` | 0.4.46 | MIT OR Apache-2.0 | crates.io |
| `thiserror` | 2.0.21 | MIT OR Apache-2.0 | crates.io |
| `thiserror-impl` | 2.0.21 | MIT OR Apache-2.0 | crates.io |
| `twox-hash` | 2.1.5 | MIT | crates.io |
| `typenum` | 1.20.1 | MIT OR Apache-2.0 | crates.io |
| `unicode-ident` | 1.0.27 | (MIT OR Apache-2.0) AND Unicode-3.0 | crates.io |
| `untrusted` | 0.9.0 | ISC | crates.io |
| `walkdir` | 2.5.0 | Unlicense/MIT | crates.io |
| `wasi` | 0.11.1+wasi-snapshot-preview1 | Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT | crates.io |
| `webpki-root-certs` | 1.0.12 | CDLA-Permissive-2.0 | crates.io |
| `winapi-util` | 0.1.11 | Unlicense OR MIT | crates.io |
| `windows-link` | 0.2.1 | MIT OR Apache-2.0 | crates.io |
| `windows-sys` | 0.52.0 | MIT OR Apache-2.0 | crates.io |
| `windows-sys` | 0.61.2 | MIT OR Apache-2.0 | crates.io |
| `windows-targets` | 0.52.6 | MIT OR Apache-2.0 | crates.io |
| `windows_aarch64_gnullvm` | 0.52.6 | MIT OR Apache-2.0 | crates.io |
| `windows_aarch64_msvc` | 0.52.6 | MIT OR Apache-2.0 | crates.io |
| `windows_i686_gnu` | 0.52.6 | MIT OR Apache-2.0 | crates.io |
| `windows_i686_gnullvm` | 0.52.6 | MIT OR Apache-2.0 | crates.io |
| `windows_i686_msvc` | 0.52.6 | MIT OR Apache-2.0 | crates.io |
| `windows_x86_64_gnu` | 0.52.6 | MIT OR Apache-2.0 | crates.io |
| `windows_x86_64_gnullvm` | 0.52.6 | MIT OR Apache-2.0 | crates.io |
| `windows_x86_64_msvc` | 0.52.6 | MIT OR Apache-2.0 | crates.io |
| `xattr` | 1.6.1 | MIT OR Apache-2.0 | crates.io |
| `zeroize` | 1.9.1 | Apache-2.0 OR MIT | crates.io |
| `zlib-rs` | 0.6.8 | Zlib | crates.io |
| `zmij` | 1.0.23 | MIT | crates.io |

## Feature-gated packages (locked, never built by default)

None of these is compiled into the default binary; they exist in the
lockfile for the opt-in `crabtables` (ctrs-init firewall adapter) and
`h12tiny` (ctrs-server pilot) cargo features, both documented as parked
experiments:
`async-channel`, `async-io`, `async-net`, `async-task`, `atomic-waker`, `autocfg`, `blocking`, `concurrent-queue`, `crabtables`, `crossbeam-utils`, `event-listener`, `event-listener-strategy`, `fastrand`, `futures-channel`, `futures-core`, `futures-io`, `futures-lite`, `futures-task`, `futures-util`, `h12tiny-core`, `h12tiny-server`, `hermit-abi`, `http-body`, `httparse`, `httpdate`, `laputa-async-channel`, `laputa-async-io`, `laputa-async-net`, `laputa-async-task`, `laputa-atomic-waker`, `laputa-blocking`, `laputa-concurrent-queue`, `laputa-event-listener`, `laputa-event-listener-strategy`, `laputa-fastrand`, `laputa-futures-lite`, `laputa-hyper-futures-lite`, `laputa-parking`, `laputa-piper`, `laputa-polling`, `netlink-sys`, `parking`, `pin-project-lite`, `piper`, `polling`, `slab`, `smallvec`.

Notable pin: `crabtables` `0.1.0` from
`github.com/laputa-systems/crabtables` at rev
`38646b8f2f6ee7256c448849edda4459842a2e10` (git dependency; no release tags).
