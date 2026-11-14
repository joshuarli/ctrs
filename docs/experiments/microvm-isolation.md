# CTRS-19 — Per-task microVM isolation research (no code)

Date: 2026-11-14. Verdict: **no microVM mode, nothing merged, no default
change. Native containers inside the existing VZ guest remain the engine's
answer to untrusted code on this host class. An opt-in per-task microVM design
is sketched below for a future slice gated on Gate H; it is not built, not
authorized, and no security claim is made for it.**

Question: for *untrusted agent workloads* on a ctrs host, is a per-task
microVM (VZ or smolvm/libkrun) a meaningful upgrade over containers in the
shared guest VM, and at what cost?

## Evidence anchors (this machine, 2026-11-14)

- ctrs VZ guest boot: **149–155 ms** wake; 152–161 ms fresh (CTRS-17).
- ctrs VM: 2 CPUs, 8192 MiB, virtio balloon (host reclaims idle memory —
  `apple.rs:392`), virtio-block data.img (Cached, Fsync), optional virtiofs
  share, Rosetta dir share. Guest helper (`com.apple.Virtualization
  .VirtualMachine.xpc`) RSS **~1.1 GB** at idle — the balloon is what keeps an
  8 GiB guest small.
- Engine daemon RSS **25 MB**.
- Container start inside the shared VM: boot is amortized (VM already up);
  end-to-end `docker run --rm alpine true` is dominated by image unpack, not
  by a kernel boot. (No single clean number measured here — deliberately not
  claimed; CTRS-22 owns the perf rows.)
- smolvm (external comparison): README claims "<200 ms to agent ready" boot,
  elastic memory, per-workload VMs, macOS via Hypervisor.framework; at the
  pinned SHA the repo also documents checkpoint/restore caveats (credential
  bindings are re-authorized on restore; virtiofs DAX rejected on arm64) —
  docs cited at the pin.

## Comparison

| axis | per-task VZ microVM (design) | smolvm/libkrun per-task | native containers (today) |
| --- | --- | --- | --- |
| boundary | host↔guest hypercall (VZ); guest kernel inside | host↔guest hypercall (HVF); guest kernel inside | namespaces + cgroups; shared guest kernel |
| boot per task | ~150–160 ms VM + guest init + agent handshake (≈1–2 s realistic) — never measured end-to-end | "<200 ms to agent ready" claimed (unverified here); Linux claims least | image open + exec in live VM; ≈tens of ms + image |
| RAM at N tasks | N × per-VM helper (~hundreds of MB floor; observed ~1.1 GB for the shared 8 GiB VM with balloon) — **N=8 ⇒ several GB, always** | claimed elastic (host commits what guest uses); no local measurement | incremental ≈50–150 MiB per container in one 8 GiB ballooned VM |
| disk per task | cloned sparse data.img (APFS clone, copy-on-write) — cheap-ish; still one template per task | overlay + `.smolmachine` artifact story | shared image layers, per-container overlay |
| mounts | virtiofs (as ctrs already has); read-only default | virtiofs (+ DAX on x86_64; off on arm64) | virtiofs (ctrs today) |
| snapshots | VZ save/restore APIs exist (macOS 13+); ctrs implements **none**; restore would need secret re-authorization anyway | implemented; secrets re-authorized on restore; restore edge cases documented | none (image layers only) |
| secrets | no broker exists; would need new mechanism (mount at runtime; never baked into image) | credential substitution bindings; restore re-auth requirement | none native; same gap |
| networking | one VZNAT per VM (bridge/IP/MAC each; conntrack per VM, macvtap-class) or `none` — losing the shared-bridge model; published ports story undefined | virtio-net (smoltcp gateway) or TSI; DNS cache + egress allowlist optional | shared bridge + one DNAT table; published ports; working DNS relay |
| blast radius | host daemon + VMM XPC helper; VM escape = host root-adjacent | same | host daemon + shared guest kernel (container escape = guest kernel compromise → every container) |
| implementation in ctrs | new engine concept (N VMs per task), task lifecycle, image unpack per task, control plane, telemetry, kill/cleanup | new VMM type + Hypervisor.framework path (or shipping smolvm binaries) | zero new code |

## What the evidence does and does not show

Shows: the VM boundary is real, boots fast enough, and ctrs's VZ path is
proven on this hardware (CTRS-04/08/17 recovery, sleep/wake). It also shows
the shared-VM model is *not* free of escape risk: one guest-kernel exploit
crosses every container; a per-task microVM reduces that to one task.

Does not show: that untrusted *agent* code is common enough to justify the
cost; that a per-task microVM is faster or safer for short-lived tasks (the
VM boot + agent handshake is real latency on every task start); or that ctrs
can ship secrets into a task VM any more safely than into a container.

Explicit non-claims (Gate H): this repo does **not** claim multi-tenant
safety today, with or without microVMs; the host runs a root daemon with a
Docker-compatible socket, container images are arbitrary code by definition,
and the practical boundary is the single-user host. MicroVMs would raise
the bar against guest-kernel exploits, nothing else — not socket abuse by the
host process, not supply chain, not side channels.

## Cost of building it here (estimate, not a commitment)

New VM lifecycle entity (create/boot/wait/exec/destroy per task), per-task
MAC + NAT or `none`, per-task disk clones, per-task virtiofs mount, task→VM
attribution in logs and `docker inspect`, kill on crash + `--restart`
semantics, cleanup on daemon exit, tests for every lifecycle step, docs. On
the order of the CTRS-03/08 onboarding slices — weeks, not days — and it
touches the same engine lifecycle code where the nine silent deaths live
(CTRS-21). It is not a small patch and must never block the container path.

## Opt-in design (documented, not built)

If a concrete untrusted-workload demand appears, the only acceptable shape:

- off by default; explicit flag (`docker run --sandbox` or a run-level label);
- one ephemeral VZ microVM per task; cloned sparse data.img; balloon on;
  read-only virtiofs workspace; no host socket, no network unless requested
  (`--network none` default when the flag is present); VM destroyed on exit;
  no persistence, no restart-always for sandbox tasks;
- image pulls for sandbox tasks never unpack into the shared ctrs image
  store (separate root) — supply chain isolation;
- secrets: none injected by default; injection is a runtime-only,
  never-persisted path (restore APIs re-authorize, never reuse);
- success criteria for Gate H before merge: measured boot and RAM on the
  target hardware (not this report's anchors), a written threat model
  covering VMM compromise + daemon compromise, one differential fixture
  (escape attempt fails), one failure-mode test (kill -9 VM at every step),
  and docs stating exactly what is and is not protected.

## Recommendation

Do not build per-task microVMs in this campaign. Revisit only with a named,
concrete workload and Gate H satisfied. The shared-VM container model with
its documented limits is the honest answer at this stage.

## Citation index

- this repo: `crates/ctrs-vmm/src/apple.rs:370-450` (VM config: 2 CPUs,
  memory, balloon, virtio-block Cached/Fsync, virtiofs share, Rosetta share,
  VZNAT attachment); `docs/evidence/net.md` (boot/sleep-wake/RSS anchors);
  `docs/decisions.md` (CTRS-17).
- smolvm pin `146f3a5121c01a98bb894dc954e3c143a17c0084` (v1.34.1):
  `README.md` comparison table (boot claims, per-workload VMs) and
  platform matrix (HVF on macOS); `docs/limitations.md` (checkpoint/DAX
  caveats); `docs/credential-substitution.md` (restore re-authorization);
  `docs/incremental-checkpoints.md` (snapshot constraints).
- libkrun `171e5023`: `README.md` (HVF on macOS/ARM64; TSI needs custom
  kernel; VMM/guest as one network context).
