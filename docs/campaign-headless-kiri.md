# Campaign: extract and harden a headless Kiri core into ctrs

**Status:** planned; execution may start immediately after the baseline is imported and proved.
**Repository:** https://github.com/joshuarli/ctrs
**Initial executable / temporary internal identifiers:** `kiri`
**Eventually:** `ctrs`
**Platforms:** macOS + Linux only; prioritize Apple Silicon, Linux aarch64 and x86_64. Mac Intel must compile if claimed as supported; runtime support requires a real runner.
**Objective:** the smallest credible, fast, headless, pure-Rust-oriented Docker-compatible container engine that directly exercises the Laputa stack. Not a general-purpose VM manager or another desktop app.

## 0. Ground truth, sources, and design constraints

Research snapshot (November 13, 2026, Pacific time):

| Codebase | Snapshot to evaluate | Role |
| --- | --- | --- |
| [Kiri](https://github.com/libracoder/kiri) | `99b63c07fc003d3dcd8e03c76891ba747b5c984f` | Source engine and correctness/performance baseline |
| [crabtables](https://github.com/laputa-systems/crabtables) | `38646b8f2f6ee7256c448849edda4459842a2e10` | Typed nf_tables/NAT/ruleset programming |
| [smolith](https://github.com/laputa-systems/smolith) | `066bb8c9c609c66c271fc32f170181375e421551` | Smol runtime, h12tiny HTTP, futures-based I/O and Graviola TLS |
| [smolvm](https://github.com/smol-machines/smolvm) | `146f3a5121c01a98bb894dc954e3c143a17c0084` | Optional microVM / userspace networking comparison |
| [Lima](https://github.com/lima-vm/lima) | `55fb02294a4199dcc49db4946f6b126f94d4f3a9` | VM networking, mounts and port forwarding oracle |

Record the actual Kiri source commit imported, its files, and its dependency lockfile in `docs/upstream.md`. Recheck snapshots before implementing a replacement; source can move after this document. Do not assert a benchmark, feature, fix, or qualification based on a README alone.

**Important Kiri provenance and licensing:** retain upstream Apache-2.0 `LICENSE`, relevant `NOTICE` entries, source attribution, and third-party licenses. The Linux kernel is GPL-2.0; retain patches, build configuration, reproducible sources, corresponding-source offer and distribution compliance. Kiri explicitly excludes its *name and logo* from the software license. Temporarily keep historical `kiri` command names, crate/module names, socket identifiers and Docker context for development and migration; do not ship its logos or represent this public fork as an official Kiri build. Switch public branding to `ctrs` before a general release. Do not rush renaming wire protocols or data formats while extraction is in progress.

**Non-negotiable invariants:**

1. No Windows, WSL2, GTK, WebKitGTK, AppKit desktop window, embedded web UI, Electron, updater, menu-bar app, Finder UI, or mandatory Docker installation at runtime.
2. Linux executes containers directly using namespaces/cgroups/overlayfs. macOS uses one small Linux guest through Apple's **Virtualization.framework**. No mandatory QEMU, libkrun, systemd, dbus, containerd, dockerd, runc or shim.
3. Keep a Docker Engine API-compatible Unix socket as a stable integration boundary; continue allowing an external Docker CLI/Compose/buildx during transition. No false claim that `kiri run` is independent: upstream `crates/kiri/src/docker.rs` presently executes an external `docker` CLI.
4. Keep OCI image pull/store, image verification, volumes, bind mounts, container lifecycle, native TCP/UDP publish, DNS and restart behavior. Do not claim full Docker parity; track each supported API operation in an explicit conformance matrix.
5. Prefer Rust, minimal transitive dependencies, static musl builds on Linux, Graviola/rustls rather than OpenSSL, smol/futures rather than introducing Tokio. Do not introduce async gratuitously into fast synchronous paths.
6. Local Unix socket only by default; no remote TCP/MCP/control plane or public sharing. A Linux daemon grants root-equivalent authority to socket holders: permissions, credentials and tests are security boundaries.
7. Every optimization or subsystem swap requires a passing behavioral oracle and comparable before/after measurements; document failed experiments as well as wins.
8. One canonical engine/state machine. Avoid duplicate "raw"/daemon runtimes, shadow stores, two network controllers or a heavyweight general VM abstraction unless experiments demonstrate a real need.

## 1. Target architecture

```text
  docker CLI / compose / buildx (optional)     eventual native ctrs CLI
                       \                      /
                        Unix Docker Engine API
                                 |
                 Kiri-derived core daemon/state machine
                 |             |             |
            OCI registry     volumes     network policy
            + blob store       |        crabtables (nf_tables)
                 |             |             |
            host/guest transport + versioned protocol
                                 |
                  macOS                     Linux
       Virtualization.framework       native root agent
           minimal Linux VM                  |
                  \                         /
                   kiri-init: clone3, cgroups v2,
                   namespaces, mounts, seccomp,
                   rtnetlink, firewall/nat, exec/reap
```

Keep, subject to measured simplification:

| Upstream location | Disposition |
| --- | --- |
| `crates/kiri-init` | Keep: agent, syscall/container lifecycle, security boundary |
| `crates/kiri-vmm` | Keep: `apple.rs` VZ and `process.rs` Linux; consider renaming only after stabilization |
| `crates/kiri-proto` | Keep: bounded host/guest wire protocol, explicit version negotiation |
| `crates/kiri-image` | Keep initially: OCI image resolution, registry and content-addressed blobs |
| `crates/kiri/src/daemon` | Keep core API/engine/volume/network modules, excise ancillary services |
| `guest/kernel` | Keep minimal bootable kernel, config, patches and source compliance |
| `crates/kiri/src/ui`, `crates/kiri-win` | Delete |
| `installer/windows`, Windows build scripts, desktop packaging, UI tests/translations/assets | Delete |
| `k8s`, `machine`, `share`, `usb`, `import`, app updater, Finder/NFS browsing, browser logins, proprietary domains/TLS CA | Delete by default; document any truly core dependency before deciding otherwise |
| `crates/kiri/src/docker.rs` | Transitional adapter only; native Rust subcommands are later milestones |

Do not confuse the **two networking planes**:
- **Inside the guest / native Linux:** each container's netns, bridge, veth, conntrack, nftables, IPAM. crabtables applies here and potentially to Linux host-owned container networking.
- **macOS host ↔ Linux guest:** Apple's VZ virtio-net + NAT, versus vsock-based fallback/port relay. crabtables *cannot* replace this layer. Lima and smolvm offer different techniques for it.

## 2. Workstream and execution order

Carry out the phases in order. Small parallel investigations are allowed, but only merge one independently testable change at a time. Track each task by its stable ID (`CTRS-01` etc.) and commit evidence under `.work/` or CI artifacts (do not commit large benchmark logs).

### Phase A — Establish provenance and a living reference

**CTRS-01: Import the actual runtime, not a marketing skeleton.**

- Import a pinned upstream Kiri snapshot (prefer preserving relevant history where economical, otherwise a clearly attributed reproducible source snapshot); no submodule that silently follows upstream HEAD. Preserve all necessary kernel/build/test files, original licenses/notice, and upstream SHA.
- First build and test *unmodified* Kiri at that SHA on the selected macOS and Linux targets. Baseline `cargo test`, smoke with a real Docker CLI and the upstream `tests/e2e.sh` and `tests/linux-host.sh`, and record failures and known flakes. Mac build must be signed with `com.apple.security.virtualization` entitlement.
- Record build graph, binary/RSS sizes, kernel size, idle memory, VM cold/warm boot, container create/start/remove times, cold/hot image pulls, HTTP API latency, first workload run, volume bind metadata throughput, and port latency/throughput. Record machine/OS/kernel, warm/cold definitions, sample counts and exact commands.
- Put reference Docker Engine conformance fixtures in a *separate* harness; running the upstream tests against the implementation is not sufficient evidence of parity.
- Add `docs/upstream.md` with a source pin, carried patches, third-party inventory and procedure for evaluating upstream security fixes.

**Gate A:** a repeatable, checked-in baseline harness runs a container and returns its exit status, with output captured for both Docker and Kiri, and proves that data paths are isolated. If no macOS test machine is available, mark macOS runtime **unverified**, not passed.

### Phase B — Headless-only, no broken runtime paths

**CTRS-02: Delete all UI and Windows build/runtime code.**

- Remove `ui` source, translations, WebKit/AppKit/GTK dependencies, Windows/WSL sources and installers. Keep only the ObjC bindings **required by Virtualization.framework**, not AppKit/WebKit.
- Remove updater, app-bundle startup and launch assumptions; the foreground `kiri daemon` must work from a terminal without any GUI or login session. Make service installation explicit and optional (launchd example for macOS; supervisor-agnostic foreground invocation or optional OpenRC service on Linux; no mandatory systemd).
- Onboarding should be shell-native: create a private data root and socket, create the Docker context only on explicit request, never hijack `/var/run/docker.sock` or another Docker context automatically.
- Strip appwatch/Finder/NFS, Kubernetes, machine provisioning, Kiri Share, CA/local-domains, telemetry/uploaders, USB and other side facilities, checking reference edges rather than deleting at random.
- Build an auditable dependency diff (Cargo tree/features). Ensure no `objc2-app-kit`, `objc2-web-kit`, GTK, WebKitGTK or Windows crates are linked into the headless artifacts.

**Gate B:** Apple Silicon and native Linux run `docker --context kiri run --rm alpine true`, `exec`, `logs`, published ports, named volume, and a controlled daemon restart with no desktop components installed. The process actually exits cleanly on SIGTERM and leaves no stale resources.

**CTRS-03: Consolidate executable and API boundaries.**

- Retain one host executable plus version-pinned guest agent/kernel/disk resources; avoid duplicating a guest kernel inside every process or insisting on a single-file artifact before size measurements.
- Make engine start/stop/status/restart possible with CLI commands, independent of a UI button. Remove or fix messages such as "press Start in the Kiri window."
- Define typed config for data root, socket, CPU/memory, network mode, guest assets, policy, and logging. Preserve upstream env-var compatibility for now; avoid repeated stringly-typed CLI/config fields. State migration must be explicit and reversible.
- Keep `kiri run`/`ps` delegated to optional external Docker CLI initially. Later native implementations should use the same Docker API client or typed domain operations, not an independent second engine.
- Evaluate `kiri raw`: delete it if it duplicates daemon logic, or reduce it to a thin one-shot client using the canonical engine. Never have two authoritative image stores/container lifecycle implementations.
- Replace platform-specific ad hoc command branching with tiny, explicit host/guest interfaces only where needed; do not overabstract for unsupported OSes.

**Gate C:** run from a clean user environment with no bundled Docker binary, and still serve any installed Docker CLI via the Unix API socket; CLI diagnostics and lifecycle commands work when the daemon is stopped.

### Phase C — Dogfood crabtables with kernel-level proofs

**CTRS-04: Introduce crabtables at the nftables boundary.**

Facts: Kiri's guest uses handwritten rtnetlink and nf_tables messages in `crates/kiri-init/src/linux/netlink.rs`. crabtables is a pure-Rust nftables/netfilter interface; it does **not** replace rtnetlink interface/route programming. Keep the working Kiri rtnetlink path initially. Target only the nftables ruleset owner and firewall/NAT operations.

- Inventory every existing firewall operation and ruleset shape: IPv4/IPv6 masquerade, SNAT/DNAT/redirect, bridges, inbound published ports, forwarding, chain priorities, ct state, cleanup and concurrency. Establish packet-level reference fixtures before a swap.
- Add an internal typed `FirewallPolicy` → `FirewallTransaction` interface with explicit network namespace, table/chain/rule ownership, version and rollback/`OutcomeUnknown` handling. Default to crabtables' **typed API** with no `lang`, `json` or `tokio` features unless necessary.
- Implement a feature-switched comparison adapter: existing handwritten nft path versus crabtables. In each isolated topology, install semantically identical rules and compare both to `nft`: kernel rulesets, packet decisions, conntrack tuples, NAT mapping/replies, IPv6, policy updates while traffic is flowing and rejected-batch behavior.
- **Atomicity requirement:** batch each dependent nftables change, but never pretend that combining nft operations atomically makes route/bridge/veth mutations atomic. Specify a compensating teardown protocol, ownership tags, failure recovery and reconciliation for cross-subsystem changes. If a kernel reply is lost after submission, surface "outcome unknown"; inspect state before retrying.
- Exercise old/foreign chain preservation and idempotent cleanup; do not flush all host firewall state. A daemon crash must not leave a permissive or stranded bridge/NAT policy.
- Respect `crabtables/TODO.md` and the CRAB-7 qualification process. Current documentation is inconsistent: README says no deployment profile qualified, while TODO records a **102-case qualified pinned-image profile** (100 pass, 2 intentional). Reproduce the suite, reconcile those claims, and qualify the *actual* ctrs kernel(s), architecture, nft version and rules required for this engine. An isolated image result is not production qualification.
- Once equal or better, delete only the superseded **nf_tables** encoder code. Keep rtnetlink until a separately proven replacement exists.

**Gate D:** strict, fresh, machine-readable NAT/conntrack/rollback evidence for both a native Linux host and Kiri's exact macOS guest kernel; no unknown-outcome silently treated as a rollback, no host-wide firewall mutation, no unexplained mismatches. Reject the crabtables cutover if the selected deployment profile is unqualified.

### Phase D — Dogfood smolith and h12tiny without paying for abstraction

**CTRS-05: Replace custom HTTP parser and registry HTTP selectively.**

Upstream Kiri's host daemon has a custom Docker Engine HTTP implementation, and `kiri-image` uses `ureq`/rustls. Upstream issue [#134](https://github.com/libracoder/kiri/issues/134) documents `Expect: 100-continue` and chunked upload/trailer gaps. The objective is **correctness first, then lower overhead**, not reflexive async conversion.

- Before changing transport, add a byte-exact HTTP/1.1 interoperability suite against Docker (request limits, method handling, keepalive/pipelining, slow headers, chunked framing, trailers, conflicting lengths, 100-continue, cancellation, streaming uploads and bounded memory).
- Pilot `h12tiny-server`/`h12tiny-core` for Docker API handling; qualify HTTP upgrade/hijack semantics for `attach`, `exec`, logs and large streaming tar uploads. h12tiny-server has an `upgrade` feature; verify it meets Docker's duplex/connection lifetime behavior before enabling it.
- Do not force every request through a global async executor. Compare per-connection blocking threads, smol's reactor and small bounded worker pools on real API workloads. Preserve the faster simpler design if there is no measurable win. Avoid Tokio dependencies and an unnecessary Hyper compatibility layer where the smallest h12tiny components suffice.
- Pilot `h12tiny-client-sync` or `h12tiny-client` for the OCI registry client, with explicit Graviola/rustls provider and platform trust roots. Keep digest validation and proxy/auth/redirect semantics. Test Docker Hub and OCI registries, bearer auth, layers, manifests, multiarch resolution, partial downloads, retries, chunking, TLS errors and content-addressed store integrity.
- Use the user's smolith workspace packages at pinned revisions via exact dependency names (`laputa-smol` as package, `smol` library; h12tiny modules). Do not copy the entire smolith monorepo into ctrs or silently float Git HEAD.
- After passing the oracle, remove `ureq` and unused HTTP/TLS dependencies and record compile time, binary size, API p50/p99, throughput, allocation and CPU changes. No loss of TLS verification or trust-root handling.

**Gate E:** identical observable Docker API results (including streaming, exit status and binary payloads) on the declared matrix, no request smuggling/DoS regression, registry digests verified, and perf evidence. Do not ship a transport swap that only makes Cargo tree prettier.

### Phase E — Explore Lima, smolvm and the real VM networking bottleneck

**CTRS-06: Benchmark the macOS VZ network that Kiri already has.**

- Kiri already constructs a `VZNATNetworkDeviceAttachment` in `kiri-vmm/src/apple.rs`. Lima's `vzNAT` is **the same Apple framework facility**, not a new fast network driver to install. Lima's measured IP-address results (59.2 Gb/s forward, 130 Gb/s reverse on an M4 Max) are useful **external reference measurements**, not promises for ctrs on another machine or for published container ports.
- Measure separately: host ↔ guest IP, host ↔ container published port, container ↔ Internet, container ↔ container, TCP small-request latency, UDP, DNS, IPv6, concurrent flows, NAT state, idle CPU and reconnection. Distinguish VM NIC from per-container netns/NAT and from Kiri's vsock port relay. Compare bridged and `--network none` cases.
- Diagnose Kiri's reported "VM NAT network unreachable; relay published ports over vsock" behavior, stale DHCP/IP discovery, reconnect after Mac sleep and different port bind addresses. Avoid layering more proxies to mask a failing fast path.
- Explore Lima's direct-IP/vzNAT path, guest-agent port discoverability, forwarding lifecycle and socket_vmnet. **Default candidate: native vzNAT**. `socket_vmnet` requires extra privileged helper/setup and is only justified for bridged/guest-reachable use cases not served by VZ NAT.
- On native Linux, there is **no VM** and therefore no relevant host↔guest VZ performance optimization. Use rtnetlink/nftables and test host kernel forwarding instead.
- Account for Tailscale: never hardcode a guest/bridge subnet overlapping tailnet routes, especially `100.64.0.0/10` (smolvm's default `100.96.0.0/30` sits there). Detect host route conflicts or offer a deterministic configurable private CIDR; measure nonconflicting IPv4/IPv6.
- Validate bind mounts/virtiofs and host file-change propagation separately; network throughput alone is not a useful developer-workflow win.

**Gate F:** a reproducible breakdown identifies the current bottleneck and justifies any code change with improved end-to-end container traffic, no regression in sleep/wake, recovery, DNS or published-port semantics.

**CTRS-07: Evaluate smolvm as an optional *networking technique*, not the default VMM.**

- smolvm is built on **libkrun** (Hypervisor.framework/KVM), unlike Kiri's native Apple Virtualization.framework approach. Its `smolvm-network` Rust crate implements a host-side **smoltcp** gateway over a **libkrun-specific frame bridge**, with TCP/UDP relays, DNS and egress policy. It is not a drop-in replacement for VZ's NAT device. It may add host sockets and packet copies, so do not assume it is faster.
- Inspect both smolvm's userspace `virtio-net` backend and its default **TSI** socket path. TSI requires kernel-specific patches; importing it into Kiri's custom kernel would enlarge the maintenance burden and change networking semantics. No default TSI adoption.
- Run an isolated proof-of-concept with the smolvm/libkrun backend *outside* the primary engine, or prototype a minimal compatible VZ frame interface only if available without a substantial new VMM. Do not require C/libkrun or whole `smolvm` in the shipping binary without a decisive result.
- Potential value to investigate: protocol-aware DNS caching, explicit egress ACLs, traffic capture/replay, predictable sandbox networking, fast UNIX socket relay, file-change notification and branchable per-task VM state. Separate those capabilities from raw throughput.
- Compare latency/throughput, per-flow FD usage, CPU, memory, guest kernel patches, security boundary, crashes and maintenance burden against VZ NAT and guest kernel networking. Test with long-lived, many-connection and short-lived traffic; smolvm's docs warn that each relay flow consumes host FDs and may hit macOS port/FD constraints.

**Gate G:** adopt individual ideas only behind a measured, narrow interface. A whole libkrun/smolvm backend belongs in a separate optional experiment, not the standard Linux-container execution path.

**CTRS-08: Evaluate optional per-workload microVM isolation only after the container engine is stable.**

- smolvm's per-workload VM/branch/checkpoint model is materially different from Kiri's one-VM-many-containers approach. That could eventually be useful for running **untrusted coding agents**, but this is not a required Docker API capability.
- Compare a minimal per-task VZ VM, smolvm/libkrun, and native Kiri containers for isolation, boot cost, RAM under N parallel sandboxes, snapshots/restore, host mounts, secret forwarding and networking. Keep this research as `docs/experiments/microvm-isolation.md` until it earns a feature.
- Never silently switch a container request into a per-container VM; maintain an explicit security/runtime mode and do not weaken default container security to increase throughput.

**Gate H:** no default microVM mode or new dependency without written threat model, perf/complexity evidence and a concrete use case.

### Phase F — Make the fork better than upstream at the core things

**CTRS-09: Harden and qualify the engine.**

- Review Kiri open issues before each upstream pin, especially [#199](https://github.com/libracoder/kiri/issues/199) (Rosetta/macOS 15), [#50](https://github.com/libracoder/kiri/issues/50) (VM kernel crash/restart), [#121](https://github.com/libracoder/kiri/issues/121) (Testcontainers command handling), [#134](https://github.com/libracoder/kiri/issues/134) (HTTP framing). Verify reproducibly rather than copying a PR and assuming the fix is complete.
- Threat-model Linux root daemon, admin-equivalent socket, host access, capability sets, `--privileged`, seccomp denylist versus allowlist, namespace setup failures, shared kernel attack surface, vsock access from guest, path traversal in tar/unpack, symlink races, mount propagation, image authenticity, corrupted local state, and network policy bypass.
- Minimize privileges and broaden seccomp coverage only with syscall-level differential fixtures; custom filters need architecture/x32/compat, `clone3`, `io_uring` and capability matrix testing. Fail closed on unknown policy semantics rather than silently treating them as Docker-compatible.
- Test kill/crash at every lifecycle step, daemon restart, host sleep/wake, VM kernel panic, orphan processes, incomplete volume/image writes, concurrent pulls, disk full, OOM, stale socket recovery, version mismatches, and network rollback.
- Build untrusted-image / hostile-guest adversarial tests under isolated VMs. Protect test hosts: never grant the harness unrestricted privileges on a real workstation to "prove" isolation.
- Maintain `cargo audit` / `cargo deny` (advisories, license policy, yanked crates), fuzz protocol/frame/HTTP/image parsing, deterministic rustfmt/clippy/lints and smoke with sanitizers where available.

**Gate I:** independently reproducible security/compatibility evidence, no known critical escape or host-policy rollback failure, cleanup after all injected failures. Do not advertise safe untrusted multi-tenant isolation merely because tests pass.

**CTRS-10: Shipping, sizes and final rename.**

- Package a signed/notarized macOS command-line executable plus pinned guest kernel/initrd/data template, without a desktop bundle; retain `com.apple.security.virtualization` entitlement. For Linux: release reproducible static musl x86_64 and aarch64 `kiri`/`kiri-init` artifacts with clear kernel/cgroup/privilege prerequisites.
- No Docker dependency to *build the Rust runtime*; the kernel-build/bootstrap tool may use a container during transition, but provide a verified direct source/toolchain path to eliminate a circular dependency. Never download unpinned rootfs/kernel code during a reproducible release.
- Ship hashes, manifest, SBOM, provenance, third-party notices, guest GPL kernel source offer, reproducible build instructions and safe uninstaller. No automatic daemon installation, sudoers changes, insecure socket link or DNS injection.
- Compare against initial source pin and latest upstream: binary sizes, resident/idle/peak memory (including VM helper), cold/warm startup, lifecycle p50/p95/p99, CPU, TCP/UDP/DNS, OCI image pull, storage operations, compatibility pass rates, dependency/LOC reduction, and boot asset size. Keep raw benchmark scripts/results.
- Only after gates A–I: rename public application/CLI/context/env/data paths to `ctrs` with an explicit migration alias and rollback. Remove Kiri branded assets early; do not postpone trademark compliance to the first public binary release.

**Gate J:** documented cross-platform install, reliable smoke, no GUI dependencies, legally compliant provenance, conformance and perf reports, and a migration-safe `ctrs` identity.

## 3. Minimum conformance and benchmark matrix

| Axis | Required examples and observations |
| --- | --- |
| Container lifecycle | Alpine true/false and exit codes, exec/attach/stdin/TTY, high-volume logs, stop/kill/restart/wait, pause/unpause, high churn and leak soak |
| OCI | Manifest indexes, amd64/arm64 selection, image config labels/Cmd, digest verification, auth, partial/corrupt blobs, save/load, registry retries |
| Docker API | HTTP/1.1 framing, SDK/Testcontainers, Unix socket permissions, streaming/hijack, CLI/Compose, BuildKit container driver |
| Storage | ext4/overlayfs, layer whiteouts, mount path safety, named volumes, host bind directories, write durability, host↔guest inotify propagation |
| Network | Default/user networks, bridge/none, veth/DNS, IPv4/IPv6, NAT/conntrack/rollback, TCP and UDP published ports, tailnet CIDR collision |
| Host guest | VZ boot/poweroff, 1+ N containers, memory balloon, guest crash, Mac sleep/wake, DHCP/IP changes, vsock recovery |
| Threat model | `--privileged`, seccomp, socket access, namespace ownership, symlink/race attacks, image traversal, network egress policy |
| Performance | Real API `run --rm`, precreated start, Redis/Postgres cold/steady startup, HTTP small requests, DNS, iperf3, file metadata and transfers, RSS/CPU |

**Experiment protocol:** same hardware/OS/build profile, pinned OCI digest, warmed and cold cases separately, repeat enough samples to report confidence/variance (not just one median), randomize/alternate experiment order, capture p50/p95/p99, include kernel and virtualization helper memory, collect syscall counters/profiles, and preserve a no-change control. Treat a negative result as useful. An optimization may trade a small regression for a major quality/security gain, but it must be explicitly justified with evidence.

**No new feature passes with only unit tests:** at least one cross-implementation differential check, one failure-mode test, and one regression/perf benchmark are required. Changes to kernel config or custom patches require boot and compatibility validation for each advertised guest architecture.

## 4. Operating rules for the coding campaign

- Follow task IDs in order; every completed ID needs: changed paths, deleted dependencies/source, new tests, exact commands and environment, benchmark evidence, known residual risks and an honest pass/fail statement.
- Use small commits directly on this repo's default branch if green and self-contained. If a change temporarily breaks the baseline, keep it on a short-lived working branch; do not leave `main` red. No speculative large rewrites before baseline evidence.
- Parallelize independent research/benchmarks (crabtables behavior, h12tiny protocol, Lima/smolvm network), but do not swap both protocol and firewall in one commit. Bisectability is a feature.
- Keep `docs/decisions.md`: accepted/rejected experiments and why. Prefer one canonical implementation over feature-flag proliferation once comparisons finish.
- Maintain a compatibility ledger instead of saying "Docker-compatible" without a tested scope. Preserve the passing upstream E2E suite and extend it where it misses real SDK behavior.
- Deletion is a goal, but measured reliability, security and end-to-end latency are the optimization objective. No unbounded caching, premature generic frameworks or new background daemons just to make components appear elegant.
- When blocked by hardware or privilege, complete the independent source/refactor/tests work, record exactly which gate remains unverified, and do **not** waive the gate.

## 5. Immediate first execution slice

1. Import the pinned Kiri core and its legal/build/test assets; record source commit and dependency graph (CTRS-01).
2. Get native Linux musl and Apple Silicon signed headless smoke operating against the same Docker API before removing modules.
3. Delete Windows/GUI and ancillary subsystems in separate commits (CTRS-02), with smoke after each change.
4. Make `kiri daemon` a first-class terminal entry point with no app lifecycle dependence; fix CLI-only start/stop/restart (CTRS-03).
5. In parallel, build **read-only** spike reports for crabtables' production-kernel qualification, h12tiny Docker API framing, Lima vzNAT vs Kiri ports, and smolvm-network's VM bridge integration; only then choose the first substitution to merge.

### Reference links

- Kiri [architecture](https://github.com/libracoder/kiri/blob/main/docs/development.md), [feature matrix](https://github.com/libracoder/kiri/blob/main/docs/features.md), [source](https://github.com/libracoder/kiri)
- crabtables [README and qualification status](https://github.com/laputa-systems/crabtables), [CRAB-7 qualification contract](https://github.com/laputa-systems/crabtables/blob/main/docs/rfc/CRAB-7-nft-differential-qualification.md), [TODO evidence](https://github.com/laputa-systems/crabtables/blob/main/TODO.md)
- smolith [facade and HTTP crates](https://github.com/laputa-systems/smolith), [h12tiny architecture](https://github.com/laputa-systems/smolith/blob/main/docs/h12tiny/architecture.md)
- Lima [VZ networking](https://lima-vm.io/docs/config/network/vznat/), [port-forward benchmarks](https://lima-vm.io/docs/config/port/), [managed VMnet](https://lima-vm.io/docs/config/network/vmnet/), [v2.3 networking update](https://www.cncf.io/blog/2026/11/08/lima-v2-3-native-on-windows-vmnet-on-linux-and-menu-tui/)
- smolvm [runtime](https://github.com/smol-machines/smolvm), [smolvm-network](https://github.com/smol-machines/smolvm/tree/main/crates/smolvm-network), [limitations](https://github.com/smol-machines/smolvm/blob/main/docs/limitations.md), [security model](https://github.com/smol-machines/smolvm/blob/main/docs/security-model.md)
