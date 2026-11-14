#!/bin/bash
# Reference fixture: the localnet guard (docs/firewall.md, "input",
# localnet_guard). CVE-2020-8558 class: with `route_localnet` set on a
# bridge, a container's packet to 127.0.0.1 is delivered to host-local
# services. The guard drops fresh packets from a Kiri bridge to
# 127.0.0.0/8.
#
# Two measurements: with the reference table in place the connection must
# fail; with it removed it must succeed (proving the guard is what stopped
# it). route_localnet is set on the bridge in both cases, as kube-proxy
# does.
#
# NEEDS LINUX ROOT. Not executed on the macOS development host; CTRS-13
# runs it inside the Linux guest.
#
# Usage:  sudo conformance/fixtures/netns-localnet.sh
set -eu
command -v ip >/dev/null || { echo "needs iproute2"; exit 2; }
command -v nft >/dev/null || { echo "needs nftables"; exit 2; }

NAME=${0##*/}
C=kfw-ln-c; BR=kiri-ln0
cleanup() {
  ip netns del "$C" 2>/dev/null || true
  ip link del "$BR" 2>/dev/null || true
  nft delete table ip kiri_ref_ln 2>/dev/null || true
}
trap cleanup EXIT
cleanup

ip link add "$BR" type bridge
ip addr add 198.18.9.1/24 dev "$BR"
ip link set "$BR" up
echo 1 > "/proc/sys/net/ipv4/conf/$BR/route_localnet"
ip netns add "$C"
ip link add kfw-ln-c0 type veth peer name kfw-ln-c1
ip link set kfw-ln-c0 master "$BR"
ip link set kfw-ln-c0 up
ip link set kfw-ln-c1 netns "$C"
ip netns exec "$C" ip link set lo up
ip netns exec "$C" ip link set kfw-ln-c1 name eth0
ip netns exec "$C" ip addr add 198.18.9.2/24 dev eth0
ip netns exec "$C" ip link set eth0 up

# Host-local secret on 127.0.0.1:8080.
python3 -c 'import http.server
from http.server import BaseHTTPRequestHandler
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"kfw-ln-secret\n")
    def log_message(self, *a): pass
http.server.HTTPServer(("127.0.0.1", 8080), H).serve_forever()' &
SERVER=$!
sleep 0.3

try_it() { ip netns exec "$C" python3 -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/", timeout=2).read().decode())' 2>&1; }

echo "without guard: $(try_it || true)"
[ "$(try_it)" = "kfw-ln-secret" ] || { echo "FAIL: route_localnet alone did not deliver to loopback; fixture not measuring what it claims"; kill $SERVER 2>/dev/null; exit 1; }

nft add table ip kiri_ref_ln
nft add chain ip kiri_ref_ln input '{ type filter hook input priority 0; policy accept; }'
nft add rule ip kiri_ref_ln input iifname "kiri*" ip daddr 127.0.0.0/8 'ct state & ( established | related ) == 0' 'ct status & dnat == 0' drop

set +e
out=$(try_it)
rc=$?
set -e
kill $SERVER 2>/dev/null || true; wait $SERVER 2>/dev/null || true
echo "with guard: rc=$rc out=$out"
[ "$rc" != 0 ] || { echo "FAIL: the guard did not stop container->127.0.0.1"; exit 1; }
echo "PASS: $NAME"
