# 2026-11-18: W2 CPU-per-success attribution on the M1 Max host

Host, binary and guest assets as in
[native-host-refresh-2026-11-18.md](native-host-refresh-2026-11-18.md):
signed ctrs `be929fe2…`, stock guest kernel `ea485341…` (built 2026-11-18
11:40:48 UTC), initramfs `6ae4d3ab…`, OrbStack 2.2.5, w8-v5 pinned stack.
All results are diagnostic/pilot evidence unless stated otherwise.

## Quiet-window confirmation of the matched-resource baseline

Predeclared repeat of `base-20261118T040927-4162` from a clean tree at
`d5d5191` (same binary, same parameters, 10 AB/BA pairs, 50,000 exact C8
operations, seed 7):

```sh
TMPDIR=$PWD/.work/tmp python3 bench/native/runner.py baseline --case W2 \
  --a ctrs --b orbstack --pairs 10 --operations 50000 --concurrency 8 \
  --write-ratio 0.3 --seed 7
```

Run `base-20261118T081857-9b61`: 20/20 trials correct, zero errors,
`worktree_dirty: false`, no reporter metadata gaps. Host load average
1.65 before and 2.74 after; the OrbStack helper used 24% CPU in the post
snapshot.

| Metric | Median ratio (ctrs/OrbStack) | 95% CI | Pilot assessment |
| --- | ---: | --- | --- |
| rps (inverted) | 0.7444 | [0.7394, 0.7495] | strict win |
| p50_ms | 0.7435 | [0.7419, 0.7511] | strict win |
| p95_ms | 0.6594 | [0.6480, 0.6704] | strict win |
| p99_ms | 0.6094 | [0.6010, 0.6202] | strict win |
| cpu_seconds_per_success | 1.0454 | [1.0154, 1.0845] | inconclusive |
| peak_total_rss_kb | 0.2128 | [0.2084, 0.2385] | strict win |
| peak_phys_footprint_bytes | 0.3509 | [0.3390, 0.3912] | strict win |

**Disclosure found later:** a campaign-owned ctrs daemon from the
reconstruction session (`.work/tmp/bootcheck2`, pid 89456, binary
`readiness-main-target`, idle VM) stayed resident from 04:08 to about 08:40 local.
It was co-resident during this batch and the earlier
`base-20261118T040927-4162` batch. It ran no workload. It was stopped with
SIGTERM at about 08:40. Neither batch is qualification evidence.

## Where the extra CPU goes

Per-process workload-phase CPU (median µs per successful request) and the
API container's cgroup `cpu.stat` from the same trials:

| Run | Engine | VM / helper | ctrs daemon | Guest API user | Guest API system |
| --- | --- | ---: | ---: | ---: | ---: |
| 040927 | ctrs | 925.3 | 38.0 | 391.5 | 149.4 |
| 040927 | OrbStack | 878.5 | — | 352.1 | 65.3 |
| 081857 | ctrs | 908.0 | 38.3 | 388.0 | 150.3 |
| 081857 | OrbStack | 903.0 | — | 351.3 | 65.1 |

The host-side difference matches the guest API **system** CPU gap
(≈85 µs/op, 2.3×). The ctrs port-forwarding daemon costs about 38 µs/op,
and guest user CPU is within about 10%.

## Guest IPI and context-switch counters

`7e88096` adds a diagnostic reader to every W2 trial: an owned, idle,
privileged, network-less container from the pinned API image reads
`/proc/stat`, `/proc/meminfo` and `/proc/interrupts` before the API
`cpu.stat` read and after the workload. Both engines mask
`/proc/interrupts` in ordinary containers. ctrs masks it like Docker and
does not implement `systempaths=unconfined`; OrbStack honors that option.
`--privileged` exposes it on both.

One diagnostic pair, `base-20261118T083123-b6db` (20,000 ops, C8, seed 11,
9 vCPUs each), per successful request:

| Counter | ctrs | OrbStack |
| --- | ---: | ---: |
| IPI1 function-call interrupts | 22.95 | 5.26 |
| IPI0 rescheduling interrupts | <0.05 | 0.08 |
| Context switches | 55.7 | 30.2 |
| Guest API system µs | 160.2 | 65.2 |

On arm64 6.18, `ttwu_queue_wakelist` sends wakeups to an idle or
non-cache-sharing CPU as call-function IPIs. Under Virtualization.framework,
every IPI to a WFI-idle vCPU is a VM exit and a host thread wake.

## SCHED_MC candidate re-tested with the IPI counters: rejected again

Hypothesis: ctrs's guest lacks `CONFIG_SCHED_MC`, so `cpus_share_cache()`
is false for every vCPU pair and every remote wakeup takes the wakelist IPI.
Predeclared: IPI1/op ≥50% lower, API system CPU ≥25% lower, then a
paired batch if host CPU/success improves ≥5% with p99/rps regressing ≤3%.

The candidate kernel differs from stock only by `CONFIG_SCHED_MC=y`
(verified `.config` diff). It was built with the pinned Debian image and
the same source and patches. Image SHA-256 `06273f8712d5624f3275ba6fcd57182e214a141ba02983e2593cb9d292802d63`,
18,800,648 bytes, built 2026-11-18 16:37:28 UTC. An interleaved
ctrs-vs-ctrs driver ran 3 blocks with alternating order, 20,000 exact C8
operations and matched seeds per block. It verified `/proc/version` before
every trial and refused to adopt a running daemon. All six trials were exact.
Runs: `mcab-stock-20261118T084107`, `mcab-mc-20261118T084107`.

| Per success | Stock median | SCHED_MC median | Per-block ratios |
| --- | ---: | ---: | --- |
| IPI1 | 22.83 | 26.12 | 1.077, 1.150, 1.144 |
| Context switches | 55.25 | 59.55 | 1.032, 1.076, 1.078 |
| API system µs | 151.7 | 162.8 | 1.092, 1.087, 1.070 |
| Host CPU µs | 969.5 | 1040.1 | 1.107, 1.074, 1.073 |
| rps | 1871 | 1837 | 0.924, 0.988, 0.982 |

The hypothesis is refuted. A shared LLC still sends a wakeup aimed at an
idle CPU through the wakelist IPI, so missing cache topology does not
explain the gap. Retain stock. An earlier attempt, `mcab-*-20261118T083814`,
is invalid. A daemon orphaned by a crashed probe script was adopted, so
both arms booted the stock kernel. The guarded rerun above replaces it.

## OrbStack guest observations (read-only)

From a privileged throwaway container of the pinned API image:

- Kernel `7.2.12-orbstack-00394-gbecdd6130068 #1 SMP PREEMPT` (Oct 22 2026),
  erofs root, `workqueue.power_efficient=1`, `cgroup.memory=nokmem,nosocket`,
  9 vCPUs.
- Cache topology: per-CPU L1, L2 shared by CPUs 0–3, L3 shared by 0–8.
  ctrs reports L1/L2 shared by 0–8 with no L3.
- `cpuidle` current driver `none`. `kallsyms` has `cpu_do_idle`,
  `default_idle_call` and `cpu_idle_poll`, but no `poll_idle` or haltpoll
  symbols, so OrbStack idles through WFI, as ctrs does. Paravirt hooks
  (`pv_time_init`, `pv_is_native_spin_unlock`) are present.
- No `/proc/config.gz`.

Stock arm64 6.18 has no `TIF_POLLING_NRFLAG`, and haltpoll cpuidle is
x86-only, so a polling-idle shortcut is not available in the ctrs guest.
OrbStack's fewer IPIs and context switches therefore come from fewer
wakeups aimed at idle vCPUs, not from idle polling. Plausible sources are
wakeup placement or futex/scheduler behavior in 7.2 and wake latency in its
VMM. None of these is established.

## Installed-default lane (first measurement on this host)

`5e42acb` adds `baseline --resource-lane installed-default`. ctrs runs its
product defaults (2 vCPUs, 8 GiB), ambient `CTRS_CPUS`/`CTRS_MEMORY_MIB`
are refused, and the lane is recorded in `workload_params`, so it never
pools with the matched lane. The reporter's budget-parity gate applies
only to the matched lane. OrbStack runs as installed (9 of 10 CPUs).

```sh
TMPDIR=$PWD/.work/tmp python3 bench/native/runner.py baseline --case W2 \
  --a ctrs --b orbstack --pairs 10 --operations 50000 --concurrency 8 \
  --write-ratio 0.3 --seed 7 --resource-lane installed-default
```

Run `base-20261118T090126-7b92`: clean tree, 20/20 correct, zero errors,
load average 1.52 before and 2.92 after.

| Metric | Median ratio | 95% CI | Pilot assessment |
| --- | ---: | --- | --- |
| rps (inverted) | 0.6450 | [0.6245, 0.6536] | strict win |
| p50_ms | 0.6389 | [0.6140, 0.6458] | strict win |
| p95_ms | 0.6203 | [0.5988, 0.6252] | strict win |
| p99_ms | 0.5653 | [0.5508, 0.5744] | strict win |
| cpu_seconds_per_success | 0.8742 | [0.8239, 0.8825] | strict win |
| peak_total_rss_kb | 0.1038 | [0.1014, 0.1248] | strict win |
| peak_phys_footprint_bytes | 0.1519 | [0.1389, 0.1694] | strict win |

Medians per success: ctrs host 646 µs (VM 614, daemon 33), guest API
system 87 µs; OrbStack host 740 µs, guest API system 62 µs. ctrs IPI1 is
about 10.8 per success, against 23 at 9 vCPUs. The earlier
`base-20261118T084511-97e4` used explicit `CTRS_CPUS=2
CTRS_MEMORY_MIB=8192` without a declared lane. The reporter rejects it,
and it remains a pilot only.

This is a single same-day pilot batch, not qualification. It shows that
the matched-lane CPU gap grows with guest vCPU count. It does not close the
matched-lane cell.

## Wakeup placement trace (matched lane)

[`w2_wake_trace.py`](../../bench/native/diagnostics/w2-wake-trace.md), run
`wake-20261118T091715`. One exact 50,000-op C8 trial per engine, 9 vCPUs
each, a 2 s tracefs window 6 s into the workload, zero lost events, both
trials correct. Per successful request (estimated from rps × window):

| | ctrs | OrbStack |
| --- | ---: | ---: |
| `sched_waking` | 28.9 | 18.0 |
| wakee on waker's CPU | 6.3 | 9.6 |
| wakee on remote idle CPU | 21.5 | 7.5 |
| wakee on remote busy CPU | 1.1 | 1.0 |
| IPIs sent | 23.2 (`ttwu_queue_wakelist` 22.5) | 5.0 (`wake_up_q` 3.5) |
| `sched_wake_idle_without_ipi` | 0 | 0.42 |
| `sched_switch` | 55.6 | 29.1 |

The largest waker→wakee pair is uvicorn→uvicorn: 18.4 per request on ctrs
and 8.6 on OrbStack, from the same image and load. The remaining wakers are
similar in size on both engines: postgres, plus each engine's port-forward
relay (ctrs guest `init` and `kworker/0:1`; OrbStack process `7` and
`orbstack-agent`). The extra CPU therefore comes from the API's own
thread-handoff wakeups. Three quarters of them land on an idle vCPU, and
each of those costs an IPI and a VM exit.
OrbStack's 7.2 guest records `sched_wake_idle_without_ipi`, so some of its
idle CPUs poll and accept a wakeup without an IPI. Stock arm64 6.18 cannot.
Its IPI call sites also differ, which indicates a different wake path. This
justifies a bounded kernel-series experiment: the same `ctrs.config` and
patches on 7.3.5 stable.

## Next profiling boundary

Measure which wakeups land on idle vCPUs, and from which API futex paths:
per-wake target-CPU idle state and waker/wakee placement. Use
`sched_wakeup` target CPU vs `idle_cpu` at wake. A kernel-version
candidate (newer stable scheduler/futex) is a bounded architectural slice
only if that trace shows the placement difference. Do not repeat the
SCHED_MC, LSE or HZ/PREEMPT candidates without new causal evidence.
