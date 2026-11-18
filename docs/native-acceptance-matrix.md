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
| W12 | Shared workspace: offline dependency materialization, build/typecheck/test discovery, warm rebuild, multi-file change/branch switch; layouts full-bind / bind-source + volume deps / all-volume | yes (this doc) | no | no | no | critical, missing |
| W12-watch | Real watcher: save, atomic replace, create, rename, delete, bursts across files; backend recorded; missed/stale counts | yes | no | no | no | critical, missing; esbuild polling stays the W5 condition |
| W13 | Artifact transfer up/down: published port, container↔container, container→Mac; 1 stream and modest parallel; exact hashes | yes | no | no | no | critical, missing; controlled egress unavailable unless an owned endpoint exists |
| W13-overlap | One transfer condition alongside W2: interactive latency | yes | no | no | no | depends on W13 |
| W14 | Connection lifecycle: fresh, persistent/streaming, cancel, idle→resume, reconnect | yes | no | no | no | missing; preserve protective session limits |
| W3-v4 | Persistent storage: meaningful dataset, sustained read/write/checkpoint, declared working set and durability | yes | no (W3 v3 exists) | no | no | missing; durability/allocation limits stay explicit |

Existing DNS, UDP, IPv6 and host-access checks are correctness tests
(`tests/e2e.sh`, `conformance/`), not performance cells. `bench/net/*.py`
(CTRS-17) streams a repeating pattern without content hashes and reports
Mbps only. It is not reusable as a verified-transfer metric.

## Ranked OrbStack deficits (this host)

1. W2 M-lane CPU per success: inconclusive, +4.5% median. Parked.
2. Every other cell is **unmeasured** on this host. W6/W7 default-build
   losses are historical only and must be re-measured.
