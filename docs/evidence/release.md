# Release evidence — CTRS-22 local release prep (2026-11-14)

Local, ad-hoc artifacts only (Decision O3). Notarization, tags, registry
publishes and the public release are owner steps (N-4) and are deliberately
absent here.

## Artifact manifest

Built with `cargo xtask host` (release profile, `lto=thin`, `panic=abort`)
and ad-hoc signed by it with `com.apple.security.virtualization`:

| Artifact | sha256 | Bytes |
| --- | --- | --- |
| `.work/release/ctrs-aarch64-apple-darwin` | `6b3466eef19b3ee73178f684fd279793bf4cb811188ecc942ee23bade6dc4eff` | 6,327,152 |

`.work/release/` is gitignored scratch; this file is the committed manifest.
`codesign --verify` passes; the entitlement is present and required — the
guest VM will not start without it. The release profile is thinner than the
import's `lto=fat` config (the ish cargo profile layout was adopted in
937cbcc) and still achieves the size below because the UI/GTK/updater/Share
stack is deleted.

## Comparison vs the initial import

| Metric | Pin (import `06a617b`) | This commit | Δ |
| --- | --- | --- | --- |
| `ctrs` release binary (aarch64-apple-darwin) | 13,187,664 B | 6,327,152 B | −52.0 % |
| Tracked files | 397 | 164 | −59 % |
| Tracked lines (tree, at ref) | 166,316 | 45,703 | −72 % |
| — Rust only | 67,910 | 35,431 | −48 % |
| `Cargo.lock` entries | 212 | 157 | −55 (GTK/UI graph deleted; feature-gated h12tiny/crabtables stacks added) |
| `cargo tree --locked` lines | 183 | 131 | −28 % |
| Workspace tests passing | 359 (12 suites) | 203 (sum over suites, 2026-11-14) | −44 % (deleted subsystems' tests) |

Pin numbers: binary size, 359 tests, 183 tree lines, 150 packages per
`cargo metadata` (not a lockfile count), and 13.98 s `cargo check` come
from the import baseline record (deleted 2026-11-14; recovered from git
object `3141847`:`docs/baseline.md`). File/line counts are the tree at
the import commit itself (`git ls-tree -r 06a617b`); the pin contained two
pre-existing files (`README.md`, `docs/campaign-headless-kiri.md`), so the
import's diffstat (396 files, 163,327 insertions) is not a tree size.
`cargo check --workspace` was 13.98 s at the pin (rustc 1.99.1); 2.9 s
warm this run (nightly 2026-11-09 + warm cache — not a comparable
methodology).

## Fresh measurements (2026-11-14)

Host: this Mac (Apple Silicon, macOS 27.2), scratch roots under
`.work/tmp/release-measure4/` (never `~/.local/share/ctrs`, never
OrbStack). Raw output: `.work/tmp/release-measure4/` and
`.work/tmp/measure2.out` (not committed).

- Daemon socket-up latency (VM boots on first container): first boot
  0.25 s; 0.014–0.016 s on the next four fresh boots. A fresh first
  `docker run --rm alpine true` with the image cached (VM cold) took
  0.33 s.
- `docker run --rm alpine true`, 25 warm samples: p50 41 ms, p95 63 ms,
  p99 65 ms, max 71 ms, min 21 ms.
- Create-once + 25× (`docker start` + `docker stop -t 0`): p50 33 ms,
  p95 41 ms, max 42 ms. (`stop` with the default 10 s grace burns the grace
  by design for a PID 1 without a handler — Linux drops unhandled signals
  to a namespace init; SIGKILL at timeout. Verified the signal path with a
  trapping PID 1: stop returns in 0.5 s, exit code 42.)
- Cold pull (`docker rmi` + `docker pull alpine`): 0.867–0.910 s over 5
  trials; hot pull: 0.392–0.427 s over 5 trials. Network-dependent; same
  host for both.
- RSS: daemon fresh-boot idle 8,256 KB (smoke harness, before the VM
  boots); daemon 22,064 KB after the VM had booted once; 23,088 KB peak
  sampled during a sequential 25× run loop. The Apple Virtualization
  helper (XPC): 301,232 KB idle after first VM boot, 314,624 KB peak
  sampled. Fresh-boot idle is inside the 30 MB smoke gate.
- Bind-mount metadata: 1000 `stat`s on a host dir inside the guest over
  virtiofs took 0.22 s (busybox `time`, logged). Host-side reference with
  one fork+exec per stat (`/usr/bin/stat`): 4.57 s — different method
  (fork-heavy), reported raw, not as a like-for-like ratio.
- Smoke: `conformance/smoke.sh` green on this build: 21/21 pass, daemon
  idle RSS 8256 KB (gate ≤ 30 MB).

## Notices / third-party

- `docs/third-party.md` (committed): 104 third-party packages in the
  default build, license histogram — all permissive; no GPL/LGPL/AGPL in
  the host engine. 47 feature-gated packages pinned in the lockfile are
  never compiled by the default build (experimental `crabtables` /
  `h12tiny` stacks, parked). `crabtables` is a git pin (rev
  `38646b8f…`); noted there with its license.
- `LICENSE` and `NOTICE` were deleted at the owner's call (`9586721`,
  confirmed 2026-11-14); attribution to the upstream project is carried in
  `README.md` only. This is the owner's decision, recorded in
  `docs/decisions.md` — not a compliance recommendation.
- GPL-2.0-only guest kernel offer intact: `guest/kernel/SOURCE_OFFER.md`,
  referenced from `README.md` and `docs/install.md`. Any distribution of
  the guest assets must carry it (kernel + patches + config are GPL-2.0).
- SBOM scope: host engine + workspace. Build tooling (OrbStack
  kernel/disk build containers, the pinned `rust:1.100.0-alpine` Linux
  builder image) is not part of the shipped artifact.

## Uninstaller

Documented in `docs/install.md` ("Uninstall"). Checked on scratch roots:
artifact + `CTRS_DATA_DIR` (21 MB, one container run) removed;
`~/.local/share/ctrs` untouched.

## Known gaps / parked (unchanged by this slice)

- N-1 native Linux runtime is compile-tested only, not run-qualified.
  N-2 crabtables native profile; N-3 Intel host smoke; N-4 notarization +
  public release (owner); N-5 Rosetta on macOS 15.x.
- Silent daemon deaths ×9 — root cause unproven (Virtualization XPC
  helper). `conformance/watch.sh` supervises; no fix claimed.
- h12tiny-server pilot parked (negative/inconclusive); crabtables adapter
  not qualified on this kernel pair; default is the handwritten netlink
  path.
- Linux perf/size: not measured (no Linux runtime available this run).

## S7 (qemu-accel) — 2026-11-15: Linux artifacts (this host)

Local Linux release artifacts prepared on this AMD64 Linux host (Alpine
Linux 7.2.9-2-stable, kernel 7.2.9-2-stable, Ryzen 9 9950X ×32, docker
29.9.0). Notarization, the macOS row, hosted CI, tags and publication are
unchanged owner steps (N-4); this section changes nothing about them. The
macOS artifact above (CTRS-22, 2026-11-14, Apple Silicon) is untouched and
cannot be rebuilt on this host.

Built with the release-workflow Linux steps (fat-LTO `dist` profile,
`strip = true`, `codegen-units = 1`):

- x86_64: inside the pinned builder image (`rust:1.100.0-alpine@sha256:
de1e0058543a81ed7b046629167db587c67a94bdf37cce14eb27f0ec83baaffb` +
`musl-dev`/`binutils`/`git`, i.e. the repo `Dockerfile`), native AMD64,
with the repo-pinned `nightly-2026-11-09` auto-installed by rustup
(`rust-toolchain.toml` wins inside the image; the image's stable is not
used — same as ci.yml).
- aarch64: cross-compiled with the pinned cross toolchain
  (`messense/rust-musl-cross:aarch64-musl@sha256:02e790506c5f15a533bc05b3
af8719b16a8a2314480f6f0fdc0166432035d9b4` — rustc 1.96.1, gcc 12.4.0,
  aarch64 musl 1.2.x), natively on the build platform with
  `RUSTUP_TOOLCHAIN=stable` (the repo nightly ships no aarch64-musl
  std there); never a target emulator. Same path as `cargo xtask linux
  --arch arm64`.

| Artifact | sha256 | Bytes |
| --- | --- | --- |
| `ctrs-x86_64-unknown-linux-musl` (DYN/PIE, x86-64) | `9b286803b87abafdc991a0a78a3944fcd0042a98737bfb15a4bd68c4490fc7a6` | 5,801,440 |
| `ctrs-init-x86_64-unknown-linux-musl` (DYN/PIE, x86-64) | `600518cd640b06e667f961c35e538f6fc874660a32245687781e6e2bbebf0211` | 1,360,912 |
| `ctrs-aarch64-unknown-linux-musl` (EXEC, AArch64) | `14d58ad033aab6206792679c8a1b8f9e9b4abcf12834b094ccf04d5815dea4b5` | 4,854,504 |
| `ctrs-init-aarch64-unknown-linux-musl` (EXEC, AArch64) | `dd6d23ff7d8a1573f4ae785a56a9e689a50b1ad60a0f4ac3cdbcbb2dce7c9795` | 1,249,584 |

`.work/release/20261115/` is gitignored scratch; this file is the committed
manifest. All four are static musl ELFs — no `INTERP`, no `NEEDED` —
verified with `readelf` on the artifacts in the builder containers and on
the packaged copies. The x86_64 engine binary starts (`ctrs` prints usage;
exit 0 on the bare command). Actual AMD64 startup/build behavior of the
**packaged dist artifacts** was exercised end to end with
`BIN="$PWD/.work/release/20261115/check/bin" bash tests/linux-host.sh`
(result recorded in `docs/evidence/arm64-build.md`, S7 section). The
aarch64 engine binary cannot execute natively on this host; ARM64
execution here would go through the qemu binfmt handler, which is not a
proof. Artifacts were built from this tree; within one source state,
the rm -rf-fresh rebuilds reproduced byte-identical sha256s for all
four binaries (verified on this host).

### Zip payload (same shape `release.yml` packages)

| Zip | sha256 | Bytes |
| --- | --- | --- |
| `ctrs-x86_64-unknown-linux-musl.zip` | `efc09c635f61165464da99f70b5c4005feccdcf2ab80d450abfa65688fdca30a` | 2,345,782 |
| `ctrs-init-x86_64-unknown-linux-musl.zip` | `7fd4b7676b976be896b557ef30850dc86b6dc94059fbe2ba47a17abeaa818bf0` | 639,454 |
| `ctrs-aarch64-unknown-linux-musl.zip` | `aa57410d92ead0017040b87a3ae8bc8168f589e832ee1c79f8fbede6d370962a` | 2,156,231 |
| `ctrs-init-aarch64-unknown-linux-musl.zip` | `05820a849a39bc5dfdab322941611477a3c50658b7fbc7730379a97d0fd0425c` | 612,415 |

`zips/SHA256SUMS` (as the release job generates, `sha256sum *.zip |
LC_ALL=C sort -k2`): `sha256sum -c SHA256SUMS` → all four `OK`.

### Provenance (what is redistributed: these four binaries, nothing else)

- Build-only pins (not redistributed): the two builder images above; the
  BuildKit pin used to *drive builds* on this host
  (`moby/buildkit@sha256:aa632b921ef07411d2cb77292cd34213d4f7b384001d6fceef1e1f25bf9752bb`,
  v0.35.0); the qemu binfmt handler shipped by this host's system — none
  of these are in the payload.
- Release profile `lto = "fat"`, `codegen-units = 1`, `strip = true`. For
  local reproduction, `cargo xtask linux --arch <arch>` builds the
  `release` profile (thin LTO, `strip = false`) — same container/toolchain,
  different profile (x86_64 artifacts differ in size); add `--profile
  dist` to the container command to reproduce the workflow byte-for-byte.
- Sources: this repository at the commit this section lands in. Within
  one source state, the rm -rf-fresh rebuilds reproduced byte-identical
  sha256s for all four binaries (verified on this host).
- The shipped Linux binaries are not both built by the repo's pinned
  toolchain: the x86_64 pair is nightly-2026-11-09 (auto-install), the
  aarch64 pair is the messense stable 1.96.1 — the combination proven by
  this campaign (S4). The macOS row uses the pinned nightly.
- No separate emulator bundle is planned or included; the aarch64 binaries
  are native ARM64 code cross-compiled on AMD64.
- Dependency inventory: `docs/third-party.md` — 104 packages in the
  default build graph, all permissive; no GPL/LGPL/AGPL code is linked.
- Guest assets are unchanged and not in these zips (GPL-2.0-only kernel;
  `guest/kernel/SOURCE_OFFER.md` must travel with any distribution of
  them). The guest/x86_64 and guest/arm64 images were not rebuilt here.
- `LICENSE`/`NOTICE` were deleted at the owner's call (CTRS-22 record
  stands); attribution is carried in `README.md` only.
- SBOM scope: host engine + workspace; build-only tooling is not part of
  the artifacts.

### Not reproduced / still Needs environment

- macOS artifact (CTRS-22 row above) — no Apple Silicon host here.
- `.github/workflows/release.yml` has never been dispatched, and must not
  be from this campaign. Its aarch64 row was changed in S7 to
  cross-compile natively on `ubuntu-26.04` with the pinned toolchain (no
  qemu on that row; native ARM64 tests stay with ci.yml's `linux-musl`
  job on every push). Both Linux rows' exact step commands were
  reproduced on this host; hosted CI remains unobserved.
- ARM64 execution on ARM64 hardware; the `arm64-compat` CI job remains
  unrun (needs one authorized CI run).
- Publication: owner steps (N-4) — notarization, tags, registry publishes,
  the public release. No published artifact reference exists.

## Gate J (local)

Rename landed (`6f26f23`); gates A–I green in prior slices and re-green
here (see the CTRS-23 closeout); artifact manifested above. The remaining
step is owner-run: N-4 (notarization + public release).
