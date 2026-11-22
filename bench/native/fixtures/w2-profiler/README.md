# Rebuild the W2 native profiler bundle

Build on the campaign Mac after the measured queue clears. The pinned base
matches the v6 API image. Debian's dated package indexes authenticate the
historical ARM64 `linux-perf` package and its runtime dependencies.

```sh
mkdir -p .work/tmp
orb="unix://$HOME/.orbstack/run/docker.sock"
for leg in first second; do
  output=$(mktemp -d "$PWD/.work/tmp/w2-profiler-$leg.XXXXXX")
  docker -H "$orb" buildx build --builder default --no-cache \
    --platform linux/arm64 --output "type=local,dest=$output" \
    bench/native/fixtures/w2-profiler
  shasum -a 256 "$output/native-tools.tar.gz"
done
```

On the campaign Mac, two uncached builds produced the same
`native-tools.tar.gz` with SHA-256
`990b13e40dcd7726198911b133c2ac59a7df8576f7c914b88b5f4b6527340ae4`.
Both exported identical package lists and reported `perf version 6.12.117`.
The leaf-only diagnostic accepts this hash. The existing stack and syscall
diagnostics still require their original archive.

Native admission `w2-guest-client-cpu-leaf-20261122T094043-03e7`
used source `4684639`, the v6 portfolio, and the signed host and guest
artifacts from the fixed-work W2 cohort. All four off/on legs completed
50,000 verified requests at concurrency eight from a guest peer. The
profiled legs covered all nine API threads on each engine, with 1,135
ctrs and 959 OrbStack samples. The raw event checks found no loss or
throttle records. Both engines finished owned cleanup. The interleaved
observer overhead budget remains open.

Use the same digest references for the three services on both engines.

```sh
python3 bench/native/diagnostics/syscall_pilot.py \
  --tools-archive "$bundle/native-tools.tar.gz" --image-refs "$refs" \
  --ctrs-binary target/release/ctrs --profile-kind cpu-leaf \
  --client-location guest --operations 50000 --concurrency 8
```

The admission `plan.json` SHA-256 was
`fcb5ac3561b2c8be3551cbe226ff7003c82157cbc8155360d1b416d293c81da3`.

For overhead confirmation, run ten blocks with those workload settings.
Odd blocks use `--mode-order off,on --engines ctrs,orbstack`. Even blocks
use `--mode-order on,off --engines orbstack,ctrs`. Put each attempted
block's receipt directory in the shell array `block_dirs` in run order.

```sh
python3 bench/native/diagnostics/w2_observer_report.py "${block_dirs[@]}"
```

The report checks fixed inputs, verified work, sample coverage and host
admission per leg. With `outside-engine-workload-cpu-v1`, work measured
outside the engine and harness must stay at or below two host cores
during each timed workload. The global gates still record busy hosts for
review. Older receipts require both global gates to pass. Start and finish
the batch with a quiet host outside the engine runs.

The report applies the 5% budget to the paired median interval with CPU
counter quantization included. Exit zero means all four numerical checks
passed. Review the saved process, power and thermal snapshots before
accepting the observer for attribution.

The original confirmation's block 2, `w2-guest-client-cpu-leaf-20261122T094748-52c1`,
failed the ctrs profiler-off post-workload gate. The gate flagged PID
74836 as hot. The same PID and kernel start identity appear in the owned
VM receipt and the workload CPU counters. The block remains invalid
under its original plan.

The lower-overhead candidate is `--profile-kind cpu-leaf-25`. It uses
a fixed 40 ms CPU-time period, the same archive, exact workload and
outside-engine admission rule. It still requires every API thread and
zero recorded sample loss. Verify coverage in one native block before
starting a new ten-block overhead confirmation. Keep its receipts
separate from the 49 Hz capture.
