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
The leaf-only diagnostic accepts this hash for its native admission run.
Guest validation and the interleaved observer budget remain open. The
existing stack and syscall diagnostics still require their original archive.
