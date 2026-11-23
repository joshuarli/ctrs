# Production defaults reconciled with experiment decisions, 2026-11-23

Starting point: `main` at `33a1aa032b89f89d7971a618545966ccca39edc1`, the
reviewed checkpoint, with no later commits. The 2026-11-23 bulk merges were
meant to retire parked branches. Ten of them also brought those branches'
production diffs into `main`. Each diff was compared with its recorded
decision. Where no later acceptance superseded the decision, the diff was
reverted by path. Bench and docs content from the same merges stayed, as did
H3 and the unrelated correctness fixes. The merges themselves were not
reverted, and no other branch was merged.

Repair commits: `657a0f2` (restored defaults and the compression
regression) and `b5ec34b` (tests that pin the decisions).

## Reconciliation

| Behavior | Originating change | Recorded decision | Default at `33a1aa0` | Corrective action |
| --- | --- | --- | --- | --- |
| Default build/load layer compression | `perf/zstd-load` `bd35436`, merge `2df176e` | Rejected: a valid 2 GiB repeated-block layer fails first use under the unchanged expansion cap ([evidence](native-build-boundaries-2026-11-16.md#zstd-default-rejected-by-expansion-admission)) | zstd level 3 injected into classic mirror builds and the buildx `--load` rewrite | **Restored** BuildKit's default (gzip). Explicit caller `compression`, `compression-level`, `force-compression` and `oci-mediatypes` are still carried. Regression added (below). |
| VZ data-disk synchronization | `campaign/np-full-sync` `f536b6e`, merge `4528e46` | "Full remains experimental"; preserve the default Fsync ([evidence](../native-performance-progress.md#w3-v4-group-commit-on-fsync-and-full)) | `Cached` + `Full` | **Restored** `Cached` + `Fsync`, now the named constants `DATA_DISK_SYNC` and `DATA_DISK_CACHING`, pinned by a test. |
| Refused-connection cache TTL | `campaign/mac-w10-refusal50` `63cd346`, merge `ee0917f` | Keep 250 ms; 50 ms missed the CPU budget ([evidence](../native-performance-progress.md#cpu-before-interruption-and-after-recovery)) | 50 ms | **Restored** 250 ms. The existing unit test pins it. |
| Guest `CONFIG_SCHED_MC` | `campaign/np-sched-mc` `1bea138`, merge `09542a6` | Rejected ([W2 IPI evidence](native-w2-ipi-2026-11-18.md)) | enabled | **Removed** |
| Guest `CONFIG_ARM64_USE_LSE_ATOMICS` | `experiment/np-lse-only` `f7ea791`, merge `def1c6c` | Rejected ([evidence](native-lse-2026-11-16.md)) | enabled | **Removed** |
| Guest `CONFIG_UPROBE_EVENTS` | `experiment/np-uprobes` `e5b9a33`, brought in through `np-preempt-full` and restored by `31c90ed` | Private diagnostic kernel only ([retained ledger](../native-performance-retained.md)) | enabled | **Removed** |
| Build-registry vsock routing (boot argument, guest dial, macOS mirror start order) | `campaign/build-mirror-vsock` `d370e8c`, merge `7307888` | Parked; the full W6/W7 comparison is still open ([campaign status](../campaign-native-performance.md#status)) | enabled | **Isolated**: reverted on `main`; the candidate stays on its branch. |
| Relay drain without zero-fill (`STEP_BUDGET`) | `perf/relay-batch` `2263bc1`, merge `485dd63` | Parked: within noise ([W13 evidence](native-w12-w13-2026-11-18.md)) | `read_into` change plus an unused `STEP_BUDGET` constant | **Reverted** |
| `CTRS_EXP_SHARE_DEVICES` extra virtiofs devices | `exp/fs-devices` `dea8b4f`, merge `36850b3` | Two-device split rejected ([evidence](native-w12-w13-2026-11-18.md#two-virtiofs-devices-on-one-share-2026-11-20)) | environment knob in the production VMM | **Removed** |
| Builder readiness audit/profile logging | `diagnostic/np-ready-audit`, `diagnostic/np-builder-readiness`, merges `63f1acf` and `3b65b9e` | Intentionally unintegrated instrumentation | info-level logs on every readiness probe | **Removed**. The readiness invalidation fix `24c4c92` was already on `main` and is unchanged. |
| H3: bounded install overlap, four-worker/FIFO barrier, zlib-rs guest gzip | `83e9c15` | Accepted, Linux C/B 0.773 [0.707, 0.786] | present | **Retained** without change. The existing gzip concatenation, truncation and error-path tests pass. |
| BuildKit cache-usage field names | `cd00a03` | Correctness fix | present | **Retained** |

After `b5ec34b`, `guest/kernel/ctrs.config` is byte-identical to `5cac40d`
(SHA-256 `ac9d0e2a…09585`), the source of the last Mac-verified kernel.

## Disk persistence contract

The product guarantee is unchanged. The ctrs data disk is `Cached` +
`Fsync`. A guest flush (`fsync`/`fdatasync`, sent to virtio-blk as a flush)
returns only after the host's `fsync(2)` of the disk image. macOS `fsync`
does not force the drive's volatile write cache to permanent storage.
Acknowledged writes therefore survive a guest crash, a VM or engine process
death and a host kernel panic once the data reaches the device. They are
**not** guaranteed across a sudden host power loss. `Full` (`F_FULLFSYNC`)
would give that guarantee. Its only measurement is the three-pair ctrs-only
diagnostic, which recorded about 0.06× the write throughput and about 39× the
mean WAL sync time. It stays a candidate. Promoting it needs an explicit
durability decision and fresh W3/W3-v4/W10/W11 measurements on that build.

Benchmark scope: the existing W3 and W3-v4 Mac storage ratios describe the
Fsync contract only. They remain `durability-unverified` against OrbStack,
whose host flush contract is unknown. No ctrs storage cell may be described
with Fsync numbers under a Full default, or the reverse.

## Compression compatibility regression

The historical fixture did not survive: its job root under `.work/tmp` was
deleted. The new fixture is a **deterministic equivalent** rebuilt from the
documented construction, not the original artifacts. It repeats one 64 KiB
high-entropy block (xorshift64, seed `0x9E3779B97F4A7C15`) 32,768 times as
the single 2 GiB file `payload`.

- `crates/ctrs-init/src/linux/layers.rs` (Linux-only, run by CI
  `linux-musl`):
  - `highly_compressible_zstd_layer_exceeds_the_expansion_cap` builds a valid
    zstd frame of the layer (about 295 KB; BuildKit's was 298,209 B). Decoded
    without a cap, it reproduces the exact 2 GiB tarball. Through the
    production `decoded()` path, it fails with `stream exceeds the allowed
    size`.
  - `rejected_zstd_layer_leaves_no_partial_layer` sends the frame through the
    real `receive()` staging and install path. It asserts the same error, no
    marker and an empty store afterwards.
  - `same_layer_as_gzip_decodes_exactly_within_the_cap` streams the same
    layer as gzip through `decoded()` and checks every byte.
  - The guard itself is unchanged: `expansion_cap` is still
    max(1 GiB, min(64 GiB, 256 × compressed)).
- `crates/ctrs/src/daemon/builder.rs`
  (`mirror_build_keeps_buildkit_layer_compression`) and
  `crates/ctrs/src/daemon/buildgrpc.rs`
  (`default_load_keeps_buildkit_layer_compression` and
  `explicit_export_controls_preserve_buildkit_compression_policy`) check the
  exporter side.
- `tests/layer-expansion.sh` is the end-to-end check against a scratch engine:
  - classic `POST /build` and the default buildx `--load` must each return the
    exact payload SHA-256 on first use;
  - an explicit `compression=zstd,force-compression=true` load must be refused
    twice;
  - with `CTRS_LAYER_ROOT` set, no `.tmp-*` or `.blob-*` entries may remain;
  - the default image must still run after the refusal.

  It needs 12 GiB free on the engine disk. It passed on the Mac at `b5ec34b`
  (see below). It has not run on a Linux host.

`decoded()` moved the decoder choice out of `unpack()` into a boxed reader so
the tests can drive the production composition without writing 2 GiB to disk.
That adds one dynamic call per read of at least 8 KiB. The H3 install path is
otherwise unchanged.

## Integrated identity

Source `b5ec34b0ae98b926f5eecde9bdb532d28714b07f`. Built on the Mac (M1 Max,
macOS 27.2.1) with `CARGO_ENCODED_RUSTFLAGS=""`:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `target/release/ctrs` (`cargo xtask host`; ad-hoc signed, `codesign --verify --strict` clean, virtualization entitlement present) | 6,738,992 | `7c5fc5be23bb0784c2dea2be0faa077d5c354c5a60842b8b5fa3c60308355eca` |
| `target/aarch64-unknown-linux-musl/release/ctrs-init` (`cargo xtask guest`) | — | `44d6ea37f866cfdedda612199ebd0dc904d9ec126bd585d5c74c86fbbcb68372` |
| `guest/out/initramfs.cpio` | 4,388,212 | `4c8bec12f58af48ba1dd855c73265d28b0af37cf6e7d5c8833362892ad3239da` |
| `guest/out/Image`: not rebuilt; built 2026-11-22 from `5cac40d`, whose `guest/kernel/` tree is identical | 18,802,696 | `19657ca4cc150ae8d04d003ac494676bcc5845dd3a3a21cd6bfb17df605d4e6f` |
| `guest/kernel/ctrs.config` | — | `ac9d0e2ab463259aaaa71617e25caa2a1edba5999e7be6f78b1fe23648109585` |

Runtime defaults in this source:

- data disk `Cached` + `Fsync`;
- refusal TTL 250 ms;
- BuildKit default (gzip) for default loads;
- `CONFIG_PREEMPT_VOLUNTARY`, default HZ, no `SCHED_MC`, LSE or uprobes;
- build registry over the existing host-bound transport order (NAT first,
  framed vsock fallback);
- vCPUs max(host − 1, 2) and memory unchanged.

### What was tested at this source

| Check | Result |
| --- | --- |
| `make test-rust` (macOS) | 273 passed, 0 failed |
| `ctrs-init` Linux suite: aarch64 musl test binary in a disposable root `alpine:3.22` container with tmpfs `/tmp` | 94 passed, 0 failed, including the three new regressions (16 layer tests in 3.2 s) |
| `cargo test -p xtask -p ctrs-vmm` | pass. A temporary `CONFIG_SCHED_MC=y` made the kernel guard fail as intended. |
| `make lint` (macOS) and clippy `-D warnings` for `ctrs-init`/`ctrs-proto` on `aarch64-unknown-linux-musl` | clean |
| `make test-bench` | 556 tests OK |
| `conformance/smoke.sh` with `CTRS_BINARY` set to the signed host above (Mac resumed the same day) | 21 pass, 0 fail |
| `tests/e2e.sh`, scratch engine (9 vCPUs, guest `6.18-ctrs`) | **509 passed, 0 failed, 0 skipped**, exit 0 |
| `tests/watch-recovery.sh` | exit 0 |
| `tests/fuse-inode-bound.sh` | First attempt exit 1: `lsof` was missing from the shell's `PATH` (no `/usr/sbin`), so the script found no VM process. That failure is environmental and is kept here. Rerun with `/usr/sbin` on `PATH`: exit 0. 150,000 files read back, peak 65,575 descriptors under the 73,728 limit, back to 89 after `drop_caches`. |
| `tests/layer-expansion.sh` on the Mac | exit 0. The classic `POST /build` and the default buildx `--load` each returned payload SHA-256 `680be809fbc078cfd603d13375cbcd634817888941149c88f4383b1473627bfd` on first use. The explicit zstd load was refused on both runs: the daemon logged `failed to unpack …/payload` while streaming the layer. The default image still ran afterwards. The cleanup check was skipped because the guest layer root is not visible from the Mac. The Linux unit test covers it. |
| Integrated native Linux runtime suite | **not run**: no Linux host access from this session |

The newest full Linux runtime result (ctrs 482/1/26) belongs to `65b7bbd`;
H3 has subset evidence. Neither qualifies `b5ec34b`. Every Mac cohort result
belongs to the binary recorded with it. None transfers to this build.

## Performance standing after the repair

The repair returns `main` to the configuration the Mac cohorts measured for
disk sync, refusal TTL, kernel options, build-registry transport and load
compression. The **ratios still belong to their recorded binaries**, though,
and this build differs from them in H3's guest gzip backend and the cache-usage
fix.

- **Still descriptive as recorded:** W2, W3/W3-v4 (Fsync scope),
  W4, W5, W9, W10 (250 ms), W12 and W12-watch, W13 and W14.
- **Need an affected-cell remeasurement before reuse at this build:**
  first-use and materialization cells that unpack gzip layers in the Mac guest
  (W1 cold, W7 first use, W8 pull-to-healthy, W6/W7 load), because H3's zlib-rs
  backend is new on the Mac guest.
- **Linux lane:** unchanged. H3 C/B 0.773 [0.707, 0.786], still C/D 1.164
  [1.036, 1.180] against Docker. The bounded queue is closed. W3, W12,
  resource-accounting and W13/W14 networking limitations remain open.

## Registry-vsock decision (Mac resumed 2026-11-23)

The candidate is `campaign/build-mirror-vsock-b5ec34b` (`279809e`): merge
`7307888`'s production diff reapplied on `e07eeb8`. Its `relay.rs` and
`agent.rs` are byte-identical to `d370e8c`, so the earlier selection,
forced-fallback, mixed-version and restoration receipts still apply to the
dial. The signed candidate host is `fb8d65ea…0813d` and its initramfs
`e70c8084…6b0a2`. It uses the same kernel and disk template.

Harness `c567992` adds `runner.py baseline --candidate-checkout DIR`. Slot b
runs the other checkout's signed host and guest assets in a clone of the warm
engine, and every slot-b trial records that build's hashes. Each cohort ran
ten pairs, installed-default, with `--pair-quiet-load 4.0 --max-pairs 16`.
Ratios are candidate / baseline `main`:

| Cohort | Correct | Result |
| --- | --- | --- |
| Admission `base-20261123T093237-6e4d` (1 pair) | 2/2 | candidate 0 NAT connections, baseline 133 |
| W7 `base-20261123T093409-2133` | 20/20 | Every build and first-use cell non-inferior, none ≤ 0.95: Hyperfine uncached 1.003 [0.994, 1.007], warm 0.963 [0.925, 1.010], incremental 0.972 [0.932, 1.006]; HTTPie uncached 1.003 [0.998, 1.010], warm 0.981 [0.953, 1.024], incremental 0.989 [0.975, 1.007]. Footprint 1.007 [0.993, 1.017]; measured CPU 1.003 [0.991, 1.011]. |
| W6 `base-20261123T094441-1c01` | 20/20 | Rust 1.002 [0.993, 1.007]; zlib 0.994 [0.916, 1.019]. Footprint 1.000 [1.000, 1.003]; CPU 1.001 [0.993, 1.014]. The candidate made 0 NAT connections per leg; baseline made 69–71. |

Raw `trials.jsonl` SHA-256: admission `9d624905…6c6e`, W7 `dc122cad…1fff`,
W6 `0a3b0764…0c16`.

The stop rule written before the Mac resumed required a W7 strict win. W7
was non-inferior with no win. Because the candidate was originally a W6
hypothesis, I amended the rule **before running W6**: a strict W6 primary
win with W7 non-inferior would promote it. W6 showed no win either.
**Decision: not promoted.** The candidate stays parked on its branch.
Moving build-registry traffic off NAT makes ctrs CPU accounting complete for
those connections but saves no measurable build time. Do not retry without a
new causal profile.

## Mac remeasurement at `b5ec34b`

These are installed-default cohorts against OrbStack 2.2.5 at nine vCPUs,
run with `pyramid.py run --name w1-stack:cohort --name w6-build:cohort --name
w7-buildx:cohort --name w8-pull-installed-default:cohort`. They replace the
older-binary standing for these cells only. Every pair was correct and
admitted (10/10 each). Ratios are ctrs/OrbStack, paired median [95% CI].
CPU is incomplete in all four because host NAT CPU is not charged to ctrs.

| Cohort | Timing | Footprint | Measured CPU |
| --- | --- | --- | --- |
| W1 warm stack `base-20261123T105610-7ad5` | health 0.894 [0.855, 0.916]; DB restart to verified 0.705 [0.675, 0.712] | 0.167 [0.166, 0.168] | 0.412 |
| W6 `base-20261123T105954-4112` | Rust 0.919 [0.898, 0.936]; zlib 0.476 [0.470, 0.585] | 0.402 [0.363, 0.412] | 0.858 |
| W7 (`w7-v5-offline-builds`) `base-20261123T111822-1e50` | all 12 build and first-use cells are strict wins; uncached builds: Hyperfine 0.869, HTTPie 0.738; HTTPie uncached first use 0.441 | 0.452 [0.371, 0.463] | 0.512 |
| W8 installed-default derived `w8-paired-f095671144de` | pull to health 0.389 [0.368, 0.400] | 0.197 [0.194, 0.200] | 0.137 |

The earlier W6 uncached-build footprint loss (1.364×, older binary) did not
reproduce. The cause is unattributed: this build adds H3's guest gzip
backend, and its store state and sampling differ from the old cohort.

These are still pilot cells, not qualified ones. Each needs an independent
confirmation batch and complete NAT CPU accounting.

Raw SHA-256:

- W1 `cf5d51c3…44ef`
- W6 `66923548…adc3`
- W7 `a66d453b…00e9c`
- W8 `62847c9e…0790`
- pyramid summary `cd703973…aa43`

## W12 full-bind: the next intervention boundary

These probes ran on `b5ec34b` in a scratch engine. They are diagnostics, not
cohorts.

- Native APFS on this Mac, single-threaded C over 92,306 files: 58–60 µs per
  create+write+close and about 1.5 µs per stat, hit or miss.
- The VZ virtiofs devices negotiate only `INDIRECT_DESC`, `EVENT_IDX` and
  `VERSION_1`, with one request queue. All their interrupts land on vCPU 0.
  Guest kicks are already suppressed.
- Inside a container, 100 repeated `stat`s of an existing bind path sent 0
  FUSE requests, and 100 of a missing path sent 1. VZ's entry and attribute
  replies already allow positive and negative caching. The install's ~650k
  requests are first-touch operations; npm's 4-thread libuv pool keeps about
  4 in flight.
- Every thread in the VZ VM process ran at priority 31 during a create loop.
  The loop managed 22,341 create+write+close cycles in 8 s, about 358 µs per
  file against 59 µs natively.
- The earlier trace measured submit→retrieve p50 of 182 / 142 / 128 µs for
  CREATE / WRITE / LOOKUP, with 0.501 s of worker dispatch.

So about 125 µs of every request is Apple's virtiofs service, not
filesystem work or guest dispatch. Caching, kick suppression, thread
priority, notification suppression (≤ 1.33 s) and a second device (rejected)
have been checked or tried, and VZ's API offers no queue count or server
options. What remains in ctrs's control is a ctrs-owned bind transport.

Containers cannot open `AF_VSOCK`, so raw vsock round-trip time is
unmeasured. The container → `host.docker.internal` relay path measured
p50 142 µs (Mac Python loopback alone: 28 µs). That path is not faster
than VZ.

**Vsock probe, measured.** Diagnostic host `46bcf12` on
`diagnostic/vsock-rtt` (signed `c55c8d16…61f8`) times host↔agent `Ping`/`Pong`
over VZ vsock after 1,000 warmup rounds, with `CTRS_DIAG_PING=20000`. Over
20,000 rounds: p50 49.5 µs, p95 62.0 µs, p99 78.3 µs, min 27.5 µs.

**Stop rule:** prototype FUSE-over-vsock for bind mounts behind a flag only if
the p50 round trip plus native operation cost is at most half of VZ's
per-request latency (≤ 65 µs for a LOOKUP). Then run one ten-pair full-bind
comparison against current `main`. Promote at a workflow upper bound ≤ 0.95
with exact outputs, watcher correctness and the Fsync contract intact.
If the probe misses that bound, record W12 full-bind as a VZ-bound loss
(1.30×) and move to the next ranked matrix deficit.

**Outcome.** 49.5 µs + about 1.5 µs of native lookup meets the ≤ 65 µs
arithmetic. The probe leaves out the hop through a guest FUSE daemon (an
estimated 10–20 µs) and VZ's concurrency, so the margin is thin. The estimated
gain is about half of each bind request's latency, at most the install plus
verification gap. That would move the workflow from 1.30× toward about
1.15×, which is still a loss.

The prototype is a ctrs-owned host file server on the guest boundary: a
multi-week architecture change needing security and semantics review. It is
**handed to the owner as a design decision** (see the
[Linux handoff](../linux-handoff-2026-11-23.md)), not started here.

**Owner decision, 2026-11-23: parked.** FUSE is tricky. W12 full-bind stays
a recorded VZ-bound loss, and `diagnostic/vsock-rtt` stays unmerged.

## Open items this session could not do

- Copy `/home/ubuntu/ctrs-evidence/` off the Linux VM and verify the committed
  manifests before retiring it. No host or credentials for that machine are
  configured here.
- Run the integrated Linux runtime suite and `tests/layer-expansion.sh` (with
  `CTRS_LAYER_ROOT`) on a Linux host at `b5ec34b`.
