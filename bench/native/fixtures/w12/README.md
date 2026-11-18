# W12 candidate: Kutt

Kutt v2.7.4 is an MIT-licensed URL shortener. It has a TypeScript server,
a Next.js client, a Jest test-discovery command, and an npm lockfile. Its
real build compiles the server and client. In the initial offline probe,
`npm ci --offline --legacy-peer-deps` installed 2,830 packages. The lockfile
predates current npm, so the same peer-dependency option is needed when
filling and using the cache. Node 22 requires
`NODE_OPTIONS=--openssl-legacy-provider` for this version of webpack.

`workload.json` records the candidate source, lockfile and Node image pins.
These are candidate inputs only: the fixture image, patch, output receipts,
watch plan, runner integration and cross-engine proof do not yet exist. Do
not use this directory to score a workload.

The preliminary fixture image uses the cached lockfile dependencies in
`/fixture/npm-cache` and the verified archive in `/fixture/source.tar.gz`.
The Dockerfile expects `source.tar.gz` and `npm-cache/` in its build context.
The preparation probe populated that cache with `npm ci --legacy-peer-deps`.

The same exported image was loaded into both engines. The ordered DiffIDs
match, but OrbStack and ctrs report different image IDs and cannot inspect
one another's ID. The IDs and DiffIDs are recorded in `workload.json`.
`identity-proof.py` reproduces that failure against the prepared OrbStack tag
`np-w12-kutt:proof` and a fresh owned ctrs engine. This blocks the requested
identical image-ID check; no workspace or watcher trials were run.
