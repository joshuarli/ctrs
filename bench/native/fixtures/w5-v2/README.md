# W5 Marked watch, rebuild and test

This fixture measures edits to the real Marked TypeScript application. A persistent
esbuild context rebuilds the compiler and runs the Marked CLI after each edit.
The test requires the exact HTML, a successful exit and empty stderr. Each edit
alternates the heading renderer between its original output and `class="w5"`.
Paragraph, link and emphasis rendering must also remain correct.

`workload.json` owns the source archive, dependency-lock hash, Node image digest,
Node and npm versions, edit patterns and exact test output. Preparation verifies
the archive and lockfile. Image validation checks ARM64, Node, npm, esbuild
from the lockfile, and fixture hashes before each trial. Preparation builds
and exports one image for all selected engines. Marked v15.0.12 is MIT
licensed. `npm ci` installs its
locked development dependencies, including esbuild, inside the fixture image.
No dependency is added to ctrs.

The runner prepares a fresh source directory for bind mounts and a fresh labelled
volume for guest-volume trials. Both watchers use the inspected immutable
image ID. Before the first edit, the runner verifies the mount's identity,
every mounted file against the pinned archive, and the installed CLI and
lockfile. Dependencies and generated bundles stay outside the source mount.
Both modes retain one watcher PID and start identity across all
edits. An early exit, timeout, unexpected event, output mismatch or restart fails
the trial. Cleanup verifies ownership before removing containers and volumes.

The primary interval begins on the host before the edit and ends when the host
receives the exact successful test event. Bind edits use a host file write.
Volume edits include Docker exec transport and the guest edit command. Raw records
retain command completion and event receipt separately. Setup includes source
extraction or volume population and the initial build and test. Input
verification, each edit, and cleanup have separate resource boundaries.
Incomplete ownership or counter coverage invalidates the measurements.
For each mount, the paired report uses CPU charged during the exact verified
edits divided by their count. Sampled footprint is the maximum across that
mount's setup, input verification, edits and cleanup.

From the repository root, prepare and run the selected engine:

```sh
TMPDIR="$PWD/.work/tmp" python3.14 bench/native/runner.py prepare --only W5 --engines orbstack,ctrs
TMPDIR="$PWD/.work/tmp" python3.14 bench/native/runner.py run --engine orbstack --case W5 --state warm
```

Source archives and build artifacts stay under `.work/`.

Current records use `w5-v3-marked-receipts`. The report admits a pair only
when both sides observed the same ordered image DiffIDs, tool receipts
and source and lock hashes. Keep earlier W5 cohorts separate. Functional
pilots establish fixture behavior and leave performance qualification open.

`pyramid.py run --name w5-esbuild-watch:cohort` uses 60 edits per mount.
The report derives nearest-rank p95 from each mount's complete verified
edits and compares those values across pairs. The five-edit check remains
available as `w5-esbuild-watch`. Use `baseline --case W5 --watch-edits 60`
to select the longer workload directly.
