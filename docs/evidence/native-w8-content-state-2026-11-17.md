# W8 content-state boundary, 2026-11-17

The source investigation at d9295f9 supports a narrow statement: the fixture
creates fresh derived compressed layer identities and DiffIDs, requires full
registry delivery, and verifies runnable application/marker contents. It does
not establish fresh application bytes, an empty store, guest-unpacked cache
absence, or page-cache state on either engine. Original app bytes remain intact;
seed-specific marker files change each layer identity.

`bench/native/registry_variant.py` verifies the source DiffIDs before appending
markers. `registry_portfolio.py` records completed server writes. The variant
pilot checks missing image identities, required distinct-layer GET delivery,
actual markers, health, fixed application work and exact DB/cache state. Server
writes do not independently prove when/how a layer was installed. The pilot
correctly records pre-content state as unknown below the image API.

ctrs has two distinguishable caches: owned host compressed blobs in
`crates/ctrs-image/src/store.rs`, and guest unpacked layers queried by compressed
digest through the existing LayerQuery path in daemon/engine.rs and
ctrs-init/src/linux/layers.rs. An exact owned pre/post probe could strengthen
ctrs-specific evidence. The public image-inspection path used here does not
supply an equivalent OrbStack guest-cache inventory. No private OrbStack paths,
VM mechanisms, or cold-cache facts are inferred. No runtime probe ran.

Independent worker usrw_bfa80807-06b8-4273-9e84-87f01e22ef23 reviewed these paths
read-only and left its checkout unchanged. Parent accepted the supported limits.
The next bounded source slice is executable receipt validation: each distinct
derived compressed digest and DiffID must differ from its source and every prior
pair, with complete source/derived mappings. Reject duplicate, missing or
mismatched entries before engine measurement. This strengthens identity evidence
and must leave cache absence explicitly unknown. Existing identical-input,
transfer and deployment checks remain required; historical batches are not
retroactively upgraded into qualification.

Receipt validation is integrated at df1f418 from worker82734b4. It rejects
missing, duplicate, source-equal or previously used compressed digests and
DiffIDs, and mismatched source contracts/seeds before measurement. Expected
sharing within one pair remains valid. Parent reviews the complete diff and
runs `python3.14 bench/native/runner.py check w8`:66 tests, zero skips.
The validator also accepts both retained37-layer pair receipts from
`w8-paired-f8cf4ddcd42e`, with74 distinct derived identities across the pairs.
No engine rerun or retrospective qualification occurs. Cache absence remains
unknown at the boundary described above.


Retained inspection now validates every returned image against the
common portfolio at `4c07c4e`. The before and after snapshots both
require complete coverage, ARM64 and the pinned DiffID list. ctrs uses
the pinned config ID and OrbStack uses the pinned manifest ID. The
under-pull baseline uses the same check. The eight archived inspections
from the two native pairs validate on the new code. Negative cases
cover missing images, wrong order and unchanged IDs with wrong layers
or architecture. The W8 component suite passed 68 tests, zero skips.
The native results retain the original measurements and cache scope.

## Interrupted delivery and retry

The W8 cancellation diagnostic runs one of two content conditions. Both
start with the complete pinned W8 v2 portfolio installed. The retained
condition derives the largest Marked layer and keeps the other layers
byte-identical to the source. The derived condition changes every layer.

```sh
python3.14 bench/native/runner.py w8-cancel \
  --layout "$W8_COMMON_LAYOUT" --ctrs-binary "$CTRS_BINARY" \
  --engine ctrs --content retained
```

Run each content condition separately on each engine. The registry sends a
partial blob and holds the rest while the harness interrupts the owned pull
client. Success requires a failed client exit, a registry-observed disconnect
after interruption, the candidate image still absent, and unchanged retained
pins. A separate registry endpoint must fully deliver the held layer on retry.
The harness checks the resulting image identity, ordered DiffIDs, architecture
and marker contents, then removes the generated reference without pruning.
Its `result.json` tracks cancellation and retry transfers and marks all
measurements invalid for scoring.

The W8 component suite passed 74 tests with zero skips. It includes a real
loopback transfer interrupted through an owned process and a completed retry.

OrbStack passed retained (`w8-cancel-2debc4544403`) and derived
(`w8-cancel-8f9bcfd81520`) on native ARM64. Each registry wrote 65,536
bytes of the held layer before it observed the engine disconnect. The
retry fully delivered the 120,861,274-byte retained-condition layer and the
120,861,273-byte derived-condition layer, respectively. Exact identity,
marker, retained-pin and cleanup checks passed. These are correctness runs.

ctrs retained (`w8-cancel-7ec83f2a59ae` and `w8-cancel-0a9f047561ed`)
failed with two signed binaries. The client exited with `context canceled`.
The daemon registered the last client leaving about half a second into the
pull, then exited the pull when the registry's 10-second hold expired.
The body read in `crates/ctrs-image/src/transport.rs` has a 60-second
production stall deadline. The cancel flag is checked after that blocking
read returns. The existing Rust test uses a 1-second transport timeout,
so it allows the timeout to wake the read. ctrs derived and retry proof
remain open. Keep the fixture cutoff and require a transport regression
that wakes a blocked body read on cancellation with the production
stall deadline in force.

The failing ctrs run `w8-cancel-0a9f047561ed` used binary SHA256
`db20b2106a9faadf8760e65a11357155166b2ed77fb6de784d63defe0ddbaada`.
Its daemon logged the last client leaving at `00:15:14.091Z` and the
pull stopping at `00:15:23.588Z`. The transport uses
`h12tiny-client-sync` 0.9.0. The crate's current source is in the
smolith workspace. Its blocking response body exposes a read timeout
but does not expose a connection shutdown handle.

## Backing allocation during deployment

Run the paired pilot with `--diagnostic --orbstack-storage-file PATH` to
collect allocation receipts. Repeat the flag for each explicit OrbStack
backing file. ctrs uses the data disk under its benchmark engine directory.
The producer checks open device and inode identity across the three
snapshots and ties each open file to an engine process with a verified
start identity. It collects snapshots before the first pull, after
deployment verification, and after cleanup of the application containers
and volumes. It records the running-container inventory before and after.

The receipt reports allocated blocks for the declared files and changes
relative to the first snapshot. It includes retained images and other
allocation in those files. Exclusive extents and isolated cache allocation
remain unknown. Missing ownership and changed file identities invalidate
the receipt. The W8 component suite passed 75 tests with zero skips.

One native diagnostic pair (`w8-paired-6c16ce569449`) completed the
derived deployment and verified all three owned-file observations on
both engines. All values below are bytes allocated in the declared
backing file at that boundary. Both records are marked ineligible for
timing and qualification.

| Engine | Before pull | Before app cleanup | After app cleanup |
| --- | ---: | ---: | ---: |
| ctrs | 1,489,813,504 | 2,677,981,184 | 2,678,620,160 |
| OrbStack | 328,923,557,888 | 330,461,614,080 | 330,460,717,056 |
