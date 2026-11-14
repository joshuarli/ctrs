# CTRS-13 — In-VM qualification evidence (2026-11-14)

Environment: scratch ctrs daemon (pinned guest, `Image` `9366868a…`, kernel
6.18.58, nftables v1.0.9 in-guest), engine at `CTRS_SOCKET=.work/tmp/ctrs13.sock`,
data root `.work/tmp/ctrs13-data`. OrbStack untouched throughout (`junior-*`
healthy, contexts unchanged). The guest VM was rebuilt from current source
before this work (`cargo xtask guest`: initramfs
`1425843c67faf956c3d29268c082a220e8adef62ffef338da1cdcda867e3900b`,
1,534 KiB) so the kernel and agent match the tree.

## 1. The engine's live table, in the guest

`nft list table ip ctrs` (privileged container, `--network host`):

- bridge network present: postrouting `oif eth0 masquerade`; prerouting
  redirect rules (`198.19.248.254` → `:1026`, dns/53); forward filter
  (`oifname != "ctrs*"`, ct state, ct status dnat, per-bridge accept, drop);
  input guards (localnet `127/8` fresh-connection drop, relay-port drop) —
  matches `docs/firewall.md` exactly.
- published port 18081: prerouting gained two high-port DNAT rules from the
  gateway (`iif eth0 ip saddr 192.168.64.1 ip daddr 192.168.64.14 tcp dport
  61000/61001 dnat to 172.17.0.2:80`) and postrouting gained
  `iif eth0 ip saddr 192.168.64.1 oifname "ctrs*" masquerade fully-random`.
  (VM-mode published ports are TCP-only; UDP and IPv6 published ports are
  relayed by the daemon, never DNATed.)
- IPv6 network `ctrs13v6` (fd00:dead::/64) with a v6 container attached:
  `ip6 ctrs` appeared with the NAT66 postrouting rule
  (`ip6 saddr fd00:dead::/64 oifname != "ctrs*" masquerade`) and the v6
  forward filter with `ctrs1`. After container/network removal, the
  `ip6 ctrs` table is destroyed (verified) and the v4 table is back to the
  ctrs0-only state.
- **Doc correction (CTRS-13):** `published_masq_rule` lives in **postrouting**
  (verified live), not prerouting as first documented. `docs/firewall.md`
  updated; the CTRS-11 diagram line for the relay redirect was corrected the
  same way (any TCP dport, not `tcp dport 1026`).

Command shape: `docker run --privileged --network host --rm alpine:3.20 sh -c
'apk add --no-cache nftables >/dev/null 2>&1; nft list table ip ctrs'`.

## 2. Reference fixtures, in-VM

All five `conformance/fixtures/netns-*.sh` run green in the guest
(`docker run --privileged --rm -v $PWD/conformance/fixtures:/fixtures:ro
alpine:3.20 sh -c 'apk add --no-cache nftables iproute2 python3 bash >/dev/null
2>&1; bash /fixtures/netns-<name>.sh'`):

| Fixture | Result | Note |
| --- | --- | --- |
| netns-masquerade.sh | PASS | upstream saw `203.0.113.1` (host uplink), not the container |
| netns-dnat.sh | PASS | LAN → host `203.0.113.1:8080` → DNAT → `198.18.0.2:80`; needed a default route in the server ns (fixture bug, fixed) |
| netns-forward-filter.sh | PASS | same-bridge OK; cross-bridge dropped (expected timeout traceback in log, rc ≠ 0) |
| netns-localnet.sh | PASS | rewritten (below): guard match semantics via nft counters |
| netns-redirect.sh | PASS | ctrs* bridge + reserved address redirected; other bridge refused |

`netns-localnet.sh`** rewrite:** the original fixture expected a container
packet to `127.0.0.0/8` to be delivered to a host-local sink when only
`route_localnet` is set. This kernel family (6.18.58) drops 127/8-destined
packets on non-loopback interfaces unconditionally — with or without
`route_localnet`, `rp_filter` (any interface or all/default/lo), which
interface is configured, or L2 AF_PACKET injection. The injected frame is
visible on the bridge (`tcpdump`) and `fib` even resolves it `local … iif`,
yet the host never delivers it. The fixture now asserts what the guard
itself owns: an attack packet injected at L2 increments the guard's drop
counter; a same-shape non-loopback packet passes the chain; a control
proves the chain and sink work.

**Fixture bugs found in-VM (all fixed):** the bridge MAC must be read
*after* the first veth is enslaved (the bridge's MAC changes on first
port attach; the fixture injected to a stale MAC and every packet died on
the floor) — that one caused the mysterious "control packet never arrives"
debugging; the DNAT server needed its own default route; the forward-filter
and localnet fixtures had nft quoting/escaping errors (fixed `ct state { … }`
syntax and `&` expressions); the forward-filter accidentally used the wrong
argument order in its helper; the redirect fixture had the container own the
reserved address (it must only route to it).

## 3. crabtables adapter vs nft(8), same netns, expression-for-expression

The adapter (feature `crabtables`) applied the full reference policy
(postrouting uplink-masq + published-masq fully-random, prerouting redirects
and DNAT, output redirect, per-bridge forward filter, both input guards, IPv4
and IPv6 tables) and `nft -j list table` dumps were diffed against the same
table built by hand with `nft(8)`, handles stripped:

```text
first apply:  Applied
second apply: Applied   (destroy-and-recreate batch, idempotent)
EQUIVALENT (IPv4 table)
EQUIVALENT (IPv6 table)
```

Both tables byte-match after normalization (handles ignored); the IPv6
masq prefix and `fib daddr type local` cmp encoding match exactly.

**How to re-run:** `cargo test -p ctrs-init --target aarch64-unknown-linux-musl
--features crabtables -- --ignored --nocapture crabtables_matches_reference`
inside a scratch netns as root (`unshare -n linux --privileged` shell in the
VM), then dump both tables with `nft -j list table ip{,6} ctrs`. The test
destroys/recreates the `ctrs` table — never run it in the engine's netns.
The driver/normalizer used here are in the session scratch (`compare-netns.sh`,
`compare-invm.sh`, `normalize.py` under `.work/tmp/`, not committed).

**One abort-semantics observation with teeth for CTRS-12:** when one message
in the batch is rejected, the kernel reports the same errno for every
message after it (`add rule … Not supported (and 8 more errors)`), i.e. the
first failing message is the only real one. The adapter already handles this
correctly: `Batch(BatchError)` → `ApplyOutcome::RolledBack` (previous table
kept), and the failing rule (masquerade in a prerouting nat chain — the
reference policy error, now fixed) surfaced identically from `nft(8)` in the
same netns (`Could not process rule: Not supported`).

Not covered (parked, see §4 and §5): packet-level differential behavior of
the adapter (conntrack tuples, NAT mappings/replies, updates under traffic,
rejected-batch rollback observed live). The fixtures in §2 exercise the
handwritten bytes path; the adapter's behavior was compared at the kernel
entry level (netlink messages in, kernel ruleset out). Anything deeper needs
the paired CRAB-7 suite run on this kernel/nft pair first.

## 4. CRAB-7 vs the ctrs kernel profile — adapter stays experimental

`crabtables` upstream is pinned at `38646b8` (no tags; default-branch HEAD at
import). Its README (via GitHub, read at this commit) says "no deployment
profile is qualified"; its TODO CRAB-7 says the **image profile** is qualified
— nft differential suite, 102 cases, 100 passed, 2 intentional (CRAB-7-D3) —
but explicitly leaves "execution on the production kernel/nft pair if it
differs from the image's". The qualified image pair is Linux + Debian trixie
reach nft 1.1.x; **ctrs's guest kernel is 6.18.58 with nftables v1.0.9 — not
the qualified profile.** The CTRS-13 dump-equivalence check above is an
encoder/transport comparison, not a packet-level qualification, and the
paired CRAB-7 suite has not been run on this kernel/nft pair.

Therefore, per P7: **no cutover.** The handwritten `netlink.rs` path remains
production; the crabtables adapter remains behind the `crabtables` feature,
uncompiled into the guest initramfs. A future gate for cutover would be a
recorded run of the upstream paired suite on 6.18.58/nft 1.0.9, or an accepted
divergence list with written justification.

## 5. Known deltas worth carrying into CTRS-21/Gate D

- The engine's silent death (no log, no panic, no jetsam evidence; host has
  plenty of memory) struck again during this slice — the deaths correlate
  with bursts of privileged-container activity (see CTRS-21 entry in
  docs/decisions.md; five strikes total).
- The guest fixture suite found real bugs in the fixtures, not the engine;
  the engine's tables behaved as documented once the bugs were fixed.
- UDP published ports are relayed, IPv6 published ports are relayed: no
  kernel DNAT for either in the VM (daemon userland path), matching the
  `docs/firewall.md` inventory and the live dump.
- `iifname`/`oifname "ctrs*"` is a 4-byte prefix match; a bridge named
  `ctrsx` would match (acceptable; ctrs bridges are `ctrs<N>`, owned).
