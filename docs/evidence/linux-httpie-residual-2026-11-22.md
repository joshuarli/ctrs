# Linux HTTPie residual first-use investigation — 2026-11-22

**Decision: no additional engine change qualifies.** The promoted H3 remains
the default. Three new residual hypotheses were declared, measured and rejected;
all engine edits are reverted. This does not close the remaining Docker gap,
and no macOS gate closes.

## Scope and frozen state

Base source: `27735335cb46534ca6bfd02927d068013360052a`. Both engines use
the same frozen native amd64 HTTPie 3.2.4 image archive and note bytes from
[the promoted H3 experiment](linux-httpie-2026-11-22.md).
Docker image:
`sha256:b5d73c6930d6ee20effd5aa62e5b1bd9efd04ff85b89db505bec13eebca60b06`.
Archive SHA-256:
`dbb2dac4a6d6e8f90f8ede8395038592fc3f706ec2e1a5025de1724cbb29bfde`.

First use is the same `run --rm ... http --version` boundary, including
create/start/app/exit/removal, with an untimed exact rootfs-note check.
The common Python base is warm; three app-only runtime layers are missing
before every ctrs trial. Docker uses its already imported image. This is
ordinary post-import engine materialization asymmetry, not equivalent empty
image stores. Build/load and layer reset are outside first use. No new build
speed or uncached-build claim.

Client and all observed live engine processes use CPUs **0–7**; containers
explicitly request that set. Each trial records live executable hashes and
affinity, not just a selected build. Baseline and candidates' embedded rustc
source hash matches:
`5b7b37aefcb5b2fba3c2392bc9065b9e4602d494`.

## Reachable profile and counter-controls

New daemon events and syscall/perf profiles reproduce the residual pre-create
boundary. These four profiler-off controls are **not scored cohort samples**:

| Engine/run | First use, s | Client→create, s | Create→start, s |
|---|---:|---:|---:|
| H3 ctrs, first | .516 | .267 | .017 |
| Docker, first | .538 | .040 | .077 |
| H3 ctrs, second | .472 | .260 | .010 |
| Docker, second | .452 | .042 | .081 |

Agent installs really execute through `agent::install_child →
layers::finish_job → install_blob → unpack → tar::Entry::unpack_in`.
The saved fork-worker traces contain file extraction and successful
`syncfs`/marker `fsync` barriers. The installed tar-rs
`validate_inside_dst` resolves both the destination and every entry parent.
The largest worker alone makes **51,812 readlink calls**, 2,983 lstat and
2,633 open calls. Its .762 seconds of traced readlink time is **perturbed**:
whole first use grows from roughly .5 to 4 seconds under strace. Do not use
traced durations as an exclusive or scored decomposition.

Independent CPU-clock perf has **429 samples, zero lost**, with **15.85%
self CPU** in zlib-rs's AVX2 inflate helper. This supports two real boundaries,
not an assertion that either alone causes the whole Docker gap. App init,
rootfs creation, metadata, syscall work and durability still contribute.

Disproof controls were retained:
- R1 really reduces aggregate install-worker readlink calls **52,046 →
  22,046**, adding 6,000 getcwd calls; write/open/lstat counts are unchanged.
  Despite removing that work, the scored latency gate fails.
- R2's independent perf has **424 samples, zero lost** and 14.62% self CPU
  in the same inflate helper. This small sampled contrast is not proof of a
  decode speedup or a critical-path decomposition.
- Perf's initial source-line lookup emitted an addr2line diagnostic.
  Flat symbol reports work with `--no-inline`; no source-line attribution
  is claimed. Missing optional `tips.txt` is not missing event data.

## Predeclared hypotheses and gate

- **R1:** extract from the fork-isolated worker's temporary CWD using '.',
  retaining tar-rs canonical containment checks and absolute root/blob paths.
  Relative inputs keep their prior behavior; parent CWD is untouched.
- **R2:** buffer bounded decoded gzip output at 64 KiB, allowing larger
  inflate calls for tar's short reads. No R1 CWD behavior in this attempt.
- **R3:** explicitly combined R1 + R2. Neither component is independently
  qualified. This is its own predeclared cohort, not pooled earlier results.

Each declares **ten alternating three-way rounds**, B,C,D / D,C,B:
current H3 baseline / candidate / frozen Docker. No replacements, reduced
inputs, outlier removal or post-hoc extensions. Primary is first-use wall time.
Required C/B paired-bootstrap upper bound **≤.95**, all correctness passes,
no >5% sampled CPU or >10% active anon+kernel regression, and strict resources.
The three-hypothesis bound is now exhausted. Attractive point estimates are
not grounds for a fourth attempt or extending a cohort.

## Scored results

Median **[Q1,Q3]**, seconds. Ratios are medians of ten paired ratios, with
2,000-pair bootstrap 95% intervals; not ratios of independent medians.

| Attempt | H3 baseline | Candidate | Frozen Docker | C/B [95% interval] | C/D [95% interval] |
|---|---:|---:|---:|---:|---:|
| R1 | 0.513 [0.495,0.551] | 0.491 [0.467,0.616] | 0.430 [0.423,0.437] | 0.985 [0.938,1.183] | 1.133 [1.106,1.634] |
| R2 | 0.529 [0.495,0.644] | 0.500 [0.485,0.527] | 0.439 [0.430,0.468] | 0.979 [0.744,1.041] | 1.148 [1.063,1.226] |
| R3 | 0.503 [0.488,0.527] | 0.457 [0.452,0.515] | 0.438 [0.427,0.451] | 0.937 [0.875,1.019] | 1.070 [1.016,1.156] |

**90/90 correct, 90/90 host-admitted; 89/90 resource-valid.** R1 pair 6
Docker reports `[Errno 19] No such device` and
`full cgroup ownership not verified`. It remains resource-invalid, not
zero or replaced. All 30 B/C pairs are resource-valid; R1 C/D has 9 valid
resource pairs, the other C/D cohorts have 10. All timing pairs are retained.

Resource medians below are **per-engine resource-valid trials**, not a
matched-nine-pair resource comparison to R1 Docker. Active footprint is peak
coincident anon+kernel among fully contained first-use periodic samples;
not page-cache-inclusive memory.current and not complete peak detection.

| Attempt | Sampled CPU s, B/C/D | Active peak MiB, B/C/D | Valid trials B/C/D |
|---|---:|---:|---:|
| R1 | 0.462 / 0.429 / 0.203 | 22.92 / 29.56 / 726.03 | 10 / 10 / 9 |
| R2 | 0.470 / 0.447 / 0.203 | 23.55 / 25.18 / 724.45 | 10 / 10 / 10 |
| R3 | 0.464 / 0.415 / 0.208 | 24.03 / 29.96 / 725.06 | 10 / 10 / 10 |

CPU remains a **sampled lower bound**, machine-marked incomplete. Full idle,
window peak and retained increments, all individual ratios, IQRs and invalid
receipts are in each analysis JSON. R3's promising latency point estimate and
lower sampled CPU are not qualified: its upper timing bound exceeds .95
and sampled active footprint exceeds the 10% guard. No broad memory or CPU
efficiency claim. All three candidates are reverted; H3 is unchanged.

## Correctness, evidence and operational state

Before each cohort, root-run ctrs-init tests and the unchanged existing
create/run/rootfs e2e sections pass:
- R1: **92 passed, 0 failed**; R2: **92 passed, 0 failed**;
  R3: **93 passed, 0 failed**.
- Each e2e subset: **135 passed, 0 failed, 17 skipped**. Skips are Mac
  bind-event forwarding cases. This is not a full-e2e rerun.

Added fork-isolated candidate tests cover normal/empty/corrupt extraction,
parent-CWD isolation and symlink escape rejection; gzip buffering also
checks many small entries across buffer boundaries. Existing gzip empty,
concatenated-member/truncation and traversal/whiteout tests remain.
Tests are saved with the rejected patches, not left as unrelated main edits.

Two preparation helper errors (missing Docker-inspect receipt, then starting
an already-active owned unit) were fixed before profiling. A non-executable
archived build helper was invoked via `sh`. An offline fresh test container
could not install the repository-pinned nightly toolchain; the corrected
untimed test setup uses the same network-enabled pinned Rust image/package
setup as the build. Both binary rustc hashes match. Failed setup logs remain.
No assertions were weakened.

Evidence root:
`/home/ubuntu/ctrs-evidence/linux-httpie-residual-20261122/`.
Manifest: [linux-httpie-residual-2026-11-22.sha256](linux-httpie-residual-2026-11-22.sha256).
It includes all schedules, declarations, freezes, raw records, copied resource
traces, stdout/stderr, profiles, source bundle, patches, analysis/audit scripts,
four binary pairs and the untimed e2e image archive. Original common archives
remain at their earlier durable roots and are not regenerated.

```sh
cd /home/ubuntu/ctrs-evidence/linux-httpie-residual-20261122
sha256sum -c /path/to/ctrs/docs/evidence/linux-httpie-residual-2026-11-22.sha256
python3 analyze.py r1
python3 analyze.py r2
python3 analyze.py r3
# Restore source from source.bundle at the recorded base, apply one saved
# patch, and adapt profile.py ROOT to that fresh worktree before a new run.
# Keep all archived records immutable; use a new evidence directory.
```

Analysis scripts reference the recorded source worktree's benchmark module;
restore that base (or adapt the path to an identical restored source) first.
The cohort command was `sudo env PATH=... python3 cohort.py rN`; the file
itself records exact Docker commands, layer-reset procedure, source/live
binary identities and CPU placement. Candidate build/test commands use
`rust:1.100.0-alpine@sha256:de1e0058543a81ed7b046629167db587c67a94bdf37cce14eb27f0ec83baaffb`,
`apk add -q musl-dev git`, `cargo build --release -p ctrs -p ctrs-init`
then `cargo test --release -p ctrs-init`.

Final audit: 90 correct/admitted trials, 89 resource-valid, exact schedule,
copied traces, live hashes/affinity, incomplete CPU preserved. Ctrs is stopped;
no ctrs process/firewall/link residue. All engine changes are reverted.
Host dockerd/containerd remain **PID 599/487**, active since
**2026-11-21 05:39:22 UTC**, unrestarted and unreconfigured.
Linux shares the host kernel; Mac retains its VM boundary.
