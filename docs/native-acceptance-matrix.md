# macOS campaign acceptance matrix

Single status table for [the campaign](campaign-native-performance.md). The
work queue and next action live in
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
| W1 | Compose up API+PG+Redis, restart | yes | yes | no | no | unmeasured |
| W2 | API fixed work, published port | yes | yes | yes (both lanes) | D: `base-20261118T090126-7b92`; M: `base-20261118T040927-4162`, `base-20261118T081857-9b61` | D at 2 vCPUs: all cells win (CPU/success 0.874). D at the 5-vCPU default (`base-20261119T053846-4c9b`): rps 0.70, p99 0.56, footprint 0.032, all strict wins; CPU/success was unmeasured (useful-work counts differed within every pair). D fixed work, 50,000 operations (`base-20261119T164542-ece1`, 10/10 pairs, per-pair quiet wait): rps 0.64 [0.61, 0.65], p50 0.66, p99 0.49 [0.41, 0.59], footprint 0.019, all strict wins; **CPU/success 1.03 [1.01, 1.05] inconclusive** (measured, not a win). M: latency/rps/footprint win; **CPU/success inconclusive 1.045 [1.015, 1.085]**, parked ([evidence](evidence/native-w2-ipi-2026-11-18.md)) |
| W3 | PG transactions, checkpoint, restart | yes | yes | no | no | unmeasured |
| W4 | Queue workers 1/4/16 | yes | yes | no | no | unmeasured |
| W5 | Marked esbuild watch (bind, volume) | yes | yes | no | no | unmeasured; 5 edits per trial cannot support tails |
| W6 | Default-builder Rust+C CI build | yes | yes | no | no | unmeasured; historical **loss** |
| W7 | Default buildx → loaded images | yes | yes | no | no | unmeasured; historical **loss** |
| W8 | Pull-to-healthy from local registry (w8-v5) | yes | yes | yes (functional gate, both engines) | no | unmeasured |
| W9 | Parallel fixed build/test jobs | yes | yes | no | no | unmeasured |
| W10 | Interrupt/recover service/DB/queue | yes | yes | no | no | unmeasured; engine-interruption parity needs isolated OrbStack |
| W11 | 12 h mixed reliability | yes | yes (parked branch) | no | n/a | unqualified |

## Filesystem and networking coverage (2026-11-18 steering)

| ID | Workflow | Spec | Impl | Functional | Compared | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| W12 | Shared workspace (Kutt v2.7.4, 2,830 packages, 92,306 files, 532 MB): offline `npm ci`, tsc + Next.js build, typecheck, Jest discovery, warm rebuild, ten-file change, branch restore; layouts full-bind / bind-source + volume deps / all-volume | yes | yes (`w12-v1`) | yes, all three layouts, D lane, exact receipts | D full-bind `base-20261118T120818-c079`; D all-volume `base-20261118T125148-c6aa`; M all-volume `base-20261118T144740-4485`; M full-bind `base-20261118T161928-8d7f` | critical. **Loss on full-bind.** Kernel k15 (patches 0013–0014, LOOKUPs −70%): M full-bind 1.23 [1.19, 1.30] (`base-20261119T064359-1f0c`), D 1.28 [1.24, 1.32] (`base-20261119T072809-bc40`): unchanged, because the Mac's virtiofs server flattens near 8,300 small files/s against OrbStack's 16,600–20,900. Kernel k14: **M full-bind 1.25 [1.23, 1.27]** (`base-20261119T023414-9164`; install 1.96, test discovery 2.15: Mac-share cost); D full-bind 1.52 at 2 vCPUs (`base-20261119T031525-7297`), **1.26 [1.21, 1.30] at the new 5-vCPU default** (`base-20261119T054737-9a02`); D all-volume 1.29 at 2 vCPUs, **1.02 [1.00, 1.03] inconclusive at 5 vCPUs** (`base-20261119T050726-d2cd`, host CPU 0.85 strict win); M all-volume parity 1.02. Before the kernel work D full-bind 1.62, M 1.44. On `bf2ea2b` M full-bind `base-20261119T214453-bfcc` is invalid (6 valid pairs; 4 rejected at 2.1–2.9 cores busy outside the engines): 1.25 [1.19, 1.28], install 2.04, test discovery 2.15, as before. D full-bind `base-20261119T171357-15a5` is invalid (pair 4 rejected, load 14.2 mid-trial despite the per-pair quiet wait); its 9 pairs give 1.33 [1.25, 1.34], install 2.01, test discovery 2.26: the loss stands, not re-scored. D bind-source + volume deps `base-20261119T181642-550e`: invalid (8 valid pairs, 2 rejected for mid-trial load); its 8 pairs give workflow 1.01 [0.99, 1.03], install 0.95, warm rebuild 1.07, CPU 0.89, footprint 0.094: near parity, not scored; again `base-20261119T225149-5f9a`: invalid by one pair (pair 3 at 2.0 cores outside the engines), 9 pairs give workflow 1.016 [0.998, 1.019], test discovery 0.95, warm rebuild 1.04, CPU 0.91: two unscored cohorts agree that volume deps remove nearly all of the full-bind loss ([evidence](evidence/native-w12-w13-2026-11-18.md)) |
| W12-watch | `tsc --watch` (fs.watch backend): save, atomic replace, create+import, rename, delete, five-file bursts, 120 results per trial | yes | yes (`w12-watch-v2`) | yes, v2 both mounts | D bind: `base-20261118T174235-c732` (k7, 10 pairs), `base-20261118T212940-afee` (k8, 3 pairs), `-215543-cd5e` / `-220619-ab8e` (k10 / k9, 2 pairs each), `base-20261118T234824-4ef9` (k11, 2 pairs), **`base-20261119T013944-e94b` (k13, 10 pairs)** | **Scored on the splice build (`base-20261120T014028-c06b`, 10/10 pairs, outside-CPU admission): edit-to-result p50 0.90 [0.90, 0.91] strict win, p95 0.98 [0.96, 1.01] non-inferior, CPU 1.07 [1.06, 1.08] loss, footprint 0.07.** Earlier on `bf2ea2b` (`base-20261119T191032-ccdc`, 5 pairs, pilot only, no verdict): edit-to-result p50 0.92 [0.89, 0.93], p95 0.97, CPU 0.91, all trials correct. **Parity (kernel k13, 10 pairs; k14 `base-20261119T040227-c39c` and k15 `base-20261119T080909-d4d8` 600/600 on both, 5 pairs each):** ctrs bind 1,200/1,200 correct, 0 stale; OrbStack 1,200/1,200; detection p50 0.65 s on both, p95 2.0 s on both. Before notifications ctrs missed 120/120. Native-semantics kernels (k8–k10) reached 97/120, missing the in-place edits after an atomic replace that `tsc` also misses on volumes on both engines; k11 raises an in-place Mac edit as a rename of the name onto itself, as OrbStack does. |
| W13 | Artifact transfer up/down: published port, container↔container, container→Mac; 1 and 4 streams; byte-exact receivers | yes | yes (`w13-v2`) | yes | D: seven cells; M: published-port upload; rx64 (patch 0005): three host→guest cells | critical. **Splice build (`4fdff1d`): published-port download 0.93 [0.92, 0.94] tool-limited (was 1.64–1.78× loss), upload 0.69 tool-limited, container→Mac upload 0.95 [0.94, 0.97] tool-limited (was 2.23×); ctrs time 0.56× / 0.77× / 0.43× its previous build with OrbStack unchanged (`base-20261120T000004-f614`, `base-20261119T235251-7eb8`, `base-20261120T000743-a0eb`). Every guest→host cell is now at the tool's ceiling, so no win is claimed. Container→Mac download (Mac→container bytes) regressed to 1.21 spliced and is back to 1.06 [1.01, 1.18] inconclusive with that direction copied (`ade0b80`, `base-20261120T030035-4a43`; pre-splice 1.04).** Before: **Guest→host loss, reduced:** over the NAT relay and legs (protocol 9), container→Mac upload 2.23× (was 7.0×), published-port download 1.64× (was 5.1×); every ctrs trial records its transport (nat/nat_leg 30, vsock 0). One NAT flow caps near 1.9 GB/s here. Host→guest after patch 0005: published-port upload 1.02 (parity) over vsock; the leg-only build regressed it to 1.14×; `439b14e` (client bytes over vsock) restored 0.96 [0.85, 1.07] inconclusive, CPU/GiB 1.17× loss (`base-20261119T134339-6c08`); Mac→container 1.03 over vsock and 0.99 [0.97, 1.02] tool-limited over NAT (`base-20261119T133649-3bc7`, non-regressing, not a win), 4-stream upload 1.25 loss. Container↔container **win** 0.82 ([evidence](evidence/native-w12-w13-2026-11-18.md)). Controlled egress unsupported (no owned endpoint) |
| W13-overlap | One transfer condition alongside W2: interactive latency | yes | no | no | no | depends on W13 |
| W14 | Connection lifecycle: fresh, persistent/streaming, cancel, idle→resume, reconnect | yes | yes (`w14-v2`) | yes, all six modes, both engines | D: fresh (v2), streaming, reconnect (v1) | **CPU loss**: fresh 1.30, streaming 1.75 (lateness p99 1.16 loss), restart 5.1. Reconnect p99 non-inferior, cleanup win. Fresh p50 5.7× is confounded by OrbStack SYN drops (p99 about 1 s); completion about 1.05×. Persistent, cancel, idle-resume: functional only ([evidence](evidence/native-w12-w13-2026-11-18.md)) |
| W3-v4 | Persistent storage: meaningful dataset, sustained read/write/checkpoint, declared working set and durability | yes | yes (pgbench fixed work) | no | D: `base-20261119T170441-5abe` (10/10 pairs, per-pair quiet wait) | D: every timing metric a strict win: rw tps 0.46 [0.45, 0.48], rw p95 0.27, checkpoint 0.41, restart 0.33, ro tps 0.81; CPU 0.81, footprint 0.064; pgdata allocation 1.0001. **Not a storage-leadership claim yet:** the flush contracts are not shown equal. Bound from the same records: OrbStack commits at 1.4–1.5 ms p50 and about 4,000 tps with 8 clients, which rules out a permanent-storage flush (`F_FULLFSYNC`, about 12 ms per WAL sync in ctrs's `Full` diagnostic, `native-ci-wal-2026-11-17.md`) per commit; whether OrbStack orders writes more strongly than ctrs's host `fsync` (for example a barrier flush) is unknown (ready queue item 5) |

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

0. Bind-mount file-change notification: **parity** (W12-watch bind 1,200/1,200 on kernel k13, 10 pairs; 0/120 before).
1. W13 guest→host transfer: container→Mac upload 7.0×, published-port
   download 5.1× (VZ vsock device ceiling; needs a different device path).
2. W12 full-bind workflow 1.28× D (5 vCPUs) / 1.23× M on kernel k15 (`base-20261119T072809-bc40`, `-064359-1f0c`; install 1.9×, test discovery 2.2–2.4× on the Mac share). The Mac's virtiofs server is throughput-bound (about 25,000 requests/s, one request queue); only fewer or off-critical-path requests can help.
3. W12 all-volume D lane: closed by the half-the-Mac vCPU default (1.02 inconclusive, was 1.29 at 2 vCPUs; `148136f`).
4. W13 4-stream published-port upload 1.25× after patch 0005.
4a. W14 lifecycle CPU: fresh 1.30×, streaming 1.75× (lateness p99 1.16×).
5. W2 M-lane CPU per success: inconclusive, +4.5% median. Parked.
6. Unmeasured on this host: W1, W3–W11, W3-v4, W12 bind-source + volume
   deps, W13-overlap, W14 persistent/cancel/idle-resume cohorts. W6/W7 default-build losses are
   historical only.

`--pid host` is accepted and ignored by ctrs (no PidMode handling). That is
a compatibility gap and is not scored.
