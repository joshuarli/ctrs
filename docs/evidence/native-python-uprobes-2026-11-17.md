# Python thread-state attribution admission

The fixed-rate experiments did not select a runtime optimization. The next
question is how much of the observed futex activity occurs during Python
thread-state attach/detach calls. No GIL, CPU-cost or speedup conclusion exists.
The kernel and trace helper are private diagnostic candidates pending review
and native proof; main guest assets and product settings remain unchanged.

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
reads. Native validation remains pending until those changes are reviewed.
