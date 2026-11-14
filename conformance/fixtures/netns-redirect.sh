#!/bin/bash
# Reference fixture: the host.docker.internal redirect (docs/firewall.md,
# "prerouting", redirect rule, and "input", host_relay_guard).
#
# A container on a ctrs bridge resolves host.docker.internal to the
# reserved 198.19.248.254; connections to it must land on the host's
# listener at :1026 (redirect), and only those (packets arriving on a
# non-ctrs interface must not be redirected).
#
# NEEDS LINUX ROOT. Not executed on the macOS development host; CTRS-13
# runs it inside the Linux guest.
#
# Usage:  sudo conformance/fixtures/netns-redirect.sh
set -eu
command -v ip >/dev/null || { echo "needs iproute2"; exit 2; }
command -v nft >/dev/null || { echo "needs nftables"; exit 2; }

NAME=${0##*/}
C=kfw-redir-c; X=kfw-redir-x; BR=ctrs-redir0; XBR=elsewhere0
cleanup() {
  ip netns del "$C" 2>/dev/null || true
  ip netns del "$X" 2>/dev/null || true
  ip link del "$BR" 2>/dev/null || true
  ip link del "$XBR" 2>/dev/null || true
  nft delete table ip ctrs_ref_redir 2>/dev/null || true
}
trap cleanup EXIT
cleanup

ip link add "$BR" type bridge
ip addr add 198.18.5.1/24 dev "$BR"
ip link set "$BR" up
ip link add "$XBR" type bridge
ip addr add 198.18.6.1/24 dev "$XBR"
ip link set "$XBR" up

mk_ns() { # netns bridge host-if-name addr gateway
  ip netns add "$1"
  ip link add "$3" type veth peer name "$3-p"
  ip link set "$3" master "$2"
  ip link set "$3" up
  ip link set "$3-p" netns "$1"
  ip netns exec "$1" ip link set lo up
  ip netns exec "$1" ip link set "$3-p" name eth0
  ip netns exec "$1" ip addr add "$4" dev eth0
  ip netns exec "$1" ip link set eth0 up
  ip netns exec "$1" ip route add default via "$5"
}
mk_ns "$C" "$BR" kfw-redir-c0 198.18.5.2/24 198.18.5.1
mk_ns "$X" "$XBR" kfw-redir-x0 198.18.6.2/24 198.18.6.1

# The relay listener on the host's 0.0.0.0:1026.
python3 -c 'import socket
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", 1026))
s.listen(4)
import sys
for conn, _ in iter(lambda: s.accept(), None):
    conn.sendall(b"kfw-redir-ok\n")
    conn.close()' &
SERVER=$!
sleep 0.3

nft add table ip ctrs_ref_redir
nft add chain ip ctrs_ref_redir prerouting '{ type nat hook prerouting priority -100; policy accept; }'
nft add rule ip ctrs_ref_redir prerouting iifname "ctrs*" ip daddr 198.19.248.254 tcp dport 1026 redirect to :1026

hit=$(ip netns exec "$C" python3 -c 'import socket; s=socket.socket(); s.settimeout(2); s.connect(("198.19.248.254", 1026)); print(s.recv(64).decode())' 2>&1) || { echo "FAIL: ctrs-bridge redirect not delivered: $hit"; kill $SERVER 2>/dev/null; exit 1; }
miss_rc=0
miss=$(ip netns exec "$X" python3 -c 'import socket; s=socket.socket(); s.settimeout(2); s.connect(("198.19.248.254", 1026)); print(s.recv(64).decode())' 2>&1) || miss_rc=$?
kill $SERVER 2>/dev/null || true; wait $SERVER 2>/dev/null || true
echo "ctrs bridge: $hit"
echo "non-ctrs bridge: rc=$miss_rc out=${miss:-<no response, as expected>}"
[ "$hit" = "kfw-redir-ok" ] || { echo "FAIL: redirect marker wrong"; exit 1; }
[ "$miss_rc" != 0 ] || { echo "FAIL: non-ctrs interface was redirected"; exit 1; }
echo "PASS: $NAME"
