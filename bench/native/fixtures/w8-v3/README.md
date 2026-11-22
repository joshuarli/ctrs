# W8 derived content-unique portfolio

`registry_variant.prepare_variant(layout, contract, destination, seed)` verifies
an existing pinned common OCI layout and creates a new destination directory.
`contract` is the common portfolio object and `seed` is explicit bytes of length 1 to
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
prepare_variant('.work/native-perf/inputs/w8-portfolio-v6/layout',
    json.loads(Path('bench/native/fixtures/w8-v6/portfolio.json').read_text()),
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

Before resource sampling, both engines execute and verify an owned no-pull Python
container to establish the declared warm-engine state. Daemon readiness alone
does not establish a booted ctrs VM. Boot and preconditioning are outside the
warm-phase resource scope and remain separate acceptance cells.

The functional diagnostic records native engine plus registry/coordinator CPU and sampled
physical footprint for setup and image inspection, each pull/install and marker
check, image identity, stack health, fixed load, persistence recovery, Marked
verification, retained identity and owned cleanup. Docker combines transfer and
guest installation in each pull. Phase boundaries, ownership and the sampler
trace are retained with each engine result; missing counters or failed phases
remain unknown and invalidate correctness for this resource diagnostic. The
registry thread lives in the coordinator, whose self PID, kernel start identity
and loaded executable are recorded in the required-process manifest. Missing
fixture counters invalidate the combined result. The scope version is
`w8-engine-fixture-v1`; keep earlier engine-only records separate. Waited-child
CPU deltas are disclosed per phase; they cover children reaped in that interval,
exclude live children and are not phase-aligned client totals. CLI footprint,
sampler overhead and active backing allocation remain excluded.
Sampled footprint is not a continuous peak. Host snapshots accompany
the run, which remains ineligible for qualification and makes no timing claim.

`--under-load` selects the separate `w8-v4-under-pull` instrumented history.
It starts an independent project from the original v2 API, PostgreSQL and Redis
immutable IDs and checks their DiffIDs, application hashes and workload inputs.
ctrs resolves the contract's config digest; OrbStack's current containerd image
store resolves its manifest digest. The selected kind and exact inspection are
recorded. Legacy tags do not select the background stack.
The project uses its own network and volume; images are never built or pulled
for this stack. A separate client runs the pinned W2 worker for 50,000 attempts,
four workers, write ratio 0.3 and seed 7. Its first successful completion admits
pulls. Every pull/install interval must contain a successful completion, and
fixed work, error counts and every acknowledged database payload must verify.
Early completion or missing overlap fails the run; no work or pairs are extended.

The client records every successful latency with its callback completion time,
acknowledged writes, errors, stdout and stderr. Interval percentiles describe
requests observed completing during a pull; callback time does not establish an
exact request start. The sampler covers baseline setup, pulls, verification and
cleanup. Waited-child CPU remains diagnostic and does not cover all client work.
This fixture is not a qualification or all-client footprint claim.
Add `--under-load` to the command above to select it. The pinned common images
must already be installed on both engines. Follow the [W8 v6 portfolio
instructions](../w8-v6/README.md) before generating the variant. Warmup uses the same
store-specific pinned API ID. An isolated ctrs root with only the common API
manifest installed and no legacy tag passes warmup; this does not qualify the
remaining fresh-host matrix.

The paired pilot starts from the original pinned v6 layout:

```sh
python3.14 bench/native/runner.py w8-baseline \
  --layout .work/native-perf/inputs/w8-portfolio-v6/layout \
  --ctrs-binary /path/to/signed/ctrs --pairs 10
```

Add `--under-load` for fixed background work or `--diagnostic` for functional
checks with invalid timing. Each pair shares one newly derived artifact and
alternates order. Original pinned common images must already be installed on
both engines. Startup and warm preconditioning are outside the whole-workflow
resource interval. Nested phases are diagnostic and must not be added to it.
With `--content retained`, the largest layer of each image gets the per-pair
marker. Every other compressed layer descriptor and DiffID must equal the
source. The registry must deliver each changed layer in full, and the existing
retained image pins must verify before and after deployment. This records
retained image contents while cache state below the image API remains unknown.
The sampled footprint is not a continuous peak; CLI and sampler resources,
active storage allocation, metadata qualification and the full matrix remain
open. This is a pilot, not qualification.

The default `--resource-lane matched` uses the resident control. The owned
ctrs daemon uses `CTRS_IDLE_SECS=0`, keeping the VM resident between pairs.
Set `--resource-lane installed-default` to compare the normal resource and idle
settings. Each leg primes the VM before sampling. A ctrs VM may exit between
legs in this lane. Sampling verifies process identity throughout each leg,
and both engines must retain the same daemon identity and resource budget
across the cohort. Diagnostic batches return zero for correct functional work
and have invalid timings. Legacy W8 records remain historical only.
