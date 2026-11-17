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

## Offline Rust compilation and export profile

`.work/tmp/w6-rust-offline-20261116/job`, durable ID
`51736a130ca44d35abe1a6cbd0337453`, exits 0 with clean owned teardown.
All three balanced pairs compile hyperfine 2.0.0 without cache, run its 132
tests with zero failures/ignores, and execute the loaded native binary with
the expected version. All six executable hashes equal
`c63f2e928959ea44b58db0f341f729c327571a18950a742f34c1371e3879c49b`.
All 81 frozen input receipts rechecked unchanged.

The diagnostic uses host candidate 58f64738… and the same guest/resources and
default-driver versions as the C case. Source and Rust base remain pinned.
Dependencies are vendored before work, outside the parent Cargo workspace,
without changing the source or lock. The original lock SHA-256 is
`190e5ac0a53fb5ceb73136b275f21ac9591fddfadcdc28dd0bb4a67dd84b3d83`.
Each of 134 registry packages matches its lock checksum and all 6,333 vendored
files match Cargo's checksum manifest. The immutable 24,694,346-byte archive
is 58eae402…. Both engines receive identical bytes and build with network none
and Cargo offline. This is a new diagnostic variant; it does not qualify the
unchanged original fixture's timed dependency-download behavior.

Unqualified median (range), seconds, three builds per engine:

| Boundary | ctrs | OrbStack |
| --- | --- | --- |
| Build command through loaded image | 38.657 (37.505–40.354) | 41.639 (39.287–42.644) |
| Compile and test vertex | 31.737 (29.724–33.965) | 32.582 (30.912–32.768) |
| Export vertex envelope | 5.742 (5.152–6.715) | 6.867 (6.368–7.291) |
| Exporting-layers status | 5.289 (4.706–6.125) | 5.555 (4.935–5.635) |

ctrs pushing-layers status in the first pair is 0.401 seconds versus 4.706
seconds exporting layers. This localizes a potential export-production cost;
it does not prove compression is the entire cost. ctrs physical peaks span
4,494,941,648–7,532,670,568 bytes; OrbStack's shared scope remains confounded.
No qualified speed, parity, memory or aggregate claim follows.

The next screen changes only new-layer gzip compression levels through the
existing exporter interface. The pinned [BuildKit gzip implementation](https://github.com/moby/buildkit/blob/v0.35.0/util/compression/gzip.go)
accepts a custom level and can use a different diff-computation path for it;
attribute support alone cannot establish an improvement. Three rotated rounds
of default/level 1/level 3 will assert identical executable bytes/tests and
record whole build, CPU, physical footprint, compressed layer bytes and allocated
blob bytes. The declared screen requires at least 5% whole-build/CPU reduction
and at most 3% growth in added and total compressed layer bytes before considering
a default change; exclusive confirmation remains required. No force-compression
or recompression of shared base layers, no product setting changed yet.

| Artifact under the Rust-profile root | SHA-256 |
| --- | --- |
| `plan.json` | ce07ed439e136d1d660828b1c8213d3644b08790c28fd68cd5fd333a42b241bb |
| `job/status.json` | 2c82cda64dd2bbb3185d0b80f24363776176385a5fe1b4433033b0ae8513a712 |
| `analysis.json` | e24283ca97c3a981042eec24c8d56ae61742f4b358ae93fa039a8fa3442db997 |

## Lower gzip levels rejected

The original screen dff9fcb… exits 1 after its first default build, with clean
owned teardown. A scratch accounting lookup assumed a `diff_id` field in store
layer records. Actual records have digest, size and media type. The corrected
v2 checks the base's uncompressed diff-ID prefix through image inspection, then
counts the following store layers. The original failure is preserved separately.

Fresh v2 job `.work/tmp/w6-compression-screen-v2-20261116/job`, ID
`3b197f66b44242799a7c1f0de83379b3`, exits 0 with clean owned teardown. All nine
planned builds execute compile/tests without cache, each passes 132 tests, and
every executable equals c63f2e92…. All 83 frozen receipts remain unchanged.
Three rounds rotate default/level 1/level 3 through the same per-round context;
the default builder and explicit docker exporter are common to all conditions.

Unqualified medians (ranges), three builds per condition:

| Condition | Whole build, seconds | Export envelope, seconds | Added compressed layer bytes |
| --- | --- | --- | --- |
| Default | 31.730 (30.396–32.487) | 4.622 (4.487–5.350) | 147,603,185 (147,601,327–147,604,030) |
| Level 1 | 28.489 (28.076–32.922) | 1.979 (1.973–2.037) | 162,550,009 (162,549,626–162,550,016) |
| Level 3 | 29.551 (29.359–30.034) | 2.585 (2.564–2.663) | 154,284,522 (154,284,244–154,284,882) |

Both configurations are **rejected for the default**. Added compressed bytes
grow about 10.13% and 4.53%, respectively, exceeding the predeclared 3% budget in
every round. Total-image ratios hide this cost behind a common large base and
cannot override the added-layer guard. Allocated new-blob bytes independently
follow the same growth. Level 1's third whole-build/CPU ratios exceed 1.0; level
3 also misses the 5% median CPU screen. No timing or CPU speed claim is qualified,
and no compression default changed. The profile identifies a real export tradeoff,
without establishing an acceptable default optimization.

Native sampled physical footprint grows from about 4.6GB to 15.7GB over the
sequence. The resident control deliberately disables VM sleep, keeps all result
images until final ownership cleanup, and preserves builder caches. This is not
evidence of a leak or an installed-default resource regression. Source also
delays balloon shrink for 120 seconds to protect next-use latency. The next
experiment isolates whether inflation returns native physical memory or mainly
evicts guest cache before selecting any reclamation change.

| Artifact under the v2 screen root | SHA-256 |
| --- | --- |
| `plan.json` | baaa4b07c63d6a6d235a8f27baacd32d5167573cd0ccd6eaf06e0072b75186bf |
| `job/status.json` | 695faf5944e5a46d080cff14cbee55d0cb26c94fe707d1c1c414bfb4c2b3f056 |
| `analysis.json` | c7f517dd09accc58b80323adc2bfabc4d41f60236aae9c67a8fe631b7665557f |

## Default multi-stage W7 profile, 2026-11-17

`.work/tmp/w7-offline-rust-profile-20261117/job`, ID
`f371a2bb92c04d2ea2128b9ad6b14ae3`, exits 0 with clean owned teardown.
All 18 builds and executable/version/note probes pass across three balanced
engine pairs and uncached, warm and one-file incremental states. Compilation
executes in every uncached case and is cached in every warm/incremental case.
All 99 frozen input receipts remain unchanged. The existing multi-stage
hyperfine fixture gains the same frozen vendored archive used above; Cargo runs
offline with network disabled. Runtime ships the binary and note on pinned
Debian, rather than exporting the compiler workspace.

The ctrs side uses tested host fda62467… and actual initrd 6ae4d3ab… with stock
kernel, 17vCPU/45,091MiB and resident control. Default docker drivers and their
different BuildKit versions remain disclosed. All timing is ineligible: host
activity and shared OrbStack CPU scopes prevent a comparative verdict. No
avoidable ctrs export/load loss was selected from this screen.

For trace inspection only, ctrs build-command medians (ranges), three per state,
are 15.378s (15.173–15.663) uncached, 0.376s (0.319–0.377) warm and 0.461s
(0.345–0.493) incremental. Its separately bracketed verified-run command spans
0.029–0.044s. The first incremental export envelope is 0.061s; the compile and
binary-copy vertices are cached, while the changed note layer executes. These
numbers establish neither qualified speed nor parity. Build and run commands
are separated by diagnostic inspection; their published medians must not be
summed into a command-to-run metric. Raw records retain both boundaries and
all OrbStack samples, including contaminated large CPU totals.

The next experiment returns to demonstrated native memory retention: the VZ
SDK recommends guest compaction before ballooning. A bounded AB/BA probe tests
that recommendation in the owned guest, with actual balloon/cache/native memory,
peak/idle CPU and exact next-read checks. It changes no product default and
cannot establish pressure-dependent reclaim without further evidence.

| Artifact under the W7 profile root | SHA-256 |
| --- | --- |
| `plan.json` | b390cf1617f837fbdb70529aae68ea723d716567cd654e66f234fb75ba04fb7f |
| `job/status.json` | b77ac41fa7f80961bea04dea1b85407e8139fce06936aa9c4d4e8032741835cc |
| `analysis.json` | cbabe48d680d4ea75820ca877a167efb95676a5042458eeae260a6a90dd7a6b7 |
