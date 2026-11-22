# macOS performance campaign: progress and continuation

## Wound down 2026-11-20

The owner paused the campaign on 2026-11-20. No gate in
[the campaign contract](campaign-native-performance.md#finish-criteria-coverage-parity-leadership)
has passed, and no cell is qualified. Every measured job was stopped. The
raw results, fixtures, warm engine copies and traces under
`.work/native-perf/` (103 GB) were deleted with the rest of `.work/`, so
the only record left is the evidence and decision docs. Every cohort run
must be measured again.

### Where ctrs stands against OrbStack

Host: M1 Max, 10 CPUs, 64 GiB, macOS 27.2.1, OrbStack 2.2.5. These are
D-lane pilots and none is qualified. Smaller numbers favor ctrs.

- **Wins:** W2 latency, throughput and footprint (rps 0.746, p99 0.612,
  footprint 0.313). Every W3-v4 timing, though it is not claimed until
  the flush contracts are shown to be equal. W6 Rust 0.953
  (non-inferior) and zlib 0.641. W7 wins every cell except the uncached
  build, which is 0.997 (non-inferior). Historical W14 streaming,
  reconnect and persistent CPU. Current W14 idle-resume cleanup and footprint.
- **Losses:** W12 full-bind, about 1.25–1.33× (the Mac virtiofs share).
  W2 fixed work uses 1.250× the measured engine CPU per request.
  W14 idle-resume p50 is 1.128×.
  The current 9-vCPU W13-overlap cohort still has a CPU loss (1.097×).
  Its W2 p99 and throughput are inconclusive. The old 5-vCPU cohort
  recorded a 1.70× p99 loss. See the [current overlap evidence](#installed-default-w13-overlap-cohort).
  Other CPU-only losses:
  W12-watch 1.07×, published-port upload CPU/GiB 1.08×, W14 fresh
  ~1.02–1.15×.
- **Tool-limited or inconclusive:** guest→host bulk transfer is now
  0.72–0.94 (it was 5–7× before the NAT relay and splice work).
- **Unscored:** W1, W4, W5, W8, W9, W10 (pilots at most). W11 12-hour
  reliability was never run. Its admission branch
  `origin/campaign/w11-bind-completed-cycles` is parked and unmerged.

Ranked detail is in
[the matrix](native-acceptance-matrix.md#ranked-orbstack-deficits-this-host)
and [the W12/W13 evidence](evidence/native-w12-w13-2026-11-18.md#ranked-measured-deficits).
Decisions, including the vCPU default and kernel patch 0017, are in
[decisions.md](decisions.md).

### Integrated at wind-down

- Kernel patches 0013–0016 (watcher recovery, `f291b04`) and 0017 (a
  bound on live virtiofs inodes, so a large bind walk can no longer
  exhaust the Mac's file table) are on main. Both guest architectures
  build on Linux (resume step 4); Mac boot/runtime checks remain: run
  `tests/watch-recovery.sh` and `tests/fuse-inode-bound.sh` before any
  measurement. 0017's descriptor results come from the session that
  wrote it and were not run again here.
- Linux development bootstrap: `scripts/setup-dev`, documented under
  "Linux development setup" in [development.md](development.md).
- Abandoned at wind-down: the two-virtiofs-device probe
  (`exp/fs-devices`, `CTRS_EXP_SHARE_DEVICES`). It got one noisy run at
  1.2–2.5× files/s and was never repeated in a quiet window. Its one
  commit is pushed to `origin/exp/fs-devices`.
- Never ran: queue q7 (`w13-overlap`, `w2-api`, `w6-build`, `w7-buildx`
  and `w14-idle-resume` cohorts at the 9-vCPU default against OrbStack).

### Resuming

**On a Linux host.** On Linux, ctrs runs its agent directly on the host
kernel, and the baseline is the Docker daemon on the same host (normally
Docker Engine: dockerd with containerd), not OrbStack. The native amd64
lane and adapter are implemented; its results never pool with the macOS
cells, and the macOS gates above stay open until measured on a Mac.
Resume from the [recoverable Linux checkpoint](evidence/linux-amd64-checkpoint-2026-11-22.md)
and its committed SHA-256 manifest, not from a new adapter implementation. Steps:

1. `./scripts/setup-dev`, then `make test` and `make lint`. Run
   `ctrs-init`'s Linux-only tests as root:
   `cargo test -p ctrs-init --target <arch>-unknown-linux-musl`.
2. Bring up the Linux engine (`cargo xtask linux --arch amd64`; run
   `tests/linux-host.sh` and `tests/kernel-features.sh` in a privileged
   container) and run `tests/e2e.sh` against it and an owned disposable
   Docker daemon. The suite uses fixed names and prune labels: never run
   it against a concurrently used daemon. Preserve integrated logs and
   active firewall deny/allow controls, not just post-stop rule snapshots.
   **2026-11-22: [integrated Linux runtime result](evidence/linux-integrated-runtime-2026-11-22.md)**:
   current-main ctrs **482/1/26**, fully isolated Docker **471/2/30**
   (pass/fail/skip). Remaining failures are host VRF support on both and
   Docker's default AppArmor mount restriction. During-operation deny/allow,
   scoped exceptions and cleanup are verified; host `docker0` was repaired
   with approval, without a daemon restart. Frozen independent image-store
   restoration and future sudo provenance are verified. No macOS gate closes.
3. Use the existing `--lane linux-amd64` path in `runner.py`/`pyramid.py`
   with engines `ctrs` and `dockerd` for W2, W6, W7 and W13. Restore
   `linux-amd64-v1` using `prepare --linux-archive`; do not regenerate its
   lock. Native x86_64 only, no architecture fallback. Docker baseline:
   Engine 29.9.2 (`0367cbe`), kernel `6.8.0-1060-aws`, systemd cgroup v2,
   overlayfs. Accounting is cgroup CPU and `memory.stat` anon/file/kernel;
   footprint is coincident anon+kernel, with `memory.current` secondary.
   The checkpoint records containerd/runc, binary/source identities,
   strict ownership limitations and verified retrieval/restore commands.
   **2026-11-22: [W2 observer/profile/experiment result](evidence/linux-w2-2026-11-22.md)**:
   fixed 50,000ops/C8, bounded observer, six Linux path/engine controls and two
   predeclared 30-trial cohorts. All 60 cohort trials correct/admitted; 58 resource-valid
   (two strict Docker ownership failures retained). Seccomp dispatch and adaptive
   small-message relay candidates did not meet the p99 interval win gate; both
   reverted. Evidence/binaries/raw traces preserved under `~/ctrs-evidence/`.
   Dominant application/shared-DB-connection work is not an established engine
   defect. No macOS gate closes; HTTPie has not started.
   The earlier Linux pilot remains descriptive, not qualification.
4. **2026-11-20: build proof complete.** All patches 0001–0017 applied
   and Linux 6.18.58 built from empty Docker cache volumes on an 8-CPU
   x86_64 Linux host; no patch fixes. With `CARGO_ENCODED_RUSTFLAGS=""`,
   `cargo xtask kernel` built AMD64 in 186.10 s (Linux defaults to the
   host arch); `cargo xtask kernel --arch arm64` built the Mac's ARM64
   guest in 212.01 s. Wall times include package/source downloads;
   AMD64 also includes the cold image pull. SHA-256 (`sha256sum`):
   - ARM64 `guest/out/Image` (18,802,696 bytes):
     `f953d09d34b0f3fe5ca2fd089727ce64ee6e9942ba2c52a896a769477d7c2225`.
   - AMD64 `guest/out/x86_64/bzImage` (10,400,768 bytes):
     `67032e023cb67185ff1746b2ed4ab8130c76d7723c56402b4ceacaf4a5933b4e`.
   Builder: `debian:trixie@sha256:9c6e381421d0f48d1b8133e573f33c185ee16cbf505eda9c4a8a4791b25ea8a6`
   (linux/amd64); GCC / aarch64-linux-gnu-gcc 14.2.0 (Debian
   14.2.0-19), GNU ld 2.44; Docker client/server 29.9.2; xtask Rust
   nightly-2026-11-09 (`rustc 1.102.0-nightly`, `5b7b37aef`). The image
   is pinned, apt packages are not. Hashes include build timestamps
   (host clock 2026-11-21 UTC); this is build proof, not Mac runtime
   qualification. Run both watch tests on the Mac before measurement.
5. Offline harness work (`make test-bench`) runs anywhere. W11 frozen
   admission is integrated; qualification still needs the Mac evidence below.

**On the Mac.** Rebuild the assets (`cargo xtask all`) and run e2e and
the two watch tests. Restore the [pinned common portfolio](../bench/native/fixtures/w8-v6/README.md)
and prepare [W12](../bench/native/fixtures/w12/README.md) before their
cohorts. Run the installed-default cohorts through
`bench/native/pyramid.py run --name <cell>:cohort` and refresh the ranked
deficits. The first optimization target is W12 full-bind.

## macOS resume setup — 2026-11-22

The Mac is the campaign host (M1 Max, 10 CPUs, 64 GiB, macOS 27.2.1,
OrbStack 2.2.5; Docker CLI 29.8.2, Compose v5.5.0, buildx 0.37.2). The tree
was clean at main `5cac40d`; two harness fixes landed at `e98575a` (e2e:
macOS VM kernel detection and a keychain-free scratch credential helper) and
`51267cd` (watch: wait for the overflow-batch flush before asserting).

Fresh assets built from that source, including kernel patches 0001–0017:
`guest/out/initramfs.cpio` SHA-256 `fbed2ff9c71d46718d9e55993e54cfab0ee72b349dcd9cfc6f735a310ab6954d`
(4,400,252 bytes), `guest/out/Image` SHA-256 `19657ca4cc150ae8d04d003ac494676bcc5845dd3a3a21cd6bfb17df605d4e6f`
(18,802,696 bytes), signed `target/release/ctrs` SHA-256
`d59eff1a7f5576a7d49e6e5edf0d5d64740fdc0f49c8e4729ce344d08c534796`
(6,738,544 bytes, `codesign --verify --strict --verbose=2` clean). The sparse
1 TiB `data.img` was retained from the earlier host reconstruction.

Boot/runtime gates on those assets: `conformance/smoke.sh` 21/21;
`tests/watch-recovery.sh` exit 0 (host-loss, guest-overflow, capacity and
oneshot cases); `tests/fuse-inode-bound.sh` exit 0 (150,000-file walk, peak
65,575 descriptors under the 73,728 limit, recovery to 57); `tests/e2e.sh`
507 pass / 2 fail, where both failures are Docker Hub 429 rate limits on the
optional Rosetta pulls (`amd64/alpine:3.22`, `node:22-alpine`), not engine
results. These setup checks preceded the resumed cohorts.

`bench/native/runner.py prepare` succeeded on both engines. W12's
`fixtures/w12/prepare.py` fails closed: the source archive and lock match
their pins and the first five diff IDs match, but the rebuilt
`np-w12-kutt:proof` has different final layers and image ID from
`workload.json`. The unmatched image was removed; W12 needs a reviewed repin
or a new fixture version before its cohorts can run. `pyramid.py` preflight
passes for `w13-overlap:cpus9`, `w2-api:cpus9`, `w14-idle-resume:cpus9`,
`w6-build:cpus9`, `w6-build:cohort` and `w7-buildx:cohort` (320 GB free, no
foreign daemon); W12 cells fail on the missing `w12-image.tar`.

The signed binary already uses the adopted all-but-one CPU default
(`b663920`). The resumed W6 run observed 9 vCPUs on each engine. The old
`:cpus9` queue targeted a 5-vCPU incumbent. Use the `:cohort` jobs for
the installed-default comparison on this build.

The first resumed overlap launch (`base-20261122T063600-88f3`) stopped
after two failed pairs. The default and cloned ctrs stores lacked the
pinned API and PostgreSQL IDs. Plain `prepare` had installed the old
floating-tag pilot inputs. The OrbStack store also lacked the pinned API.
The pinned PostgreSQL and Redis manifests remain available from their
upstream digest references. The old common layout and W12 image archive
were lost with scratch. Recover their exact private-built images from an
archived artifact if available. A rebuild that changes an image pin
requires a new fixture version and fresh results for its consumers.

W6 and W7 completed independently of the common portfolio. The replacement
v6 portfolio passed its functional proof and the W13 overlap cohort.
The published-port fixed-work W2 and W14 idle-resume cohorts are recorded
below. Use `reporting.py --match <run>` to summarize their trials. Use
Python 3.11 or later. On this host
the supported interpreter is `/opt/homebrew/bin/python3`.
For hand-run watch tests, use a gate path with no extension so the daemon
derives `<gate>.overflow`, point `CTRS_DAEMON_LOG` at the daemon's readable
stderr capture, and include `/usr/sbin` in PATH for `lsof` in the inode test.

### W3 migration and committed-state cohort

`pyramid.py run --name w3-migration:cohort` runs the declared migration,
300-transaction mix, checkpoint and PostgreSQL restart with the v6 image
pin. The pair verifies identical migration and transaction SQL. CPU per
transaction uses the transaction phase and the count verified against
committed state after restart.

Native admission run `base-20261122T093602-8149` at `e95ffa2` delivered
one valid installed-default pair. Each engine verified all 300
transactions after restart, matched the PostgreSQL manifest and both SQL
hashes, and returned a transaction CPU phase without errors. Both engines
observed 9 vCPUs. The 10-pair cohort and equivalent host storage durability
remain open.

```sh
python3 bench/native/runner.py baseline --case W3 --a ctrs --b orbstack \
  --resource-lane installed-default --pairs 1 --pair-quiet-load 4
python3 bench/native/reporting.py --match base-20261122T093602-8149
```

`trials.jsonl` SHA-256
`15658c72db794c6420bde922dfb8cce4bfaf9550a8112f7b64f827666ddde045`.

### Installed-default W6 cohort

Run `base-20261122T063709-0627` used harness source `2910f31` and the signed
binary and guest hashes above. The default drivers retained base images
and compiled and tested Hyperfine 2.0.0 and zlib 1.3.1 with `--no-cache`.
All 10 alternating pairs verified the compile steps and both artifact
hashes. There were zero failures, rejections or missing footprint samples.
Both engines observed 9 vCPUs. Guest MemTotal was 8,407,957,504 bytes on
ctrs and 63,157,620,736 on OrbStack. The maximum measured outside-engine
CPU in any build phase was 0.77 cores.

| Metric | ctrs / OrbStack paired median | 95% CI | Descriptive result |
| --- | ---: | ---: | --- |
| Sampled peak physical footprint | 1.3642 | 1.1823–1.4851 | Loss |
| Summed peak RSS | 1.6781 | 1.5020–1.7506 | Loss |
| Rust build | 0.9439 | 0.9320–0.9507 | Non-inferior |
| zlib build | 0.5242 | 0.5126–0.6433 | Strict win |
| Engine CPU | 0.9549 | 0.9447–0.9696 | Incomplete host NAT accounting in all ctrs trials |

The physical-footprint medians were 8.64 GB and 6.33 GB. At every ctrs
peak, the VZ helper accounted for over 99.8% of the sample. The first
build started at 0.41 GB and reached 8.62 GB. The following nine trials
already started just above 8.62 GB. The trace localizes the retained
memory to the VM helper. Guest active, cache and balloon counters are
needed to explain the retention. Measure those alongside host footprint
with the next-use check before changing reclaim policy.

```sh
export PATH="/opt/homebrew/bin:$PATH" TMPDIR="$PWD/.work/tmp"
python3 bench/native/pyramid.py run --name w6-build:cohort
python3 bench/native/reporting.py --match base-20261122T063709-0627
```

`trials.jsonl` SHA-256
`d1fe8a523db792ebf118804489839db138f0af704d8be8858d9700a71aa9203e`.
This covers uncached builds under installed defaults. Warm builds,
complete CPU accounting and fresh confirmation remain open.

Screen a 6144 MiB ceiling against the installed default with
`pyramid.py run --name w6-build:memory6144`. The VZ helper supplied
nearly all of the observed peak. If resident guest pages dominate that
footprint, the lower ceiling should reduce it while preserving the
compile and validation outputs. This test holds vCPUs, binary, guest
assets and workspace inputs fixed. Its screen requires ten valid pairs,
an upper 95% bound of 0.95 for peak footprint and an upper bound of 1.03
for each build time. Inspect the VM's observed ceiling, memory used,
target and OOM counters. The screen cannot establish CPU parity or
choose a new default. A useful result needs next-use, W2 and W7 checks
before a separate comparison against OrbStack.

The native admission smoke `base-20261122T080710-ebbc` tested the
8,192 and 6,144 MiB limits at 9 vCPUs (`fae1787`). Docker's `/info`
reported both exact ceilings and targets. Both uncached Rust and zlib
builds passed, and each artifact hash matched across slots. Both slots
recorded zero guest OOM kills, complete footprint samples and NAT usage.
One pair verifies the configuration and build outputs.
`trials.jsonl` SHA-256
`fc7c6e865a0f66cb4cab7a6558fadfe7e00237e57506eaadaf0c2faee44de515`.

The ten-pair screen `base-20261122T083610-c7a4` used clean source
`7eb4859`, the same signed binary and guest assets as the installed-default
W6 cohort, and fixed 9 vCPUs. All 20 builds verified the same Rust and zlib
artifact hashes. Every leg reported its requested ceiling and zero guest
OOM kills. All pairs passed admission with complete footprint samples.

| Metric | 6,144 / 8,192 MiB paired median | 95% CI | Screen |
| --- | ---: | ---: | --- |
| Sampled peak physical footprint | 0.7545 | 0.7511–0.9729 | Missed 0.95 upper bound |
| Rust build time | 0.9981 | 0.9897–1.0032 | Met 1.03 upper bound |
| zlib build time | 1.0216 | 0.9903–1.0272 | Met 1.03 upper bound |
| Measured engine CPU | 0.9989 | 0.9915–1.0170 | Incomplete |

Both slots used host NAT throughout. The first three pairs reached similar
footprints in both slots as resident usage rose between trials. The
6,144 MiB slot plateaued near 6.49 GB by pair four, while the default slot
continued up to 8.64 GB by pair six. The full ordered cohort missed the
predeclared footprint requirement. The smaller cap did not advance.
A future sustained-residency test needs its warmup declared before sampling.

```sh
export PATH="/opt/homebrew/bin:$PATH" TMPDIR="$PWD/.work/tmp"
python3 bench/native/pyramid.py run --name w6-build:memory6144
python3 bench/native/reporting.py --candidate --match base-20261122T083610-c7a4
```

`trials.jsonl` SHA-256
`e392a7879a158e4ba970a086d87de8984e2b65d581bdd84ac2120ef4a3d7d195`.

### Installed-default W7 cohort

Run `base-20261122T065539-5b0c` used harness source `2910f31`, the same
signed binary, guest assets and engine allocations as W6. Each engine
completed all 10 trials. Each trial built and loaded Hyperfine 2.0.0 and
HTTPie 3.2.4 in uncached, warm and one-file incremental states and ran
each image. BuildKit progress verified cache behavior. All expected
versions and per-build notes matched. No pairs were rejected. The
maximum measured outside-engine CPU was 1.49 cores.

All entries below are paired median ctrs / OrbStack timing ratios with
95% confidence intervals.

| App and state | Build and load | First use |
| --- | ---: | ---: |
| Hyperfine uncached | 0.886 [0.875, 0.893] | 0.114 [0.090, 0.121] |
| Hyperfine warm | 0.416 [0.363, 0.422] | 0.058 [0.057, 0.061] |
| Hyperfine incremental | 0.267 [0.259, 0.278] | 0.074 [0.071, 0.078] |
| HTTPie uncached | 0.783 [0.771, 0.799] | 0.589 [0.574, 0.605] |
| HTTPie warm | 0.417 [0.412, 0.426] | 0.295 [0.291, 0.309] |
| HTTPie incremental | 0.308 [0.297, 0.329] | 0.313 [0.302, 0.326] |

All twelve timing cells cleared the strict-win threshold under the
installed defaults. The cohort does not isolate which build or engine
phase drives the differences. Sampled peak physical footprint was
inconclusive at 1.088 [0.923, 1.345], with all pairs sampled. Engine CPU
remains incomplete because all ten ctrs trials used host NAT. W7
remains open for resource parity and independent confirmation.

```sh
export PATH="/opt/homebrew/bin:$PATH" TMPDIR="$PWD/.work/tmp"
python3 bench/native/pyramid.py run --name w7-buildx:cohort
python3 bench/native/reporting.py --match base-20261122T065539-5b0c
```

`trials.jsonl` SHA-256
`fffe7fcb953d0692a0b093cf21a6475e465ec316b71b158ea0a2ceb1e9373aba`.

### Installed-default W2 fixed-work cohort

Run `base-20261122T081048-91d4` used clean source `7eb4859`, the same
signed binary and guest assets as W6, and the v6 API, PostgreSQL and Redis
pins. All ten alternating pairs matched their image, SQL seed, client and
API file receipts. Each leg completed 50,000 requests with eight clients
through the published port, verified every persisted write, and recorded
zero errors. Both engines observed 9 vCPUs with the W6 memory allocations.
Maximum outside-engine CPU during load was 1.00 core.

| Metric | Paired median ratio | 95% CI | Descriptive result |
| --- | ---: | ---: | --- |
| Measured engine CPU per verified request | 1.2499 | 1.2347–1.2594 | Loss |
| Sampled peak physical footprint | 0.3129 | 0.3025–0.3276 | Strict win |
| Request rate (OrbStack / ctrs) | 0.7458 | 0.7366–0.7551 | Strict win |
| API p50 | 0.7477 | 0.7410–0.7555 | Strict win |
| API p95 | 0.6720 | 0.6576–0.6820 | Strict win |
| API p99 | 0.6124 | 0.5977–0.6331 | Strict win |

Lower ratios favor ctrs. All ten ctrs legs used host NAT (81 connections).
The host kernel's NAT CPU is outside the engine counters. The median
workload-phase engine CPU was 48.87 s on ctrs and 39.03 s on OrbStack.
The API cgroup recorded medians of 26.61 s and 21.06 s respectively,
including counter-reader execution. On the host, the ctrs VM helper used
46.68 s and the ctrs daemon used 2.17 s. OrbStack's helper used 39.03 s.
The process split puts most of the measured gap in the VM helper. It
does not attribute that time to guest scheduling, transport, or app code.
Run the eight-client guest-direct cohort and the paired fixed-rate
conditions next. Guest-direct engine CPU includes the in-guest load client,
so compare its engine totals within that placement.

```sh
export PATH="/opt/homebrew/bin:$PATH" TMPDIR="$PWD/.work/tmp"
python3 bench/native/pyramid.py run --name w2-api:cohort
python3 bench/native/reporting.py --match base-20261122T081048-91d4
```

`trials.jsonl` SHA-256
`5aefe93dc8901170f7191adfbd2710abea89ff69628f8c9118f53327e2d0cb67`.

### Installed-default W13 overlap cohort

Run `base-20261122T073402-7351` used harness source `6278898`, the W6
signed binary and guest assets, and the v6 API, PostgreSQL and Redis
pins. Both engines used 9 vCPUs. Guest MemTotal was 8,407,957,504 bytes
on ctrs and 63,157,620,736 on OrbStack 2.2.5 (Docker 29.8.2).
All ten alternating pairs passed with zero rejections or missing resource
samples. Each trial verified the application work and a single
published-port upload of a 1 GiB artifact repeated 96 times. The
receiver reported 103,079,215,104 bytes with the expected hash, and
receiver timing covered the entire 20,000-request API window in every
trial. Maximum outside-engine CPU during that window was 1.24 cores.

| Metric | Paired median ratio | 95% CI | Descriptive result |
| --- | ---: | ---: | --- |
| Measured engine CPU | 1.0967 | 1.0513–1.1577 | Loss |
| Sampled peak physical footprint | 0.7484 | 0.6529–0.7816 | Strict win |
| API p50 | 0.9747 | 0.9329–1.0031 | Non-inferior |
| API p99 | 0.8775 | 0.8239–1.0431 | Inconclusive |
| API request rate | 0.9928 | 0.9409–1.0437 | Inconclusive |
| Transfer goodput | 1.0360 | 0.9633–1.0680 | Inconclusive |

Ratios below 1 favor ctrs. Request rate and goodput use OrbStack / ctrs.
All ten ctrs trials used host NAT (97 connections total). Its kernel CPU
is outside the measured engine counters, so charging it would increase the
CPU deficit. The earlier p99 loss used a 5-vCPU default and different image
pins. The new fixture and CPU allocation prevent attributing the difference
to the vCPU change alone. Independent confirmation and the matched-resource
comparison remain open.

The process counters localize the measured CPU difference to the overlap
workload phase. Across the ten ctrs trials, the median was 117.5 CPU seconds
in the Virtualization.framework VM helper and 15.4 in the daemon, with
15.2 of the daemon seconds charged as system CPU. OrbStack's helper median
was 118.7 seconds. These process totals include both the API and bulk
work. The next diagnostic is to measure the upload and API separately,
then attribute the daemon's system CPU during upload.

```sh
export PATH="/opt/homebrew/bin:$PATH" TMPDIR="$PWD/.work/tmp"
python3 bench/native/pyramid.py run --name w13-overlap:cohort
python3 bench/native/reporting.py --match base-20261122T073402-7351
```

`trials.jsonl` SHA-256
`08090558a7c1bd1643ad60040574aab8bdea9a5ee10bd2782d32776e40b539b0`.

### Installed-default W14 idle-resume cohort

Run `base-20261122T082410-0094` used clean source `7eb4859`, the W6
signed binary and guest assets, and the pinned v6 API image. Both engines
observed 9 vCPUs with the same memory allocations as W6. All ten pairs
matched the `w14-v3` fixture inputs and completed with zero rejections.
Each leg verified 32 resumed TCP sessions after 30 seconds of idle
time, zero leaked sessions and successful owned cleanup. Outside-engine
CPU during the lifecycle phase reached at most 0.38 cores.

| Metric | ctrs / OrbStack paired median | 95% CI | Descriptive result |
| --- | ---: | ---: | --- |
| Resume p50 | 1.1281 | 1.0558–1.4681 | Loss |
| Resume p95 | 0.9640 | 0.9080–1.2592 | Inconclusive |
| Resume p99 | 0.9423 | 0.9061–1.2563 | Inconclusive |
| Cleanup latency | 0.3530 | 0.2619–0.5451 | Strict win |
| Sampled peak physical footprint | 0.3172 | 0.3031–0.3257 | Strict win |
| Measured engine CPU | 0.1844 | 0.1597–0.1975 | Incomplete |

All ten ctrs legs used host NAT (220 connections). Host-kernel CPU for
those connections is outside the measured counters. This mode resumes
idle connections to a running service. It does not measure a stopped VM's
wake latency.

```sh
export PATH="/opt/homebrew/bin:$PATH" TMPDIR="$PWD/.work/tmp"
python3 bench/native/pyramid.py run --name w14-idle-resume:cohort
python3 bench/native/reporting.py --match base-20261122T082410-0094
```

`trials.jsonl` SHA-256
`8bb607932e787f79531a644b4c416081a5682bede314429e70b4813f8734d0ce`.

### Rebuilt W8 common portfolio

The [v6 recipe and lock](../bench/native/fixtures/w8-v6/README.md) replace
the lost v5 API and Marked images. PostgreSQL and Redis were recovered by
their unchanged manifest digests. Two independent uncached builds per
private image matched, and a separate run of the tracked prepare script
recreated the canonical archive with SHA-256
`8c2d09449cbc4002735068c825eb23a51ed3dd4f0fd44e7b9a12ff8291fb1cd7`.
All four images loaded into an empty dedicated ctrs store and matched
the ARM64 image IDs and ordered DiffIDs.

Both engines passed registry deployment in `w8-common-20261122T072209-1171`.
Each completed 688 reads and 312 writes, verified every stored payload,
read the committed database/cache value after restart, and produced the
pinned Marked artifact. ctrs and OrbStack `result.json` SHA-256s were
`39d2878bfc08b3169100207cae8ee4903106459cf4da1e4b23008c2bba812418` and
`900a8d3ebe891c22518de1c4975fe897819eea17b0b542563f123bd4b3709b34`.
The images are installed on the campaign Mac. The W8 timing cohort and
fresh comparative results for portfolio consumers remain open.

The paired W8 control reports the whole-workflow CPU delta and sampled
physical footprint for the verified engine processes and fixture
registry coordinator. It takes ctrs relay snapshots around that interval.
An observed NAT relay or missing accounting keeps favorable CPU results
from qualifying. This control uses matched resources and keeps the
engines resident.

Run the no-load and concurrent API controls as `w8-pull:cohort` and
`w8-pull-under-load:cohort`. The installed-default counterparts are
`w8-pull-installed-default:cohort` and
`w8-pull-under-load-installed-default:cohort`. Add `-retained` before
`:cohort` to select the corresponding retained-layer condition.

Both one-pair installed-default deployment checks passed on `5c67876`.
Each engine verified the transfers, exact deployment output, retained
pins, owned cleanup and sampled footprint. Both observed 9 vCPUs. ctrs
used host NAT in both trials, leaving CPU accounting incomplete. The
earlier retained and derived attempts were refused at admission because
the coordinator was still flagged as hot after compressing the fixture.
The successful checks waited for a separate compression process to exit
before taking the host gate snapshot.

| Content | Valid pairs | Run | `trials.jsonl` SHA-256 |
| --- | ---: | --- | --- |
| Retained | 1 | `w8-paired-cf3c016e3ac2` | `179294d1b8bb0fae179c4ceea5e7ae2d44c5553de26975c6303fe87035da7395` |
| Derived | 1 | `w8-paired-9075cc26943d` | `e0abe0cbc6eb6d993c81bd010501bed602c4171b0ef78ec80fc96ee0a50cdeb7` |

To reproduce a check, use `runner.py w8-baseline --pairs 1 --resource-lane
installed-default --content retained` with the v6 layout and signed
binary. Use `--content derived` for the other condition. The ten-pair
timing cohorts and comparable backing-allocation measurements remain open.

The two installed-default checks with concurrent API load passed on
`8f23986`. Each engine completed 35,159 reads and 14,841 writes, verified
every persisted payload, and recorded successful completions during each of
the four pull intervals. All four legs verified the deployment and retained
pins, passed their host gates and reported complete physical footprint.
ctrs used host NAT. Each check supplies one valid pair.

| Content | Run | `trials.jsonl` SHA-256 |
| --- | --- | --- |
| Retained | `w8-paired-fa188fe00a13` | `dd0abc5597c7ef85db7d8e2647ee1098b9a3e293f8b17c91d0923d87662ed830` |
| Derived | `w8-paired-eb317bd82df9` | `7e2d21f324dfa2604626c11c7fb1412e096c659c4d9e56b6c948e46b743358fc` |

Add `--under-load` to the one-pair command to reproduce these checks.

### Rebuilt W11 worker fixture

The historical worker's manifest and config IDs were absent from OrbStack
and the dedicated ctrs store. Two uncached native ARM64 builds reproduced
the same new manifest, config and DiffIDs from the pinned W4 Dockerfile
and unchanged application bytes. The canonical archive SHA-256 is
`b775e9bdf8c029026d4e2e53c0ebab2e0e0920c223d28df37380ba42c79b0dd7`.
See the [worker recipe and pin](../bench/native/fixtures/w11-v2/README.md).

Both engines passed the two-cycle functional proof
`w11-mixed-20261122T085837-51e2` on source `68f70ee` with the v5 worker
and v6 portfolio. Each cycle verified 5,000 API operations, 200 queue
jobs, 12,800 queue events, 400 artifacts, 16 build jobs, and all 500
retained seed rows. Owned cleanup completed without errors.
The continuous 12-hour legs and post-cleanup resource growth gates remain
open. The functional proof used the bounded-working-set workload.

`trials.jsonl` SHA-256
`b7bf0a89e172a4f74d710cf3e8f7d4dbce2c13ae95f4d5e7143c742bf08d0926`.
`plan.json` SHA-256
`ae60b1e3bbdf0c5e32f01f24a1ccaa4bb08fea26b28b518efab26726cf1593bb`.

The v5 resource observation `w11-mixed-20261122T091336-64f6` passed
two exact cycles on each engine at source `8f23986`. All four
post-cleanup intervals ran for 32.10–32.15 seconds and returned verified
physical footprint, descriptor counts and backing allocation. For ctrs,
allocation covered the isolated VM data disk. For OrbStack it covered the
engine's open `data.img.raw` and `swap.img`. APFS shared extents remain
outside the exclusive-allocation scope. Cleanup passed with zero errors.
The resource budget needs a warmup plus five subsequent observations.
These two cycles per engine verify collection and leave growth and
12-hour reliability open.

To reproduce, use the v5 worker and v6 portfolio in the mixed-pilot command
with `--cycles 2 --resource-observation-seconds 32` and a fresh
`--ctrs-root`. Pass `--orbstack-storage-file` for each of the two files
under the running engine's group-container data directory. The collector
verifies each open backing identity on every observation.

`trials.jsonl` SHA-256
`a5de6b5abcd8bbadb6df97e459d950e72311569934f87cb9f0730fcae60107e2`.
`plan.json` SHA-256
`f11ee0bedc4add94082efac2dc2cff895d29135bb0ff6c43bd9f95ba725ae520`.
`driver-result.json` SHA-256
`f0914f7f9b678cd3e6981946403df7a2ee579c602c0fb1b10370330ab10984b0`.

### Rebuilt W12 workspace fixture

The [v2 recipe and lock](../bench/native/fixtures/w12/README.md) rebuild
the Kutt image from pinned inputs. Two uncached prototype builds and an
independent run of the tracked prepare script produced the same archive
SHA-256, `d852665d1d6865482e9e42dc3aeffb20922cb8bf91531935416cfaa3cb2f5f32`.
The identity proof loaded the archive and verified the native ARM64 image
and both lock hashes on each engine. The historical v1 image pins and
cohort results stay separate.

The migrated npm lock retains the 2,830-package install on both engines.
All three layouts reproduced the original server, client and Jest
receipts on both. The original volume file-watch strategy still missed
23 of 120 results on OrbStack (`w12p24937af681`). Every miss was a
five-file burst result, matching the historical failure after atomic
replacement on native volumes. The separate volume fixture uses
TypeScript's parent-directory `fs.watch` strategy, with the same 120
expected results. Bind retains the existing file-watch strategy.

Both engines returned all 120 correct results with zero misses and
zero stale outputs in each watch condition. Bind proof runs were
`w12pb67161e96f` and `w12p24937af681`. Parent-directory volume proof
runs were `w12p15c4e8961f` and `w12p9792405904`.

Run fresh `w12-full-bind:cohort`, `w12-mixed:cohort`,
`w12-all-volume:cohort`, `w12-watch-bind:cohort` and
`w12-watch-volume:cohort` pairs. The independently registered
`w6-build-warm:cohort` covers W6's primed build-cache condition.

## Linux lane pilot (amd64) — 2026-11-21

**Separate native Linux pilot; closes no macOS gate.** Do not pool these
samples with the macOS/OrbStack matrix or the earlier one-pair Linux smokes.
Measured 07:28:58–08:49:45 UTC: **80m 47s**, within the 2.5-hour budget.
Ten attempted pairs per workload, 80 trials total; no count reduction,
replacement pairs or retries. All four cohort commands exited 0.

### Design and identity

The contract's [Measurement rules](campaign-native-performance.md#measurement-rules),
**Same work and state**, requires alternating AB/BA or balanced randomization.
The **Consistent statistics** rule says “Three pairs are pilots” and requires
at least ten valid complete pairs for a qualified cell. This pilot used ten
pairs per case, alternating AB/BA (ctrs/dockerd, then dockerd/ctrs: ABBA
repeated), seed 7, with shared per-pair seeds/stamps and no randomization.
Ten pairs alone do not establish qualification. Counts, primary metrics and
admission rules were frozen before running; no performance-based exclusion.

Host: Ubuntu 22.04.5 LTS, Linux `6.8.0-1060-aws`, x86_64, 8 CPUs,
33,655,406,592 bytes RAM. Dockerd **29.9.2**, `overlayfs` storage driver,
systemd cgroup driver, cgroup v2. Both engines ran natively, without VM caps;
both remained resident while either was measured. Warm engine/base-image
stores were retained, without global pruning. No concurrent campaign builds,
tests or load jobs were run. Absolute resource values include each engine's
resident service/store state, including the preexisting host Docker services.

Harness worktree HEAD was `c57ec08`; frozen Linux inputs were
`linux-amd64-v1`, sampler `2-linux-cgroup-v2-memory-stat`, with structural
BuildKit ownership. The externally managed ctrs build includes the forwarding
coexistence fix (PR #14), with actual running executable SHA-256
`5e80c7f8011af060a541b756d62ff2ffe6f79f9876b528c70925343e6a9202f7`.
Daemon and agent file hashes were unchanged after all measurements. Raw trial
`git_sha` is `unknown` in this sudo execution; the pre-run worktree revision
is recorded separately, and runner, sampler, fixture/lock and running-binary
hashes remain in the provenance. Raw records have not been relabeled.

Frozen cells, all `--state warm --resource-lane matched` (native host, no VM cap):

- **W2:** 50,000 fixed-work operations, C8, write ratio 0.3, host client,
  no offered-rate throttle. Primary time: `p99_ms`; completion wall time is
  also shown below. Pair seeds are `7 + 10 * pair_id`.
- **W6:** default builder, uncached Rust and zlib compile/test builds,
  base images retained, frozen native artifact hashes checked. Primary:
  `build_rust_s`; zlib is a separate companion, not averaged away.
- **W7:** default builder, both real apps in uncached/warm/incremental
  states, loaded-image version/note/cache assertions and first-use probes.
  Primary: `hyperfine_uncached_s` (build/load); first use remains separate.
- **W13:** published-port upload, one stream, 1 GiB per transfer, three
  transfers per trial, exact receiver SHA-256/byte checks and capacity
  controls. Primary: `completion_seconds`.

### Primary timing scorecard

Values are median **[Q1, Q3]**, using linear quartiles. Ratios are the median
of whole-pair **ctrs/dockerd** ratios, not the ratio of marginal medians;
smaller favors ctrs. Brackets on ratios are 95% percentile bootstrap intervals
of that same paired median (2,000 whole-pair resamples, seed 20261121).
All ten complete, correct, host-admitted pairs contribute to each timing row.

| Workload / primary | ctrs median [Q1, Q3] | dockerd median [Q1, Q3] | Paired C/D [95% CI] |
| --- | --- | --- | --- |
| W2 p99 (ms) | 27.486 [25.424, 30.007] | 24.449 [23.071, 27.874] | 1.086 [1.034, 1.201] |
| W6 Rust build (s) | 86.784 [84.081, 89.849] | 90.733 [87.504, 96.711] | 0.956 [0.914, 1.011] |
| W7 hyperfine uncached build/load (s) | 28.710 [28.259, 31.269] | 29.198 [28.511, 31.357] | 0.993 [0.911, 1.136] |
| W13 completion (s), tool-limited | 0.539 [0.493, 0.615] | 0.508 [0.483, 0.590] | 1.032 [0.840, 1.275] |

W2's p99 pilot favors dockerd. W6's point estimate favors ctrs, but its
interval crosses 1; W7's primary interval is also inconclusive. W13 is
**inconclusive for engine attribution**: every trial hit the tool-limit flag
(over half the slower capacity control). Do not interpret its descriptive
timing distribution as network parity or an engine win/loss.

### Resource medians and validity

CPU is estimated whole-sampled-trial CPU seconds, not CPU isolated to the
primary timing phase. Memory is the median of trial peaks, in MiB. Footprint
means the peak coincident **anon + kernel** sum; `memory.current` is secondary
and includes file cache. Anon/file/kernel components remain separately in
the traces. CPU from exited Docker transients is a sampled lower bound;
these are not macOS physical-footprint or resource-qualification results.

| Case | Resource-valid complete pairs | CPU s, ctrs / dockerd | Anon+kernel MiB, ctrs / dockerd | memory.current MiB, ctrs / dockerd |
| --- | --- | --- | --- | --- |
| W2 | 10/10 | 75.068 / 74.105 | 75.71 / 890.39 | 150.60 / 13,795.49 |
| W6 | 10/10 | 193.295 / 199.915 | 1,216.88 / 1,764.83 | 4,802.42 / 15,691.68 |
| W7 | 10/10 | 74.375 / 79.965 | 1,681.05 / 1,819.85 | 9,166.34 / 15,390.27 |
| W13 | 7/10 | 2.898 / 3.285 | 832.70 / 915.34 | 9,917.87 / 15,825.19 |

| Case | Correct trials | Complete/no-host-contention timing pairs | Resource-valid pairs | Tool-limited trials |
| --- | --- | --- | --- | --- |
| W2 | 20/20 | 10/10 | 10/10 | 0/20 |
| W6 | 20/20 | 10/10 | 10/10 | 0/20 |
| W7 | 20/20 | 10/10 | 10/10 | 0/20 |
| W13 | 20/20 | 10/10 | 7/10 | 20/20 |

Ctrs resource coverage was 40/40 trials; dockerd was 37/40. W13 dockerd
trials in pairs **2, 4, 6** failed strict sampling with
`unverified process in Docker transient cgroup: system.slice/docker-<id>.scope`.
Those resource values remain invalid/missing, never zero. The W13 resource
medians use only the seven complete resource-valid pairs for **both** engines;
no replacement pairs were run. The underlying member-attribution failure was
not diagnosed or bypassed. W13 resources and timing attribution remain open.
Host admission used the existing reporter's foreign-CPU/load rule; there
were no host-contention exclusions. Missing resource attribution did not
invalidate the separately correct byte/completion observations.

### Companion timings (seconds; no family averaging)

Build/load and first use remain separate. All rows use the same ten timing
pairs, median [Q1, Q3], and paired C/D bootstrap procedure. In particular,
httpie uncached first use is slower on ctrs; do not hide it behind its faster
build or behind the hyperfine primary. Hyperfine warm build is also a
slower point estimate. W7's fixture still executes its `pip wheel` path;
no new transitive-dependency or WAN-timing qualification was performed.

| Metric | ctrs median [Q1, Q3] | dockerd median [Q1, Q3] | Paired C/D [95% CI] |
| --- | --- | --- | --- |
| W2 fixed-work completion | 61.225 [58.774, 65.716] | 55.342 [52.926, 59.726] | 1.078 [1.034, 1.179] |
| W6 zlib build | 2.584 [2.437, 2.959] | 2.809 [2.646, 2.989] | 0.897 [0.815, 1.028] |
| W7 hyperfine uncached first use | 0.0640 [0.0504, 0.0741] | 0.2893 [0.2766, 0.3048] | 0.1815 [0.1648, 0.2642] |
| W7 hyperfine warm build/load | 0.2838 [0.2698, 0.3045] | 0.2589 [0.2306, 0.2752] | 1.1648 [0.9867, 1.3304] |
| W7 hyperfine warm first use | 0.0378 [0.0304, 0.0411] | 0.2726 [0.2454, 0.2798] | 0.1313 [0.0924, 0.1586] |
| W7 hyperfine incremental build/load | 0.2859 [0.2664, 0.3150] | 0.4698 [0.4384, 0.5235] | 0.6339 [0.5591, 0.6849] |
| W7 hyperfine incremental first use | 0.0331 [0.0306, 0.0374] | 0.2806 [0.2744, 0.2842] | 0.1171 [0.1029, 0.1439] |
| W7 httpie uncached build/load | 9.7688 [9.4661, 10.4690] | 11.3303 [10.7696, 12.7281] | 0.8757 [0.8179, 0.9440] |
| W7 httpie uncached first use | 0.8396 [0.7815, 0.8876] | 0.5846 [0.5803, 0.7617] | 1.3411 [1.1913, 1.4014] |
| W7 httpie warm build/load | 0.1625 [0.1571, 0.1733] | 0.2288 [0.2101, 0.2821] | 0.6888 [0.5869, 0.8688] |
| W7 httpie warm first use | 0.2917 [0.2609, 0.3710] | 0.5633 [0.5226, 0.6987] | 0.5264 [0.4764, 0.6268] |
| W7 httpie incremental build/load | 0.3637 [0.3363, 0.3903] | 0.5442 [0.5083, 0.6265] | 0.6104 [0.5181, 0.7339] |
| W7 httpie incremental first use | 0.3090 [0.2729, 0.3567] | 0.5692 [0.5376, 0.6442] | 0.5218 [0.4093, 0.7688] |

### Evidence, cleanup and unchanged macOS gates

Raw cohort directories under `.work/native-perf/results/`, each with
`trials.jsonl`, per-trial provenance, BuildKit logs and cgroup traces:

| Case | Run |
| --- | --- |
| W2 | `base-20261121T072858-c236` |
| W6 | `base-20261121T075122-4767` |
| W7 | `base-20261121T082337-13db` |
| W13 | `base-20261121T083950-75d8` |

Frozen design, exact commands, logs, deterministic analysis program/output,
host identity, binary hashes and pre/post daemon identity are under
`.work/linux-pilot-20261121/`. The commands were
`runner.py --lane linux-amd64 baseline --a ctrs --b dockerd --case <case> --pairs 10 --seed 7`,
with `--operations 50000 --concurrency 8 --write-ratio 0.3` for W2; W13 used
the default 1 GiB, three-repeat published-port upload. Fixture preparation
was not timed or repeated; the committed Linux lock was not regenerated.

Ctrs stopped successfully: MainPID 0, inactive, no remaining cgroup or owned
firewall rules. Dockerd stayed PID **599**, active since
`Sat 2026-11-21 05:39:22 UTC`; pre/post identity matched exactly. No daemon
restart/configuration change or global prune. Owned containers were cleaned up.

All [macOS finish gates](campaign-native-performance.md#finish-criteria-coverage-parity-leadership)
remain **open, unchanged**:

- **Coverage:** representative W1–W10 cells/states/loads on the Mac.
- **Meet OrbStack:** all critical paired timing/resource upper bounds and correctness/recovery gates.
- **Exceed OrbStack:** family aggregate and default W6/W7 improvements, without hidden losses.
- **Reliability:** each engine's 12-hour W11 qualification and growth/durability budgets.
- **Reproducibility:** fresh signed release/isolated-root reproduction and independent holdout.

Mac asset/kernel/watch-test rebuilds and the parked q7 cohorts above still
need the Mac. Before Linux resource qualification, investigate the three
Docker-scope attribution failures and W13 tool limits; do not treat this
scorecard as full Linux or macOS qualification.

## Status at wind-down (history)

**Active 2026-11-18 after new-host migration.** The development host moved to
a MacBook Pro (Apple M1 Max), 10 cores, 64 GiB (68,719,476,736 bytes), macOS
27.2.1 (26B131), Darwin 27.2.0. OrbStack 2.2.5 (bf842321…) is unchanged.
All raw results and VM assets from the old host are unrecoverable; every
pre-2026-11-18 measurement is historical to that host.

Reconstruction evidence is in [native-host-refresh-2026-11-18.md](evidence/native-host-refresh-2026-11-18.md).
Rebuilt and verified 2026-11-18: guest initramfs with the exact accepted
hash (`6ae4d3ab…`); guest kernel from pinned source/config/patches (`ea485341…`,
18,800,648 bytes, same size as accepted; `35087713…` is unrecoverable by
construction because builds embed a timestamp); sparse 1 TiB `data.img`;
signed host binary `be929fe2…` from main at `19c3fc8` (includes c7b4b90);
`conformance/smoke.sh` 21/21; offline Python discovery 318 tests OK with
`TMPDIR=$PWD/.work/tmp`, 0 skips.

The W8 common portfolio was refreshed as fixture **`w8-v5`** (never pool with
v2): `np-v5/postgres` and `np-v5/redis` are bit-identical to the v2 pins;
`np-v5/api` and `np-v5/marked` were rebuilt from the pinned fixtures with
digest-pinned bases; fixture input hashes and the Marked artifact hash are
unchanged (verified on both engines, 1,000 requests, exact payloads and
HTML). `assets.lock` records the new host, tools (python 3.15.1, docker
29.8.2, Compose v5.5.0), engines and rebuilt guest assets. Two stray
100%-CPU benchmark-harness greps from an earlier session turn were found and
killed on 2026-11-18; the user's own python-build session and OrbStack
Helper (`vmgr -handoff`, 100% CPU for 6+ hours) were left running and are
disclosed on every affected measurement. All code references now use w8-v5;
docs/evidence history was not rewritten.

The 2026-11-18 refreshed W2 matched-resource baseline
(`base-20261118T040927-4162`, 10 pairs, 50,000 ops, C8, seed 7, AB/BA) is in
[native-host-refresh-2026-11-18.md](evidence/native-host-refresh-2026-11-18.md#refreshed-baseline-this-host):
all 20 trials correct, zero errors; ctrs wins every latency/footprint cell
(rps 0.744, p99 0.611, footprint 0.359 vs OrbStack) but loses ~8.5% on
cpu_seconds_per_success (1.085, [1.052, 1.123]) — same direction as the old
host's system-CPU finding. Pilot quality, not qualification: disclosed
co-resident user load and a dirty worktree at launch; a quiet-window
confirmation batch from a clean tree is required before promotion use. The
earlier "missing provenance" note was a reporter defect (it ignored
`provenance.build_outputs`), fixed 2026-11-18; the trials carry all binary
and guest-asset hashes. The installed-default ctrs lane was 2 vCPUs until `148136f`; it was half the Mac's cores until 2026-11-20 and is now all but one (9 here). No campaign-owned measured job is active.

Later 2026-11-18 ([W2 IPI evidence](evidence/native-w2-ipi-2026-11-18.md)):
the quiet-window matched confirmation `base-20261118T081857-9b61` keeps all
latency/throughput/footprint cells as strict wins. CPU per success is
inconclusive (1.045 [1.015, 1.085]). An idle campaign `bootcheck2` daemon
was co-resident during both matched batches and is disclosed there. The
whole CPU gap is guest API system CPU, and new W2 guest counters (`7e88096`)
show 4.4× more call-function IPIs per success than OrbStack. SCHED_MC was
re-tested with those counters and rejected again: it raises the IPI count.
The first declared installed-default lane batch (`5e42acb`,
`base-20261118T090126-7b92`, ctrs 2 vCPUs vs OrbStack 9) is a strict win
on every W2 cell, including CPU/success 0.874 [0.824, 0.883] (pilot).

## Accepted and verified

All items below were measured on the old host (2026-11-15…17) and are not
portable to the 2026-11-18 host; they remain as design/outcome history.
See [native-host-refresh-2026-11-18.md](evidence/native-host-refresh-2026-11-18.md).

- Native accounting uses actual ri_phys_footprint and complete owned daemon/VM
  counters, kernel start identity and loaded executable/boot hashes. v4 adds
  shutdown acknowledgment. [Measurement evidence](evidence/native-sampler-lifecycle-2026-11-17.md)
  retains the defects, focused checks and original v3 on/off calibration limits.
- W2 fixed useful work, exact persisted payloads, normalized CPU/success,
  fixed-offered-rate diagnostics and separate saturation are implemented.
  Matched same/distinct-CPU futex controls reject the old unpinned contrast as
  proof of a VZ ceiling. Counts and on-CPU/wait profiles remain distinct.
- Real W4 queue/artifacts, pinned Marked W5 watch/test, common/derived W8,
  fixed-build W9 and representative short W11 fixtures pass functional proofs.
  [Historical evidence](evidence/native-performance.md) preserves versions and
  failures; these are not final acceptance or 12h reliability results.
- Resource-cycle source declares idle/reclaim/next-use/growth budgets. Physical
  allocation is scoped to explicit files; exclusive APFS extents and isolated
  build-cache size remain unknown. [Current cycles](evidence/native-resource-cycles-2026-11-17.md).
- W10 v2 persistent clients and recovery tracing pass exact-data functional
  checks. The50ms refusal-cache candidate remains parked;250ms default stays.
- Persistent-mount guard, data-preserving disk expansion, image DiffID/label
  repairs and balloon accounting are integrated. Restart/daemon-interruption
  proofs do not establish host power-loss durability; Full sync is unpromoted.
- Readiness reuse passes both buildx/Rust and classic C callers. Compression,
  scheduler, affinity and quiet-policy candidates remain rejected/unqualified;
  their [build](evidence/native-build-boundaries-2026-11-16.md), [W2](evidence/native-w2-boundaries-2026-11-16.md)
  and [preemption](evidence/native-preemption-2026-11-17.md) records preserve the decisions.

## Last active next action (macOS, before the pause)

**Current (2026-11-19, second steering: coherence, then guest→host):**
live kernel k17 = patches 0001–0011 plus a new 0012 (echo proof and
rescan; the old two-second echo window, 0013 and 0014 are removed),
protocol 9, host binary and agent from `bf2ea2b`, e2e 508/508. Done this round:

- Filesystem coherence: an echo is skipped only when proven to be the
  guest's own change; FSEvents drop/must-scan/root-change flags, failed
  sends and agent-queue overflow become rescans with a bounded
  reconciliation walk; stream replacement replays from the last event id.
  Contract and regressions: `docs/design-bind-notify.md`.
- Keep/revert: 0013/0014 reverted (no paired W12 benefit).
- Admission: W12-watch misses/stale fail the trial; W13 claims are capped
  when the favored side was tool-limited; W13/W14 pair on pinned image
  identity (older cohorts flagged unverified); W13 ctrs trials record
  connections per transport (`GET /ctrs/relays`). The latest W2 records
  were saturation runs (no `--operations`).
- Guest→host: the NAT host relay (`3351ba9`) and published-port legs
  (`ad22161`) cut container→Mac upload to 2.23× (was 7.0×) and
  published-port download to 1.64× (was 5.1×), paired, 10 pairs, every
  connection over NAT. Leg-only regressed published-port upload to 1.14×;
  `439b14e` moves client bytes back to vsock (unmeasured). One NAT flow
  caps near 1.9 GB/s here. Evidence: "Guest→host transfer attribution".

- W14 CPU: the agent busy-looped while a container connect was pending
  (1.35 s agent CPU in one streaming run; 0.05 s after `bf2ea2b`).
  Host-bound split (Mac bytes over vsock) built and rejected: no gain.

Measured since (all D lane, 10 pairs unless noted; evidence
`evidence/native-w12-w13-2026-11-18.md`, matrix rows W2, W3-v4, W12,
W12-watch, W13, W14):

- Host-bound download over NAT 0.99 tool-limited (no regression);
  published-port upload on the split 0.96 inconclusive, CPU/GiB 1.17
  loss; published-port download still a ~1.7× loss (two invalid cohorts).
- W14 after the spin fix: streaming CPU 0.28 win; reconnect p99 0.42 and
  CPU 0.30 wins; persistent latency non-inferior (1.025), CPU 0.61 win;
  idle-resume CPU 0.15 win, latency inconclusive; fresh p50 5.6 loss is
  an admission confound (completion inconclusive), CPU 1.15 loss.
- W2 50k fixed work: latency/rps wins, CPU/success 1.03 inconclusive.
- W3-v4: every timing a win, not claimed until flush contracts are
  shown equal (bound recorded in the matrix row).
- W12 full-bind still a loss (~1.3); W12-watch 5-pair pilot 0.92.

Harness changes this round: `pyramid.py` entrypoint (README
"Entrypoint"); W13-overlap pairs on verified identity (`8b5709d`) and
carries resources (`689b63f`); admission on CPU busy outside the engine
and harness (`d211cae`, `886774f`), with a pre-pair idle-CPU wait.

Guest→host intervention (2026-11-20): on a quiet host the NAT network
carried a direct container→Mac flow at 3.9–5.3 GB/s and the relayed one
at 1.5–3.1, so the agent's copy loop was the limit. The agent now splices
bulk relay bytes (`4fdff1d`, e2e 508/508). Paired on that build:
published-port download 0.93 and container→Mac upload 0.95 (were 1.7×
and 2.2× losses), published-port upload 0.69, all tool-limited on both
engines, with ctrs's own time 0.56× / 0.43× / 0.77× its previous build
and OrbStack unchanged. Container→Mac download (Mac→container) looked
worse (8 clean pairs 1.27) in a cohort partly contaminated by a tool
edit; a held probe put the splice's cost there near 6 %.

Since: the NAT host-bound Mac→container direction went back to the copy
loop (`ade0b80`; download 1.21 spliced → 1.06, pre-splice 1.04); on that
guest (`e217587c…`, e2e 508/508) published-port download 0.92,
container→Mac upload 0.94, published-port upload 0.72, all tool-limited.
Two W13 tool rewrites were reverted (`a68248e` memoryview compare,
`60f6036` no in-trial gain): Mac single-flow loopback caps the tool.
W13-overlap is a scored loss (p99 1.70) attributed to guest CPU at the
5-vCPU default. Scored: W12-watch p50 0.90, W14 cancel wins. Ranked list:
`evidence/native-w12-w13-2026-11-18.md` "Ranked measured deficits".

Since (2026-11-20, later): W14 fresh scored on `completion_seconds`
(1.00, inconclusive; `base-20261120T052835-f228`); W12 mixed layout
(bind source, volume deps) 1.027 inconclusive (`-045710-1dc3`); the
W3-v4 flush probe recorded each engine's `fdatasync` cost (OrbStack
p50 0.6–2.0 ms, ctrs 0.26 ms; VZ offers only `Fsync` or `Full`).
buildx 0.37's docker-driver `--load` sent `prefer-image-digest`, which
ctrs's build gRPC rewrite rejected; `d692709` drops it (e2e 508/508),
restoring W6/W7. Change-tier pilots W1, W6, W7, W10 pass; costs are in
the `pyramid.py` registry.

Third steering (2026-11-20): default builds, the vCPU default as a
measured decision, watcher recovery after loss, then full-bind.

Done so far: the matrix is reconciled (`1e45fc1`); W4/W5 inputs build
alone (`runner.py prepare --only W4,W5`) and W9 finds its pinned image
(`bc996cf`); W4, W5, W9 one-pair pilots are correct on both engines;
concurrent builds each hold measured pairs (`.work/tmp/holds/<name>`,
`bf8512f`); a same-engine CPU candidate design (`--candidate-cpus N`,
`reporting.py --candidate`, pyramid `<cell>:cpus9`; `83a3315`,
`98eb949`) clones the default warm engine copy-on-write; ctrs CPU is
marked incomplete in machine-readable output when the Mac's NAT carried
the trial's connections (`adf2f67`). Watcher regression
`tests/watch-recovery.sh` (branch `fix/watch-recovery`, `a00f3d6`) fails
on main for both host loss and guest overflow; the fix is in progress
on that branch.

Next, in order:

1. Queue `.work/tmp/queue.sh` (log `.work/native-perf/matrix/q1.log`),
   serial: `w13-overlap:cpus9` (primary decision test), `w2-api:cpus9`
   + `w14-idle-resume:cpus9`, `w12-full-bind:cpus9` + `w6-build:cpus9`,
   then `w6-build:cohort` + `w7-buildx:cohort`. Report each with
   `reporting.py --candidate --match <run>`. Decide the default from the
   overlap tail plus the W2 CPU/success, idle-resume CPU, footprint and
   next-use budgets (`resource_cycles.BUDGETS`); if adopted, change
   `default_cpus`, record policy and candidate identity in
   `docs/decisions.md`, and re-run the D-lane cohorts at the new default.
2. Watcher recovery landed (`f291b04`, kernel patches 0013–0016,
   lane kernel `3e1b55bd…`, host `b2b1679f…`; e2e 508/0/0,
   watch-recovery.sh passes with and without dropped caches). Not yet
   deployed to `guest/out`: install it (`cargo xtask kernel`, then
   `cargo xtask all`) only after the measurement queue drains, then
   re-run W12-watch (a rescan now raises one event per uncached
   retained name; review note D3) and record the asset change.
3. Full-bind boundary: a two-virtiofs-device probe
   (`exp/fs-devices`, `CTRS_EXP_SHARE_DEVICES=2`, a noisy first run
   showed 1.2–2.5× more files/s split across two devices) tests whether
   the Virtualization.framework server serializes per device. Rerun in a
   quiet window before drawing a conclusion.
4. W6/W7 D-lane cohorts reported (2026-11-20, source `0536435`): no
   build phase loses. W6 `base-20261120T143829-8345`: Rust 0.953×
   non-inferior, zlib 0.641× win. W7 `base-20261120T150445-1408`: the
   uncached hyperfine build is 0.997× non-inferior, every other cell
   wins. The closest-to-losing phase is the uncached compile, which is
   CPU-bound in the guest: the 9-vCPU W6 candidate (queue q6) is its
   intervention. Resource metrics sampled only 8 of 10 pairs and stay
   incomplete; find why two trials dropped their samples.
   The 9-vCPU W6 candidate failed every slot-b build until `0536435`:
   the builder config write was reset right after VM boot and the
   builder started on a copied config naming the other daemon's mirror
   port.

Kernel experiments build in a labeled copy of `ctrs-kbuild`
(`ctrs-kbuild-exp-*`, label `dev.ctrs.campaign.run=bind-notify`) and are
tried with `CTRS_GUEST_DIR` pointing at a guest dir made with `cp -c`
(`data.img` is 1 TB sparse; never checksum it).

Tooling: `kache` hung debug test builds for over 20 minutes on 3 small
crates. Workaround: `RUSTC_WRAPPER="" CARGO_TARGET_DIR=.work/tmp/target-nowrap`.
The ownership resolver (`laputa-systems/stuff/repomod/which.py`) is not
present on this host, so no ticket was filed.

**Earlier (2026-11-18 afternoon, after `19d4eb2`):** the frozen first
comparison matrix is running serially on the Mac. Live assets are main's
`d9465bc2…` binary and `f3ab7344…` initramfs (half-close fix). Every cell is
10 AB/BA pairs, warm, `--resource-lane installed-default`, run from the repo
root with `TMPDIR=$PWD/.work/tmp`:

```sh
python3 bench/native/runner.py baseline --a ctrs --b orbstack --pairs 10 \
  --resource-lane installed-default --case W13 \
  --transfer-path {published-port|container-to-container|container-to-mac} \
  --direction {upload|download} --streams {1|4}
python3 bench/native/runner.py baseline --a ctrs --b orbstack --pairs 10 \
  --resource-lane installed-default --case W12 \
  --workspace-layout {full-bind|all-volume}
```

Frozen D-lane cells, in order: W13 published-port upload/1, download/1,
container-to-container upload/1, container-to-Mac upload/1 and download/1,
published-port upload/4; W12 full-bind and all-volume. W12 needs
`.work/tmp/kutt.tar.gz` and `.work/tmp/w12-image.tar` from
`bench/native/fixtures/w12/prepare.py`. Next: report each cell with
`reporting.py`, then rerun the M lane for the losing W13 path(s) and W12
all-volume to separate the 2-vCPU default from engine cost, then rank the
deficits in the matrix. Expand only to answer a concrete question.

**Earlier (2026-11-18, owner steering):** W2 tuning is parked. Status per cell
lives in [native-acceptance-matrix.md](native-acceptance-matrix.md). Next
milestone: one trustworthy W12 shared-workspace comparison and one W13
bulk-transfer comparison on this host, then a ranked deficit list. Then W14
connection lifecycle and the W3-v4 storage extension. Fixture work runs in
parallel worktrees, and measured jobs run serially on the Mac. Freeze a
small representative matrix before tuning.

### Superseded W2 next action

**Current (2026-11-18, after `5e42acb`):** attack the matched-lane W2
CPU/success gap at its measured boundary. Collect a wakeup-placement trace
on both engines at 9 vCPUs: per `sched_wakeup`/`sched_waking` target CPU,
whether the target was idle, and the waker/wakee API TIDs. Use the
existing profiler plumbing (`bench/native/diagnostics/w2-counters.md`,
`sched_trace.py`) and one matched block with exact 50,000-op C8 work. Then
choose between a scheduler-side guest candidate (for example, a newer
stable kernel's wake placement) and a VMM-side idle/IPI candidate. Do not
repeat SCHED_MC, LSE or HZ/PREEMPT. In parallel, re-baseline the other
cells (W1, W3–W10) on this host in both resource lanes, starting with W8
paired acceptance (queue item 3). Before launching any measured job, run
`pgrep -fl "ctrs daemon"`. A leftover campaign daemon silently serves
adopted trials.

### Earlier next action (2026-11-18 morning, partly superseded)

2026-11-18 host is reconstructed and the refreshed W2 matched-resource
baseline is recorded (see evidence doc). Before any qualification claim, the
entire per-cell matrix must be re-measured on this host against w8-v5 pins;
only then do the 2026-11-17 decisions (e.g. the leaf-only 49 Hz observer
validation plan at `experiment/w2-leaf-49hz` `4bf9107`) become actionable,
again in an exclusive window:

Use the [leaf-only command and paired plan](evidence/native-w2-equal-work-2026-11-17.md#leaf-only-observer-preparation)
from `experiment/w2-leaf-49hz` at `4bf9107`. First validate the guest
capture in one matched block using 50,000 exact C8 operations per cell.
Require every API thread, valid native samples and zero loss. Collect a
fresh paired overhead batch before using the profile for product selection.
All commands now reference `w8-v5` inputs (`.work/native-perf/inputs/w8-portfolio-v5/layout`).

The [W8 backing-allocation diagnostic](evidence/native-w8-content-state-2026-11-17.md#backing-allocation-during-deployment)
verified the three owned-file snapshots in a native diagnostic pair.
The [W8 cancellation diagnostic](evidence/native-w8-content-state-2026-11-17.md#interrupted-delivery-and-retry)
passed both native OrbStack conditions. Native ctrs reproduced a stalled
registry body read after the last pull client disconnected. The transport
fix wakes that read and passes the production-deadline regression with
the published 0.9.0 source plus the shutdown backport. Both native ctrs
cancellation and retry conditions now pass on the signed candidate.
[W5 mounted-input and phase-resource receipts](evidence/native-performance.md#w5-v3-mounted-inputs-and-resource-receipts)
pass native correctness on both engines. The [W1 warm restart proof](evidence/native-performance.md#w1-pinned-startup-and-database-restart)
passed on both engines with pinned images, exact writes and reads, and
the same owned database container and volume across the restart. Engine-cold
parity still requires an isolated OrbStack environment.
The [W10 recovery proofs](../bench/native/diagnostics/recovery-client.md)
passed API, database and queue interruption on both engines. The private
ctrs engine diagnostic passed with pinned images, a durable startup auth
file and exact acknowledged rows after the daemon and VM restarted.
The [W6 warm and uncached producers](evidence/native-build-boundaries-2026-11-16.md#w6-build-cache-conditions)
passed native compile-cache and artifact checks on the default builders.
The [W7 import and first-use producer](evidence/native-build-boundaries-2026-11-16.md#w7-per-build-first-use-receipts)
now proves compile and note cache behavior. Both engines passed all three
conditions for both apps with pair-specific note bytes.
The [W3 pinned transaction proof](evidence/native-performance.md#w3-commit-latency-and-persisted-rows)
passed all 300 commit receipts and exact persisted rows on both engines.
The [W9 fixed-work diagnostic](evidence/native-performance.md#w9-job-completion-measurement)
passed all four concurrency conditions per engine.
W11 qualification admission from `f0250a9` is integrated, with current
portfolio pins and recursive shared-runner source receipts. It verifies
fixture revisions against the case manifest. Its historical
[bounded checks](evidence/native-mixed-retention-2026-11-17.md#qualification-branch-refresh)
passed 49 W11 tests and 117 W2 tests. The asset lock remains in pilot status.
Landing checks on Linux: `make test-bench` ran 426 tests (15 skips);
`runner.py check w11` ran 50 (11 skips), and `check w2` ran 142 (3 skips).
No test failures; component checks still refuse native-only skips.
[W2 placement](../bench/native/diagnostics/w2-fixed-rate.md#native-placement-proof)
verified exact persisted work on the published port and guest network
in all twelve pinned trials. The two OrbStack offered-rate trials
completed all operations but exceeded the scheduling-lag budget.
W2 baselines now require the same pinned stack and prime the VM before
sampling. Both engines and both paths verified exact fixed work again
with matching input receipts and complete phase counters. Repeat pacing
admission in an exclusive window with the pinned baseline. Preserve the
10 ms budget and both failed receipts.
The [W4 v4 queue diagnostic](evidence/native-performance.md#w4-queue-latency)
verified the job and timing receipts at 1, 4 and 16 workers on both engines.
An equivalent [W10 engine interruption](../bench/native/diagnostics/recovery-client.md#owned-engine-recovery)
still requires an isolated OrbStack target.
Scored W3, W4, W6, W7 and W9 runs remain open.
The [qualification coverage inventory](evidence/native-mixed-retention-2026-11-17.md#qualification-coverage)
lists the next fixture gaps. Keep `assets.lock` in pilot status until the
contract, fixture versions and evidence are reviewed.

The reduced observer proof is complete. Source `7184d42` remains on
`experiment/w2-wake-entry-only`. Use the evidence record for its verified
probe coverage, scope and perturbation. A new run requires a distinct
observer policy or an exclusive confirmation window. The completed profiles
do not establish exclusive-store retry counts and give no basis for
repeating the rejected LSE or affinity candidates.

W11 v3's reviewed short proof is complete:
[exact results and command](evidence/native-mixed-retention-2026-11-17.md).
The 20,000-operation result leaves the 12-hour, growth, timing and durability gates open.

The final c3775ce functional job13731c9782f64101a2425063857ddf49 exits0 with
all four1000-operation trials correct,708 reads/292 writes each, complete phase
CPU and both periodic traces. Teardown is verified and all155 inputs rechecked.
Later failure-path corrections use offline regressions, not another identical
normal-path run. [Exact command and scope](evidence/native-sampler-lifecycle-2026-11-17.md).

Save pre/post gates and actual process, guest, power and thermal snapshots.
Ordinary gate0 has coexisted with hot Niceforge work. The owner subsequently
accepted some noise; a perfectly quiet window is no longer a prerequisite for
diagnostic W2 progress. Preserve unrelated work and disclose interference.
Keep inconclusive or structurally contaminated resource cells explicit. The
`-s` swap advisory is lane admission, not a performance gate.

W8 receipt validation is integrated at df1f418. Its source investigation and
remaining [content-state limits](evidence/native-w8-content-state-2026-11-17.md)
are explicit: new compressed identities/DiffIDs plus full delivery and runnable
contents do not establish guest-cache or page-cache absence. Preserve the66-test
component result and successful validation of two actual37-layer receipts.

Reconstruct the runtime from the repository. On the 2026-11-18 host the
reconstruction is done; the commands below reproduce it. Do not substitute
old `target/release` artifacts for the verified ones. Note: `cargo xtask
guest` rebuilds only the initramfs (hash must match `6ae4d3ab…`);
`cargo xtask kernel` rebuilds the kernel (expect a *different* hash — builds
embed a timestamp — but the same 18,800,648-byte size); `cargo xtask disk`
creates the sparse 1 TiB `data.img` from Docker. The bench suite needs
`TMPDIR=$PWD/.work/tmp`, and inline runner scripts must set
`runner.DOCKER = runner.find_docker()` before creating an `Engine`.

```sh
codex-campaign-closeout.py cancel
CARGO_ENCODED_RUSTFLAGS='' CARGO_BUILD_JOBS=4 cargo xtask guest
CARGO_ENCODED_RUSTFLAGS='' CARGO_BUILD_JOBS=4 cargo xtask kernel
cargo xtask disk
CARGO_TARGET_DIR="$PWD/.work/tmp/readiness-main-target" \
  CARGO_ENCODED_RUSTFLAGS='' CARGO_BUILD_JOBS=4 \
  cargo build --locked --release -p ctrs --bin ctrs
codesign --force --sign - --entitlements crates/ctrs/ctrs.entitlements \
  .work/tmp/readiness-main-target/release/ctrs
codesign --verify --strict --verbose=2 .work/tmp/readiness-main-target/release/ctrs
```

The 2026-11-18 signed host binary at main `19c3fc8` is SHA256
`be929fe2a81b960d0b4e2d3a02da864d91349eb9d1438cd74cd24be13795e9f2`
(6,617,104 bytes). The 2026-11-17 accepted binary (`2f37d02`,
`db20b210…`) and accepted kernel (`35087713…`) are unrecoverable history.
The guest initramfs hash is exact; the kernel hash is not asserted (see the
refresh evidence doc). Sparse guest disks require sparse receipts, never
whole-1TiB hashing.

The [readiness evidence](evidence/native-builder-readiness-2026-11-17.md) records
source invariants, native cases, comparison scope, binary identity and the
preserved C1 outlier. The [build boundary record](evidence/native-build-boundaries-2026-11-16.md)
records rejected gzip/zstd/default-build experiments, including the zstd expansion
limit failure; do not relax the unpack bound. The [uprobe record](evidence/native-python-uprobes-2026-11-17.md)
and [preemption record](evidence/native-preemption-2026-11-17.md) preserve the W2
counts and rejected kernel change. The [resource-cycle record](evidence/native-resource-cycles-2026-11-17.md)
records the rejected quiet policy. These outcomes are diagnostic, not qualified
speed claims. Earlier detailed checkpoints remain recoverable with
`git show 2f37d02:docs/native-performance-progress.md`; do not execute obsolete
next-action paragraphs from that historical revision.

## Ready queue

The queue below began against the old host and portfolio. For current
Mac runs, use the v6 portfolio in `.work/native-perf/inputs/w8-portfolio-v6/layout`
and the rebuilt W11 worker where required. Historical results remain
with their original image and worker pins.

1. Resolve W2 observer overhead using the exact next action above. Separate fixed work/offered load, saturation, on-CPU samples
   and off-CPU/wake latency. Commands and observer budgets:
   `bench/native/diagnostics/w2-counters.md` and `w2-fixed-rate.md`.
2. Integrated W11 admission binds the contract digest to
   `assets.lock` and validates the complete mixed workload and resource
   observation per cycle. The archived
   [native v4 proof](evidence/native-mixed-retention-2026-11-17.md#w11-v4-post-cleanup-observations)
   passed on both engines, with 181 frozen receipts unchanged. Complete
   the fixture producers, conditions and evidence needed to freeze the
   proposed cell contract. The integrated
   `mixed_job.py` uses the finite supervisor for admitted qualification
   legs. Launch the two 12-hour legs after their admission requirements
   are satisfied.
3. W8: retained-image pin checks are integrated and pass 68 component
   tests. The eight archived native inspections agree with the pins.
   Complete exclusive paired acceptance. Keep the identity guard, shared per-pair inputs,
   AB/BA order, actual transfer/deployment and source-state unknowns explicit.
   Never treat a deleted tag as a cold store or pool incompatible fixtures.
4. Interleave resource-cycle acceptance with W2/W10: declared5 post-warmup cycles,
   30s idle/reclaim minima, next-use cost and real allocation/growth. Commands:
   `bench/native/diagnostics/resources.md`. Unknown cache/exclusive allocation
   stays unknown; do not count sparse nominal capacity as physical reclamation.
5. Resolve Cached+Fsync/Full, guest flush and promised persistence guarantees
   before storage leadership claims. Full and50ms refusal-cache branches need
   separate exclusive confirmations. Preserve250ms/default Fsync meanwhile.
6. Resolve known correctness gaps, freeze candidate/inputs and a complete
   per-cell status matrix. Use the integrated frozen-readiness/resource-growth
   qualification admission; existing short W11 proofs must not be repeated as
   substitutes. Then execute the owner-requested full paired comparison,
   independent batch, fresh held-out app and finite12h W11 for each engine.
7. Benchmark-suite audit (2026-11-19), ranked by risk of a missed or false
   regression, then by wasted iteration. The entrypoint
   (`bench/native/pyramid.py`, README "Entrypoint") replaced the scratch
   queue scripts; the rest is open:
   1. Done: `reporting.py --anchor A --match B` compares each engine with
      itself across runs of the same workload and host. First use:
      container→Mac download vsock (`base-20261118T142833-063e`) against
      NAT (`base-20261119T133649-3bc7`) moved both engines 0.90 in step,
      so that cell's change is host drift, not the transport.
   2. Load admission (`f366b36`) judged the 1-minute load, which counts
      each engine's own vCPU threads: OrbStack's W12 trials ended at loads
      up to 11.8 from the same start as ctrs's, so pairs were rejected for
      the engine's behavior. `d211cae` records, per resource phase, cores
      busy outside the engine and harness (host_statistics busy minus the
      engine's counters minus the harness's rusage) and rejects above 2;
      records without it keep the load rule. Open: confirm on the first
      cohorts that the outside-CPU figure is near zero and alike for both
      engines on a quiet host (an engine process missing from the match
      would inflate its own figure). First cohort: quiet trials 0.9–1.4
      cores, ctrs about 0.2 above OrbStack in every W13 NAT pair, which
      points at host kernel networking charged to no engine process; the
      CPU metric undercounts ctrs on NAT paths until that is attributed.
   3. Metrics that do not measure what they name: W14 fresh p50 measures
      how many clients each engine admits at once (completion time is not
      a reported metric); W13 cells above half the loopback control are
      tool-limited on both engines; W14 reports every mode's metrics, most
      as "unmeasured". W13-overlap rejected every pair until `8b5709d`.
   4. A cohort with one load-rejected pair is invalid and reruns whole;
      on 2026-11-19 four of nine cohorts were lost that way. Topping up
      pairs was rejected: excluding pairs by their own end-of-trial load
      would drop the pairs where ctrs used the most CPU and bias toward
      ctrs. Instead `baseline --pair-quiet-load L` holds each pair until
      the 1-minute load is below L (decided before the pair runs); the
      scenario tier passes 4. Mid-pair foreign bursts are still rejected.
   5. Guest attribution: W13 already has an in-tree per-process guest CPU
      diagnostic (`diagnostics/w13_guest_cpu.py`, /proc snapshots around
      each transfer); use it for the remaining published-port download
      gap. Only the W14 agent syscall trace (tracefs, `common_pid==1`) was
      scratch; it diagnosed the spin fixed in `bf2ea2b`, so promote it
      only if W14 CPU (fresh 1.15×) needs it.
   6. W12 inputs (`kutt.tar.gz`, `w12-image.tar`) live in disposable
      `.work/tmp`; preflight fails when they are missing and names the
      rebuild (`fixtures/w12/prepare.py`, pinned by sha256 in its README).
      Open: W1, W4–W10 and W8 have no trial records on this host, so their
      costs are estimates until each runs once.

All work stays native ARM64/macOS. Installed-default behavior, disclosed
resource-matched default-driver results and identical-builder controls stay
separate. No mean may hide a CPU, memory, storage, recovery, tail, correctness or
durability loss. Full/workspace suites remain deliberate named manual gates;
qualification is conditional on the prerequisites above, never an automatic
check-command fallback. Continue until measured goals, explicit owner stop or
a specific blocker of all remaining authorized work.
