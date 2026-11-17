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
