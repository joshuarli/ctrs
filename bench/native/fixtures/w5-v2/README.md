# W5 v2: Marked CLI watch and test

This fixture uses the Marked v15.0.12 Markdown compiler and CLI (MIT):
https://github.com/markedjs/marked/tree/v15.0.12. Its upstream archive is
`https://codeload.github.com/markedjs/marked/tar.gz/refs/tags/v15.0.12`,
SHA256 `2da1adfd5d17b47477dbeecdf6d9de69cbfd84558320807987406b9e7a1e8ca5`.
The archive's `package-lock.json` SHA256 is
`5acaa75805a6efc1d58be5415cc94cb09058ad6ec3ff7c0fb1a4f05491b1abf4`.
The image is Node v22.15.0, npm 10.9.2,
`node:22.15.0-bookworm-slim@sha256:557e52a0fcb928ee113df7e1fb5d4f60c1341dbda53f55e3d815ca10807efdce`
(multi-platform index; require linux/arm64). `npm ci` installs the upstream
lockfile including development dependencies, including esbuild. No dependency
is added to the product. The installed size and preparation time are unverified.

`watch.mjs` starts one persistent esbuild watch context on the mounted source,
bundles the real TypeScript entry point, and invokes the real Marked CLI against
a Markdown document after each build. It checks the entire HTML output, CLI
exit status and stderr. A build or test failure terminates the watcher. Each
successful build emits one JSON line with `event: tested`, `state: original` or
`edited`, and the complete `output`. The controlled edit changes the renderer's
heading output to include `class="w5"`; paragraph, link and emphasis rendering
must also match exactly. `edit.mjs` accepts only the exact pinned source state
and refuses repeated or unexpected edits. The CLI and generated bundle live in
the image; only source is mounted, so dependency and bundle writes do not
contaminate the bind or the volume.

## Preparation

Use a scratch directory under `.work/`, never commit extracted sources,
`node_modules` or image artifacts. Set `F` to this fixture's absolute path and
`D` to a fresh scratch build-context path. From the repository root:

```sh
F="$PWD/bench/native/fixtures/w5-v2"
D="$PWD/.work/tmp/w5-v2-context"
mkdir -p "$D"
curl -fL https://codeload.github.com/markedjs/marked/tar.gz/refs/tags/v15.0.12 -o "$D/marked.tar.gz"
python3 "$F/prepare.py" "$D/marked.tar.gz" "$D/source"
cp "$F/Dockerfile" "$F/watch.mjs" "$F/verify.mjs" "$F/edit.mjs" "$D/"
```

After the parent authorizes container work, build with `docker build --platform
linux/arm64 -t <owned-image> "$D"`. Verify the resulting image architecture,
Node/npm versions and installed size; retain exact build output and exit status.
Use a dedicated explicit Docker endpoint and unique owned image, container and
volume names. Never alter Docker contexts or prune shared resources.

## Parent runner integration and bounded pilot

Pilot is **pending** parent clearance and real execution. For each of bind and
volume, give startup and each edit at most 120 seconds; any timeout, early exit,
nonzero exit, build error, duplicate/unexpected event or output mismatch is a
failure. Capture complete logs and process exit statuses. Keep the same watcher
container and PID from its initial `original` event through the `edited` event.
Verify the JSON `output` byte-for-byte against the exported constants in
`verify.mjs`, not just the state string. Check the watcher is still alive after
the second event. Run one trial per mount mode before any measurement.

* Bind: start a container from the image with a fresh prepared source directory
  mounted at `/src`. Wait for the exact original event. On the host run
  `node "$F/edit.mjs" <host-source> edited`, then wait for the exact edited
  event. The edit command is the host-side control cost.
* Named volume: create a fresh owned volume, populate it from `/opt/seed` using
  a one-shot container and `cp -a /opt/seed/. /src/`, then start the watcher
  with that volume mounted at `/src`. Wait for the exact original event. Run
  `docker exec <watch-container> node /opt/app/edit.mjs /src edited` and wait
  for the exact edited event. Record population and exec/edit costs separately
  from the host edit and from the watch-to-tested interval.

Use separate fresh source copies for each trial; do not reuse the Docker build
context source as the bind trial's mutable source. Record edit start, command
completion and matching event receipt independently, and describe whether the
reported edit-to-result interval includes command launch/transport. Keep failed
trials and logs. Remove only the uniquely owned container, volume and image after
checking ownership. No performance or acceptance claim follows from this recipe
until both pilots actually pass. Old W5 results are not comparable.
