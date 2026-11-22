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
