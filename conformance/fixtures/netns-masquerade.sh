#!/bin/bash
# Reference fixture: masquerade on the uplink (docs/firewall.md, "postrouting").
#
# Builds a bridge the way ctrs-init does, an upstream network, the reference
# `ip ctrs_ref_masq` table by hand (via the nft(8) tool, not ctrs-init's wire
# encoding), and checks the *packet-level* result: the upstream server sees
# the host's uplink address, not the container's.
#
# NEEDS LINUX ROOT (network namespaces, nftables, veth). Not executed on the
# macOS development host; CTRS-13 runs it inside the Linux guest. Do not run
# on a shared host without care: it adds and removes network namespaces and
# one nftables table named ctrs_ref_masq.
#
# Usage:  sudo conformance/fixtures/netns-masquerade.sh
set -eu
command -v ip >/dev/null || { echo "needs iproute2"; exit 2; }
command -v nft >/dev/null || { echo "needs nftables"; exit 2; }

NAME=${0##*/}
CLIENT=kfw-masq-c; UP=kfw-masq-up; BR=ctrs-masq0; UPIF=kfw-masq-u0
cleanup() {
  ip netns del "$CLIENT" 2>/dev/null || true
  ip netns del "$UP" 2>/dev/null || true
  ip link del "$BR" 2>/dev/null || true
  ip link del "$UPIF" 2>/dev/null || true
  nft delete table ip ctrs_ref_masq 2>/dev/null || true
  rm -f /tmp/kfw-masq-peer
}
trap cleanup EXIT
cleanup

# The client network (a ctrs bridge), and an upstream namespace.
ip link add "$BR" type bridge
ip addr add 198.18.0.1/24 dev "$BR"
ip link set "$BR" up
ip netns add "$CLIENT"
ip link add kfw-masq-c0 type veth peer name kfw-masq-c1
ip link set kfw-masq-c0 master "$BR"
ip link set kfw-masq-c0 up
ip link set kfw-masq-c1 netns "$CLIENT"
ip netns exec "$CLIENT" ip link set lo up
ip netns exec "$CLIENT" ip link set kfw-masq-c1 name eth0
ip netns exec "$CLIENT" ip addr add 198.18.0.2/24 dev eth0
ip netns exec "$CLIENT" ip link set eth0 up
ip netns exec "$CLIENT" ip route add default via 198.18.0.1
ip netns add "$UP"
ip link add "$UPIF" type veth peer name kfw-masq-u1
ip addr add 203.0.113.1/24 dev "$UPIF"
ip link set "$UPIF" up
ip link set kfw-masq-u1 netns "$UP"
ip netns exec "$UP" ip link set lo up
ip netns exec "$UP" ip link set kfw-masq-u1 name eth0
ip netns exec "$UP" ip addr add 203.0.113.2/24 dev eth0
ip netns exec "$UP" ip link set eth0 up
echo 1 > /proc/sys/net/ipv4/ip_forward

nft add table ip ctrs_ref_masq
nft add chain ip ctrs_ref_masq postrouting '{ type nat hook postrouting priority 100; policy accept; }'
nft add rule ip ctrs_ref_masq postrouting oifname "$UPIF" masquerade

# The upstream server logs the peer it sees.
ip netns exec "$UP" python3 - <<'EOF' &
import socket, sys
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("203.0.113.2", 8080))
s.listen(1)
c, peer = s.accept()
with open("/tmp/kfw-masq-peer", "w") as f:
    f.write(peer[0])
c.sendall(b"ok\n")
EOF
SERVER=$!
for i in $(seq 1 50); do ip netns exec "$UP" ss -ltn 2>/dev/null | grep -q 8080 && break; sleep 0.1; done

out=$(ip netns exec "$CLIENT" python3 -c 'import socket; s=socket.socket(); s.settimeout(3); s.connect(("203.0.113.2", 8080)); print(s.recv(8).decode())') || { echo "FAIL: client could not reach upstream"; exit 1; }
kill "$SERVER" 2>/dev/null || true; wait "$SERVER" 2>/dev/null || true
peer=$(cat /tmp/kfw-masq-peer)
echo "client got: $out ; upstream saw peer: $peer"
[ "$out" = "ok" ] || { echo "FAIL: bad response"; exit 1; }
[ "$peer" = "203.0.113.1" ] || { echo "FAIL: not masqueraded (upstream saw $peer, want 203.0.113.1)"; exit 1; }
echo "PASS: $NAME"
