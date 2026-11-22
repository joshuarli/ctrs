# Native Linux workload survey — 2026-11-22

This is the native amd64 ctrs/host-Docker lane, not macOS/OrbStack.
Linux shares the host kernel; macOS has a VM boundary. No macOS gate closes.
The existing common lock remains byte-identical. This slice adds frozen native
worker, Marked and workspace images and a native four-image registry portfolio.
It changes no Rust runtime, sampling ownership guard, resource budget or Mac pin.

## Design, fixtures and admission

The campaign's **Same work and state** rule requires identical paired inputs
and AB/BA ordering; **Consistent statistics** permits three pairs as pilots,
not qualification (which needs at least ten valid complete pairs). The durable
`pilot-declaration.md` fixes three alternating C,D / D,C / C,D pairs per cell.
There are no performance exclusions, replacements or pooling with old results.
Both engines, their clients and all containers use CPUs 0–7. Build, image load,
native-tool checks and expected-output freezing are untimed. The independent
registry, CLI/coordinator and sampler lie outside both engine accounting scopes.

Additional images are built once on Docker from the existing source fixtures,
then the identical archive is imported into ctrs. `workloads.lock.json` freezes
engine-specific IDs, Linux/amd64, ordered DiffIDs, recipe/source hashes, native
tools, the common-lock SHA and the original exact W12 output receipts. Original
ARM64 defaults and semantic assertions remain. New adapters cover W4, W5,
W8, W9, API/DB/queue W10, finite W11, full-bind/all-volume W12 and W12-watch.
W11's finite three-cycle pilot is not a 12-hour reliability qualification,
macOS FD plateau, APFS allocation or VM-disk observation; those remain Mac-only.

W12 verifies 2,830 installed packages, 92,306 files / 532,136,968 bytes, exact
base/warm/changed/branch-return server/client receipts and the unchanged test
list. Native versions include Node v22.15.0, npm 10.9.2, esbuild 0.25.3,
Python 3.13.18, PostgreSQL 17.12 and Redis 7.4.12. Preparation is preserved,
including earlier failed setup attempts; none is presented as scored work.

The first original batch stopped before an unstarted trial at host load 6.20
(limit 5.60). Its 47 records remain untouched. The controller subsequently
waits before unstarted work, with the unchanged pre/post gate. Resume runs the
same frozen binary/store and continues trial sequence 47 without retrying the
completed inadmissible W11 record. Original schedules/freezes/logs are retained.

### Native watch configuration, not an engine fix

The original bind per-file strategy (`UseFsEvents`) stops the original cohort
on a real correctness failure: **97/120 correct, 23 missed, 0 stale**. A frozen
Docker counter-control produces the exact same 23 missed sequence/path pairs.
All save, atomic, create/import, rename and delete outputs pass; later burst
writes after atomic replacement account for the misses. This disproves an
exclusively ctrs-specific explanation for the observed failure. The existing
workload README already describes this native inode file-watch issue for volumes.

Linux bind and volume now use the already campaign-sanctioned
`UseFsEventsOnParentDirectory` strategy, still **fs.watch, not polling**. They
have distinct `w12-watch-linux-bind-v1` / `w12-watch-linux-volume-v1` versions.
Mac file/parent-directory settings and versions are unchanged. No deadline,
edit spacing, event kind, output count, identity or admission rule is relaxed.
The stopped original cohort has 61 attempted records and 11 explicitly
unstarted records; it is not silently called complete. A separate declaration
admits one unscored C,D bind pair, then three alternating pairs for each native
mount. Admission and all 12 scored trials produce all 120 exact outputs per
trial, zero missed/stale, and unchanged watcher PID/start ticks. The two old
failures remain separate and unqualified, never replacement samples.
## Paired timing pilots

Seconds except named `_ms` metrics. Medians [Q1,Q3]; C/D is the median
within-pair ratio with seeded bootstrap 95% interval. Three pairs are
pilots, not qualification. W11 has only two host-admitted timing pairs.

| Cell / metric | ctrs median [Q1,Q3] | Docker median [Q1,Q3] | Paired C/D [95% CI] |
| --- | ---: | ---: | ---: |
| W4 / `workers_1_s` | 0.8620 [0.8459,0.9572] | 1.2454 [1.2321,1.3064] | 0.7073 [0.6068,0.8449] |
| W4 / `queue_p99_ms_at_1` | 655.3502 [638.3742,712.8897] | 876.8575 [850.5669,908.1841] | 0.7474 [0.6614,0.9347] |
| W4 / `workers_4_s` | 0.9132 [0.8942,0.9306] | 1.2651 [1.2080,1.3479] | 0.7219 [0.6626,0.7603] |
| W4 / `queue_p99_ms_at_4` | 641.3653 [637.6060,645.2907] | 851.8579 [829.7440,887.2579] | 0.7621 [0.6870,0.7941] |
| W4 / `workers_16_s` | 1.5803 [1.5319,1.6598] | 2.2759 [2.2583,2.3454] | 0.6621 [0.6544,0.7643] |
| W4 / `queue_p99_ms_at_16` | 937.2856 [910.8695,957.5788] | 1136.6604 [1099.7717,1232.4700] | 0.7781 [0.7362,0.8818] |
| W5 / `bind_edit_to_result_median_s` | 0.1530 [0.1520,0.1538] | 0.1143 [0.1132,0.1160] | 1.3521 [1.2835,1.3649] |
| W5 / `volume_edit_to_result_median_s` | 0.1523 [0.1518,0.1542] | 0.2105 [0.2079,0.2122] | 0.7370 [0.7121,0.7416] |
| W8 / `whole_workflow_s` | 12.1335 [11.7294,13.7902] | 21.3968 [21.1064,22.1984] | 0.5671 [0.4924,0.7421] |
| W8 / `pull_to_health_s` | 9.5505 [9.1582,10.9634] | 16.9716 [16.6646,17.4326] | 0.5627 [0.4899,0.7566] |
| W9 / `fixed16_at_1_s` | 5.5474 [5.0189,6.9115] | 6.1389 [6.1383,7.5119] | 0.7314 [0.6244,1.3483] |
| W9 / `job_completion_p95_ms_at_1` | 5543.6462 [5014.7601,6907.8965] | 6134.6850 [6131.2314,7507.8720] | 0.7321 [0.6242,1.3484] |
| W9 / `fixed16_at_4_s` | 1.4527 [1.2683,1.6483] | 1.7285 [1.7097,2.1165] | 0.6271 [0.5800,1.0904] |
| W9 / `job_completion_p95_ms_at_4` | 1448.3280 [1264.4113,1643.0215] | 1725.2854 [1706.4869,2112.9302] | 0.6263 [0.5792,1.0889] |
| W9 / `fixed16_at_8_s` | 0.9388 [0.7962,0.9505] | 1.1822 [1.1725,1.4516] | 0.5528 [0.5455,0.8275] |
| W9 / `job_completion_p95_ms_at_8` | 934.5482 [792.3330,946.2784] | 1178.7816 [1169.1077,1446.0846] | 0.5515 [0.5454,0.8263] |
| W9 / `fixed16_at_16_s` | 0.8876 [0.7713,0.8920] | 1.0314 [1.0311,1.2466] | 0.6351 [0.6072,0.8697] |
| W9 / `job_completion_p95_ms_at_16` | 883.0603 [767.1846,887.2197] | 1027.6550 [1027.3376,1242.5520] | 0.6338 [0.6059,0.8679] |
| W10-api / `recovery_s` | 0.4443 [0.4360,0.4515] | 0.5772 [0.5547,0.6091] | 0.7409 [0.7156,0.8349] |
| W10-api / `recovered_p99_ms` | 16.6695 [15.0742,18.9562] | 19.7059 [16.2641,20.0505] | 0.8173 [0.6840,1.6567] |
| W10-db / `recovery_s` | 0.1979 [0.1902,0.2433] | 0.3876 [0.3481,0.4149] | 0.4711 [0.4475,0.9356] |
| W10-db / `recovered_p99_ms` | 16.5156 [14.9895,17.9416] | 15.7548 [12.8092,16.4379] | 0.9646 [0.8546,1.9636] |
| W10-queue / `recovery_s` | 0.2360 [0.2275,0.2602] | 0.3287 [0.3276,0.3358] | 0.7227 [0.6662,0.8292] |
| W10-queue / `recovered_p99_ms` | 803.0364 [789.4123,860.0617] | 876.8430 [863.3887,938.6141] | 0.9167 [0.8848,0.9448] |
| W11-finite / `mixed_work_s` | 16.3710 [15.7293,17.0128] | 16.7256 [16.7030,16.7483] | 0.9790 [0.8996,1.0584] |
| W12-full-bind / `install_seconds` | 15.0488 [14.9721,17.4377] | 12.4911 [11.8688,13.5099] | 1.3381 [1.0252,1.5873] |
| W12-full-bind / `build_seconds` | 17.6266 [17.5385,18.3139] | 16.7885 [16.2825,17.7158] | 1.1173 [0.9360,1.1318] |
| W12-full-bind / `typecheck_seconds` | 4.6415 [4.4746,5.3298] | 4.1005 [3.9430,5.6751] | 1.1319 [0.5942,1.5898] |
| W12-full-bind / `test_discovery_seconds` | 0.5424 [0.5226,0.5575] | 0.5622 [0.5514,0.5674] | 0.9999 [0.8944,1.0032] |
| W12-full-bind / `warm_rebuild_seconds` | 13.6241 [13.3212,14.8650] | 12.2822 [11.5016,13.0532] | 1.2708 [0.9417,1.3113] |
| W12-full-bind / `multi_file_change_seconds` | 18.2030 [18.0793,18.6265] | 18.6447 [17.0663,19.5643] | 0.9763 [0.9300,1.1593] |
| W12-full-bind / `branch_switch_seconds` | 15.9684 [15.4059,16.1443] | 19.0459 [16.9313,23.0859] | 0.8569 [0.5887,1.0018] |
| W12-full-bind / `install_verification_seconds` | 0.4906 [0.4811,0.5017] | 0.5793 [0.5738,0.5904] | 0.8469 [0.8298,0.8525] |
| W12-full-bind / `workflow_seconds` | 86.3504 [85.3947,91.2796] | 91.7567 [84.0875,92.0244] | 1.0424 [0.9411,1.1050] |
| W12-all-volume / `install_seconds` | 10.4726 [10.2019,13.1167] | 14.3433 [12.0949,15.6588] | 1.0086 [0.6170,1.0988] |
| W12-all-volume / `build_seconds` | 13.4115 [13.3889,14.9615] | 16.1531 [14.9195,16.1819] | 0.9766 [0.8273,1.0222] |
| W12-all-volume / `typecheck_seconds` | 4.3048 [4.1569,4.5365] | 3.7753 [3.7049,3.8155] | 1.1403 [1.0397,1.3119] |
| W12-all-volume / `test_discovery_seconds` | 0.5508 [0.5262,0.7742] | 0.6292 [0.5836,0.7776] | 0.7972 [0.5948,1.8547] |
| W12-all-volume / `warm_rebuild_seconds` | 10.8551 [10.8020,11.2904] | 11.9685 [11.4337,12.6927] | 0.8981 [0.8739,0.9960] |
| W12-all-volume / `multi_file_change_seconds` | 14.9765 [14.7736,16.1787] | 15.8521 [15.0365,16.6431] | 0.9969 [0.9448,1.0246] |
| W12-all-volume / `branch_switch_seconds` | 14.6549 [14.6065,15.0281] | 14.4861 [14.3824,15.9751] | 1.0117 [0.8336,1.0786] |
| W12-all-volume / `install_verification_seconds` | 0.5215 [0.5147,0.5241] | 0.5951 [0.5876,0.6506] | 0.8535 [0.7462,0.8989] |
| W12-all-volume / `workflow_seconds` | 70.3983 [69.8473,75.8589] | 80.5567 [74.1277,82.3879] | 0.9656 [0.8602,1.0399] |
| W12-watch-bind / `edit_to_result_p50_s` | 0.7165 [0.6936,0.7202] | 0.8027 [0.7798,0.8144] | 0.8926 [0.8118,0.9562] |
| W12-watch-bind / `edit_to_result_p95_s` | 1.2315 [1.2062,1.3232] | 1.5227 [1.4676,1.5723] | 0.8718 [0.7281,0.9292] |
| W12-watch-volume / `edit_to_result_p50_s` | 0.6437 [0.6407,0.6672] | 0.8123 [0.8036,0.8479] | 0.7925 [0.7219,0.8688] |
| W12-watch-volume / `edit_to_result_p95_s` | 1.1274 [1.1195,1.1407] | 1.4716 [1.4501,1.5148] | 0.7781 [0.7236,0.7842] |

## Resource scope and validity

Independent counts: 72/72 correct; 71/72 host-admitted; 64/72 strict
resource-valid. There are 35 admitted timing pairs and 28 admitted
strict resource-valid complete pairs. Invalid records remain raw.

Only complete admitted resource-valid pairs enter the medians below.
CPU is sampled cgroup CPU, explicitly **incomplete/lower-bound**, not
all host-kernel CPU. Footprint is the coincident anon+kernel peak over
the whole sampled setup/work/check/cleanup window, not an isolated
primary-operation peak or cache-inclusive memory.current. Idle and
retained medians are independent before/after observations. Do not
subtract these columns to infer an operation peak or broad efficiency.

| Cell | Admitted timing pairs | Resource pairs | CPU s C/D | Peak MiB C/D | Idle MiB C/D | Retained MiB C/D |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| W4 | 3/3 | 3/3 | 9.57 / 11.66 | 258.34 / 970.96 | 3.43 / 688.56 | 5.21 / 688.60 |
| W5 | 3/3 | 2/3 | 9.46 / 13.23 | 46.06 / 730.23 | 6.37 / 687.80 | 6.80 / 688.39 |
| W8 | 3/3 | 3/3 | 9.07 / 19.89 | 255.40 / 916.47 | 95.57 / 739.46 | 188.70 / 789.24 |
| W9 | 3/3 | 3/3 | 22.57 / 19.71 | 627.48 / 1209.59 | 267.27 / 783.46 | 267.27 / 783.46 |
| W10-api | 3/3 | 3/3 | 22.37 / 23.65 | 331.33 / 868.11 | 267.40 / 782.13 | 267.62 / 782.21 |
| W10-db | 3/3 | 3/3 | 22.23 / 23.96 | 406.56 / 948.63 | 267.89 / 783.60 | 268.26 / 783.55 |
| W10-queue | 3/3 | 3/3 | 7.10 / 8.37 | 438.37 / 1001.33 | 268.45 / 780.71 | 269.13 / 780.84 |
| W11-finite | 2/3 | 1/3 | 38.64 / 48.97 | 492.82 / 1025.05 | 269.38 / 777.25 | 270.46 / 779.22 |
| W12-full-bind | 3/3 | 3/3 | 205.40 / 208.69 | 1880.20 / 2614.82 | 13.82 / 745.75 | 15.14 / 746.48 |
| W12-all-volume | 3/3 | 3/3 | 184.94 / 199.11 | 1886.09 / 2588.93 | 15.32 / 748.41 | 16.47 / 742.62 |
| W12-watch-bind | 3/3 | 1/3 | 108.21 / 123.48 | 1493.46 / 2237.19 | 5.91 / 746.93 | 6.11 / 751.66 |
| W12-watch-volume | 3/3 | 0/3 | unavailable | unavailable | unavailable | unavailable |

Eight Docker records fail the unchanged nonempty unowned transient
cgroup guard: W5 pair 0; W11 pairs 1 and 2; watch-bind pairs 0 and 1;
watch-volume all three pairs. These are not zero CPU/memory. The
watch-volume cell has **no paired resource comparison**. W11 ctrs pair
2 fails post host-admission and that whole pair is timing-unqualified.

The old per-file bind strategy is separate: both engines returned
97/120 correct, 23 missed, zero stale, with exactly the same missed
sequence/path identities. It is correctness-unqualified, not a slow
sample to replace or pool with the newly versioned native strategy.
## W13: sanctioned four-stream control still lacks 2x headroom

The existing `w13_host_headroom.py` and W13 receiver already sanction one and
four streams. Use the unchanged byte-verifying 1 GiB transfer and matching
host/container loopback controls, CPUs 0–7. Four streams are a separate
calibration, not a repair of or pool with the historical one-stream cell.

| Four-stream calibration | Host control GB/s | Container control GB/s | Engine attempts |
| --- | ---: | ---: | --- |
| ctrs upload | 4.895 | 5.447 | tool-limited |
| Docker upload | 4.070 | 6.006 | tool-limited |
| Docker download | 4.488 | 6.966 | tool-limited |
| ctrs download | 5.548 | 6.041 | tool-limited |

All transfers are byte-exact, admitted and resource-valid, but every attempt
exceeds half the slower matching control. Thus **2x tool headroom remains
unproven**; there is no scored W13 cohort, throughput verdict, receiver rewrite
or threshold relaxation. Controlled external egress is also unsupported: no
owned external endpoint. Historical one-stream evidence stays unchanged.

## Preservation and restore

Durable root: `/home/ubuntu/ctrs-evidence/linux-survey-20261122/` (`E` below).
The committed `.sha256` manifest covers image archives, inputs/layouts, raw
trial and sampler output, schedules/freezes, logs, analysis/render programs,
preparation scripts, the exact runtime pair and a complete-history source
bundle. Records retain their original absolute path strings; resolve the suffix
after `.work/native-perf/results/` against `$E/results/`. Nothing in old raw
records is rewritten. `analysis.json` preserves every timing spread, paired
ratio and interval, independent admission count and resource median.

`workloads.tar` SHA-256 is
`233e6408606e11a191a6e1f64f3fd968906be120ce99346ff718ee196fecc502`.
`portfolio.tar` is
`05d8ff1c8b24a49bd738ccde0b2f237e82afec5694fd87195142fbe3ee69c3eb`.
Common lock SHA remains
`246c0c6aca1d8c0a749f37b9281ec32735a326e414de872b45b1e77fa4f3b874`.

Restore the existing common archive with the documented `--linux-archive`
procedure first (see the recoverable baseline report); do not regenerate its
lock. Start an owned ctrs root with `$E/baseline/ctrs` and adjacent `ctrs-init`,
load `$E/workloads.tar` into each engine, then verify every role through
`linux_lane.workload_image`. Restore `$E/inputs/` to `.work/native-perf/inputs/`
and `$E/kutt.tar.gz` to `.work/tmp/kutt.tar.gz`. The supplemental images were
loaded and inspected in both original stores; this slice does not claim a new
independent empty-Docker-store restoration. Any disposable Docker restore must
use a private netns, private containerd/address/root/state, private Docker roots
and socket and no default bridge/socket, as specified in the baseline report.

The source bundle retains pre-rebase measured harness heads `ff3b180` and
`96bce5f`; their per-run freezes include actual file/patch/binary hashes. Rebase
onto `d941863` brings unrelated Mac harness/documentation updates, not Rust
runtime changes. The only watch conflict is resolved by preserving the new Mac
version constant and the separate Linux selector. No measurement is relabeled
as having run against the rebased source. Use the source bundle to reconstruct
the exact frozen harness if reproducing those runs.

## Checks, standing and next slice

Full offline suite after native watch selection: **528 tests, OK (15 skipped)**.
After integrating new main harness inputs: **540 tests, OK (16 skipped)** with
`make test-bench TMPDIR=/home/ubuntu/repos/ctrs/.work/tmp`. The first rebased
check hits the newly added W10 unit test's 104-byte Unix socket guard under
the long nested worktree temporary path. A shorter existing repository `.work`
TMPDIR runs unchanged assertions; no production guard or test is weakened.
`git diff --check` is clean. No Rust rebuild/e2e is needed for these Python-only
adapters: the frozen H3 runtime is unchanged, and actual paired workloads above
exercise each admitted adapter. No full-e2e or new CPU-completeness pass is claimed.

The point-estimate losing follow-up list is **W5 bind** and **W12** (full-bind
install/build/typecheck/warm rebuild/workflow; all-volume install/typecheck/
branch return). Every listed loss, including intervals spanning one, goes to
the next bounded profile-supported engine loop. No optimization is promoted
by this survey. W1/W2/W3/W3-v4/W6/W7 already have distinct preserved Linux
coverage; no historical score is pooled with these pilots. Final W1–W13 standing
and the disposition of these two follow-ups belong to the subsequent checkpoint.

Ctrs is stopped, MainPID=0. Host dockerd/containerd remain PID 599/487 with the
original 2026-11-21 05:39:22 UTC start times, unrestarted/unreconfigured. Linux
has no VM isolation boundary; macOS comparisons and full gates remain open.
