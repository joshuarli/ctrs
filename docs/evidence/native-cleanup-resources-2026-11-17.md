# Native campaign resource cleanup, 2026-11-17

The owner explicitly requested cleanup after pausing the performance campaign.
All native campaign jobs and workers finished before cleanup. No experiment or
qualification was restarted. This record contains the ownership decisions; raw
inspection receipts are optional scratch.

## Approved stopped stores

The twelve exact roots `.work/tmp/gzd-{1..6}-{baseline,zlib}` belong to decoder
job `f6f723a3470549188d05c302f7c41883`. Each original result records
`native_stop_verified: true`, no cleanup errors and its exact absolute root.
Their container indexes are empty. The completed experiment is rejected and
summarized in [the build evidence](native-build-boundaries-2026-11-16.md).
The stores are regenerable image/cache copies; conclusions, input identities and
failures remain tracked. Before deletion, inspect all twelve indexes and check
that no process or open file uses any root.

The exact `.work/native-perf/engines/ctrs-warm` root is created by
`bench/native/runner.py` for this campaign. Its last two containers are stopped:
`npw8-reg-ctrs` and `buildx_buildkit_ctrs-build0`. The registry container matches
the campaign runner's registry fixture and volume. This root contains historical
fixture volumes, compressed blobs and a guest/build-cache disk; it is disposable
campaign state. Verify no live daemon/socket owner/open file before deletion.
Deleting it intentionally discards the warm cache. On resume use a fresh isolated
root and regenerate pinned fixtures; never claim its old warm-state equivalence.
Neither the installed ctrs user store nor OrbStack's VM store is in this scope.

## Docker scope

Use only endpoint `unix:///Users/josh/.orbstack/run/docker.sock`. Capture exact
container IDs, labels, mounts, image IDs and volume labels first. Remove only
stopped, verified campaign resources, using explicit IDs/names without force.
Preserve unrelated bctl/Helium, doas/stuf89 and junior resources and unknown
anonymous volumes. Global prune and shared builder-cache prune are out of scope.
The pre-cleanup report lists 340 unique images, 38 stopped containers and 83
volumes; the advertised reclaimable totals include unrelated data and are not
an authorization to delete it.

## Exact Docker deletion set

Five stopped kernel-build containers carry `dev.ctrs.campaign=native-performance`:
`np-preempt-full-private-20261117`, `np-uprobes-private-v2-20261117`,
`np-uprobes-private-20261117`, `np-lse-build-20261116`, `np-sched-mc-build`.
Their four experiment-specific build volumes carry matching campaign/experiment
labels. The shared `ctrs-kbuild` volume is this repository's documented kernel
cache; its only five container references are exactly those five owned builds.
The original closeout contract also names this cache for deletion after use.

The stopped `buildx_buildkit_np-dc-orbstack-f04a9943362a0` container and its exact
`_state` volume match the campaign-owned buildx instance's node, endpoint and
pinned BuildKit image in `.work/native-perf/buildx/orbstack-f04a9943362a/instances`.
This is an owned attribution-control builder, not a user default builder.

158 exact `npw6/hyperfine:<suffix>` / `npw6/zlib:<suffix>` tags match the tag
construction in `bench/native/runner.py` and the suffixes of 82 recorded OrbStack
W6 run IDs. Remove these exact tags only; preserve any other aliases on the same
image. The labeled uprobes builder image has only its owned alias and was used
only by the three owned stopped kernel builds. No base image or unknown image
is selected. Reinspect stopped state and labels before removal, check container
references before deleting volumes/images, and use no force flag.

## Completed outcome

All 13 approved stopped roots were removed. Fifteen additional storage-test
`data` directories were removed from exact owned roots: `space-001547f0`,
`space-0691f55a`, `space-11f1e15c`, `space-32241aef`, `space-9c94d113`,
`space-e793d5a5`, `space-e9a6bb14`, `sync-proof-ed045113` (existing fsync/full
legs), and `disk-expand-04b85cfe/engine`. Their source drivers, plans, results,
error records and allocation receipts remain. Fresh native open-file inspection
found no consumer before deletion. Failed runs retain their original failure;
deleting a stopped disposable store does not convert its result to a pass.

The `.work` allocated-size sum fell from **204,764,948 KiB (195.3 GiB)** to
**22,026,160 KiB (21.0 GiB)**, measured with `du -sk`. This is path allocation,
not a proven change in unique physical APFS extents or host free capacity.
Tracked evidence and parked source were preserved. No sparse disk was hashed.

Removed six stopped owned Docker containers, six exact unreferenced owned
volumes and 159 owned image tags (158 W6 outputs plus the labeled private builder
image). Reinspection matched all W6 tags to their planned image IDs; image
removal stderr was empty. Removal used no force or global prune. Docker reports
181 images, 32 containers and 77 volumes afterward (other projects can mutate
concurrently). Reported volume usage fell from 152.9 to 122.8 GB. Image accounting
fell from 107.6 to 67.23 GB while shared build-cache accounting grew from 78.31 to
112.7 GB; these categories must not be added as reclaimed physical space.
Unknown/shared build-cache entries and anonymous volumes remain untouched.
The live unrelated Chromium build and unrelated bctl/Helium, doas and junior
resources were preserved. Campaign builder metadata is now historical: regenerate
the owned control builder explicitly if needed; do not adopt its removed state.

Cleanup retired 28 checkouts in total, including the temporary cleanup controller;
22 checkouts remain including main. The [worktree report](native-cleanup-2026-11-17.md)
records the mechanic's 16-path pass. Parent retired six clean completed trees
before it, then five accepted readiness/balloon trees and the controller.
Ordinary three-way merges `2fdab58` and `f5f6471` integrated already accepted
readiness/balloon lane history with **exactly unchanged Git trees**, permitting
ancestor-safe retirement; existing green evidence remains valid. The accepted
initrd was copied to a separate optional asset cache and its standby symlink
retargeted before the completed source checkout was retired.

A trial merge of `fix/np-vm-stop` conflicted in `docs/development.md` and was
aborted; the main tree stayed unchanged and that source branch/checkout remains.
No rejected or unverified source was merged. Other parked trees are intentionally
kept with their reasons in [the retained inventory](../native-performance-retained.md).
No builds, performance workloads or broad tests ran during cleanup.
