# CTRS-18 — `smolvm-network` paper analysis (no code)

Date: 2026-11-14. Verdict: **reject adoption. No dependency, no code, no new
device path. The only attachable idea with real upside today is a DNS answer
cache, and even that is not adopted here — it needs a measured hot path and a
written threat model first (Gate G).**

Inputs (all pinned; paths/line numbers verified at the pin):

- smolvm `146f3a5121c01a98bb894dc954e3c143a17c0084` (2026-11-14T08:19, v1.34.1)
  — `crates/smolvm-network/` (identical to current main `e2aa564a` / v1.35.0
  except the crate version bump; `git diff` shows only `Cargo.toml`).
- libkrun `171e502379b513d0f15d4edf1c27e518f33ba58d` (2026-11-13) — `README.md`.
- ctrs (this repo, CTRS-01…17 head): `crates/ctrs/src/daemon/{dns.rs,ports.rs}`,
  `crates/ctrs-init/src/linux/relay.rs`, `docs/evidence/net.md`.

smolvm-network is **not** a vzNAT drop-in. It is a userspace TCP/IP stack
(smoltcp 0.13) in the VMM process, terminating every guest flow and relaying
payloads to host sockets (`README.md`, "How traffic flows":
guest kernel → virtio-net → libkrun frame bridge → shared frame queues →
smoltcp gateway → host sockets). TSI is a different, mutually exclusive
mechanism in libkrun ("networking is provided by two different, mutually
exclusive techniques: virtio-vsock + TSI and virtio-net + passt/gvproxy" —
libkrun `README.md` §Networking), and it **requires a custom kernel** ("like
the one bundled in libkrunfw", libkrun `README.md` §TSI known limitations)
plus sockets of type SOCK_STREAM/SOCK_DGRAM and AF_INET/AF_INET6/AF_UNIX only.

## Host resources per flow and port exhaustion

| Concern | smolvm-network (virtio-net) | ctrs (VZNAT + vsock fallback) |
| --- | --- | --- |
| host FDs per guest TCP flow | 1 host `TcpStream` (host-facing) + ≈1 wake-pipe/channel set; the guest-facing smoltcp socket holds no FD. Published ports: 1 accept socket per `-p HOST:GUEST` (`lib.rs` `TcpPortListeners` — "one accept thread for every `-p HOST:GUEST`") | 0 per egress flow (the guest kernel owns them; host kernel tracks conntrack only). Published ports: 1 host socket per client connection; vsock relay path additionally holds the guest-relay stream pair |
| per-process FD cap | macOS `kern.maxfilesperproc` = 10,240 on an 8 GB Mac → "a Mac machine holds about 9,900 connections at once" (`docs/limitations.md:35-36`); Linux ~524,288, `SMOLVM_TCP_RELAY_CAPACITY` caps machine at 65,536 open TCP connections (`docs/limitations.md:40`) | not applicable to VZNAT egress (no VMM sockets); published ports capped by host sockets, not by a VM-wide table (1024-session cap per UDP relay, `relay.rs`) |
| outbound source ports | leave from the host's ephemeral pool **shared by every machine on the host**; TIME-WAIT 30 s (macOS) / 60 s (Linux) over a 16,384-port range; churn → `EADDRNOTAVAIL` (`docs/limitations.md:42-45`) | VZNAT flows originate inside the guest (own ephemeral range, guest conntrack); shared-host-port exhaustion cannot occur for egress |
| guest-facing buffers/flow | full tier (≤1024 flows): 256 KiB RX + 256 KiB TX smoltcp buffer per flow (`tcp_relay.rs:52-64` `TCP_RX/TX_BUFFER_BYTES`, `FULL_BUFFER_CONNECTIONS`); small tier: 16 KiB/side; relay channel 32 × 16 KiB (`CHANNEL_CAPACITY`, `RELAY_BUFFER_BYTES`) | kernel socket buffers + conntrack entry (~hundreds of bytes/flow); no per-flow smoltcp state in the VMM |
| extra per-flow state | `TsyncSender`/`mpsc` channels, `FlowSummary` accounting, timers in a binary heap, relay poller | conntrack tuple only (measured 12→20 entries after 10×10 MB fetches, `docs/evidence/net.md`) |
| throughput ceiling | one poll thread per machine (`smolvm-net-poll thread`) plus one relay thread per flow, or a shared reactor (`tcp_reactor.rs`); every packet crosses userspace twice | hardware line rate for NAT paths (container↔container measured 125–149 Gbps in the guest); published-port vsock fallback ≈2.1/4.17 Gbps single/8-flow |

Memory estimate (derived from code constants, not measured): full tier ≈0.5–1 MiB
per active flow in the VMM (two 256 KiB smoltcp buffers + relay/channel
buffers + kernel socket buffers); tens of thousands of full-tier flows = tens
of GB. smolvm mitigates past 1024 flows with the 16 KiB tier (still ≈0.5 MB
worst case with channel capacity). ctrs VZNAT holds none of this.

## Latency and correctness shape

smolvm-network terminates TCP in smoltcp: every guest byte is parsed and
re-framed by a userspace stack — correctness lives or dies with smoltcp's
reassembly, window probing, RST handling and its interaction with the guest's
kernel stack. The design pays TCP_NODELAY on both sides explicitly to avoid
batching delay (`README.md`), and the relay adds a userspace hop over VZNAT's
kernel path. There is no published latency number for the smolvm gateway in
the repo to quote, and CTRS's own CTRS-17 measurement (vsock relay published
ports: p50 0.74 ms fresh / 0.47 ms keepalive; keepalive p99 2.6 ms) shows the
*vsock* fallback already costs a few hundred µs — the right comparison class
for any userspace relay, not the kernel path.

## Security boundary

- smolvm's virtio-net gateway sees every guest byte; a parser bug in smoltcp
  is a VMM compromise (the VMM is in root-adjacent trust for the host
  service). The egress policy (`EgressPolicy`, `egress.rs`) is a filter on
  *which* flows open host sockets, never a boundary for a compromised VMM.
  Its own docs say so: "An allowlist is one layer of enforcement, not a
  complete sandbox" (`crates/smolvm-network/README.md:62`).
- TSI (libkrun): "the VMM and the guest should be considered to be running in
  the network context"; apply on the VMM whatever restrictions you would apply
  on the guest (libkrun `README.md` §Security model). TSI additionally
  requires the custom libkrunfw kernel and silently gives the guest raw
  network access with no policy at all — egress policy is not enforceable
  there; smolvm's own header says TSI is *rejected* for policy-bearing
  machines because "its libkrun filter has not enforced the equivalent policy
  in empirical tests" (`egress.rs:3-6`).
- ctrs: VZNAT attachment is off the VMM data path entirely (device only;
  DNAT/conntrack in the guest kernel, which is the isolation boundary for the
  container model anyway). The vsock relay is the same *class* of trust
  (userspace proxy of guest streams) but is bounded to published ports and is
  the documented fallback — and it is what our own measurements exercise.
  A general userspace gateway would widen that surface from "published ports
  only" to "every byte every flow".

## Which ideas could attach to our design without libkrun

1. **DNS answer cache in the daemon's vsock DNS relay** — attachable, honest
   design candidate. ctrs's relay (`crates/ctrs/src/daemon/dns.rs`) has no
   cache: every lookup pays the Mac's resolver round trip (measured p50
   1.63 ms) and a concurrent burst fans out 1:1. smolvm's cache
   (`dns_cache.rs`) is a good template: keyed on the lowercased question +
   RD/CD/DO/EDNS + upstream set; only single-question recursive queries
   cached; positive TTL = smallest record TTL (capped 300 s), negative =
   SOA's, nothing else cached; entries live in the VMM process only (a
   fork/branch starts empty); sits *behind* the policy so a cached answer can
   never authorize a disallowed name. ctrs differences: no policy layer, so
   the "behind the allow-list" invariant does not exist — the cache would be
   unscoped, and a cache that serves stale answers after the host's network
   changes (sleep/wake, new vmnet) is a correctness bug class; flushing on
   wake and capping at 4,096 entries / 60–300 s TTL would be mandatory. This
   is a real but narrow win; the DNS hot path is not a named CTRS-17
   bottleneck. **Design note only — not implemented.** If DNS is ever named
   the bottleneck (or an egress policy lands, restoring the behind-policy
   invariant), Gate G requires a measured before/after (pull-heavy or
   dial-heavy workload), the cache behind the policy, and a written threat
   note (poisoning/stale-answer scope) before merge.
2. **Egress allowlist ACLs** — attachable at the guest's nftables layer
   (CTRS-11/13 owned the firewall inventory; the guest already runs nftables
   from the initramfs). smolvm's shape is the model: static CIDR list,
   allow-host names via DNS interception with *learned* IPs (TTL clamp
   [60 s, 3600 s], `egress.rs:30-31`), a private-floor block with explicit
   exceptions (`with_private_floor`), protocol rules, denial logging, and a
   replacement path that can only narrow. For ctrs this would be a new opt-in
   feature (`--egress-allow` or a daemon config), not a default; it interacts
   with CTRS-13's adapter work and with tailnet/private-subnet collisions
   (don't hardcode 100.96.0.0/10 — smolvm's own choice; detect host routes).
   **Design note only — not implemented**; adoption would need a written
   threat model first (allowlist is one layer, never a sandbox; the guest
   kernel is in the boundary), plus one differential fixture and one
   failure-mode test per the experiment protocol.
3. **Socket relay as the general egress path** — not attachable. Would
   require replacing VZNAT with a userspace gateway (no such layer exists in
   VZ; there is no frame queue to hang smoltcp off), accepting the FD caps,
   shared ephemeral range, and VMM-in-the-data-path boundary above, and
   discarding a kernel path that measures at line rate. Rejected.
4. **TSI / libkrunfw** — not attachable. Custom kernel requirement; no
   policy enforcement in empirical tests per smolvm's own note; mutually
   exclusive with VZNAT. Rejected.
5. **Small-buffer tier past N flows** (`FULL_BUFFER_CONNECTIONS` pattern) —
   fine pattern to steal for ctrs's vsock relay allocation policy if published
   ports become fd-heavy, but it solves a problem we have not measured; ctrs
   uses bounded per-stream buffers already. Note only.
6. **Mediated egress** (token-authenticated preamble + external decider,
   `smolvm_protocol::mediated_egress`) — requires a VMM-resident decider and
   protocol changes; ctrs's boundary is the guest, not a host-service
   sideband. Skip.

## Explicit recommendation

**Adopt nothing.** Specifically: (a) do not add `smolvm-network` or libkrun to
any build; (b) do not reimplement a smoltcp gateway for VZ; (c) do not enable a
per-flow relay where vzNAT works; (d) keep published-port fallback on vsock as
is (measured clean); (e) if and only if a later slice names DNS latency as the
bottleneck, propose the cache as its own gated slice (Gate G) with the
CTRS-18-referenced threat note; (f) record the egress-ACL option as a design
candidate alongside CTRS-13's firewall adapter, not as work in this campaign.

This is the default outcome the slice pre-committed to ("Default outcome: no
adoption"), reached here from evidence rather than from the default: every
attachable idea either contradicts our trust boundary or lacks a measured
hot path; the one that doesn't (DNS cache) is documented and deliberately not
authorized for implementation.

## Citation index

- `crates/smolvm-network/README.md` (pin v1.34.1): frame-bridge path; "one
  accept thread for every `-p HOST:GUEST`" is in `lib.rs` module docs;
  "allowlist is one layer" at line 62; TCP_NODELAY both sides.
- `crates/smolvm-network/src/tcp_relay.rs` (pin): `TCP_RX_BUFFER_BYTES` /
  `TCP_TX_BUFFER_BYTES` = 256 KiB (L52-53); `MAX_CONNECTIONS` = 65,536 (L58);
  `FULL_BUFFER_CONNECTIONS` = 1024, `TCP_SMALL_BUFFER_BYTES` = 16 KiB (L63-64);
  `CHANNEL_CAPACITY` = 32, `RELAY_BUFFER_BYTES` = 16 KiB (L71-72);
  `GUEST_CLOSED_KEEPALIVE` = 60 s (L81-84); flow → host-`TcpStream` mapping and
  `TcpRelayTable` (module docs).
- `crates/smolvm-network/src/tcp_reactor.rs` (pin): shared reactor vs
  per-flow thread; reactor adopts established flows.
- `crates/smolvm-network/src/dns_cache.rs` (pin): TTL caps 300/60 s, 4,096
  entries; single-query recursive only; key = lowercased question + flags +
  upstreams; VMM-process lifetime.
- `crates/smolvm-network/src/egress.rs` (pin): policy is pre-connection filter
  ("Disallowed destinations are dropped before any host socket is created");
  learned hosts TTL clamp [60, 3600] (L30-31, clamped at L968); private floor
  with explicit exceptions; TSI explicitly rejected for policy machines (L3-6).
- `crates/smolvm-network/src/lib.rs` (pin): `GuestNetworkConfig` point-to-point
  /30 + ULA fd53:4d00::/64 link; NAT-in-default (`GuestSubnet` RFC 6598
  100.96.0.0/30); TUN/TAP netns mode behind `#[cfg(target_os = "linux")]`.
- `docs/limitations.md` (pin): per-flow host socket holds one FD; macOS
  maxfilesperproc 10,240 → ~9,900 concurrent; virtio-net cap
  `SMOLVM_TCP_RELAY_CAPACITY` = 65,536; host-ephemeral TIME-WAIT 30 s/16,384
  ports → `EADDRNOTAVAIL`; "ping fails … even while HTTP works" (default
  backend) — i.e., the default has no interface, no ICMP.
- libkrun `README.md` (`171e5023`, main): TSI "Requires a custom kernel";
  "networking is provided by two different, mutually exclusive techniques";
  "It's limited to SOCK_DGRAM and SOCK_STREAM … AF_INET, AF_INET6 and
  AF_UNIX"; "virtio-vsock + TSI" proxy model; "you should apply on the VMM
  whatever restrictions you want to apply on the guest".
- this repo: `crates/ctrs/src/daemon/dns.rs` (no cache; 1,500 ms/resolver,
  3,500 ms budget, 256 concurrent relays); `crates/ctrs/src/daemon/ports.rs`
  (NAT fast path + vsock fallback); `docs/evidence/net.md` (CTRS-17 matrix);
  `crates/ctrs-init/src/linux/relay.rs` (fallback relay).
