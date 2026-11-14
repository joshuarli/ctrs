# Architecture — the headless fork, as of CTRS-07

Verified against git state after CTRS-06/07 deletions (see `docs/upstream.md` for the import record). This is a reading map, not a design doc; keep it accurate as slices land.

## Workspace

| Crate | Role |
| --- | --- |
| `ctrs` | host daemon + CLI (`crates/ctrs/src/`); Docker Engine API 1.47 on a local Unix socket; external `docker` CLI delegation |
| `ctrs-init` | guest agent (PID 1): clone3, cgroups v2, namespaces, mounts, seccomp, netlink, exec/reap |
| `ctrs-vmm` | VMM backends: `apple.rs` (macOS, Virtualization.framework, `VZNATNetworkDeviceAttachment`) and `process.rs` (Linux native, agent as root child, vsock↔unix sockets) |
| `ctrs-proto` | bounded host↔guest wire protocol + version negotiation |
| `ctrs-image` | OCI resolution, registry client (h12tiny-client-sync), content-addressed blob store |
| `xtask` | build orchestration: `guest`, `kernel`, `disk`, `host`, `linux`, `all` |

Deleted in CTRS-06/07: `ctrs-win`, `ctrs-share-proto`, `crates/ctrs/src/ui/`, `wsl.rs`, `ui/` tests and assets, `brand/`, `about.*`, the `window` cargo feature, all desktop dependencies (`objc2-app-kit`, `objc2-web-kit`, `objc2-core-text`, `gtk`, `webkit2gtk`, `javascriptcore-rs`, `rustls`, `webpki-roots`, `rcgen`), the Wi-Fi `ctrs share`/`ctrs Cloud` upload paths, the container-domain (`*.ctrs.localhost`, TLS CA) machinery, the `~/ctrs` NFS Finder mount, USB passthrough, the Kubernetes (`k3s`) surface, the Linux-machines surface, `ctrs setup` (docker-context creation, LaunchAgent, `/etc/resolver` install), the updater, the Builds/history window surface and BuildKit's unused host-side helpers. CTRS-10 additionally removed: the Windows-cfg arms in `main.rs`/`buildwith.rs`, the WSL path translation in `binds.rs` (with its `wslpath`/`/etc/wsl.conf` handling; the `-v` source parser is path-only now), `diag/report.rs`'s Finder reveal (`/usr/bin/open -R`), and `scripts/ctrs-linux.sh`.

## CLI surface (after CTRS-07)

`ctrs daemon`, `ctrs build-with [docker|ctrs]`, `ctrs diag …`, plus Docker's commands delegated to the external `docker` CLI against the daemon socket (`DOCKER_HOST=unix://…`, `DOCKER_CONTEXT` stripped). Nothing elsewhere creates a docker context.

## Host daemon, `crates/ctrs/src/daemon/`

- `api.rs` — Docker Engine API 1.47 surface; request routing, ~30 resource families. ctrs-specific routes: guest IP, resources, proxy setting, system df.
- `http.rs` — hand-written HTTP/1.1: keep-alive, Content-Length + chunked, chunked responses, upgrades for `attach`; thread-per-connection; `MAX_BODY` 8 MiB for JSON endpoints, streamed bodies at any size.
- `engine.rs` — the container lifecycle state machine (create→start→stop→remove), persisted records; `ops.rs` — API-facing operations; `filters.rs`, `names.rs`, `time.rs`, `logfile.rs`, `health.rs` — supporting pieces.
- `network.rs` — user networks + IPAM state. `ports.rs` — published TCP/UDP; `dns.rs` — the guest-relay resolver path (`serve_relay` over vsock; the `*.ctrs.local` loopback server is gone); `proxy.rs` — proxy config for registry pulls; `mirror.rs` — registry mirror config; `hostetc.rs`, `hostopts.rs` — host configuration touchpoints.
- `volumes.rs` — named/anonymous volumes + bind mounts; `binds.rs` — bind-mount path safety.
- `pulls.rs` — OCI pull flow; `builder.rs`, `builds.rs`, `buildwith.rs` — BuildKit builder provisioning (`ctrs-build`, docker-container) and the plain-`docker build` builder choice (headless; kept).
- `access.rs` — socket permissions/credentials boundary (Linux root + group mode); `vmcpu.rs`, `vmlink.rs` — VM CPU/memory and vsock link; `usage.rs` — resource accounting.
- `ssh-agent` forwarding to the guest/vm stays (`ports::serve_ssh_agent`, `SSH_AGENT_PORT`): headless-relevant, not Finder/UI.

## Engine integration points

- macOS: ad-hoc signed `ctrs` binary with entitlement `com.apple.security.virtualization`; `cargo xtask host` does both. Boots `guest/out/Image` (`cargo xtask kernel`, 6.18.58) with `initramfs.cpio` (`cargo xtask guest`); data disk `data.img` (`cargo xtask disk`). One VM, many containers.
- Linux: no VM; `ctrs-init` runs as root on the host kernel; namespaces/cgroups directly.
- Transport: host↔guest over vsock; published ports relayed (vsock fast path or IP path).
- Delegation: `ctrs run`/`ps`/… exec the external `docker` CLI with `DOCKER_HOST=unix://<socket>`, `DOCKER_CONTEXT` stripped (`crates/ctrs/src/docker.rs`, `crates/ctrs/src/client.rs`).

## Wire protocol (after CTRS-07)

`ctrs-proto` carries: daemon↔agent lifecycle (create/start/exec/stop/remove/update/pause/stats/top/listening/logs), image storage, networks/routes/detach, copy (`docker cp`), DNS relay, memory pressure, volume/bridge removal, usage. The FS-view messages (`FsStat`/`FsList`/`FsRead`) and `UsbNodes` are deleted; `FsEntry` remains only for `docker cp`.

## On-disk state

`vm.json` (CPUs/memory) lives in the diag state dir; the image/VM data root is `CTRS_DATA_DIR` or `~/.local/share/ctrs/data` (0700, enforced on open). No migration planned; `CTRS_*` env vars stay compatible (D2). `CTRS_STATE_DIR` redirects the diag state dir for tests and `CTRS_DATA_DIR` for all image/VM state (`docs/decisions.md`).

## External delegations (audit, CTRS-10)

Every process the engine or its CLI spawns, and what to make of it. Test-only spawns (Linux ACL tests use `useradd`/`userdel`/`groupadd`/`groupdel`) and build tooling (`xtask` spawns cargo/docker/codesign for the build) are excluded.

| Spawner | Binary | Why | Verdict |
| --- | --- | --- | --- |
| `docker.rs` (`ctrs ps`/`run`/…) | external `docker` CLI on PATH | Docker's own commands, delegated: `DOCKER_HOST=unix://<socket>`, `DOCKER_CONTEXT` removed, argv untouched | intended delegation; tested with a stub CLI (argv + env) |
| `builds.rs` (`ctrs build-with ctrs` / first `docker build`) | `docker buildx` | BuildKit builder provisioning for `docker build`: `buildx version → inspect → rm --keep-state → create`. The builder is addressed by **endpoint** (`unix://<socket>`), never a docker context; ctrs never creates one | intended delegation, user- or first-build-triggered; no context created (CTRS-10) |
| `service.rs` | `ps` | `ctrs engine status` RSS/uptime readout | OS helper |
| `service.rs` | the `ctrs` binary itself | `ctrs engine start` spawns `ctrs daemon` in its own process group | self; not a delegation |
| `guest.rs` | `/usr/bin/tar` | unpacks the packed 64 GiB `data.img.tgz` template (holes preserved as sparse) | OS helper; fails loudly if missing |
| `ports.rs` | `/usr/sbin/lsof` | names the non-ctrs process holding a published port, in the "already allocated" error message | macOS integration; absence just drops the detail |
| `ports.rs` | `/bin/launchctl` | `getenv SSH_AUTH_SOCK` when the daemon wasn't started from a shell that has it | macOS integration; `SSH_AUTH_SOCK` env takes precedence |
| `proxy.rs` | `/usr/sbin/scutil --proxy` | macOS proxy settings for registry pulls | macOS integration; absence = no proxy |
| `ctrs-vmm` (`process.rs`) | `ctrs-init` (the initrd) | Linux host: the guest agent as a root child process | own runtime, not a delegation |

Nothing spawns `git`, `curl`, `ruby`, `python3`, `open`, `find`, or a shell to *do the engine's work*; shelling out is not a control path. The remaining delegations are: (1) Docker's CLI for Docker's commands, (2) optional macOS system-info probes that degrade gracefully, (3) `ps` for process state. There is exactly one privileged external command surface (`ctrs-init` on Linux, by design).

## Verification map

| Surface | Tool |
| --- | --- |
| Unit/integration | `cargo test --workspace` (193 passing after CTRS-07, see `docs/baseline.md`) |
| Engine round-trip | `conformance/smoke.sh` |
| API conformance | `conformance/run.sh` + fixtures (D1) |
| Docker-CLI e2e | `tests/e2e.sh` (adapted to scratch env in CTRS-08) |
| Linux host proof | `tests/linux-host.sh` — needs Linux (N-1) |
| Firewall | netns fixtures in `conformance/fixtures/` (CTRS-11/13) — needs the guest VM or Linux root |
| Parity oracle | `docs/parity.md` |
