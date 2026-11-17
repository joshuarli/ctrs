# Native W2 equal-work diagnostic

Run `w2-equal-work-primed-20261117` compares five blocks of 50,000 successful
published-port operations per trial, using eight persistent clients and a
0.3 write probability. Seed `7 + block` gives the same per-client requests
in all four cells. Every cell verifies the 500 seed rows and exact payloads
for its acknowledged writes. Setup, work and cleanup have separate CPU
boundaries. The operator accepted some background activity for this diagnostic.

| Blocks | Trial order |
| --- | --- |
| 1, 3, 5 | ctrs boundaries, OrbStack boundaries, ctrs periodic, OrbStack periodic |
| 2, 4 | OrbStack periodic, ctrs periodic, OrbStack boundaries, ctrs boundaries |

Both engines use the pinned common portfolio. ctrs uses its default-size
allocation, configured explicitly at 2 vCPUs and 8,192 MiB, with a fresh data
root. OrbStack uses the installed service and its existing resource settings.
The measured envelopes are 2 vCPUs and 8,408,772,608 guest bytes for ctrs,
and 17 vCPUs and 46,278,524,928 guest bytes for OrbStack. Results apply to
these configurations. The OrbStack helper also serves unrelated activity,
making its aggregate host CPU and footprint unsuitable for isolating W2.

The host load generator uses Python 3.14.8, Docker CLI 27.3.1 and Docker
Compose 2.29.7. The actual executable paths and hashes are in each engine's
`tools.json`. The recorded booted ctrs executable, kernel and initramfs must
match the accepted hashes in the [campaign checkpoint](../native-performance-progress.md).
The raw host process, gate, thermal, power and guest capacity snapshots sit
beside each trial's measurements. The generic trial metadata resolved the
initramfs hash from `guest/out` despite the explicit `CTRS_GUEST_DIR`.
The per-trial ownership receipts bind the loaded initramfs to
`6ae4d3abfb3be1f4dcc1edf200261a29e22ad96c922c2d677d5874df21abc8b2`.
Use those receipts and the frozen inputs for this batch's boot identity.

## First attempt

Job `5f4f8384cf954bd3bedeb0c10e587d6e` exited 1. Six trials completed
300,000 exact operations before the batch stopped. Block 1 had 34,932 reads
and 15,068 writes in each cell. Block 2 had 34,818 reads and 15,182 writes in
each of its attempted cells. The sixth trial had valid application results and
invalid host resource observations. The other 14 declared cells were unattempted.
The supervisor confirmed cleanup. The private ctrs daemon and VM stopped,
OrbStack had no project containers, networks or volumes left, and all 159
frozen input receipts rechecked unchanged.

The ctrs daemon log records idle VM shutdown at 21:15:01.300 UTC after 60
seconds of inactivity. The next pre-trial `docker info` reported zero guest
memory. Ownership discovery reported `expected distinct disk-owning VM helper: []`.
Compose then booted the VM at 21:15:02.344 UTC. The Docker socket stayed live. VM ownership requires an awake disk-owning
helper.

The revised harness primes each engine with the pinned API before every trial.
Priming is outside the setup, workload and cleanup CPU intervals. The package
default idle timer stays enabled. The control regression exercises priming
before measurement and checks that the original exception survives cleanup.
The W2 component check passes 106 tests with zero skips. In the primed run
the ctrs VM went idle again at 21:19:08.933 UTC. Priming booted it at
21:19:24.630 UTC before block 2's periodic trial. That trial verified all
50,000 operations and recorded all CPU boundaries and its periodic trace.

## Primed batch results

Job `4587075d90bc49baa5f7cebf9297cbb6` exited 0. All 20 cells completed
50,000 successful operations, with zero request errors and exact persisted
data. The four write receipts in each block were byte-identical. All
setup, workload and cleanup boundaries were complete, as were the ten
periodic traces. Native teardown and absence of OrbStack project containers,
networks and volumes were verified. All 159 frozen input receipts rechecked.
The tools matched between engines and rehashed to the captured values.

| Block | Reads per cell | Writes per cell |
| --- | ---: | ---: |
| 1 | 34,932 | 15,068 |
| 2 | 34,818 | 15,182 |
| 3 | 35,123 | 14,877 |
| 4 | 34,933 | 15,067 |
| 5 | 35,057 | 14,943 |

The table gives each side's median and observed range. The ratio is the
median of five paired ratios with a 95% percentile bootstrap interval.
Ratio direction favors ctrs below 1. Throughput uses OrbStack divided
by ctrs.

| Metric | Observer | ctrs median [range] | OrbStack median [range] | Paired ratio [95% interval] |
| --- | --- | ---: | ---: | ---: |
| API CPU, µs/op | Boundaries | 297.1 [289.4–346.4] | 322.8 [284.1–378.7] | 0.898 [0.842–1.073] |
| API CPU, µs/op | Periodic | 290.6 [284.8–309.0] | 319.9 [293.7–390.6] | 0.948 [0.731–0.970] |
| API user, µs/op | Boundaries | 236.2 [226.3–266.2] | 264.4 [231.7–308.4] | 0.866 [0.803–1.011] |
| API user, µs/op | Periodic | 224.4 [221.5–242.3] | 263.4 [239.5–319.6] | 0.900 [0.702–0.925] |
| API system, µs/op | Boundaries | 63.1 [60.9–80.2] | 58.6 [52.5–70.3] | 1.089 [1.013–1.368] |
| API system, µs/op | Periodic | 65.5 [61.1–68.7] | 56.6 [54.2–71.0] | 1.158 [0.861–1.261] |
| Successful requests/s | Boundaries | 2,956 [2,548–3,101] | 1,811 [1,542–2,527] | 0.588 [0.550–0.837] |
| Successful requests/s | Periodic | 3,069 [2,807–3,137] | 2,021 [1,520–2,327] | 0.692 [0.485–0.758] |
| p99, ms | Boundaries | 6.18 [5.29–8.21] | 12.19 [6.95–30.00] | 0.465 [0.235–0.888] |
| p99, ms | Periodic | 6.00 [5.23–6.08] | 10.42 [7.30–30.23] | 0.583 [0.173–0.787] |

Boundary-only total API CPU did not reproduce a consistent ctrs deficit.
The system component was higher on ctrs in all five boundary-only pairs
and three of five periodic pairs. In boundary-only controls the pair
ratios were 1.089, 1.013, 1.198, 1.023 and 1.368. This selects an on-CPU
profile of the guest API system component as a diagnostic. The 3% loss
threshold remains unresolved. There is no runtime change selected.

Periodic-to-boundary API CPU ratios were 0.970 [0.839–1.021] for ctrs
and 0.963 [0.933–1.212] for OrbStack. The corresponding wall ratios were
0.988 [0.831–1.011] and 0.876 [0.841–1.191]. The OrbStack interval leaves
the 5% observer budget unresolved, and the host conditions leave both
engines' observer qualification open.

All 40 readiness commands exited 0. Separate process snapshots recorded
OrbStack helper activity from 0% to 253% around trials. Unrelated VM work
was present at admission. The throughput comparison remains diagnostic,
and the aggregate OrbStack helper resource measurements remain unattributable.
The capacity-matched and fixed-offered-rate cells remain open.

Raw `trials.jsonl` SHA-256
`7c6424570b8178f1423318f08b5a018b82190d737f526fd83dff4e6fd1a5509d`.
Job status SHA-256
`267703ef6161e4a7ce734418de2d275b60728a0be40208846dac2941a50aaad9`.
The source used for the primed batch is the sampler and tests committed
in `a8c55cc`, captured before that documentation commit.

## Saturation diagnostic

Job `627d4248db6b46c79e65b1cf05416dde` exited 0 after five pairs with
alternating engine order. The boundary-only workload issued requests for
20 seconds at concurrency 8 and seed `7 + block`. All ten trials verified
exact data with zero request errors, for 402,065 successful operations.
Observed write fractions ranged from 29.65% to 30.35%. Native teardown
passed and all 160 frozen inputs rechecked, including the configured initramfs.
All 20 timing gates returned 0. The recorded OrbStack helper CPU ranged from
0% to 792% in the adjoining snapshots.

| Metric | ctrs median [range] | OrbStack median [range] | Paired ratio [95% interval] |
| --- | ---: | ---: | ---: |
| Successful requests/s | 2,485 [1,848–2,671] | 1,559 [1,073–2,114] | 0.631 [0.403–1.144] |
| p99, ms | 7.54 [7.27–19.14] | 12.37 [8.74–42.38] | 0.593 [0.172–2.189] |
| API CPU, µs/op | 348.1 [328.8–453.5] | 379.4 [310.4–486.5] | 0.918 [0.686–1.431] |
| API user, µs/op | 271.1 [257.0–359.6] | 308.2 [256.1–403.5] | 0.880 [0.637–1.374] |
| API system, µs/op | 77.1 [71.3–93.9] | 71.3 [54.3–83.1] | 1.082 [0.894–1.702] |

Saturation leaves each listed cross-engine comparison inconclusive. Keep
these results separate from the equal-work blocks. The raw trial SHA-256
is `7880592ace28b7e79dc22669e8de1fb3d692a24dbba19c86994cc391a1c5b47e`.
The job status SHA-256 is
`da825177cf71a2985e2bb5d98ba8ad02ffd85b2c53f0dc3f6442a6e4d1fa80b6`.

To reproduce saturation, prepare the same pinned registry and engines with
`sampler_pilot._prepared_engine`. Prime the API before each trial. Run
`runner.trial_w2(ctx, engine, 'saturation', 8, 20, .3, 7 + block,
sampling=runner.SamplingMode.BOUNDARIES)` once per engine for each of five
blocks, reversing the engine order in even blocks. Omitting the operation
limit selects duration mode. Capture the guest capacity and host conditions
before and after each trial. Normalize CPU using each trial's actual
successful count. Keep the raw results and write fractions for each pair.

## Reproduction

Reconstruct the signed host and guest assets described in the campaign
checkpoint. Verify their hashes. Reconstruct the pinned OCI layout with the
[common portfolio instructions](../../bench/native/fixtures/w8-v2/README.md).
Set `CTRS_GUEST_DIR` to the accepted kernel, initramfs and data disk template.

```sh
export TMPDIR="$PWD/.work/tmp" PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=bench/native
export CTRS_CPUS=2 CTRS_MEMORY_MIB=8192
python3.14 - <<'PY'
from pathlib import Path
from diagnostics.sampler_pilot import run_calibration

run_calibration(
    run_id='w2-equal-work-reproduction',
    portfolio_layout=Path('.work/native-perf/inputs/w8-portfolio-v2/layout'),
    ctrs_binary=Path('.work/tmp/readiness-main-target/release/ctrs'),
    pairs=5,
    operations=50000,
    concurrency=8,
)
PY
```

The recorded batch used `durable_job.launch` with a 40-minute deadline and
frozen receipts for the executable, inputs, layout and source. It used an
extent-based receipt for the sparse disk template. Run ID
`4587075d90bc49baa5f7cebf9297cbb6` binds the primed run to its terminal status.
A failed cell stays in the run and halts the batch. The declared order in
`plan.json` identifies any remaining unattempted cells.

Calculate per-trial API CPU cost from the workload's cgroup
`cpu.stat` deltas divided by successful operations. Usage, user and system
costs are separate. Each includes the counter-reader exec at the ending
boundary. Use client latency and requests per second from the completed load.
Calculate ctrs divided by OrbStack for CPU and latency, and OrbStack divided
by ctrs for throughput, separately in each observer mode. Calculate periodic
divided by boundaries for each engine's observer cost. Report the median
of the five paired ratios, a paired 95% percentile bootstrap interval
(`reporting.bootstrap_ci`), and each engine's observed range. Five blocks
provide diagnostic uncertainty and leave the ten-pair qualification gate open.
