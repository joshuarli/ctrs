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

The two archives must match before selecting a new profiler hash. Verify
the bundle inside the pinned API image on both engines before using it for
observer comparisons. Keep the original observer archive hash until
that proof passes. The package versions and executable version travel with
each candidate archive.
