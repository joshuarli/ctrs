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
