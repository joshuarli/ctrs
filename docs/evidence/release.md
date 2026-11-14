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
  kernel/disk build containers, the `rust:1-alpine` linux build container)
  is not part of the shipped artifact.

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

## Gate J (local)

Rename landed (`6f26f23`); gates A–I green in prior slices and re-green
here (see the CTRS-23 closeout); artifact manifested above. The remaining
step is owner-run: N-4 (notarization + public release).
