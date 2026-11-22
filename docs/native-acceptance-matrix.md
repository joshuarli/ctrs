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
| W1 | Compose up API+PG+Redis, restart | yes | yes | yes, v3 on both engines | D: `base-20261122T093654-6f3a` (10/10 warm pairs) | Verified restart 0.686× [0.675, 0.698], initial roundtrip 0.848× [0.719, 0.912], and footprint 0.419× [0.387, 0.429] were strict wins. CPU accounting is incomplete due to host NAT. Engine-cold coverage remains open. [Evidence](native-performance-progress.md#installed-default-w1-warm-stack-cohort) |
| W2 | API fixed work, published port | yes | yes | yes (both lanes) | D: `base-20261122T081048-91d4` (10/10 pairs, 50,000 requests, both engines 9 vCPUs) | **Measured CPU per request loss** 1.250× [1.235, 1.259] before uncharged host NAT. p99 0.612× [0.598, 0.633], request rate 0.746× [0.737, 0.755] and footprint 0.313× [0.303, 0.328] were strict wins. [Current evidence](native-performance-progress.md#installed-default-w2-fixed-work-cohort), [historical installed and matched comparisons](evidence/native-w2-ipi-2026-11-18.md) |
| W2 | API fixed work, container-to-container | yes | yes | yes (installed defaults) | D: `base-20261122T091635-df7a` (10/10 pairs, 50,000 requests, both engines 9 vCPUs) | **Measured CPU per request loss** 1.131× [1.123, 1.143] with zero ctrs host NAT connections and both guest load clients included. p99 0.454× [0.444, 0.459], request rate 0.581× [0.576, 0.590] and footprint 0.443× [0.412, 0.463] were strict wins in this cohort. [Evidence](native-performance-progress.md#installed-default-w2-container-to-container-fixed-work-cohort) |
| W2 | API fixed offered rate, published port | yes | yes | ctrs passed, OrbStack missed scheduled slots | D: `base-20261122T093101-7063` (0/2 valid pairs) | Both engines completed 10,000 exact requests in each leg. The OrbStack legs exceeded the 10 ms start-lag budget on 53 and 41 slots. The stop rule fired and timing comparisons remain unmeasured. [Evidence](native-performance-progress.md#installed-default-w2-published-port-fixed-offered-rate) |
| W2 | API fixed offered rate, container-to-container | yes | yes | both engines missed scheduled slots | D: `base-20261122T093306-1b10` (0/2 valid pairs) | Both engines completed 10,000 exact requests in each leg. OrbStack had 8 and 19 late slots, and ctrs had 0 and 1. All 28 had an in-flight predecessor at the lateness deadline. The stop rule fired and timing comparisons remain unmeasured. [Evidence](native-performance-progress.md#installed-default-w2-container-to-container-fixed-offered-rate) |
| W3 | PG transactions, checkpoint, restart | yes | yes | yes, exact 300 transactions on both engines | D: one valid admission pair | Comparative cohort and equivalent host durability remain open. [Evidence](native-performance-progress.md#w3-migration-and-committed-state-cohort) |
| W4 | Queue workers 1/4/16 | yes | yes | yes (one-pair pilot `base-20261120T061132-4479`, inputs from `prepare --only W4`) | no | unmeasured |
| W5 | Marked esbuild watch (bind, volume) | yes | yes | yes, 2,400 exact edit results | D: `base-20261122T123236-7047` (10/10 pairs, 60 edits per mount) | Edit p50 and p95 were non-inferior on both mounts. Setup and sampled footprint were strict wins on both. CPU per edit was non-inferior on bind and a strict win on volume. Frozen confirmation remains open. [Evidence](native-performance-progress.md#installed-default-w5-cohort) |
| W6 | Default-builder Rust+C CI build | yes | yes | yes | D: uncached `base-20261122T063709-0627` and primed `base-20261122T102417-474d` (10/10 pairs each, both engines 9 vCPUs) | Uncached physical footprint loss 1.364× [1.182, 1.485], Rust 0.944× non-inferior, zlib 0.524× strict win. Primed cached build and load strict wins for both applications, Rust 0.476× [0.448, 0.483] and zlib 0.448× [0.446, 0.461]; primed physical footprint inconclusive at 1.152× [0.949, 1.288]. CPU accounting is incomplete due to host NAT. The 6,144 MiB candidate missed its footprint bound. [Uncached evidence](native-performance-progress.md#installed-default-w6-cohort) [Primed-cache evidence](native-performance-progress.md#installed-default-w6-primed-cache-cohort) |
| W7 | Default buildx → loaded images | yes | yes | yes | D: `base-20261122T065539-5b0c` (10/10 pairs, source `2910f31`, both engines 9 vCPUs) | All 12 build/load and first-use timings cleared the strict-win threshold. Hyperfine uncached 0.886× [0.875, 0.893]; HTTPie uncached 0.783× [0.771, 0.799]. Footprint 1.088× [0.923, 1.345] inconclusive. CPU incomplete due to host NAT accounting. [Evidence and reproduction](native-performance-progress.md#installed-default-w7-cohort) |
| W8 | Pull-to-healthy from local registry (w8-v6 portfolio) | yes | yes | yes, both engines and content states, with and without API load | D: one valid pair in each deployment condition | Comparative cohorts, matched resource controls and backing-allocation evidence remain open. [Deployment proofs](native-performance-progress.md#rebuilt-w8-common-portfolio) |
| W9 | Parallel fixed build/test jobs | yes | yes | yes, all four concurrency levels on both engines | D: `base-20261122T101434-f89b` (10/10 pairs) | Batch time, p95, measured CPU per job and sampled footprint cleared the strict-win threshold at all four concurrencies. Frozen confirmation remains open. [Evidence](native-performance-progress.md#installed-default-w9-cohort) |
| W10 | Interrupt/recover service/DB/queue | yes | yes | yes, exact API/DB/queue pilots | D: API, database and queue (10/10 pairs each) | API recovery loss 1.239× [1.195, 1.315], DB recovery strict win 0.342× [0.301, 0.415], queue recovery strict win 0.451× [0.438, 0.459]. Recovered p99 and sampled footprint cleared the strict-win threshold in all three conditions. Measured CPU/success lost at 1.167× for API and 1.302× for database. Queue CPU/job cleared the strict-win threshold at 0.521× [0.513, 0.553]. Whole-engine parity needs isolated OrbStack. [API evidence](native-performance-progress.md#installed-default-w10-api-recovery-cohort) [Database evidence](native-performance-progress.md#installed-default-w10-database-recovery-cohort) [Queue evidence](native-performance-progress.md#installed-default-w10-queue-recovery-cohort) |
| W11 | 12 h mixed reliability | yes | yes, v5 worker and v6 portfolio | yes, 12 exact ctrs cycles and 11 exact OrbStack cycles with growth observations | n/a | Both exceeded the short footprint and active-backing growth budgets. Durability admission and both 12-hour legs remain open. [ctrs growth](native-performance-progress.md#w11-short-ctrs-growth-result) · [OrbStack growth](native-performance-progress.md#w11-short-orbstack-growth-result) |

## Filesystem and networking coverage (2026-11-18 steering)

W12 v2 full-bind completed ten installed-default pairs on 2026-11-22.
The workflow ratio was 1.2999 [1.2883, 1.3223], with measured CPU at
1.1630 [1.1593, 1.1725] and sampled physical footprint at 0.3606
[0.3455, 0.3871]. The v2 mixed, all-volume and watch comparisons remain
open. The table below retains W12 timing history from the previous fixture.
[Current cohort](native-performance-progress.md#installed-default-w12-full-bind-cohort)

| ID | Workflow | Spec | Impl | Functional | Compared | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| W12 | Shared workspace (Kutt v2.7.4, 2,830 packages, 92,306 files, 532 MB): offline `npm ci`, tsc + Next.js build, typecheck, Jest discovery, warm rebuild, ten-file change, branch restore; layouts full-bind / bind-source + volume deps / all-volume | yes | yes (`w12-v1`) | yes, all three layouts, D lane, exact receipts | D full-bind `base-20261118T120818-c079`; D all-volume `base-20261118T125148-c6aa`; M all-volume `base-20261118T144740-4485`; M full-bind `base-20261118T161928-8d7f` | critical. **Loss on full-bind.** Kernel k15 (patches 0013–0014, LOOKUPs −70%): M full-bind 1.23 [1.19, 1.30] (`base-20261119T064359-1f0c`), D 1.28 [1.24, 1.32] (`base-20261119T072809-bc40`): unchanged, because the Mac's virtiofs server flattens near 8,300 small files/s against OrbStack's 16,600–20,900. Kernel k14: **M full-bind 1.25 [1.23, 1.27]** (`base-20261119T023414-9164`; install 1.96, test discovery 2.15: Mac-share cost); D full-bind 1.52 at 2 vCPUs (`base-20261119T031525-7297`), **1.26 [1.21, 1.30] at the new 5-vCPU default** (`base-20261119T054737-9a02`); D all-volume 1.29 at 2 vCPUs, **1.02 [1.00, 1.03] inconclusive at 5 vCPUs** (`base-20261119T050726-d2cd`, host CPU 0.85 strict win); M all-volume parity 1.02. Before the kernel work D full-bind 1.62, M 1.44. On `bf2ea2b` M full-bind `base-20261119T214453-bfcc` is invalid (6 valid pairs; 4 rejected at 2.1–2.9 cores busy outside the engines): 1.25 [1.19, 1.28], install 2.04, test discovery 2.15, as before. D full-bind `base-20261119T171357-15a5` is invalid (pair 4 rejected, load 14.2 mid-trial despite the per-pair quiet wait); its 9 pairs give 1.33 [1.25, 1.34], install 2.01, test discovery 2.26: the loss stands, not re-scored. **D bind-source + volume deps scored `base-20261120T045710-1dc3` (adopted guest, 10/10): workflow 1.027 [1.019, 1.033] inconclusive (about 3 % slower, not a win), build 1.04 and warm rebuild 1.05 losses, typecheck 0.99 and test discovery 0.99 non-inferior, CPU 0.92 win.** Earlier `base-20261119T181642-550e`: invalid (8 valid pairs, 2 rejected for mid-trial load); its 8 pairs give workflow 1.01 [0.99, 1.03], install 0.95, warm rebuild 1.07, CPU 0.89, footprint 0.094: near parity, not scored; again `base-20261119T225149-5f9a`: invalid by one pair (pair 3 at 2.0 cores outside the engines), 9 pairs give workflow 1.016 [0.998, 1.019], test discovery 0.95, warm rebuild 1.04, CPU 0.91: two unscored cohorts agree that volume deps remove nearly all of the full-bind loss ([evidence](evidence/native-w12-w13-2026-11-18.md)) |
| W12-watch | `tsc --watch` (fs.watch backend): save, atomic replace, create+import, rename, delete, five-file bursts, 120 results per trial | yes | yes (`w12-watch-v2`) | yes, v2 both mounts | D bind: `base-20261118T174235-c732` (k7, 10 pairs), `base-20261118T212940-afee` (k8, 3 pairs), `-215543-cd5e` / `-220619-ab8e` (k10 / k9, 2 pairs each), `base-20261118T234824-4ef9` (k11, 2 pairs), **`base-20261119T013944-e94b` (k13, 10 pairs)** | **Scored on the splice build (`base-20261120T014028-c06b`, 10/10 pairs, outside-CPU admission): edit-to-result p50 0.90 [0.90, 0.91] strict win, p95 0.98 [0.96, 1.01] non-inferior, CPU 1.07 [1.06, 1.08] loss, footprint 0.07.** Earlier on `bf2ea2b` (`base-20261119T191032-ccdc`, 5 pairs, pilot only, no verdict): edit-to-result p50 0.92 [0.89, 0.93], p95 0.97, CPU 0.91, all trials correct. **Parity (kernel k13, 10 pairs; k14 `base-20261119T040227-c39c` and k15 `base-20261119T080909-d4d8` 600/600 on both, 5 pairs each):** ctrs bind 1,200/1,200 correct, 0 stale; OrbStack 1,200/1,200; detection p50 0.65 s on both, p95 2.0 s on both. Before notifications ctrs missed 120/120. Native-semantics kernels (k8–k10) reached 97/120, missing the in-place edits after an atomic replace that `tsc` also misses on volumes on both engines; k11 raises an in-place Mac edit as a rename of the name onto itself, as OrbStack does. |
| W13 | Artifact transfer up/down: published port, container↔container, container→Mac; 1 and 4 streams; byte-exact receivers | yes | yes (`w13-v2`) | yes | D: seven cells; M: published-port upload; rx64 (patch 0005): three host→guest cells | critical. **Splice build (`4fdff1d`): published-port download 0.93 [0.92, 0.94] tool-limited (was 1.64–1.78× loss), upload 0.69 tool-limited, container→Mac upload 0.95 [0.94, 0.97] tool-limited (was 2.23×); ctrs time 0.56× / 0.77× / 0.43× its previous build with OrbStack unchanged (`base-20261120T000004-f614`, `base-20261119T235251-7eb8`, `base-20261120T000743-a0eb`). Every guest→host cell is now at the tool's ceiling, so no win is claimed. Container→Mac download (Mac→container bytes) regressed to 1.21 spliced and is back to 1.06 [1.01, 1.18] inconclusive with that direction copied (`ade0b80`, `base-20261120T030035-4a43`; pre-splice 1.04).** Before: **Guest→host loss, reduced:** over the NAT relay and legs (protocol 9), container→Mac upload 2.23× (was 7.0×), published-port download 1.64× (was 5.1×); every ctrs trial records its transport (nat/nat_leg 30, vsock 0). One NAT flow caps near 1.9 GB/s here. Host→guest after patch 0005: published-port upload 1.02 (parity) over vsock; the leg-only build regressed it to 1.14×; `439b14e` (client bytes over vsock) restored 0.96 [0.85, 1.07] inconclusive, CPU/GiB 1.17× loss (`base-20261119T134339-6c08`); Mac→container 1.03 over vsock and 0.99 [0.97, 1.02] tool-limited over NAT (`base-20261119T133649-3bc7`, non-regressing, not a win), 4-stream upload 1.25 loss. Container↔container **win** 0.82 ([evidence](evidence/native-w12-w13-2026-11-18.md)). Controlled egress unsupported (no owned endpoint) |
| W13-overlap | Published-port upload alongside W2 | yes | yes (v6 portfolio, verified overlap) | yes, both engines | D: `base-20261122T073402-7351` (10/10 pairs, both engines 9 vCPUs) | **Measured CPU loss** 1.097× [1.051, 1.158] before uncharged host NAT. Footprint 0.748× [0.653, 0.782] strict win. API p50 0.975× non-inferior. API p99, request rate and transfer goodput inconclusive. The older 5-vCPU cohort recorded p99 1.70× with different image pins. [Evidence and reproduction](native-performance-progress.md#installed-default-w13-overlap-cohort) |
| W14 | Connection lifecycle: fresh, persistent, streaming, cancel, idle-resume, reconnect | yes | yes | yes, all six modes, both engines | D: `base-20261122T082410-0094` (idle-resume v3, 10/10 pairs, both engines 9 vCPUs) | **Idle-resume p50 loss** 1.128× [1.056, 1.468]. p95 and p99 inconclusive. Cleanup 0.353× and footprint 0.317× strict wins. CPU incomplete because of host NAT. [Current evidence](native-performance-progress.md#installed-default-w14-idle-resume-cohort), [historical modes](evidence/native-w12-w13-2026-11-18.md) |
| W3-v4 | Persistent storage: meaningful dataset, sustained read/write/checkpoint, declared working set and durability | yes | yes (pgbench fixed work) | no | D: `base-20261119T170441-5abe` (10/10 pairs, per-pair quiet wait) | D: durability unverified. Diagnostic ratios favor ctrs: rw tps 0.46 [0.45, 0.48], rw p95 0.27, checkpoint 0.41, restart 0.33, ro tps 0.81, CPU 0.81, footprint 0.064. Pgdata allocation ratio is 1.0001. The direct guest `fdatasync` probe (2,000 × 4 KiB writes to a named volume, three runs per engine) measured OrbStack p50 at 0.6–2.0 ms and ctrs at 0.26–0.28 ms. Host flush semantics require separate evidence. [Durability boundary](native-performance-progress.md#w3-migration-and-committed-state-cohort) |

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

Current ranking (2026-11-20, guest `e217587c…`): [Ranked measured
deficits](evidence/native-w12-w13-2026-11-18.md#ranked-measured-deficits).
States are kept apart: a **loss**, **inconclusive**, **tool-limited**
(the transfer tool, not the engine, may bound the result), **incomplete**
(a metric that omits part of the engine's cost, such as host-kernel NAT
networking) and **qualified** (none yet).

1. W12 v2 full-bind workflow 1.300× and measured CPU 1.163×. The Mac
   share's offline install and verification walk account for about 71%
   of the workflow gap. [Evidence](native-performance-progress.md#installed-default-w12-full-bind-cohort)
2. W13-overlap CPU loss 1.097× at the 9-vCPU default. W2 p99 and request
   rate are inconclusive in the current cohort.
   [Evidence](native-performance-progress.md#installed-default-w13-overlap-cohort)
3. CPU-only losses: W12-watch 1.07×, published-port upload CPU/GiB 1.08×,
   W14 fresh ~1.02–1.15×; NAT-path CPU is incomplete.
4. Guest→host bulk transfer: the 5–7× losses are closed to the tool's
   ceiling (0.72–0.94, tool-limited); container→Mac download 1.06
   inconclusive.
5. W6 sampled peak physical footprint 1.36× loss in the resumed
   installed-default cohort. The VZ helper retained the allocation
   across builds. [Evidence](native-performance-progress.md#installed-default-w6-cohort)
6. W7 sampled peak physical footprint is inconclusive and CPU accounting
   is incomplete. The offline W7 fixtures and the W4 and W8 cohorts still
   need native evidence. W5 has ten admitted pairs, with bind and volume
   p95 each required for frozen qualification. W10 has API, database
   and queue pairs, with whole-engine parity pending on an isolated
   OrbStack target.

`--pid host` is accepted and ignored by ctrs (no PidMode handling). That is
a compatibility gap and is not scored.
