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
| W2 | API fixed work, published port | yes | yes | yes (both lanes) | D: `base-20261118T090126-7b92`; M: `base-20261118T040927-4162`, `base-20261118T081857-9b61` | D: all cells win (CPU/success 0.874). M: latency/rps/footprint win; **CPU/success inconclusive 1.045 [1.015, 1.085]**, parked ([evidence](evidence/native-w2-ipi-2026-11-18.md)) |
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
| W12 | Shared workspace (Kutt v2.7.4, 2,830 packages, 92,306 files, 532 MB): offline `npm ci`, tsc + Next.js build, typecheck, Jest discovery, warm rebuild, ten-file change, branch restore; layouts full-bind / bind-source + volume deps / all-volume | yes | yes (`w12-v1`) | yes, all three layouts, D lane, exact receipts | D full-bind `base-20261118T120818-c079`; D all-volume `base-20261118T125148-c6aa`; M all-volume `base-20261118T144740-4485` | critical. **Loss.** D full-bind workflow 1.62 [1.59, 1.64] (install 2.34, test discovery 2.39); D all-volume 1.29 [1.28, 1.29] with host CPU 0.81; **M all-volume parity 1.02 [0.96, 1.04]** (the D gap is the 2-vCPU default). Bind-source + volume deps unmeasured ([evidence](evidence/native-w12-w13-2026-11-18.md)) |
| W12-watch | `tsc --watch` (fs.watch backend): save, atomic replace, create+import, rename, delete, five-file bursts, 140 results per trial | yes | yes (`w12-watch-v2`) | v1 proof both mounts; v2 oracle not yet run | no | critical. **ctrs bind: 140/140 missed** (no Mac→guest notifications). Volume: 23 burst results missed on both engines (engine-independent). Latency is exec-poll limited and not scored; esbuild polling stays the W5 condition |
| W13 | Artifact transfer up/down: published port, container↔container, container→Mac; 1 and 4 streams; byte-exact receivers | yes | yes (`w13-v2`) | yes | D: seven cells; M: published-port upload; rx64 (patch 0005): three host→guest cells | critical. **Guest→host loss:** container→Mac upload 7.0×, published-port download 5.1× (VZ vsock ceiling, bounded). Host→guest after patch 0005: published-port upload 1.02 (parity), Mac→container 1.03, 4-stream upload 1.25 loss. Container↔container **win** 0.82 ([evidence](evidence/native-w12-w13-2026-11-18.md)). Controlled egress unsupported (no owned endpoint) |
| W13-overlap | One transfer condition alongside W2: interactive latency | yes | no | no | no | depends on W13 |
| W14 | Connection lifecycle: fresh, persistent/streaming, cancel, idle→resume, reconnect | yes | yes (`w14-v2`) | yes, all six modes, both engines | D: fresh (v2), streaming, reconnect (v1) | **CPU loss**: fresh 1.30, streaming 1.75 (lateness p99 1.16 loss), restart 5.1. Reconnect p99 non-inferior, cleanup win. Fresh p50 5.7× is confounded by OrbStack SYN drops (p99 about 1 s); completion about 1.05×. Persistent, cancel, idle-resume: functional only ([evidence](evidence/native-w12-w13-2026-11-18.md)) |
| W3-v4 | Persistent storage: meaningful dataset, sustained read/write/checkpoint, declared working set and durability | yes | no (W3 v3 exists) | no | no | missing; durability/allocation limits stay explicit |

Existing DNS, UDP, IPv6 and host-access checks are correctness tests
(`tests/e2e.sh`, `conformance/`), not performance cells. `bench/net/*.py`
(CTRS-17) streams a repeating pattern without content hashes and reports
Mbps only. It is not reusable as a verified-transfer metric.

## Correctness findings from fixture work (2026-11-18)

- **Bind-mount file-change notification (open, critical).** Mac-side edits under
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

0. Bind-mount file-change notification: missing on ctrs (correctness).
1. W13 guest→host transfer: container→Mac upload 7.0×, published-port
   download 5.1× (VZ vsock device ceiling; needs a different device path).
2. W12 full-bind workflow 1.62× (install, test discovery on the Mac share).
3. W12 all-volume workflow 1.29× in the D lane only; M lane parity. The cause is the 2-vCPU product default, an owner decision.
4. W13 4-stream published-port upload 1.25× after patch 0005.
4a. W14 lifecycle CPU: fresh 1.30×, streaming 1.75× (lateness p99 1.16×).
5. W2 M-lane CPU per success: inconclusive, +4.5% median. Parked.
6. Unmeasured on this host: W1, W3–W11, W3-v4, W12 bind-source + volume
   deps, W12-watch v2, W13-overlap, W14 persistent/cancel/idle-resume cohorts. W6/W7 default-build losses are
   historical only.

`--pid host` is accepted and ignored by ctrs (no PidMode handling). That is
a compatibility gap and is not scored.
