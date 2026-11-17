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
