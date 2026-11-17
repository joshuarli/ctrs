# Native performance worktree cleanup, 2026-11-17

## Scope and integration proof

The performance campaign is paused by the owner. This bounded cleanup uses
integration head `fd8d18f675cec90afe984332a252c9aa30c06f31` in `/Users/josh/repos/ctrs`.
Only the 16 exact completed campaign paths listed below were eligible. Their
terminal status and cleanup authorization come from the owner and the
winddown inventory in `docs/native-performance-retained.md` lines 111-140,
152-153, 161, and 169-171. The progress file says the campaign is paused and
that required conclusions are tracked while `.work/` contains optional
regenerable artifacts (`docs/native-performance-progress.md` lines 3-18).

Before retirement, each target had an empty tracked/untracked status. The
`git status --porcelain --ignored=matching` output contained ignored entries
only. `git cherry fd8d18f675cec90afe984332a252c9aa30c06f31 <head>` reported only
`-` entries or no entries for every target (zero `+` entries); each head was an
ancestor or patch-equivalent with no merge commits in its unique range. No
process command line or process working directory matched a target. `lsof`
reported no process with cwd in any target and no open files below any target.
The 16 trees were all present in the before-list below.

| Checkout | Branch | Exact head | `du -sk` before | Integration check |
| --- | --- | --- | ---: | --- |
| `np-disk-expand` | `campaign/np-disk-expand` | `8b41bc208d52293361ba928c43b320b3503705e5` | 84272 | cherry `-` (1), no merges |
| `np-disk-review` | `review/np-disk-expand` | `8b41bc208d52293361ba928c43b320b3503705e5` | 4780 | cherry `-` (1), no merges |
| `np-flush-audit` | `review/np-flush-path` | `c74b1a196c7f8e8ea84590dca5d478eb6144c7db` | 4772 | ancestor; no unique commits |
| `np-image-diffids` | `fix/image-inspect-diffids` | `cdcbfb4913b42e54946bb6408b454e4c85a8bec2` | 4588 | ancestor; no unique commits |
| `np-resource-pins` | `fix/np-resource-pins` | `0783b4371119ae17d5e3f928106b3d381df5a49f` | 5328 | cherry `-` (2), no merges |
| `np-space-fix` | `campaign/np-space-fix` | `34a0c39538451b52c1b40fcaa7ec8574fbde75b1` | 5392 | cherry `-` (1), no merges |
| `np-test-pyramid` | `chore/np-test-pyramid` | `c8355f0edc9b54b08ff276e3cb648623e7b2d158` | 5644 | cherry `-` (1), no merges |
| `np-w11-deadline` | `campaign/np-w11-deadline` | `31094511425d03c583a6eb4c9040fce662e714d4` | 2294168 | cherry `-` (6), no merges |
| `np-w2-affinity` | `experiment/np-w2-affinity` | `8d94a2292e7a9819b6f802c09d73ed8bc28c780b` | 5632 | cherry `-` (1), no merges |
| `np-w2-client-path` | `experiment/np-w2-client-path` | `f2d394c0988866dde12b8074c5e2216931f4753e` | 5712 | cherry `-` (1), no merges |
| `np-w8-content` | `campaign/np-w8-content` | `bc6625ffaa18fe4d75ce3011147bcabf99c24eea` | 5124 | cherry `-` (1), no merges |
| `np-w8-paired` | `campaign/np-w8-paired` | `bfcf4a9d1160172893507f1a58e7b24eedfdb96d` | 5804 | cherry `-` (1), no merges |
| `np-w8-phases` | `campaign/np-w8-phases` | `72f4921566f2bf534066311fb321098a569274f0` | 5556 | cherry `-` (1), no merges |
| `np-w8-underpull` | `campaign/np-w8-underpull` | `d67782c630e0ed154fcbb49fb4dcde6b0a922550` | 5624 | cherry `-` (1), no merges |
| `np-w8-v2` | `campaign/np-w8-v2` | `95c318f096aa30dbc918b7f05b668713a3611a02` | 1838316 | ancestor; no unique commits |
| `np-w9-v2` | `campaign/np-w9-v2` | `be7f41da0344d924cd80d02a6eeb3a258bb1e1c0` | 5348 | ancestor; no unique commits |

Total pre-retirement allocation for these paths was `4,286,060 KiB` by `du -sk`.
This is a filesystem allocation measurement at that time, not a promised reclaim.

## Ignored data inventory and evidence disposition

The ignored-file inventory used `git ls-files --others --ignored --exclude-standard`
in each target, with `git status --porcelain --ignored=matching` immediately
before retirement. Counts below are ignored files, grouped by directory; no
ignored data is represented as tracked source.

| Checkout(s) | Ignored contents found | Disposition |
| --- | --- | --- |
| `np-disk-expand` | `.work/tmp`: 65 files for `disk-guard-68029d4e` (valid/bad fixture logs, JSON state, blob files, `vm/data.img`, tar inputs, runner and owner record); `target/`: 212 build-cache files; `guest/out/initramfs.cpio`; 9 Python bytecode files. | Discarded only after inventory. The tracked progress record preserves the mount-guard/expansion conclusion and limits (`docs/native-performance-progress.md` lines 45-51, 136-139). |
| `np-disk-review` | `.work/review`: `before-init.rs`, `native-result.json`, `before-guest.rs`, `change.patch`. | Discarded after inventory; retained source/review verdict is patch-equivalent at the pinned head and recorded in the inventory (`docs/native-performance-retained.md` lines 121, 169). |
| `np-flush-audit` | `.work/review/VZDiskImageStorageDeviceAttachment.h`. | Discarded after inventory; remaining durability questions and limits are tracked (`docs/native-performance-progress.md` lines 136-139). |
| `np-image-diffids` | `.work/tmp/ctrs-test-state/logs/cli.log`. | Discarded after inventory; accepted fix, test count, deployment and binary hash are tracked (`docs/native-performance-progress.md` lines 52-56). |
| `np-resource-pins` | No ignored files. | None to discard. |
| `np-space-fix` | 11 Python bytecode files. | Discarded after inventory; accepted integration and focused/full/native proof summary are tracked (`docs/native-performance-retained.md` lines 15, 127). |
| `np-test-pyramid` | 13 Python bytecode files. | Discarded after inventory. |
| `np-w11-deadline` | `.work/native-perf`: 907 files, including `results/w11-mixed-*` plans, trials and transfers and `engines/ctrs-warm` logs, image/container/network state and VM data; 47 Python bytecode files. | Raw receipts/runtime data discarded after inventory. The accepted W11 duration/cleanup integration state and paused campaign gates are summarized in `docs/native-performance-progress.md` lines 3-18 and 131-149. |
| `np-w2-affinity` | 17 Python bytecode files. | Discarded after inventory; diagnostic conclusion and limits remain in `docs/evidence/native-affinity-2026-11-16.md` and the progress record lines 26-31. |
| `np-w2-client-path` | 17 Python bytecode files. | Discarded after inventory; client-path and host-accounting conclusions remain in `docs/evidence/native-w2-boundaries-2026-11-16.md`. |
| `np-w8-content` | 3 Python bytecode files. | Discarded after inventory; W8 outcome and qualification limits are tracked (`docs/native-performance-progress.md` lines 57-64, 131-135). |
| `np-w8-paired` | 25 Python bytecode files. | Discarded after inventory; paired functional status and open qualification items are tracked (`docs/native-performance-progress.md` lines 131-135). |
| `np-w8-phases` | 16 Python bytecode files. | Discarded after inventory; paired functional status and open qualification items are tracked (`docs/native-performance-progress.md` lines 131-135). |
| `np-w8-underpull` | 18 Python bytecode files. | Discarded after inventory; W8 conclusion and qualification limits remain in tracked progress/evidence. |
| `np-w8-v2` | `.work/native-perf`: 88 files, including `results/w8-common-20261116T043656-23ec` plans, portfolio/export scripts, transfer/result records, and `engines/ctrs-warm` logs, image/container/network state and VM data; 10 Python bytecode files. | Raw receipts/runtime data discarded after inventory. Tracked progress preserves the shared portfolio, exact-operation result, and explicit non-comparable cold-transfer limitation (`docs/native-performance-progress.md` lines 57-64). |
| `np-w9-v2` | 34 Python bytecode files. | Discarded after inventory; W9 conclusion and qualification gates remain in tracked evidence and progress. |

The worktree inventory identifies the W8 worktree proof as `043656-23ec`; the
tracked progress record explicitly calls its 389 MB full transfer non-comparable
to the retained OrbStack 0-byte transfer. The tracked main proof is
`w8-common-20261116T044051-d3d5`; no cold-result claim is carried forward.
Raw W11/W8 receipts and VM state were optional ignored artifacts, not a live
consumer: the owner confirmed no campaign process/build/workload, and process,
cwd and open-file checks found no consumer in the exact authorized trees.

## Retirement commands and result

For each row, the pre-command was exactly
`git -C <exact-path> status --porcelain --ignored=matching`; all output consisted
of the `!!` ignored-directory entries shown in the retirement transcript, with
no tracked or untracked changes. The following exact retire commands each
exited 0. No refusal occurred.

| Exact command | Exit | Decisive output |
| --- | ---: | --- |
| `worktree-retire /Users/josh/repos/ctrs/.work/wt/np-disk-expand --into fd8d18f675cec90afe984332a252c9aa30c06f31 --discard-ignored` | 0 | removed (patch-equivalent); kept branch `campaign/np-disk-expand` |
| `worktree-retire /Users/josh/repos/ctrs/.work/wt/np-disk-review --into fd8d18f675cec90afe984332a252c9aa30c06f31 --discard-ignored` | 0 | removed (patch-equivalent); kept branch `review/np-disk-expand` |
| `worktree-retire /Users/josh/repos/ctrs/.work/wt/np-flush-audit --into fd8d18f675cec90afe984332a252c9aa30c06f31 --discard-ignored` | 0 | removed (ancestor); deleted branch `review/np-flush-path` |
| `worktree-retire /Users/josh/repos/ctrs/.work/wt/np-image-diffids --into fd8d18f675cec90afe984332a252c9aa30c06f31 --discard-ignored` | 0 | removed (ancestor); deleted branch `fix/image-inspect-diffids` |
| `worktree-retire /Users/josh/repos/ctrs/.work/wt/np-resource-pins --into fd8d18f675cec90afe984332a252c9aa30c06f31 --discard-ignored` | 0 | removed (patch-equivalent); kept branch `fix/np-resource-pins` |
| `worktree-retire /Users/josh/repos/ctrs/.work/wt/np-space-fix --into fd8d18f675cec90afe984332a252c9aa30c06f31 --discard-ignored` | 0 | removed (patch-equivalent); kept branch `campaign/np-space-fix` |
| `worktree-retire /Users/josh/repos/ctrs/.work/wt/np-test-pyramid --into fd8d18f675cec90afe984332a252c9aa30c06f31 --discard-ignored` | 0 | removed (patch-equivalent); kept branch `chore/np-test-pyramid` |
| `worktree-retire /Users/josh/repos/ctrs/.work/wt/np-w11-deadline --into fd8d18f675cec90afe984332a252c9aa30c06f31 --discard-ignored` | 0 | removed (patch-equivalent); kept branch `campaign/np-w11-deadline` |
| `worktree-retire /Users/josh/repos/ctrs/.work/wt/np-w2-affinity --into fd8d18f675cec90afe984332a252c9aa30c06f31 --discard-ignored` | 0 | removed (patch-equivalent); kept branch `experiment/np-w2-affinity` |
| `worktree-retire /Users/josh/repos/ctrs/.work/wt/np-w2-client-path --into fd8d18f675cec90afe984332a252c9aa30c06f31 --discard-ignored` | 0 | removed (patch-equivalent); kept branch `experiment/np-w2-client-path` |
| `worktree-retire /Users/josh/repos/ctrs/.work/wt/np-w8-content --into fd8d18f675cec90afe984332a252c9aa30c06f31 --discard-ignored` | 0 | removed (patch-equivalent); kept branch `campaign/np-w8-content` |
| `worktree-retire /Users/josh/repos/ctrs/.work/wt/np-w8-paired --into fd8d18f675cec90afe984332a252c9aa30c06f31 --discard-ignored` | 0 | removed (patch-equivalent); kept branch `campaign/np-w8-paired` |
| `worktree-retire /Users/josh/repos/ctrs/.work/wt/np-w8-phases --into fd8d18f675cec90afe984332a252c9aa30c06f31 --discard-ignored` | 0 | removed (patch-equivalent); kept branch `campaign/np-w8-phases` |
| `worktree-retire /Users/josh/repos/ctrs/.work/wt/np-w8-underpull --into fd8d18f675cec90afe984332a252c9aa30c06f31 --discard-ignored` | 0 | removed (patch-equivalent); kept branch `campaign/np-w8-underpull` |
| `worktree-retire /Users/josh/repos/ctrs/.work/wt/np-w8-v2 --into fd8d18f675cec90afe984332a252c9aa30c06f31 --discard-ignored` | 0 | removed (ancestor); deleted branch `campaign/np-w8-v2` |
| `worktree-retire /Users/josh/repos/ctrs/.work/wt/np-w9-v2 --into fd8d18f675cec90afe984332a252c9aa30c06f31 --discard-ignored` | 0 | removed (ancestor); deleted branch `campaign/np-w9-v2` |

After each command, `[ -e <exact-path> ]` was false. The worktree-retire tool
deleted ancestor branches only; all patch-equivalent branches remain intact.
All 16 targeted paths were absent from the after-list. The other listed paths
remain. The main checkout head advanced from `fd8d18f` to `5303fa5` during the
pass under parent ownership; all retirement commands explicitly targeted the
frozen integration hash `fd8d18f675cec90afe984332a252c9aa30c06f31`.

## Exact `git worktree list` snapshots

### Before

```text
/Users/josh/repos/ctrs                                  fd8d18f [main]
/Users/josh/repos/ctrs/.work/wt/np-balloon-model-review 45fd902 [research/np-balloon-model-review]
/Users/josh/repos/ctrs/.work/wt/np-balloon-reserve      4ecd599 [fix/np-balloon-reserve]
/Users/josh/repos/ctrs/.work/wt/np-balloon-used         45fd902 [fix/np-balloon-used]
/Users/josh/repos/ctrs/.work/wt/np-builder-readiness    4c217a2 [diagnostic/np-builder-readiness]
/Users/josh/repos/ctrs/.work/wt/np-cleanup-final        fd8d18f [chore/np-cleanup-final]
/Users/josh/repos/ctrs/.work/wt/np-disk-expand          8b41bc2 [campaign/np-disk-expand]
/Users/josh/repos/ctrs/.work/wt/np-disk-review          8b41bc2 [review/np-disk-expand]
/Users/josh/repos/ctrs/.work/wt/np-durable-job          ac1fb74 [campaign/np-durable-job]
/Users/josh/repos/ctrs/.work/wt/np-durable-review       879fa20 [review/np-durable-job]
/Users/josh/repos/ctrs/.work/wt/np-flush-audit          c74b1a1 [review/np-flush-path]
/Users/josh/repos/ctrs/.work/wt/np-full-sync            f536b6e [campaign/np-full-sync]
/Users/josh/repos/ctrs/.work/wt/np-gzip-backend         d0b2a72 [experiment/np-gzip-backend]
/Users/josh/repos/ctrs/.work/wt/np-image-diffids        cdcbfb4 [fix/image-inspect-diffids]
/Users/josh/repos/ctrs/.work/wt/np-lse-only             f7ea791 [experiment/np-lse-only]
/Users/josh/repos/ctrs/.work/wt/np-preempt-full         631d704 [experiment/np-preempt-full]
/Users/josh/repos/ctrs/.work/wt/np-ready-audit          24c4c92 [diagnostic/np-ready-audit]
/Users/josh/repos/ctrs/.work/wt/np-ready-cache          c484fa8 [perf/np-ready-cache]
/Users/josh/repos/ctrs/.work/wt/np-ready-review         c39d95f [review/np-ready-cache]
/Users/josh/repos/ctrs/.work/wt/np-resource-cells       b486f06 [campaign/np-resource-cells]
/Users/josh/repos/ctrs/.work/wt/np-resource-pins        0783b43 [fix/np-resource-pins]
/Users/josh/repos/ctrs/.work/wt/np-sched-mc             1bea138 [campaign/np-sched-mc]
/Users/josh/repos/ctrs/.work/wt/np-space-fix            34a0c39 [campaign/np-space-fix]
/Users/josh/repos/ctrs/.work/wt/np-test-pyramid         c8355f0 [chore/np-test-pyramid]
/Users/josh/repos/ctrs/.work/wt/np-uprobes              e5b9a33 [experiment/np-uprobes]
/Users/josh/repos/ctrs/.work/wt/np-vm-stop              4ad8f01 [fix/np-vm-stop]
/Users/josh/repos/ctrs/.work/wt/np-w10-cache-trace      942bba3 [campaign/np-w10-cache-trace]
/Users/josh/repos/ctrs/.work/wt/np-w11-deadline         3109451 [campaign/np-w11-deadline]
/Users/josh/repos/ctrs/.work/wt/np-w11-v2               9052439 [campaign/np-w11-v2]
/Users/josh/repos/ctrs/.work/wt/np-w2-affinity          8d94a22 [experiment/np-w2-affinity]
/Users/josh/repos/ctrs/.work/wt/np-w2-client-path       f2d394c [experiment/np-w2-client-path]
/Users/josh/repos/ctrs/.work/wt/np-w2-rate              dabc710 [experiment/w2-fixed-rate]
/Users/josh/repos/ctrs/.work/wt/np-w3-full              b030772 [experiment/np-w3-uncached]
/Users/josh/repos/ctrs/.work/wt/np-w4                   45dca6d [campaign/np-w4]
/Users/josh/repos/ctrs/.work/wt/np-w5                   14d3427 [campaign/np-w5]
/Users/josh/repos/ctrs/.work/wt/np-w8-content           bc6625f [campaign/np-w8-content]
/Users/josh/repos/ctrs/.work/wt/np-w8-paired            bfcf4a9 [campaign/np-w8-paired]
/Users/josh/repos/ctrs/.work/wt/np-w8-phases            72f4921 [campaign/np-w8-phases]
/Users/josh/repos/ctrs/.work/wt/np-w8-underpull         d67782c [campaign/np-w8-underpull]
/Users/josh/repos/ctrs/.work/wt/np-w8-v2                95c318f [campaign/np-w8-v2]
/Users/josh/repos/ctrs/.work/wt/np-w9-v2                be7f41d [campaign/np-w9-v2]
/Users/josh/repos/ctrs/.work/wt/np-zstd-load            bd35436 [perf/zstd-load]
/Users/josh/repos/ctrs/.work/wt/np-zstd-review          bd35436 [review/np-zstd-load]
/Users/josh/repos/ctrs/.work/wt/stuf89                  4e2bffc [fix/stuf89-help]
```

### After

```text
/Users/josh/repos/ctrs                                  5303fa5 [main]
/Users/josh/repos/ctrs/.work/wt/np-balloon-model-review 45fd902 [research/np-balloon-model-review]
/Users/josh/repos/ctrs/.work/wt/np-balloon-reserve      4ecd599 [fix/np-balloon-reserve]
/Users/josh/repos/ctrs/.work/wt/np-balloon-used         45fd902 [fix/np-balloon-used]
/Users/josh/repos/ctrs/.work/wt/np-builder-readiness    4c217a2 [diagnostic/np-builder-readiness]
/Users/josh/repos/ctrs/.work/wt/np-cleanup-final        fd8d18f [chore/np-cleanup-final]
/Users/josh/repos/ctrs/.work/wt/np-durable-job          ac1fb74 [campaign/np-durable-job]
/Users/josh/repos/ctrs/.work/wt/np-durable-review       879fa20 [review/np-durable-job]
/Users/josh/repos/ctrs/.work/wt/np-full-sync            f536b6e [campaign/np-full-sync]
/Users/josh/repos/ctrs/.work/wt/np-gzip-backend         d0b2a72 [experiment/np-gzip-backend]
/Users/josh/repos/ctrs/.work/wt/np-lse-only             f7ea791 [experiment/np-lse-only]
/Users/josh/repos/ctrs/.work/wt/np-preempt-full         631d704 [experiment/np-preempt-full]
/Users/josh/repos/ctrs/.work/wt/np-ready-audit          24c4c92 [diagnostic/np-ready-audit]
/Users/josh/repos/ctrs/.work/wt/np-ready-cache          c484fa8 [perf/np-ready-cache]
/Users/josh/repos/ctrs/.work/wt/np-ready-review         c39d95f [review/np-ready-cache]
/Users/josh/repos/ctrs/.work/wt/np-resource-cells       b486f06 [campaign/np-resource-cells]
/Users/josh/repos/ctrs/.work/wt/np-sched-mc             1bea138 [campaign/np-sched-mc]
/Users/josh/repos/ctrs/.work/wt/np-uprobes              e5b9a33 [experiment/np-uprobes]
/Users/josh/repos/ctrs/.work/wt/np-vm-stop              4ad8f01 [fix/np-vm-stop]
/Users/josh/repos/ctrs/.work/wt/np-w10-cache-trace      942bba3 [campaign/np-w10-cache-trace]
/Users/josh/repos/ctrs/.work/wt/np-w11-v2               9052439 [campaign/np-w11-v2]
/Users/josh/repos/ctrs/.work/wt/np-w2-rate              dabc710 [experiment/w2-fixed-rate]
/Users/josh/repos/ctrs/.work/wt/np-w3-full              b030772 [experiment/np-w3-uncached]
/Users/josh/repos/ctrs/.work/wt/np-w4                   45dca6d [campaign/np-w4]
/Users/josh/repos/ctrs/.work/wt/np-w5                   14d3427 [campaign/np-w5]
/Users/josh/repos/ctrs/.work/wt/np-zstd-load            bd35436 [perf/zstd-load]
/Users/josh/repos/ctrs/.work/wt/np-zstd-review          bd35436 [review/np-zstd-load]
/Users/josh/repos/ctrs/.work/wt/stuf89                  4e2bffc [fix/stuf89-help]
```

The 16 target paths each printed `ABSENT` in the after check; `du` was skipped
because the paths no longer exist. No aggregate reclaimed total is claimed.

## Kept work and exclusions

The following named trees were outside the authorized list and remain untouched:

- `/Users/josh/repos/ctrs` (`main`) and this integration checkout
  `/Users/josh/repos/ctrs/.work/wt/np-cleanup-final`.
- `np-w2-rate` (explicitly parked/unverified proposal), `stuf89` (original task
  consumer), `np-balloon-used` (standby initrd), and every other non-target
  worktree in the exact before snapshot, including `np-durable-job`,
  `np-durable-review`, `np-full-sync`, `np-resource-cells`, `np-sched-mc`,
  `np-w11-v2`, `np-w10-cache-trace`, `np-w4`, `np-w5`, and the private/rejected
  diagnostic trees. Their ownership/status remains as recorded in
  `docs/native-performance-retained.md`.
- `.work/tmp`, `.work/native-perf` in the integration checkout, and all
  controller/main scratch. The parent owns their cleanup. No parked or unrelated
  checkout was passed to `worktree-retire`.

No refusal or unresolved condition is recorded at this stage.

## Verification and commit

`git diff --check` and the report-only commit result are recorded after running
them below.
