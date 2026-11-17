# Retained native performance work

This inventory records owner-requested winddowns on 2026-11-16 and 2026-11-17.
The latest dated inventory supersedes earlier checkout-retention statements.
The campaign resumed later the same day. Original winddown lanes are terminal;
the storage repair lane is also terminal and integrated. Checkouts preserve source or
qualification evidence. The current campaign status and next action live in
[native-performance-progress.md](native-performance-progress.md).

## Parked work

| Branch | Revision | Cause and retry condition |
| --- | --- | --- |
| `campaign/np-storage-space` | `538e2c3` | Restored on resumed main as 3a87d61 with repair 97a6a69. Revised native allocation and relation-ENOSPC proofs pass; retain original failed/narrower evidence separately. |
| `campaign/np-space-fix` | `34a0c39` | Integrated as 97a6a69 after parent review, six focused tests, full harness suite and both native storage stages. Retained checkout `np-space-fix` preserves repair provenance. |
| `campaign/np-w8-content` | `bc6625f` | Reviewed and integrated as 00ac842. Real four-image generation reproduces 37 layer identities. Native full-transfer/marker proofs pass; sub-API guest cache absence and scored qualification remain open. |
| `campaign/np-full-sync` | `f536b6e` | Full synchronization candidate remains unpromoted. Complete resource and performance confirmations in an exclusive window. |
| `campaign/np-refusal-ttl` | `54c6a00` | Recovery candidate remains parked. Re-establish the v2 exclusive baseline and preserve the failed prior confirmation. |
| `campaign/np-sched-mc` | `1bea138` | Rejected scheduler configuration snapshot. Do not deploy it. Reconsider only with a new causal profile. |

Storage proof `space-32241aef` lives under `.work/tmp/`. Its finite supervisor
receipt is `.work/tmp/space-source-20261116T0935/`, job
`570bdc7ba990456e94b3c7b25b652099`, exited 0. Both variants preserve the exact
100-record prefix and accept 10 more records after relation SQLSTATE 53100.
The reported zero host allocation growth compares endpoints. It is not a peak
bound. Root-reserved blocks, host-full storage, power loss and exclusive reclaim
remain untested. Failed `space-0691f55a` and temporary-spill-only `space-e9a6bb14`
are retained separately. The review is terminal session
`usrw_34112a16-8e65-4b9d-953d-8b88183d95eb`.

## Retained checkouts

Paths below are relative to `.work/wt/`. Their current consumers are the named
qualification or source-review tasks. Native artifacts retain their original
paths. No ignored fixture or build data was discarded during winddown.

| Checkout | Branch | Current consumer |
| --- | --- | --- |
| `np-disk-expand` | `campaign/np-disk-expand` | Expansion source and guest assets for later qualification provenance. |
| `np-disk-review` | `review/np-disk-expand` | Original expansion review receipts and patch comparison. |
| `np-durable-job` | `campaign/np-durable-job` | Original supervisor source and lifecycle proof provenance. |
| `np-durable-review` | `review/np-durable-job` | Retirement refused because the head is not integrated. Preserve for patch review. |
| `np-flush-audit` | `review/np-flush-path` | Flush-path audit inputs for remaining storage guarantees. |
| `np-full-sync` | `campaign/np-full-sync` | Parked Full synchronization source for candidate confirmation. |
| `np-image-diffids` | `fix/image-inspect-diffids` | Native image deployment proof and release provenance. |
| `np-resource-cells` | `campaign/np-resource-cells` | Original resource prototype snapshot `b486f06`; compare before retirement. |
| `np-sched-mc` | `campaign/np-sched-mc` | Rejected kernel configuration and retained guest assets. |
| `np-w10-cache-trace` | `campaign/np-w10-cache-trace` | Recovery trace prototype snapshot `942bba3` and binary provenance. |
| `np-w11-deadline` | `campaign/np-w11-deadline` | Raw final W11 normal and cancellation proofs referenced by progress. |
| `np-w11-v2` | `campaign/np-w11-v2` | Original mixed fixture snapshot `9052439` and native evidence. |
| `np-w4` | `campaign/np-w4` | Original queue fixture snapshot `45dca6d`; compare with accepted source. |
| `np-w5` | `campaign/np-w5` | Original watch fixture snapshot `14d3427` and source provenance. |
| `np-w8-content` | `campaign/np-w8-content` | Parent review and real artifact proof for the parked W8 slice. |
| `np-w8-v2` | `campaign/np-w8-v2` | Common portfolio native evidence and reproduction artifacts. |
| `np-w9-v2` | `campaign/np-w9-v2` | Fixed build-job fixture evidence and source provenance. |

Completed checkouts `np-cpu-review`, `np-space-review`, `np-w11-fix-review` and
`np-w11-review` were retired after integration or preservation of their source.
Branches `campaign/np-w11-fix-review` and `campaign/np-w11-review` remain as
patch-equivalent provenance. Their checkouts contained no ignored evidence.

Pre-existing branches `chore/ctrs-proto-target-gate`, `cleanup/mount-guard` and
`repomod/fix/f844dfc9dd284537af0a958ad9dfadf1` remain unchanged outside this winddown.

## Completed W2 checkout retirement (2026-11-17)

Integration head: `c2a7fab426667d383d9e04dcc5f9d10047769618`.
Both completed source lanes were patch-equivalent to this head with no merge
commits, clean of tracked and untracked changes, and had no live agent, process
working directory, or open file using either checkout. `git worktree list
--porcelain` identified both exact paths and branches before retirement. The
only ignored files were Python `.pyc` files under `__pycache__` directories;
they were test scratch, not source or unique proof.

| Checkout retired | Lane source commits | Integrated commits on main | Verdict and retirement |
| --- | --- | --- | --- |
| `.work/wt/np-w2-timer` (`perf/w2-timer`) | `a0b24b553d238e38a1d39a9628dffe4723c0d1fe`, `89ba4a8bfeac43db09224fcecc3e46edfaca917e` | `cae881b1bd5f0092a49caaef4bdb2ad19ec9c91f`, `ab7861343443b7a5d2d2f2dc5a82c55a1784ab0d` | Both integration commits are ancestors of the pinned head; `git cherry` marked both lane commits `-` (patch-equivalent). Retired successfully; branch preserved because it is not an ancestor. |
| `.work/wt/np-w2-uprobes` (`diagnostic/w2-uprobes`) | `31783d78c001d37d29423e80adf460843440047e`, `18bd6706b5f51fd94648f9e0c2f791f0212de750` | `b2a676164df5e97faed4930b3beb53d4b8b36e83`, `f042b2195a29c743d699ce2be683e7ee5125ce0e`, plus parent fix `7c0dda12d8e15e538cfd90a81738f5bfb5a69664` | All three integration commits are ancestors of the pinned head; `git cherry` marked both lane commits `-` (patch-equivalent). Retired successfully; branch preserved because it is not an ancestor. |

Retirement used `worktree-retire` with `--discard-ignored` only after inspecting
the `.pyc` entries, and both dry runs reported `would remove` with the branch
kept. Before retirement, `du -sk` reported 6,092 KiB for the timer checkout
and 5,528 KiB for uprobes (11,620 KiB total). After retirement both exact paths
were absent (`du` reported “No such file or directory”), reclaiming those
checkout sizes. Native fixture sentinels `.work/tmp/resource-quiet-policy-20261117/job`,
`.work/tmp/balloon-model-assets`, `.work/tmp/balloon-reserve-target/release/ctrs`
and `.work/native-perf/engines/ctrs-warm` remained present. No fixture or
benchmark process was modified. `sparseguest/out/data.img` was not present at
the integration checkout path when checked.

Kept unchanged: integration checkout `/Users/josh/repos/ctrs`; controller
`.work/wt/np-cleanup-resume`; parked dirty proposal `.work/wt/np-w2-rate`;
private-kernel worktrees `.work/wt/np-uprobes` and `.work/wt/np-preempt-full`;
and live-initrd worktree `.work/wt/np-balloon-used`. Every other checkout in
the pre-retirement worktree inventory also remains; ownership or lane status
was outside this authorized two-checkout pass. No scratch, builder volume,
container, VM disk, input, result, or benchmark process was otherwise cleaned.

## Winddown inventory 2026-11-17

The owner paused performance work and separately requested cleanup afterward.
All experiment/build/worker attempts are terminal. No campaign process was found
in the native process snapshot; no user crontab exists. User/system launch-agent
searches contain no campaign job, and scheduled power events are unrelated Apple
services. No workstation service or unrelated OrbStack workload was stopped.
No new experiment started. Six clean completed checkouts were retired with
`worktree-retire`: `np-balloon-reserve-review`, `np-balloon-review`,
`np-cleanup-resume`, `np-python-leaf`, `np-wal-review`, `np-wal-trace`.
Ancestor-only branches were removed by the tool; patch-equivalent branches remain.

Every checkout below is temporarily retained for the explicit follow-on cleanup:
inspect ignored artifacts, establish aggregate integration, and retire only with
`worktree-retire <exact-path> --into <accepted-head>`. Unverified/rejected branches
must not be merged merely to satisfy retirement. The unrelated stuf89 checkout
has its original task as its consumer. All necessary source is committed; no
uncommitted proposal is required after reboot. Raw `.work` artifacts are optional.
The source/evidence and runtime reconstruction commands are in the progress file.

| Branch | Revision | Checkout under `.work/wt` | Cause, consumer and retry condition |
| --- | --- | --- | --- |
| `campaign/np-disk-expand` | `8b41bc208d52` | `np-disk-expand` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `campaign/np-durable-job` | `ac1fb749b222` | `np-durable-job` | Historical source snapshot with non-equivalent commits; cleanup compares final source against integrated main. Preserve branch; do not merge without a demonstrated missing accepted fix and affected proof. |
| `campaign/np-full-sync` | `f536b6e24466` | `np-full-sync` | Unpromoted VZ Full policy; retry only with exclusive W3/W2/resource and durability confirmation. |
| `campaign/np-refusal-ttl` | `54c6a00b1c51` | `none` | Unpromoted 50ms recovery delay; retry after exclusive v2 baseline/control; preserve failed confirmation. |
| `campaign/np-resource-cells` | `b486f06b4c4b` | `np-resource-cells` | Historical source snapshot with non-equivalent commits; cleanup compares final source against integrated main. Preserve branch; do not merge without a demonstrated missing accepted fix and affected proof. |
| `campaign/np-sched-mc` | `1bea138e2918` | `np-sched-mc` | Rejected scheduler hypothesis; require new causal evidence before reconsidering. |
| `campaign/np-space-fix` | `34a0c3953845` | `np-space-fix` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `campaign/np-w10-cache-trace` | `942bba3135b4` | `np-w10-cache-trace` | Historical source snapshot with non-equivalent commits; cleanup compares final source against integrated main. Preserve branch; do not merge without a demonstrated missing accepted fix and affected proof. |
| `campaign/np-w11-deadline` | `31094511425d` | `np-w11-deadline` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `campaign/np-w11-fix-review` | `50716e7850b5` | `none` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `campaign/np-w11-review` | `8acbf602adfd` | `none` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `campaign/np-w11-v2` | `9052439310d6` | `np-w11-v2` | Historical source snapshot with non-equivalent commits; cleanup compares final source against integrated main. Preserve branch; do not merge without a demonstrated missing accepted fix and affected proof. |
| `campaign/np-w4` | `45dca6dd7873` | `np-w4` | Historical source snapshot with non-equivalent commits; cleanup compares final source against integrated main. Preserve branch; do not merge without a demonstrated missing accepted fix and affected proof. |
| `campaign/np-w5` | `14d3427bde17` | `np-w5` | Historical source snapshot with non-equivalent commits; cleanup compares final source against integrated main. Preserve branch; do not merge without a demonstrated missing accepted fix and affected proof. |
| `campaign/np-w8-content` | `bc6625ffaa18` | `np-w8-content` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `campaign/np-w8-paired` | `bfcf4a9d1160` | `np-w8-paired` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `campaign/np-w8-phases` | `72f4921566f2` | `np-w8-phases` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `campaign/np-w8-underpull` | `d67782c630e0` | `np-w8-underpull` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `campaign/np-w8-v2` | `95c318f096aa` | `np-w8-v2` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `campaign/np-w9-v2` | `be7f41da0344` | `np-w9-v2` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `chore/ctrs-proto-target-gate` | `e0a24301a8fa` | `none` | Pre-existing unrelated branch; no campaign cleanup authority to change it. |
| `chore/np-cleanup-resume` | `6d1df7ba127c` | `none` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `chore/np-test-pyramid` | `c8355f0edc9b` | `np-test-pyramid` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `cleanup/mount-guard` | `7acbcf16c123` | `none` | Pre-existing mount-guard provenance; do not integrate again. |
| `diagnostic/np-builder-readiness` | `4c217a259129` | `np-builder-readiness` | Private logging-only profile; reconstruct if a new readiness boundary needs attribution. |
| `diagnostic/np-ready-audit` | `24c4c920c1bb` | `np-ready-audit` | Private two-log lifecycle observer; reconstruct from branch for a new functional question. |
| `diagnostic/w2-uprobes` | `18bd6706b5f5` | `none` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `experiment/np-gzip-backend` | `d0b2a72d136a` | `np-gzip-backend` | Rejected: decoder CPU ratio misses declared 10% screen; miniz default remains. |
| `experiment/np-lse-only` | `f7ea79162d60` | `np-lse-only` | Rejected kernel hypothesis; require new causal evidence before reconsidering. |
| `experiment/np-preempt-full` | `631d704c70c7` | `np-preempt-full` | Rejected: no pair achieves declared 10% API CPU reduction; require a new causal profile. |
| `experiment/np-uprobes` | `e5b9a3326ee7` | `np-uprobes` | Private diagnostic kernel only; reconstruct from branch if another named attribution question needs it. |
| `experiment/np-w2-affinity` | `8d94a2292e7a` | `np-w2-affinity` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `experiment/np-w2-client-path` | `f2d394c09888` | `np-w2-client-path` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `experiment/np-w3-full` | `be068821426c` | `none` | Historical source snapshot with non-equivalent commits; cleanup compares final source against integrated main. Preserve branch; do not merge without a demonstrated missing accepted fix and affected proof. |
| `experiment/np-w3-uncached` | `b03077287b89` | `np-w3-full` | Historical source snapshot with non-equivalent commits; cleanup compares final source against integrated main. Preserve branch; do not merge without a demonstrated missing accepted fix and affected proof. |
| `experiment/w2-fixed-rate` | `dabc710d0a0a` | `np-w2-rate` | Unverified superseded three-file proposal committed as dabc710; compare against current integrated implementation before retry. |
| `experiment/wal-trace` | `e1b12f6f6ddc` | `none` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `fix/image-inspect-diffids` | `cdcbfb4913b4` | `np-image-diffids` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `fix/np-balloon-reserve` | `4ecd599914b9` | `np-balloon-reserve` | Accepted host-accounting repair; patch provenance for cleanup comparison. |
| `fix/np-balloon-used` | `45fd902b3aa4` | `np-balloon-used` | Accepted guest-accounting repair; old initrd symlink is standby only, not a running consumer; rebuild from main before deleting assets. |
| `fix/np-resource-pins` | `0783b4371119` | `np-resource-pins` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `fix/np-vm-stop` | `4ad8f0139ab4` | `np-vm-stop` | Historical source snapshot with non-equivalent commits; cleanup compares final source against integrated main. Preserve branch; do not merge without a demonstrated missing accepted fix and affected proof. |
| `fix/stuf89-help` | `4e2bffca3960` | `stuf89` | Unrelated owner task; preserve checkout, branch and all ignored data. |
| `perf/np-ready-cache` | `c484fa80011c` | `np-ready-cache` | Two source commits combined into accepted 2f37d02; preserve provenance and prove aggregate equivalence before retirement. |
| `perf/w2-timer` | `89ba4a8bfeac` | `none` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `perf/zstd-load` | `bd35436de01e` | `np-zstd-load` | Rejected: valid 2GiB repeated layer exceeds unchanged unpack expansion bound; no default promotion. |
| `repomod/fix/f844dfc9dd284537af0a958ad9dfadf1` | `35697c5e33ea` | `none` | Pre-existing unrelated branch; preserve untouched. |
| `research/np-balloon-model-review` | `45fd902b3aa4` | `np-balloon-model-review` | Accepted guest-accounting source snapshot; prove aggregate equivalence before retirement. |
| `review/np-disk-expand` | `8b41bc208d52` | `np-disk-review` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `review/np-durable-job` | `879fa20f9064` | `np-durable-review` | Historical source snapshot with non-equivalent commits; cleanup compares final source against integrated main. Preserve branch; do not merge without a demonstrated missing accepted fix and affected proof. |
| `review/np-flush-path` | `c74b1a196c7f` | `np-flush-audit` | Integrated or patch-equivalent provenance; cleanup may retire after ignored-artifact and process-use checks. No new experiment required. |
| `review/np-ready-cache` | `c39d95ffae61` | `np-ready-review` | Read-only earlier readiness snapshot; corrected source is integrated; retirement tool may reject partial patch equivalence. |
| `review/np-zstd-load` | `bd35436de01e` | `np-zstd-review` | Read-only snapshot of rejected zstd source; preserve branch, no retry without a different compatible design. |

This is a retention inventory, not an instruction to rerun completed proofs.
Reconstruct a retired source checkout with `git worktree add .work/wt/<name>
<branch>`. Rebuild assets using the pinned component instructions on main; do not
rely on retained binary locations or old symlinks. Original detailed checkpoints
remain in Git at `2f37d02:docs/native-performance-progress.md`.
