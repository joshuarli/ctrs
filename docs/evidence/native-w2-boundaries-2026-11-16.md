# W2 client path and host accounting, 2026-11-16

No product policy is selected from these diagnostics. The fixed client-path
batch completed all six blocks and 24 phases: 1.2 million correct operations,
exact payloads, matching client/boot identities and clean teardown. Timings remain
unqualified. The predeclared screen required a consistent API CPU contrast of
at least 10% across all three rounds; the observations do not meet that screen.

## Published port versus Compose bridge

Both locations use the same fixed load source, concurrency four, seed seven and
50k operations after warmup. The guest client is a distinct pinned API-image
container on the Compose bridge, with bounded tmpfs and verified source hash.
Source and output transfers use exec outside the measurement boundary. Native
5k proofs and cancellation pass; the original OrbStack tmpfs archive-copy failure
is preserved separately. Source: 6b62edd plus parent repairs e271003.

API CPU guest/host ratios, preserving each round and profiler mode:

| Engine | Profiler | Round 1 | Round 2 | Round 3 |
| --- | --- | ---: | ---: | ---: |
| ctrs | off | 0.877 | 1.091 | 0.981 |
| ctrs | on | 0.895 | 1.015 | 0.961 |
| OrbStack | off | 0.995 | 1.048 | 0.923 |
| OrbStack | on | 0.857 | 1.029 | 0.977 |

This changes client placement, runtime (host 3.14 versus pinned guest 3.13.18)
and delivery cadence. It does not isolate forwarding CPU alone. Guest engine
CPU includes the client, so host/guest engine-CPU ratios would compare different
scopes. Complete wall/tail observations remain in the raw analysis; none is a
qualified win or regression. Do not select a forwarding change from this batch.

Raw coordinator/analysis: `.work/tmp/w2-client-path-explore-20261116/`.
Durable job `20c045e9e8f84ccbaf4c7fe98a4fc7a3` exits 0 with cleanup complete.
SHA-256 receipts:

- `job/status.json`: `116fe5f2c4ae2508fd9fba51846ee17850d2ab41e5bc3eb441f003ac5c770230`
- `analysis.json`: `529fa36d083c6ae4d88bb11f3dcf7b3fd4ce3d7c98b54009b60ebefb8d9b3c90`
- `plan.json`: `10a05fb929cfce93a79cf32dfb499c6c1ec272fcd0869e7e8f225f91f9a1231c`

## Resolve private Python leaves before naming a mechanism

The common OCI image supplies an exact 5,306,944-byte libpython ELF, SHA-256
`1cf1fea4c287605d994fcde537ad7e6d078bb4325e12a34f19b783a5f2badc3b`.
Its GNU build ID `d704afba0a1ffc97a890285b221a04d8a8660fb1` matches recorded
perf build-ID metadata on both engines. Compressed layer and uncompressed diff-ID
were verified against the pinned manifest. The executable PT_LOAD has file offset
and virtual address zero. For the stock ctrs mapping at `0xffff9a9f0000`, runtime
PC minus that base gives the ELF/file offset.

The top four unresolved libpython leaf PCs map to `0xf3fac` (nine samples),
`0xf8b18` (seven), `0x137bc4` (six), and `0xf3f9c` (six). Actual instructions are
ordinary loads, an add, and register restoration in these ranges. The ELF lacks
a full symbol table. Nearest exported objdump labels are misleading: their
recorded function sizes do not cover these private PCs. Do not name those
private routines from a nearest-symbol label or label all unknown work as GIL.
These 28 leaves out of 305 unresolved samples do not isolate a dominant private
spin loop or establish instruction latency/causal cost.

Artifact, mapping/fault observations, build-ID checks and disassembly:
`.work/tmp/py-leaf/`. The read-only scout could not execute a decoder; the parent
independently verified the ELF, mappings, actual disassembly and symbol bounds.

## Check host accounting and core placement

A private C probe compiles directly against this host's SDK `rusage_info_v6`.
Host calibration agrees with Python process CPU after Mach-timebase conversion;
known guest compute checks correct results and increasing native instruction
coverage. This remains an experimental observer, separate from the accepted
canonical V0 sampler. It is not a clock correction or a scored sampler upgrade.

One 50k off/on W2 block per engine then records V6 boundaries. The ctrs VM helper
spends 96.8%/95.3% of observed CPU time on performance cores; effective QoS time
is almost entirely legacy. OrbStack's helper is also predominantly legacy and
performance-core time is 92.6%/96.8%, with unrelated work still in its totals.
This does not establish a credible priority/core-type deficit for a QoS change.
Do not change VZ queue policy merely because its serial queue has no explicit QoS.

The field mapping follows [Apple's rusage implementation](https://github.com/apple-oss-distributions/xnu/blob/main/osfmk/kern/bsd_kern.c)
and [CPU-kind accounting](https://github.com/apple-oss-distributions/xnu/blob/main/osfmk/kern/recount.h).
The local SDK and native calibration bind the actual probe ABI. Raw source,
binary, host/guest calibrations, plan and W2 rows:
`.work/tmp/native-core-probe-20261116/`. Durable W2 job
`8576e61b146841989f59bd07e2f3da64` exits 0 with cleanup complete; all four phases
verify exact 50k work. New observers and host contention leave timing unqualified.

Next: use a genuinely quiet host window for the saved ten-block canonical
observer confirmation. If unrelated work prevents it, profile the default-build
zlib boundary; do not repeat rejected kernel/client-location/QoS guesses.
