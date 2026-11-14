# Firewall reference fixtures

Packet-level reference checks for the nftables configuration that
`kiri-init` maintains by hand (`docs/firewall.md`). They express the
reference semantics with the `nft(8)` tool — not kiri-init's wire encoding —
and verify them on real packets inside network namespaces. They are the
oracle for CTRS-13 (in-VM qualification of the guest kernel) and for the
firewall acceptance gate; they do not exercise any Rust code.

| Fixture | What it checks |
| --- | --- |
| `netns-masquerade.sh` | `postrouting`: traffic from a container netns to upstream leaves with the host's uplink address |
| `netns-dnat.sh` | `prerouting` DNAT of a published port (+ `ct status dnat` pass-through in `forward`) reaches the container |
| `netns-forward-filter.sh` | `forward`: same-bridge traffic passes, cross-bridge traffic is dropped |
| `netns-localnet.sh` | `input`: container packets to 127.0.0.0/8 are dropped even with `route_localnet` (CVE-2020-8558) |
| `netns-redirect.sh` | `prerouting` redirect: only packets from a `kiri*` bridge to the reserved address reach the host listener |

Every fixture needs **Linux root** (namespaces, veth, nftables). They are
not executed on the macOS development host. They were run in the Linux
guest at CTRS-13 and pass there (see `docs/evidence/crabtables.md`); they
are the Gate D oracle and must stay green there. Each fixture is
self-contained, cleans up with a trap, and exits non-zero on failure.
Nothing here is run in ordinary CI.

`netns-localnet.sh` asserts the guard's match semantics with nft counters
around an L2-injected attack packet: on kernel 6.18.58 packets with
destination 127.0.0.0/8 are dropped on non-loopback interfaces regardless
of `route_localnet`, so the fixture does not claim an end-to-end delivery
the kernel refuses to perform.
