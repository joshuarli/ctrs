# W9 fixed CI jobs

Every concurrency condition runs the same 16 jobs. Each fresh container builds the
pinned Marked TypeScript source with esbuild, runs three real CLI golden cases,
and returns exact tool versions, source-lock hash, bundle hash and test results.
There are no timed work loops. jobs.json owns the count, concurrency and goldens;
W8's common portfolio owns the immutable image/artifact/tool pins, and W5 owns
the source lock. The image must already exist; job containers have no network.

After preparing the common W8 portfolio, select its Marked digest reference from
the printed result directory and pass it explicitly:

```sh
python3.14 bench/native/runner.py run --case W9 --engine ctrs \
  --image-ref '127.0.0.1:PORT/np-v2/marked@sha256:0d507a8e7c2f89ffd80ddb8dd625bb482643d8da44d30a35391e1c1c87f875b7'
```

run, baseline and noop require the pinned reference; tags and other digests are
rejected before engine access. New metrics fixed16_at_1_s/4_s/8_s/16_s measure
whole job batches, including create/start/build/test/rm. Warmup excludes VM boot.
Setup and cleanup have separate native boundaries. All per-job outputs and
failures are retained; a failed condition is not retried or omitted. Cleanup
checks labels before removal. Pending jobs are cancelled on interruption and
already-running calls have finite timeouts. Required engine/VM resource coverage
remains strict; client/coordinator CPU is outside the declared engine CPU scope.

v1 varied both work count and concurrency and used an elapsed 0.6-second hash loop.
Those historical records remain diagnostic; new metric names, fixture version
and provenance prevent pooling. The old loop remains only in the unfinished W11
proxy, which cannot close reliability acceptance. Native pilots demonstrate
functional equivalence; frozen interleaved timing/resource qualification remains
open, especially while unrelated host work is active.
