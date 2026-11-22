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
- Rejected: splitting a bind mount across two virtiofs devices. Three
  interleaved rounds for each writer count showed limited aggregate gains
  across separate mounts. A single mount uses one device's inode IDs.
  [Two-device evidence](evidence/native-w12-w13-2026-11-18.md#two-virtiofs-devices-on-one-share-2026-11-20)
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

### Combined release confirmation

After `cargo xtask all`, record the SHA-256 hashes of the signed binary,
kernel and initramfs. Verify the ad-hoc signature and virtualization
entitlement. Record the build source revision and the kernel build identity
when using a previously built `Image`.

Request XML explicitly before parsing the entitlement on the campaign Mac.
The default `codesign` display produces a human-readable representation.

```sh
codesign --verify --strict "$CTRS_BINARY"
codesign --display --xml --entitlements - "$CTRS_BINARY" > "$entitlements_plist"
/usr/libexec/PlistBuddy -c 'Print :com.apple.security.virtualization' "$entitlements_plist"
```

Run `make test` from the confirmation checkout. Set `CTRS_BINARY` to the
absolute path of the verified artifact and `CTRS_GUEST_DIR` to the matching
guest directory when running `conformance/smoke.sh`. The smoke script checks
the existing signature before using the binary. Run `tests/watch-recovery.sh`,
`tests/fuse-inode-bound.sh` and `tests/e2e.sh` with a dedicated ctrs daemon on
those assets and a fresh private data root, state and Unix socket. Start the
daemon with `CTRS_TEST_FSEVENTS_GATE` pointing to a private file path, and set
`CTRS_DAEMON_LOG` to its log for watch recovery. The e2e script also checks the
guest kernel feature probes. Keep the Docker client and builder state private.

Build the agent's layer tests from the same source with
`cargo test -p ctrs-init --target aarch64-unknown-linux-musl --release --no-run`.
Run the resulting test executable with the `linux::layers::tests::` filter in
a root ARM64 Linux container served by that private Mac VM. Include the gzip
member concatenation and truncated-stream cleanup assertions. Verify the
artifact hashes again after all checks and retain results by command.

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

### Installed-default W1 warm stack cohort

Run `base-20261122T093654-6f3a` used clean source `be29aa5` and the same
signed binary and guest assets as W2. Both engines used 9 vCPUs with their
installed memory settings. All ten alternating pairs matched the v6
portfolio and SQL seed. Every leg verified initial DB and cache reads,
the exact written value after PostgreSQL restarted on the same volume,
and a new write and read after restart. Health checks polled at 100 ms.

| Metric | Paired median ratio | 95% CI | Descriptive result |
| --- | ---: | ---: | --- |
| Compose up to health | 0.8475 | 0.7184–0.9122 | Strict win |
| Compose up to exact DB/cache roundtrip | 0.8477 | 0.7186–0.9121 | Strict win |
| Database restart to verified reads and write | 0.6855 | 0.6749–0.6983 | Strict win |
| Total time through verified recovery | 0.8146 | 0.7153–0.8654 | Strict win |
| Sampled peak physical footprint | 0.4191 | 0.3870–0.4293 | Strict win |
| Measured engine CPU | 0.4459 | 0.4262–0.4622 | Incomplete, host NAT CPU uncharged |

Lower ratios favor ctrs. Median verified restart time was 0.623 s on ctrs
and 0.919 s on OrbStack. The stop-to-return internals were uninstrumented,
so the result gives the client-observed time through verified recovery.
The ctrs trials used 91 host NAT connections in total. Engine-cold
comparison remains open while OrbStack shares its daemon and store.

```sh
python3 bench/native/pyramid.py run --name w1-stack:cohort
python3 bench/native/reporting.py --match base-20261122T093654-6f3a
```

`trials.jsonl` SHA-256
`5f2d444b5b1e58daed9e90375306b33f613a9210b3d2baa166baafe2a1aaf25d`.

#### W1 engine-cold admission on ctrs

The cold entry point creates a fresh private ctrs store, imports the three
pinned v6 images from the local layout, and stops the preparation daemon.
It requires the private socket to disappear before timing starts. The next
launch verifies the same images and seed, runs Compose through the first
exact DB/cache roundtrip, and finishes with the existing database restart
and owned cleanup checks. The cold metrics cover daemon readiness and launch
through the first exact roundtrip. They include runtime readiness polling and
exclude the image import. VM resource sampling begins at the existing sampler
boundary after guest wake.

```sh
python3 bench/native/runner.py run --case W1 --engine ctrs --state cold --cold
```

Use the signed release, installed defaults and the frozen local v6 layout.
This is a standalone ctrs diagnostic. Equivalent engine-cold measurements on
an isolated OrbStack target remain open.

OrbStack's installed `create --isolated` option isolates a Linux machine's
host integration. The built-in Docker engine and those machines still share
one OrbStack VM. W1 cold and W10 whole-engine comparison need a dedicated
native OrbStack installation whose process and guest disk belong to the
campaign. Reproduce both engine legs on that host. The runner rejects a
W1 cold request against the shared socket before engine setup.
[OrbStack architecture](https://docs.orbstack.dev/architecture)

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

Run the full migration comparison with the verified signed Mac release and
its isolated initialized warm store. Keep the release binary and guest
assets fixed across all pairs.

```sh
python3 bench/native/runner.py baseline --case W3 --a ctrs --b orbstack \
  --resource-lane installed-default --pairs 10 --pair-quiet-load 4 --max-pairs 16
```

The W3 and W3-v4 reports retain paired ratios and confidence intervals.
Favorable assessments are marked `durability-unverified` until both engines'
host flush contracts are established. An orderly PostgreSQL restart verifies
committed logical state. Guest `fdatasync` and device flush tracing establish
guest behavior. The current ctrs VZ attachment uses [Fsync](https://developer.apple.com/documentation/virtualization/vzdiskimagesynchronizationmode/fsync?language=objc),
which can return while data is still in the drive cache. Apple documents
cache-to-permanent-storage synchronization for [Full](https://developer.apple.com/documentation/virtualization/vzdiskimagesynchronizationmode/full?language=objc).
OrbStack's corresponding host guarantee remains unknown. Obtain its explicit
contract or separately qualify acknowledged commits across host failure on a
disposable setup before claiming a comparative durability-qualified result.

The public OrbStack volume documentation identifies where named-volume data
lives and how to back it up. The host flush guarantee remains unspecified
there. [OrbStack volume documentation](https://docs.orbstack.dev/docker/file-sharing)

The next ctrs-only diagnostic measures the stronger Full attachment with
the existing eight-client W3-v4 pgbench fixture. Earlier Full probes used
one writer. Use a detached checkout of signed release source `99db1aa` and
cherry-pick `f536b6e` to change only the disk attachment mode. Build the
signed host executable with `RUSTC_WRAPPER="" CARGO_ENCODED_RUSTFLAGS="" cargo xtask host`.
Use the same verified release kernel, initramfs, disk template, and v6
PostgreSQL image in private stores. Alternate Fsync/Full, Full/Fsync and
Fsync/Full, using a fresh named volume per leg. Record the signed binary
digest and the raw W3-v4 results for every leg. Each run must check all
16,000 write transactions after PostgreSQL restart and retain all three
PostgreSQL durability settings. This measures the cost under group commit.
Equivalent host durability across engines remains a separate gate.

Run the instrumented W3-v4 trial with `RunContext.design` set to
`storage-sync-diagnostic`. Both legs pin `wal_sync_method=fdatasync` and turn
on `track_wal_io_timing`. Read `pg_stat_wal` immediately before and after the
write pgbench command, before copying logs or starting the read-only phase.
Require a stable statistics reset marker and positive count and time deltas.
The counters are PostgreSQL cluster totals over that interval. They can include
background WAL activity and pgbench preparation work.
[PostgreSQL WAL statistics](https://www.postgresql.org/docs/17/monitoring-stats.html#MONITORING-PG-STAT-WAL-VIEW)

### W4 pipeline comparison with common images

Prepare one Linux ARM64 v4 worker image from the pinned W4 latency
Dockerfile on OrbStack. Save `np-w4-events:v4` and verify the archive hash
before loading it into the private ctrs store with the signed Mac release.
Preload the pinned Redis reference on each engine. In each trial, verify the
ordered layers and launch configuration of both images and run by the
inspected IDs. The reporter rejects pairs whose input receipts differ.

Run one native admission pair before the ten-pair installed-default cohort.
Each leg must verify all 200 jobs and 400 artifacts at 1, 4 and 16 workers.
Check queue p95 and p99 and the CPU and sampled footprint receipts for each
condition. Image preparation stays outside the measured pipeline interval.

```sh
python3 bench/native/runner.py baseline --case W4 --a ctrs --b orbstack \
  --resource-lane installed-default --pairs 10 --pair-quiet-load 4 --max-pairs 16
```

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
This covers uncached builds under installed defaults. Complete CPU accounting
and fresh confirmation remain open.

### Installed-default W6 primed-cache cohort

Run `base-20261122T102417-474d` at `50c827d` used the same signed binary,
guest assets and default engines as the uncached W6 run. Each trial primed
both applications with a unique pair stamp and verified a completed uncached
compile-and-test vertex. It then timed buildx and image load with the same
context. All 40 measured build vertices were cache hits. Both artifact hashes
matched on every trial. All ten alternating pairs were admitted, with zero
correctness failures and complete footprint samples. Both engines reported
9 vCPUs. Guest MemTotal remained 8,407,957,504 bytes on ctrs and
63,157,620,736 bytes on OrbStack. Maximum one-minute host load was 3.003.

| Metric | ctrs median | OrbStack median | Paired ratio and 95% CI | Descriptive result |
| --- | ---: | ---: | --- | --- |
| Hyperfine cached build and load | 264 ms | 567.5 ms | 0.4755 [0.4481, 0.4825] | Strict win |
| zlib cached build and load | 266.5 ms | 597.5 ms | 0.4479 [0.4461, 0.4606] | Strict win |
| Sampled peak physical footprint | 8.640 GB | 7.124 GB | 1.1522 [0.9487, 1.2879] | Inconclusive |
| Summed peak RSS | 14,663,416 KiB | 10,054,536 KiB | 1.4173 [1.0804, 1.5276] | Loss |
| Measured engine CPU | 1.47 CPU-s | 2.83 CPU-s | 0.5182 [0.4912, 0.5548] | Incomplete host NAT accounting |

The measured path reused the compile-and-test results. It timed the full
cached solve and image import, without attributing the difference to either
step. Pair 9 retained a 911 ms ctrs Hyperfine result with a verified cache hit
and matching artifact. Sampling began after both uncached primes. The sampled
peak includes memory retained from priming and later verification. It rose
from 3.03 GB to 8.64 GB on ctrs and stayed near 8.64 GB from pair five onward.
Each ctrs trial recorded 118–120 NAT connections across priming and measured
work. The cohort leaves complete CPU accounting, resource parity and fresh
confirmation open.

```sh
python3 bench/native/pyramid.py run --name w6-build-warm:cohort
python3 bench/native/reporting.py --match base-20261122T102417-474d
```

`trials.jsonl` SHA-256
`92c0b7333a03a249c23de1a654182d8d64f8ca92686eb561635bb3b310da4b4c`.

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

The next screen used a 5,120 MiB ceiling. The 6,144 MiB slot's peak
plateau was about 47 MB above its ceiling, and its endpoint guest used
counter stayed below 0.59 GB. These readings motivate a lower ceiling
and leave transient cache pressure during a build unresolved. The screen
includes all startup pairs, uses the same footprint and build-time
bounds as the 6,144 MiB screen, and requires a zero-OOM receipt from
each engine slot.

Run `base-20261122T110954-3f61` used clean source `34141a3` and admitted all
ten paired uncached builds. All legs reported their assigned memory ceilings
at 9 vCPUs and zero guest OOM kills. The Rust and zlib artifact hashes each
matched across all 20 legs. Complete footprint samples were available.

| Metric | 5,120 / 8,192 MiB paired median | 95% CI | Screen |
| --- | ---: | ---: | --- |
| Sampled peak physical footprint | 0.6269 | 0.6268–0.8020 | Met 0.95 upper bound |
| Rust build time | 1.0075 | 0.9984–1.0292 | Met 1.03 upper bound |
| zlib build time | 1.0171 | 0.9959–1.0301 | Missed 1.03 upper bound |
| Measured engine CPU | 1.0149 | 1.0061–1.0469 | Incomplete |

The 5,120 MiB slot reached about 5.42 GB of host footprint in pair two.
The installed default reached about 8.64 GB in pair five. The zlib upper
bound narrowly missed the predeclared limit, so the cap remains a candidate.
Host NAT use leaves CPU accounting incomplete.

```sh
python3 bench/native/pyramid.py run --name w6-build:memory5120
python3 bench/native/reporting.py --candidate --match base-20261122T110954-3f61
```

`trials.jsonl` SHA-256
`683de0e7768b343959d550c97a674acfae6f8d5a2bf263babbc0166be50b3333`.

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

The next Mac build comparison also verifies runtime contents. After the
timed work and sampling finish, it hashes each loaded Hyperfine executable
and records the versions and file-content hashes of the installed HTTPie
runtime distributions. It compares these receipts across uncached, warm and
incremental builds within each trial and across each engine pair. Generated
Python bytecode and wheel installation metadata are outside the runtime file
receipt. This check can catch runtime drift. A frozen comparison also needs
reproducible build-time dependencies. Keep the earlier W7 results separate
and admit one native pair before the new ten-pair cohort.

All 20 uncached HTTPie legs in `base-20261122T065539-5b0c` downloaded the
same 15 wheel filenames. `bench/native/fixtures/w7/httpie/wheels-arm64.json`
records those files and their SHA-256 digests from the exact PyPI releases.
Restore and verify them with
`python3 bench/native/fixtures/w7/httpie/prepare_wheels.py`. The resulting
wheelhouse is for Linux ARM64 and CPython 3.13. A clean restore verified all
15 wheel hashes. The lock SHA-256 is
`321ffcf392383c35e0c3101516233a0e26c684a1a5749a967bbeea4e379d52ec`.
Setuptools 84.2.1 is the recorded runtime version and the pinned build
backend for the new fixture. [PyPI JSON API](https://docs.pypi.org/api/json/)

`w7-v4-offline-httpie` was the first offline revision. It copies the verified wheels
into the HTTPie context and runs its BuildKit steps with `--network=none`.
The Dockerfile installs the pinned build tools, builds the sdist without
build isolation, installs exactly the local wheels and runs `pip check`.
Each trial records the wheel lock digest and compares the installed package
set with the lock. The Hyperfine recipe still uses the network with
`cargo build --release --locked`. Admit one pair before running a ten-pair
cohort. Revision 3 remains the archived network-resolved comparison and
the Linux amd64 workload.

The pinned Hyperfine source contains 134 crates.io packages in `Cargo.lock`
with no Git dependencies. Run
`python3 bench/native/fixtures/w7/hyperfine/prepare_vendor.py` from the repo
to restore the offline source archive. It runs `cargo vendor --locked` with
a private Cargo home, checks the registry checksums against the lock, then
resolves `aarch64-unknown-linux-gnu` with `cargo metadata --frozen` from an
empty Cargo home. All 104 registry crates in the filtered graph resolved
from the vendored directory. Cargo 1.99.1 and the repository's Cargo
1.102.0 nightly independently produced archive SHA-256
`46ac26bd0205449fff0f866be91cb730bd27ae05d4708964f5f2afc79c129e7e`.
Native offline Hyperfine builds and cache-state admission remain open.
[Cargo vendor command](https://doc.rust-lang.org/cargo/commands/cargo-vendor.html)

`w7-v5-offline-builds` uses this archive in the Hyperfine context and compiles
with `cargo build --release --frozen`. Both build commands use
`--network=none`. Base image pulls remain part of untimed preparation.
The runner records the Cargo vendor and wheel lock digests and verifies
both apps across the three cache states. Use `w7-buildx:cohort` after a
native pair admits both builds. The changed contexts require a new cohort.

#### Frozen HTTPie first-use input

Prepare a single Linux ARM64 image using the pinned W7 HTTPie Dockerfile,
the 3.2.4 sdist from `assets.lock`, and the note from pair 10's incremental
OrbStack probe above. Build once on OrbStack and save one platform using
`docker image save --platform linux/arm64`. Give the image a unique campaign
tag. Archive the BuildKit metadata and the Dockerfile, sdist and note hashes.
Use `httpie_first_use.archive_identity` to record the archive digest, config
digest and ordered rootfs DiffIDs. After loading the same archive into each
engine, require its inspected native platform and ordered DiffIDs to match.
Preserve engine-specific IDs alongside the common bytes. A fresh build may
resolve dependencies, so the resulting archive starts a new cohort.

The comparison measures `docker run --rm --pull=never IMAGE http --version`
with the engine already ready and image import outside the timed boundary.
Verify the exact `3.2.4` output and the frozen incremental note. Retain the
import duration in a separate receipt. First-create materialization, when
required by the engine, occurs inside the measured command. Use fresh private
ctrs stores to restore the imported-but-unrun condition across pairs. Reload
the archive on OrbStack under its already verified campaign tag. OrbStack's
materialization during import is part of its preparation. Keep both installed
defaults and report the measured allocations, ten alternating pairs, and
resources scoped to first use.

```sh
CTRS_GUEST_DIR="$release/guest/out" python3 bench/native/runner.py httpie-first-use \
  --archive "$archive" --receipt "$freeze_receipt" \
  --ctrs-binary "$release/target/release/ctrs" --pairs 10
```

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
The process split puts most of the measured gap in the VM helper. Its CPU
total combines guest scheduling, transport and app code. See the
[guest-direct cohort below](#installed-default-w2-container-to-container-fixed-work-cohort).

```sh
export PATH="/opt/homebrew/bin:$PATH" TMPDIR="$PWD/.work/tmp"
python3 bench/native/pyramid.py run --name w2-api:cohort
python3 bench/native/reporting.py --match base-20261122T081048-91d4
```

`trials.jsonl` SHA-256
`5aefe93dc8901170f7191adfbd2710abea89ff69628f8c9118f53327e2d0cb67`.

### Installed-default W2 container-to-container fixed-work cohort

Run `base-20261122T091635-df7a` used clean source `c26aaac` and the
same signed binary and guest assets as the published-port cohort. All ten
alternating pairs matched the v6 portfolio, SQL seed, load client and API
file receipts. Each leg completed 50,000 mixed read/write requests at
eight-client concurrency, verified every persisted write and recorded
zero errors. Both guests had 9 vCPUs. Guest MemTotal was 8,407,957,504 bytes
on ctrs and 63,157,620,736 on OrbStack 2.2.5 (Docker 29.8.2). Maximum
outside-engine CPU during the workload was 0.83 core.

| Metric | Paired median ratio | 95% CI | Descriptive result |
| --- | ---: | ---: | --- |
| Measured engine CPU per verified request | 1.1306 | 1.1234–1.1434 | Loss |
| Sampled peak physical footprint | 0.4427 | 0.4124–0.4627 | Strict win |
| Request rate (OrbStack / ctrs) | 0.5814 | 0.5764–0.5898 | Strict win |
| API p50 | 0.5946 | 0.5910–0.6080 | Strict win |
| API p95 | 0.4793 | 0.4728–0.4839 | Strict win |
| API p99 | 0.4544 | 0.4443–0.4592 | Strict win |

Lower ratios favor ctrs. Median request rates for this fixed work were
2,144 and 1,247 requests/s on ctrs and OrbStack, respectively. The
limiting component at eight-client concurrency remains unknown. The CPU
loss persists with zero ctrs host NAT connections. Median workload-phase
engine CPU was 39.19 s on ctrs and 34.54 s on OrbStack, including the
in-guest client on both engines. The API cgroup recorded medians of 24.10 s
and 19.98 s including counter-reader execution. These process totals
leave the CPU contribution of each transport unresolved.

```sh
export PATH="/opt/homebrew/bin:$PATH" TMPDIR="$PWD/.work/tmp"
python3 bench/native/pyramid.py run --name w2-container-to-container-fixed-work-c8:cohort
python3 bench/native/reporting.py --match base-20261122T091635-df7a
```

`trials.jsonl` SHA-256
`2ddff2311be62f118080899d69f8c798d90babb77a849000101e0abd3b744899`.

### Installed-default W2 published-port fixed offered rate

Run `base-20261122T093101-7063` used the same clean source and artifacts
as the guest-direct fixed-work cohort. The pinned v3.2 client scheduled
10,000 operations at 500 requests/s across four serial HTTP connections.
All four legs completed the exact work with zero request errors and
verified every persisted write. The two ctrs legs met the 10 ms start-lag
budget. OrbStack had 53 late slots in pair 1 and 41 in pair 2. The runner
stopped at the predeclared two-consecutive-invalid-pair rule, leaving zero
valid pairs and no paired latency, CPU or footprint estimate.

In the two OrbStack legs, 51 of 53 and 38 of 41 late slots had an in-flight
predecessor on the same connection when the slot's lateness budget expired.
Each connection receives a slot every 8 ms. The breakdown locates backlog
at the connection and leaves the source of the initiating delays open.
The maximum outside-engine CPU during load was 0.76 core.

```sh
python3 bench/native/pyramid.py run --name w2-published-port-fixed-offered-rate:cohort
python3 bench/native/reporting.py --match base-20261122T093101-7063
```

`trials.jsonl` SHA-256
`036489f606816c399d038af754d2dd220313cd840fcecc3116bd396f4d3df7ec`.

### Installed-default W2 container-to-container fixed offered rate

Run `base-20261122T093306-1b10` used the same pinned workload, schedule
and artifacts through an owned peer on the application network. All four
legs completed all 10,000 operations, verified the exact persisted writes
and recorded zero request errors. There were zero ctrs host NAT connections.
The maximum outside-engine CPU during the workload was 0.64 core.

OrbStack had 8 and 19 late slots, and ctrs had 0 and 1, in pairs 1 and 2
respectively. The previous request on the same worker was still in flight
at the lateness deadline for all 28 late slots. The stop rule fired after
pair 2. The cohort has zero valid pairs and no paired performance estimate.

```sh
python3 bench/native/pyramid.py run --name w2-container-to-container-fixed-offered-rate:cohort
python3 bench/native/reporting.py --match base-20261122T093306-1b10
```

`trials.jsonl` SHA-256
`231f577b8eeb6bdaf972c8479bb0e3b95813d49569ce4cacde4eca62289982a1`.

### W2 leaf observer overhead on the guest-direct workload

The 49 Hz confirmation at `44e542f` ran all ten alternating blocks.
Each of the 40 legs completed 50,000 exact requests at concurrency eight.
Each profiled leg covered all nine API threads with zero recorded loss.
Block 2 failed the ctrs profiler-off post-workload gate. PID 74836,
identified as hot by that gate, matches the owned VM PID and kernel
start identity in the receipt. The original rule leaves nine valid blocks
and the observer unqualified.

| Engine and interval | Median on/off ratio | Descriptive 95% CI |
| --- | ---: | ---: |
| ctrs API CPU | 1.0157 | 0.9878–1.0455 |
| ctrs workload wall time | 1.0103 | 1.0014–1.0222 |
| OrbStack API CPU | 1.0426 | 1.0154–1.0698 |
| OrbStack workload wall time | 1.0276 | 1.0163–1.0499 |

API CPU intervals include counter quantization. The OrbStack CPU interval
extends beyond the 5% budget even among the admitted blocks. The smallest
per-thread profile had 26 samples, motivating a separate lower-frequency
candidate with the same coverage requirement.

Pass the following run directories, in order, to
`bench/native/diagnostics/w2_observer_report.py`. All names have the prefix
`w2-guest-client-cpu-leaf-20261122T`.

```text
094448-a9cb  094748-52c1  095046-b953  095344-bba3  095645-0670
095943-5c54  100240-186f  100536-3e9c  100833-6b1c  101131-a496
```

Batch log SHA-256
`f620b515afc922f5e6c6b96c32f05d44a58a25fe1076e55f0025519436187f04`.

#### Outside-engine CPU admission

The native block `w2-guest-client-cpu-leaf-20261122T104218-c699` exercised
the new host-counter receipts at source `bbe7b30` with the same signed
artifacts and 49 Hz observer. Each leg verified 35,140 reads and 14,860
writes, with zero errors and clean teardown. The profiling legs sampled
all nine API threads with raw event coverage verified. The smallest
thread sample counts were 42 on ctrs and 26 on OrbStack.

| Engine | Profiler off, outside-engine cores | Profiler on, outside-engine cores |
| --- | ---: | ---: |
| ctrs | 0.161 | 0.190 |
| OrbStack | 0.793 | 0.787 |

All four phase receipts had complete process CPU boundaries and both host
gate calls exited zero for each leg. The ctrs post-run hot-process lists
named PID 1902, which was the owned VM in both boundary receipts. The
report admitted one of the ten blocks required for an overhead verdict.
Independent review of host processes remains required. The previous nine
valid 49 Hz blocks use the older admission policy and stay separate. The
25 Hz observer has its own pending admission.

```sh
python3 bench/native/diagnostics/syscall_pilot.py \
  --tools-archive "$native_tools_tar" --image-refs "$common_refs_json" \
  --ctrs-binary target/release/ctrs --profile-kind cpu-leaf \
  --client-location guest --operations 50000 --concurrency 8
python3 bench/native/diagnostics/w2_observer_report.py \
  .work/native-perf/results/w2-guest-client-cpu-leaf-20261122T104218-c699
```

Use the API, PostgreSQL and Redis references from the same v6 portfolio
loaded by both engines. The tool archive SHA-256 is
`990b13e40dcd7726198911b133c2ac59a7df8576f7c914b88b5f4b6527340ae4`.
The block's `plan.json` SHA-256 is
`bef3d2d0f196dbce83946622e1177e186a659cdc2d250461acb132a441689499`.

### W9 parallel job resource admission

Run `base-20261122T094007-1ee3` used source `3ad2f5b`, installed defaults,
and the digest reference shared by both engines in the v6 portfolio
deployment. Each engine completed 16 verified jobs at each concurrency
of 1, 4, 8 and 16. All eight intervals returned CPU and sampled physical
footprint receipts with no resource errors. Each interval included at
least two samples between the boundaries. ctrs used zero host NAT
connections.

The earlier run `base-20261122T093626-994f` used an image reference from
the isolated W11 store. The installed-default ctrs store lacked that
reference and rejected the launch. The W9 admission repeat and full
cohort used the common deployment reference from both engines' image
receipts.

```sh
BENCH_W9_IMAGE_REF="$common_marked_digest_ref" python3 bench/native/pyramid.py run --name w9-jobs
python3 bench/native/reporting.py --match base-20261122T094007-1ee3
```

`trials.jsonl` SHA-256
`e48361975e639d0f4601623517eff52ebb49524c7315cf9a18e663021884a213`.

### Installed-default W9 cohort

Run `base-20261122T101434-f89b` used clean source `3ad2f5b`, the same
signed Mac binary and guest assets as W2, and the common v6 Marked
digest. All ten alternating pairs verified 16 fresh containers' builds
and CLI tests at each of four concurrencies. Both engines observed
9 vCPUs with installed memory limits. Each job ran with networking off.
ctrs recorded zero host NAT connections. The busiest measured phase
had 1.84 cores outside the engine and harness.

| Concurrency | Batch time | Job p95 | CPU per job | Sampled peak footprint |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 0.436 [0.430, 0.438] | 0.436 [0.430, 0.438] | 0.490 [0.487, 0.496] | 0.548 [0.532, 0.559] |
| 4 | 0.287 [0.277, 0.301] | 0.287 [0.277, 0.301] | 0.527 [0.519, 0.532] | 0.540 [0.521, 0.547] |
| 8 | 0.223 [0.215, 0.230] | 0.223 [0.215, 0.230] | 0.535 [0.532, 0.543] | 0.528 [0.507, 0.537] |
| 16 | 0.222 [0.206, 0.231] | 0.222 [0.206, 0.231] | 0.557 [0.543, 0.562] | 0.521 [0.512, 0.527] |

These paired median ctrs / OrbStack ratios and 95% intervals describe
the installed-default cohort. At concurrency 16, median batch time
was 0.480 s on ctrs and 2.190 s on OrbStack. Batch times include
create, start, build, test and removal. With 16 observations per batch,
nearest-rank p95 is the slowest job in that batch. The limiting component
remains unattributed. All resource phases returned verified boundaries and
interior samples. The shortest ctrs phases had just one interior sample,
so transient footprint peaks may be missed. Engine CPU excludes the
host CLI and coordinator.

```sh
BENCH_W9_IMAGE_REF="$common_marked_digest_ref" python3 bench/native/pyramid.py run --name w9-jobs:cohort
python3 bench/native/reporting.py --match base-20261122T101434-f89b
```

`trials.jsonl` SHA-256
`8e354c33086fa356b6d9ebe52403270adc69a04dae8195f54074345268b9e012`.

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

The first allocation attempt, `w8-paired-1efa95ef1e7d`, stopped at
admission on both engines. The inventory found the legacy
`npw8-reg-ctrs` and `npw8-reg-orbstack` containers. The retained and
derived no-load diagnostics returned no allocation snapshots. The retry
uses the fresh ctrs release store. On OrbStack, check the archived full
container ID, registry image, localhost port, restart policy and named
volume before temporarily stopping its legacy campaign registry.
Restore its original running state after the diagnostic. Any unrelated
running container still prevents allocation admission.

Run the scored installed-default cohorts on the same signed release after
the retained and derived cancellation checks. Each of the four combinations
gets ten alternating pairs and its own result directory. Check OrbStack's
running container inventory before and after each measurement. Temporarily
stop only the verified legacy campaign registry and restore its original
running state after the cohorts. Preserve complete timing and correctness
receipts, and report the backing-allocation diagnostic separately.

```sh
for content in retained derived; do
  python3 bench/native/runner.py w8-baseline --layout "$v6_layout" \
    --ctrs-binary "$signed_binary" --resource-lane installed-default \
    --content "$content" --pairs 10
  python3 bench/native/runner.py w8-baseline --layout "$v6_layout" \
    --ctrs-binary "$signed_binary" --resource-lane installed-default \
    --content "$content" --pairs 10 --under-load
done
```

#### Mac release check after the shared layer-install change

Source `83e9c15` changes the gzip decoder compiled into the Linux guest
and shares the streaming reply path with macOS. Verify on a fresh signed
host binary and rebuilt initramfs. The current check pins `99db1aa` and
uses a fresh ctrs data root with the existing kernel and sparse disk
template. The earlier Mac cohorts used the prior signed artifacts.

In an isolated checkout, copy the existing `Image` and `data.img` into
`guest/out` with an APFS clone for the disk. Build with
`CARGO_ENCODED_RUSTFLAGS="" cargo xtask all` and verify the signature with
`codesign --verify --strict --verbose=2 target/release/ctrs`. Run the W8
registry pilot with `--engines ctrs` to seed and verify the four pinned
services. Then run `w8-cancel --engine ctrs --resource-lane installed-default`
for both `--content retained` and `--content derived`, using the same
binary, v6 layout and private store. Record the binary and boot asset
hashes with the pull, cancellation and retry receipts.

The signed `99db1aa` release passed this check on 2026-11-22. The first host
test build stalled in the installed `kache 1.0.0` wrapper. Restarting the
same checkout with `RUSTC_WRAPPER=""` for the host build passed all three
`daemon::vmlink::tests` and completed `cargo xtask all`. The ad-hoc signature
verified and the XML entitlement was `true`.
[Cargo environment variables](https://doc.rust-lang.org/cargo/reference/environment-variables.html)

| Release artifact | SHA-256 |
| --- | --- |
| Signed `ctrs` | `10667e6d929207167f1812e5fd41c7ad6474f12bc9d5a42788af5ae027c93d17` |
| Reused `Image` | `19657ca4cc150ae8d04d003ac494676bcc5845dd3a3a21cd6bfb17df605d4e6f` |
| Rebuilt `initramfs.cpio` | `fb0f832b79eca9463d3aafb0bebdff8a5e620e2ff1779c896727fc91d3e32c87` |

The v6 portfolio booted all four pinned services. Both cancellation controls
exited with signal status 130, recorded an incomplete 65,536-byte write to
the selected layer and verified a clean retry of the same digest. The retained
and derived retries transferred 58,602,018 and 58,602,021 bytes for those
layers. These are single-engine correctness checks. Both receipts have
`measurement_valid=false`.

| Run | `result.json` SHA-256 |
| --- | --- |
| Retained `w8-cancel-1db513a1d825` | `36772a317f274fcfe3bde97710bf0482616740916f2c6b298ff25a2e6551398c` |
| Derived `w8-cancel-27f60aa4547b` | `186aed73d961d6afabae440581a04d729a66fc17aa04b8efc96cf893d99ce1bd` |

### Installed-default W10 API recovery cohort

Run `base-20261122T104521-90d4` at `ca24add` admitted all ten alternating
pairs. Both engines ran the same pinned v6 portfolio and SQL seed at
installed defaults with 9 vCPUs. Eight clients ran persistent 20-second
workloads with a 30% offered write mix. The owned API was interrupted after
six seconds and held down for three seconds. Every acknowledged write was
present and exact. Across the ten trials, ctrs verified 94,117 acknowledged
writes plus 3 exact rows with interrupted acknowledgements. OrbStack
verified 69,368 acknowledged writes plus 33 exact uncertain rows. Both
engines recorded zero unexpected errors. Maximum measured outside-engine
load was 1.02 cores.

| Metric | ctrs median | OrbStack median | ctrs / OrbStack paired ratio and 95% CI |
| --- | ---: | ---: | --- |
| Start command to first exact read | 547.1 ms | 442.5 ms | 1.2385 [1.1952, 1.3145] |
| Recovered request p99 | 6.79 ms | 11.16 ms | 0.6092 [0.5744, 0.6159] |
| Measured engine CPU per successful response | 1,010 µs | 866 µs | 1.1671 [1.1482, 1.1734] |
| Sampled peak physical footprint | 2.39 GB | 5.86 GB | 0.4036 [0.3913, 0.4100] |

The start command itself took a median 21.6 ms on ctrs and 101.4 ms on
OrbStack. Median time from command return to the first exact read was
522.7 ms and 342.7 ms respectively. The gap is in the post-command
readiness interval. The saturation driver recorded 45,178–48,620 expected
outage failures per ctrs trial and 42,482–44,834 per OrbStack trial.
Recovered p99 uses successful load after the first exact read. The CPU
denominator counts successful load responses and the counter omits host
NAT CPU. The measured CPU is already higher on ctrs. Database, queue and
isolated whole-engine recovery remain separate cells.

Reproduce at `ca24add` on `origin/campaign/w10-recovery-inputs` with
the original signed Mac artifacts and the preloaded v6 image references.

```sh
python3 bench/native/runner.py baseline --case W10 --a ctrs --b orbstack \
  --resource-lane installed-default --interrupt-service api --pairs 10 \
  --pair-quiet-load 4 --max-pairs 16
python3 bench/native/reporting.py --match base-20261122T104521-90d4
```

`trials.jsonl` SHA-256
`d8002cc4f1717f89df692e27ecbf5340d8b3893fc670ea8bb1a40a8e0b7772f3`.

The archived `attempts.jsonl` records narrow the readiness gap. In all
ten ctrs trials, a readiness probe connected to the published port within
1.95 ms of the start command returning. Before the first exact response,
98 readiness probes opened a connection and received no HTTP response,
87 of them with a connection reset. OrbStack had 113 connected probes
close without a response and 10 connection refusals. These are client-side
observations of the published port.

Use the earliest exact read started after the command returns from either
the load workers or the dedicated readiness probe. From command start,
that read completed in 534–541 ms on ctrs and 405–460 ms on OrbStack.
This diagnostic endpoint retains the gap even though the dedicated probe's
observed scheduling interval varied. The ctrs refusal cache is a specific
hypothesis because the timing clusters near two 250 ms cache lifetimes.
Check the actual cache insertion, first-hit and expiry events before
attributing the gap or changing the timeout.

Run a separate ctrs-only diagnostic on the same binary and pinned stack
using `CTRS_LOG=debug` and the original client count, seed, outage and load
duration. Preserve the daemon's raw event interval and use the readiness
attempt's wall-clock receipt to align the first exact response with the
cache events for the owned API target. Keep the diagnostic separate from
the scored pair observations.

Inspect the Compose `api` container immediately after `up` and before
`down`. `recovery_trace.api_backend` verifies the project and service labels,
loopback port binding and guest IPv4 endpoint. Require both inspections to
agree before calling `recovery_trace.refusal_recovery_trace` with
`timeline.json`, the `attempts.jsonl` rows, the daemon log lines and the API
endpoint. The receipt reports only cache events for that endpoint during
the interruption through the first exact post-restart read. It reports the
observed wall-to-monotonic clock offset range and includes the daemon log's
millisecond resolution in event time bounds.

### Installed-default W10 database recovery cohort

Run `base-20261122T105526-a8d2` admitted all ten alternating pairs at
`ca24add` with the same resources and inputs as the API cohort. The trial
interrupted the owned PostgreSQL container while the API and Redis remained
up. All twenty exact-state checks passed with zero unexpected errors. ctrs
verified 94,451 acknowledged writes and 384 exact rows with interrupted
acknowledgements. OrbStack verified 68,546 acknowledged writes and 450
exact uncertain rows. The maximum measured outside-engine load was 0.72 cores.

| Metric | ctrs median | OrbStack median | ctrs / OrbStack paired ratio and 95% CI |
| --- | ---: | ---: | --- |
| Start command to first exact read | 178.6 ms | 517.2 ms | 0.3421 [0.3007, 0.4148] |
| Recovered request p99 | 7.04 ms | 11.61 ms | 0.6078 [0.5962, 0.6156] |
| Measured engine CPU per successful response | 1,171 µs | 898 µs | 1.3017 [1.2930, 1.3364] |
| Sampled peak physical footprint | 2.46 GB | 5.99 GB | 0.4087 [0.4028, 0.4155] |

The database start command took a median 30.4 ms on ctrs and 213.0 ms on
OrbStack. The interval from command return to the first exact read was
151.8 ms and 301.6 ms, respectively. The measured per-response CPU loss
remains, and the counter omits host NAT CPU. The live application had
121–133 expected outage errors per ctrs trial and 138–149 per OrbStack
trial. The separate API interruption stops the published application
endpoint and produces a different failure load.

Repeat the API cohort reproduction with `--interrupt-service db` at the
same revision and with the same assets. Report run
`base-20261122T105526-a8d2` separately. Its `trials.jsonl` SHA-256 is
`dc8af48b2d10eaa7f54cbbb3f34c0c31e4b582ee3674657a87126ba430bd77f5`.

### Installed-default W10 queue recovery cohort

Run `base-20261122T110531-9992` admitted all ten alternating pairs at
`ca24add`. Both engines used a common v4 worker archive and the pinned
Redis image with AOF and `appendfsync always` in an owned volume. Four
workers verified 200 recovered backlog jobs and 200 fresh jobs per trial.
The raw before-and-after snapshots matched all 200 FIFO entries in every
trial, and each backlog output carried its original clock and enqueue
time. All twenty trials verified all 800 artifacts and owned teardown.
Both engines reported 9 vCPUs. Maximum measured outside-engine CPU was
1.33 cores, and ctrs recorded zero NAT connections in all ten trials.

| Metric | ctrs median | OrbStack median | ctrs / OrbStack paired ratio and 95% CI |
| --- | ---: | ---: | --- |
| Start command to exact backlog recovery | 174.2 ms | 387.7 ms | 0.4508 [0.4376, 0.4592] |
| Fresh batch queue p99 after recovery | 423 ms | 1,372 ms | 0.3192 [0.2780, 0.3356] |
| Measured engine CPU per verified job | 7.01 ms | 13.42 ms | 0.5210 [0.5128, 0.5527] |
| Sampled peak physical footprint | 2.26 GB | 5.35 GB | 0.4247 [0.4185, 0.4306] |

The CPU interval includes both verified worker batches. The fresh-batch tail
starts with enqueue preparation and ends after both artifacts close. Freeze
and whole-engine interruption on an isolated OrbStack remain open.

```sh
python3 bench/native/runner.py baseline --case W10 --a ctrs --b orbstack \
  --resource-lane installed-default --interrupt-service queue --concurrency 4 \
  --pairs 10 --pair-quiet-load 4 --max-pairs 16
python3 bench/native/reporting.py --match base-20261122T110531-9992
```

The common worker archive SHA-256 is
`de1778215fc772400d03eb365fbdde325a04a676d03a03fc04eeab700872fd1b`.
The `trials.jsonl` SHA-256 is
`d5df9d32bdd99631047d13c0517c4a432d74904bc14765984d62e58d5660b1ec`.
Main reuses the W4 image verifier for the queue input contract. The focused
integration suite passed 135 tests and the reports reproduced on the
integrated analyzer.

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

The next resource diagnostic uses duration mode with a separate
seven-minute work deadline for each engine. Set the drain and cleanup
deadlines three and six minutes after the work deadline. Use
`--resource-observation-seconds 32`, the same pinned v5 worker and
v6 portfolio, and the rebuilt signed Mac release. Keep ctrs at 9 vCPUs
and 8,192 MiB with a new `--ctrs-root`. Use the two explicit open
OrbStack backing files for its leg. Run the engines serially.

Inspect `resources.cycle_growth` in each W11 trial record. The first
complete observation establishes the baseline, and at least five more
must cover 30 seconds each. Read the footprint, descriptor and active disk
growth results alongside owned cleanup and exact-state checks. The
diagnostic will leave the 12-hour qualification and exclusive APFS
allocation open.

The 12-hour check now requires the API, DB and cache container IDs, guest
PIDs, start times and restart counters to match from setup through every
completed cycle, including its post-cleanup observation. A restart that
reuses the container ID fails the trial. Run the pinned short pilot with
`--cycles 1 --resource-observation-seconds 32` on both engines to verify
the new `initial_service_lifecycle` and per-cycle `service-lifecycle.json`
receipts before the long run. Freeze the candidate and resolve the
[host durability evidence](#w3-migration-and-committed-state-cohort) before
requesting qualification admission.

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

Use the same signed release, verified archive hashes and runner revision
`fa72716` for the three build layouts so each records the split install and
verification timings. The mixed layout leaves source on the bind mount and
puts dependencies and generated outputs on named volumes. The all-volume
control keeps the whole workspace in the guest. Each uses a cold dependency
directory and the existing offline package cache. Keep separate paired
cohorts and preserve the full workflow time, the two install intervals and
the exact output receipts for each layout.

For timing revision 2, the reporter admits a pair only when both legs
record the same source and dependency lock, image DiffIDs, tool versions,
phase cache states, installed file and byte counts, package count, initial
build output and discovered tests. Each engine verifies its own mount and
image identity during the trial.

```sh
for layout in full-bind bind-source-volume-deps all-volume; do
  python3 bench/native/runner.py baseline --case W12 --workspace-layout "$layout" \
    --a ctrs --b orbstack --resource-lane installed-default \
    --pairs 10 --pair-quiet-load 4 --max-pairs 16
done
```

The next W12-watch cohorts use `w12-watch-v4` for bind and
`w12-watch-volume-v2` for named volumes. Each verifies all 60 edit sequences,
their exact output paths, and the same guest watcher PID and process start
ticks across the edit phase. Use the signed Mac release and verified v2
fixture archives for both mount conditions.

The reporter verifies that each watcher kept its PID and start ticks, and
checks the edited paths and compiled output hashes of each result. The two
engines must agree on the fixture inputs and the ordered edit receipts.

```sh
for mount in bind volume; do
  python3 bench/native/runner.py baseline --case W12-watch --watch-mount "$mount" \
    --watch-edits 60 --a ctrs --b orbstack --resource-lane installed-default \
    --pairs 10 --pair-quiet-load 4 --max-pairs 16
done
```

### Independent Gitea holdout

`holdout-v3-exact-content` verifies the seeded repository and issue fields in
REST write and read responses. It checks the `main` branch and verifies the
README from each smart-HTTP clone against the pinned Gitea template after
the clone timer stops. A two-engine run fails on differing loaded image IDs,
Compose hashes or cloned README hashes. The image pins and holdout inputs
are ready for verification on the frozen candidate and OrbStack.
[Gitea 1.24.7 API](https://docs.gitea.com/api/1.24/)
[Pinned README template](https://raw.githubusercontent.com/go-gitea/gitea/v1.24.7/options/readme/Default)

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
3. Full-bind boundary: the completed
   [two-device probe](evidence/native-w12-w13-2026-11-18.md#two-virtiofs-devices-on-one-share-2026-11-20)
   rejected sharding a single mount. Rebaseline the v2 workspace with the
   install command and verification walk timed separately before selecting
   the next filesystem candidate.
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

## Linux HTTPie first use (amd64), 2026-11-22

[Evidence and replay](evidence/linux-httpie-2026-11-22.md): three predeclared
10-round baseline/candidate/frozen-Docker cohorts, 90/90 correct, resource-valid
and host-admitted. Native materialization before create dominates the deficit.
H1 streamed-install overlap and H2 zlib-rs alone were neutral under the strict
gate and reverted; the explicitly combined H3 qualifies: paired first-use C/B
**0.773 [0.707,0.786]**, medians **0.492 vs 0.649s**. Frozen Docker median
0.428s; C/D **1.164 [1.036,1.180]**, still slower. No build timing claim.
H3 uses the existing four-worker/FIFO install barrier and lock-pinned pure-Rust
gzip backend; it does not move work into preparation. First-use sampled CPU
medians B/C/D .554/.445/.248s; active anon+kernel peaks 33.23/24.16/797.93MiB,
with idle and retained state separately disclosed. No broad memory claim.

The five earlier ownership-invalid receipts remain invalid. Actual ordered
process/start-time/cgroup reads reproduce a short-lived runc ancestry gap,
including during the frozen 50,000-op W2 DB workload. A matching W13 diagnostic
did not reproduce it. Old samples lack the offending PID's instantaneous
reads, so individual attribution of all five remains unproven; strict ownership
was not weakened. Raw data/binaries live under
`~/ctrs-evidence/linux-httpie-20261122/` with a committed SHA-256 manifest.
This Linux optimization closes no macOS gate; their status is unchanged.

## Linux checkpoint and finite Mac handoff (amd64), 2026-11-22

[Current slice evidence](evidence/linux-checkpoint-2026-11-22.md) and
[manifest](evidence/linux-checkpoint-2026-11-22.sha256) preserve the CI audit,
W13 ceiling controls and incremental W1/W3 pilots. Native Linux x86_64,
Ubuntu 22.04.5, kernel `6.8.0-1060-aws`, cgroup v2; Docker 29.9.2
(`0367cbe`), containerd 2.4.2 and runc 1.5.2 remain frozen. Engine source
includes landed H3; no further product change was made in this slice.

### Recoverable baseline and current compatibility

- Historical baseline: `~/ctrs-evidence/linux-amd64-v1/` contains
  `baseline.tar`, frozen `images.tar`, source bundle, binary identities,
  commands, all raw records/traces and the historical analysis. Verify with
  `docs/evidence/linux-amd64-v1.sha256`; extract and verify
  `baseline-members.sha256` before using it. Unknown SHAs and invalid receipts
  stay unchanged. [Retrieval instructions](evidence/linux-amd64-checkpoint-2026-11-22.md)
  include source recovery without the original worktree.
- **Use the corrected independent restoration**, not the historical incomplete
  isolation attempt: [integrated runtime evidence](evidence/linux-integrated-runtime-2026-11-22.md),
  `~/ctrs-evidence/linux-integrated-20261122/restore-owned.sh` and its log.
  Launch owned Docker in a private netns with private containerd address/root/
  state, private Docker socket/data/exec roots and unique bridge or bridge none;
  never attach a disposable daemon to default host sockets. Inside its private
  mount namespace bind only its socket to the harness endpoint and run:
  `python3 bench/native/runner.py --lane linux-amd64 prepare --linux-archive ~/ctrs-evidence/linux-amd64-v1/images.tar`.
  Preserve the committed lock. Recorded proof: `INDEPENDENT_OWNED_RESTORE_EXIT=0`
  and `FROZEN_LOCK_UNCHANGED`. This was an independent image-store restore,
  not an entirely empty Docker build-cache or off-host disaster-recovery test.
  This slice additionally loaded that archive into a fresh owned H3 ctrs store
  and verified all twenty W1/W3 trials, without modifying Docker's portfolio.
- Integrated compatibility remains **ctrs 482 pass / 1 fail / 26 skip**;
  isolated Docker **471 / 2 / 30**. Both exit 1: missing host VRF module
  affects both; Docker's SYS_ADMIN mount is denied by its default AppArmor
  profile (unconfined control passes). Earlier Docker cp ownership differs
  for UID-1000 sources; root-owned current sources pass. All 74 historical
  printed ctrs FAIL labels were reconciled, with the historical 73-summary
  discrepancy retained. No new full-e2e rerun is claimed here.
- During-operation IPv4 proof retained the preexisting non-ctrs DROP while
  allowing ctrs networking, proved denial removal as a positive control, denied
  unsolicited non-ctrs→ctrs traffic, then restored rules exactly on stop.
  Independent IPv6 packet-policy proof remains unperformed. The earlier host
  docker0 repair needed no dockerd restart; its disappearance's cause remains
  unconfirmed. Logs/manifests preserve the incident rather than hiding it.

### Profile → decisions → measured improvement

- **W2:** 50,000 operations/concurrency 8, two AB/BA observer pairs per mode.
  Periodic C/D completion/p99 1.026/.997 versus boundary 1.119/1.215 does not
  establish ownership-discovery bias. Six real-path controls show app/database
  CPU dominates; relay bypass removes daemon work but not a consistent deficit.
  Storage-wait attribution is limited by disabled task delay accounting. Native
  seccomp-dispatch H1 and relay H2 failed the declared p99 upper-bound gate
  (1.535 and 1.034 versus ≤.95); both reverted. 60/60 correct/admitted,
  58/60 resource-valid, all 20 B/C pairs valid. [Evidence](evidence/linux-w2-2026-11-22.md)
  and `~/ctrs-evidence/linux-w2-20261122/` retain patches and traces.
- **HTTPie H3:** materialization before create is the dominant native deficit.
  Separate overlap-only and zlib-rs-only attempts failed the strict gate; the
  predeclared combined candidate wins against baseline: C/B **.773
  [.707,.786]**, medians .492/.649s. Docker .428s; C/D **1.164
  [1.036,1.180]**, still slower. All 90 trials correct/resource-valid/admitted;
  no build/load timing claim. Sampled CPU B/C/D .554/.445/.248s; active
  anon+kernel peaks 33.23/24.16/797.93MiB, with idle 1.46/1.46/778.40MiB
  and retained increments 6.36/6.34/2.43MiB. Host/agent sizes rise .23%/.60%;
  no broad memory or build-time claim. Correctness: host tests 155 passed,
  2 ignored; layer tests 13 passed; create/run/rootfs e2e subset 135 passed,
  17 skipped. [Evidence](evidence/linux-httpie-2026-11-22.md) preserves traced
  nested phase bounds and profiler corrections, not falsely exclusive timings.
- **Ownership:** strict rejection remains. Five old invalid receipts are
  unchanged. Live PID/start-tick/cgroup transitions reproduce short-lived runc
  ancestry gaps, including correct W2 work; a matching W13 diagnostic did not.
  Old failing-instant offending-PID reads are unavailable, so all five individual
  causes are not proven. Structural BuildKit naming and its collision limitation
  remain documented. Retired counters are retained; CPU is machine-marked
  incomplete/sampled-lower-bound, not promoted to complete accounting.

### New coverage and W13 stopping decision

W13's unchanged, byte-verifying host-loopback tool, CPUs 0–7, five admitted
1-GiB one-stream uploads: median **3.352 GB/s [2.556,3.405]**, range
2.470–3.451. Historical engine maximum 2.633 GB/s; required 2× control
headroom is 5.267 GB/s. The necessary host-only gate fails; container-side
headroom is also unproven. **No W13 engine rerun or cohort.** No threshold
relaxation or receiver rewrite. W13 remains tool-limited/inconclusive.

Existing W1 verified DB/cache recovery and W3 synchronous-transaction volume
work now run in the Linux lane, selecting the unchanged frozen native images.
Five alternating AB/BA pairs each (the contract's three-pair pilot floor is
exceeded), **20/20 correct/admitted/resource-valid**, no replacements:

| Primary metric | ctrs median [Q1,Q3], s | Docker median [Q1,Q3], s | Paired C/D [95% CI] |
| --- | ---: | ---: | ---: |
| W1 restart→exact reads/new acknowledged write | .578 [.576,.578] | .742 [.738,.742] | .776 [.768,.802] |
| W3 300 synchronous transactions, full exec | .0765 [.0764,.0785] | .1569 [.1525,.1580] | .484 [.454,.506] |

W1 total-work ratio .974 [.841,1.301] is inconclusive, including the retained
lazy-agent/first-materialization trial (not uniformly warm agent/cache state).
W3 COMMIT p95 ratio .843 [.741,.866], restart-ready
1.021 [.568,1.114]. These short SQL/CLI and application-restart pilots establish
coverage, not disk throughput, engine restart or power-loss recovery. Window
CPU medians C/D: W1 1.533/2.469s, W3 .159/.398s, sampled lower bounds.
Observed window anon+kernel peak increments: W1 62.33/80.59MiB, W3
9.58/20.25MiB; retained .51/2.22 and .29/−.44MiB. Windows differ from the
primary operations; sub-200ms memory peaks may be missed. Idle/peak/retained
values and negative deltas remain separate in the linked evidence, not a broad
memory-efficiency claim. Raw data and exact current binaries are under
`~/ctrs-evidence/linux-checkpoint-20261122/`.

Requested-head CI audit: five checked heads (`d75f876`, `75491e7`, `cd9800e`,
`2910f31`, `65b7bbd`) each **5 passed / 0 failed / 0 pending**. Intermediate
`c5b8f0d`, `11e4967`, `215b8db` return no checks, not green results; their
checked descendants cover unchanged runtime/Cargo/e2e inputs. Nothing red
required a fix-forward. Exact refs are in the preserved audit receipt.

### Next exact Linux experiment (not started)

Extend only the existing **W3-v4** native database selection, then predeclare
ten alternating pairs: scale 50, shared_buffers=128MB, clients 8, threads 2,
2,000 transactions/client (16,000 total), random seed 42, CPUs 0–7. Verify
native pgbench availability before scheduling; if absent, stop for an explicitly
frozen common fixture, not a download during timing. Show equal fsync,
synchronous_commit, full_page_writes and mount/flush contracts before any
storage claim; retain complete transaction receipts and exact state after
restart. Primary transaction completion, companion p95/CPU/storage/recovery,
same immutable-input/ownership/admission rules. This tests a longer existing
workflow; it does not assume the short W3 exec ratio scales.

### W3-v4 Linux follow-up, 2026-11-22

The named next experiment is now complete. [Native pgbench evidence](evidence/linux-w3v4-2026-11-22.md)
preserves ten alternating AB/BA pairs, native-tool hashes, actual successful
WAL fdatasync traces, matching host ext4 data-mount/flush contracts, complete
transaction logs, profiles and analysis. Scale 50, 8 clients, 2 threads,
2,000 transactions/client/phase and seed 42 remain unchanged. Both engines
use native PostgreSQL/pgbench 17.12 and CPUs 0–7. All 20 trials are correct,
host-admitted and resource-valid, with no replacements.

The primary RW p99 is **inconclusive**: paired C/D **1.040 [.830,1.958]**;
medians 1.894 versus 1.818 ms. RW throughput **loses**, C/D
**.902 [.797,.999]**, 8267 versus 9181 TPS. RO p99/TPS ratios are
.965 [.910,1.061] / 1.003 [.942,1.051]. Restart-ready remains slower,
1.100 [1.025,1.142], .264 versus .240 seconds. No disk-throughput or
physical power-loss claim follows from this page-cache-fitting pilot.

The separate full-input profiles reverse the throughput ordering and show
substantial overlapping PostgreSQL WAL-sync work. An extra-CHECKPOINT
counter-control also changes full-page-image/WAL volume and cannot serve as
a pure phase subtraction. Neither a background-checkpoint explanation nor a
ctrs-engine-specific cause is established. No unsupported engine candidate is
invented; the original deficits remain visible, not declared parity.

Full-window sampled CPU medians are 13.565/13.830 seconds, still explicitly
incomplete. Idle anon+kernel is 53.96/738.60 MiB; observed peaks are
173.22/859.15 MiB; peak-minus-idle 119.30/120.31 MiB; retained-minus-idle
.14/.69 MiB. These are not isolated transaction peaks or broad efficiency
claims. The first initialization and negative retained deltas are retained.
The queue next proceeded to residual HTTPie materialization/create profiling,
then the complete W1–W13 Linux admissibility survey. Mac gates stay open.

### HTTPie residual follow-up, 2026-11-22

[Evidence and replay](evidence/linux-httpie-residual-2026-11-22.md): the
remaining pre-create boundary reproduces at .260–.267s versus Docker
.040–.042s. Actual install workers repeatedly canonicalize tar paths, and
independent perf also finds gzip inflate work. Three bounded hypotheses
tested worker-local extraction paths, bounded decoded buffering, and their
explicit combination. Each had ten predeclared alternating three-way rounds,
current H3 / candidate / frozen Docker, CPUs 0–7.

All **90/90 correct and host-admitted; 89/90 resource-valid**. R1 paired C/B
first-use ratio **.985 [.938,1.183]**, R2 **.979 [.744,1.041]**, combined R3
**.937 [.875,1.019]**. None meets the declared upper ≤.95 latency gate; R1
and R3 also exceed the sampled active-footprint guard. R3 medians are
baseline .503s, candidate .457s, Docker .438s, not a qualified win. One R1
Docker resource failure stays invalid. All edits were reverted; H3 remains
unchanged. Three-attempt bound exhausted; no fourth hypothesis or pooled win.
Root-run ctrs-init suites passed 92/92/93 tests respectively; each unchanged
create/run/rootfs subset passed 135, failed 0, skipped 17 Mac bind cases.
CPU remains incomplete; active anon+kernel is sampled, not memory.current.
Ctrs stopped, host Docker lifecycle unchanged. Raw data and all binaries/
patches are at `/home/ubuntu/ctrs-evidence/linux-httpie-residual-20261122/`.
Next: every W1–W13 Linux admissibility cell and remaining sanctioned W13
headroom configurations. No macOS gate closes.

### Finite Mac handoff; no gate closes from Linux

Linux containers share the **host kernel**; macOS ctrs has a **VM boundary**.
Neither equal isolation nor identical resource baselines is implied. All full
macOS coverage, parity, leadership, reliability and reproducibility gates remain
**open**; the active Mac coordinator owns its existing campaign independently.

1. At one recorded main SHA, rebuild **combined kernel/agent/watch assets and
   host binary** (`cargo xtask all`); record all asset/config hashes. Run the
   existing workspace tests, kernel-feature and create/run/rootfs/network e2e
   checks against that combined build, including gzip concatenation/truncation
   and cleanup/error paths. Do not combine receipts from separate builds.
2. On that build run existing **W5 and W12-watch**, both bind and volume, at
   their declared edit counts with exact event/output and watcher-identity
   checks; report tails and resources. These are the combined kernel/watch
   checks still requiring real native ARM64 macOS, not Linux substitutes.
3. Measure **H3/new-default HTTPie first use** versus frozen OrbStack with ten
   alternating pairs, identical frozen native ARM64 image bytes, explicit CPU/
   resource policy, build/load excluded, and create/run/rootfs correctness.
   H3's streamed-host branch is Linux-gated; the gzip backend also affects the
   Mac guest and needs its own measured comparison. Do not import Linux pins
   or infer a Mac speedup from the .773 ratio.
4. Freeze the outstanding cells of the existing acceptance matrix at that SHA
   and complete their **new-default** comparisons (minimum ten alternating
   pairs; W11's existing 12h/engine reliability contract). Keep installed-default,
   resource-matched and identical-builder controls separate, prove W13 tool
   headroom on that host first, and report every unresolved correctness,
   durability, resource or tail cell. No new workload/framework is handed off.

Linux work does not wait for this list and cannot satisfy it by proxy.
