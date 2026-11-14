#!/bin/bash
# Reference fixture: published port via DNAT (docs/firewall.md, "prerouting",
# Linux-host mode) and the forward filter's ct-status-dnat accept.
#
# Topology: a "container" netns on a ctrs-like bridge (198.18.0.0/24), a
# host uplink to a "LAN" netns (203.0.113.0/24), and the reference tables
# ctrs_ref_dnat + the filter chain by hand. The LAN netns dials the host's
# uplink address:8080; the packet is prerouted into the container:80.
#
# NEEDS LINUX ROOT. Not executed on the macOS development host; CTRS-13
# runs it inside the Linux guest.
#
# Usage:  sudo conformance/fixtures/netns-dnat.sh
set -eu
command -v ip >/dev/null || { echo "needs iproute2"; exit 2; }
command -v nft >/dev/null || { echo "needs nftables"; exit 2; }

NAME=${0##*/}
LAN=kfw-dnat-lan; SRV=kfw-dnat-srv; BR=ctrs-dnat0; LANIF=kfw-dnat-l0
cleanup() {
  ip netns del "$LAN" 2>/dev/null || true
  ip netns del "$SRV" 2>/dev/null || true
  ip link del "$BR" 2>/dev/null || true
  ip link del "$LANIF" 2>/dev/null || true
  nft delete table ip ctrs_ref_dnat 2>/dev/null || true
}
trap cleanup EXIT
cleanup

ip link add "$BR" type bridge
ip addr add 198.18.0.1/24 dev "$BR"
ip link set "$BR" up
ip netns add "$SRV"
ip link add kfw-dnat-s0 type veth peer name kfw-dnat-s1
ip link set kfw-dnat-s0 master "$BR"
ip link set kfw-dnat-s0 up
ip link set kfw-dnat-s1 netns "$SRV"
ip netns exec "$SRV" ip link set lo up
ip netns exec "$SRV" ip link set kfw-dnat-s1 name eth0
ip netns exec "$SRV" ip addr add 198.18.0.2/24 dev eth0
ip netns exec "$SRV" ip link set eth0 up
ip netns exec "$SRV" ip route add default via 198.18.0.1

ip link add "$LANIF" type veth peer name kfw-dnat-l1
ip addr add 203.0.113.1/24 dev "$LANIF"
ip link set "$LANIF" up
ip netns add "$LAN"
ip link set kfw-dnat-l1 netns "$LAN"
ip netns exec "$LAN" ip link set lo up
ip netns exec "$LAN" ip link set kfw-dnat-l1 name eth0
ip netns exec "$LAN" ip addr add 203.0.113.2/24 dev eth0
ip netns exec "$LAN" ip link set eth0 up
ip netns exec "$LAN" ip route add default via 203.0.113.1

echo 1 > /proc/sys/net/ipv4/ip_forward
nft add table ip ctrs_ref_dnat
nft add chain ip ctrs_ref_dnat prerouting '{ type nat hook prerouting priority -100; policy accept; }'
nft add chain ip ctrs_ref_dnat forward '{ type filter hook forward priority 0; policy accept; }'
nft add rule ip ctrs_ref_dnat prerouting ip daddr 203.0.113.1 tcp dport 8080 dnat to 198.18.0.2:80
nft add rule ip ctrs_ref_dnat forward ct state { established, related } accept
nft add rule ip ctrs_ref_dnat forward ct status dnat accept
nft add rule ip ctrs_ref_dnat forward iifname "$BR" oifname "$BR" accept
nft add rule ip ctrs_ref_dnat forward drop

# The container serves a marker.
ip netns exec "$SRV" python3 - <<'EOF' &
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"kfw-dnat-ok\n")
    def log_message(self, *a):
        pass
HTTPServer(("198.18.0.2", 80), H).serve_forever()
EOF
SERVER=$!
for i in $(seq 1 50); do ip netns exec "$SRV" ss -ltn 2>/dev/null | grep -q ':80 ' && break; sleep 0.1; done

out=$(ip netns exec "$LAN" python3 -c 'import urllib.request; print(urllib.request.urlopen("http://203.0.113.1:8080/", timeout=3).read().decode())') || { echo "FAIL: LAN could not reach the published port"; exit 1; }
kill "$SERVER" 2>/dev/null || true; wait "$SERVER" 2>/dev/null || true
echo "LAN got: $out"
[ "$out" = "kfw-dnat-ok" ] || { echo "FAIL: wrong body"; exit 1; }
echo "PASS: $NAME"
