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

## API system CPU profile

Job `e8b1976509aa4a94843dc16e1100c570` exited 0. All four cells replayed
the first equal-work block with concurrency 8 and seed 8, following 1,000
read-only warmup requests per cell. They verified 200,000 successful mixed
operations, clean teardown, 161 unchanged input receipts, and the same
write receipt as equal-work block 1. The first launch
`f713778b52b548e4bb817da8d0d32647` failed at import before creating a
result directory, registry or engine. Its receipts rechecked unchanged.

The guest helper sums stable API thread ticks and excludes profiler and
counter-reader processes. The bound on CPU quantization is 0.18 seconds
per trial, or 3.6 µs per successful request. This measurement and the
earlier cgroup totals have different counting scopes.

| Engine | Profile | API usage, µs/op | API user, µs/op | API system, µs/op | Work wall, s |
| --- | --- | ---: | ---: | ---: | ---: |
| ctrs | Off | 320.0 | 251.6 | 68.4 | 18.46 |
| OrbStack | Off | 276.2 | 226.4 | 49.8 | 23.04 |
| ctrs | On | 295.2 | 224.2 | 71.0 | 16.38 |
| OrbStack | On | 326.8 | 264.2 | 62.6 | 27.39 |

The 49 Hz collector recorded 692 ctrs samples and 678 OrbStack samples.
All nine API threads on each engine were sampled. Decoded and raw counts
agreed, with no loss or throttle records. The most common kernel leaf on
both sides was `wake_up_q`, with 66 ctrs samples and 22 OrbStack samples.
All 66 ctrs leaves landed at `ffff800080078fe4`, the stock
`wake_up_q+0x64` exclusive-store instruction from the
[earlier binary mapping](../../bench/native/diagnostics/w2-counters.md).
The per-thread sample-weighted cost estimates are 29.1 and 12.3 µs per
request for that leaf. Sampling cannot establish store retries, instruction
latency, or time spent off CPU. The ctrs profile also retained 178 unknown
libpython leaves.

API CPU and wall varied beyond 5% between off and on cells. The OrbStack
helper reached 1,322% CPU in the adjoining snapshots despite all eight
readiness commands returning 0. No observer budget pass or kernel change
follows. Run the capacity-matched workload to check whether normalized
system CPU still differs before selecting another experiment.

The profile uses the documented `syscall_pilot.trial` path with
`profile_kind='cpu', concurrency=8, seed=8`. Include both `bench/native`
and `bench/native/diagnostics` on `PYTHONPATH` for programmatic imports.
Use the pinned profiler archive and common registry preparation from the
[W2 profiler instructions](../../bench/native/diagnostics/w2-counters.md).
Run ctrs then OrbStack once with the profiler off and once with it on.
Use the accepted boot assets and the default-size capacity pair above.

## Capacity-matched fixed work

Job `aa8b70c7c2fc4d41893fa5463d766a11` exited 0 with clean native
teardown and 160 unchanged input receipts. The ten boundary-only cells
replayed the same five seeds and exact request counts. The write receipts
matched within every pair. All 500,000 requests succeeded and persisted
state was exact.

Both guests reported 17 vCPUs. Guest MemTotal was 46,321,221,632 bytes
on ctrs and 46,278,524,928 bytes on OrbStack, within 0.1%.
ctrs's configured memory ceiling was 45,084 MiB. Every trial had equal
CPU counts and guest MemTotal within 1% before and after work.

| Metric | ctrs median [range] | OrbStack median [range] | Paired ratio [95% interval] |
| --- | ---: | ---: | ---: |
| API CPU, µs/op | 362.9 [352.8–378.9] | 289.3 [276.4–324.5] | 1.266 [1.087–1.289] |
| API user, µs/op | 259.0 [250.9–269.7] | 239.4 [225.6–266.5] | 1.089 [0.941–1.115] |
| API system, µs/op | 104.7 [101.9–109.3] | 51.4 [49.9–58.5] | 2.020 [1.760–2.114] |
| Successful requests/s | 2,691 [2,527–2,755] | 2,086 [1,775–2,246] | 0.790 [0.644–0.819] |
| p99, ms | 5.66 [5.48–6.22] | 9.86 [8.03–13.89] | 0.631 [0.445–0.705] |

All 20 readiness checks passed. OrbStack helper CPU ranged from 0%
to 257% near trials. The system CPU deficit recurred in every pair under
these conditions. Timing and host resource qualification remain open.
The fixed-work batches changed both CPU allocation and memory across cohorts.
The next test isolates vCPU count at a common 8,192 MiB configured limit
on the same ctrs binary and guest assets.

To reproduce, use the same five-block fixed-work plan with boundary
sampling only, and reverse engine order on even blocks. Set `CTRS_CPUS=17`
and `CTRS_MEMORY_MIB=45084` for the guest envelope above. Derive the
ceiling from observed OrbStack MemTotal shifted by 20, plus
`runner.CTRS_GUEST_RESERVE_MIB`, on other supported configurations.
Require matching reported vCPU counts and MemTotal within 1% both before
and after each workload.

## ctrs vCPU count

Job `92611768ac9d4895ae440ce893cf05df` exited 0 and verified both private
engines stopped. All 160 frozen inputs rechecked. Five alternating
boundary-only pairs each verified 50,000 requests per cell and identical
acknowledged writes. Both sides used the same ctrs executable, boot assets,
images and 8,192 MiB configured memory. The 2-vCPU guest reported
8,408,772,608 bytes of MemTotal and the 17-vCPU guest 8,407,035,904 bytes.

| Metric | 17 vCPUs median [range] | 2 vCPUs median [range] | Paired cost ratio [95% interval] |
| --- | ---: | ---: | ---: |
| API CPU, µs/op | 376.1 [356.0–403.3] | 279.4 [268.9–359.2] | 1.301 [1.086–1.500] |
| API user, µs/op | 271.0 [254.4–289.5] | 218.8 [210.2–282.9] | 1.199 [0.996–1.377] |
| API system, µs/op | 106.5 [101.6–113.8] | 60.6 [58.6–76.3] | 1.736 [1.422–1.942] |
| Successful requests/s | 2,549 [2,332–2,718] | 3,180 [2,421–3,327] | 1.224 [0.979–1.426] |
| p99, ms | 6.49 [5.77–9.41] | 5.56 [4.92–8.57] | 1.110 [0.757–1.913] |

Ratios divide 17 vCPUs by 2 vCPUs for costs, and reverse for throughput.
The predeclared 1.10 lower bound for system CPU passed. This associates
the additional API system CPU with higher guest vCPU count in this
cohort. Host throughput and tail inference remain inconclusive.
The CPU result motivates an aligned profile to distinguish observed
wake-path changes from other scheduler and kernel work.

Reproduce using two fresh ctrs roots and the same pinned assets. Set
`CTRS_MEMORY_MIB=8192` for both private daemons. Set `CTRS_CPUS=2` and
`CTRS_CPUS=17` respectively before spawning them. Use the capacity-matched
five-block fixed-work recipe, substituting the two ctrs daemons and
checking their vCPU counts before and after each trial.

Raw trial SHA-256
`7b88cbfc71d9ea724ff831ab8b83f1a54617b2c2f3acd863aa6df9e0f8f105b7`.
Job status SHA-256
`88588bda0251cb8251a7602cc5c31439a20bc85dc3e072cb2753022169b5cb2d`.

## ctrs vCPU topology profile

Job `69619497509b458d9ce16c406dbfcaa2` exited 0. All four cells had the
same acknowledged writes and exact persisted state, with 200,000 successful
operations, both private engines stopped and all 161 receipts unchanged.
The profile replays C8 seed 8 with 1,000 warmup reads and 50,000 mixed
requests per cell. Use the same two private ctrs daemons as the vCPU-count
recipe and the 49 Hz profiler call above. Run 2 then 17 vCPUs in each mode.

| vCPUs | Profile | API system, µs/op | API total, µs/op | Work wall, s |
| ---: | --- | ---: | ---: | ---: |
| 2 | Off | 57.8 | 276.0 | 15.59 |
| 17 | Off | 102.8 | 368.2 | 19.10 |
| 2 | On | 74.6 | 311.2 | 17.68 |
| 17 | On | 125.8 | 394.4 | 19.91 |

The 2-vCPU profile recorded 48 `wake_up_q` leaves out of 732 samples.
All 48 landed at `ffff800080078fe4`. The 17-vCPU profile recorded 110
out of 892, with 109 at the same instruction. The sample-weighted estimates
were 20.5 and 50.3 µs per request for the whole leaf. These are estimates
from the profiled runs. The raw and decoded counts matched with no loss or
throttle records. All nine API threads were sampled on each side.

The associated system CPU gap also appeared with the profiler disabled.
Profiler-on total API CPU exceeded the off controls by 12.8% and 7.1%.
The observer budget remains open. Sampled instruction addresses cannot
distinguish additional wake calls from higher cost per call. Test that
distinction with the pinned W2 counters and the same vCPU topology before
selecting another product change. Earlier affinity and LSE results remain
separate, including the [rejected LSE candidate](native-lse-2026-11-16.md).

## ctrs wake counts by vCPU count

Job `327c401967f742b2a77ea5ea8612dfc5` exited 0. All four cells
verified exact persisted data for the same seed-8 workload and completed
200,000 successful requests. Both native engine identities stopped.
All 161 frozen inputs rechecked. Each counters-on cell collected 162
required per-thread selector counts, with zero missed probes.

| Event per successful request | 2 vCPUs | 17 vCPUs |
| --- | ---: | ---: |
| `FUTEX_WAKE` calls | 21.897 | 29.787 |
| Positive futex returns | 12.428 | 15.455 |
| `sched_waking` in API context | 17.753 | 20.423 |
| Futex `EAGAIN` returns | 0.945 | 1.835 |
| API task context switches | 20.499 | 19.410 |

The 17-vCPU cell issued 36.0% more `FUTEX_WAKE` calls per success with
the counters enabled. The positive-return count measures calls reporting
a wake. It does not count the number of tasks awakened. System task cost
with counters off was 64.4 and 122.4 µs per request for 2 and 17 vCPUs.
With counters on it was 103.2 and 162.0 µs per request. Those observer
effects leave ordinary wake frequency, per-call CPU, and exclusive-store
retries unmeasured. Keep the sampled-leaf and event counts separate.
No product change was selected.

Reproduce with the topology-profile recipe and `profile_kind='counters'`.
Keep off before on and 2 before 17 vCPUs within each mode. Use the
[documented counter coverage and cleanup checks](../../bench/native/diagnostics/w2-counters.md).
Job status SHA-256
`03a2fc5db9149283336d4a86b2f0ba8837cfe079bb67314bb3246404611a0086`.

## Wake-entry observer feasibility

Private source `7184d42` on `experiment/w2-wake-entry-only` reduces
the instrumentation to `FUTEX_WAKE` entry and `sched_waking`.
It installs one owned entry probe and uses the existing API thread
coverage checks. All 24 focused counter and profile tests pass.

Job `f202af4b1a184da98d5848a0ed26532c` exited 0 with 200,000 exact
operations, equal acknowledged writes, verified probe removal and both
native engines stopped. Both counters-on phases recorded all 18 required
selector cells and zero misses. All 161 frozen receipts rechecked.
The earlier wrapper job `b6726d2ea9154ddd8946570d43cfeae4` exited 1
before creating a result directory or engine because its output parent
was missing. The replacement creates the parent first. The original
161 frozen receipts also rechecked.

| vCPUs | `FUTEX_WAKE` calls/op | `sched_waking` events/op | Total API CPU off → on, s | System API CPU off → on, s | Wall off → on, s |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 20.565 | 16.410 | 15.81 → 15.97 | 3.33 → 3.93 | 18.28 → 17.94 |
| 17 | 31.301 | 20.929 | 19.81 → 18.74 | 5.78 → 5.97 | 20.82 → 18.81 |

The direction of the wake-count difference recurred under the reduced
probe set. The 2-vCPU system CPU observation still moved by 18%. The
17-vCPU wall difference was 9.6%. This single block cannot establish
ordinary uninstrumented wake frequency or certify the observer budget.
Keep the source parked and the two recorder versions separate.

Reproduce from `7184d42` using the topology-profile recipe with
`profile_kind='wake-counters'`. Create the results parent in the source
worktree first. Bind all runtime and image paths to the accepted assets.
Job status SHA-256
`79b76c74125d35ef4c87d2dc59e9261610a27fe5363d32a6c1c4db0b87ed4b16`.

## Ten-block observer comparison

Job `58086f0fccb04a1c94b4cb4320a4d961` exited 0 after 40 exact trials
and two million successful measured requests. All four cells in each
block agreed on writes and read/write counts. The 20 profile traces
passed the raw event checks. Native teardown and all 161 frozen
receipts rechecked. Both guest CPU counts were 17 and MemTotal stayed
within 1%. The plan reverses the engine and observer order in alternate
blocks. Each cell uses C8, seed `7 + block`, 1,000 warmup reads and
50,000 measured operations.

| Engine | Metric | Off median [range], s | On median [range], s | Paired on/off [95% interval] |
| --- | --- | ---: | ---: | ---: |
| ctrs | API CPU | 18.87 [17.93–23.15] | 19.83 [18.85–21.33] | 1.042 [1.023–1.088] |
| ctrs | Workload wall | 19.48 [18.37–24.73] | 20.10 [19.03–21.70] | 1.016 [0.996–1.062] |
| ctrs | API system CPU | 5.51 [5.15–6.46] | 6.42 [6.05–6.95] | 1.168 [1.105–1.205] |
| OrbStack | API CPU | 15.25 [14.13–19.17] | 15.81 [15.12–16.89] | 1.029 [0.970–1.143] |
| OrbStack | Workload wall | 23.26 [21.15–32.33] | 24.33 [21.64–27.53] | 1.043 [0.944–1.123] |
| OrbStack | API system CPU | 2.75 [2.48–3.43] | 3.31 [3.08–3.65] | 1.206 [1.103–1.343] |

All 80 readiness commands returned 0. Per-trial process snapshots
recorded the separate Niceforge VM at 90% CPU or higher in 48 snapshots
across all ten blocks. Preserve those blocks as diagnostics. Host
exclusivity remains unestablished, and the four primary CPU and wall
intervals each extend above the 1.05 observer limit. No qualified
observer pass follows.

Reproduce using the capacity-matched recipe with `syscall_pilot.trial`,
`profile_kind='cpu'`, C8 and seed `7 + block`. Run 10 blocks with a
distinct directory per engine and block. In odd blocks run ctrs then
OrbStack in each mode, off before on. Reverse both orders in even blocks.
Check capacity and process evidence before and after each trial. Compare
on/off within each engine using the median of matched ratios and the
same whole-block bootstrap procedure. Keep the samples and system/user
CPU breakdowns separate from the primary observer budget.

Plan SHA-256
`40fd44ea3ac59046b2431d5d02b62894243f2783c47f3d8b79bc65325222252e`.
Result SHA-256
`55c6472a621c8e36b05fad8445884c52add14f5969d05995ad2863c062b06f9b`.
Terminal status SHA-256
`6fbb6c2840782696770cce29242d9aa3e9be9d856021d6df1656d7e124dbfe4a`.

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
