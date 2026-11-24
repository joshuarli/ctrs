# Docker-driver `docker buildx build` — design note

Status: historical design note. Current performance work is in
`docs/roadmap.md`. Historical pilots identified a
W6/W7 default-driver gap, but the 2026-11-15 scoring/input audit withdrew
their qualification and precise magnitudes. Rebaseline real application
builds before choosing/promoting a change; this design note does not
close the gap or establish that it is the only remaining loss.
Protocol observations below were verified against buildx
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
  is heavier). Existing deps checked 2026-11-15: no `h2`, `prost`, or
  `tonic` anywhere; `h12tiny` is the repo's HTTP/1.1 server
  (feature-gated pilot) and `hyper` is an optional fork
  (`laputa-hyper-futures-lite`) — the h2c framer is new code either
  way, which keeps the change additive behind the unix socket.
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

## Implementation protocol notes (verified 2026-11-15, buildx v0.22.0 / buildkit v0.35.0)

- `DialHijack("/grpc","h2c")` is an ordinary HTTP/1.1 `POST` with
  `Connection: Upgrade` + `Upgrade: h2c`, expecting `101`. The path is
  visible at HTTP/1.1 level — route on it; after 101 the conn is
  prior-knowledge h2c. Same for `/session`.
- `/grpc` conn: buildx is the gRPC **client**, buildkitd the server
  (Control service). Byte-pipe host↔buildkitd works; only the first
  SolveRequest needs MITM rewrite. h2 frame headers are 9 bytes;
  HEADERS payloads (HPACK) pass through untouched — never decode.
- SolveRequest (control.proto): `ExporterDeprecated`=3 (string),
  `ExporterAttrsDeprecated`=4 (map), `Exporters`=13 (repeated
  `Exporter{Type=1, Attrs=2 map<string,string>}`). gRPC frame =
  1B flag + 4B BE len + protobuf. Rewrite type `docker`/`image`
  without `push=true` → `type=image`, `name=<mirror push ref>`,
  `push=true`, `registry=<mirror>`. Multi-platform/attestation/
  `--push`/`--output` → fail closed.
- `/session` conn: buildx is the h2 **server** (session attachables);
  buildkitd reaches it via `session.Manager.HandleConn` →
  `grpcClientConn` (h2 **client**). HandleConn is in-process only —
  NOT exposed on buildkitd's TCP port. The bridge: byte-splice the
  `/session` conn to a `Control.Session` bidi stream
  (`rpc Session(stream BytesMessage)` on the same Control service)
  opened by our own minimal gRPC **client** to buildkitd TCP.
  `BytesMessage{data=1}` (tag 0x0A + varint). Roles align: buildkitd
  is h2 client on both legs, buildx h2 server — pure byte shuttle,
  no HPACK decode needed; only literal HPACK *encoding* for our
  request headers. Must implement h2 client flow control
  (SETTINGS/WINDOW_UPDATE/PING/GOAWAY/RST_STREAM) and grpc 5-byte
  prefixes.
- Transport: managed builder container (`buildx_buildkit_ctrs-build0`)
  gets `--addr tcp://0.0.0.0:1234` added to `create_body` Cmd (additive;
  unix sock remains for buildctl/dial-stdio). Daemon reaches it via
  `ports::open_relay(vm, container_ip, 1234)`; container IP from engine
  inspect. Extend `BuilderSnapshot`/`classify` to compare `spec.cmd`
  so pre-change builders go stale and are replaced.
- Ensure path: `builder::ensure_running(engine, say)` (make
  `pub(crate)`); call it lazily on first /grpc or /session conn.
- `/grpc` and `/session` conns must never be served by accident:
  unknown Upgrade values and non-builder engines keep current 404/426
  behavior; builder-not-running/foreign → actionable error, not hang.
