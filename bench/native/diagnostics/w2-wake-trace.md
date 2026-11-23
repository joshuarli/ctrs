# W2 wakeup placement trace

`w2_wake_trace.py` runs one normal pinned W2 trial per engine. A fixed delay
after the workload phase starts, the trial's privileged counter reader enables
the `ipi:ipi_send_cpu`, `ipi:ipi_send_cpumask`, `sched:sched_waking`,
`sched:sched_wakeup`, `sched:sched_switch` and
`sched:sched_wake_idle_without_ipi` tracepoints in a private tracefs instance
for a fixed window (default 2 s). The instance uses the monotonic trace clock
to order events across CPUs. The reader removes the instance when its shell
exits. The script uses the pinned API image's shell and requires tracefs
instance support and all six tracepoints in the guest.

```sh
TMPDIR=$PWD/.work/tmp python3 bench/native/diagnostics/w2_wake_trace.py \
  [--engines ctrs,orbstack] [--operations 50000] [--resource-lane matched] \
  [--client-location host|guest]
```

Each `sched_waking` is classified by the waker's CPU and the target CPU's
running task. The task is reconstructed from `sched_switch`; a CPU not yet
seen in the window is `remote-unknown`. IPIs are counted by sending call site.
Per-success values divide window counts by the trial's rps × window
length, which is an estimate. Every CPU's stats must report both an
overrun count and a dropped-event count. Any overrun or dropped event
invalidates the window. A traced trial's timings are perturbed and never
scored. Raw `*-trace.txt` and `*-wake.json` files stay in the run's
results directory.
