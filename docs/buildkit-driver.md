# Docker-driver `docker buildx build` — design note

Status: scoped, not implemented. This is the campaign's one remaining
scored loss (W6/W7 default-driver builds). Verified against buildx
v0.22.0 source and live `docker buildx ls`/`build` probes on 2026-11-15.

## What buildx actually requires

The implicit `default` builder resolves its driver per docker endpoint
via `driver.GetDefaultFactory` (lowest `Priority` wins):

- `docker` driver `Priority` = 10 **iff**
  `Client.DialHijack("/grpc", "h2c")` succeeds, else 99
  (`driver/docker/factory.go`). docker-container is the fallback.
- `Builder-Version` on `/_ping` is **not** consulted (falsified: ctrs
  header 1→2 changed nothing).
- The docker driver then speaks BuildKit directly
  (`driver/docker/driver.go`):
  - `Dial` → hijacked `/grpc`, h2c (HTTP/2 prior knowledge) carrying the
    BuildKit control API (Solve, workers, session, history, prune).
  - session dialer → hijacked `/session` with proto + metadata,
    carrying the BuildKit session protocol (build context, secrets,
    ssh, auth, llb bridge).
  - `Version()` → `ServerVersion` + buildkit version resolution.
  - `Features()` → `client.ListWorkers`, checks the
    `org.mobyproject.buildkit.worker.snapshotter` worker label;
    `DefaultLoad` is always true.
- It **never uses `POST /build`** — ctrs's classic-API builder cannot
  serve it at all.

## Why a plain proxy is not enough

Proxying `/grpc`+`/session` bytes to a standalone buildkitd gives
protocol compatibility but **not** the store-direct benefit: with an
oci/containerd worker, `type=docker` export still streams the full
image tar back through Solve to buildx, which then `POST /images/load`s
it — the same crossing as docker-container, plus a relay hop. The
in-store write on real Docker comes from moby's embedded worker
(builder-next), which standalone buildkitd does not have.

## Recommended path: `/grpc` proxy + exporter rewrite to mirror push

ctrs already has every ingest-side piece: the build mirror accepts
OCI pushes from buildkitd (`/v2/<token>/push/…`), content-addressed
blob ingest with dedup, manifest→image-record mapping, and retag on
success (see `crates/ctrs/src/daemon/mirror.rs`,
`builder.rs` push export). The missing piece is only the front door.

1. **Dedicated buildkitd target.** A ctrs-managed buildkitd (the
   managed-builder image/config already exists: privileged container,
   `/var/lib/buildkit` state volume, `buildkitd.toml` naming the mirror
   for every registry) reachable from the daemon over a stable
   guest-internal channel (vsock dial to a fixed agent port, or a
   published loopback port — decide at implementation; must survive
   builder-container restarts).

2. **`/grpc` h2c endpoint on the unix socket.** The daemon's HTTP
   layer is hand-rolled HTTP/1.1; `/grpc` needs HTTP/2 prior-knowledge
   (h2c) framing: HEADERS/DATA/SETTINGS/PING/WINDOW_UPDATE, HPACK.
   Bounded but real work — evaluate `h2`/`hyper` crates vs a minimal
   framer; the API server must not regress HTTP/1.1 paths.

3. **Transparent `/session` proxy.** Session bytes are end-to-end
   gRPC between buildx and buildkitd — a pure byte pipe needs no
   parsing. This carries build context, secrets and auth unchanged.

4. **SolveRequest exporter rewrite.** Parse gRPC frames (5-byte
   prefix + protobuf) far enough to rewrite `SolveRequest` exporter
   attrs: `type=docker`/`type=image` without push →
   `type=image,"name=<mirror-repo>/<requested-tag>",push=true,
   registry=<mirror>`. Untagged builds get the archive-convention
   config-digest name (existing retag logic). Multi-platform /
   attestation exporters need the same treatment or an explicit
   refusal — decide during implementation, do not silently drop
   attestations (orbstack emits a provenance manifest list today).

5. **Result.** Image lands in the ctrs store via mirror ingest +
   retag — compressed blobs, content dedup, no docker-archive tar,
   no `/images/load`. Expected to remove most of the ~0.8–1.5 s
   export+send+import delta measured on W7; residual vs true
   docker-driver is export serialization + push protocol overhead.

## Risks / open questions

- gRPC/protobuf surface: SolveRequest exporter attrs are a
  `map<string,string>`; rewriting needs a small protobuf codec for
  exactly that message (hand-rolled varint is feasible; adding `prost`
  is heavier — check existing deps first).
- buildx version drift: exporter attrs and session features vary by
  buildx release; the rewrite must fail closed (refuse the build with
  a clear error) rather than produce a wrong image.
- `--push`/`--output` builds must not be rewritten — only the
  `--load`/default-load docker-driver path.
- Builder lifecycle: the proxy target must exist before the first
  docker-driver build; lazy-start it like the managed builder does.
- Crash durability: mirror ingest is already atomic per blob; a
  failed push must leave no half-tagged image (retag only on success —
  existing behavior).

## Fallback

If the rewrite proves too fragile, option C (a real moby-worker
writing ctrs's store) is the only path to exact parity, and is
strictly larger. Status quo (documented structural gap, matched
`--driver dc` already shows ctrs ahead) remains the honest floor.
