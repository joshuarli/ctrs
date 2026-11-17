# Native default-build boundary experiments, 2026-11-16

These are diagnostic experiments on a shared Mac, not performance qualification.
The C build profile found no export/load loss requiring a change. It exposed an
image-inspection defect, fixed separately with a failing-baseline regression.

## Host-window rejection

The canonical W2 observer job
`.work/tmp/w2-observer-clean-20261116/job`, ID
`c8051c089948484b9de838819d6812fe`, exited 1 before starting its first block.
The strict preflight retained a hot OrbStack Helper warning despite exit 0.
No observer pair completed; do not restart this receipt or replace its blocks.

The separate read-only guest CPU probe
`.work/tmp/orb-idle-attribution-20261116/result.json` found active `rustc`
processes with `cargo` as parent, despite no listed Docker containers.
`orbctl list --format json` also reported the running `bctl-r7-qualify` Linux
machine. Neither observation proves that these are the same job. Both show why
an empty Docker container list cannot establish exclusive use of OrbStack's
helper. Unrelated work was preserved. Timing and observer acceptance are deferred.

## C compilation and export profile

Raw coordinator, plan, receipts, traces, resource samples and analysis:
`.work/tmp/w6-zlib-profile-20261116/`. Durable job
`2ebe4185fbb64bbbbd7a985884e10879` exited 1 with four refused image deletions;
all six planned builds and artifact checks had completed before cleanup.
The original failed receipt remains unchanged.

The three pairs alternate ctrs/OrbStack, OrbStack/ctrs, ctrs/OrbStack, using
the same per-pair context and pinned zlib 1.3.1 archive. Both use their normal
`docker` driver, `buildx build --load --no-cache --network none`, a prewarmed
builder/base, and the Dockerfile's configure, parallel make and make-check.
This is the C half of W6, with retained stores, not a cold or complete W6 cell.
The compiler image is pinned at `gcc:14.2.0-bookworm@sha256:b99b86a…` in the
unchanged fixture. ctrs uses host 37bec61b…, stock guest 35087713…, 17 vCPUs
and 45,091MiB. Docker CLI 27.3.1/buildx 0.22.0 is shared; default BuildKit differs:
ctrs 0.35.0, OrbStack 0.33.1. No version change is credited to ctrs.

All six compile/test vertices executed without cache hits; only the base was
cached. Every runnable result produced the same library SHA-256:
`6b6ba12f2f7ed1e8c7ebe08480e408394c8e66aebec862a10494fb2dc415914b`.
The native architecture and example program also passed. All 78 frozen input
receipts rechecked unchanged.

Unqualified phase observations, median (range), seconds, three builds per engine:

| Boundary | ctrs | OrbStack |
| --- | --- | --- |
| Build command through loaded image | 0.990 (0.965–1.117) | 1.747 (1.681–1.850) |
| Configure, compile and test vertex | 0.481 (0.479–0.581) | 0.574 (0.530–0.676) |
| Export vertex envelope | 0.179 (0.177–0.179) | 0.408 (0.347–0.412) |

Vertex envelopes use earliest start/latest completion for each digest because
export progress can restart the same vertex. Vertices can overlap; do not sum
them into command wall time. No ratio, confidence interval, speedup or parity
claim follows from this busy-host screen. OrbStack CPU/footprint includes
unrelated Linux-machine work. Native sampled ctrs physical peaks were
1,762,397,976–1,884,835,848 bytes; these do not establish idle or storage budgets.
The next build boundary is the Rust application with frozen vendored dependencies,
so timed compile/test cannot include WAN fetches.

## Image-label repair

ctrs preserved labels in image config blobs but omitted `Config.Labels` from
inspection. Consequently the campaign's ownership check refused all four ctrs
image deletions; it did not guess ownership or force cleanup. Commit 241c4c9
projects the stored labels and reuses one config read/parse for rootfs,
healthcheck and labels. Runtime formats, guest code and durability are unchanged.

The named regression is
`python3.14 conformance/image-labels.py --ctrs-binary /path/to/signed/ctrs`.
It loads tiny owned archives without booting a guest or using a registry.
Baseline 37bec61b… fails only the populated-label assertion in
`.work/tmp/image-labels-yo6_xdz7/`. Candidate 58f64738… passes populated,
empty and absent labels, exact image identity, healthcheck, environment, command,
user, working directory and rootfs in `.work/tmp/image-labels-6ytlk0fk/`.
Both daemons exit 0 with no cleanup errors. The affected rootfs Rust regression
passes (one selected test, 181 filtered); six-job release build takes 12.29s.
The signed candidate is 6,613,856 bytes, equal to the baseline. Full suites remain
manual-only. This is a correctness repair without a measured performance claim.

The repaired candidate then inspected the retained warm-root tags, checked their
exact campaign label, recorded IDs and removed only those four tags.
`owned-label-recovery.json` preserves this separate successful recovery; it does
not turn the original job's exit 1 into a pass.

| Artifact under the C-profile root | SHA-256 |
| --- | --- |
| `plan.json` | ecaca3d02f705c3f710c73e446924483a169c2636a1abe147dd21ee15f80be08 |
| `job/status.json` | 8eb8093ac5cc317ae58c229d884830f325fcccdb3f79be0ff4b1ce0d6bfe4f6b |
| `analysis.json` | 2c1642d447a4b6193fb2b298c4e4892bb0b8408ee782c6bc98b105302c954154 |
| `owned-label-recovery.json` | 94a5ddaa65f2c769cd522d5a53b4879235bce25b4d278c1fe1cef77e913d337c |
