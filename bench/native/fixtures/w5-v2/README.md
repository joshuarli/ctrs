# W5 v2: Marked watch, rebuild and test

This fixture measures edits to the real Marked TypeScript application. A persistent
esbuild context rebuilds the compiler and runs the Marked CLI after each edit.
The test requires the exact HTML, a successful exit and empty stderr. Each edit
alternates the heading renderer between its original output and `class="w5"`.
Paragraph, link and emphasis rendering must also remain correct.

`workload.json` owns the source archive, dependency-lock hash, Node image digest,
Node and npm versions, edit patterns and exact test output. Preparation verifies
the archive and lockfile. Image validation checks ARM64, tool versions and fixture
hashes before each trial. Marked v15.0.12 is MIT licensed. `npm ci` installs its
locked development dependencies, including esbuild, inside the fixture image.
No dependency is added to ctrs.

The runner prepares a fresh source directory for bind mounts and a fresh labelled
volume for guest-volume trials. Dependencies and generated bundles stay outside
the source mount. Both modes retain one watcher PID and start identity across all
edits. An early exit, timeout, unexpected event, output mismatch or restart fails
the trial. Cleanup verifies ownership before removing containers and volumes.

The primary interval begins on the host before the edit and ends when the host
receives the exact successful test event. Bind edits use a host file write.
Volume edits include Docker exec transport and the guest edit command. Raw records
retain command completion and event receipt separately. Setup, each edit and
cleanup have separate resource boundaries. Setup includes source extraction or
volume population and the initial build and test.

From the repository root, prepare and run the selected engine:

```sh
TMPDIR="$PWD/.work/tmp" python3.14 bench/native/runner.py prepare --engines orbstack
TMPDIR="$PWD/.work/tmp" python3.14 bench/native/runner.py run --engine orbstack --case W5 --state warm
```

Preparation also builds the campaign's other fixtures. Use the explicit engine
option for ctrs. Never change Docker contexts or prune shared resources. Source
archives and build artifacts stay under `.work/`.

W5 v2 records use `w5-v2-marked` and separate bind and volume metrics. Earlier
Python-loop W5 records remain diagnostics and cannot be pooled with these results.
Functional pilots establish fixture behavior. They do not freeze the final
workload size or qualify performance.
