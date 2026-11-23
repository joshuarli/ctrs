# macOS campaign acceptance matrix

Status table for the [macOS campaign](campaign-native-performance.md), resumed
on 2026-11-22. The November 20 pause left historical summaries for the deleted
raw results. The resumed cohorts have new receipts and commands in
[native-performance-progress.md](native-performance-progress.md). Host: M1 Max,
10 CPUs, 64 GiB, macOS 27.2.1, OrbStack 2.2.5 (from 2026-11-18). Every
measurement before 2026-11-18 is **historical to the previous host** and
counts as "not measured" here.

Statuses are cumulative and must be stated separately:

- **Specified**: a declared workflow, metrics and correctness checks exist.
- **Implemented**: a fixture and runner path exist in the tree.
- **Functionally verified (this host)**: both engines completed the
  workload with exact outputs on this host.
- **Compared (this host)**: a paired cohort with ≥10 valid pairs exists on this host in the
  stated lane. It is pilot evidence unless qualified.
- **Qualified**: the campaign gates pass (frozen inputs, exclusive
  window, independent confirmation). No cell is qualified.

Lanes: **D** = installed default (ctrs product defaults vs OrbStack as
installed); **M** = resource-matched control (ctrs vCPUs/memory set to
OrbStack's). Never pool lanes.

## Existing workloads

| ID | Workflow | Spec | Impl | Functional (this host) | Compared (this host) | Critical result (this host) |
| --- | --- | --- | --- | --- | --- | --- |
| W1 | Compose up API+PG+Redis, restart | yes | yes | yes, warm v3 on both engines and a cold ctrs admission | D: `base-20261122T093654-6f3a` (10/10 warm pairs) | Verified restart 0.686× [0.675, 0.698], initial roundtrip 0.848× [0.719, 0.912], and footprint 0.419× [0.387, 0.429] were strict wins. CPU accounting is incomplete due to host NAT. Equivalent engine-cold comparison remains open. [Warm evidence](native-performance-progress.md#installed-default-w1-warm-stack-cohort) [Cold admission](native-performance-progress.md#w1-engine-cold-admission-on-ctrs) |
| W2 | API fixed work, published port | yes | yes | yes (both lanes) | D: `base-20261122T081048-91d4` (10/10 pairs, 50,000 requests, both engines 9 vCPUs) | **Measured CPU per request loss** 1.250× [1.235, 1.259] before uncharged host NAT. p99 0.612× [0.598, 0.633], request rate 0.746× [0.737, 0.755] and footprint 0.313× [0.303, 0.328] were strict wins. At one client, CPU/request was 0.3915× [0.3765, 0.4155] in ten admitted pairs, with host NAT CPU uncharged. [One client](native-performance-progress.md#w2-published-port-fixed-work-at-one-client). At four clients, CPU/request was 1.4620× [1.4276, 1.4726] before uncharged NAT in ten admitted pairs. [Four clients](native-performance-progress.md#w2-published-port-fixed-work-at-four-clients) · [Eight clients](native-performance-progress.md#installed-default-w2-fixed-work-cohort). At 16 clients, ten admitted pairs still showed a measured CPU/request loss of 1.1529× [1.1393, 1.1583] before uncharged NAT. [Sixteen clients](native-performance-progress.md#w2-published-port-fixed-work-at-16-clients) · [Historical comparisons](evidence/native-w2-ipi-2026-11-18.md) |
| W2 | API fixed work, container-to-container | yes | yes | yes (installed defaults) | D: `base-20261123T033422-bb7b` (10/10 pairs, 50,000 requests, both engines 9 vCPUs) | **Measured CPU per request loss** 1.1162× [1.1056, 1.1244] with zero ctrs host NAT connections and both guest load clients included. p99 0.4428× [0.4375, 0.4454], request rate 0.5652× [0.5556, 0.5695] and footprint 0.1538× [0.1500, 0.1554] were strict wins in this cohort. At one client, CPU/request was a strict win at 0.8464× [0.8338, 0.8538] in ten admitted pairs. [One client](native-performance-progress.md#w2-guest-direct-fixed-work-at-one-client). At four clients, the CPU/request ratio was 1.1900× [1.1786, 1.2035] in ten admitted pairs. [Four clients](native-performance-progress.md#w2-guest-direct-fixed-work-at-four-clients) · [Eight clients](native-performance-progress.md#w2-guest-direct-eight-client-repeat-on-the-common-runtime). At 16 clients, ten admitted pairs still showed a CPU/request loss of 1.0560× [1.0517, 1.0628]. [Sixteen clients](native-performance-progress.md#w2-guest-direct-fixed-work-at-16-clients) |
| W2 | API saturation, published port at 1 client | yes | yes | yes, exact persisted writes and zero request errors | D: `base-20261123T020744-c034` (10/10 pairs) | Throughput ratio 0.2852× [0.2779, 0.2963], p99 0.1403× [0.1329, 0.1413] and sampled footprint 0.1520× [0.1511, 0.1529]. Measured CPU per success 0.3781× [0.3733, 0.3997] remains incomplete before charging host NAT CPU. [Evidence](native-performance-progress.md#published-port-at-one-client) |
| W2 | API saturation, container-to-container at 1 client | yes | yes | yes, exact persisted writes and zero request errors | D: `base-20261123T015720-c637` (10/10 pairs) | Throughput ratio 0.4367× [0.4292, 0.4423], p99 0.2276× [0.2240, 0.2401] and sampled footprint 0.1531× [0.1504, 0.1548]. Measured CPU per success was a strict win at 0.8282× [0.8138, 0.8415] with zero ctrs host NAT connections. [Evidence](native-performance-progress.md#container-to-container-at-one-client) |
| W2 | API saturation, published port at 4 clients | yes | yes | yes, exact persisted writes and zero request errors | D: `base-20261123T014658-81a6` (10/10 pairs) | Throughput ratio 0.7586× [0.7558, 0.7655], p99 0.5400× [0.5310, 0.5494] and sampled footprint 0.1513× [0.1493, 0.1544]. Measured CPU per success lost at 1.4543× [1.4454, 1.4691] before uncharged host NAT CPU. [Evidence](native-performance-progress.md#published-port-at-four-clients) |
| W2 | API saturation, container-to-container at 4 clients | yes | yes | yes, exact persisted writes and zero request errors | D: `base-20261123T013630-f6a6` (10/10 pairs) | Throughput ratio 0.5669× [0.5482, 0.5751], p99 0.3680× [0.3622, 0.3762] and sampled footprint 0.1524× [0.1502, 0.1544]. CPU per success lost at 1.1817× [1.1612, 1.1973] with zero ctrs host NAT connections. [Evidence](native-performance-progress.md#container-to-container-at-four-clients) |
| W2 | API saturation, published port at 8 clients | yes | yes | yes, exact persisted writes and zero request errors | D: `base-20261123T012518-8a0d` (10/10 pairs) | Throughput ratio 0.7446× [0.7395, 0.7496], p99 0.6234× [0.6120, 0.6299] and sampled footprint 0.1500× [0.1484, 0.1513]. Measured CPU per success lost at 1.2752× [1.2565, 1.2862] before uncharged host NAT CPU. [Evidence](native-performance-progress.md#published-port-at-eight-clients) |
| W2 | API saturation, container-to-container at 8 clients | yes | yes | yes, exact persisted writes and zero request errors | D: `base-20261123T011451-df53` (10/10 pairs) | Throughput ratio 0.5709× [0.5576, 0.5770], p99 0.4520× [0.4378, 0.4574] and sampled footprint 0.1521× [0.1494, 0.1554]. CPU per success lost at 1.1189× [1.0899, 1.1363] with zero ctrs host NAT connections. [Evidence](native-performance-progress.md#installed-default-w2-saturation-at-eight-clients) |
| W2 | API saturation, published port at 16 clients | yes | yes | yes, exact persisted writes and zero request errors | D: `base-20261123T010350-c7eb` (10/10 pairs) | Throughput ratio 0.6928× [0.6892, 0.6972], p99 0.5400× [0.5312, 0.5551] and sampled footprint 0.1504× [0.1496, 0.1529]. Measured CPU per success lost at 1.1248× [1.1154, 1.1483] before uncharged host NAT CPU. [Evidence](native-performance-progress.md#published-port-saturation) |
| W2 | API saturation, container-to-container at 16 clients | yes | yes | yes, exact persisted writes and zero request errors | D: `base-20261123T005321-6ac0` (10/10 pairs) | Throughput ratio 0.5554× [0.5497, 0.5606], p99 0.3959× [0.3926, 0.4054] and sampled footprint 0.1553× [0.1529, 0.1563]. CPU per success is inconclusive at 1.0265× [1.0189, 1.0449] with zero ctrs host NAT connections. [Evidence](native-performance-progress.md#container-to-container-saturation) |
| W2 | API fixed offered rate, published port | yes | yes | ctrs passed, OrbStack missed scheduled slots | D: `base-20261122T093101-7063` (0/2 valid pairs) | Both engines completed 10,000 exact requests in each leg. The OrbStack legs exceeded the 10 ms start-lag budget on 53 and 41 slots. The stop rule fired and timing comparisons remain unmeasured. [Evidence](native-performance-progress.md#installed-default-w2-published-port-fixed-offered-rate) · [16-connection diagnostic](native-performance-progress.md#w2-fixed-offered-rate-with-sixteen-connections) |
| W2 | API fixed offered rate, container-to-container | yes | yes | both engines missed scheduled slots | D: `base-20261122T093306-1b10` (0/2 valid pairs) | Both engines completed 10,000 exact requests in each leg. OrbStack had 8 and 19 late slots, and ctrs had 0 and 1. All 28 had an in-flight predecessor at the lateness deadline. The stop rule fired and timing comparisons remain unmeasured. [Evidence](native-performance-progress.md#installed-default-w2-container-to-container-fixed-offered-rate) · [16-connection diagnostic](native-performance-progress.md#w2-fixed-offered-rate-with-sixteen-connections) |
| W3 | PG transactions, checkpoint, restart | yes | yes | yes, exact 300 transactions per leg | D: `base-20261122T130640-24d2` (10/10 pairs) | Commit p95 0.069× [0.061, 0.082] and engine CPU per transaction 0.145× [0.135, 0.168] are durability-unverified. Restart timing is inconclusive. Both ctrs sync modes recovered exact data after guest relation ENOSPC and backing-file allocation failure on a private host APFS volume. Equivalent host durability remains open. [Paired evidence](native-performance-progress.md#w3-migration-and-committed-state-cohort) · [Guest ENOSPC](native-performance-progress.md#w3-guest-relation-enospc-and-recovery) · [Private host APFS](native-performance-progress.md#w3-private-host-apfs-exhaustion-and-recovery) |
| W4 | Queue workers 1/4/16 | yes | yes | yes, 12,000 exact jobs and 24,000 artifacts across both engines | D: `base-20261122T143625-9f92` (10/10 pairs) | Worker phase time, queue p95/p99, engine CPU per job and sampled physical footprint cleared the strict-win interval at all three worker counts. At 16 workers, time was 0.279× [0.267, 0.286] and queue p99 was 0.289× [0.273, 0.318]. Frozen confirmation remains open. [Evidence](native-performance-progress.md#installed-default-w4-cohort) |
| W5 | Marked esbuild watch (bind, volume) | yes | yes | yes, 2,400 exact edit results | D: `base-20261122T123236-7047` (10/10 pairs, 60 edits per mount) | Edit p50 and p95 were non-inferior on both mounts. Setup and sampled footprint were strict wins on both. CPU per edit was non-inferior on bind and a strict win on volume. Frozen confirmation remains open. [Evidence](native-performance-progress.md#installed-default-w5-cohort) |
| W6 | Default-builder Rust+C CI build | yes | yes | yes | D: uncached `base-20261122T063709-0627` and primed `base-20261122T102417-474d` (10/10 pairs each, both engines 9 vCPUs) | Uncached physical footprint loss 1.364× [1.182, 1.485], Rust 0.944× non-inferior, zlib 0.524× strict win. Primed cached build and load strict wins for both applications, Rust 0.476× [0.448, 0.483] and zlib 0.448× [0.446, 0.461]; primed physical footprint inconclusive at 1.152× [0.949, 1.288]. CPU accounting is incomplete due to host NAT. The independent 5,632 MiB repeat reproduced the footprint reduction, but zlib missed the timing bound. [Uncached evidence](native-performance-progress.md#installed-default-w6-cohort) [Primed-cache evidence](native-performance-progress.md#installed-default-w6-primed-cache-cohort) |
| W7 | Default buildx → loaded images | yes | yes | yes, exact runtime receipts across engines and cache states | D: network-resolved `base-20261122T170828-8009` and offline `base-20261122T172448-ffd0` (10/10 each) | All 12 timing cells cleared the descriptive strict-win threshold in both cohorts. Offline uncached Hyperfine 0.883× [0.867, 0.897], HTTPie 0.793× [0.779, 0.804], sampled footprint 0.599× [0.563, 0.613]. Build CPU still lacks host NAT accounting. Separately, identical imported HTTPie first-use time was 0.848× [0.827, 0.876] across ten pairs. [Network-resolved evidence](native-performance-progress.md#w7-installed-default-cohort-with-exact-runtime-receipts) · [Offline evidence](native-performance-progress.md#w7-offline-build-cohort) · [Imported first use](native-performance-progress.md#frozen-httpie-first-use-result) |
| W8 | Pull-to-healthy from local registry (w8-v6 portfolio) | yes | yes | yes, both engines and content states, with and without API load | D and M: ten complete pairs per content and load condition in each lane | No-load pull-to-health was 0.546× [0.505, 0.549] retained and 0.433× [0.420, 0.464] derived. Under load it was 0.453× [0.419, 0.460] in the corrected retained repeat and 0.414× [0.384, 0.430] derived. Matched pull-to-health upper bounds ranged from 0.356× to 0.593× across four controls. Derived-load p99 remains inconclusive. Host NAT CPU was uncharged. [Retained](native-performance-progress.md#w8-retained-content-timing-without-concurrent-load) [Derived](native-performance-progress.md#w8-derived-content-timing-without-concurrent-load) [Retained with load](native-performance-progress.md#w8-retained-content-timing-with-concurrent-load) [Derived with load](native-performance-progress.md#w8-derived-content-timing-with-concurrent-load) [No-load allocation](native-performance-progress.md#w8-backing-allocation-with-no-concurrent-load) [Under-load allocation](native-performance-progress.md#w8-backing-allocation-under-concurrent-api-load) |
| W9 | Parallel fixed build/test jobs | yes | yes | yes, all four concurrency levels on both engines | D: `base-20261122T101434-f89b` (10/10 pairs) | Batch time, p95, measured CPU per job and sampled footprint cleared the strict-win threshold at all four concurrencies. Frozen confirmation remains open. [Evidence](native-performance-progress.md#installed-default-w9-cohort) |
| W10 | Interrupt/recover service/DB/queue | yes | yes | yes, exact API/DB/queue and owned ctrs engine recovery | D: API, database and queue (10/10 pairs each) | API recovery loss 1.239× [1.195, 1.315], DB recovery strict win 0.342× [0.301, 0.415], queue recovery strict win 0.451× [0.438, 0.459]. Recovered p99 and sampled footprint cleared the strict-win threshold in all three conditions. Measured CPU/success lost at 1.167× for API and 1.302× for database. Queue CPU/job cleared the strict-win threshold at 0.521× [0.513, 0.553]. Whole-engine parity needs isolated OrbStack. [API evidence](native-performance-progress.md#installed-default-w10-api-recovery-cohort) [Database evidence](native-performance-progress.md#installed-default-w10-database-recovery-cohort) [Queue evidence](native-performance-progress.md#installed-default-w10-queue-recovery-cohort) [Owned engine evidence](native-performance-progress.md#w10-owned-engine-recovery-on-ctrs) |
| W11 | 12 h mixed reliability | yes | yes, v5 worker and v6 portfolio | yes, short runs with 12 exact ctrs cycles and 11 exact OrbStack cycles | n/a | ctrs exceeded the short footprint and active-backing growth budgets. OrbStack exceeded the backing budget twice, with a recurring cycle-eight jump confirmed in APFS private bytes. OrbStack exceeded the footprint budget in the first run and passed it in the repeat. Durability admission and both 12-hour legs remain open. [ctrs growth](native-performance-progress.md#w11-short-ctrs-growth-result) · [OrbStack repeat](native-performance-progress.md#w11-orbstack-private-backing-repeat) |

The installed-default W2 saturation grid has ten admitted pairs at each of
1, 4, 8 and 16 clients on both paths. The independent raw audit matched
1,504,565 acknowledged writes to persisted rows across 5,009,975
successful requests. Both fixed offered-rate cells still need admitted
cohorts.

The eight-client fixed-work cohorts used the earlier signed
`5cac40d` runtime (`d59eff1a…`) and initramfs (`fbed2ff9…`).
The one-, four- and sixteen-client cohorts above use `99db1aa`
with binary `10667e6d…` and initramfs `fb0f832b…`. The eight
completed cohorts passed the raw equal-work audit across 8,000,000
requests and 2,403,504 acknowledged writes. The eight-client guest-direct repeat
on `99db1aa` also passed the audit. The published-port repeat on
that runtime is still needed. Keep the earlier measurements separate.

## Filesystem and networking coverage (2026-11-18 steering)

W12 v2 full-bind completed ten installed-default pairs on 2026-11-22.
The workflow ratio was 1.2999 [1.2883, 1.3223], with measured CPU at
1.1630 [1.1593, 1.1725] and sampled physical footprint at 0.3606
[0.3455, 0.3871]. The v2 mixed-layout cohort also completed ten pairs.
The workflow was non-inferior at 0.9990 [0.9887, 1.0026], with an
inconclusive install interval and a strict footprint win. The ten-pair
v2 all-volume cohort had non-inferior workflow time at 0.9915
[0.9880, 0.9986] and non-inferior CPU, with a strict footprint win.
Both watch cohorts are complete.
[Mixed-layout evidence](native-performance-progress.md#installed-default-w12-mixed-layout-cohort)
[All-volume evidence](native-performance-progress.md#installed-default-w12-all-volume-cohort)
The upgraded mixed-layout receipt passed a native admission pair with
all four exact build outputs and both discovered tests.
[Build output admission](native-performance-progress.md#w12-native-build-output-receipt-admission)
The table retains W12 timing history from the previous workspace fixture.
[Current cohort](native-performance-progress.md#installed-default-w12-full-bind-cohort)

| ID | Workflow | Spec | Impl | Functional | Compared | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| W12 | Shared workspace (Kutt v2.7.4, 2,830 packages, 92,306 files, 532 MB): offline install, build, typecheck, Jest discovery, rebuild, edit and branch restore | yes | yes (`w12-v2`) | yes, all three layouts on the signed release | D: 10/10 pairs per layout | Critical full-bind loss. Workflow ratio 1.2999 [1.2883, 1.3223], offline install 2.1055 [2.0701, 2.1621], and install verification 4.1610 [4.0605, 4.5087]. Mixed workflow 0.9990 [0.9887, 1.0026] and all-volume 0.9915 [0.9880, 0.9986] were non-inferior. The full-bind install verifier issued 91,875 birth-time stat requests in one traced leg. [Full bind](native-performance-progress.md#installed-default-w12-full-bind-cohort) · [Mixed](native-performance-progress.md#installed-default-w12-mixed-layout-cohort) · [All volume](native-performance-progress.md#installed-default-w12-all-volume-cohort) · [FUSE trace](native-performance-progress.md#w12-install-verification-fuse-requests) · [Earlier experiments](evidence/native-w12-w13-2026-11-18.md) |
| W12-watch bind | `tsc --watch` (fs.watch backend), host-side edits including atomic replaces and five-file bursts | yes | yes (`w12-watch-v4`) | yes, 120 exact results per leg | D: `base-20261122T131311-6799` (10/10 pairs) | **Whole-trial engine CPU loss** 1.186× [1.170, 1.215]. Offline install accounted for most of the extra setup CPU in a two-pair breakdown. Edit p50 0.881× [0.838, 0.931] strict win, p95 0.971× [0.939, 1.026] non-inferior, sampled footprint 0.269× strict win. [Cohort](native-performance-progress.md#installed-default-w12-bind-watch-cohort) · [Setup](native-performance-progress.md#w12-bind-watch-setup-cpu-attribution) |
| W12-watch volume | Same edit plan with `docker exec` edits to a named volume | yes | yes (`w12-watch-volume-v2`) | yes, 120 exact results per leg | D: `base-20261122T135713-1c0c` (10/10 pairs) | Descriptive strict wins in edit p50 0.725× [0.705, 0.767], edit p95 0.763× [0.716, 0.805], measured engine CPU 0.859× [0.843, 0.877], and sampled physical footprint 0.287× [0.281, 0.325]. [Evidence](native-performance-progress.md#installed-default-w12-named-volume-watch-cohort) |
| W13 | Artifact transfer up/down: published port, container↔container, container→Mac; 1 and 4 streams; byte-exact receivers | yes | yes (`w13-v2`) | yes | D: seven cells; M: published-port upload; rx64 (patch 0005): three host→guest cells | critical. **Splice build (`4fdff1d`): published-port download 0.93 [0.92, 0.94] tool-limited (was 1.64–1.78× loss), upload 0.69 tool-limited, container→Mac upload 0.95 [0.94, 0.97] tool-limited (was 2.23×); ctrs time 0.56× / 0.77× / 0.43× its previous build with OrbStack unchanged (`base-20261120T000004-f614`, `base-20261119T235251-7eb8`, `base-20261120T000743-a0eb`). Every guest→host cell is now at the tool's ceiling, so no win is claimed. Container→Mac download (Mac→container bytes) regressed to 1.21 spliced and is back to 1.06 [1.01, 1.18] inconclusive with that direction copied (`ade0b80`, `base-20261120T030035-4a43`; pre-splice 1.04).** Before: **Guest→host loss, reduced:** over the NAT relay and legs (protocol 9), container→Mac upload 2.23× (was 7.0×), published-port download 1.64× (was 5.1×); every ctrs trial records its transport (nat/nat_leg 30, vsock 0). One NAT flow caps near 1.9 GB/s here. Host→guest after patch 0005: published-port upload 1.02 (parity) over vsock; the leg-only build regressed it to 1.14×; `439b14e` (client bytes over vsock) restored 0.96 [0.85, 1.07] inconclusive, CPU/GiB 1.17× loss (`base-20261119T134339-6c08`); Mac→container 1.03 over vsock and 0.99 [0.97, 1.02] tool-limited over NAT (`base-20261119T133649-3bc7`, non-regressing, not a win), 4-stream upload 1.25 loss. Container↔container **win** 0.82 ([evidence](evidence/native-w12-w13-2026-11-18.md)). Controlled egress unsupported (no owned endpoint) |
| W13-overlap | Published-port upload alongside W2 | yes | yes (v6 portfolio, verified overlap) | yes, both engines | D: `base-20261122T073402-7351` (10/10 pairs, both engines 9 vCPUs) | **Measured CPU loss** 1.097× [1.051, 1.158] before uncharged host NAT. Footprint 0.748× [0.653, 0.782] strict win. API p50 0.975× non-inferior. API p99, request rate and transfer goodput inconclusive. The older 5-vCPU cohort recorded p99 1.70× with different image pins. [Evidence and reproduction](native-performance-progress.md#installed-default-w13-overlap-cohort) |
| W14 | Connection lifecycle: fresh, persistent, streaming, cancel, idle-resume, reconnect | yes | yes | yes, exact buffered v4 results in all six modes | D: all six v4 modes (10/10 each) | Fresh p50 1.331×, p95 1.425× and CPU 1.170× lost. Persistent p95 0.829× was a strict win and cleanup 1.279× lost. Streaming p99 lateness 1.393× [1.260, 1.541] lost. Post-cancel response 0.422× was a strict win. Resume p50 and reconnect p99 were inconclusive. Host NAT CPU remains outside the counters. [Fresh and persistent](native-performance-progress.md#w14-fresh-and-persistent-connections-with-buffered-frames) [Streaming, cancel and reconnect](native-performance-progress.md#w14-streaming-cancellation-and-reconnect-with-buffered-frames) [Idle-resume](native-performance-progress.md#w14-idle-resume-with-buffered-frames) |
| W3-v4 | Persistent storage: meaningful dataset, sustained read/write/checkpoint, declared working set and durability | yes | yes (pgbench fixed work) | no | D: `base-20261119T170441-5abe` (10/10 pairs, per-pair quiet wait) | D: durability unverified. Diagnostic ratios favor ctrs: rw tps 0.46 [0.45, 0.48], rw p95 0.27, checkpoint 0.41, restart 0.33, ro tps 0.81, CPU 0.81, footprint 0.064. Pgdata allocation ratio is 1.0001. The direct guest `fdatasync` probe (2,000 × 4 KiB writes to a named volume, three runs per engine) measured OrbStack p50 at 0.6–2.0 ms and ctrs at 0.26–0.28 ms. Host flush semantics require separate evidence. [Durability boundary](native-performance-progress.md#w3-migration-and-committed-state-cohort) |

W13 v3 admission verified exact bytes in all twelve configurations.
Both engines missed the twofold tool-headroom requirement in every
configuration. [Published-port evidence](native-performance-progress.md#w13-published-port-v3-admission) · [Guest and host-internal evidence](native-performance-progress.md#w13-guest-and-host-internal-v3-admission)

Existing DNS, UDP, IPv6 and host-access checks are correctness tests
(`tests/e2e.sh`, `conformance/`), not performance cells. `bench/net/*.py`
(CTRS-17) streams a repeating pattern without content hashes and reports
Mbps only. It is not reusable as a verified-transfer metric.

## Correctness findings from fixture work (2026-11-18)

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

## Ranked OrbStack deficits (this host)

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
   [Evidence](native-performance-progress.md#installed-default-w12-full-bind-cohort)
2. **W10 API recovery.** Time to the first exact read was 1.239×. The
   gap accrued after the start command returned. The refusal trace
   found two 250 ms expiries before the first exact read. The 50 ms
   candidate passed its ctrs screen at 0.643× recovery time.
   Against OrbStack it reached 0.823× recovery time and 1.180× measured
   CPU per successful response. CPU blocked promotion.
   [Evidence](native-performance-progress.md#installed-default-w10-api-recovery-cohort)
3. **W6 uncached build memory.** Sampled peak physical footprint was
   1.364×. In the quiet-window diagnostic, guest balloon pages increased
   while the VM helper's footprint stayed within 0.7 MB per leg.
   [Evidence](native-performance-progress.md#installed-default-w6-cohort)
4. **W12 bind watch and guest-direct W2 CPU.** Whole-trial watch CPU was
   1.186×, with the excess concentrated in setup. W2 CPU per verified
   request was 1.131× on the guest-direct path. Both cohorts had zero ctrs
   host NAT connections. Offline install accounted for 19.33–20.15
   of the 28.56–29.04 extra measured watch setup CPU-seconds. W2's
   leaf samples and guest interrupt counts point to excess wakeup work.
   [W12 evidence](native-performance-progress.md#installed-default-w12-bind-watch-cohort)
   [W2 evidence](native-performance-progress.md#installed-default-w2-container-to-container-fixed-work-cohort)
5. **CPU losses with incomplete host accounting.** Measured engine CPU
   per successful operation was 1.302× for W10 database recovery, 1.250×
   for W2 published-port fixed work and 1.167× for W10 API recovery.
   Total measured engine CPU was 1.097× for W13 overlap. These counters
   omit ctrs host NAT CPU.
   [W10 database evidence](native-performance-progress.md#installed-default-w10-database-recovery-cohort)
   [W2 published-port evidence](native-performance-progress.md#installed-default-w2-fixed-work-cohort)
   [W10 API evidence](native-performance-progress.md#installed-default-w10-api-recovery-cohort)
   [W13 evidence](native-performance-progress.md#installed-default-w13-overlap-cohort)

W11 exceeded the short resource-growth budgets on both engines. The
12-hour reliability gate remains open. W7 peak footprint is inconclusive,
and earlier guest-to-host bulk transfer was tool-limited. The
[November 20 observations](evidence/native-w12-w13-2026-11-18.md#ranked-measured-deficits)
retain the previous workload versions and their limitations.

`--pid host` is accepted and ignored by ctrs (no PidMode handling). That is
a compatibility gap and is not scored.
