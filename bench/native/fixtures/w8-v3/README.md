# W8 derived content-unique portfolio

`registry_variant.prepare_variant(layout, contract, destination, seed)` verifies
an existing pinned W8 v2 common OCI layout and creates a new destination directory.
`contract` is the v2 portfolio object and `seed` is explicit bytes of length 1 to
1024. The destination must not exist, must be separate from the source, and must
be in caller-owned scratch. The function returns and writes `receipt.json` with
source and derived identities, seed hash, method, and Python/zlib versions.
Failures remove the owned destination. Do not write to the destination concurrently.

Each distinct source layer receives a deterministic owned marker based on the seed
hash and original uncompressed DiffID. Original tar bytes through the last member
are preserved; the marker precedes new terminal records. Outputs use gzip level 9,
zero mtime and no filename. Shared source layers remain shared. The image config
retains its original fields except updated rootfs DiffIDs and the owned fixture
label. The selected Linux ARM64 images are represented directly in the output index.
Unsupported layer media, sparse or global tar headers, oversized extensions, and
ambiguous tar layouts fail closed. Identical source, seed, Python and zlib produce
the same artifact bytes; the receipt records tool versions rather than asserting
cross-version or fresh-host reproduction.

Use one prebuilt artifact for both engines. A different seed changes every layer's
compressed digest and DiffID. This artifact targets a warm-engine unseen-content
comparison; generation alone proves neither guest content absence nor an empty
store or cold engine. Native content-absence and retained-state verification,
matched transfer phases, and qualification remain pending. Never pool w8-v3
results with v2 or other fixture histories.
