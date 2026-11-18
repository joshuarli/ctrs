> **Superseded 2026-11-18.** The artifacts described here were not recoverable on the new
> macOS host. The pins were refreshed as [w8-v5](../w8-v5/README.md); use that fixture for
> any current work. This file and the v2 contract remain as the historical pin set.

# W8 common multilayer portfolio

`portfolio.json` pins four native ARM64 images: the real Python API, PostgreSQL,
Redis, and the Marked TypeScript build/test environment. All images come from one
read-only export, not independent builds or flattened scratch copies. The same
selected manifest/config/diff IDs are served to both engines. Service/tool
versions, application contents, seed/load inputs and the exact Marked artifact
are enforced. Changing these inputs requires a fixture version and new baselines.

The retained local artifact is `.work/native-perf/inputs/w8-portfolio-v2/`:
`portfolio.tar` SHA256 99dbbad6ba7df1f16919c7c41aaff39886cc2a826536deb3caf73be2dc51a592,
390,585,344 bytes. The directory contains the extracted OCI layout, source image
inspections, export driver and preparation receipt. The archive is not committed.
Re-export requires exact source image IDs, not mutable tags. The config digests
in tracked `portfolio.json` are those Docker image IDs, so the scratch receipt
is not required to identify them. The shared OrbStack store retains these inputs.
Use a new owned tag namespace with the existing `layout_reference` tag suffixes,
save those exact images through the explicit Unix endpoint, and extract the OCI
archive with `tarfile.extractall(filter='data')`. Validate the resulting layout
with `registry_portfolio.prepare_pinned_portfolio(layout, contract)` before use.
Record a fresh export receipt without rewriting the historical archive checksum.
If pinned manifests or blobs cannot be recovered, stop or version new inputs and
affected baselines. Do not silently substitute an image. Publication/reproduction
on another host remains open.

```sh
TMPDIR=$PWD/.work/tmp python3.14 bench/native/diagnostics/registry_pilot.py \
  --layout .work/native-perf/inputs/w8-portfolio-v2/layout \
  --ctrs-binary .work/tmp/image-diffids-target/release/ctrs
```

The independent loopback host server verifies all selected blob bytes before
serving, streams files without loading the portfolio into RAM, records GET/HEAD
body bytes and incomplete transfers, and shuts down with its owner. No Docker
registry container or shared daemon restart is involved. ctrs must include the
RootFS diff-ID fix cdcbfb4. The driver verifies actual running artifacts after boot.

After pulling, the diagnostic checks common layer identity, brings up a healthy
API/database/cache stack, completes 1,000 fixed mixed requests, checks every seed
and acknowledged-write payload, and verifies a committed DB/cache value across
application restart. It builds Marked with pinned tools and verifies exact CLI
HTML and bundle hash. Only owned containers/networks/volumes are cleaned up;
common image content is retained. Saved failures remain failures.

This is functional coverage, not final W8 qualification. The old flattened v1
fixtures remain diagnostic-only. No deleted-tag state is called cold. Record
actual transferred bytes and establish content absence separately. Shared
OrbStack content must not be pruned to manufacture a cold cell. Cold/retained
comparison design, interleaved timing/resource phases, workload freeze and final
qualification remain open; do not pool v1 results with this portfolio.
