# Native CI concurrency and PostgreSQL WAL diagnostics

These bounded native ARM64 macOS experiments retain the frozen common portfolio,
explicit signed host fda62467/initrd6ae4d3ab/stock kernel35087713, 17vCPUs and
45091MiB ctrs ceiling. The resident control disables sleep. It is separate from
installed-default acceptance. OrbStack's existing guest capacity matches within1%.
Shared host/OrbStack Linux-machine exclusivity remains unproved; no scored
timing, confidence interval, parity or speedup follows from the numbers below.
No product configuration changed.

## W9 fixed build/test jobs

Job18475b48d7164b2c9d725778f7edee09 under
`.work/tmp/w9-concurrency-profile-20261117/job` exits0 with clean owned teardown.
Three AB/BA/AB pairs run16 fresh Marked esbuild/CLI jobs at each concurrency
1/4/8/16:384 successful jobs, identical exact CLI results and executable bundle
SHA-256 `0823c3960d93d71ea9b2e9bd1fe032659016ddf97b757cc35b38108ae677ef0b`.
All native counters are complete, with no resource errors; all89 frozen receipts
remain unchanged. The pinned image, Node/npm/esbuild and source lock are checked
by `ci_jobs`; the actual running ctrs binary/boot assets are also verified.

Diagnostic medians for each16-job phase:

| Concurrency | ctrs wall s | OrbStack wall s | ctrs CPU s | OrbStack CPU s |
| --- | ---: | ---: | ---: | ---: |
| 1 | 2.094 | 6.170 | 2.243 | 12.350 |
| 4 | 0.550 | 2.830 | 2.179 | 8.379 |
| 8 | 0.339 | 1.856 | 2.362 | 6.701 |
| 16 | 0.235 | 1.433 | 2.463 | 5.906 |

No concurrency meets the predeclared ctrs loss screen (>=10% CPU cost increase in
every pair). Select no contention patch from this experiment. The measured host
process scope excludes Docker clients/coordinator and includes OrbStack helpers
that can serve unrelated Linux machines, so its totals are not exclusive Docker
work attribution. Sampled physical peaks are2.11–2.13GB ctrs and12.50–12.56GB
OrbStack; unequal resident state prevents a memory-win claim. This tests app
build jobs, not concurrent Docker buildx or default-build W6/W7 leadership.

Raw result SHA-256:
`bc916f3c81173e0a30ab94800f208d91668b7d76837c0f3316f8e4d9bfdb31d9`;
analysis `ab24dc264079b0a6ee7dd2489bcd29a376db702a405009c1008831625eff4e3d`.
Reproduce with `runner.trial_w9` and the frozen portfolio's digest reference for
`marked`; all16 jobs and all four concurrency levels are required. The saved
driver/plan freeze the three-pair order and comparison controls.

## W3 synchronous commit boundary

Job da7234e183d44305ad7731dbf95b328a under
`.work/tmp/w3-wal-boundary-20261117/job` exits0/clean teardown. Three AB/BA/AB
pairs each use a fresh uniquely labelled Postgres17.12 ARM64 container/volume,
network none and frozen portfolio digest. `fsync`, `synchronous_commit`,
`full_page_writes` and diagnostic `track_wal_io_timing` are all on; guest sync
method is `fdatasync`. No flush guarantee is weakened.

Each leg migrates two tables, commits1,000 independent transactions (one4096-byte
deterministic text row plus counter update), checkpoints, restarts Postgres and
checks exact row count/key sum/min/max length/all-row MD5/counter. Every leg
passes `1000|499500|4096|4096|dff3b9f0bf86164666a5c7dea2a27128|1000`
before and after restart.
These repeated text payloads compress: their logical4MiB size is not an
incompressible4MiB I/O fixture. Exact observed WAL delta is320,607bytes and
1,000 syncs per leg. All89 frozen receipts remain unchanged; native phase/trace
counters are complete with no errors.

| Pair | ctrs transaction wall s | OrbStack wall s | ctrs WAL sync ms | OrbStack WAL sync ms |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0.261 | 1.359 | 107.554 | 1188.080 |
| 2 | 0.248 | 1.192 | 90.387 | 1050.189 |
| 3 | 0.520 | 1.465 | 187.127 | 1141.535 |

WAL timings are after-minus-before `pg_stat_wal` values, not totals since init.
Wall/CPU are unqualified diagnostic observations. No repeated ctrs cost loss is
selected here. Sampled physical peaks1.33–1.43GB ctrs versus12.09–12.52GB
OrbStack remain shared-state observations. This is orderly database restart,
not engine-crash, power-loss durability or complete W3 workload qualification.

Raw result SHA-256:
`49493eaddffb2a8db2ef8c1bf81ab62f11b41b8d5b1da709068bee9ddd583b9a`;
plan `bb492601098a23a732baf80d3a7ef50dd1474437ec66acd0563ab9a19d7b9c34`.
SQL is recorded in the frozen plan/`transactions.sql`. The next comparison
isolates the SDK disk synchronization mode on current identical source; the
existing `Fsync` default and private `Full` candidate have different contracts.
Do not credit their cost difference as equivalent-durability performance.

## Synchronization contract cost

Job1198bea5d5d247df96bd38c28aee6ad9 under
`.work/tmp/w3-sync-mode-20261117/job` exits0, clean owned teardown, all94 frozen
receipts checked unchanged after completion. Three Fsync/Full, Full/Fsync,
Fsync/Full pairs repeat the exact SQL/outputs/settings above on ctrs only.
Both signed binaries are freshly built in separate target directories from
3ce96e0 and private be06882, differing in the VZ synchronization selection and
comment. The previously parked Full patch is rebased onto the current balloon
repair; guest assets remain identical. The product default stays Fsync.

| Pair | Fsync transaction wall s | Full wall s | Fsync WAL sync ms | Full WAL sync ms |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0.330 | 4.007 | 112.329 | 3777.492 |
| 2 | 0.241 | 4.064 | 86.661 | 3732.397 |
| 3 | 0.271 | 4.166 | 98.313 | 3893.264 |

All6 exact checkpoint/restart checks and complete native counters pass. Sampled
footprints are1.33–1.43GB. This diagnostic points at the stronger flush boundary;
it neither measures equivalence with OrbStack nor qualifies host power loss.
The SDK defines Full as permanent-storage synchronization, while Fsync does
not guarantee movement from a drive's internal cache. Do not promote weaker
flush behavior on these costs. No speedup is established on this shared host.

Both binaries are6,613,984bytes (+16 versus prior fda62467): Fsync SHA-256
`6b3c7175931e745114fcca1ac9b24acc1106934dc7704c2092b19043e6fe600d`;
Full `9fec13707a623a984914670e3976599e99c4134c36d03f2ed098630054861a5b`.
Separate named package builds finish2.17s/11.61s; those are verification logs,
not comparable build-time measurements. A shared-target switch was discarded
before collecting a baseline to avoid stale cross-worktree artifacts.
Signed artifact paths are `.work/tmp/w3-sync-artifacts/ctrs-{fsync,full}`.
Result SHA-256 and further candidate decisions follow the continuation record.
Next bounded test changes only Cached→Uncached while retaining Full, checking
whether avoiding double caching removes material cost without weakening flushes.

Synchronization result SHA-256:
`6576e4ee36be8c139d5d1892bfdbf3c9d89dd81f090e7307155f611a1e5b5065`;
plan `052cc1cf194af8d80e307fa0615c8f73fb6c9de193145f6d8810fb15f90ece1d`.
All94 input receipts are unchanged. Private Full source is be06882 in
`.work/wt/np-w3-full`, based on current3ce96e0; main remains Fsync.

## Uncached Full rejected

Job4240274e8c684e9eb07829b0765f0ce8 under
`.work/tmp/w3-full-cache-mode-20261117/job` exits0 with clean owned teardown.
The private b030772 changes only Cached to Uncached atop be06882. Six fresh
database legs retain Full synchronization and all prior SQL/settings/oracles.
All exact checkpoint/restart checks and native counters pass; all97 receipts
are unchanged. The initial launcher failed before creating a job on a wrong
artifact path; it started once after resolving the actual isolated build output.

| Pair | Cached Full wall s | Uncached Full wall s | Cached CPU s | Uncached CPU s |
| --- | ---: | ---: | ---: | ---: |
| 1 | 4.044 | 4.046 | 0.590 | 0.690 |
| 2 | 3.976 | 4.008 | 0.789 | 0.628 |
| 3 | 4.047 | 4.029 | 0.634 | 0.610 |

The predeclared10% median wall reduction and every-pair improvement are absent:
candidate rejected. Observed WAL sync costs remain about3.7–3.8seconds per1,000
commits. Sampled footprint1.43–1.45GB and signed size6,613,984bytes fit the
declared diagnostic budgets, but cannot rescue the failed improvement criterion.
No caching default changes. Uncached artifact SHA-256:
`088e3709948a494201993b04b30d7496d30cb369b55915902aedb2d0ec3b28a2`.
Result SHA-256:
`5455185d2ab008101f93b9ded64628d5c4d11e623911bf21a2733935fdbb4b9d`;
plan `c4a1d81f0850e6338b6f0d5ac1a167dd262eae0ad1b0df0415adf5e9101d7939`.

## Full flush wait localized

Native trace-v3 job3225b0d7264d4a21b1fb4490f667911f under
`.work/tmp/w3-full-flush-trace-v3-20261117/job` exits0 with owned cleanup complete.
All1,000 exact committed rows/counter/checksum survive checkpoint and orderly
restart. All95 frozen receipts are unchanged. The source helper is integrated
through d209805, with bounded resources70 tests/zero skips and its7 focused
tests passing. Full suites remain manual-only.

The raw trace contains exactly4,000 records:1,000 backend `fdatasync` entries,
1,000 successful returns,1,000 device254:0 flush issues and1,000 successful
completions. Every syscall contains exactly one issue/completion pair, with no
overlap or unmatched endpoints. All17 CPU buffers report zero overrun, commit
overrun and dropped events. Both exact owned kprobe profiles have1,000 hits,
zero missed instances. The owned trace instance uses monotonic clock; one
syscall changes CPU between entry and return. Raw formats/filters/PID identity,
loss stats, scope and cleanup receipts are retained.

Guest timing inside the instrumented diagnostic:

| Span | Total seconds | Median microseconds | p99 microseconds |
| --- | ---: | ---: | ---: |
| fdatasync entry→return | 3.716265 | 3658 | 4136 |
| block issue→complete | 3.663664 | 3608 | 4079 |
| syscall entry→block issue | 0.049078 | 45 | 109 |
| block complete→return | 0.003523 | 2 | 7 |

Block issue→completion accounts for98.585% of observed syscall wait. This
localizes the measured Full wait below the engine control plane; it does not
separate VZ internals from host storage latency, establish an unavoidable ceiling,
measure observer overhead, qualify user latency or establish OrbStack durability.
Trace timestamp precision is microseconds. No product change is selected.

Reproduce with the existing SQL/oracle above and an owned privileged API-image
probe mounting `bench/native/diagnostics/wal_trace_guest.py`. Mount tracefs inside
that probe. Connect psql with one unique fresh owned login; retain
`pg_backend_pid()` and identify its guest-global PID from that login's process
in `docker top` (the agent reads the container cgroup from the root guest).
Run the helper's `setup TAG PID`, `start TAG`, stream the1,000 transactions through
that same psql connection, then `stop TAG` and `cleanup TAG`. TAG is `npwal`
followed by12 lowercase hex digits. Never trace a shared/unowned guest or infer
global PID from namespace PID. Require complete exact event pairing and all
loss counters before using the durations.

Earlier trace attempts remain failed and separate: job3e9509d9… could not read
the DB root-guest PID inside the isolated probe; the requested host PID mode did
not provide that view. Job68a3392a… verifies the corrected unique-role/top PID
identity but stops before transactions because stock kernel `rwbs` is10 bytes,
not the assumed8. The helper now validates the actual typed field/array length;
neither failure supplies a performance result. Their cleanup is complete.

Trace JSON SHA-256:
`3490af3c2b9656baeaeb2d5a767bc2975fc370fea7a5404864cc0def3f9eb52e`;
analysis `aea4c0ffa0e91ecf552bebc79183a738a4c6bd3760aac8d943b63769bdcea082`;
result `1895539dac89e18c9296d0e6401971339d2b56be5ec92c314c6b0badf614abbf`.
Next diagnostic compares direct synchronization of separate owned host files on
the same APFS volume. It never writes the VM backing file and is a boundary
probe, not a replacement for application acceptance.

## Direct host synchronization boundary

Job92ce290a552747238e0fb9c7b9766707 under
`.work/tmp/host-full-sync-boundary-20261117/job` exits0. Three AB/BA/AB pairs each
write1,000 distinct8KiB blocks into a fresh, prewritten and Full-synced owned file
on the same host volume. Every write is followed by `fsync` or `F_FULLFSYNC`51,
as defined in this host's SDK. All6 exact final SHA checks pass. Each file stays
at8,192,000 allocated bytes and is deleted after verification. No VM backing
file is opened. Sampled coordinator footprint stays below32MB, within128MiB.
All96 frozen receipts are unchanged. No engine or product source changes.

| Pair | fsync total s | Full-sync total s |
| --- | ---: | ---: |
| 1 | 0.019931 | 3.10 |
| 2 | 0.021168 | 3.37 |
| 3 | 0.023407 | 3.21 |

Direct host Full synchronization is already of the same order as the observed
guest block wait. This provides no evidence for a large removable control-plane
cost or for a VMM rewrite. It does not prove an irreducible floor: direct-file
block sizes, filesystem state, virtualization and workload differ. Never subtract
these totals from the application trace to manufacture a VZ overhead estimate.
The synthetic boundary probe is neither an application benchmark nor an
equivalent-durability OrbStack comparison.

Result SHA-256:
`3d3aa607fd9f5fb4289376946cb96a73ff583b7b7ad7bc03b2bba08ef41b79a8`;
plan `ca3e822d01d9c49278d605a34272ff40ea41d4b1da7d2b268dc72194420e2936`.
Resident resource and Full durability qualification remain open. Move to the W2
offered-load/cadence boundary rather than expand unchanged Full/cache hypotheses.

## Reproduction and next diagnostic

For the database workload, start the pinned portfolio Postgres17.12 image with
a fresh labelled volume, network none and `-c track_wal_io_timing=on`.
Use `psql -X -U postgres -d postgres -v ON_ERROR_STOP=1 -At`. Create
`events(k integer PRIMARY KEY, body text NOT NULL)` and `meta(n bigint)` with
one initial counter0, then `CHECKPOINT`. For each integer0..999 execute a separate
`BEGIN; INSERT INTO events VALUES(i,repeat(md5(i::text),128)); UPDATE meta SET n=n+1; COMMIT;`.
Use one psql connection for the timed transaction stream. Force its stats flush
with `SELECT pg_stat_force_next_flush()` before reading `pg_stat_wal` on another
connection. Time checkpoint separately. Before and after orderly container
restart, require exactly:

```sql
SELECT count(*),sum(k),min(length(body)),max(length(body)),
       md5(string_agg(k::text||':'||md5(body),',' ORDER BY k)),
       (SELECT n FROM meta) FROM events;
```

The expected full row is given above. Verify native image digest/DiffIDs,
unchanged binary/guest hashes, actual open-file process ownership, resource
completeness and exact labels before deletion. A fresh signed comparison build
uses `cargo build --release -p ctrs -j 6`, `RUSTC_WRAPPER=kache`, explicit
`CARGO_ENCODED_RUSTFLAGS=''`, separate target directories and the existing
virtualization entitlements. Private branches preserve the two one-line modes.

Read-only scout usrw_140c29f3-0a3f-4add-a8a3-54747a939f23 is terminal with no
source changes. It independently follows guest flush through the virtual block
device and finds no per-commit engine/RPC work in the inspected source. It did
not verify the raw JSON because its worktree-relative paths were unavailable;
the parent checked those receipts directly. Its recommendation is to time the
actual PostgreSQL fdatasync calls and same-window guest block-flush issue/
completion events under Full. Source/SDK alone cannot identify internal VZ or
host-media latency, nor establish OrbStack's policy. That is the next boundary;
do not add a speculative storage policy from these diagnostics.
