# Linux checkpoint: CI, W13 ceiling, storage and recovery — 2026-11-22

Native amd64 only, CPUs **0–7**, same Ubuntu 22.04.5/kernel 6.8.0-1060-aws
host and cgroup-v2 accounting. Docker 29.9.2 (`0367cbe`), containerd 2.4.2,
runc 1.5.2 and the Linux fixture lock remain unchanged. No new engine change,
image build, image pull, dependency resolution or Docker lifecycle change.
This adds **pilots**, not Linux or macOS performance qualification.

Raw evidence: `/home/ubuntu/ctrs-evidence/linux-checkpoint-20261122/`.
The [manifest](linux-checkpoint-2026-11-22.sha256) covers copied records,
traces, exact H3 binaries, declarations, scripts, source bundle/patch, identities,
CI receipt, analyses, restore/start logs and tests. This is durable local storage,
not an off-host backup. Copy it before retiring the VM.

## Completed CI audit

Each requested ref was queried with `git_commit_checks(wait_mode="all")`:

| Head | Passed | Failed | Pending | Interpretation |
| --- | ---: | ---: | ---: | --- |
| `d75f876` | 5 | 0 | 0 | HTTPie final head |
| `75491e7` | 5 | 0 | 0 | W2 final head |
| `cd9800e` | 5 | 0 | 0 | Integrated final head |
| `2910f31` | 5 | 0 | 0 | Checkpoint |
| `65b7bbd` | 5 | 0 | 0 | Incident disclosure |
| `c5b8f0d`, `11e4967`, `215b8db` | 0 | 0 | 0 | No check runs returned; **not passes** |

The last three intermediate commits are ancestors of main. Their corresponding
final descendants above have all five checks green; runtime crates, Cargo inputs
and e2e inputs do not differ from those intermediates. There was no red job to
fix forward. Full refs are in `ci-audit.json`; absent checks are not silently
represented as completed workflows.

## W13: headroom not demonstrated; no engine rerun

Read `headroom-declaration.md` and `headroom.py` before replay. Five unchanged
W13 host-loopback upload controls used one stream, exactly 1 GiB per stream,
the deterministic existing payload, explicit sender/receiver CPU set 0–7,
ordinary pre-admission and immediate `-1` post-admission. All five controls were
byte-exact and host-admitted. No engine transfer or new W13 cohort was run.

Host-loopback goodput: median **3.352 GB/s**, IQR **[2.556,3.405]**, range
**2.470–3.451 GB/s** (decimal GB). The maximum of the twenty correct historical
engine trials was **2.633 GB/s**. The existing `tool_limited` policy requires
engine goodput to remain at most half the relevant control capacity. The
conservative necessary host-only gate was therefore a minimum control capacity
of **5.267 GB/s**; observed minimum/engine maximum was **0.938**, not 2.

Even the best observed control does not provide 2× headroom. Passing this
host-only gate would still require container-side capacity proof. The receiver
compares every received block with the expected file within the timed transfer;
these numbers measure that verification/transport tool path, not network capacity
or engine leadership. Child sender+receiver CPU was 0.693–0.802s per transfer.
No receiver rewrite, relaxed threshold or silent substitution was attempted.
The 1 GiB generated payload was removed after the controls; its seed, hash,
tool source identity and exact receipts are preserved. Historical invalid
resource receipts remain untouched.

## Incremental existing-workload pilots

`pilot-declaration.md` precedes the run. Five alternating AB/BA pairs for each
of W1 and W3, 20 trials, no retries, replacements or timing exclusions. The
campaign **Consistent statistics** rule calls three pairs pilots; five also
meets the benchmark checklist's repeatability minimum. Each trial had normal
pre-admission and immediate `-1` post-admission. **20/20 correct, 20/20
host-admitted, 20/20 resource-valid; 5/5 complete resource-valid pairs each.**

W1 already had native frozen-stack selection; Linux workload admission is now
enabled. W3 now selects the frozen Linux database rather than the ARM64 macOS
portfolio, and pairs ordered DiffIDs plus the common lock/SQL hashes. Its SQL,
300 transactions, synchronous commit, CHECKPOINT, restart and exact persisted
rows/counter/fsync checks are unchanged. Mac pins and selection remain unchanged.
No new framework or fixture lock was introduced.

The coordinator explicitly pins Docker `run` and compose services to CPUs 0–7;
client and live daemon/agent/shim CPU receipts are preserved. Both engines stay
running. A fresh owned ctrs image store loaded the existing archive untimed;
Docker's existing frozen portfolio was verified without loading or altering it.
The first ctrs W1 trial includes lazy agent startup and first materialization
after load (health
5.377s versus approximately 3.1s thereafter); it remains in the cohort. The
primary recovery interval starts later, after an acknowledged write. The first
pre-trial live receipt has only the daemon; subsequent receipts include the
same persistent H3 agent processes with their expected hashes. Thus the health
and total-work observations are not a uniformly warm-agent/cache comparison.
W3 follows
W1, so its database image is materialized on both engines.

Timing is median **[Q1,Q3]**; ratios are median paired ctrs/Docker with the
existing 2,000 whole-pair bootstrap draws, seed 7, 95% intervals:

| Metric | ctrs | Docker | Paired C/D [95% CI] |
| --- | ---: | ---: | ---: |
| W1 DB restart → exact recovery, s | .578 [.576,.578] | .742 [.738,.742] | .776 [.768,.802] |
| W1 health, s | 3.105 [3.102,3.108] | 3.473 [3.000,3.624] | 1.034 [.857,1.416] |
| W1 total work, s | 3.944 [3.937,3.964] | 4.488 [4.038,4.690] | .974 [.841,1.301] |
| W3 300-transaction exec, s | .0765 [.0764,.0785] | .1569 [.1525,.1580] | .484 [.454,.506] |
| W3 COMMIT p95, ms | .432 [.398,.440] | .508 [.472,.527] | .843 [.741,.866] |
| W3 CHECKPOINT command, s | .026 [.025,.027] | .052 [.051,.054] | .510 [.410,.648] |
| W3 restart-ready, s | .242 [.241,.245] | .236 [.229,.251] | 1.021 [.568,1.114] |

These are short end-to-end application/CLI pilots, **not sustained storage
throughput or engine-daemon/crash/power-loss recovery**. W1 includes API health
polling and verified reads/writes. W3's summed psql query timers have medians
.054/.105s C/D, with .023/.050s residual inside the full exec wall time. Thus
the full-exec ratio is not a disk-only ratio. The remaining query-time difference
has not been causally attributed; no product optimization is inferred or landed.
Five pairs and tight subsecond timings are not a qualification claim.

### Resources and consequences

CPU is explicitly a sampled lower bound, with incomplete accounting machine
flags preserved. Footprint is coincident **anon+kernel**, not page-cache-inclusive
`memory.current`. Raw traces retain anon/file/kernel separately. Medians below
use all five matched valid pairs. Memory and CPU windows are the existing
sampler windows: W1 includes startup and cleanup; W3 starts after initial DB
readiness and includes migration, transactions, checkpoint/restart and checks.
They are not isolated primary-operation peaks. Sub-200ms W3 phases can fall
between periodic memory samples.

| Case / engine | CPU s | Idle MiB | Observed window peak MiB | Peak−idle MiB | Retained−idle MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| W1 ctrs | 1.533 | 73.29 | 135.50 | 62.33 | .51 |
| W1 Docker | 2.469 | 755.44 | 835.36 | 80.59 | 2.22 |
| W3 ctrs | .159 | 74.72 | 84.30 | 9.58 | .29 |
| W3 Docker | .398 | 756.50 | 776.79 | 20.25 | −.44 |

Negative retained deltas are preserved, not clamped. Independent medians need
not subtract exactly. Whole-service baselines differ substantially; no broad
memory-efficiency or complete-CPU claim follows. W3 verified 300 committed
transactions per trial, 3,000 total, and exact rows after every restart.

## Replay and provenance

The run's Git SHA remains **99db1aa77c2d4c8416461b71ed756e41f9b41f05**, with
`worktree_dirty: true`; `pilot-freeze.json` and `linux-coverage.patch` identify
the exact harness changes. Do not relabel records with a later landing SHA.
The ctrs/agent binaries are the preserved H3 releases from
`linux-httpie-20261122/candidate-h3/`, copied under this evidence root's
`current/`. Runtime crate/Cargo/e2e inputs were unchanged through the measured
base and subsequent integration. Incoming runner changes affect W5/W12 CLI
options, not W1/W3 execution; `rebase-input-diff.txt` records them.

Copy the evidence and baseline off-host, verify manifests before replay, then
restore the source bundle/patch and adjust only controller absolute paths:

```sh
cd ~/ctrs-evidence/linux-checkpoint-20261122
sha256sum -c /path/to/ctrs/docs/evidence/linux-checkpoint-2026-11-22.sha256
git clone source.bundle /path/to/restored-source
python3 analyze.py
```

Do not rerun `pilot.py` into the existing evidence directory: it refuses to
overwrite records. Review both declarations, make a fresh output directory,
and use the existing external-engine launcher and frozen image archive.
No Linux native-adapter provenance or old receipts have been rewritten.

The integrated checkpoint and finite Mac handoff are in the dated Linux
section of [progress](../native-performance-progress.md). Linux shares the host
kernel; the Mac VM boundary is different. Linux results close no Mac gate.

## Local verification and cleanup

`make test-bench`: **499 tests, OK (skipped=15)**; after integrating incoming
W5/W12 harness changes: **501 tests in 23.915s, OK (skipped=15)**.
The new Linux W3 test retains normal, corrupt-row, incomplete-commit and
wrong-owner assertions; existing Mac selection tests remain unchanged.
No runtime source changed, so no new Rust/full-e2e run is claimed.
`final-audit.py` verifies all pilot correctness/resource/admission counts,
paired inputs, live executable hashes and CPU sets, copied traces and unchanged
runtime inputs. It explicitly accounts for the lazy agent absent before trial 1.
Owned workload resources, service/cgroup, firewall entries and links were
removed; host dockerd/containerd remain PID **599/487**, active since
**2026-11-21 05:39:22 UTC**, unrestarted and unreconfigured.
