# Security model — ctrs (a headless ctrs)

Date: 2026-11-14. Status: honest statement of what is and is not protected,
with the evidence for each claim (see `docs/evidence/security.md`). Nothing
here claims multi-tenant safety; the host runs a root daemon with a
Docker-compatible socket and arbitrary images pull through it. Single user,
single trust domain. Untrusted code runs *inside* the guest VM; the guest is
the boundary, and a container inside it is a namespace smaller than the
guest's kernel.

## Components and trust

| Component | Runs as | Sees | Talks to |
| --- | --- | --- | --- |
| `ctrs` daemon | host user (usually the login user; root on Linux) | Docker API socket, its data root (`~/.local/share/ctrs/data` / `CTRS_DATA_DIR`), registry credentials | the VM over vsock, the guest agent, the Mac's resolvers |
| macOS VM (VZ) | VZ XPC helper process per VM | guest memory (shares host page cache for virtiofs) | the daemon |
| `ctrs-init` (agent) in the guest | root in the guest kernel | the guest kernel; the host only through framed vsock messages | the daemon; netns per container |
| container | uid inside the guest's user namespace | its rootfs, its netns | outbound network (via the guest's NAT/conntrack), the DNS relay |

The two trust boundaries, in order of strength:

1. host ↔ guest (VZ hardware virtualization): the host's memory and devices
   are not guest-addressable. The guest reaches the host only as a vsock
   peer answering fixed, typed frames (`ctrs-proto`) — never shared memory.
2. guest ↔ container (namespaces + cgroups + seccomp): weaker. Root in a
   container is root in the guest's user namespace. This boundary exists to
   contain accident, not an adversary with a kernel exploit.

## Attack surface, and what closes it

### The daemon socket (`CTRS_SOCKET`, `~/.local/share/ctrs/run/docker.sock`)

- `0600` permissions; Linux hosts may grant a group with
  `CTRS_SOCKET_GROUP` (checked per connection, not only at connect).
- Two daemons may not share a data root: an `flock(2)` on `<root>/.lock`
  refuses the second engine at boot (added CTRS-21). Before it, two engines
  on one root interleaved blob writes silently.
- The stale socket is unlinked and rebound on boot; the socket path is
  never created before `0700` state directories exist.
- The API is the full Docker surface ctrs implements — including
  `--privileged` creation — so whoever can touch the socket can run code
  in the VM. It is a *user* boundary, not a hardening layer.
- The HTTP parser is hand-written (CTRS-14/15): 100-continue, framing
  validation (CL+TE rejected; mismatched/non-numeric repeated CL rejected;
  identical repeated CL accepted), 64 KiB head cap, 8 MiB buffered-body
  cap, bounded chunked decoder (64 B chunk lines, 8 KiB/32-field trailers,
  per-chunk CRLF). A framing failure answers `400 bad request framing` and
  closes rather than executing a misparsed next request.

### The guest agent (`ctrs-init`)

Runs as root in the guest. Everything it accepts arrives as a framed vsock
message with a typed opcode (`ctrs-proto`); malformed frames are dropped.
It does no path lookup it was not asked to do: image unpacks are confined
to the container's rootfs with the `tar` crate's traversal rules *plus* a
fail-closed check (CTRS-21): an entry whose path escapes the layer root
previously unpacked silently-skipped yet was recorded as loaded; now the
layer is refused outright.

### Seccomp (the container's filter)

Default profile = Docker's deny-list shape, enforced per container:

- Everything outside the container's namespaces that Docker also closes:
  kernel keyrings, module loads, kexec, time-setting, swap/quota/NUMA
  policy, `bpf`, `perf_event_open`, `userfaultfd`, `io_uring_{setup,enter,
  register}` — EPERM, unless the container holds the capability that would
  make the operation legitimate (e.g. `SYS_ADMIN` for mounts, `PERFMON`
  for `perf_event_open`, `BPF` for `bpf`, `SYS_TIME` for `clock_settime`,
  `SYS_NICE` for `mbind`/`set_mempolicy`/`*_pages`, `SYS_PACCT` for
  `acct`, `SYS_MODULE` for module syscalls, `SYS_BOOT` for
  kexec/`reboot`).
- `clone3` is ENOSYS for everyone without `CAP_SYS_ADMIN` (its flags are
  hidden in memory a filter cannot read, so libc must fall back to
  `clone`, whose flags the filter does read and rejects `CLONE_NEWNS`
  et al. for non-`SYS_ADMIN` containers).
- `socket(AF_VSOCK, …)` is `EAFNOSUPPORT` for *everyone, always* —
  including `--privileged` and `seccomp=unconfined`. vsock is not
  namespaced; it is the control channel to the host, and no container
  gets it.
- `io_uring` is EPERM for everyone, always, for the same class of reason
  (it can fabricate fds the filter never sees, including sockets).
- `seccomp=unconfined` and `--privileged` install only the host boundary
  (vsock + io_uring). Everything else is then capability-gated by the
  kernel, as with Docker.
- Architecture: aarch64 `AUDIT_ARCH_AARCH64` only; x86-64 is not built
  with the x32 mask because the released VM is aarch64 (the x32 block
  exists in source for the x86_64 build).

The matrix fixture (`conformance/seccomp/run.sh`) compiles a static probe
and replays every probe syscall under default, `no-new-privileges`,
`seccomp=unconfined`, `--privileged`, eight single `--cap-add` modes, and
asserts the filter and the relaxation rules. It is green on this host
(2026-11-14).

### `--privileged`

`--privileged` gives a container every capability, the guest's devices,
writable `/sys` and writable cgroups. It does **not** give the host's
socket, `/dev/kmsg` on the host, or io_uring/vsock — those stay closed.
What it *shares* is the guest: a privileged
container can reach the agent's vsock control channel (it is a root
process in the guest, after all), can mount over what it can see, and can
set the guest's clock (verified: `settimeofday` returns OK).
`--privileged` is therefore a guest-escape-to-VM level grant by
convention, not a sandbox escape — but assume a privileged container owns
the guest.

### Mounts and volumes

- The host's root filesystem is shared into the guest over virtiofs,
  **read-write**, at `/mnt/mac` (that is how bind mounts work). Containers
  never see it — only the guest agent and, in the guest, root-equivalent
  processes do. A privileged container, or anything that escapes the guest
  boundary, can therefore read and write the host filesystem, including
  `~/.ssh`, `~/.docker`, and the engine's data root. That is the single
  trust domain this engine is built for; do not run workloads you do not
  trust with your host's filesystem.
- Host directories share through virtiofs, read-only or read-write as
  asked. Every host page the guest reads through virtiofs is also
  readable by anything in the guest.
- A container can see only its own rootfs, its volumes, and its mounts.
  Mount propagation inside the guest is private; the host never sees a
  container's mount table.
- The engine maps container uids through the guest's user namespace, so
  host file ownership does not leak into a container as root.

### DNS relay and the Mac

Containers resolve through the guest agent's resolver, which forwards
failures to the daemon over vsock; the daemon relays to the Mac's
resolvers. A container can therefore ask the Mac's resolver anything —
that is the designed leak and is bounded by the relay's per-query caps
(1.5 s/resolver, 3.5 s budget, 256 concurrent, garbage dropped). There is
no DNS-based exfiltration path beyond the DNS payload itself.

### Networking

Egress is the guest's NAT/route (or vsock relay when vmnet is blocked by
Local Network privacy — the common case on this host, CTRS-17). There is
no egress allowlist in ctrs; every container can reach whatever the
guest can route to, filtered by `conntrack` and the guest's default
forward rules. Nothing here prevents a container from port-scanning the
host LAN — do not run untrusted workloads on a guest attached to a
primary LAN segment.

## Failure and crash behavior

- Daemon SIGKILL at rest: the VM stops with it; the stale socket is
  rebound on restart; containers whose record says they were running come
  back under their restart policy on the next boot (verified:
  `unless-stopped` auto-restarted after SIGKILL, both engines).
- VM death *while the daemon lives*: containers are marked `Exited (255)`
  and persisted, and since CTRS-21 the `Event::Lost` handler boots a fresh
  VM and restarts every `always` / `unless-stopped` container that was
  running when the VM died (the same policy scan a daemon boot uses).
  Verified by `kill -9` of the Virtualization.framework XPC helper on a
  scratch engine: VM re-boots in ~150 ms, the policy container comes back.
  Details: the #50 known-issue in `docs/decisions.md` and
  `docs/evidence/security.md`.
- Nine silent daemon deaths in this campaign (zero log output, no host
  memory pressure, guest VM helper gone) — root cause **unproven**: a
  hypothesis (Virtualization.framework XPC helper dying after bursts of
  privileged-container activity and VM wakes), not an established cause.
  `conformance/watch.sh` now supervises the daemon as a child process
  under privileged-container churn and records the OS-reported end
  (exit code or signal), instance identity (pid, data root, socket,
  kernel boot id), VM generations and the log tail to
  `.work/tmp/watch-reports/*.jsonl`; the next death on this host will be
  classified as signal or exit code rather than presumed. The engine
  survives each one if a supervisor restarts it; a restart loses
  in-flight pulls but not the store (digest-verified, atomic
  `containers.json`).
- The guest's console (`hvc0`) is captured to `<data root>/vm-console.log`
  (previous generation `.prev`) since CTRS-21, and the last 32 KiB are
  emitted into the daemon log when the VM stops unexpectedly, so a guest
  oops is no longer silent.

## What is not protected, stated plainly

- No claim of multi-tenant isolation. One daemon, one user, one trust
  domain; containers are not a boundary against a guest-kernel exploit.
- No seccomp profile for the *agent* itself (`ctrs-init` is root by
  design; it is the container's warden, not a tenant).
- No integrity enforcement beyond the app sandbox: an attacker who
  replaces the binary runs their own daemon.
- No audit log of container API calls beyond the engine log
  (`containers` start/stop/exit records); no SBOM attestation of images
  at pull time beyond digest verification.
- Images pulled by tag are mutable; pin digests (`@sha256:…`) for
  byte-identical pulls. Digest-verified on pull, verified again at
  unpack.
- `io_uring` and `vsock` are denied to containers, but a container can
  still reach the host's LAN when the VM is attached to one.
- The registry's bearer token is held in memory by the daemon; an
  attacker who reads the daemon's memory or the store gets it. The store
  is `0700`.

## Secrets

- `CTRS_SOCKET` (socket) is `0600`; the data root is `0700`.
- Registry credentials live in the docker CLI credential store (OS
  keychain), passed per request, never written by ctrs.
- No secret is ever injected into the VM by this engine.
