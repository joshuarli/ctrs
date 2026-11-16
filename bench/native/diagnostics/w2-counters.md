# Collect W2 syscall and wake counts

The stock ctrs guest lacks FTRACE_SYSCALLS. This pilot uses the same ARM64
syscall-entry kprobes on both engines, with the same pinned perf and libraries.
It attaches to every tagged API thread, without inheritance. Software counters
record task-clock, context switches and migrations. Syscall counters record
futex, read/write, epoll_pwait and recvfrom/sendto entries. `sched_waking` counts
wakes generated in API thread context. It does not measure target wake latency.

Use preinstalled common W8 service refs. A saved `refs.json` from the common
portfolio or W11 preparation supplies immutable API/PostgreSQL/Redis references:

```sh
TMPDIR=$PWD/.work/tmp python3.14 bench/native/diagnostics/syscall_pilot.py \
  --tools-archive .work/tmp/w2-profile/native-tools.tar.gz \
  --image-refs .work/native-perf/results/w11-mixed-20261116T063716-8565/ctrs-host/refs.json \
  --ctrs-binary .work/tmp/disk-expand-target/release/ctrs --operations 5000
```

The runner's default ctrs capacity follows OrbStack. Explicit CTRS_CPUS and
CTRS_MEMORY_MIB override that policy. Verify online CPUs, MemTotal and each API
thread's recorded affinity. A functional pilot does not assert allocation equality.
Keep installed-default, disclosed resource-matched and identical-builder results
separate. The build driver is unchanged.

Each engine runs a fresh seeded stack with the profiler off and on. Both phases
perform identical fixed useful work after 1,000 warmup reads. A live helper enables
counters before signaling readiness and disables them after the load finishes.
Actual helper and host workload intervals are preserved separately. CPU samples
for every API thread exclude profiler/helper exec processes. User/system CPU use
guest clock ticks and expose quantization. Perf task-clock uses milliseconds;
normalized application CPU fields use seconds per successful operation.

Every seeded and acknowledged database payload is checked. Process/start identity,
actual daemon/guest artifacts, image digests/diff IDs, application hashes, profiler
and helper sources are preserved. Every required thread/event must have a finite
count, positive runtime and 100% scheduled coverage. Missing, duplicate, unsupported
or partially scheduled counters make all totals unknown. These are counting events,
not sampled event records; no trace buffer is decoded.

Probes use a random owned group and verified definitions. Cleanup deletes only
those definitions and confirms absence. Cancellation stops the owned profiler,
removes its probes and project, and restores the original signal exit status.
SIGKILL of the coordinator cannot run cleanup; retain the run receipt for explicit
ownership checks before removing any orphan. Never clear global probe definitions.

The pilot saves raw profiler-off/on controls. A predeclared 5% CPU and wall-time
observer budget needs exclusive, interleaved confirmation with differences above
CPU quantization. Short busy-host records leave overhead inconclusive. No corrected
CPU-efficiency ratio is derived by multiplying published medians. Scored W2 still
requires exclusive aligned 50k application profiling, with saturation separate.

## Validate command and return decoding

`futex_decode_pilot.py` uses an identical pinned static ARM64 C binary on both
engines. Build `futex_calls.c` with the pinned GCC 14.2.0 image and verify the
recorded source/binary hashes. The local compilation receipt is
`.work/tmp/futex-calls/build.json`.

```sh
TMPDIR=$PWD/.work/tmp python3.14 bench/native/diagnostics/futex_decode_pilot.py \
  --proof-binary .work/tmp/futex-calls/proof \
  --tools-archive .work/tmp/w2-profile/native-tools.tar.gz \
  --image-refs .work/native-perf/results/w11-mixed-20261116T063716-8565/ctrs-host/refs.json \
  --ctrs-binary .work/tmp/disk-expand-target/release/ctrs
```

The single thread is pinned to CPU0. Each of 100 iterations performs one WAIT
with a mismatched value, one WAKE with no waiter, and one WAIT with a 1ns timeout.
Expected totals are 300 calls, 200 WAITs, 100 WAKEs, 100 EAGAIN, 100 ETIMEDOUT,
100 zero returns and zero positive returns. FIFO commands bound work. The running
C executable hash is checked through `/proc/1/exe`. This validates argument and
return decoding, not latency or VM scheduling performance.

One entry probe fetches the ARM64 syscall wrapper's saved second argument. One
return probe fetches its signed return, with maxactive 4096. Required missed-probe
counts are zero. Filters use explicit opcode comparisons. The pinned perf rejects
tracepoint `name=` terms, so raw selectors appear as ordered event blocks. This
known-count proof verifies that ordering before those labels are used on W2.
Probe event names include the random run tag to disambiguate miss accounting.

Probes are removed before the C process exits. The stop writer may exit 137 when
PID1 terminates its namespace; its raw status is preserved and the C process must
still exit 0. Native cleanup confirms owned probes absent. These are expected
control-process semantics, not recovered application failures.

## Interpret detailed W2 counts

Current instrumentation is `w2-counters-v2-futex-commands`. `counter_specs.py` owns
probe definitions, opcode filters, return-probe capacity and selector order for
both the host and mounted guest helper. The C conformance driver uses the same
facts. Historical v1 parser records remain separate.

V2 requires 18 selectors for every API thread (90 cells with five threads),
including ordinary WAIT, WAIT_BITSET, WAKE and return classifications. Zero missed
entry/return probes is required independently of perf counter coverage. Probe
names contain the run tag, so kernel miss accounting cannot alias another group.
Unclassified commands or negative returns remain explicit. Each thread can have
one call crossing a boundary; selector activation skew is a separate limitation.
These edge effects are not silently replaced with zero.

The output preserves CPU, event counts and operation denominators from each raw
trial. Counts cannot identify where a return originated: a zero return may be a
successful wait or a WAKE that found no waiter. Positive returns identify WAKE
calls that reported waking threads, not the sum of threads woken. EAGAIN indicates
a changed expected value. It is not a measured spin duration or CPU cost.

Counter callbacks can perturb scheduling. A profiler-on trial with a larger CPU
budget or more futex calls cannot be treated as ordinary product performance.
Validate overhead and use a separate low-rate on-CPU profile before attributing
the frequency difference to a material share of the real CPU deficit.

## Sample on-CPU work separately

Add `--profile-kind cpu` to the bounded command above. This uses `cpu-clock`
with a fixed 20,408,163ns CPU period (nominal 49Hz), native DWARF stacks and
explicit API TIDs without inheritance. It installs no syscall probes. The same
live enable/disable boundaries, profiler-off control, pinned inputs, exact data
verification and owned cleanup apply. `cpu.data`, decoded `cpu.txt`, raw event
dump and stderr remain in each on trial. Loss/throttle records, raw/decoded
sample-count disagreement, unexpected tasks and changed identities invalidate
analysis. `cpu_profile.py` retains unresolved frames and unsampled threads.

Per-thread leaf-cost estimates use only that profile's thread CPU and sample
fractions divided by its successful operations. Inclusive stacks overlap and
cannot be summed. These are native stacks, not Python source stacks; tick
quantization and sparse samples limit attribution. The 5k functional pilot
`w2-cpu-20261116T082957-1e4f` passes both engines, with 93/55 samples and no raw
loss/throttle records. Every thread is sampled, but some have only two samples.
Adaptive-frequency feasibility run `082819-3763` is kept separately; do not pool.
SIGTERM `083059-fc2b` preserves coordinator exit -15 and clean owned teardown.
Neither pilot establishes observer overhead or a material mechanism. Before
selecting a change, require exclusive interleaved 50k controls within the 5%
CPU/wall observer budget and own-sample attribution of at least 25% of the
contemporaneous CPU-per-success gap. Off-CPU waits remain a separate measurement.
