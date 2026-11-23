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

#### Combined release results

On 2026-11-22 the confirmation checkout `2b603fc` and release source
`99db1aa` had identical Cargo inputs, crates, guest sources and xtask code.
The ad-hoc signature and virtualization entitlement passed. SHA-256 checks
agreed before and after the native suite.

| Artifact | SHA-256 |
| --- | --- |
| Signed ctrs | `10667e6d929207167f1812e5fd41c7ad6474f12bc9d5a42788af5ae027c93d17` |
| Guest kernel | `19657ca4cc150ae8d04d003ac494676bcc5845dd3a3a21cd6bfb17df605d4e6f` |
| Guest initramfs | `fb0f832b79eca9463d3aafb0bebdff8a5e620e2ff1779c896727fc91d3e32c87` |

| Check | Result | Log SHA-256 |
| --- | --- | --- |
| `make test` | 270 Rust and 504 Python tests passed | `ebed0024a14794bd583ce2dbf6777406e3267668414f41db3e2b84fe0a276ea6` |
| `conformance/smoke.sh` | 21 passed | `e28bb91f2f50c9356bd335b638366aeca5f4d0c70ef62783e147428efd4ababb` |
| `tests/watch-recovery.sh` | 12 checks passed, including host loss, guest overflow, one-shot re-add and the capacity case | `845b91f8541003320303eb7d65bf6864966d96ec220767ef01cd9f8b91aa9f7e` |
| `tests/fuse-inode-bound.sh` | Read all 150,000 files and 64 held-open files. VZ helper descriptors peaked at 65,510 against a 73,728 limit and recovered to 58. | `d6241dd53406e726da5b453a4f2977806f3e8f25d51afb9468893666219fc86a` |
| ARM64 guest layer tests | 13 passed, including concatenated gzip members and truncated gzip rollback | `31229da7b26c1b1d7c4e77bc2aa574fea7cffa0f463fa725d5ce4c38911918f4` |
| `tests/e2e.sh` | 509 passed, zero failed or skipped | `f3e5cb8ef49950aaea337e0cc696653b5eef089ccd96e0343d343c80de104008` |

The workspace and guest test builds used `RUSTC_WRAPPER=""` and
`CARGO_ENCODED_RUSTFLAGS=""`. Capture stdout separately when parsing the
guest test build's `--message-format=json` artifact path. The standalone
failure and isolation suites have their own queue entries.

#### Earlier asset preparation

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
The ctrs admission `run-20261122T154102-607b` used harness `2e5fb82` and
signed release `99db1aa`. Its fresh private store preserved all three
image pins. The socket answered in 44 ms and the first exact roundtrip
completed 5.244 s from daemon launch. The database restart, persisted
state, post-restart read/write and owned cleanup checks passed.
This was one trial. It used nine host NAT connections, so the engine
counters omit their host kernel CPU. Equivalent engine-cold measurements
on an isolated OrbStack target remain open.

`trials.jsonl` SHA-256
`b90d4a60590192d48b04c68eef3c62b33a7871745f2bd5227cc49c188016090b`.

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
were pending at admission.

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

`base-20261122T130640-24d2` ran ten alternating pairs from harness
`0d75114` with signed release `99db1aa`. All 20 legs passed, with 6,000
committed rows verified after PostgreSQL restart. The manifest and SQL
pins matched, `synchronous_commit` was enabled for the timed workload,
and the resulting row receipt confirmed `fsync=on` in every leg. The
reporter used host-load admission, with a maximum endpoint one-minute
load of 3.12 on 10 host CPUs. Outside CPU was recorded in 16 transaction
phases and reached 1.26 cores in those phases.

| Metric | Normalized paired median | 95% CI |
| --- | ---: | ---: |
| Verified transaction throughput (OrbStack / ctrs) | 0.0904 | 0.0893–0.1095 |
| Commit p95 (ctrs / OrbStack) | 0.0691 | 0.0605–0.0820 |
| Migration time | 0.3404 | 0.3097–0.3548 |
| Checkpoint time | 0.1359 | 0.1267–0.1939 |
| Restart time | 1.0726 | 0.8469–1.3336 |
| Engine CPU per verified transaction | 0.1448 | 0.1353–0.1684 |
| PGDATA allocated bytes | 1.0029 | 1.0029–1.0029 |
| Sampled physical footprint | 0.1453 | 0.1366–0.1498 |

Median trial commit p95 was 0.192 ms on ctrs and 2.817 ms on OrbStack.
Restart time was inconclusive. The other listed ratios are
`durability-unverified`. Raw trials SHA-256
`0a3e43eb632babfaf02a9cd3660a3ca48d42056117a9a1594de397d464afc864`.

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

The ctrs-only diagnostic measures the stronger Full attachment with
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

#### W3-v4 group commit on Fsync and Full

All three ctrs-only pairs in `w3v4-sync-z4EWsp` completed on harness
`dd74021`. The signed builds used release `99db1aa` for Fsync and the
one-mode patch `8a233fe` for Full. Each leg used native PostgreSQL 17.12
from the same v6 portfolio, 5 million accounts at scale 50, 128 MiB
shared buffers, eight clients and two pgbench threads. All six legs
verified 16,000 committed transactions and the matching account balance
after an orderly restart. PostgreSQL durability settings matched before
and after restart. The raw WAL counter deltas matched every recorded
measurement, with zero ctrs host NAT connections and no host rejections.

| Pair | Fsync WAL syncs | Full WAL syncs | Fsync mean WAL sync (ms) | Full mean WAL sync (ms) | Fsync write tx/s | Full write tx/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 8,413 | 4,345 | 0.1613 | 6.3876 | 9,475 | 559 |
| 2 | 8,508 | 4,363 | 0.1568 | 6.1625 | 9,647 | 576 |
| 3 | 8,498 | 4,352 | 0.1639 | 6.1501 | 9,404 | 580 |

The paired median Full/Fsync ratio was 39.30 for mean WAL sync time,
20.16 for time spent in all WAL syncs and 0.0598 for write throughput.
Per-trial write p95 ranged from 0.970 to 1.020 ms under Fsync and
23.658 to 26.800 ms under Full. The Full legs issued about half as many
syncs, consistent with group commit absorbing some of the cost. The
remaining gap is concentrated in the WAL sync interval. These three
pairs measure the cost of different Apple disk synchronization contracts.
Full remains experimental. OrbStack's host commit guarantee remains
unverified. [Apple Full](https://developer.apple.com/documentation/virtualization/vzdiskimagesynchronizationmode/full.md)
[Apple Fsync](https://developer.apple.com/documentation/virtualization/vzdiskimagesynchronizationmode/fsync.md)

Signed Fsync SHA-256
`10667e6d929207167f1812e5fd41c7ad6474f12bc9d5a42788af5ae027c93d17`.
Signed Full SHA-256
`cf0b4e9ad1c22672e563798a3bc1397ff4490ffcef0a24cd22fa67fb6b20659c`.
Derived comparison SHA-256
`a88778def312d9753f77ae692de88727ad20c91c54eb8d7dfa1f3a16876d0c69`.

| Run suffix | Raw trials SHA-256 |
| --- | --- |
| `1-fsync` | `f96f16ab0f538d4ecee83e850c4a0da682cd3d0d90c115f5c27c4e91a998b468` |
| `1-full` | `6aa194cfe21f45841c95a9da661759400b8bb4494f9568548b92e98a80380f8b` |
| `2-fsync` | `c1da4f4fe97f1f13bca6b049d50a0762dd37974632c17bf9fee07dd8687d47c9` |
| `2-full` | `ae608beda1652627ec8b6552c33b0b630ca092bac598f6e33f066ad8de9e6076` |
| `3-fsync` | `623545bd6bc9d2b14d01405252be92bd6e7cf2b682640511173cfafc067eac62` |
| `3-full` | `eeae468b483b4c3b63d26c7519bb167afc6f463a995069b792988a42520757b8` |

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

#### Installed-default W4 cohort

Admission `base-20261122T143601-2aea` and cohort
`base-20261122T143625-9f92` used clean harness `9284033` and the signed
`99db1aa` release. The shared ARM64 worker archive SHA-256 was
`de1778215fc772400d03eb365fbdde325a04a676d03a03fc04eeab700872fd1b`.
Both engines used 9 vCPUs and their installed memory defaults, 8.41 GB on
ctrs and 63.16 GB on OrbStack. Every pair matched the worker and Redis
layer and launch-configuration receipts. In ten alternating pairs, every
leg verified 200 jobs and 400 output artifacts per worker condition. The
cohort covered 12,000 jobs and 24,000 artifacts with no failures or
rejections. No ctrs leg recorded host NAT connections. The maximum measured
outside-engine load during a worker phase was 0.98 cores.

| Metric | 1 worker | 4 workers | 16 workers |
| --- | ---: | ---: | ---: |
| Worker phase time | 0.6251 [0.6088, 0.6300] | 0.4524 [0.4480, 0.4608] | 0.2786 [0.2670, 0.2860] |
| Queue p95 | 0.6721 [0.6598, 0.6836] | 0.5479 [0.5324, 0.5565] | 0.2874 [0.2713, 0.3175] |
| Queue p99 | 0.6718 [0.6600, 0.6840] | 0.5521 [0.5358, 0.5597] | 0.2888 [0.2729, 0.3180] |
| Engine CPU per verified job | 0.7028 [0.6755, 0.7181] | 0.6688 [0.6581, 0.6730] | 0.6119 [0.5970, 0.6181] |
| Sampled peak physical footprint during workers | 0.1454 [0.1416, 0.1472] | 0.1437 [0.1405, 0.1454] | 0.1405 [0.1380, 0.1413] |

Ratios are paired medians of ctrs / OrbStack with 95% CIs. All reported
intervals cleared the descriptive strict-win threshold. The worker phase
includes worker container starts and completion. Median worker-phase time
at 16 workers was 0.729 s on ctrs and 2.632 s on OrbStack. The results
cover the finite queue fixture with a fresh batch at each concurrency.

```sh
python3 bench/native/reporting.py --match base-20261122T143625-9f92
```

`trials.jsonl` SHA-256
`5e8c8f8308ab99e585d114fa3346b50dfb799d0921fcf5246a707d8326b9b98a`.

### Installed-default W5 cohort

`base-20261122T123236-7047` used harness `a6de621` and signed release
`99db1aa`. All 10 alternating pairs passed with 60 edits per mount and leg,
for 2,400 exact Marked CLI results. Every leg verified the mounted source,
tool image and dependency lock, retained the same watcher, and removed its
owned resources. Both engines reported 9 vCPUs. Guest memory was 8.41 GB for
ctrs and 63.16 GB for OrbStack. The reporter admitted all pairs by its
host-load fallback, with a maximum endpoint one-minute load of 2.24 on 10
host CPUs. The W5 receipts lacked a combined outside-CPU measure.

Ratios are paired ctrs/OrbStack medians with 95% bootstrap intervals.

| Metric | Bind | Named volume |
| --- | --- | --- |
| Edit-to-result p50 | 0.9698 [0.9656, 0.9721], non-inferior | 0.9719 [0.9691, 0.9757], non-inferior |
| Edit-to-result p95 | 0.9488 [0.9376, 0.9539], non-inferior | 0.9852 [0.9814, 0.9913], non-inferior |
| Watcher setup | 0.4932 [0.4826, 0.5015], strict win | 0.2770 [0.2737, 0.2798], strict win |
| Engine CPU per edit | 0.9614 [0.9535, 0.9843], non-inferior | 0.8606 [0.8517, 0.8664], strict win |
| Sampled physical footprint | 0.1919 [0.1832, 0.1951], strict win | 0.1937 [0.1845, 0.1980], strict win |

Median trial p95 was 155.6 ms versus 164.1 ms on bind and 149.3 ms versus
151.7 ms on volume. The timer ends when the host receives verified CLI
output. The edit command occupied less than 1% of median bind latency on
either engine and 21% on ctrs versus 49% on OrbStack for volume. The
remaining interval includes watch detection, rebuild, CLI execution, and
delivery of the verified result. Their individual costs were not measured.

Build the pinned image once and load the same archive on both engines using
`watch_loop.prepare_shared_image`. The exported archive SHA-256 was
`e55ae7dec6d034b93c0bf88d6e22d1980f289ac200b4aa2557872e35105980af`.
Run the installed-default cohort with the signed release and pinned guest.

```sh
python3 bench/native/runner.py baseline --case W5 --watch-edits 60 \
  --a ctrs --b orbstack --resource-lane installed-default \
  --pairs 10 --pair-quiet-load 4 --max-pairs 16
```

Raw trials SHA-256
`ddee9ccc1dc87d0b8dd4592e078198521db754449258035f2fed56aeb575efe3`.
Frozen confirmation remains open.

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

#### W6 balloon reclaim diagnostic

The ceiling screens bound peak footprint and leave the retention mechanism
unresolved. Test whether the balloon grace period accounts for retained
footprint after an uncached build. Use the signed `99db1aa` release and its
pinned guest assets, the existing private W6 store, and 9 vCPUs at an 8,192
MiB ceiling. Disable auto-sleep in both legs with `CTRS_IDLE_SECS=0` so the
VM helper stays resident. Restart only the campaign daemon between legs.
Run the 120-second grace first and zero-second grace second using
`CTRS_BALLOON_QUIET_SECS`.

Run the pinned uncached W6 Rust and zlib builds in each leg. Check both
compile receipts and artifact hashes. Read `/proc/meminfo` in a short
network-disabled container from the local W6 GCC image before and after
a 150-second quiet interval. Record available, cache, reclaimable slab,
anonymous and balloon pages. During the interval, sample the identified
VM helper's physical footprint and the daemon's target, used, stall and
OOM fields every five seconds. Send `X-Ctrs-Background: 1` with `GET /info`
so the observations preserve daemon quiet time. Repeat the two uncached
builds at the end and verify the same artifacts. The diagnostic tests
whether the target and footprint move together while guest cache and
balloon pages change. Its fixed order and reused build store limit timing
inference. A timing claim requires a separate paired confirmation.

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

The current Mac build comparison also verifies runtime contents. After the
timed work and sampling finish, it hashes each loaded Hyperfine executable
and records the versions and file-content hashes of the installed HTTPie
runtime distributions. It compares these receipts across uncached, warm and
incremental builds within each trial and across both engines in each pair.
The reporter also requires one runtime receipt across all pairs in an
exact-runtime cohort. Generated Python bytecode and wheel installation
metadata are outside the runtime file
receipt. This check can catch runtime drift. A frozen comparison also needs
reproducible build-time dependencies. Keep the earlier W7 results separate
and admit one native pair before the new ten-pair cohort.

Admission `base-20261122T170630-266b` passed on harness `5710ea2` with
signed release `99db1aa`. Both engines passed all 25 checks across the
six builds. Each produced the same Hyperfine executable hash
`fcfbf31a7d309a79dba362d75310ead3eafc35d984248a197f5cfbd2dce09c3f`
and the same content and version receipts for 16 installed HTTPie
distributions in all three cache states. Both runtime receipt files
had SHA-256
`2ec1c509dd9bca6ff469a88553e74950256160df8e3fb739eba4f803ea07e3f2`.
The admission `trials.jsonl` SHA-256 was
`34d10d2334ad9c72d43368574c4e64c9276afd25d2bff024931a4c86a9697aac`.
The ten-pair installed-default run started as
`base-20261122T170828-8009`. Use the pinned harness and release with the
W7 command above to reproduce it.

#### W7 installed-default cohort with exact runtime receipts

All ten pairs in `base-20261122T170828-8009` passed. The 20 runtime
receipt files shared the admission file's SHA-256. Together, the engines
completed 120 builds and 120 first-use probes, with all 500 correctness
and cache checks passing. Both guests used nine vCPUs. The installed memory
budgets were 8,407,957,504 bytes on ctrs and 63,157,620,736 on OrbStack.

All twelve timing cells cleared the descriptive strict-win threshold.
The table gives paired median ctrs / OrbStack ratios with 95% confidence
intervals.

| Application and state | Build and load | First use |
| --- | ---: | ---: |
| Hyperfine uncached | 0.8769 [0.8592, 0.9067] | 0.0819 [0.0727, 0.0928] |
| Hyperfine warm | 0.4713 [0.4231, 0.4929] | 0.0471 [0.0455, 0.0480] |
| Hyperfine incremental | 0.3204 [0.3141, 0.4382] | 0.0565 [0.0542, 0.0725] |
| HTTPie uncached | 0.8334 [0.8244, 0.8664] | 0.4948 [0.4704, 0.5228] |
| HTTPie warm | 0.5811 [0.5163, 0.6048] | 0.2443 [0.2316, 0.2480] |
| HTTPie incremental | 0.3679 [0.3504, 0.3825] | 0.2475 [0.2343, 0.2558] |

Median uncached build and load was 15.487 s versus 17.640 s for
Hyperfine, and 6.893 s versus 8.306 s for HTTPie. Build time spans
the default builder command through image load. First use times the
version probe in the loaded image. The runtime file audits run after
timing and sampling.

Sampled peak physical footprint was 0.6120 [0.5399, 0.6296].
Measured CPU was 0.6065 [0.6044, 0.6082] with 130–133 ctrs host NAT
connections per leg and incomplete accounting. The highest available
outside-engine CPU estimate in any phase was 1.61 cores. For trials with
missing host tick estimates in short phases, the reporter used the
one-minute host load fallback. Build-time dependency freezing remains
in the separate offline comparison.

Raw `trials.jsonl` SHA-256
`ece016b66e965bc3f560063eaa2d24e7ee04b8c51c4cbef97fe77ddb6f51dcc4`.

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
`cargo build --release --locked`. Both engines passed the single admission
pair `base-20261122T172144-cf67` on harness `535cccf`. The two native runtime
receipt files shared SHA-256
`c7bfedd667c46386bb9336fb96d09004e636f6440b1668caa0ba203950ef6b66`.
Against revision 3, the Hyperfine executable hash matched. The HTTPie
receipt recorded pip 26.3 in place of 26.2.2 and changed file hashes
for five other distributions at the same versions. Revision 3 remains the
network-resolved comparison and the Linux amd64 workload.

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
[Cargo vendor command](https://doc.rust-lang.org/cargo/commands/cargo-vendor.html)

`w7-v5-offline-builds` uses this archive in the Hyperfine context and compiles
with `cargo build --release --frozen`. Both build commands use
`--network=none`. Base image pulls remain part of untimed preparation.
The runner records the Cargo vendor and wheel lock digests and verifies
both apps across the three cache states.

#### W7 offline build cohort

Admission `base-20261122T172318-a5f4` and all ten installed-default
pairs in `base-20261122T172448-ffd0` passed on harness `e8b6e4e` with
signed release `99db1aa`. All 20 cohort legs used the pinned archives
above and passed all 25 correctness and cache checks. All runtime
receipts, including admission, shared SHA-256
`0c7da05f53ededa3eafc9e993ce5e5434ad59b08a92668f5479e55d56057c587`.
HTTPie reproduced the revision 4 distribution receipts. The vendored
Hyperfine build produced executable SHA-256
`50106869518edd39f5a0c6efed87b848a6f8b523134dc2cc414db901417d6cec`
in all cache states on both engines. The changed build contexts and
runtime receipts define a separate comparison from revision 3.

| Application and state | Build and load | First use |
| --- | ---: | ---: |
| Hyperfine uncached | 0.8834 [0.8666, 0.8966] | 0.0834 [0.0759, 0.0856] |
| Hyperfine warm | 0.4193 [0.3073, 0.4788] | 0.0457 [0.0436, 0.0471] |
| Hyperfine incremental | 0.3230 [0.3111, 0.3340] | 0.0557 [0.0519, 0.0568] |
| HTTPie uncached | 0.7933 [0.7792, 0.8037] | 0.4863 [0.4736, 0.5129] |
| HTTPie warm | 0.5176 [0.4453, 0.5555] | 0.2350 [0.2319, 0.2381] |
| HTTPie incremental | 0.3902 [0.3714, 0.4075] | 0.2480 [0.2374, 0.2538] |

The entries are paired median ctrs / OrbStack ratios with 95% confidence
intervals. Median uncached build and load was 16.011 s on ctrs and
18.249 s on OrbStack for Hyperfine, and 6.133 s and 7.752 s for HTTPie.
Sampled peak physical footprint was 0.5986 [0.5633, 0.6125]. Measured CPU
was 0.6112 [0.6094, 0.6174]. ctrs still recorded 130 or 133 host NAT
connections per leg with build-step networking disabled, leaving CPU
accounting incomplete. Use the pinned harness and release with
`python3 bench/native/pyramid.py run --name w7-buildx:cohort` to reproduce.

| Run | Raw trials SHA-256 |
| --- | --- |
| Revision 4 admission | `8e19caaed7e1b992eee7f7c5e7f4ffc5def0181d0bc315a12cb256c87c3b1ce0` |
| Revision 5 admission | `e0d8932086d05570b0b15b58247ee8deb6715a202f679b3b2313984b2dfdc9ff` |
| Revision 5 cohort | `dd2af3cc24e1effb74ec517ee1a803dbeccef0b969eb2739bf3fb783508745b6` |

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

#### W2 API cgroup CPU split

Both fixed-work cohorts saved API cgroup `cpu.stat` at the workload
boundaries. For each admitted pair, subtract the before snapshot from
the after snapshot, then subtract OrbStack's delta from ctrs's delta.
The user and system fields reconcile to total CPU usage in all 40
legs within 2 microseconds. Each leg verified 50,000 requests.

| Paired CPU difference | Published port, median [range] | Guest-direct, median [range] |
| --- | ---: | ---: |
| Measured engine CPU | +9.74 s [8.92, 10.58] | +4.51 s [4.11, 5.58] |
| API cgroup total | +5.64 s [5.30, 5.83] | +4.13 s [3.65, 4.57] |
| API cgroup user | +1.49 s [1.27, 2.19] | +1.00 s [0.64, 1.50] |
| API cgroup system | +4.09 s [3.48, 4.38] | +3.14 s [2.84, 3.53] |

The API system CPU delta exceeded the user CPU delta in every pair,
including the guest-direct path with zero host NAT connections. The
cgroup interval includes the counter-reader exec and uses separate
boundaries from the host process interval. Use the guest-direct observer
confirmation before attributing system CPU to specific kernel functions.

The derived `pairs.jsonl` SHA-256 is
`043c3e8d4cf5095cd3d5c6844a42bad9eb9d23e43e86ee893b35c8a50e94bc91`.

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
valid 49 Hz blocks use the older admission policy and stay separate.

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

#### 25 Hz leaf observer admission

`w2-guest-client-cpu-leaf-25-20261122T124015-f6df` used candidate
`3d0a124` on `campaign/w2-leaf-25`, the same pinned service images, and
the 40 ms CPU-clock period. Each of four legs verified 35,140 reads and
14,860 writes, with zero errors and clean teardown. Both profiled legs
passed raw event validation across all nine threads. ctrs recorded 558
samples with a minimum of 17 per thread. OrbStack recorded 450 samples
with a minimum of 11 per thread.

Both gate calls exited zero for all four legs. Outside-engine CPU was
0.205 cores off and 0.240 on for ctrs, and 0.847 off and 0.803 on for
OrbStack. The candidate reporter admitted the block. The 5% CPU and wall
overhead checks require a fresh ten-block cohort and process review.

Use the guest-direct command above with `--profile-kind cpu-leaf-25`.
Alternate engine and mode order over ten blocks, starting with the default
orders. Use the reporter from the candidate branch on those ten blocks
in run order. Admission `plan.json` SHA-256
`9a43c8eaf4b8802c2a3d5ddf020c0694901145bdab9b0ec62e6dadc9217fed3e`.

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

#### W13 Mac loopback headroom

On 2026-11-22, `bench/native/diagnostics/w13_host_headroom.py` at
`7f07f18` completed five byte-exact 1 GiB trials per direction and stream
count without either engine. Four streams split the same 1 GiB. The
launcher counted distinct stream-receipt arrays as separate conditions.
Grouping by each array's length verifies exactly five trials in each
condition. All 20 trials passed their byte and SHA-256 checks.

| Host loopback condition | Median (GB/s) | Observed range (GB/s) |
| --- | ---: | ---: |
| Download, 1 stream | 2.55 | 2.53–2.60 |
| Download, 4 streams | 2.27 | 2.20–2.32 |
| Upload, 1 stream | 5.05 | 4.79–5.28 |
| Upload, 4 streams | 4.48 | 4.34–4.51 |

These controls measure the transfer tool over Mac loopback. The engine
comparison still needs matching direction, stream count and payload size
on both engines and the corresponding in-guest controls. Raw
`host.jsonl` SHA-256
`826585c7c0dda12be32023dbbb9e1c4757886b7d90e2c442b82cd5855c89a77f`.

Use the signed `99db1aa` release, the pinned v6 API image and harness
`8c1c25d` to carry the same controls into the engine trials. Run one
installed-default admission pair for each of the twelve cells, with
three verified 1 GiB transfers in every leg. Vary the three supported
paths, both directions and one or four streams. Each leg must also
verify the same byte count and digest on host and guest loopback.

```sh
python3 bench/native/runner.py baseline --case W13 --transfer-path "$transport" \
  --direction "$direction" --streams "$streams" --size-bytes 1073741824 \
  --repeats 3 --a ctrs --b orbstack --resource-lane installed-default \
  --pairs 1 --pair-quiet-load 4 --max-pairs 2
```

For a ten-pair comparison, require every measured transfer in the
admission pair to be at or below half the slower loopback capacity at
the endpoints the path uses. The v3 reporter rechecks the receiver
hashes and byte counts, derives goodput from each receipt, and verifies
the recorded twofold headroom flag for both engines. Retain failed or
contended trials and tool-limited results with their path and controls. The queue uses
separate cohort invocations with `--pairs 10 --max-pairs 16` after admission.

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

#### W14 idle-resume with buffered frames

`base-20261122T124324-6b62` used `w14-v4-buffered-frames` from
`ce50555` and the signed `99db1aa` release. All ten alternating pairs
passed. Both engines verified 32 responses after the 30-second idle
period in each leg, with no leaked sessions or cleanup errors. Outside
CPU was at most 0.62 cores. The published-port path used 192 ctrs NAT
connections, leaving host-kernel CPU outside the measured scope.

| Metric | ctrs / OrbStack paired median | 95% CI | Descriptive result |
| --- | ---: | ---: | --- |
| Resume p50 | 1.4584 | 1.0259–2.2510 | Inconclusive |
| Resume p95 | 0.8787 | 0.7668–1.3071 | Inconclusive |
| Resume p99 | 0.8009 | 0.6472–1.1554 | Inconclusive |
| Cleanup latency | 0.9276 | 0.7705–0.9788 | Non-inferior |
| Sampled peak physical footprint | 0.0673 | 0.0603–0.0853 | Strict win |
| Measured engine CPU | 0.2539 | 0.2286–0.3754 | Incomplete |

The median trial p50 was 14.87 ms on ctrs and 9.48 ms on OrbStack. The
timer includes the published-port path and both endpoints' application
scheduling. These receipts do not isolate the source of the gap. Repeat
the idle-resume command above from `ce50555` with the signed release and
installed-default resources. Keep the v3 and v4 cohorts separate.
Raw trials SHA-256
`aaea59cf5cc691fd2a359302a202606ef5aad01f80c99644283925e7eed44c2c`.

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
The images are installed on the campaign Mac. The retained-content timing
cohort without concurrent load is recorded below.

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

The backing-file diagnostic now records private bytes alongside `st_blocks`
before the pull, after deployment and after cleanup. A 65,536-byte APFS
file reported all bytes private before cloning. The file and clone each
reported zero private bytes while sharing all blocks. After a 4,096-byte
overwrite in the clone, both reported 16,384 private bytes, while both
`st_blocks` values still represented 65,536 bytes. The diagnostic measures
deletion-reclaimable bytes per selected file. Shared extents remain excluded
even when both files are selected. Engine backing-file evidence is pending.
[Apple `getattrlist` manual](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/man/man2/getattrlist.2)

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

The allocation diagnostic records ten seconds of idle allocation change
before the pull and ten seconds of delayed allocation change after
application cleanup. Read both ordinary and private deltas on the same
backing identities. Preserve the idle deltas alongside the deployment
and cleanup deltas for review.

#### W8 backing allocation with no concurrent load

Both no-load conditions completed on `8b6b2be` with the signed `99db1aa`
release. Each engine verified the pinned outputs and cleanup. The five
allocation snapshots for each leg covered stable backing identities and
returned private bytes. Both idle windows exceeded ten seconds.

| Content | Engine | Deployment allocation delta | After application cleanup | Private delta after cleanup |
| --- | --- | ---: | ---: | ---: |
| Retained | ctrs | 706,117,632 bytes | 706,838,528 bytes | 706,838,528 bytes |
| Retained | OrbStack | 998,490,112 bytes | 991,838,208 bytes | 991,838,208 bytes |
| Derived | ctrs | 1,228,455,936 bytes | 1,229,193,216 bytes | 1,229,225,984 bytes |
| Derived | OrbStack | 1,382,703,104 bytes | 1,376,403,456 bytes | 1,376,403,456 bytes |

ctrs recorded 32,768 bytes of growth in both pre-pull idle windows and
425,984 and 442,368 bytes in the post-cleanup windows. OrbStack recorded
zero change in all four idle windows. The cleanup removed the owned
application resources and left the pulled images in the stores. The
backing files started with different allocation histories, and the
diagnostic supplies one pair per condition.

| Content | Run | Raw trials SHA-256 |
| --- | --- | --- |
| Retained | `w8-paired-e67bc5619fec` | `aa050a34fe99b9ee5d4f75feeec6d712bed182d9d865cecce7f7af77932a1790` |
| Derived | `w8-paired-b8a7b50e0d1e` | `fcdc4f22131b7daf0d844bd6afbca9f3307411f77b6c58bc6d997610d6e3709a` |

#### W8 backing allocation under concurrent API load

The same allocation diagnostic completed both content conditions with API
load. Every leg verified 35,159 reads and 14,841 writes alongside deployment
and cleanup. All five snapshots returned both allocation measures for the
same backing identities, and both idle windows exceeded ten seconds.

| Content | Engine | Deployment allocation delta | After application cleanup | Private delta after cleanup |
| --- | --- | ---: | ---: | ---: |
| Retained | ctrs | 664,174,592 bytes | 666,402,816 bytes | 666,402,816 bytes |
| Retained | OrbStack | 1,056,239,616 bytes | 994,926,592 bytes | 994,926,592 bytes |
| Derived | ctrs | 1,105,756,160 bytes | 1,107,771,392 bytes | 1,107,804,160 bytes |
| Derived | OrbStack | 1,441,845,248 bytes | 1,380,020,224 bytes | 1,380,020,224 bytes |

ctrs recorded 32,768 bytes of growth in each pre-pull idle window and
409,600 and 425,984 bytes in the post-cleanup windows. OrbStack recorded
zero change in those windows. The wrapper verified that the legacy
OrbStack registry was running again before releasing the W3 run. The
allocation comparisons remain descriptive because initial storage histories
differed and each condition supplied only one pair.

| Content | Run | Raw trials SHA-256 |
| --- | --- | --- |
| Retained | `w8-paired-f0baad335ce2` | `eb30425f61d1f109e4dd706b73baedb79b0fcc0993b3b4c130323d498775d320` |
| Derived | `w8-paired-22a69f1c75ab` | `d79b855c26bb75aba5e967922d7c451aec44f245feefdd930301f36e33f65072` |

#### W8 timing cohorts

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

#### W8 retained-content timing without concurrent load

All ten AB/BA installed-default pairs in `w8-paired-a56d7a800f7b`
passed host admission and deployment verification on harness `ce50555`
with signed release `99db1aa`. Both engines reported nine guest vCPUs.
ctrs reported 8,407,957,504 bytes of guest memory and OrbStack reported
63,157,620,736. OrbStack's Docker server reported 29.8.2.

Each pair shared four freshly derived layers totaling 206,480,802 to
206,480,812 compressed bytes. The registry logged complete delivery of
each changed digest and equal total blob bytes within every pair. Both
engines verified the retained image pins, the installed markers, 688
reads, 312 writes, persisted payloads after restart and the Marked output.
Host gate receipts passed and the OrbStack running-container inventory was
empty before and after each leg. The store was prewarmed and no cache
purge was used.

| Metric | Median ctrs/OrbStack | Paired 95% CI | Descriptive result |
| --- | ---: | ---: | --- |
| First pull to stack health | 0.5457 | [0.5045, 0.5493] | Strict win |
| Sampled peak physical footprint | 0.1689 | [0.1621, 0.2466] | Strict win |
| Measured whole-workflow CPU | 0.2858 | [0.2797, 0.2977] | Incomplete Mac NAT accounting |

Median first-pull-to-health time was 6.484 s (range 6.335–7.072 s) for
ctrs and 11.960 s (11.722–13.851 s) for OrbStack. At the recorded phase
boundaries, the paired median gap was 5.47 s overall and 5.00 s before
the stack-health phase, across the four pull/install and image
verification paths. Verification and cleanup after health are outside
that timing and inside the resource interval. The resource interval
includes the owned engine and fixture coordinator. Eleven ctrs host NAT
connections in each leg left their host-kernel CPU uncharged. Matched
resident controls use the same four conditions and ten pairs per
condition with `--resource-lane matched`. Backing allocation remains
covered by the separate diagnostics above.

As a CPU accounting cross-check, multiply each ctrs leg's host busy cores
by its whole-workflow wall time, then divide by the paired OrbStack
engine-plus-coordinator CPU. The all-process ctrs host estimate was
9.25–11.59 CPU-s and the paired OrbStack process measurement was
18.91–21.25 CPU-s. The median ratio was 0.4965 [0.4694, 0.5306].
The numerator uses the Mac's aggregate CPU tick fractions and includes
unrelated processes. The CPU-efficiency verdict still requires attributed
resource accounting.

| Artifact | SHA-256 |
| --- | --- |
| Signed ctrs binary | `10667e6d929207167f1812e5fd41c7ad6474f12bc9d5a42788af5ae027c93d17` |
| Guest kernel | `19657ca4cc150ae8d04d003ac494676bcc5845dd3a3a21cd6bfb17df605d4e6f` |
| Guest initramfs | `fb0f832b79eca9463d3aafb0bebdff8a5e620e2ff1779c896727fc91d3e32c87` |
| Guest data template | `9ded055a953c718b93b45432714ab8e0d4bb3528e5b439f6d157525dfaa76de8` |
| Plan | `65d13bdbc5a1eaa1fcbbaaa988352ad1a12c76c9626274e6f89b147c92de83fe` |
| Raw trials | `a8df6c4fa048e19d36a2d7854fdca699bcdce4b27fba4888d664410fdcca07cf` |
| Report | `03fa7dbbafd1091286a780b1e931cd0f0cbdaf7fdb757e59d5d0dcc714766658` |

#### W8 retained-content timing with concurrent load

The first OrbStack leg in `w8-paired-5527bdad376c` completed the 50,000
background API operations with overlap in all four pulls. It also passed
the deployment checks. The harness rejected the leg during resource
validation. A periodic sample started at monotonic 151671.639771 s and
read the fixture coordinator at 151671.639948 s, after the cleanup end
boundary read that process at 151671.639935 s. Sorting the periodic sample
by its start time put its later CPU reading before the true end boundary.

Phase accounting now requires a periodic sample to finish before the
phase end boundary starts. Replaying the saved cleanup trace keeps five
interior samples and reports 0.7834 CPU-s with no validation errors.
The original leg remains rejected in its run records. New W8 trial
records preserve separate workload and resource checks. The report
identifies resource rejection after a successful workload, and both
checks are required for timing admission.

The installed-default cohort on harness `ce50555` and signed release
`99db1aa` finished all 20 legs, with nine pairs admitted by the original
reporter. The corrected phase replay
recovers the first OrbStack leg for descriptive comparison. Replay
also verified all 50,000 background operations per leg, their persisted
writes, completion overlap in every pull window, changed-layer
delivery, deployment outputs and stable engine identities and budgets.
The no-load trial replay reproduced all 420 phase summaries exactly.

| Metric | Median ctrs/OrbStack | Paired 95% CI |
| --- | ---: | ---: |
| First pull to stack health | 0.5062 | [0.4980, 0.5216] |
| API completion p95 during pulls | 0.5436 | [0.4656, 0.6384] |
| API completion p99 during pulls | 0.7386 | [0.7052, 0.8993] |
| Sampled peak physical footprint | 0.1813 | [0.1762, 0.2504] |
| Measured whole-workflow CPU, incomplete NAT accounting | 0.9042 | [0.8972, 0.9126] |

Median first-pull-to-health time was 6.592 s (6.521–7.028 s) on ctrs
and 13.102 s (12.641–13.488 s) on OrbStack. The paired median gap
was 6.46 s overall and 6.12 s before the stack-health phase. The
background client used four workers with fixed work. The latency samples
are completions inside the actual pull intervals, with 485–546 per ctrs
leg and 5,237–5,507 per OrbStack leg. Every pull window had at least 73
completions. ctrs had 18–20 host NAT connections per leg. A new
ten-pair installed-default run on the corrected harness is queued.

To reproduce the diagnostic replay, use
`resource_cycles.phase_summary` from `1e4fa49` or later with the saved
`result.json` ownership and `under_pull_cleanup` boundaries and the
same leg's `resources.jsonl`. Use the corrected phase with the existing
whole-workflow resource summary, the saved `pull_to_health_s` and
`w8_benchmark.completion_metrics` over the saved completions and pull
intervals. Recheck the workload and host receipts before supplying
that row to `reporting.analyze` with the other 19 rows. Keep the original
failed status and exclude the replay from qualification.

| Artifact | SHA-256 |
| --- | --- |
| Plan | `d0fa82eec0b6bc1ee49998986d1d5737737fccf10b7381b8f21523a3310d377d` |
| Original trials | `46b97f86593b3a1e4eb8aebb16d42970488ca7fffb73fc56947a5c45e547516f` |
| Original report | `9361292dfd2981058ef9888dc2f556a8e1eb7363d79ec04a64ac88524f17977f` |
| Rejected leg result | `49a7880c155d023d7c2104ffd4c73e79f98524916016d68d2e2c3ddc93e1dc25` |

#### W8 derived-content timing without concurrent load

All ten installed-default pairs passed in `w8-paired-99ec4b7d32de`
on harness `ce50555` and signed release `99db1aa`. Each pair used 37
regenerated layers totaling 315,779,472 to 315,779,551 compressed bytes.
Each engine fetched every changed digest at its expected size, and total
blob delivery matched within each pair. All 20 legs verified 688 reads,
312 writes, persisted payloads after restart and the Marked output. Both
host gates passed for each leg and the OrbStack running-container
inventory was empty at both boundaries. The guest budgets were the
same as in the retained-content cohort.

| Metric | Median ctrs/OrbStack | Paired 95% CI | Descriptive result |
| --- | ---: | ---: | --- |
| First pull to stack health | 0.4334 | [0.4202, 0.4645] | Strict win |
| Sampled peak physical footprint | 0.1763 | [0.1737, 0.1795] | Strict win |
| Measured whole-workflow CPU | 0.2125 | [0.2069, 0.2184] | Incomplete Mac NAT accounting |

Median first-pull-to-health time was 7.568 s (7.205–8.162 s) on ctrs
and 17.034 s (16.482–19.844 s) on OrbStack. The paired median gap was
9.57 s overall and 9.06 s before the stack-health phase. ctrs used
11–12 host NAT connections per leg. The run warms the engine and
controls blob identity through fresh digests. Use the derived no-load
command in [W8 timing cohorts](#w8-timing-cohorts) to reproduce it.

| Artifact | SHA-256 |
| --- | --- |
| Plan | `1c0dd4c583cc235b2272b33f12b50f1cf1b7087e1b5801e2d07d34415ce128af` |
| Raw trials | `480e125d981b1db4fc87ad77196e2c17b84e0e52cfa4989734b2ed41f3b57f74` |
| Report | `b3c74d676bb2672dff558a712647b0731fd8f6b8b1b2f76598c535c663a8f826` |

#### W8 derived-content timing with concurrent load

All ten installed-default pairs in `w8-paired-6cef19315162` passed on
harness `ce50555` and signed release `99db1aa`. Both engines fetched
the 37 regenerated layers at their exact sizes. Compressed layer bytes
ranged from 315,779,495 to 315,779,525, and total blob bytes matched
within each pair. All 20 legs verified deployment and 50,000 additional
background API operations each, including 296,820 persisted background
writes across the cohort. Host gates and resource validation passed.
The legacy OrbStack registry was restored after the cohort.

| Metric | Median ctrs/OrbStack | Paired 95% CI | Descriptive result |
| --- | ---: | ---: | --- |
| First pull to stack health | 0.4138 | [0.3836, 0.4296] | Strict win |
| API completion p95 during pulls | 0.9089 | [0.8601, 0.9471] | Strict win |
| API completion p99 during pulls | 0.8169 | [0.7594, 1.0877] | Inconclusive |
| Sampled peak physical footprint | 0.1861 | [0.1833, 0.1920] | Strict win |
| Measured whole-workflow CPU | 0.7353 | [0.7312, 0.7372] | Incomplete Mac NAT accounting |

Median first-pull-to-health time was 7.509 s (7.010–7.717 s) on ctrs
and 17.806 s (17.357–20.437 s) on OrbStack. The paired median gap was
10.37 s overall and 10.15 s before the stack-health phase. The four
background workers supplied fixed work. During the actual pull windows,
ctrs recorded 708–907 completions per leg and OrbStack recorded
8,410–9,023. Every pull window had at least 92 completions. ctrs used
18–20 host NAT connections per leg. The independent matched-resource
controls and the fresh retained-load confirmation remain queued.

| Artifact | SHA-256 |
| --- | --- |
| Plan | `d3d8fa4d351fd5a70f0d48d3ca5f3fbe2bf422c02eb4cdb11cd60d1f61315dfb` |
| Raw trials | `8282de1dba8b2f5569af66a65f69d3e1a0c5795542e1d1a715d1ca7146332076` |
| Report | `876b5f07d480d2da932b7c6a48afe62df6be0d7c923f79dc09607633e9061d87` |

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

#### W10 refusal-cache trace

The ctrs-only diagnostic `w10-refusal-cache-e0512b7f1465` used harness
`ca24add`, the original signed release from the API cohort, eight
clients, seed 11 and a 20-second request window. The API backend identities
matched before and after interruption. All persisted writes were exact
and the trial reported zero unexpected errors.

Relative to restart command start, the command returned at 21.23 ms.
The owned endpoint's cache expired at 271.59–272.60 ms and again at
523.59–524.60 ms. The daemon recorded ages of 250 ms and 2,167 and 2,245
cache hits at those expiries. The first exact read began at 523.61 ms and
completed at 535.39 ms. The cache suppressed connection attempts between
expiries, leaving application readiness within each window unobserved.

Compare `campaign/mac-w10-refusal50` at `63cd346` with signed baseline
`99db1aa`. The candidate applies the parked `54c6a00` change and adjusts
its expiry tests. Build both with the same guest assets and run the
`ca24add` fixture, alternating private daemons from cloned warm-image stores.
Admit one pair on exact state and complete recovery first. Use ten alternating
pairs with a readiness-time upper 95% bound of 0.95 and a post-recovery
p99 and measured CPU per success upper bound of 1.03. Retain outage
errors and host NAT coverage. Confirm a passing candidate against
OrbStack separately before changing the default.

| Receipt | SHA-256 |
| --- | --- |
| `trials.jsonl` | `53cd874dccc7c2de4b995fab8e73f26988c167b46b117096bb97a21207fbc99b` |
| `correlated-cache-events.json` | `6058b9910e269fc578801031122be8c02fc6e3e8a66c1d999e20498af24ea47b` |

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

#### W10 owned-engine recovery on ctrs

Run `run-20261122T174201-330f` passed with the signed `99db1aa` release
and harness `2598d6a`. The run used the pinned API/Postgres/Redis stack
and eight clients for 90 seconds with seed 11. A verified owned daemon
and VM were interrupted after six seconds of load and restarted
after the declared three-second downtime. The new native process
identities reopened the same disk and control socket. The database and
API kept their container IDs. The PostgreSQL startup authentication file
had matching hashes before and after restart.

The first exact read finished 4.046 s after the restart request, or
7.301 s after interruption began. The run verified 47,362 acknowledged
writes, one persisted write whose reply was uncertain and the 500 seed
rows. There were 145,273 successful recovered requests and zero
unexpected errors. The outage classifier accounted for the failed
attempts during the interruption. The recovered client p99 was 6.838 ms.
This is one owned-engine admission. Equivalent whole-engine recovery
requires a dedicated OrbStack instance.

Use the pinned v6 OCI layout and signed binary with the private engine
root selected by the harness.

```sh
python3 bench/native/runner.py run --case W10 --engine ctrs --state warm \
  --interrupt-service engine --duration 90 --concurrency 8 --seed 11
```

Raw `trials.jsonl` SHA-256
`991329f40e9cae52a05fcfaf96ee5c44284bc822c79b0f64f5ea4d9d0bc82acb`.

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
run also samples APFS private bytes after cleanup on the same verified
backing files. The private-byte summary requires the full observation
count, stable file identities and complete attribute coverage. The
growth gate uses the declared active-backing, footprint and descriptor
budgets. The 12-hour qualification remains open.

#### W11 short ctrs growth result

`w11-mixed-20261122T121618-26c7` ran `dc198a9` on signed release `99db1aa`.
All 12 cycles passed exact state checks for 60,000 total API operations with
the same API, DB and cache processes. All 12 post-cleanup intervals lasted
at least 32 seconds. The driver reported zero cleanup errors.

| Resource | Post-warmup increase | Final change from first observation | Budget |
| --- | ---: | ---: | --- |
| Sampled physical footprint | 25,042,944 bytes | 55,443,456 bytes | Failed 16 MiB |
| Owned active backing allocation | 86,786,048 bytes | 105,103,360 bytes | Failed 16 MiB |
| Owned descriptors | 0 | 0 | Passed 16 descriptors |

The same ctrs backing file returned private allocation in all 12 observations.
Its private bytes grew by 105,103,360 from first to last, matching the total
allocation change. Total allocation rose at every boundary and grew by
30,572,544 bytes over the final five intervals. Inspect guest live data
and free extents on this private disk after cleanup, then test whether
guest trim reclaims the host bytes.

Use a stopped APFS clone of that private store for trim. Mount a new probe
volume and verify its ext4 mount resolves to the guest data disk `/dev/vda`.
Use `storage_trim_guest.py` to fsync a sentinel, sample guest usage and issue
`FITRIM`. Record two pre-trim backing snapshots across a quiet interval and
compare with the post-trim snapshot. Verify the sentinel and pinned image
again after a daemon restart. The submitted discard length is a guest
receipt. APFS shares the source extents until their last reference is removed,
so the clone's `st_blocks` delta measures the change in backing references.
[Linux FITRIM interface](https://github.com/torvalds/linux/blob/master/include/uapi/linux/fs.h)

| Receipt | SHA-256 |
| --- | --- |
| `trials.jsonl` | `a2df9e0330b4296060cf02e10cc1fcca1dcaea03a602fd9243d3570282ed6676` |
| `plan.json` | `0a51db19315e20977eadb3e600724f5d1a47850a499998885991727a3098ba0f` |
| `driver-result.json` | `f0914f7f9b678cd3e6981946403df7a2ee579c602c0fb1b10370330ab10984b0` |

#### W11 ctrs guest trim diagnostic

The signed `99db1aa` release booted a stopped APFS clone of the W11 store.
A new volume mounted at `/probe` resolved to ext4 on `/dev/vda`. A 10-second
idle control increased the clone's backing allocation by 32,768 bytes.
The guest then submitted 1,080,030,900,224 bytes of free extents through
`FITRIM`. Guest used space stayed at 1,068,244,992 bytes. Ten seconds after
trim, the clone's backing allocation had fallen from 1,471,102,976 to
1,211,015,168 bytes, a reduction of 260,087,808 bytes.

The stopped source retained 1,470,971,904 bytes of backing allocation.
Its private allocation rose by 258,141,056 bytes as the clone dropped
shared extents. The clone's private allocation rose by 69,632 bytes.
The sentinel checksum and the fixture image's config and layer identities
matched after restarting the clone's daemon. Receipt SHA-256:
`875731cffbc6e855682642a737e82cec08c295f273c9b727d7787bd2eb887367`.
For physical reclaim, run the same 420-second W11 diagnostic with a new
`--ctrs-root`, 9 vCPUs, 8,192 MiB and 32-second observations. Before boot,
create `data/vm/data.img` under that root by truncating a new file to the
template size and copying the template's `SEEK_DATA`–`SEEK_HOLE` extents.
Verify content across the union of the two extent maps. A native check
copied the 1 TiB template with exact logical contents and 25,247,744 bytes
of both ordinary and private allocation.

Require exact workload and cleanup receipts, then restart that owned
store in place. Repeat the idle control, trim and restart checks on the
same device and inode. Require ordinary and private allocation to match
at the stopped and trim boundaries before claiming physical reclaim.

#### W11 short OrbStack growth result

`w11-mixed-20261122T122344-a9fc` ran the same source and fixture. All 11
cycles verified 55,000 API operations, stable service identities and owned
cleanup. Every post-cleanup interval met the observation minimum.

| Resource | Post-warmup increase | Final change from first observation | Budget |
| --- | ---: | ---: | --- |
| Sampled physical footprint | 49,796,472 bytes | −304,411,504 bytes | Failed 16 MiB growth |
| Owned active backing allocation | 17,661,952 bytes | 18,006,016 bytes | Failed 16 MiB |
| Owned descriptors | 0 | 0 | Passed 16 descriptors |

macOS returned `EPERM` when opening the owned `data.img.raw` and `swap.img`
files for the private allocation probe. Their ordinary allocation receipts
passed the ownership checks. Both engines missed growth budgets in the
short run, and both 12-hour legs remain open.

The interval ending at cycle 8 added 16,613,376 bytes to
`data.img.raw`. The remaining intervals added 1,392,640 bytes net.
`swap.img` stayed at 4,096 allocated bytes throughout. A repeat
diagnostic uses the same 420-second work window and 32-second observation
intervals to check whether the jump recurs in ordinary and private bytes.

A later `getattrlist` metadata check returned private allocation for both
OrbStack files with the same device and inode IDs as the W11 receipt. The
sampler now requests file identity and private allocation together. A new
cycle is needed to measure private allocation growth. Metadata receipt
SHA-256: `65cd55f1287288a29c4c4fc5231a962feab581e0edaed0d98bb58ce86f196ae2`.

| Receipt | SHA-256 |
| --- | --- |
| `trials.jsonl` | `b4e684c256ca6eaaedc64cf054ffb2901699a0ae42e4f2dd0d495636bd46f947` |
| `plan.json` | `69fa21643125255e0f4b3efaa2f1536d9d1528504b82c0957a4328e1d2331e59` |
| `driver-result.json` | `f0914f7f9b678cd3e6981946403df7a2ee579c602c0fb1b10370330ab10984b0` |

#### W11 physical footprint attribution

Recomputed the steady physical footprint for all 23 post-cleanup
observations from 2,241 native samples in the two short runs. Join each
sample's process IDs to the verified ownership manifest and sort by the
sum of the same sample's physical-footprint counters. Take the middle
sample, or the average of the two middle samples, retaining each
process's contribution. Their sums reproduced every recorded steady
footprint.

| Engine | Cycles for the growth check | Helper change | Other process change | Total change |
| --- | --- | ---: | ---: | ---: |
| ctrs | 1 to 11 | VZ helper +24,363,008 B | ctrs daemon +679,936 B | +25,042,944 B |
| OrbStack | 1 to 8 | OrbStack Helper +49,845,624 B | OrbStack app −49,152 B | +49,796,472 B |

From cycle 0 to the final observation, the ctrs VZ helper contributed
53,985,280 bytes of the 55,443,456-byte increase. The OrbStack Helper fell
by 304,362,352 bytes from cycle 0 to the final observation. These results
localize the measured footprint to the helpers. Guest page cache, balloon
state, and host-side helper allocations still need separate measurements.
The derived `observations.jsonl` SHA-256 is
`8a3153923d264a43adde0e076e6d59eefeaf53aedcc1654a5806eb4869369365`.

#### W11 guest storage and memory attribution

Use the signed `99db1aa` release and the `ae96711` mixed pilot with a
six-minute work window per engine and 32 seconds of post-cleanup observation.
Take read-only samples immediately before and after exact row cleanup.
Record `pg_database_size`, the items heap and total relation sizes,
`pg_stat_wal.wal_bytes`, and the live and dead tuple estimates. Read
`df -Pk "$PGDATA"`, `du -sk "$PGDATA"` and `du -sk "$PGDATA/pg_wal"`
inside the owned database container. Verify the ctrs mount resolves to
`/dev/vda` and retain guest device and mount identity in both legs.

Read `/proc/meminfo` at both cleanup boundaries and immediately after
each post-cleanup observation. Retain available memory, file cache,
reclaimable slab, anonymous pages, and the ctrs guest's balloon pages.
Use background `GET /info` on the private ctrs daemon to retain the
ceiling, target, used, stall, and OOM counters. Match at least six
exact cycles to their valid host backing and footprint observations.
Use these samples for attribution under the current trim, database,
memory, and durability policies.

The 12-hour check now requires the API, DB and cache container IDs, guest
PIDs, start times and restart counters to match from setup through every
completed cycle, including its post-cleanup observation. A restart that
reuses the container ID fails the trial.

The native lifecycle check ran `ae96711` with the signed `99db1aa` release,
the v5 worker and the v6 portfolio. Each engine ran one cycle with
`--cycles 1 --resource-observation-seconds 32`. Both verified 5,000 API
operations, 200 queue jobs and 400 artifacts, and both retained the exact
initial API, DB and cache process identities through observation. Both
drivers finished with no cleanup errors.

| Engine | Run | Engine result SHA-256 |
| --- | --- | --- |
| ctrs | `w11-mixed-20261122T143417-ed26` | `622ad3e3f8be76e4b01d85e17a0be1147b58d38b05bdc7fe52955c9a02183eef` |
| OrbStack | `w11-mixed-20261122T143505-a93c` | `0bbb33278250bad38adf0f89464fbbc9dab8ee8bf452335c366512c3d4187b0a` |

These runs verify the lifecycle receipts. Freeze the candidate and resolve the
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

Build output receipt version 1 also keeps the warm rebuild, multi-file
change and branch-restore output receipts. The reporter checks that the
warm rebuild and restore match the initial build, the changed output
differs, and both engines agree on all four output receipts. The producer
checks each output against the fixture pin during its timed phase.

#### Installed-default W12 full-bind cohort

`base-20261122T113705-c0df` admitted ten alternating pairs at `fa72716`
using the signed `99db1aa` ctrs release. Both engines observed 9 vCPUs at
their installed memory defaults. Each leg verified 2,830 packages, 92,306
files and 532,136,968 bytes after install, along with matching build and
test-discovery receipts. All ctrs legs recorded zero host NAT connections.

| Metric | ctrs median | OrbStack median | Paired ratio and 95% CI |
| --- | ---: | ---: | --- |
| Workflow | 116.48 s | 89.76 s | 1.2999 [1.2883, 1.3223] |
| Offline `npm ci` | 26.57 s | 12.58 s | 2.1055 [2.0701, 2.1621] |
| Verification walk | 6.83 s | 1.65 s | 4.1610 [4.0605, 4.5087] |
| Jest discovery | 2.79 s | 1.12 s | 2.5178 [2.4545, 3.2113] |
| Measured engine CPU | 256.23 s | 220.18 s | 1.1630 [1.1593, 1.1725] |
| Sampled peak physical footprint | 3.32 GB | 9.16 GB | 0.3606 [0.3455, 0.3871] |

The install command and verification walk together explain a median 71.0%
of the per-pair workflow gap. The offline install command itself has the
largest absolute phase gap. Typecheck was non-inferior. Build, warm rebuild,
multi-file change and branch restore also trailed OrbStack. The mixed and
all-volume layouts will test how much of the gap follows the bind mount.

```sh
python3 bench/native/reporting.py --match base-20261122T113705-c0df
```

`trials.jsonl` SHA-256
`f13b187c281dc2838597476765e0a9744c43f2c788f1c5020db95ca34e0aa2b7`.

#### Installed-default W12 mixed-layout cohort

`base-20261122T144132-719e` used harness `fa72716` and the same signed
`99db1aa` release and fixture as the full-bind cohort. Both engines used
9 vCPUs. Guest memory was 8.41 GB on ctrs and 63.16 GB on OrbStack. Both
used a source bind at `/app` and named volumes at `/app/node_modules`,
`/app/production-server` and `/app/client/.next`. All ten alternating pairs
matched the installed tree, build output and test-discovery receipts.
No ctrs leg recorded a host NAT connection. Outside-engine CPU stayed
below 1.18 cores in the measured phases.

| Metric | ctrs median | OrbStack median | ctrs / OrbStack paired median and 95% CI | Descriptive result |
| --- | ---: | ---: | --- | --- |
| Workflow time | 83.65 s | 83.71 s | 0.9990 [0.9887, 1.0026] | Non-inferior |
| Offline `npm ci` | 11.60 s | 11.06 s | 1.0487 [0.9823, 1.0944] | Inconclusive |
| Verification walk | 0.294 s | 0.321 s | 0.9197 [0.9087, 0.9563] | Non-inferior |
| Jest discovery | 0.348 s | 0.378 s | 0.9174 [0.9029, 0.9240] | Strict win |
| Whole-trial engine CPU | 202.04 CPU-s | 203.32 CPU-s | 0.9927 [0.9831, 0.9989] | Non-inferior |
| Sampled peak physical footprint | 4.15 GB | 12.35 GB | 0.3386 [0.3263, 0.3680] | Strict win |

Build, typecheck, warm rebuild, multi-file change and branch restore each
met the non-inferiority bound. The full-bind cohort remains a loss. All
three volume mounts changed together, so this comparison leaves their
individual effects unknown.

```sh
python3 bench/native/reporting.py --match base-20261122T144132-719e
```

`trials.jsonl` SHA-256
`cc0d2392b340a26300fe7653c1298ce90eae5e344ddf4ffc85a4f4b8a02b5410`.

#### Installed-default W12 all-volume cohort

`base-20261122T151113-701c` ran `fa72716` on signed release `99db1aa`.
All ten alternating pairs verified the source, dependency lock,
installed tree, exact build output and test-discovery receipts. Both
engines mounted one writable named volume at `/app` and used 9 vCPUs.
Guest memory was 8.41 GB on ctrs and 63.16 GB on OrbStack. Outside-engine
CPU was below 0.65 cores across measured phases. All ctrs legs recorded
zero host NAT connections.

| Metric | ctrs median | OrbStack median | ctrs / OrbStack paired median and 95% CI | Descriptive result |
| --- | ---: | ---: | --- | --- |
| Workflow time | 82.78 s | 83.53 s | 0.9915 [0.9880, 0.9986] | Non-inferior |
| Offline `npm ci` | 10.90 s | 11.07 s | 0.9892 [0.9666, 1.0540] | Inconclusive |
| Verification walk | 0.276 s | 0.317 s | 0.8812 [0.8612, 0.9056] | Strict win |
| Jest discovery | 0.318 s | 0.366 s | 0.8689 [0.8615, 0.8886] | Strict win |
| Whole-trial engine CPU | 200.25 CPU-s | 202.26 CPU-s | 0.9915 [0.9839, 0.9954] | Non-inferior |
| Sampled peak physical footprint | 4.19 GB | 12.17 GB | 0.3481 [0.3353, 0.3788] | Strict win |

The workflow sums install through branch restore and excludes setup and
cleanup. Both layouts that keep dependencies and build output in named
volumes reached workflow non-inferiority. The full-bind loss and its
reproduced verification-walk gap remain open.

```sh
python3 bench/native/reporting.py --match base-20261122T151113-701c
```

`trials.jsonl` SHA-256
`f7cb64acab3ee7db305807da7421d36ac5f403d8e8698feea9b0cad2539e1b99`.

#### W12 inode-pruning probe

Test inode-pruning cost in two alternating pairs of private ctrs guests at
`/proc/ctrs/fuse_inodes` bounds of 65,536 and 98,304. Use the signed
`99db1aa` release and W12 timing revision 2 full-bind fixture. Read the
default bound before setting the test value. Record live inodes and host
file-table headroom after setup, install, the verification walk, discovery,
branch restore and cleanup. Take each extra sample outside its timed
phase. Require the existing exact W12 receipts for both variants. This
diagnostic tests whether the inode cap contributes to the gap and whether
a larger ceiling merits the full descriptor, watcher and comparative gates.

The first leg, `w12-inode-cap-1AdS00-1-65536` on harness `fa72716`,
stopped immediately after the 26.12 s install. The guest reported
103,959 live inodes with the knob still at 65,536. The observer rejected
counts more than 16,384 above the knob before collecting any host
descriptor counts. Patch 0017 queues reclamation asynchronously after
that threshold and retains in-use dentries. The separate 150,000-file
stress test measured the host process and completed recovery.

For the repeat, keep the same two alternating cap pairs and signed
artifacts. Before applying any threshold check, persist the guest
`live bound` pair, `kern.num_files`, `kern.maxfiles`, and
`kern.maxfilesperproc`. Count numeric descriptors from
`lsof -nP -a -p "$vm_pid" -F pf` after each phase, with the VM's kernel
start identity verified before and after. Treat the live inode count as
reclamation telemetry. Require the exact knob value, system headroom for
two candidate thresholds and headroom for one candidate threshold
against the kernel per-process limit. A native observer self-check
counted its own descriptors and retained a receipt when the expected
knob differed. The revised guest run is queued. The initial leg's
`trials.jsonl` SHA-256 is
`34f2c5fddfc1eee9bc2efbea2155d0a0590da178bf67ca8d0dcd94094805e517`.

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
checks each edited path against the runner's edit plan. It requires every
output from each multi-file edit, with matching compiled hashes and
ordered receipts across engines. It verifies that the recorded timestamps
are in order and that recomputed p50 and p95 match the reported values.
New trials declare the fixture version in the workload parameters and
verify that it matches the mount and result receipts.

Bind admission `base-20261122T130910-762c` on `b7c59e1` with signed
`99db1aa` verified 120 results from 60 edit sequences on each engine,
with zero missed or stale results. Each watcher retained its PID and
start ticks. The current reporter admitted the pair after checking the
ordered result hashes. Raw trials SHA-256
`683df1ceb49d7476fe191d6fb43ec9927493f72855fb1c3e13951b0d6bc3d2da`.

Named-volume admission `base-20261122T135409-22b2` used the same harness
and signed release. Both engines verified all 120 results using
`UseFsEventsOnParentDirectory`. There were no missed or stale results
and each watcher kept its PID and start ticks. The current reporter
admitted the pair. Raw trials SHA-256
`d552ae484e500a1a8a1d2f18de04e3ade485374b2efc003458013a9df0038f3d`.

```sh
for mount in bind volume; do
  python3 bench/native/runner.py baseline --case W12-watch --watch-mount "$mount" \
    --watch-edits 60 --a ctrs --b orbstack --resource-lane installed-default \
    --pairs 10 --pair-quiet-load 4 --max-pairs 16
done
```

#### Installed-default W12 bind watch cohort

`base-20261122T131311-6799` ran `b7c59e1` on signed release `99db1aa`.
All ten alternating pairs verified 2,400 outputs with zero misses, stale
results or watcher changes. The current reporter independently checked
each edited path, output hash and latency summary. Both engines used
9 vCPUs. Guest memory was 8.41 GB on ctrs and 63.16 GB on OrbStack.
Outside CPU during edits stayed below 0.34 cores. Four short OrbStack
cleanup phases lacked that counter, so those legs used endpoint
host-load admission. The maximum endpoint load was 3.00 on 10 host CPUs.

| Metric | ctrs / OrbStack paired median | 95% CI | Descriptive result |
| --- | ---: | ---: | --- |
| Edit-to-result p50 | 0.8809 | 0.8381–0.9311 | Strict win |
| Edit-to-result p95 | 0.9712 | 0.9393–1.0258 | Non-inferior |
| Sampled physical footprint | 0.2686 | 0.2440–0.2835 | Strict win |
| Whole-trial engine CPU | 1.1862 | 1.1699–1.2150 | Loss |

Median trial p50 was 0.649 s on ctrs and 0.724 s on OrbStack. Host polling
of the compiled output is part of the latency. No ctrs leg reported a
host NAT connection. Setup added a median 28.80 engine CPU-seconds per
pair, while edits used 6.83 fewer CPU-seconds. The setup phase includes
mount preparation, the offline install, the installed-tree verification
walk, a standalone TypeScript compile and the watcher's initial compile.
The receipt gives a single CPU total for those operations.
Raw trials SHA-256
`a39223750c6e0a1aad9981ab249982e0a7b76d379b430d1261cc8441a2d144dc`.

The W12 proof tool measures each setup operation with independent engine
CPU and wall-clock boundaries. Run `python3 bench/native/fixtures/w12/proof.py
--engine ctrs --mount bind` and repeat with `--engine orbstack` using the
pinned W12 assets and a signed ctrs build. The diagnostic samples appear
under `setup_phases`. Use the regular paired cohort for acceptance,
since the extra counter reads add work to setup.

#### Installed-default W12 named-volume watch cohort

`base-20261122T135713-1c0c` used clean harness `b7c59e1` and the signed
`99db1aa` release with the same kernel and initramfs as the bind cohort.
Both engines used 9 vCPUs. Guest memory was 8.41 GB on ctrs and 63.16 GB on
OrbStack. The `w12-watch-volume-v2` fixture edited a named volume through
`docker exec` and used TypeScript's `UseFsEventsOnParentDirectory`.
All ten alternating pairs verified 2,400 exact outputs with zero misses,
stale results, or watcher changes. All phases recorded outside CPU, and
that counter stayed below 0.29 cores during edits. Every ctrs leg recorded
zero host NAT connections.

| Metric | ctrs median | OrbStack median | ctrs / OrbStack paired median and 95% CI |
| --- | ---: | ---: | --- |
| Edit-to-result p50 | 0.585 s | 0.806 s | 0.7250 [0.7045, 0.7669] |
| Edit-to-result p95 | 1.208 s | 1.619 s | 0.7628 [0.7164, 0.8047] |
| Sampled peak physical footprint | 3.56 GB | 12.30 GB | 0.2865 [0.2811, 0.3247] |
| Whole-trial engine CPU | 91.40 CPU-s | 106.65 CPU-s | 0.8594 [0.8427, 0.8766] |

All four intervals cleared the descriptive strict-win threshold. Edit
latency includes the `docker exec` edit transport and output polling.
The bind cohort uses host filesystem edits, so each cohort supports an
engine comparison within its own mount condition.

```sh
python3 bench/native/runner.py baseline --case W12-watch --watch-mount volume \
  --watch-edits 60 --a ctrs --b orbstack --resource-lane installed-default \
  --pairs 10 --pair-quiet-load 4 --max-pairs 16
python3 bench/native/reporting.py --match base-20261122T135713-1c0c
```

Raw trials SHA-256
`e627ea87c50ecd7ddadf98bb4be725a9b1cd47b38b8e6579b8d442ec65465261`.

### Independent Gitea holdout

`holdout-v3-exact-content` verifies the seeded repository and issue fields in
REST write and read responses. It checks the `main` branch and verifies the
README from each smart-HTTP clone against the pinned Gitea template after
the clone timer stops. Both registry manifests and their configs were
verified by SHA-256 and resolve to Linux ARM64. The holdout checks config
and ordered layer pins and compares those identities across engines. It
also verifies that each running container uses the image ID reported by
its own engine. A two-engine run fails on differing pinned image inputs,
Compose hashes or cloned README hashes. The workload still needs a frozen
candidate and OrbStack run.
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

### 2026-11-22: native Linux W1–W13 admissibility survey

[Survey evidence and all timing/resource tables](evidence/linux-survey-2026-11-22.md)
add narrow native amd64 support for the remaining movable W4/W5/W8/W9,
API/DB/queue W10, finite W11, full-bind/all-volume W12 and W12-watch cells.
Three alternating pairs per cell are pilots, not qualification: **72/72
correct, 71/72 host-admitted, 64/72 strict resource-valid**, with 35 admitted
timing pairs and 28 complete admitted resource pairs. All invalids remain raw;
watch-volume has no paired resource estimate. Linux CPU remains incomplete.

The old bind per-file watch strategy fails identically on both engines
(97/120 correct, the exact same 23 missed outputs). The separately versioned
native parent-directory fs.watch strategy uses the existing campaign volume
configuration, no polling or relaxed oracle; every new trial passes 120/120.
Old failures and the stopped original schedule are explicitly preserved.
Four-stream W13 controls also remain tool-limited under the unchanged 2x
headroom rule; there is no scored W13 throughput verdict. Durable images,
source bundle, inputs, raw records/traces, schedules and analysis live under
`/home/ubuntu/ctrs-evidence/linux-survey-20261122/` with the committed manifest.

The subsequent bounded profile loops covered **W5 bind** (paired C/D 1.352) and **W12**
(full-bind install 1.338, workflow 1.042; all-volume typecheck 1.140, plus all
other point-estimate losing phases). No survey result is an engine change.
Mac-only FD/APFS/VM-disk/12h qualification remains on the Mac handoff. Linux
shares the host kernel; no Linux result closes a macOS/OrbStack gate.

### Final Linux standing after the bounded queue, 2026-11-22

[Losing-cell profiles and controls](evidence/linux-gaps-2026-11-22.md) are now
landed. W5's exact 60-edit boundary-free control removes the measured bind
gap: 0.151253/0.150781 s. Actual Docker phase-boundary work adds about 45 ms
outside each edit timer and changes cadence relative to the existing esbuild
polling backend. This is not an engine speedup or a replacement of the pilot.
W12's eight new normal controls and four separately instrumented profiles are
all correct/admitted/strict resource-valid. Node/npm accounts for about 90%
userspace plus 8–9% kernel CPU; runtime own-process CPU is 0.01–1.81%.
Quota/priority and speculative-mitigation differences were checked and absent.
Original losses, variable volume installs and slower normal full-bind warm
rebuild remain visible; an exclusive engine-specific cause is not established.
No unsupported patch or meaningless candidate cohort was manufactured.

This table is Linux-only and preserves each cohort's age, sample count and
scope. **C/D** means within-pair ctrs/Docker, lower is faster; it is not a
cross-cohort ratio of medians. Three-pair cells are pilots, not qualified wins.
All sampled Linux CPU is incomplete/lower-bound; strict ownership invalids
are never zero or replaced. Anon+kernel excludes file cache and is not a
Mac VM-footprint comparison. Full IQR/interval/resource tables and exact
commands remain in the linked evidence, not collapsed into a single league.

| Workload | Linux result / exact boundary | Correctness, resources and remaining limitation |
|---|---|---|
| **W1** restart/recovery | Five paired native pilots; exact acknowledged state and new-write recovery C/D .776 [.768,.802]. | 10/10 correct/admitted/resource-valid. Application restart, not engine/kernel crash or physical power loss. [Checkpoint](evidence/linux-checkpoint-2026-11-22.md). |
| **W2** API/DB | Existing 50,000-op, concurrency-8 coverage; observer and loopback/host-IP/container-peer profiles; two engine hypotheses rejected and reverted. | Candidate cohorts 60/60 correct/admitted, 58/60 resource-valid. No qualified p99 improvement; app/DB dominates but an engine-specific deficit cause is unproven. [W2 evidence](evidence/linux-w2-2026-11-22.md). |
| **W3 / W3-v4** storage/transactions | Basic five-pair pilot plus ten full-input v4 pairs; RW p99 C/D 1.040 [.830,1.958], RW TPS .902 [.797,.999], restart 1.100 [1.025,1.142]. | v4 20/20 correct/admitted/resource-valid; native pgbench/flush contracts verified. Losses retained; independent profiles reverse TPS ordering, no supported engine candidate. Fits page cache, not sustained disk or power-loss proof. [W3-v4](evidence/linux-w3v4-2026-11-22.md). |
| **W4** queue | Three native pairs at 1/4/16 workers; completion C/D .707/.722/.662, queue p99 .747/.762/.778. | 6/6 correct/admitted/resource-valid; imported common bytes and frozen native workers/cache. [Survey](evidence/linux-survey-2026-11-22.md). |
| **W5** bind/volume watch | Three five-edit median pilots: bind C/D 1.352, volume .737. Separate matched 60-edit observer controls remove bind gap; no engine change. | Survey 6/6 correct/admitted, 5/6 resource-valid. Exact persistent-app outputs remain mandatory. Boundary-free controls lack phase CPU qualification; not a tail-parity claim. [Follow-up](evidence/linux-gaps-2026-11-22.md). |
| **W6** Rust build | Ten paired native pilots; build C/D .956 [.914,1.011]. | 20/20 correct/admitted/resource-valid; no significant timing win. Frozen common fixture; ordinary build workflow, not a Mac builder comparison. Initial Linux pilot above. |
| **W7** build/first use | Promoted H3 HTTPie first-use C/B .773 [.707,.786]; still C/D 1.164 [1.036,1.180]. Three residual hypotheses all rejected/reverted. | H3 30/30 valid; residual 90/90 correct/admitted, 89/90 resource-valid. Build/load excluded from first-use timing; no new uncached-build claim. [H3](evidence/linux-httpie-2026-11-22.md), [residuals](evidence/linux-httpie-residual-2026-11-22.md). |
| **W8** pull/materialize under load | Three native frozen-portfolio pairs; whole workflow C/D .567, pull-to-health .563. | 6/6 correct/admitted/resource-valid. Existing local registry/shared bytes and derived variants; not internet speed. [Survey](evidence/linux-survey-2026-11-22.md). |
| **W9** finite CI jobs | Three native pairs; fixed-16 completion C/D .731/.627/.553/.635 at concurrency 1/4/8/16. | 6/6 correct/admitted/resource-valid; several intervals span one. Closed finite work, no synthetic infinite throughput extrapolation. [Survey](evidence/linux-survey-2026-11-22.md). |
| **W10** API/DB/queue recovery | Three pairs each; recovery C/D .741/.471/.723. Exact recovery/new work checked. | 18/18 correct/admitted/resource-valid. Component restart/recovery, not kernel panic or hardware failure. [Survey](evidence/linux-survey-2026-11-22.md). |
| **W11** finite mixed work | Three planned native pairs, two timing-admitted; mixed-work C/D .979 [.900,1.058]. | 6 correct, 5 host-admitted, 4 strict resource-valid records; only one complete admitted resource pair. Mac FD/APFS/VM-disk and existing 12h/engine qualification are not closed by this finite Linux pilot. [Survey](evidence/linux-survey-2026-11-22.md). |
| **W12** workspace / watch | Three pairs per full-bind/all-volume/watch mount. Original workflow C/D 1.042/.966; original phase losses retained. Native watch p50 .893/.793 and p95 .872/.778. Follow-up eight controls/four perf workflows, no supported engine patch. | Full workflows 12/12 valid; native watch 12/12 correct/admitted, 7/12 strict resource-valid, no volume resource pair. Legacy per-file bind watcher fails identically on both engines (97/120, same 23 misses), preserved invalid. Native parent-directory strategy passes all 120 outputs per trial without polling/deadline/oracle changes. [Survey](evidence/linux-survey-2026-11-22.md), [follow-up](evidence/linux-gaps-2026-11-22.md). |
| **W13** network | **Tool-headroom blocked**: existing one-stream and sanctioned four-stream configurations cannot demonstrate the unchanged 2× ceiling over both engine paths. No new scored cohort. | Historical transfers remain byte-exact and tool-limited; three Docker ownership failures remain invalid. Four-stream controls also tool-limited, despite exact bytes. No threshold relaxation, receiver rewrite or throughput-parity verdict. [Checkpoint](evidence/linux-checkpoint-2026-11-22.md), [four-stream evidence](evidence/linux-survey-2026-11-22.md). |

#### Recoverability, compatibility and finite stopping boundary

The [recoverable baseline](evidence/linux-amd64-checkpoint-2026-11-22.md) and
[corrected independent restore/runtime proof](evidence/linux-integrated-runtime-2026-11-22.md)
remain authoritative: common fixture lock SHA
`246c0c6aca1d8c0a749f37b9281ec32735a326e414de872b45b1e77fa4f3b874`,
preserved archive and binary identities, restore via existing `--linux-archive`
without regenerating locks. Disposable Docker always uses private netns,
private containerd/address/root/state, explicit `--containerd`, separate
Docker roots/socket and no default bridge/socket. Do not repeat the initial
incompletely isolated restoration; the docker0 incident cause stays unconfirmed.

Integrated compatibility remains **ctrs 482/1/26; isolated Docker 471/2/30**
(pass/fail/skip). Both VRF failures are host unsupported; Docker's remaining
SYS_ADMIN mount failure is the default AppArmor boundary. Earlier copy-UID
behavior and all historical ctrs failures are reconciled in that report.
Active IPv4 deny/allow controls and exact stop cleanup were proved there;
independent active IPv6 policy proof was not performed. No broad full-e2e
pass is implied by classified nonzero failures.

The five historical Docker transient-scope failures remain unchanged and
invalid. [Actual process/start-time transitions](evidence/linux-httpie-2026-11-22.md)
reproduce runc ancestry/reparenting gaps, but missing historical offending-PID
snapshots prevent individual retrospective attribution. New invalid survey and
residual receipts are also retained. Strict ownership was never weakened.

Preserved evidence roots under `/home/ubuntu/ctrs-evidence/` include
`linux-amd64-v1`, `linux-integrated-20261122`, `linux-w2-20261122`,
`linux-httpie-20261122`, `linux-checkpoint-20261122`, `linux-w3v4-20261122`,
`linux-httpie-residual-20261122`, `linux-survey-20261122` and
`linux-gaps-20261122`. Each scientific slice has committed SHA-256 manifests
and replay/restore instructions. Survey/gap manifests cover **4,175 / 2,546**
durable artifacts; frozen pre-rebase bundles are labelled by their actual
heads, never relabelled as final integrated source.

**Linux goals left:** no unstarted movable workload, sanctioned W13 tool
configuration, or currently profile-supported engine candidate remains in
this bounded queue. H3 is the promoted product change; all unqualified runtime
edits are reverted. Unexplained W3/W12 residuals and incomplete CPU/ownership
attribution remain honest limitations, not claims of parity or impossibility.
A new exploratory hypothesis or larger qualification campaign needs its own
declaration; it is not a silently extended pilot or an erased losing cell.

The finite Mac handoff immediately above is unchanged: combined kernel/agent/
watch correctness at one build, W5/W12-watch, H3/new-default comparisons,
remaining acceptance-matrix cells including the existing long reliability
contract, and W13 headroom on that host. **Linux shares the host kernel; Mac
has a VM boundary. All full macOS/OrbStack gates remain open.** No Mac work was
run or held hostage to Linux completion.

Final integrated offline check after the incoming Mac-only benchmark/reporting
updates: `make test-bench TMPDIR=/home/ubuntu/repos/ctrs/.work/tmp` printed
`Ran 542 tests in 25.178s`, `OK (skipped=16)`, exit 0. The first attempt in the
fresh documentation worktree encountered 28 missing explicit `.work/tmp`
scratch-parent errors; creating that parent fixed the environment, without
changing tests or guards. Both attempts and both large-manifest verification
logs are preserved by `docs/evidence/linux-standing-2026-11-22.sha256`.
