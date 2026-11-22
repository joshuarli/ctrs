# Rebuild the W8 common portfolio

W8 v6 serves four native linux/arm64 images through a loopback registry.
The same manifests, configs and layer DiffIDs feed both engines. PostgreSQL
and Redis retain their v5 digests. The API and Marked have new image
identities and need fresh baselines. The API source and Marked app output
checks remain pinned.

Use Python 3.11+ and an available OrbStack daemon on Apple Silicon. The
reproduction used OrbStack 2.2.5, Docker CLI 29.8.2, buildx 0.37.2 and the
OrbStack docker driver's BuildKit 0.33.1.

```sh
export TMPDIR="$PWD/.work/tmp"
python3 bench/native/fixtures/w8-v6/prepare.py
python3 bench/native/diagnostics/registry_pilot.py \
  --layout .work/native-perf/inputs/w8-portfolio-v6/layout \
  --ctrs-binary target/release/ctrs
```

Preparation pulls PostgreSQL and Redis by digest, rebuilds the API and
Marked from pinned bases and locked dependencies, and exports only the
four selected image manifests and their blobs in a canonical archive.
BuildKit uses `SOURCE_DATE_EPOCH=0` and rewrites layer timestamps.
The API pins every wheel hash. Marked discards npm's transient cache and
disables Node's compile cache during preparation. The OCI layout and
archive digest are checked before the files are installed under
`.work/native-perf/inputs/w8-portfolio-v6/`.

The registry pilot loads the four images into both stores, verifies the
exact API, database and cache workload outputs and restart persistence,
and runs the pinned Marked artifact check. Run it before the paired
installed-default cohorts that consume these images. Plain `runner.py prepare`
installs the legacy pilot images.
