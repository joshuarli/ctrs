# Firewall — the nf_tables configuration `kiri-init` maintains

Scope: every nftables message the agent builds, by hand, in
`crates/kiri-init/src/linux/netlink.rs` — there is no `nft` binary, no
iptables, no iptables-nft. The file is the only place that speaks
`NETLINK_NETFILTER`; the configuration is always the whole table, replaced
atomically. This inventory was written against the tree at the CTRS-11
commit; grep for `NFT_MSG_`, `NFNL_MSG_` and `NETLINK_NETFILTER` to confirm
the call sites.

## Verified call sites

| Constructor | Purpose | Called by |
| --- | --- | --- |
| `install_nat_from()` | IPv4 table, whole replacement | `net::install_nat` ← `host_uplink()`, `uplink()`, `publish()`, `publish_vm()`, `refresh_nat()` |
| `install_nat6()` | IPv6 table (per IPv6 network) | `Bridges::bring_up`/`update_v6` (adds), `Bridges::remove` (last removal), `remove_host_network()` |
| `remove_nat()` | destroy the IPv4 table | `remove_host_network()` (clean stop of a Linux host agent) |
| `dnat_rule()` / `dnat_rule_from()` / `dnat_rules()` | published ports | `install_nat_from` |
| `redirect_rule()` | host.docker.internal → local listener | `install_nat_from` |
| `dns_redirect_rule()` | UDP/53 to the reserved address → bridge-gateway DNS | `install_nat_from` |
| `published_masq_rule()` | MASQ of VM-uplink→bridge traffic from the Mac | `install_nat_from` (VM mode, TCP dnat only) |
| `forward_filter_in()` | filter isolation, IPv4 + IPv6 | `install_nat_from`, `install_nat6` |
| `localnet_guard()` | containers → host loopback guard | `install_nat_from` |
| `host_relay_guard()` | only redirected connections to the relay port | `install_nat_from` (VM mode) |
| `masq6_rule()` | NAT66 per IPv6 network | `install_nat6` |
| `nat_chain()` | prerouting/output nat chains | `install_nat_from` |

No other file touches `NETLINK_NETFILTER`. The rtnetlink side (bridges,
veth, addresses, routes) lives in the same file; it is inventoried at the
end for completeness.

## Wire encoding, once

`NETLINK_NETFILTER`, subsystem `NFNL_SUBSYS_NFTABLES` (10), big-endian
`nla_type` semantics with `NLA_F_NESTED`. A change is one
`NFNL_MSG_BATCH_BEGIN` (with `nfgenmsg { AF_UNSPEC, res-id = NFTABLES }`),
`NFT_MSG_*` messages, `NFNL_MSG_BATCH_END`, sent on one socket in one
`send()` call. The kernel applies it as one transaction: if any message is
refused, none are.

Table replacement is `DESTROYTABLE kiri` + `NEWTABLE` + chains + rules in
the same batch (`NFT_MSG_DESTROYTABLE` = like DELTABLE but no error when
absent, Linux 6.3+). The comment in `install_nat_from` says it correctly:
*destroying it in the same batch keeps the old one if anything below is
refused*.

`Msg::new` sets `NLM_F_REQUEST`; create messages use `NLM_F_CREATE`
(+ `NLM_F_EXCL` for bridges), rule messages use `0x800` = `NLM_F_APPEND`.

Attribute numbering follows the nftables UAPI: `NFTA_TABLE_NAME` = 1,
`NFTA_CHAIN_TABLE`/`NFTA_CHAIN_NAME` = 1/3, `NFTA_CHAIN_HOOK` = 4
(`hooknum`, `priority`), `NFTA_CHAIN_POLICY`/`NFTA_CHAIN_TYPE` = 5/7,
`NFTA_RULE_TABLE`/`CHAIN` = 1/2, `NFTA_RULE_EXPRESSIONS` = 4,
`NFTA_EXPR_NAME` = 1, `NFTA_EXPR_DATA` = 2, `NFTA_META_*` = 1/2,
`NFTA_CT_KEY` = 2 (STATE = 0, STATUS = 2), `NFTA_DATA_*` for verdicts,
`NFTA_MASQ_FLAGS` = 1 (only `NF_NAT_RANGE_PROTO_RANDOM_FULLY` = 16 used).

## Table layout

```text
table ip kiri {                                  # created iff the engine manages any network
  chain postrouting { type nat hook postrouting priority 100; policy accept;
    oif <uplink> masquerade
    # VM mode with >=1 published TCP port:
    iif <uplink> ip saddr <gateway> oifname "kiri*" masquerade fully-random
  }
  chain prerouting { type nat hook prerouting priority -100; policy accept;
    # VM mode (redirect=true):
    iifname "kiri*" meta l4proto tcp ip daddr 198.19.248.254 redirect to :1026   # HOST_RELAY_PORT
    iifname "kiri*" udp dport 53 ip daddr 198.19.248.254 redirect to :53           # dns_redirect_rule
    iif <uplink> ip saddr <gateway> fib daddr type local                           # published TCP ports,
      ip daddr != 127.0.0.0/8 tcp dport <hp> dnat to <ip>:<p>                      #   from the Mac only
    # Linux host mode (redirect=false):
    [iif <any>] [ip daddr X | fib daddr type local ip daddr != 127.0.0.0/8]
      tcp|udp dport <hp> dnat to <ip>:<p>
  }
  chain output     { type nat hook output priority -100; policy accept;
    # VM mode: ip daddr 198.19.248.254 tcp dport 1026 redirect to :1026
    # host mode: per published port (tcp and udp), same match as prerouting
  }
  chain forward    { type filter hook forward priority 0; policy accept;
    oifname != "kiri*" accept
    ct state established,related accept
    ct status dnat accept
    iifname "kiriN" oifname "kiriN" accept   # one per bridge, whole name
    drop
  }
  chain input      { type filter hook input priority 0; policy accept;
    iifname "kiri*" ip daddr 127.0.0.0/8 \
      ct state & (established|related) == 0 ct status & dnat == 0 drop
    # VM mode only:
    tcp dport 1026 ct status & dnat == 0 drop
  }
}
```

```text
table ip6 kiri {                                 # created iff an IPv6 network exists
  chain postrouting { type nat hook postrouting priority 100; policy accept;
    ip6 saddr <subnet>/<prefix> oifname != "kiri*" masquerade   # one per IPv6 network (NAT66)
  }
  chain forward    { … same as IPv4, family NFPROTO_IPV6 … }
}
```

The reserved host address is `HOST_ADDR = 198.19.248.254` (`net.rs`);
the VM's host relay port is `HOST_RELAY_PORT = 1026`. `iptables` priorities
are used (filter = 0, NAT prerouting/output = -100, NAT postrouting = 100).
Both tables carry `chain policy accept`; isolation is by explicit `drop`
rules, not by chain policy.

## Every rule, precisely

### postrouting (IPv4)
1. `meta oif (NFT_META_OIF = 5) => reg 1; cmp eq <uplink ifindex>; masquerade`.
   Matches only packets leaving the uplink; the VM or Linux host is NATed to
   its own address, as Docker's default. On a Linux host this was written
   once at `host_uplink()`; in the VM at `uplink()` boot.
2. VM mode, only with ≥1 published TCP port: `published_masq_rule()` —
   `meta iif <uplink> (NFT_META_IIF = 4)` `and` `payload saddr <gateway>`
   `and` `oifname "kiri*"` `masq fully-random`
   (`NFTA_MASQ_FLAGS = NF_NAT_RANGE_PROTO_RANDOM_FULLY (16)`).
   The Mac's connections to a published port arrive at the container from
   the bridge gateway on a fresh port, like Docker's userland proxy; a Mac
   source port reused within the container's 60 s TIME_WAIT never meets the
   old socket. Verified live in the VM (CTRS-13): the rule appears in
   postrouting, not prerouting as first drafted here.

### prerouting (IPv4, VM mode)
1. `redirect_rule(…, from_bridges = true)`: `iifname "kiri*"` (4-byte prefix
   cmp against `BRIDGE_PREFIX`) `ip daddr 198.19.248.254` (payload network
   header +16, 4 bytes) `l4proto tcp` → immediate reg 1 = `HOST_RELAY_PORT`,
   `redir`. Connections from a container to the reserved address land on the
   host's listener. The `iifname` constraint is what keeps the LAN (on a
   Linux host with the same reserved address routed elsewhere) from being
   redirected.
2. `dns_redirect_rule(HOST_ADDR)`: `iifname "kiri*" udp dport 53 ip daddr
   <HOST_ADDR> redirect to :53`. A kind-node resolv.conf rewrite of
   127.0.0.11 → host.docker.internal:53 hits Kiri's embedded DNS on the
   bridge's gateway.
3. Per published **TCP** port, `dnat_rule_from("prerouting", d, Some((uplink,
   gateway)))`: `meta iif (NFT_META_IIF = 4) == <uplink>` **and** payload
   network +12 == `gateway` (the Mac's address on the NAT network), then
   `fib daddr type local` (NFTA_FIB_DREG, ADDRTYPE result, DADDR flag)
   `cmp eq 2 (RTN_LOCAL)`, and `payload daddr & 255.0.0.0 != 127.0.0.0`,
   and `tcp dport <hp>` → `immediate` to_ip/to_port regs →
   `nat dnat ip addr reg1 proto reg2`. **Only connections from the Mac's
   gateway address are DNATed.** Another VM on the NAT network, or the LAN
   routed through the Mac, cannot reach an unpublished container; and even a
   published one is reachable only from the Mac. UDP published ports are not
   DNATed in the VM (the daemon relays them on loopback instead).
   The `!= 127.0.0.0/8` clause exists so that a packet for 127.0.0.1 is
   never rewritten before routing: one arriving from the LAN would
   otherwise reach a container instead of being dropped.

### prerouting (IPv4, Linux-host mode)
Per published port, TCP **and** UDP, `dnat_rules("prerouting", d, local)`:
- `fib daddr type local` form (default): `ip daddr` any address assigned to
  this machine (`RTN_LOCAL`), 127.0.0.0/8 excluded, `tcp|udp dport <hp>` →
  dnat to `to_ip:to_port`.
- Fallback form (kernel without `nft_fib_ipv4`; the agent detects
  `ENOENT` at apply time and rebuilds once): one rule **per local address**
  (`local_addrs()`: `getifaddrs`, AF_INET, not 127), same semantics by
  enumeration. `NO_FIB4` latches, so subsequent rebuilds go straight to the
  fallback.

### output (IPv4)
VM mode: the same `redirect_rule` without the `iifname` constraint
(`ip daddr <HOST_ADDR> tcp redirect to :1026`) for the VM's own processes
and `--network host` containers. Linux-host mode: the same per-port dnat
rules as prerouting (so `localhost:8080` on the host itself reaches the
published container, as Docker does).

### forward (both families)
Policy accept, explicit rules in order:

1. `oifname != "kiri*" accept` — traffic not headed into a Kiri bridge is
   not judged; a Linux host's other forwarding stays as it was.
2. `ct state established,related accept` (NF_CT_STATE_BIT STATE=0,
   mask `1<<1 | 1<<2`, `bitwise`/`cmp neq 0`).
3. `ct status dnat accept` (IPS_DST_NAT = `1<<5`) — published ports pass.
4. One `iifname "kiriN" oifname "kiriN" accept` per bridge, whole IFNAMSIZ
   (NUL-padded 16 bytes), as written for every bridge in `MADE_BRIDGES`.
5. `drop` — everything else headed into a bridge dies.

Containers on different networks cannot reach each other (Docker's
DOCKER-ISOLATION equivalent). Same-bridge traffic never hits this hook
unless `br_netfilter` is loaded, in which case iif and oif are the same
bridge and rule 4 passes it. A published port on another network is still
reached through the host's address (rule 3, `ct status dnat`), as with
Docker. `fib daddr . iif oif` was deliberately avoided: WSL2 kernels lack
`nft_fib_ipv6` and the IPv6 table was refused there; the prefix-match
table is rebuilt whenever a bridge comes or goes.

### input (IPv4)
1. `localnet_guard()` — `iifname "kiri*" ip daddr 127.0.0.0/8
   ct state & (established|related) == 0 ct status & dnat == 0 drop`.
   With `route_localnet` set on a bridge (kube-proxy does), a container
   sending to the host's loopback would be delivered to host-local
   services (the CVE-2020-8558 hole). Replies and DNATed packets pass;
   fresh container→127.0.0.1 dies. Kiri itself never sets `route_localnet`
   (loopback connections to published ports go through the daemon's relay).
2. `host_relay_guard(HOST_RELAY_PORT)` (VM mode only) — `tcp dport 1026
   ct status & dnat == 0 drop`: the host.docker.internal listener takes
   only connections a `redir` rule DNATed. A direct dial (another VM on
   the NAT network, a container to its gateway) is refused, so a gateway
   dial never reaches the Mac; the agent additionally checks
   SO_ORIGINAL_DST for the reserved address.

### IPv6 (whole table, NAT66)
`masq6_rule` per IPv6 network: `ip6 saddr <subnet>/<prefix> oifname !=
"kiri*" masquerade` (payload network +8, 16 bytes, `bitwise` with an
arbitrary-prefix mask, `cmp eq`). Matched by source because an input
interface is not known yet at `postrouting`. The **forward** chain is the
IPv4 one built by `forward_filter_in(NFPROTO_IPV6)` (no IPv6-only
differences; no `fib` anywhere, by design). There is no DNAT6: published
ports on IPv6 are relayed by the daemon, not forwarded by the kernel. The
table exists only while at least one IPv6 network does; the last removal
installs `install_nat6(&[], &[])`, which destroys the ip6 table and does
not recreate it. `net::ipv6_forwarding` also saves/restores
`net/ipv6/conf/all/forwarding` and `accept_ra` (1→2, so a router's flag
survives re-enabling forwarding) for the interfaces it touched; the saved
state is process-local (`V6_SAVED`), not on-disk.

## Chain/rule ownership and cleanup

- The table is `kiri` (v4) and `kiri` (v6), owned solely by kiri-init;
  nothing else names them. Another engine's tables (`docker`, `libvirt`,
  `firewalld`) are never opened, listed or flushed. Within the table,
  chains are created with `NLM_F_CREATE` (EEXIST is fine — the whole table
  was just destroyed and recreated in the same batch, so chains cannot
  exist) and rules are always appended in one ordered batch.
- Forward-filter rules are the only per-bridge rules: they are rebuilt on
  every bridge add/remove (`refresh_nat()` → `install_nat_from` with the
  same NAT image and the current bridge list). Bridge removal deletes
  `kiriN` and its addresses and routes; the rebuilt table then has no
  `same_bridge(kiriN)` accept and the `oifname != "kiri*"` rule no longer
  matters for it.
- `remove_host_network()` (clean stop, Linux host) deletes all bridges
  this agent made (`MADE_BRIDGES`), destroys the ip table, destroys the
  ip6 table and restores IPv6 forwarding. In the VM, the table dies with
  the VM.
- **Crash:** a hard-killed agent leaves both tables behind on a Linux
  host. The stale DNAT entries point at container addresses that are gone;
  traffic to those published ports disappears into `dnat` and gets RST/
  dropped, and `ip kiri` lingers until removed by hand (`nft delete table
  ip kiri`) or by the next clean `remove_host_network()` on boot. No path
  currently removes it at startup. This is a known gap, and the reason
  CTRS-11 defines a transaction type with an explicit outcome instead of a
  fire-and-forget batch.

## Concurrency

Single-threaded at the granularity of the batch: one agent process, one
`Netlink` socket per operation. `NAT` (last image) and `MADE_BRIDGES` are
process-local `Mutex`es; `NO_FIB4`/`V6_SAVED` are atomics/mutex. Two
kiri-init processes on one host race on the shared `kiri` table — last
writer wins, and each writer's image is self-contained, so no half-built
state is visible, but the loser's published ports vanish. There is no
cross-process lock and no generation counter; the table is treated as
*last write wins, whole table or nothing*.

## Kernel requirements

`ip_forward` (written by `host_uplink`/`uplink`, not restored), IPv6
forwarding only while an IPv6 network exists, `NODAD` addresses, `nft`
tables with `DESTROYTABLE` (6.3+), `nft_fib_ipv4` **optional** (per-address
fallback), `nft_fib_ipv6` deliberately **unused** (prefix-match tables
instead), no `br_netfilter` requirement (if loaded, same-bridge traffic
passes rule 4).

## Known gaps, to feed the CTRS-11/13 design

1. Crash leaves stale tables on a Linux host (see *Crash* above).
2. UDP published ports are not DNATed in the VM (daemon relays them) and
   are DNATed only in Linux-host mode; IPv6 published ports are never
   DNATed by the kernel anywhere.
3. `iifname`/`oifname "kiri*"` is a 4-byte prefix match: a bridge named
   `kirifoo` that is not Kiri's would match. Bridges are named `kiri<N>`
   from Kiri's own sequence.
4. Rebuild-on-change means published ports and networks cannot be applied
   incrementally; very large port/network counts rebuild the whole table
   on every change.
5. The `output` redirect rule (VM mode) exists in the table that `/proc`
   relay clients in the VM rely on; removing it breaks `host.docker.internal`.
6. On a Linux host, `host_uplink()` writes `ip_forward=1` globally and
   never restores it — a host's forwarding posture changes silently.
