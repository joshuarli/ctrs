# CTRS-17 — vzNAT breakdown (host ↔ guest ↔ container)

Date: 2026-11-14. Verdict: **published ports on this machine ride the vsock
relay, not vmnet — macOS Local Network privacy blocks the NAT/DNAT path for
unsigned binaries (and for the dev `kiri` daemon itself). The one concrete
defect found and fixed is the guest agent answering `UplinkQuery` from a
boot-time cached DHCP lease forever; it now reads the kernel's live default
route + primary address. vzNAT as such was not stress-qualified here: the
host cannot address the guest VM's vmnet interface except through system
tools, so no honest apples-to-apples Lima comparison is possible on this
hardware.**

## Machine and topology

- macOS, Apple Silicon; Mac on `bridge102` at `192.168.64.1/24` (vmnet NAT
  is 192.168.64.0/24 — same facility as Lima's vzNAT). Guest eth0
  `192.168.64.20/24`, default via `192.168.64.1`.
- Engine: `target/release/kiri` (CTRS-16 head), guest initramfs rebuilt with
  the live-route agent fix (1,538 KiB; `cargo xtask guest`).
- Containers: `--network host` for engine-net measurements, `--network bridge`
  (172.17.0.0/16) for container tests, `fd00:dead::/64` for the v6 bridge.

## The Local Network privacy finding (the cause of "VM NAT unreachable")

Every attempt by a non-system process to open a TCP or UDP connection to
192.168.64.20 fails with `No route to host (os error 65)`; system binaries
are exempt. Verified in this session:

| process | TCP to guest | notes |
| --- | --- | --- |
| `ping` (ICMP) | works | RTT 0.23–1.20 ms |
| `nc` (connect) | works | `nc -v 192.168.64.20 5201` → "succeeded" |
| `curl` (connect) | connect ok, transfer fails (err 56) | |
| python (pyenv, `/usr/bin/python3` both) | `EHOSTUNREACH` | all builds, all ports, TCP and UDP |
| `kiri` dev daemon (unsigned) | `EHOSTUNREACH` | logged as `VM's NAT network is unreachable… over vsock` |

Consequence: the engine's published-port fast path (Mac → vmnet →
guest-kernel DNAT → container) is **unreachable for development builds on
this machine**; published ports already go over the vsock relay, which is
exactly the upstream #170/#186 report. The engine's 30 s retry (warn
first, info afterwards, per upstream #186) is alive in the logs. Nothing in
this slice makes vzNAT work around the filter; that needs a
Local Network permission grant for the engine (owner action) or a
signed/entitled build — recorded as a needs-owner item, not done here.

UDP side: Mac→guest UDP is dropped outright (no datagrams arrive, even
from `nc -u`). The published-UDP path (loopback → daemon → vsock → guest →
relay → container) works: 1000/1000 and 2000/2000 datagrams received,
0.00% loss (55 Mbps at 1280 B datagrams).

## Measured matrix

Single-flow unless noted. "Mbps/Gbps" is wire rate of application payloads.

| axis | result | spread / notes |
| --- | --- | --- |
| Mac → guest TCP (nc → in-VM python receiver) | ~2.13 Gbps | 2129, 2139, 2130 (one 1069 outlier) |
| Mac → guest TCP, 8 flows | **8.27 Gbps** | |
| guest → Mac TCP (nc in container → python receiver) | bimodal ~1.07 / 2.15 Gbps | 1072, 715, 2149, 1074 |
| guest → Mac TCP, 8 flows | **2.85 Gbps** | directional, vs 8.27 Mac→guest |
| host → container, published port, single flow | ~2.13 Gbps | 2127, 2142, 2128 |
| host → container, published port, 8 flows | **4.17 Gbps** | rides the vsock relay (NAT unreachable) |
| container → container (bridge, iperf3) | **125–149 Gbps** | 125, 149, 141 Gbit/s |
| container → Internet (OVH 10 MB) | ~14–45 Mbps | ≈ the Mac's own link (5.4–5.6 MB/s): WAN ceiling |
| published HTTP, fresh connection | p50 **0.74 ms**, p99 0.85, max 0.85 | n=50 |
| published HTTP, keepalive | p50 **0.47 ms**, p95 0.63, p99 2.61 | n=50, http.client |
| DNS via guest vsock relay | p50 **1.63 ms**, p95 2.25, max 19.44 | n=30 A lookups (google.com) |
| IPv6 bridge | works: `fd00:dead::2/64`, AAAA 4.96 ms | **no v6 egress** (no carrier v6 on uplink) |
| NAT state (conntrack, root netns) | 12 → 20 entries after 10×10 MB fetches | ≈ 1 entry per active flow |
| idle: daemon RSS / guest loadavg / VM CPU | 25 MB / 0.24 / 0.1–0.5 % | Virtualization.xpc helper ≈ 1.1 GB RSS |
| sleep (VM asleep after 60 s idle) → wake | boot 149–155 ms | `docker start` end-to-end 0.29–0.76 s |
| wake: `docker ps` | does NOT wake the VM | sleep/wake is request-driven |
| wake: published HTTP after wake | 0.55–0.63 ms | fresh + keepalive |

Lima reference points (M4 Max, vmnet iperf3: ~59.2 / ~130 Gbit/s) are not
reproducible here: the Mac side of vmnet is filtered for every binary that
is not Apple's, and a fair VM-to-VM measurement would need a second VM.
Sub-Gbit directional asymmetry and the 1.07/2.15 bimodality look like the
filter's shape, not the vmnet hardware.

## The stale-DHCP defect and its fix

`Kiri` reported "published ports over vsock" because vmnet was unreachable,
but a second, independent defect lurked behind the same symptom: the guest
agent answered `UplinkQuery` from a **boot-time cached DHCP lease forever**,
with no lease renewal anywhere (`Dhcp::timeout_ms` returns −1 once Bound).
If vmnet re-leased without a VM restart (walk into another vmnet, host
network change), the host would keep relaying/d-natting at a dead address
and published ports would ride vsock or fail silently.

Fix landed in this slice (`crates/kiri-init/src/linux/netlink.rs` +
`agent.rs`): `UplinkQuery` now issues `RTM_GETROUTE` (dst 0.0.0.0/0, main
table, unicast) and `RTM_GETADDR` (scope-universe primary IFA_LOCAL) and
answers with the live kernel state; the lease remains only as the
pre-DHCP-bind fallback. `cargo check -p kiri-init --target
aarch64-unknown-linux-musl` is clean. The guest was rebuilt (1,538 KiB) and
the fix verified live: VM boots in 161 ms, published HTTP answers 20/20
200 OK. Honest scope note: the renewal path itself (dhcp client never
renews) is unchanged — it still feeds DNS fallback, now redundant for the
route query. Pulling the relay's own address from the kernel removed the
class of failure; forcing a vmnet re-lease from inside the VM to exercise
the updated answer is not possible on this hardware.

## Bottleneck named, with evidence

On this machine there is **no measurable vmnet/NAT bottleneck at the
container boundary** — container↔container runs at 125–149 Gbps and
container→Internet saturates the WAN link. The real, named bottlenecks:

1. **macOS Local Network privacy** decides whether Mac-side binaries may
   reach the vmnet subnet at all (findings table above). Unsigned dev
   binaries and the daemon get nothing; `nc`/`curl`/`ping` do. This is the
   whole story of "VM NAT unreachable" on this hardware.
2. **The vsock relay**, which carries all published-port traffic here:
   ~2.1 Gbps single / ~4.2 Gbps 8-flow — healthy, but capped relative to
   vmnet claims and direction-asymmetric vs raw vmnet (8.27 Gbps Mac→guest).
   Published UDP works without loss at ~55 Mbps.
3. **WAN** for anything leaving the VM (~40 Mbps — same as the Mac's own
   uplink to the same endpoint).

An honest vzNAT qualification additionally needs a Local Network grant for
the engine (or a signed/entitled build), or a Linux host — both are
recorded as needs-owner items. Before/after for the fix that *did* land:
before = agent answers a possibly-dead lease forever; after = live kernel
answers every `UplinkQuery` (code-level; the NAT path stays exercised only
through the vsock relay on this machine, as before).

## Verification and session notes

- Fresh scratch engine (empty data/home roots): **e2e
  `tests/e2e.sh` 480 passed, 0 failed, 0 skipped** with the new guest
  agent. A first attempt on the pre-existing scratch engine reported 9
  failures, all environmental: (a) the eight `build-*` checks used a stale
  user-level buildx builder `kiri-build-e2e` (endpoint
  `.work/tmp/e2e.sock`, no longer exists — `docker buildx inspect` exits 0,
  so the harness never recreated it; removed with`docker buildx rm -f`),
  (b) `filter-ancestor` saw 3 alpine containers because of a leftover bench
  container in the shared scratch root. No code change was involved; the
  re-run after cleanup is the 480/0/0 figure.
- `cargo test --workspace` 192 pass; `cargo check --workspace` clean;
  musl check `-p kiri-init` clean; smoke was 15/15 with the CTRS-16 binary
  and the VM was exercised end-to-end by the above.
- Two VM boot anomalies this session, both self-clearing: "storage device
  attachment is invalid" on a boot raced with the old VM's shutdown
  (flock(2) on `data.img` verified free; retry booted in 152 ms).
- Silent engine deaths **#8** (10:16:30Z, right after the guest→Mac 8-flow
  burst; VM helper gone, zero log output) and **#9** (10:42:51Z, during the
  published-UDP probes). Session tally: **9**. The VM helper process for
  this run is `com.apple.Virtualization.VirtualMachine.xpc` at ~1.1 GB RSS.
- Benchmark tools are in `bench/net/` (`send.py`, `recv.py`, `udploss.py`,
  `udprecv.py`, `latency.py`) — Python stdlib only, usable inside guests via
  `docker cp`/`-v`.
