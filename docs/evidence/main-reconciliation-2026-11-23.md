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

  It needs 12 GiB free on the engine disk. **It has not been run.** The Mac is
  paused, and no Linux host is reachable from this session.

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
| `tests/layer-expansion.sh`, `conformance/smoke.sh`, `tests/e2e.sh`, watch and inode tests | **not run**: Mac host work is paused |
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

## Next decision and stopping rule

When Mac host work resumes, the one next optimization decision is the
already-declared **registry-vsock candidate**:

1. Rebase `campaign/build-mirror-vsock` onto this `main` and rebuild the host
   and initramfs.
2. Reuse the selection, fallback, mixed-version and restoration receipts only
   if `relay.rs` and `agent.rs` around the dial are unchanged by the rebase.
   Otherwise rerun the zlib routing control once.
3. With at least 32 GiB free, run one fresh full W7 comparison (ten alternating
   pairs of baseline `main` and the candidate, against frozen OrbStack). Then
   run full W6.

**Stop rule:**

- Promote only if the default-build W7 primary cells improve on baseline
  `main` with a paired upper bound ≤ 0.95. W6, W1 cold start and the fallback
  must stay within their existing budgets (≤ 1.03), with exact artifacts.
- Otherwise record the result and leave the candidate parked. Do not retry
  without a new causal profile.

After that decision, W12 full-bind gets one declared intervention. It targets
the host-service and device-notification part of the virtiofs round trip:
130–182 µs p50 per request, with all nine vCPUs on one request queue and only
0.501 s of the 26.80 s install in completion-worker dispatch. Mixed and
all-volume layouts are at parity, so the ceiling for any bind-path change is
the install-plus-verification gap, about 71% of the 26.7 s workflow gap.

Stop rule: ten alternating full-bind pairs against the current `main`, with
exact installed contents and outputs, watcher correctness and the Fsync
contract unchanged. Promote at a paired workflow upper bound ≤ 0.95;
otherwise revert and record. Keep the result separate from the volume-layout
cells.

## Open items this session could not do

- Copy `/home/ubuntu/ctrs-evidence/` off the Linux VM and verify the committed
  manifests before retiring it. No host or credentials for that machine are
  configured here.
- Run the integrated Linux runtime suite and `tests/layer-expansion.sh` at
  `b5ec34b`. This needs that Linux host, or the Mac once it is resumed.
