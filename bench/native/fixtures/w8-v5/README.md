# W8 common portfolio (v5, refreshed 2026-11-18)

`portfolio.json` is the common multilayer pin set used by the W1/W2/W3/W8
fixtures: the real Python API, PostgreSQL, Redis, and the Marked TypeScript
build/test environment. All images come from one read-only OCI layout
(`portfolio.tar`, see `archive_sha256` in the contract).

This fixture version replaces `w8-v2` on the 2026-11-18 macOS host
(M1 Max, 10 cores, 64 GiB, macOS 27.2.1). The v2 artifacts were not
recoverable on the new host (locally built API/Marked images and the moving
`python:3.13-slim` tag are not bit-reproducible). Per the fixture rules,
changed inputs start a new fixture version; never pool v5 results with v2
history.

What changed and what did not:

- `np-v5/postgres` and `np-v5/redis` are **bit-identical to the v2 pins**:
  both images were pulled by the exact manifest digests recorded in the v2
  contract and verified against the pinned ordered DiffIDs and config digests.
- `np-v5/api` was rebuilt from `../w1/api` with the digest-pinned base
  (`python@sha256:e48f59cd…`). The first four layers (base OS) are
  bit-identical to v2; the pip-install and app layers differ (layer tar
  metadata), as do the manifest and config digests. `/app/app.py` and
  `/app/requirements.txt` verify against the unchanged `api_files_sha256` pins.
- `np-v5/marked` was rebuilt from the pinned `marked` v15.0.12 sources and
  `../w5-v2` with the digest-pinned `node@sha256:557e52a0…` base and
  `npm ci` from the pinned lockfile. The Node base layers are bit-identical
  to v2; the npm layers differ. Tool versions verify against the pins
  (node v22.15.0, npm 10.9.2, esbuild 0.25.3).
- Fixture input hashes (`seed.sql`, `load.py`, API files, runtime versions)
  are unchanged from v2. `marked_artifact_sha256` is carried over and must
  be re-verified on the first Marked build, not assumed.
- `layout_reference` tags: `17-alpine`, `7-alpine` (unchanged), `np5-api`,
  `v5`.

Regeneration on another host requires the pinned bases and sources to remain
retrievable, or a further fixture-version bump. Do not silently substitute
images. Do not prune shared OrbStack/ctrs content to manufacture absence.
The derived content-unique variant flow is documented in
`../w8-v3/README.md` and now consumes this fixture.
