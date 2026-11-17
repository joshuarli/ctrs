# W2 fixed offered-load admission

The fixed-rate fixture is diagnostic. No timing, CPU win, observer acceptance or
campaign qualification follows yet. This record separates source checks,
application correctness and successful rate delivery.

## Frozen clients and bounded verification

Initial worker `usrw_f628bac1-b206-46e4-bc41-87380bbfeb03` implemented pacing in the old loader, then stopped
uncommitted when the bounded W2 check rejected its changed portfolio hash.
Parent reviewed that entire diff and moved the new client to `fixtures/w2/v3.py`.
The v2 loader remains exactly SHA-256
`3bff357920dea4aed4b4e2eb52c3e978712963dfd476ab42e990fb1b348a0992`.
W11 and existing fixed-work/saturation clients retain their frozen inputs.
The uncommitted original proposal is retained in `.work/wt/np-w2-rate`.

e01c298 adds the separate rate client and runner support. Its primary latency
starts at each absolute scheduled slot, including queue wait. Service latency
is separate. All attempted operations and exact writes are retained; any slot
more than10ms late makes delivery invalid. Invalid/nonfinite/unbounded rates and
wrong-case options fail before engine access. See the
[fixture instructions](../../bench/native/diagnostics/w2-fixed-rate.md).

The actual HTTP test initially assumed a healthy server implied timely client
scheduling; it flaked under foreign host load. The test now checks real exact
HTTP work and delayed backlog, while a controlled-clock check proves valid
delivery without relying on host scheduling. The10ms product-fixture budget is
unchanged; missing or late delivery never becomes a pass.

## First native proof remains failed

Job `fcbc4c4ba6664d6780bf7ddf75650129` in
`.work/tmp/w2-fixed-rate-proof-20261117/job` exits 1 with clean owned teardown.
The two native ARM64 legs use host fda62467/initrd6ae4d3ab/stock kernel35087713,
17vCPUs/45091MiB resident control, pinned API/Postgres/Redis,500 operations,
500 offered requests/s, concurrency4, write mix0.3 and seed17. Both complete all
500 requests with identical reads/writes and exact persisted data, no load errors
and complete native counters. Owned teardown completes and all92 inputs recheck.

ctrs has zero late slots. OrbStack has124 late slots, so the job exits1 and
does not admit the larger comparison. First late slot4 belongs to one client:
12.373ms lag,16.993ms scheduled completion. Its later same-worker lag grows;
other clients remain timely. Service p99 and scheduled p99 are deliberately
different; no CPU or latency comparison is scored from this invalid delivery.

## Absolute-slot regression and new admission experiment

Parent reproduced a pacer defect with a controlled clock: one20ms response plus
1ms timer overshoot caused four late requests because subsequent deadlines were
rebased on actual start. fcf5468 removes that re-pacing. The regression now has
one late slot and recovers future deadlines, while the run remains invalid.
Fixture version is `w2-v3.1-fixed-rate`; do not pool with v3. Bounded W2 check
passes53 tests/zero skips. Original v2 bytes remain unchanged.

The next separate experiment rotates unprimed and200-read primed fresh stacks
over three alternating engine rounds,500 operations at500req/s in every leg.
It records all12 admission observations even when rate delivery is invalid;
application/counter/ownership failures still stop it. Priming uses the original
read-only client during setup, before API CPU workload boundaries. “Unprimed”
means no explicit application read priming, not an engine-cold installation.
The larger steady CPU matrix starts only if every primed leg has complete,
timely delivery. No native timer/QoS or product runtime setting changed.

## Priming did not establish admission

Job `949ea73c33cc446790739ed5831a7159` under
`.work/tmp/w2-rate-warmup-admission-20261117/job` exits 0 with clean teardown.
All 12 observations/6,000 operations pass exact application and native-counter
checks; all 92 inputs recheck unchanged. Its completed workflow does not mean
rate delivery passed. Primed delivery is **not admitted**.

| Round | ctrs unprimed late | ctrs primed late | OrbStack unprimed late | OrbStack primed late |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0 | 0 | 9 | 4 |
| 2 | 1 | 0 | 0 | 16 |
| 3 | 0 | 0 | 6 | 0 |

For each late slot, analysis compares its lag with the previous same-client
completion minus the 8ms slot interval. Prior completion explains 34 of 36 late
slots. Only two need additional client scheduling delay, about 10.007/10.008ms.
This identifies the fixed four-client response queues as the leading admission
boundary; it does not prove an engine CPU deficit or a timer-policy remedy.
No late result is suppressed, and the large CPU comparison has not started.

The next frozen experiment compares 4 versus 16 clients at the same total
500 offered requests/s, 2,000 operations per leg, read priming and three rotated
engine/condition rounds. It changes client capacity, preserves the 10ms limit,
retains invalid observations, and admits a larger 16-client matrix only if every
16-client leg delivers all scheduled work on time. Request corpora remain paired
between engines within each concurrency; concurrency changes the seeded worker
partition, so cross-concurrency CPU differences cannot be treated as pure engine
improvements. The raw plan's oracle prose retained “500” from the short template;
numeric plan parameters, commands and exact-work assertions all require 2,000.


## Client capacity does not admit delivery

Job `2dad081db1e54a8abfabb916d3b09c0c` under
`.work/tmp/w2-rate-client-capacity-20261117/job` exits 0 with clean owned teardown.
All 12 observations pass exact application work and native counters; all 92
frozen receipts remain unchanged. Workflow success does not override the failed
`c16_delivery_admitted` result.

| Round | ctrs C4 | ctrs C16 | OrbStack C4 | OrbStack C16 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 1 | 30 | 3 | 57 |
| 2 | 0 | 27 | 12 | 28 |
| 3 | 0 | 62 | 0 | 48 |

Cells count requests starting more than 10ms after their absolute slots. More
clients do not solve admission. Many C16 misses lie just beyond 10ms; this
motivates a separate owned-client scheduling control, not a product speed claim.
Result SHA-256: `aaff495c0cc31d056edabf397e183ba4a3975ab22b771a2e63dca8320a2db09d`.
Plan SHA-256: `b20b19fc974b39f74e46a7dce10e1bd3a825c8989ccea76bbae74d23ce7b6850`.

## Owned client QoS is rejected for admission

The C probe under `.work/tmp/w2-rate-qos-admission-20261117/` verifies the SDK
pthread QoS API: all calls return zero, requested class changes from 21 to
USER_INITIATED (25), with relative priority zero. Private client copies add the
same receipt collection to both conditions; only the candidate sets class 25.
They preserve absolute slots, deterministic writes and the unchanged 10ms limit.
Neither the VM dispatch queue nor workstation settings change.

Initial job `7445817ae99e4e4d8f7952cfbe519a0e` exits 1/clean after one exact
legacy leg: coordinator looked for `client_qos` in runner summary metrics,
which intentionally copy selected fields. The raw client output has the receipt.
This failed attempt remains frozen. The corrected coordinator reads that raw
output and records its SHA alongside all 16 worker receipts.

Job `895a24ed1cb34a829dd95a42adcd6b03` under
`.work/tmp/w2-rate-qos-admission-v2-20261117/job` exits 0/clean. All 12 observations
complete 2,000 exact operations, setup read priming, complete native counters,
matching capacity/binary/guest inputs and owned teardown. All 99 input receipts
recheck unchanged. Actual QoS is 21 in every legacy worker and 25 in every
candidate worker, with no API errors. Late request counts are:

| Round | ctrs legacy | ctrs elevated | OrbStack legacy | OrbStack elevated |
| --- | ---: | ---: | ---: | ---: |
| 1 | 28 | 46 | 68 | 34 |
| 2 | 97 | 75 | 77 | 85 |
| 3 | 108 | 108 | 95 | 104 |

No elevated leg meets delivery admission, so this policy is rejected for the
larger CPU comparison. Three diagnostic pairs establish neither a speedup nor a
regression; timings remain ineligible on the shared host. Every invalid delivery
is retained. No source default or product policy changes.

Reproduction: use separate copies of `fixtures/w2/v3.py`, querying
`pthread_get_qos_class_np(pthread_self(), ...)` in each worker in both modes,
and setting `pthread_set_qos_class_self_np(QOS_CLASS_USER_INITIATED, 0)` only in
the candidate. Require zero API errors, class 25 on every candidate worker,
and retain raw receipts. Run three alternating engine pairs at 16 clients,
500 total requests/s, 2,000 operations, write ratio 0.3, seed 17+round and
200 setup read operations. Rotate condition order legacy/elevated,
elevated/legacy, legacy/elevated. All other pinned assets and capacity match the
prior admission runs. Any application, ownership or counter failure stops the
batch; rate-invalid observations are retained rather than replaced.


## Timer-only isolation selects a native admission candidate

Job `a7d66088a60a42e6bcc5d5e925318f78` under
`.work/tmp/w2-rate-timer-20261117/job` exits 0/clean. Six alternating pairs each
schedule 2,000 slots at 500/s across 16 owned threads, with no HTTP or engine.
Every Python-sleep observation has 152–245 late slots; every mach_wait_until
observation has 162–233 late slots. Both retain delays just beyond 10ms, so
switching to Mach absolute wait alone is rejected. Peak client RSS is 26,935,296
bytes. This first timer diagnostic lacks bracketing host gates and is not timing
qualification; its during-run gate does not repair that gap.

Job `bf483e8fc179486b8d28990343a4a750` under
`.work/tmp/w2-rate-kqueue-20261117/job` compares sleep with a one-shot kqueue
EVFILT_TIMER using SDK NOTE_NSECONDS (0x4) and NOTE_CRITICAL (0x20). The latter
requests minimal timer coalescing. There is no spin loop, real-time scheduling,
product policy or workstation setting. Six alternating pairs retain all 24,000
slot records with exact contiguous indices. Sleep late counts are
122/222/157/227/156/175; kqueue late counts are all zero. Peak RSS is 27,574,272
bytes. Both simple gates exit 0, but the after-gate stderr reports hot unrelated
Niceforge controller work. The unrelated OrbStack machine also prevents
exclusive qualification. Perf gate deferred: host busy. This selects an admission experiment, not an
engine performance improvement. Clock mapping brackets are retained per leg.

Reproduction for timer isolation: start 16 owned threads behind a barrier, set a
shared future origin 50ms ahead, assign worker w slots w,w+16,...,1999 at 500/s,
and record actual start minus original deadline. Compare unchanged Python sleep
with the SDK timer, alternate order six times and retain every slot. Mach control
uses mach_timebase_info to convert absolute ticks and records the monotonic/tick
clock bracket. Reject incomplete slot sets or timer errors. Kqueue waits are
one-shot, checked for EV_ERROR, and owned descriptors close after use. Preserve
the unchanged 10ms threshold; no rebase, busy wait or late-slot omission.


## Checksummed diagnostic records

Large raw records remain outside Git. These hashes identify the conclusions
above; reproduction does not require their continued presence.

| Diagnostic | Plan SHA-256 | Result SHA-256 |
| --- | --- | --- |
| client capacity | `b20b19fc974b39f74e46a7dce10e1bd3a825c8989ccea76bbae74d23ce7b6850` | `aaff495c0cc31d056edabf397e183ba4a3975ab22b771a2e63dca8320a2db09d` |
| owned client QoS | `eea58425eff620e75990c559bbe69d7ae8f276b5575f75a6121d386de12c606e` | `821bea57ac4e1aae99ba15633015450fbf60df73aa5f2e6e7cb699466e66e6e3` |
| sleep versus Mach | parameters in frozen probe | `2c1a108a2d2d3a1222c2ad88329830c006627a7ee48baf6916002f49614ebe78` |
| sleep versus kqueue | parameters in frozen probe | `a4cfc9677b6394a516deaad5c6719008bb3606f60bc9ee25b28355d2442d0f0b` |


## Native kqueue admission passes

Initial job `dc8bf1fd6aa94428bc557379712e6c5d` exits 1/clean before HTTP work:
the private client wrongly assumed Python kqueue supported a context manager.
The corrected client uses contextlib.closing; an actual wait is checked before
launching a separate frozen attempt. No failed observation is replaced in place.

Job `f569a92727cc4e319baacfeda40475e1` under
`.work/tmp/w2-rate-kqueue-admission-v2-20261117/job` exits 0/clean in 63.9 seconds.
All six alternating engine observations deliver exactly 2,000 operations with
zero errors and zero requests starting beyond 10ms. Exact seeded persisted data,
complete native counters, actual binary/boot hashes and resource parity pass;
all 95 frozen input receipts remain unchanged. The experimental client has a
separate fixture version and uses a bounded, checked kqueue wait per absolute
slot; every queue closes. No timer/QoS/product policy changes outside that client.

This admits the C16 cadence CPU diagnostic, not speedup or global qualification.
Keep C4/C16, v3.1/v3.2 and closed-loop/fixed-rate histories separate. The six-pair
CPU plan rotates closed-loop/500/2,000req/s conditions with 10,000 operations each,
paired seeds and alternating engine order. Any invalid cell stops that fixed
matrix with partial data retained and no replacement.

plan.json SHA-256: `187792107d3447380ea85a658dfab37f47537136fedd8d67b9f1a62867a9b666`.

result.json SHA-256: `7e069604c3da38773e396220d901db0ddf2b65c953fd1546353ad3523b226b41`.
