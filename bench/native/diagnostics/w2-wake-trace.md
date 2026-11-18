# W2 wakeup placement trace

`w2_wake_trace.py` runs one normal pinned W2 trial per engine. A fixed delay
after the workload phase starts, the trial's privileged counter reader enables
the `ipi:ipi_send_cpu`, `ipi:ipi_send_cpumask`, `sched:sched_waking`,
`sched:sched_wakeup`, `sched:sched_switch` and
`sched:sched_wake_idle_without_ipi` tracepoints through tracefs for a fixed
window (default 2 s). It then restores the guest's original buffer size and
`tracing_on`. It refuses to run if the guest already has a tracer or
enabled events. No extra tool is installed. The script uses the pinned API
image's shell and the guest's tracefs.

```sh
TMPDIR=$PWD/.work/tmp python3 bench/native/diagnostics/w2_wake_trace.py \
  [--engines ctrs,orbstack] [--operations 50000] [--resource-lane matched]
```

Each `sched_waking` is classified by the waker's CPU and the target CPU's
running task. The task is reconstructed from `sched_switch`; a CPU not yet
seen in the window is `remote-unknown`. IPIs are counted by sending call site.
Per-success values divide window counts by the trial's rps × window
length, which is an estimate. Any ring-buffer overrun or dropped event
invalidates the window. A traced trial's timings are perturbed and never
scored. Raw `*-trace.txt` and `*-wake.json` files stay in the run's
results directory.
