# Roadmap

This is the single plan for this repository: all current and future work, and the handoff for resuming it. Campaigns are sections below, and their items interleave in **Sequence**. "Resume the roadmap" means continue from **Status**.

## Status

- active: native performance campaign; Linux evidence preservation is the next slice.
- Last accepted source revision: `4cad4ed`. Integration was green at `b5ec34b` on Mac (smoke 21/21, e2e 509/0/0, watch recovery, inode bound and layer expansion); no later full integration result is recorded.
- All macOS performance gates remain open. W1 warm, W6, W7 and W8 were remeasured at `b5ec34b`; other cells retain their recorded binary identities.
- Registry vsock `campaign/build-mirror-vsock-b5ec34b` is parked after no strict W6/W7 win; retry with a new causal hypothesis.
- W12 full-bind transport is parked by the owner; retry only with a design addressing FUSE protocol, security and semantics or evidence of a cheaper lever.
- W11 branches `campaign/w11-bind-completed-cycles`, `campaign/w11-required-cells-20261117` and `campaign/w11-admission-20261117` are unaccepted; review, native proof, durability admission and bounded growth precede 12-hour legs.
- Full sync `campaign/np-full-sync` needs a durability decision and fresh resource confirmation. Refusal TTL candidates remain unpromoted; re-establish the baseline before retry.
- The candidate checkout and 47 older linked worktrees were preserved without a complete retirement audit; compare source and consumers before retiring any.
- Next: copy and verify Linux evidence before VM retirement, then qualify the integrated Linux runtime. Do not repeat finished Linux performance investigations.

## Sequence

| ID | Campaign | Owned files or resources | Prerequisites | Acceptance command |
| --- | --- | --- | --- | --- |
| L1 | Native performance | `/home/ubuntu/ctrs-evidence/`, durable destination | Linux host and off-host storage | Copy all evidence; run `sha256sum -c` for every committed `docs/evidence/linux-*.sha256` from its documented root. |
| L2 | Native performance | Linux runtime, `crates/ctrs-init/`, `tests/` | L1; owned Linux engine and isolated Docker | `CARGO_ENCODED_RUSTFLAGS="" cargo xtask linux --arch amd64`, `make test`, `make lint`, root `cargo test -p ctrs-init --target x86_64-unknown-linux-musl`, `tests/linux-host.sh`, `tests/kernel-features.sh`, and `tests/e2e.sh` on each owned engine. |
| L3 | Native performance | Linux layer store | L2; running ctrs | `CTRS_SOCKET=<sock> CTRS_LAYER_ROOT=/var/lib/ctrs/layers tests/layer-expansion.sh`, including zstd-refusal-cleanup. |
| W11 | Native performance | `bench/native/`, owned Mac engines | frozen cell contract, durability admission, bounded growth and review | Run one 12-hour mixed leg per engine with the finite supervisor; verify outputs, errors and growth. |
| DSLP-3 | Deslop | Rust/Python types and lint configuration | explicit campaign execution request | Complete the type profile and witnesses in [TODO-DESLOP.md](../TODO-DESLOP.md). |
| DSLP-4 | Deslop | test suites | DSLP-3 | Complete the coverage and mutation acceptance in [TODO-DESLOP.md](../TODO-DESLOP.md). |
| DSLP-5 | Deslop | repository sources | DSLP-4 | Complete the dead-code acceptance in [TODO-DESLOP.md](../TODO-DESLOP.md). |

## Campaign: Native performance

### Goal and state

Make normal headless ctrs workflows on Apple Silicon macOS meet and exceed OrbStack on the same Mac using native linux/arm64 containers. Measure correct useful work, CPU, memory, storage, recovery and reliability without weakening durability. The native linux-amd64 lane compares ctrs with dockerd separately; Linux results never close macOS gates.

The owner accepted some background noise for W2 diagnostics. Use interleaved work and observer controls, disclose activity and preserve failures. Scored measurements retain their admission and correctness rules. No full gate has passed.

### Decisions

- Production defaults are gzip loads, Cached+Fsync disk and 250 ms refusal TTL. SCHED_MC, LSE, uprobes, registry vsock, relay batching, extra virtiofs devices and readiness logging are not promoted. H3 and cache-usage fixes remain. See [reconciliation](evidence/main-reconciliation-2026-11-23.md).
- Registry vsock was non-inferior in ten-pair W6/W7 comparisons without a strict win; do not promote it.
- W12 full-bind is a recorded VZ-bound loss: workflow 1.30×, install 2.11×, verification 4.16×. Mixed and volume layouts are near parity. A sync-to-volume screen estimated 0.93–0.96× OrbStack full-bind with a native Mac writer, but docker cp back took 52 seconds. No transport was built.
- Preserve Fsync. Promoting Full requires an explicit decision and fresh storage cohorts. W3 ENOSPC recovery does not establish equivalent power-loss durability.
- Do not repeat the finished Linux W2 candidate loop, three HTTPie residual attempts, W5 observer investigation or exhausted W13 headroom configurations.

### Baseline

The Mac runtime passed at `b5ec34b`; the [reconciliation record](evidence/main-reconciliation-2026-11-23.md) identifies its artifacts and results. W1 warm, W6, W7 and W8 timing and footprint cells were strict wins in ten-pair installed-default comparisons at that revision. Prior measurements remain descriptive and belong to their recorded binaries. Host NAT CPU attribution is incomplete. W2 offered-rate trials missed pacing; W2 guest-direct CPU and W12 full-bind remain losses. W13 is tool-limited under the twofold headroom guard.

The 2026-11-20 Linux 6.18.58 guest build proof used ARM64 Image SHA-256 `f953d09d34b0f3fe5ca2fd089727ce64ee6e9942ba2c52a896a769477d7c2225` and AMD64 bzImage SHA-256 `67032e023cb67185ff1746b2ed4ab8130c76d7723c56402b4ceacaf4a5933b4e`. Build timestamps affect these hashes; this is build proof, not runtime qualification.

The Linux host baseline is Ubuntu 22.04.5, kernel 6.8.0-1060-aws and Docker 29.9.2. H3 measured C/B 0.773 [0.707, 0.786] and C/D 1.164 [1.036, 1.180]; Linux resource accounting is not macOS physical footprint. See [Linux results](evidence/linux-amd64-checkpoint-2026-11-22.md) and [integrated runtime](evidence/linux-integrated-runtime-2026-11-22.md).

### Acceptance

Freeze inputs, workloads, resource budgets and statistical procedures before optimization. Coverage requires W1–W10 exact work and outputs on both engines. Parity requires every critical timing, tail, CPU, physical-memory and allocated-storage cell to have paired 95% upper confidence bound ≤1.03, plus correctness and recovery. Leadership requires the equal-family W1–W10 primary geometric mean upper bound ≤0.90, strict ≥5% improvements in default W6 and W7 and two of W1/W2/W5/W8, without hiding a losing critical cell. W11 requires 12 hours per engine with no unexplained deaths or errors, correct durable data and bounded growth. A fresh signed release, isolated roots and independent held-out workload must reproduce the result. Unknown cells are unqualified.

#### Workloads and metrics

Retain W IDs for traceability. Changed inputs, assertions, cache semantics
or metrics start a new fixture/baseline version; never pool history.
Current proxies remain pilots until upgraded.

| ID | Complete user task | Primary outcomes and integrity |
| --- | --- | --- |
| W1 | Compose up API + Postgres + Redis | Command-to-health and verified read/write; persisted data after restart; startup failures |
| W2 | API reads/writes at fixed offered load and saturation | Successful requests/s; end-user p50/p95/p99; exact accepted records; published-port and container-to-container paths |
| W3 | Migrate/seed database, transact, checkpoint, restart | Fixed successful transactions/s, p95, recovery, exact data and allocated bytes; equivalent durability |
| W4 | API ingest → queue → 1/4/16 real workers → artifacts | Fixed batch completion, queue tails, no lost/duplicate outputs; shell hashing is diagnostic only |
| W5 | Edit → watch/rebuild → test a pinned upstream TS/JS app | Host-bind and named-volume latency separately; real dependencies, change propagation, tests/checksums |
| W6 | Compile/test/package a pinned Rust app plus another language | Clean/warm CI duration, successful tests and equivalent artifacts; CPU/memory; clean trials actually compile |
| W7 | Default buildx → loaded runnable images for two real apps | Uncached/warm/one-file incremental completion; contents and behavior; export/import/first-use included |
| W8 | Deploy identical multi-layer images from independent local registry | Pull-to-healthy including guest install; digests; app latency under load; cancellation/cleanup |
| W9 | 1/4/8/16 parallel real fixed-work build/test jobs as capacity allows | Valid jobs/min, p95 completion, artifacts, networks/volumes, logs, teardown/leaks; no timed busy loop |
| W10 | Interrupt/recover real service/database/queue work | Verified recovery, exact committed data, retries, recovered p99, cleanup; errors are not throughput |
| W11 | 12-hour mixed app/DB/queue/build/teardown qualification | No unexplained deaths/errors; complete outputs; memory/FD/disk trends; no raw churn-count speed claim |

Collect total engine CPU-seconds per unit of successful work, peak/steady
physical footprint, idle CPU/footprint and allocated storage where
meaningful. Count daemon, VM/VZ helper, guest, managed builder and owned
services. Add startup, idle wake, shutdown and reclaim-to-next-use cells;
do not trade a smaller idle screenshot for slower next-use.

`collect.py` uses native proc_pid_rusage CPU, actual ri_phys_footprint and kernel
start identity with explicit required-process coverage. Socket and dedicated VM
disk ownership plus unchanged open executable/boot assets identify the running
engine; build outputs alone do not. The subprocess sampler failed overhead
calibration and is retired from scored sampling. Native v3 passed short median
observer budgets on both engines; noisy individual pairs require stronger final
qualification. Historical resource wins remain superseded. Freeze numerical
idle/reclamation/storage/growth budgets before candidate selection.

#### Measurement rules

- **Pin and enforce inputs.** Parse `cases.toml` and `assets.lock` before
  work; the latter remains pilot until digest/source/dataset/tool locks
  are enforced. Record host/OS, power/thermal/load state, actual image
  architecture, OrbStack/config, CLI/Compose/buildx/BuildKit versions,
  source and executable hashes, guest assets, fixture hash, cache state,
  workload parameters and sampler version. Identify the actual running
  binary, including adopted daemons; HEAD alone is insufficient.
- **Separate the lanes.** Primary = normal installed/default user
  experience, with configuration disclosed. Controlled = equal resources
  and pinned identical BuildKit/driver to attribute costs. Neither lane
  substitutes for the other. Default W6/W7 losses remain red when the
  docker-container control wins. Do not credit BuildKit version changes
  to ctrs. An upgrade after freeze starts a new comparison version.
- **Same work and state.** Paired trials share seeds, bytes, requested
  load and cache semantics. Alternate AB/BA or use balanced randomized
  order. Cache-busting identity differs between pairs, not A/B engines.
  Assert clean build steps executed and warm reuse is correct. Use one
  identical multi-layer portfolio and independent local registry. WAN
  timing and independent per-engine rebuilds do not qualify.
- **Preserve user state.** Dedicated ctrs roots/sockets; unique owned
  containers/networks/volumes/builders/ports; explicit Docker endpoint;
  verified builder endpoint. No global image/build/system prune, context
  changes, shared-daemon restart, user container stop, or security/privacy
  changes. Cleanup verifies ownership, not merely an `np*` prefix.
  `--no-cache` measures uncached work, not an empty store or cold engine.
  Unavailable equivalent cold states remain missing.
- **Exclusive measurements.** Capture then stop only identified
  campaign-owned watch/churn jobs before scoring; never run them with
  W11. Quiesce campaign-owned non-tested load. User activity invalidates
  affected pairs or requires another window; do not kill it. Idle
  resident engines require a frozen policy that measures background
  activity and prevents cross-attribution. Never rebuild or replace a
  binary/asset underneath a running trial or soak.
- **Correctness first.** Nonzero exits, malformed/missing summaries,
  mismatched inputs, duplicate/incomplete pairs and integrity failures
  remain visible; failed runs exit nonzero. They cannot produce favorable
  ratios. Preserve failure counts and coverage denominators. Errors are
  not throughput; missing resources are not zero. Planned W10 outage
  errors must be distinguished from unexpected errors/recovery failures.
- **Consistent statistics.** Three pairs are pilots. Require at least
  ten valid complete pairs per qualified cell, identified by run and
  configuration plus pair ID. Display the median paired ratio and 95%
  bootstrap interval of that same median over whole pairs. Strict win:
  upper bound ≤0.95. Non-inferior: upper bound ≤1.03. Loss: lower bound
  >1.03, or a hard correctness failure. Otherwise inconclusive. Failure
  to show significance is not proof of parity. W11 has a separate
  reliability gate, not an ordinary ten-pair speed requirement.
- **No selection bias.** Freeze counts, invalidation rules, primary
  metrics and equal family weights before tuning. In the reviewed
  `cell_contract`, mark the selected application or recovery cells with
  `"primary_performance": true` for each W1–W10 family. The frozen digest
  covers the markers. Confirm selected changes with fresh independent
  batches. For family/aggregate CIs,
  resample whole paired batches, preserving related-metric dependence.
  Never average away a loss. If a holdout failure guides tuning, retire
  it as a holdout and freeze a fresh independent case for confirmation.

The corrected reporter is a descriptive audit aid, not an implementation
of every qualification gate above. A “strict win” statistical label does
not establish representative inputs, durability or physical accounting.


#### Finite reliability jobs and continuation

Short pilots unblock development. Full 12-hour-per-engine W11 belongs
once a candidate is frozen for qualification. A job has a run ID, binary/
input hashes, PID/start identity, fixed start/deadline, logs, results and
saved exit status. Preserve exit codes; never pipe launches through
`tail` and confuse an empty log with a running job. Do not extend/restart
a healthy soak just to fill turns. Rerun for a demonstrated failure or
an explicitly new candidate's qualification.

The [finite native supervisor](../bench/native/diagnostics/durable-job.md) now
provides at-most-once claiming, frozen input receipts, native process identity,
fixed deadlines and durable terminal status. The caller must enforce the freeze
gates and run persistent representative cycles; short subprocess tests do not
qualify W11. Missing status is indeterminate and never authorizes automatic retry.

While W11 owns the Mac, do review, source/fixture work or implementation
on noncontending resources without changing the job's binary/assets.
If nothing independent remains, wait for its completion event/deadline
through the execution harness instead of spending model turns polling.
Record one outcome, close the job and take the next queue item. A watch
that survived its finite budget is finished; more `alpine true` churn
cannot improve this scorecard.


### Needs environment

- W1 engine-cold and W10 whole-engine recovery require a disposable OrbStack endpoint. W11 requires admission before its two 12-hour legs. The shared endpoint remains with its users.
- W3 requires equivalent power-loss durability evidence. Host NAT work remains unattributed. W13 needs a tool with adequate headroom. An independent holdout remains open.
- Restore the pinned [W8 portfolio](../bench/native/fixtures/w8-v6/README.md) and prepare [W12](../bench/native/fixtures/w12/README.md) before their cohorts.

#### Linux tasks, in order

The host is the existing native x86_64 lane machine: Ubuntu 22.04.5, kernel
`6.8.0-1060-aws`, Docker 29.9.2 (frozen). Its evidence roots live under
`/home/ubuntu/ctrs-evidence/`.

1. **Copy the retained evidence off the VM before retiring it.** Copy every
   directory under `/home/ubuntu/ctrs-evidence/` to durable off-host storage,
   for example `rsync -a ubuntu@HOST:/home/ubuntu/ctrs-evidence/ <dest>/`.
   Then, at the destination, run `sha256sum -c` against each committed
   manifest in `docs/evidence/linux-*.sha256`, using the relative paths the
   manifests expect. Each evidence doc gives its own manifest's root. Record
   the destination, the file count and the verification output in a short
   addendum to this file. Do not build another preservation framework.
2. **Build the integrated runtime at current `main`.**
   `./scripts/setup-dev`, then `CARGO_ENCODED_RUSTFLAGS="" cargo xtask linux
   --arch amd64`. Record the SHA-256 of `target/linux-x86_64/release/ctrs` and
   `ctrs-init`. Run `make test` and `make lint`. As root, run
   `cargo test -p ctrs-init --target x86_64-unknown-linux-musl`; it must
   include the three new `layers::tests` compressible-layer regressions.
3. **Run the integrated Linux runtime suite in owned, disposable state.**
   Repeat the procedure in
   [linux-integrated-runtime-2026-11-22.md](evidence/linux-integrated-runtime-2026-11-22.md),
   using `~/ctrs-evidence/linux-integrated-20261122/restore-owned.sh`:
   - start ctrs through `bench/native/linux/ctrs-engine.sh start`;
   - run the isolated Docker daemon in a private netns, with its own
     containerd, roots and socket, and no default bridge;
   - run `tests/linux-host.sh` and `tests/kernel-features.sh` in a privileged
     container;
   - run `tests/e2e.sh` against each engine.

   Do not start, stop or reconfigure the host's `docker.service`. Compare with
   the `65b7bbd` result (ctrs 482/1/26, Docker 471/2/30). Classify each
   failure with evidence, as before (host VRF module, Docker's AppArmor mount
   denial). Report nonzero exits as nonzero.
4. **Run the compression regression on a Linux host.** With ctrs running:
   `CTRS_SOCKET=<sock> CTRS_LAYER_ROOT=/var/lib/ctrs/layers
   tests/layer-expansion.sh`. That is the host lane's layer store; read it as
   root. The `zstd-refusal-cleanup` check that the Mac had to skip must pass
   here.
5. **Linux lane performance: nothing more is queued.** H3 stays at C/B 0.773
   [0.707, 0.786] and is still C/D 1.164 [1.036, 1.180] against Docker.
   - Do not restart these finished investigations:
     - the W2 candidate loop;
     - the three rejected HTTPie residual attempts;
     - W5's observer/cadence investigation;
     - exhausted W13 headroom configurations.
   - The W3, W12, resource-accounting and networking limitations stay open
     and stated.
   - Registry vsock, relay-batch and the readiness logging landed after the
     2026-11-22 Linux cohorts and are reverted again, so the Linux runtime
     matches what H3 measured. The one exception is the boxed `decoded()`
     reader in the layer install path. A one-cohort HTTPie first-use check at
     the new SHA is optional, not required.
6. Record results in the relevant dated evidence and update this roadmap.


### Execution boundary and non-goals

Use dedicated owned roots, sockets, containers and builders. Do not touch shared daemon configuration or Docker contexts. Do not pool Linux and macOS samples. No UI, Kubernetes, remote control plane, WSL, emulation, cross-ISA builds or VMM rewrite without a demonstrated application bottleneck. Production defaults follow decisions, not branch-retirement merges.

### Reference

[Benchmark harness](../bench/native/README.md), [performance evidence](evidence/native-performance.md), [decisions](decisions.md), [W12 and W13 evidence](evidence/native-w12-w13-2026-11-18.md), [reconciliation](evidence/main-reconciliation-2026-11-23.md), and [TODO.md](../TODO.md). Historical progress and raw artifacts that were deleted require remeasurement; Git retains the earlier written record.

#### Existing workloads

D is installed-default and M is the resource-matched control. These rows describe their recorded binaries; the newer `b5ec34b` measurements and open qualification limits are in Baseline above. No cell is qualified.

| ID | Workflow | Spec | Impl | Functional (this host) | Compared (this host) | Critical result (this host) |
| --- | --- | --- | --- | --- | --- | --- |
| W1 | Compose up API+PG+Redis, restart | yes | yes | yes, warm v3 on both engines and a cold ctrs admission | D: `base-20261122T093654-6f3a` (10/10 warm pairs) | Verified restart 0.686× [0.675, 0.698], initial roundtrip 0.848× [0.719, 0.912], and footprint 0.419× [0.387, 0.429] were strict wins. CPU accounting is incomplete due to host NAT. Equivalent engine-cold comparison remains open. |
| W2 | API fixed work, published port | yes | yes | yes (both lanes) | D: `base-20261123T034853-15d4` (10/10 pairs, 50,000 requests, both engines 9 vCPUs) | **Measured CPU per request loss** 1.2881× [1.2701, 1.2956] before uncharged host NAT. p99 0.6264× [0.6183, 0.6338], request rate 0.7510× [0.7469, 0.7571] and footprint 0.1461× [0.1449, 0.1486] were strict wins. At one client, CPU/request was 0.3915× [0.3765, 0.4155] in ten admitted pairs, with host NAT CPU uncharged.. At four clients, CPU/request was 1.4620× [1.4276, 1.4726] before uncharged NAT in ten admitted pairs.. At 16 clients, ten admitted pairs still showed a measured CPU/request loss of 1.1529× [1.1393, 1.1583] before uncharged NAT. · [Historical comparisons](evidence/native-w2-ipi-2026-11-18.md) |
| W2 | API fixed work, container-to-container | yes | yes | yes (installed defaults) | D: `base-20261123T033422-bb7b` (10/10 pairs, 50,000 requests, both engines 9 vCPUs) | **Measured CPU per request loss** 1.1162× [1.1056, 1.1244] with zero ctrs host NAT connections and both guest load clients included. p99 0.4428× [0.4375, 0.4454], request rate 0.5652× [0.5556, 0.5695] and footprint 0.1538× [0.1500, 0.1554] were strict wins in this cohort. At one client, CPU/request was a strict win at 0.8464× [0.8338, 0.8538] in ten admitted pairs.. At four clients, the CPU/request ratio was 1.1900× [1.1786, 1.2035] in ten admitted pairs.. At 16 clients, ten admitted pairs still showed a CPU/request loss of 1.0560× [1.0517, 1.0628]. |
| W2 | API saturation, published port at 1 client | yes | yes | yes, exact persisted writes and zero request errors | D: `base-20261123T020744-c034` (10/10 pairs) | Throughput ratio 0.2852× [0.2779, 0.2963], p99 0.1403× [0.1329, 0.1413] and sampled footprint 0.1520× [0.1511, 0.1529]. Measured CPU per success 0.3781× [0.3733, 0.3997] remains incomplete before charging host NAT CPU. |
| W2 | API saturation, container-to-container at 1 client | yes | yes | yes, exact persisted writes and zero request errors | D: `base-20261123T015720-c637` (10/10 pairs) | Throughput ratio 0.4367× [0.4292, 0.4423], p99 0.2276× [0.2240, 0.2401] and sampled footprint 0.1531× [0.1504, 0.1548]. Measured CPU per success was a strict win at 0.8282× [0.8138, 0.8415] with zero ctrs host NAT connections. |
| W2 | API saturation, published port at 4 clients | yes | yes | yes, exact persisted writes and zero request errors | D: `base-20261123T014658-81a6` (10/10 pairs) | Throughput ratio 0.7586× [0.7558, 0.7655], p99 0.5400× [0.5310, 0.5494] and sampled footprint 0.1513× [0.1493, 0.1544]. Measured CPU per success lost at 1.4543× [1.4454, 1.4691] before uncharged host NAT CPU. |
| W2 | API saturation, container-to-container at 4 clients | yes | yes | yes, exact persisted writes and zero request errors | D: `base-20261123T013630-f6a6` (10/10 pairs) | Throughput ratio 0.5669× [0.5482, 0.5751], p99 0.3680× [0.3622, 0.3762] and sampled footprint 0.1524× [0.1502, 0.1544]. CPU per success lost at 1.1817× [1.1612, 1.1973] with zero ctrs host NAT connections. |
| W2 | API saturation, published port at 8 clients | yes | yes | yes, exact persisted writes and zero request errors | D: `base-20261123T012518-8a0d` (10/10 pairs) | Throughput ratio 0.7446× [0.7395, 0.7496], p99 0.6234× [0.6120, 0.6299] and sampled footprint 0.1500× [0.1484, 0.1513]. Measured CPU per success lost at 1.2752× [1.2565, 1.2862] before uncharged host NAT CPU. |
| W2 | API saturation, container-to-container at 8 clients | yes | yes | yes, exact persisted writes and zero request errors | D: `base-20261123T011451-df53` (10/10 pairs) | Throughput ratio 0.5709× [0.5576, 0.5770], p99 0.4520× [0.4378, 0.4574] and sampled footprint 0.1521× [0.1494, 0.1554]. CPU per success lost at 1.1189× [1.0899, 1.1363] with zero ctrs host NAT connections. |
| W2 | API saturation, published port at 16 clients | yes | yes | yes, exact persisted writes and zero request errors | D: `base-20261123T010350-c7eb` (10/10 pairs) | Throughput ratio 0.6928× [0.6892, 0.6972], p99 0.5400× [0.5312, 0.5551] and sampled footprint 0.1504× [0.1496, 0.1529]. Measured CPU per success lost at 1.1248× [1.1154, 1.1483] before uncharged host NAT CPU. |
| W2 | API saturation, container-to-container at 16 clients | yes | yes | yes, exact persisted writes and zero request errors | D: `base-20261123T005321-6ac0` (10/10 pairs) | Throughput ratio 0.5554× [0.5497, 0.5606], p99 0.3959× [0.3926, 0.4054] and sampled footprint 0.1553× [0.1529, 0.1563]. CPU per success is inconclusive at 1.0265× [1.0189, 1.0449] with zero ctrs host NAT connections. |
| W2 | API fixed offered rate, published port | yes | yes | ctrs passed, OrbStack missed scheduled slots | D: `base-20261122T093101-7063` (0/2 valid pairs) | Both engines completed 10,000 exact requests in each leg. The OrbStack legs exceeded the 10 ms start-lag budget on 53 and 41 slots. The stop rule fired and timing comparisons remain unmeasured. |
| W2 | API fixed offered rate, container-to-container | yes | yes | both engines missed scheduled slots | D: `base-20261122T093306-1b10` (0/2 valid pairs) | Both engines completed 10,000 exact requests in each leg. OrbStack had 8 and 19 late slots, and ctrs had 0 and 1. All 28 had an in-flight predecessor at the lateness deadline. The stop rule fired and timing comparisons remain unmeasured. |
| W3 | PG transactions, checkpoint, restart | yes | yes | yes, exact 300 transactions per leg | D: `base-20261122T130640-24d2` (10/10 pairs) | Commit p95 0.069× [0.061, 0.082] and engine CPU per transaction 0.145× [0.135, 0.168] are durability-unverified. Restart timing is inconclusive. Both ctrs sync modes recovered exact data after guest relation ENOSPC and backing-file allocation failure on a private host APFS volume. Equivalent host durability remains open. |
| W4 | Queue workers 1/4/16 | yes | yes | yes, 12,000 exact jobs and 24,000 artifacts across both engines | D: `base-20261122T143625-9f92` and `w4-confirmation-2ce01ca3` (10/10 pairs each) | Both runs cleared the descriptive strict-win bounds for worker phase time, queue p95/p99, CPU per job and sampled footprint at all three worker counts. The repeat used the same source and a different executable hash. Exact-binary confirmation and isolated OrbStack footprint remain open. |
| W5 | Marked esbuild watch (bind, volume) | yes | yes | yes, 2,400 exact edit results per cohort | D: `base-20261122T123236-7047` and `w5-confirmation-2fe3db15` (10/10 pairs each, 60 edits per mount) | Both runs found non-inferior edit p50 and p95 and strict wins in setup and sampled footprint on both mounts. CPU per edit was non-inferior on bind and a strict win on volume. The repeat used the original signed executable on a separate ctrs store and shared OrbStack. Isolated OrbStack footprint and fresh signed release confirmation remain open. |
| W6 | Default-builder Rust+C CI build | yes | yes | yes | D: uncached `base-20261122T063709-0627` and primed `base-20261122T102417-474d` (10/10 pairs each, both engines 9 vCPUs) | Uncached physical footprint loss 1.364× [1.182, 1.485], Rust 0.944× non-inferior, zlib 0.524× strict win. Primed cached build and load strict wins for both applications, Rust 0.476× [0.448, 0.483] and zlib 0.448× [0.446, 0.461]; primed physical footprint inconclusive at 1.152× [0.949, 1.288]. CPU accounting is incomplete due to host NAT. The independent 5,632 MiB repeat reproduced the footprint reduction, but zlib missed the timing bound. |
| W7 | Default buildx → loaded images | yes | yes | yes, exact runtime receipts across engines and cache states | D: network-resolved `base-20261122T170828-8009` and offline `base-20261122T172448-ffd0` (10/10 each) | All 12 timing cells cleared the descriptive strict-win threshold in both cohorts. Offline uncached Hyperfine 0.883× [0.867, 0.897], HTTPie 0.793× [0.779, 0.804], sampled footprint 0.599× [0.563, 0.613]. Build CPU still lacks host NAT accounting. The vsock diagnostic passed the exact offline cells with zero recorded NAT connections. A subsequent OrbStack comparison stopped at the disk floor after six complete pairs. Separately, identical imported HTTPie first-use time was 0.848× [0.827, 0.876] across ten pairs. |
| W8 | Pull-to-healthy from local registry (w8-v6 portfolio) | yes | yes | yes, both engines and content states, with and without API load | D and M: ten complete pairs per content and load condition in each lane | No-load pull-to-health was 0.546× [0.505, 0.549] retained and 0.433× [0.420, 0.464] derived. Under load it was 0.453× [0.419, 0.460] in the corrected retained repeat and 0.414× [0.384, 0.430] derived. Matched pull-to-health upper bounds ranged from 0.356× to 0.593× across four controls. Derived-load p99 remains inconclusive. Host NAT CPU was uncharged. |
| W9 | Parallel fixed build/test jobs | yes | yes | yes, all four concurrency levels on both engines | D: `base-20261122T101434-f89b` and `w9-confirmation-c30e65e8` (10/10 pairs each) | The rebuilt release reproduced the strict-win direction for batch time, p95, CPU per job and sampled footprint at all four concurrencies. At 16 workers, the repeat batch-time ratio was 0.206× [0.196, 0.214]. OrbStack used a shared endpoint and its resident footprint changed between cohorts. |
| W10 | Interrupt/recover service/DB/queue | yes | yes | yes, exact API/DB/queue and owned ctrs engine recovery | D: API, database and queue (10/10 pairs each) | API recovery loss 1.239× [1.195, 1.315], DB recovery strict win 0.342× [0.301, 0.415], queue recovery strict win 0.451× [0.438, 0.459]. Recovered p99 and sampled footprint cleared the strict-win threshold in all three conditions. Measured CPU/success lost at 1.167× for API and 1.302× for database. Queue CPU/job cleared the strict-win threshold at 0.521× [0.513, 0.553]. Whole-engine parity needs isolated OrbStack. |
| W11 | 12 h mixed reliability | yes | yes, v5 worker and v6 portfolio | yes, short runs with 12 exact ctrs cycles and 11 exact OrbStack cycles | n/a | ctrs exceeded the short footprint and active-backing growth budgets. OrbStack exceeded the backing budget twice, with a recurring cycle-eight jump confirmed in APFS private bytes. OrbStack exceeded the footprint budget in the first run and passed it in the repeat. Uncached disk with online discard and explicit trim still exceeded both growth budgets. Durability admission and both 12-hour legs remain open. |

The installed-default W2 saturation grid has ten admitted pairs at each of
1, 4, 8 and 16 clients on both paths. The independent raw audit matched
1,504,565 acknowledged writes to persisted rows across 5,009,975
successful requests. Both fixed offered-rate cells still need admitted
cohorts.

The installed-default fixed-work grid has ten admitted pairs at each of
1, 4, 8 and 16 clients on both paths using signed release `99db1aa`.
All 160 legs matched their engine's executable identities and the shared
API, portfolio, SQL seed and client pins. All ctrs legs matched the guest
boot assets. The raw
equal-work audit verified 8,000,000 requests and 2,403,504 acknowledged
writes with zero errors. The eight-client cohorts from the earlier
`5cac40d` runtime remain separate historical evidence.

#### Filesystem and networking coverage (2026-11-18 steering)

W12 v2 full-bind completed ten installed-default pairs on 2026-11-22.
The workflow ratio was 1.2999 [1.2883, 1.3223], with measured CPU at
1.1630 [1.1593, 1.1725] and sampled physical footprint at 0.3606
[0.3455, 0.3871]. The v2 mixed-layout cohort also completed ten pairs.
The workflow was non-inferior at 0.9990 [0.9887, 1.0026], with an
inconclusive install interval and a strict footprint win. The ten-pair
v2 all-volume cohort had non-inferior workflow time at 0.9915
[0.9880, 0.9986] and non-inferior CPU, with a strict footprint win.
Both watch cohorts are complete.
The upgraded mixed-layout receipt passed a native admission pair with
all four exact build outputs and both discovered tests.
The table retains W12 timing history from the previous workspace fixture.

| ID | Workflow | Spec | Impl | Functional | Compared | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| W12 | Shared workspace (Kutt v2.7.4, 2,830 packages, 92,306 files, 532 MB): offline install, build, typecheck, Jest discovery, rebuild, edit and branch restore | yes | yes (`w12-v2`) | yes, all three layouts on the signed release | D: 10/10 pairs per layout | Critical full-bind loss. Workflow ratio 1.2999 [1.2883, 1.3223], offline install 2.1055 [2.0701, 2.1621], and install verification 4.1610 [4.0605, 4.5087]. Mixed workflow 0.9990 [0.9887, 1.0026] and all-volume 0.9915 [0.9880, 0.9986] were non-inferior. The full-bind install verifier issued 91,875 birth-time stat requests in one traced leg. Missing-path lookups during install mostly overlapped other FUSE requests. · [Earlier experiments](evidence/native-w12-w13-2026-11-18.md) |
| W12-watch bind | `tsc --watch` (fs.watch backend), host-side edits including atomic replaces and five-file bursts | yes | yes (`w12-watch-v4`) | yes, 120 exact results per leg | D: `base-20261122T131311-6799` (10/10 pairs) | **Whole-trial engine CPU loss** 1.186× [1.170, 1.215]. Offline install accounted for most of the extra setup CPU in a two-pair breakdown. Edit p50 0.881× [0.838, 0.931] strict win, p95 0.971× [0.939, 1.026] non-inferior, sampled footprint 0.269× strict win. |
| W12-watch volume | Same edit plan with `docker exec` edits to a named volume | yes | yes (`w12-watch-volume-v2`) | yes, 120 exact results per leg | D: `base-20261122T135713-1c0c` (10/10 pairs) | Descriptive strict wins in edit p50 0.725× [0.705, 0.767], edit p95 0.763× [0.716, 0.805], measured engine CPU 0.859× [0.843, 0.877], and sampled physical footprint 0.287× [0.281, 0.325]. |
| W13 | Artifact transfer up/down: published port, container↔container, container→Mac; 1 and 4 streams; byte-exact receivers | yes | yes (`w13-v2`) | yes | D: seven cells; M: published-port upload; rx64 (patch 0005): three host→guest cells | critical. **Splice build (`4fdff1d`): published-port download 0.93 [0.92, 0.94] tool-limited (was 1.64–1.78× loss), upload 0.69 tool-limited, container→Mac upload 0.95 [0.94, 0.97] tool-limited (was 2.23×); ctrs time 0.56× / 0.77× / 0.43× its previous build with OrbStack unchanged (`base-20261120T000004-f614`, `base-20261119T235251-7eb8`, `base-20261120T000743-a0eb`). Every guest→host cell is now at the tool's ceiling, so no win is claimed. Container→Mac download (Mac→container bytes) regressed to 1.21 spliced and is back to 1.06 [1.01, 1.18] inconclusive with that direction copied (`ade0b80`, `base-20261120T030035-4a43`; pre-splice 1.04).** Before: **Guest→host loss, reduced:** over the NAT relay and legs (protocol 9), container→Mac upload 2.23× (was 7.0×), published-port download 1.64× (was 5.1×); every ctrs trial records its transport (nat/nat_leg 30, vsock 0). One NAT flow caps near 1.9 GB/s here. Host→guest after patch 0005: published-port upload 1.02 (parity) over vsock; the leg-only build regressed it to 1.14×; `439b14e` (client bytes over vsock) restored 0.96 [0.85, 1.07] inconclusive, CPU/GiB 1.17× loss (`base-20261119T134339-6c08`); Mac→container 1.03 over vsock and 0.99 [0.97, 1.02] tool-limited over NAT (`base-20261119T133649-3bc7`, non-regressing, not a win), 4-stream upload 1.25 loss. Container↔container **win** 0.82 ([evidence](evidence/native-w12-w13-2026-11-18.md)). Controlled egress unsupported (no owned endpoint) |
| W13-overlap | Published-port upload alongside W2 | yes | yes (v6 portfolio, verified overlap) | yes, both engines | D: `base-20261122T073402-7351` (10/10 pairs, both engines 9 vCPUs) | **Measured CPU loss** 1.097× [1.051, 1.158] before uncharged host NAT. Footprint 0.748× [0.653, 0.782] strict win. API p50 0.975× non-inferior. API p99, request rate and transfer goodput inconclusive. The older 5-vCPU cohort recorded p99 1.70× with different image pins. |
| W14 | Connection lifecycle: fresh, persistent, streaming, cancel, idle-resume, reconnect | yes | yes | yes, exact buffered v4 results in all six modes | D: all six v4 modes (10/10 each) | Fresh p50 1.331×, p95 1.425× and CPU 1.170× lost. Persistent p95 0.829× was a strict win and cleanup 1.279× lost. Streaming p99 lateness 1.393× [1.260, 1.541] lost. Post-cancel response 0.422× was a strict win. Resume p50 and reconnect p99 were inconclusive. Host NAT CPU remains outside the counters. |
| W3-v4 | Persistent storage: meaningful dataset, sustained read/write/checkpoint, declared working set and durability | yes | yes (pgbench fixed work) | no | D: `base-20261119T170441-5abe` (10/10 pairs, per-pair quiet wait) | D: durability unverified. Diagnostic ratios favor ctrs: rw tps 0.46 [0.45, 0.48], rw p95 0.27, checkpoint 0.41, restart 0.33, ro tps 0.81, CPU 0.81, footprint 0.064. Pgdata allocation ratio is 1.0001. The direct guest `fdatasync` probe (2,000 × 4 KiB writes to a named volume, three runs per engine) measured OrbStack p50 at 0.6–2.0 ms and ctrs at 0.26–0.28 ms. Host flush semantics require separate evidence. |

W13 v3 admission verified exact bytes in all twelve configurations.
Both engines missed the twofold tool-headroom requirement in every
configuration.
The combined native receiver, sendfile and socket-buffer controls
also missed Mac headroom. In the guest, four-stream native bridge
transfers all exceeded half of the corresponding native loopback
rate.

The separate W14 backlog-128 confirmation admitted ten fresh-connection
pairs with no listen overflows or long stalls. p95 and p99 were 0.731×
and 0.651×. Measured CPU per response was 1.234× [1.209, 1.247]
before host NAT CPU.
The vsock setup diagnostic localized the largest measured elapsed
interval to connection establishment. The follow-up localized it
inside the framework call and completion interval. Caching the
socket device missed its CPU target.

Existing DNS, UDP, IPv6 and host-access checks are correctness tests
(`tests/e2e.sh`, `conformance/`), not performance cells. `bench/net/*.py`
(CTRS-17) streams a repeating pattern without content hashes and reports
Mbps only. It is not reusable as a verified-transfer metric.

#### Correctness findings from fixture work (2026-11-18)

- **Bind-mount file-change notification (fixed 2026-11-18; see W12-watch).** Mac-side edits under
  a ctrs bind mount produce no guest inotify events at all. A raw inotify
  probe tried save, atomic replace, create, rename and delete on a
  `-v <mac dir>:/w` mount. OrbStack delivered events for all five; ctrs
  delivered none. Native watchers (chokidar/nodemon, `tsc --watch`,
  webpack, vite) therefore never react to Mac edits on ctrs unless they
  poll. Virtualization.framework virtiofs carries no host change
  notifications, and ctrs has no forwarding mechanism. Proposed fix (needs
  owner approval: wire-protocol addition plus guest kernel patch):
  [design-bind-notify.md](design-bind-notify.md). W12-watch quantifies the
  effect.
- **Container→Mac half-close (fixed, `9940611`).** Over
  `host.docker.internal`, a container's half-close after about 1 MiB or more
  of data never reached the Mac service. Virtualization.framework drops the
  guest's vsock half-close after bulk data. Request/response protocols that
  half-close hung until timeout: Python at 1–256 MiB, busybox `nc` at
  64 MiB. Host-bound relays now frame the container's bytes on vsock port
  1032. The e2e check `host-internal-upload-eof` covers it. Guest
  initramfs and host binary identities change from this commit on.

- **W13 v1 capacity controls were invalid.** This host's Python is an
  OpenSSL-free build with software SHA-256 near 320 MiB/s. Receiver-side
  hashing capped host receivers and the host loopback control at 330 MB/s,
  below the measured paths, so every trial was tool-limited. v2 compares
  received bytes with the identical local artifact. Controls are now
  3.6–3.7 GB/s on the host and 4.7–6.3 GB/s in containers.

#### Ranked OrbStack deficits (this host)

The November 22 installed-default cohorts identify these losses. The
ordering gives priority to user-visible time, then build memory and engine
CPU. See the workload rows for the paired intervals, other metrics and
qualification gaps.

1. **W12 full-bind workflow.** Median paired workflow time was 1.300×
   and measured engine CPU was 1.163×. The offline install and verification
   walk account for about 71% of the workflow time gap. Both layouts that
   used volumes for dependencies and build outputs cleared workflow
   non-inferiority. The native inode-cap repeat verified headroom at
   both settings. Each reached about 105,000 VM descriptors, and
   whole-workflow differences were under 0.54 s.
   The notification-loss diagnostic removed 121,674 init lookups
   but left the traced install near twice the mixed-layout time.
2. **W10 API recovery.** Time to the first exact read was 1.239×. The
   gap accrued after the start command returned. The refusal trace
   found two 250 ms expiries before the first exact read. The 50 ms
   candidate passed its ctrs screen at 0.643× recovery time.
   Against OrbStack it reached 0.823× recovery time and 1.180× measured
   CPU per successful response. CPU blocked promotion.
   The excess was present before the interruption and after recovery
   in every pair at both TTLs.
3. **W6 uncached build memory (older binary; not reproduced at `b5ec34b`,
   0.402).** Sampled peak physical footprint was
   1.364×. In the quiet-window diagnostic, guest balloon pages increased
   while the VM helper's footprint stayed within 0.7 MB per leg.
   At the 5,632 MiB ceiling, image export accounted for most of the
   added zlib wall time in the three slowest repeat pairs.
4. **W12 bind watch and guest-direct W2 CPU.** Whole-trial watch CPU was
   1.186×, with the excess concentrated in setup. W2 CPU per verified
   request was 1.131× on the guest-direct path. Both cohorts had zero ctrs
   host NAT connections. Offline install accounted for 19.33–20.15
   of the 28.56–29.04 extra measured watch setup CPU-seconds. W2's
   leaf samples and guest interrupt counts point to excess wakeup work.
5. **CPU losses with incomplete host accounting.** Measured engine CPU
   per successful operation was 1.302× for W10 database recovery, 1.250×
   for W2 published-port fixed work and 1.167× for W10 API recovery.
   Total measured engine CPU was 1.097× for W13 overlap. These counters
   omit ctrs host NAT CPU.

W11 exceeded the short resource-growth budgets on both engines. Online
discard reduced ctrs backing growth in an eight-cycle screen. Both
online discard and uncached VZ disk backing still missed the backing
and physical-footprint limits. The 12-hour reliability gate remains
open.

W7 peak footprint is inconclusive,
and earlier guest-to-host bulk transfer was tool-limited. The
[November 20 observations](evidence/native-w12-w13-2026-11-18.md#ranked-measured-deficits)
retain the previous workload versions and their limitations.

`--pid host` is accepted and ignored by ctrs (no PidMode handling). That is
a compatibility gap and is not scored.

## Campaign: Deslop

### Goal and state

The [ticket backlog](../TODO-DESLOP.md) contains the remaining types, test and dead-code work. The original ground pass passed `make test`; later project instructions report `make lint` clean, superseding the backlog's old lint observation. The diagnostic found the layer symlink xattr defect, subsequently covered by the Linux test named in AGENTS.md. Take the lowest numbered open deslop ticket and proceed through DSLP-5 before other open P1/P2 findings when this campaign is explicitly resumed.

### Acceptance

Each ticket in the backlog states its acceptance. Linux-only and privileged verification needs an appropriate environment.

### Execution boundary and non-goals

The backlog and this roadmap do not authorize execution by themselves.

## Later

- CTRS-11: qualify the benchmark pyramid when the host is ready. See [TODO.md](../TODO.md).
- CTRS-13: reproduce and repair the ARM64 platform case under emulation. See [TODO.md](../TODO.md) and [ARM64 evidence](evidence/arm64-build.md).
- CTRS-14: investigate kache reading the sparse guest disk. See [TODO.md](../TODO.md).
- CTRS-15: decide the optional firewall backend and policy. See [TODO.md](../TODO.md).
- CTRS-16: pin guest kernel and benchmark sources. See [TODO.md](../TODO.md).
- DSLP-6: reconcile the historical lint ticket with the newer clean result. See [TODO-DESLOP.md](../TODO-DESLOP.md).
- N-2 / CRAB-7: qualify crabtables on the native production kernel and nftables pair before cutover.
- N-3: run the Intel host boot smoke; N-5: qualify Rosetta on macOS 15 when available.
- N-4: owner decides public release, notarization and the license-text question; the guest kernel source offer must accompany distributions.
- CTRS-21 follow-up: investigate unexplained daemon deaths when a surviving crash or Apple evidence is available.
- CTRS-14 follow-up: requalify h12tiny-server with a transport-neutral comparison; retain the incumbent until then.
- CTRS-17 follow-up: qualify vzNAT after the Local Network grant.
