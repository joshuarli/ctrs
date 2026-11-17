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
and qualification remain pending. Never pool w8-v3
results with v2 or other fixture histories.

For native functional validation, generate a portfolio with an explicit fresh
seed, then run the diagnostic with that same artifact for both engines:

```sh
TMPDIR=$PWD/.work/tmp PYTHONPATH=bench/native python3.14 - <<'PY'
import json
from pathlib import Path
from registry_variant import prepare_variant
prepare_variant('.work/native-perf/inputs/w8-portfolio-v2/layout',
    json.loads(Path('bench/native/fixtures/w8-v2/portfolio.json').read_text()),
    '.work/native-perf/inputs/w8-new-variant', b'explicit-fresh-comparison-seed')
PY
TMPDIR=$PWD/.work/tmp python3.14 bench/native/diagnostics/registry_variant_pilot.py \
  --layout .work/native-perf/inputs/w8-new-variant \
  --ctrs-binary .work/tmp/disk-expand-target/release/ctrs
```

The diagnostic requires each derived config to be absent through the image API,
complete GET bodies for every distinct layer, exact installed marker payloads,
the existing service/Marked integrity checks and unchanged retained image IDs.
Shared layers count once per engine. Incomplete downloads and HEAD responses
cannot establish transfer. The labelled marker containers and application stack
have owned cleanup. Derived images remain installed; use a new seed and new
destination for a subsequent unseen-image trial. API absence does not prove
absence from every guest content cache, and this command does not score timings.

The functional diagnostic records native owned-engine process CPU and sampled
physical footprint for setup and image inspection, each pull/install and marker
check, image identity, stack health, fixed load, persistence recovery, Marked
verification, retained identity and owned cleanup. Docker combines transfer and
guest installation in each pull. Phase boundaries, ownership and the sampler
trace are retained with each engine result; missing counters or failed phases
remain unknown and invalidate correctness for this resource diagnostic. The
resource scope excludes the host registry, coordinator, CLI and active backing
allocation. Sampled footprint is not a continuous peak. Host snapshots accompany
the run, which remains ineligible for qualification and makes no timing claim.
