# W12 shared workspace

W12 uses Kutt v2.7.4, an MIT-licensed URL shortener with a TypeScript server,
Next.js client and Jest tests. The locked install contains 2,830 packages.
The source archive, lockfile, Node image, patch and expected output receipts
are pinned in `workload.json`. The fixture adds no product dependencies.

Cache preparation and offline installation both use `--legacy-peer-deps`.
Node 22 requires `NODE_OPTIONS=--openssl-legacy-provider` for Kutt's webpack.
The fixture uses both settings on both engines. The fixture Dockerfile embeds
an npm cache populated from the lockfile and checks the archive and lock hashes.
`identity-proof.py` checks the ordered image DiffIDs and in-image hashes on
both engines. The engines report different immutable image IDs; both are
recorded in `workload.json` and used on their respective engine.

W12 runs a cold offline `npm ci` with the container network disabled. It
builds the server with `tsc` and copies the mail templates, then runs the
Next.js client build. These are Kutt's build steps, without the initial
`rimraf` of the server output mount. It checks typecheck output, Jest's sorted
test list, a warm rebuild, a ten-file patch, and the restored branch.
The server receipt hashes sorted regular-file paths, sizes and contents.
The client receipt hashes the build manifest after replacing Next.js build
IDs, generated 40-character chunk identifiers, and runtime filenames derived
from numeric chunk IDs. It separately hashes the main and polyfills runtime
contents after replacing those numeric IDs. Other content hashes remain in
the manifest receipt. Counts cover regular files and bytes under `/app` after
installation, and installed packages under `node_modules`.
An owned, network-isolated Node readiness check starts the guest before
resource sampling. Setup is recorded separately and is not scored.

W12-watch uses Kutt's TypeScript compiler in watch mode with
`TSC_WATCHFILE=UseFsEvents` and `TSC_WATCHDIRECTORY=UseFsEvents`. It records
`fs.watch` as the configured backend. It verifies emitted JavaScript against
TypeScript's `transpileModule` for the exact edited content and waits for a
zero-error watch cycle. Bind edits use host filesystem operations. Volume
edits use `docker exec`. Each burst writes five files within 50 ms. Missed and
stale results are recorded separately. No polling fallback is enabled.

Prepare the pinned image and run the functional proof from the repository root:

```sh
TMPDIR="$PWD/.work/tmp" PYTHONDONTWRITEBYTECODE=1 python3 bench/native/fixtures/w12/prepare.py
TMPDIR="$PWD/.work/tmp" PYTHONDONTWRITEBYTECODE=1 python3 bench/native/fixtures/w12/identity-proof.py
TMPDIR="$PWD/.work/tmp" PYTHONDONTWRITEBYTECODE=1 python3 bench/native/fixtures/w12/proof.py --all
```

Preparation saves the image at `.work/tmp/w12-image.tar` and the source archive
at `.work/tmp/kutt.tar.gz`. If the pinned image is unavailable, preparation
builds a candidate and fails if its identity differs from the recorded pin.

The proof driver uses the pinned signed ctrs binary and a fresh private engine.
It writes complete records under `.work/native-perf/results/` and prints one
summary per condition. These runs are functional checks, not comparisons.
