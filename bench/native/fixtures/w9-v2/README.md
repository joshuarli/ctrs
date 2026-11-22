# W9 fixed CI jobs

Every concurrency condition runs the same 16 jobs. Each fresh container builds the
pinned Marked TypeScript source with esbuild, runs three real CLI golden cases,
and returns exact tool versions, source-lock hash, bundle hash and test results.
There are no timed work loops. jobs.json owns the count, concurrency and goldens;
W8's common portfolio owns the immutable image/artifact/tool pins, and W5 owns
the source lock. The image must already exist; job containers have no network.

Prepare and install the [W8 v6 portfolio](../w8-v6/README.md) on both engines.
The cohort finds the installed Marked digest reference on OrbStack:

```sh
python3 bench/native/pyramid.py run --name w9-jobs:cohort
```

For a direct `runner.py run`, `baseline` or `noop` invocation, pass
`--image-ref` with the installed `np-v6/marked` manifest digest reference.
The `fixed16_at_1_s/4_s/8_s/16_s` metrics measure
whole job batches, including create/start/build/test/rm. Warmup excludes VM boot.
Setup and cleanup have separate native boundaries. All per-job outputs and
failures are retained; a failed condition is not retried or omitted. Cleanup
checks labels before removal. Pending jobs are cancelled on interruption and
already-running calls have finite timeouts. Required engine/VM resource coverage
remains strict; client/coordinator CPU is outside the declared engine CPU scope.
At each concurrency, the report divides the engine CPU charged over the
job phase by the 16 verified completions and uses that phase's sampled
physical footprint. Missing or invalid phase receipts leave the corresponding
resource cells unmeasured.

v1 varied both work count and concurrency and used an elapsed 0.6-second hash loop.
Those historical records remain diagnostic; new metric names, fixture version
and provenance prevent pooling. The old loop remains only in the unfinished W11
proxy, which cannot close reliability acceptance. Native pilots demonstrate
functional equivalence; frozen interleaved timing/resource qualification remains
open, especially while unrelated host work is active.
