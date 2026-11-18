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
