# W2 scheduler diagnostic

`scheduler_pilot.py` captures scheduler events for one real API process. The
command establishes trace support and thread identity. It does not qualify
performance or measure observer overhead.

The diagnostic requires the recorded native-tools archive, SHA256
`475ad5495772fa311084f9e15335c18aeffce3e8cb138c3d11e3f9a12b06883b`.
The archive contains the same perf binary and libraries for both engines.
From the repository root:

```sh
TMPDIR="$PWD/.work/tmp" python3.14 bench/native/diagnostics/scheduler_pilot.py \
  --tools-archive .work/tmp/w2-profile/native-tools.tar.gz
```

The default capture has 2,000 fixed operations after 1,000 warmup reads. The
load driver verifies responses and saves acknowledged writes. The diagnostic
checks every seeded and acknowledged database payload afterward. The normal
API, Postgres and Redis images must already be prepared. Raw records preserve
image identity, booted-engine ownership, tool hashes and task snapshots.

Both APIs use the same privileged diagnostic configuration. The bootstrap
requires CPython 3.13.18 and names application threads with a unique tag.
`Thread._bootstrap_inner` covers subclasses that override `run`. Every task's
tag and start identity must remain unchanged across the trace. Production
entrypoints and security defaults remain unchanged.

Kernel filters restrict waking, wakeup and migration targets to the tag. A
switch event requires the tag on its previous or next task. Switch-out samples
join the displayed namespace TID to the payload's global guest TID. Docker
`State.Pid` is not assumed to share that global namespace. An independently
verified kernel PID can corroborate the join.

The pinned perf binary starts disabled. The control FIFO enables capture and
returns the exact five-byte `ack\n\0` frame. A deliberate SIGINT ends capture.
Exit 130 is accepted only after that verified stop request and successful data
decode. The coordinator owns the profiler, project and VM lifecycle. Cancellation
cleans up those resources before restoring and re-raising the received signal.
Cleanup failures are saved and fail an otherwise successful run.

`sched_trace.py` separates blocked time, waking-to-wakeup elapsed time and
runnable wait. A wake can begin while the target still runs, before switch-out.
The parser preserves that overlap and charges only its later portion to the
off-CPU interval. A complete wake while the target still runs is counted
separately. Neither wake elapsed time nor scheduled residency is a task CPU
counter. CPU attribution still requires process counters or CPU samples.

Loss, malformed events, task reuse, filter leaks and ambiguous namespace joins
invalidate the result. Missing or duplicate wake pairs produce partial coverage.
Trace-edge time remains unknown. A boundary-only trace cannot report zero cost.
The diagnostic saves raw perf data, decoded events, exact application state,
CPU boundaries, parser output and cleanup status under `.work/native-perf/results/`.

An actual application profile still needs aligned operation boundaries, a
sampler/profiler on/off comparison, verified identical runtime inputs and an
exclusive host window. Event counts from a busy-host trace are diagnostic
observations. They cannot establish a CPU or latency win.

Application user and system CPU come from every required API thread's
`/proc/1/task/TID/stat`, using the guest's actual `SC_CLK_TCK`. This excludes
profiler exec processes that share the API cgroup. Missing threads, changed
starts or decreasing counters make CPU unknown. Records expose the counter
quantization bound. Short trials cannot substantiate a tight CPU budget merely
because the arithmetic returns many decimal places.
