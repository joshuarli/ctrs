# Guest Python attach/detach trace

`w2_uprobes_guest.py` captures a bounded trace in a new tracefs instance. Run as root in the guest with tracefs mounted and `CONFIG_UPROBE_EVENTS=y` (plus kprobe events). It creates only a tag-owned uprobe group, kprobe group, and instance; it does not reset global tracing. Use a fresh `npu` followed by exactly twelve lowercase hexadecimal digits for each capture. The state receipt is under `/run/ctrs-w2-uprobes`; preserve it until cleanup.

```sh
python3 w2_uprobes_guest.py setup npu0123456789ab 123,124
python3 w2_uprobes_guest.py start npu0123456789ab
python3 w2_uprobes_guest.py stop npu0123456789ab > capture.json
python3 w2_uprobes_guest.py cleanup npu0123456789ab
```

TIDs are explicit, unique, positive guest-global kernel TIDs (at most 128). The caller must validate task identity and namespace mapping before and after the measured phase. Each event uses the same `common_pid` filter. The trace instance uses the monotonic clock and a bounded per-CPU buffer (4000 KiB requested, at most 4096 KiB after kernel rounding). Stop returns JSON with raw trace, event formats, raw per-CPU statistics, exact owned profile rows, filters and identity receipt. It exits 2 if required loss counters or profile rows are missing, or if any trace buffer loss or kprobe misses are reported. Uprobe profile rows contain file, event, and hit count only; they do not prove zero uretprobe misses. Profile hit counts are global for each owned event and may include tasks outside the instance filter. Stop does not interpret trace events or determine a performance outcome.

Setup records the actual buffer readback, requires it within that range and checks the same value at start/stop. Setup requires each filter readback to match the requested predicate with whitespace ignored; any other kernel formatting fails closed. Stop marks the capture invalid if the selected monotonic clock or buffer size has changed or cannot be read.

The only supported file is `/usr/local/lib/libpython3.13.so.1.0`, size 5306944, SHA-256 `1cf1fea4c287605d994fcde537ad7e6d078bb4325e12a34f19b783a5f2badc3b`. Setup verifies the content and freezes device, inode, size and timestamps; start verifies them again. Cleanup verifies the complete receipt and all global definitions before any trace mutation and can remove those definitions if the library has since changed. Do not reuse a tag after a failed or interrupted setup without inspecting the retained receipt and tracefs state; an incomplete rollback deliberately refuses adoption.

The parent verified this exact ELF's dynamic symbols and executable LOAD mapping: `PyEval_SaveThread` file offset `0x177560` (size `0x60`), `PyEval_RestoreThread` file offset `0x177a40` (size `0xbc`). Entry and return probes use those offsets; they are not inferred from nearby symbols. The futex entry fetch `op=+8(%x0):u64` uses the ARM64 syscall register-frame convention in [counter_specs.py](../counter_specs.py); the return probe uses `r4096` and `ret=$retval:s64`. [Linux v6.18 uprobe documentation](https://raw.githubusercontent.com/torvalds/linux/v6.18/Documentation/trace/uprobetracer.rst) specifies the configuration, file-offset interface, and profiling interface. [Linux v6.18 uprobe source](https://raw.githubusercontent.com/torvalds/linux/v6.18/kernel/trace/trace_uprobe.c) lines 725–740 and 791–810 defines padded offset serialization and profile columns; [kprobe source](https://raw.githubusercontent.com/torvalds/linux/v6.18/kernel/trace/trace_kprobe.c) lines 1217–1235 and 1288–1308 defines serialization and miss counts.

[CPython 3.13.18 ceval_gil.c](https://github.com/python/cpython/blob/v3.13.18/Python/ceval_gil.c#L590-L610) shows SaveThread calling `_PyThreadState_Detach` and RestoreThread calling `_PyThreadState_Attach`. These probes cover those exports, not every GIL transition. Before interpreting a workload, the parent must run a native known-count task and verify exactly N filtered entries and returns for each export, validate task identities around the phase, and resolve phase-boundary and incomplete-interval cases. Futex timing inside or outside these intervals is elapsed time, not CPU-cost attribution. Native support, known counts, event format, filter behavior, and API phase edges remain unverified by this unit-only slice.


The known-count fixture is [`thread_state_probe.c`](../fixtures/w2/thread_state_probe.c).
Compile inside the pinned ARM64 Linux builder with
`gcc -O2 -std=c11 -Wall -Wextra -Werror thread_state_probe.c -ldl -o probe`.
Run `probe TAG 100` inside the pinned API image. It writes `READY`, accepts a
single `G` byte, performs exactly100 SaveThread/RestoreThread pairs, then writes
`DONE`. It accepts one further `G` for a second interval or `X` to finalize and
exit; at most two intervals are allowed, with30-second command waits.

On this host, OrbStack's Docker top PID differs from tracefs common_pid. A
unique-COMM discovery capture followed by a second interval using the observed
trace PID verifies the mapping for the same live task. Never infer a fixed PID
offset, substitute a namespace PID, or accept an empty filtered trace. Namespace
PID/start ticks and the unique root command remain identity evidence; the actual
trace PID is separately learned and validated. Native known-count results and
failed attempts: [attribution evidence](../../../docs/evidence/native-python-uprobes-2026-11-17.md).


Run `python3.14 bench/native/runner.py check uprobes` for the bounded source gate.
It selects owned trace lifecycle, the pure span parser and shared safety boundaries;
zero matches, required skips or a60-second timeout fail. Full suites and native
scenarios are separate. `uprobe_trace.analyze(capture, expected_comm=validated_tag)`
rejects empty, foreign, malformed and interior-unmatched events, and preserves
leading/trailing partial spans. Its counts do not attribute elapsed wait to CPU.
