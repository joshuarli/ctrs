# Architecture — the imported Kiri core, as of CTRS-05

Verified against the pinned snapshot (`docs/upstream.md`). This is a reading map, not a design doc; keep it accurate as slices land.

## Workspace

| Crate | Role | Fate |
| --- | --- | --- |
| `kiri` | host daemon + CLI (`crates/kiri/src/`); Docker Engine API 1.47 on a local Unix socket | core (headless after CTRS-07) |
| `kiri-init` | guest agent (PID 1): clone3, cgroups v2, namespaces, mounts, seccomp, netlink, exec/reap | keep |
| `kiri-vmm` | VMM backends: `apple.rs` (macOS, Virtualization.framework, `VZNATNetworkDeviceAttachment`) and `process.rs` (Linux native, agent as root child, vsock↔unix sockets) | keep; rename only after stabilization |
| `kiri-proto` | bounded host↔guest wire protocol + version negotiation | keep |
| `kiri-image` | OCI resolution, registry client (currently `ureq` → pilot CTRS-16), content-addressed blob store | keep |
| `kiri-share-proto` | Kiri Share attestation protocol | delete (CTRS-07) |
| `kiri-win` | Windows service/pipe | delete (CTRS-06) |
| `xtask` | build orchestration (`guest`, `kernel`, `disk`, `host`, `linux`, …) | keep guest/kernel/disk/host/linux; delete windows/msi/dmg tasks |

## Host daemon, `crates/kiri/src/daemon/`

- `api.rs` — Docker Engine API 1.47 surface; request routing, ~30 resource families (containers, images, networks, volumes, system, events…).
- `http.rs` — hand-written HTTP/1.1: keep-alive, Content-Length + chunked, chunked responses, upgrades for `attach`; thread-per-connection; `MAX_BODY` 8 MiB for JSON endpoints, streamed bodies at any size. Interoperability oracle lands in CTRS-14; h12tiny pilot in CTRS-15.
- `engine.rs` — the container lifecycle state machine (create→start→stop→remove), persisted records; `ops.rs` — API-facing operations; `filters.rs`, `names.rs`, `time.rs`, `logfile.rs`, `health.rs` — supporting pieces.
- `network.rs` — user networks + IPAM state; **dead code `parse_ipam` (`network.rs:472`), pre-existing**. `ports.rs` — published TCP/UDP; `dns.rs` — container DNS; `proxy.rs` — host↔guest relays; `hostetc.rs`, `hostopts.rs` — host configuration touchpoints.
- `volumes.rs` — named/anonymous volumes + bind mounts; `binds.rs` — bind-mount path safety; `hostopts.rs`.
- `pulls.rs` — OCI pull flow; `mirror.rs` — registry mirror config; `time.rs`.
- `builder.rs`, `builds.rs` — BuildKit-in-a-container builder provisioning (headless feature; keep).
- `mirror.rs`, `tls.rs`, `domains.rs`, `nfs.rs`, `hostetc.rs` — deletion candidates with domains/TLS/Finder (CTRS-07, verify edges first).
- `access.rs` — socket permissions/credentials boundary; `vmcpu.rs`, `vmlink.rs` — VM CPU/memory and vsock link; `usage.rs` — resource accounting.
- `usb.rs` — USB passthrough; delete (CTRS-07). `health.rs`, `logfile.rs` — keep.

## Engine integration points

- macOS: ad-hoc signed `kiri` binary (`codesign --sign -`) with entitlement `com.apple.security.virtualization`; `cargo xtask host` does both. Boots `guest/out/Image` (from `cargo xtask kernel`, 6.18.58) with `initramfs.cpio` (`cargo xtask guest`); data disk `data.img` (`cargo xtask disk`). One VM, many containers (not one VM per container).
- Linux: no VM; `kiri-init` runs as root on the host kernel; namespaces/cgroups directly; agent sockets under `/run/kiri-agent-<pid>`.
- Transport: host↔guest over vsock; published ports relayed (vsock fast path or IP path — see CTRS-17).
- Delegation: `kiri run`/`ps`/… exec the external `docker` CLI with `DOCKER_HOST=unix://<socket>` and `DOCKER_CONTEXT` stripped (`crates/kiri/src/docker.rs`).

## Verification map

| Surface | Tool |
| --- | --- |
| Unit/integration | `cargo test --workspace` (359 passing at baseline, see `docs/baseline.md`) |
| Engine round-trip | `conformance/smoke.sh` (CTRS-04) |
| API conformance | `conformance/run.sh` + fixtures (D1) |
| Docker-CLI e2e | `tests/e2e.sh` (adapted to scratch env in CTRS-08) |
| Linux host proof | `tests/linux-host.sh` — needs Linux (N-1) |
| Firewall | netns fixtures in `conformance/fixtures/` (CTRS-11/13) — needs the guest VM or Linux root |
| Parity oracle | `docs/parity.md` (register; nothing merges while a row is `open` at close) |

## On-disk state

`vm.json` (CPUs/memory), data root (volumes, images, records), `sockets`. No migration planned in this campaign; `vm.json` and `KIRI_*` env vars stay compatible (D2).
