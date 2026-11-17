# Python thread-state attribution admission

The fixed-rate experiments did not select a runtime optimization. The next
question is how much of the observed futex activity occurs during Python
thread-state attach/detach calls. No GIL, CPU-cost or speedup conclusion exists.
The helper and parser are integrated in c2a7fab. Native capability and API
captures pass on both engines. The diagnostic kernel remains private.
CPU-cost and observer-overhead acceptance remain open.

The stock generated kernel configuration has CONFIG_ARCH_SUPPORTS_UPROBES=y but
CONFIG_UPROBE_EVENTS unset. Linux documents the latter as required for tracefs
uprobes. It also requires file offsets rather than runtime symbol addresses,
and its uprobe_profile records filename, event and hits, without a miss column.
[Linux uprobe tracing](https://raw.githubusercontent.com/torvalds/linux/v6.18/Documentation/trace/uprobetracer.rst).

The pinned common API libpython3.13.so.1.0 is 5,306,944 bytes, SHA-256
`1cf1fea4c287605d994fcde537ad7e6d078bb4325e12a34f19b783a5f2badc3b`, already extracted
under `.work/tmp/py-leaf/`. xcrun llvm-objdump --dynamic-syms confirms exported
PyEval_SaveThread at0x177560/size0x60 and PyEval_RestoreThread at0x177a40/size0xbc.
The executable LOAD has file offset and virtual address both zero, so these are
also file offsets. This uses exact exports and executable-segment mapping,
not nearest-symbol guesses for unresolved PCs. Re-extract the library from the
pinned API image and verify its hash before using these offsets.

CPython3.13.18 maps SaveThread to detach and RestoreThread to attach. These
exports do not cover every GIL path, and elapsed call duration includes waits.
[CPython implementation](https://raw.githubusercontent.com/python/cpython/v3.13.18/Python/ceval_gil.c).

The native admission must first verify capability and exact known counts. A C
program dynamically loads the pinned libpython, initializes Python, and blocks
at a READY barrier using C read/write. After the controller starts its exact
PID-filtered trace, it performs N SaveThread/RestoreThread pairs and reaches a
DONE barrier before finalizing. C barriers avoid additional Python I/O calls in
the counted interval. Require N entries and N returns for each export, complete
trace/profile coverage, unchanged input/library identity and owned cleanup on
both engines. Compile with the pinned ARM64 Linux toolchain and inspect required
libc symbol versions before copying it into the API image. The prepared source
is `.work/tmp/w2-uprobe-known-count-20261117/probe.c`.

Only then run a bounded API trace with the same exported-call probes and actual
ARM64 futex entry/return events. Check thread identities at phase boundaries.
Correlate futex calls inside/outside attach/detach intervals, retain unmatched
phase edges explicitly, and require loss-free capture. Keep this elapsed-wait
classification separate from contemporaneous on-CPU costs and observer overhead.
Do not promote a diagnostic kernel, change scheduler policy or rerun a rejected
kernel optimization based on probe availability alone.


The first kernel build stops before compilation because generated CC_VERSION_TEXT
uses the target-prefixed compiler name. Its actual compiler SHA matches the prior
pinned binary. A separate v2 build invokes the original gcc alias and keeps the
strict allowed configuration diff: UPROBES and UPROBE_EVENTS only. Initial failed
container d77da67b… and input receipts remain preserved; no Image from that
attempt is eligible. Private source worker f125c2f3 owns this build. Source helper
31783d7 has had its complete diff reviewed; the same-session correction adds
strict filter readback, stop-time clock/buffer validation and bounded library
reads. Those changes are reviewed and integrated. The native outcomes follow.


## Kernel and helper source admission

Private kernel e5b9a33 adds one requested configuration line; generated differences
are only UPROBES and UPROBE_EVENTS. Parent inspected that diff, recipes and pinned
compiler checks. Image SHA-256 is
`4a06b32165c0b5e916a4db737cb99e03aa0c3683fcd8289edfda77735faef963`,
18,868,232 bytes (+67,584, about0.36%). Generated config SHA is
`cfd859d034d6c7db90e761c050f8d555591f0cbdd90e9b1dd57f0254f2992379`.
Six-CPU/6GiB build exits0, stopped/noOOM. It remains a private diagnostic kernel,
never a promoted performance candidate. Initrd remains6ae4d3ab; actual native
boot hashes are checked through open VM assets. Main kernel assets remain intact.

Helper source b2a6761/f042b21 is reviewed and integrated after initial and single
worker correction. Parent independently passes11 focused tests in0.145s. The
known-count C binary is71,272B (under128KiB ceiling), needs GLIBC2.17/2.34 only,
and builds with pinned compiler/noOOM at55,848,960B peak, under256MiB. No full
suite or qualification ran.

Initial native job `e440a1719ac549c8a50c4a8a73f6ecdf` exits1/clean before counted
calls because exact buffer readback differs: requested4096KiB yields4099KiB.
A separate owned-instance query records4KiB guest pages, then request4000 selecting
4000KiB on all17CPUs. Source now requests4000, accepts kernel rounding only within
4000..4096KiB, records the actual value, and requires that exact value during
capture. The4MiB per-CPU ceiling is unchanged.13 focused tests pass in0.170s,
including acceptable rounding and above-ceiling failure/owned rollback.

v2 job `144188a9bf5846b3a7e1ab67a6205c41` passes ctrs: exact100 entries and100
returns for both exports, zero futex calls in this uncontended C loop, complete
all-CPU trace statistics/profile rows and clean removal. It then exits1/clean
before OrbStack setup: its default top table has PID/USER/TIME/COMMAND rather
than the ctrs UID/PID/PPID/C/STIME/TTY/TIME/CMD layout. Separate mapping query
records both namespace PID/start ticks and unique command in the four-column
root table. v3 job `1902295e9dcf4155896cd708bff377ce` under
`.work/tmp/w2-uprobe-known-count-v3-20261117/job` tests OrbStack alone with
header-based column mapping. Keep its result separate from the earlier failed
batch, retaining the valid ctrs functional leg. No timing claim follows.


## Native PID admission and API capture

OrbStack v3 exits 1 with clean teardown: its Docker top PID selects zero events.
The unique C task's actual trace PID differs from both its namespace PID and
Docker top PID. No fixed offset is valid. Preserve this failed capture.
COMM-only discovery v4 (`8f22527fa10e4e2ba794a3a1de8712b3`) passes exactly
100 entries and returns for both exports. The two-interval v5 proof
(`15bd7ff818a5463faf7cdec455b5e0ad`) then discovers trace PID541956 and passes
another exact100 calls through the canonical PID filter on the same live task.
Both runs have zero loss, complete profile rows and clean probe removal.
Their roots are `.work/tmp/w2-uprobe-known-count-v{4,5}-20261117/`.
All101 v5 receipts were checked before later source edits. The ctrs v2 proof
above and OrbStack v5 establish capability, without qualifying timing.

API job716e5838fba34db1b5c0125510e1133d under
`.work/tmp/w2-uprobe-api-proof-20261117/` exits0 with clean teardown. Both engines
complete500 exact C4 operations after the same read-only warmup and discovery.
Discovery learns all five stable task IDs from unique COMM values. All17 CPU
loss counters and kretprobe misses are zero. Source/library/boot identities and
all97 frozen receipts pass before subsequent edits.

| Capture | Save entries and returns | Restore entries and returns | Futex entries | In Save | In Restore | Outside | Unknown edge |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ctrs | 14,993 each | 14,993 each | 25,252 | 6,632 | 11,073 | 7,487 | 60 |
| OrbStack | 14,391 each | 14,391 each | 12,928 | 3,244 | 4,009 | 5,650 | 25 |

Each capture has four trailing futex entries without returns and no unmatched
export entries. Interior pairing is complete. About84.8% of the excess futex
entries occur within the two exports. This is count correlation, not CPU-cost
attribution. Guest CPU ticks are too coarse for the short capture.
`analysis-verified.json` reproduces the private classifier through the integrated
strict parser, including explicit edges and rejection of empty filtered traces.
The `uprobes` component gate passes43 tests, zero skips, in0.375s. No full suite.

Raw `ctrs/off/work-capture.json` SHA-256 is
`1ce48cb14d244b66915248b943bd43896f6f50010a2e46219d164a0b570aa387`.
OrbStack capture SHA-256 is
`c3fa46775e71675a01653264fb070c57ddb1c9ced0d514ae261aecc9bc3bf6ab`.
The C fixture is now `bench/native/fixtures/w2/thread_state_probe.c`.
Before reusing the private API coordinator for fault scenarios, move trace
cleanup into the load wrapper's `finally`, before pilot cleanup deletes the
API container. The successful run removed all probes, but its outer cleanup
ordering is not accepted for injected failure. Do not edit frozen run inputs.
