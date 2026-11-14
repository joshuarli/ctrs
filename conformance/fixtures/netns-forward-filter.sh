#!/bin/bash
# Reference fixture: the forward filter (docs/firewall.md, "forward").
#
# Two ctrs-like bridges (ctrs-iso1, ctrs-iso2), one container netns on each,
# the reference `ip ctrs_ref_fwd` filter table by hand, and two packets: a
# same-bridge connection (must pass) and a cross-bridge connection (must be
# dropped). This is Docker's DOCKER-ISOLATION equivalent.
#
# NEEDS LINUX ROOT. Not executed on the macOS development host; CTRS-13
# runs it inside the Linux guest.
#
# Usage:  sudo conformance/fixtures/netns-forward-filter.sh
set -eu
command -v ip >/dev/null || { echo "needs iproute2"; exit 2; }
command -v nft >/dev/null || { echo "needs nftables"; exit 2; }

NAME=${0##*/}
A=kfw-iso-a; B=kfw-iso-b; BR1=ctrs-iso1; BR2=ctrs-iso2
cleanup() {
  ip netns del "$A" 2>/dev/null || true
  ip netns del "$B" 2>/dev/null || true
  ip link del "$BR1" 2>/dev/null || true
  ip link del "$BR2" 2>/dev/null || true
  nft delete table ip ctrs_ref_fwd 2>/dev/null || true
}
trap cleanup EXIT
cleanup

mkdir_bridge() { # name addr
  ip link add "$1" type bridge
  ip addr add "$2" dev "$1"
  ip link set "$1" up
}
veth_into() { # bridge name netns addr
  ip link add "$2-h" type veth peer name "$2-p"
  ip link set "$2-h" master "$1"
  ip link set "$2-h" up
  ip link set "$2-p" netns "$3"
  ip netns exec "$3" ip link set lo up
  ip netns exec "$3" ip link set "$2-p" name eth0
  ip netns exec "$3" ip addr add "$4" dev eth0
  ip netns exec "$3" ip link set eth0 up
}

mkdir_bridge "$BR1" 198.18.1.1/24
mkdir_bridge "$BR2" 198.18.2.1/24
ip netns add "$A"; veth_into "$BR1" kofa "$A" 198.18.1.2/24
ip netns add "$B"; veth_into "$BR2" kofb "$B" 198.18.2.2/24
ip netns exec "$A" ip route add 198.18.2.0/24 via 198.18.1.1
ip netns exec "$B" ip route add 198.18.1.0/24 via 198.18.2.1

echo 1 > /proc/sys/net/ipv4/ip_forward
nft add table ip ctrs_ref_fwd
nft add chain ip ctrs_ref_fwd forward '{ type filter hook forward priority 0; policy accept; }'
nft add rule ip ctrs_ref_fwd forward oifname != "ctrs*" accept
nft add rule ip ctrs_ref_fwd forward ct state { established, related } accept
nft add rule ip ctrs_ref_fwd forward ct status dnat accept
nft add rule ip ctrs_ref_fwd forward iifname "$BR1" oifname "$BR1" accept
nft add rule ip ctrs_ref_fwd forward iifname "$BR2" oifname "$BR2" accept
nft add rule ip ctrs_ref_fwd forward drop

serve() { # netns addr
  ip netns exec "$1" python3 -c "import http.server,sys
from http.server import BaseHTTPRequestHandler
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b'kfw-iso-ok')
    def log_message(self, *a): pass
http.server.HTTPServer((sys.argv[1], 80), H).serve_forever()" "$2"
}
serve "$A" 198.18.1.2 & SA=$!
serve "$B" 198.18.2.2 & SB=$!
for i in $(seq 1 50); do
  ip netns exec "$A" ss -ltn 2>/dev/null | grep -q ':80 ' && ip netns exec "$B" ss -ltn 2>/dev/null | grep -q ':80 ' && break
  sleep 0.1
done

same=$(ip netns exec "$A" python3 -c 'import urllib.request; print(urllib.request.urlopen("http://198.18.1.2:80/", timeout=3).read().decode())' 2>&1) || { echo "FAIL: same-bridge connection failed: $same"; kill $SA $SB 2>/dev/null; exit 1; }
cross_rc=0
cross=$(ip netns exec "$A" python3 -c 'import urllib.request; print(urllib.request.urlopen("http://198.18.2.2:80/", timeout=2).read().decode())' 2>&1) || cross_rc=$?
kill $SA $SB 2>/dev/null || true; wait 2>/dev/null || true
echo "same-bridge got: $same"
echo "cross-bridge rc=$cross_rc out=$cross"
{ [ "$same" = "kfw-iso-ok" ]; } || { echo "FAIL: same-bridge body wrong"; exit 1; }
{ [ "$cross_rc" != 0 ]; } || { echo "FAIL: cross-bridge connection was NOT dropped"; exit 1; }
echo "PASS: $NAME"
