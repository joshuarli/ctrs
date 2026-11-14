#!/bin/bash
# Reference fixture: the localnet guard (docs/firewall.md, "input",
# localnet_guard). CVE-2020-8558 class defense-in-depth: a packet from a
# container arriving on a ctrs bridge with destination 127.0.0.0/8 must not
# be accepted by host-local services.
#
# What this kernel (6.18.58) does: packets with destination 127.0.0.0/8
# arriving on any non-loopback interface are dropped as martians
# regardless of route_localnet, rp_filter or which interface is configured;
# the attack packet cannot be delivered here anyway. The fixture therefore
# asserts what the guard itself owns: the drop rule *matches* the
# injected attack packet (counter fires), and a same-shape packet to a
# non-loopback destination passes the same chain.
#
# NEEDS LINUX ROOT and AF_PACKET. Not executed on the macOS development
# host; CTRS-13 runs it inside the Linux guest.
#
# Usage:  sudo conformance/fixtures/netns-localnet.sh
set -eu
command -v ip >/dev/null || { echo "needs iproute2"; exit 2; }
command -v nft >/dev/null || { echo "needs nftables"; exit 2; }

NAME=${0##*/}
C=kfw-ln-c; BR=ctrs-ln0
cleanup() {
  ip netns del "$C" 2>/dev/null || true
  ip link del "$BR" 2>/dev/null || true
  nft delete table ip ctrs_ref_ln 2>/dev/null || true
  rm -f /tmp/kfw-ln-got
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
BR_MAC=$(cat "/sys/class/net/$BR/address")
C_MAC=$(ip netns exec "$C" cat /sys/class/net/eth0/address)

inject() {
  ip netns exec "$C" python3 - "$BR_MAC" "$C_MAC" "$1" <<'EOF'
import socket, struct, sys
def csum(data):
    if len(data) % 2:
        data += b"\0"
    s = sum(struct.unpack("!%dH" % (len(data) // 2), data))
    s = (s >> 16) + (s & 0xffff)
    s += s >> 16
    return ~s & 0xffff
dst_mac = bytes.fromhex(sys.argv[1].replace(":", ""))
src_mac = bytes.fromhex(sys.argv[2].replace(":", ""))
src, dst = socket.inet_aton("198.18.9.2"), socket.inet_aton(sys.argv[3])
payload = b"kfw-ln-probe"
udp_len = 8 + len(payload)
ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + udp_len, 0, 0, 64, 17, 0, src, dst)
ip = ip[:10] + struct.pack("!H", csum(ip)) + ip[12:]
frame = struct.pack("!6s6sH", dst_mac, src_mac, 0x0800) + ip + struct.pack("!HHHH", 12345, 8080, udp_len, 0) + payload
s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0800))
s.bind(("eth0", 0))
s.send(frame)
EOF
}

host_sink() { # addr
  python3 - "$1" <<'EOF' &
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind((sys.argv[1], 8080))
s.settimeout(3)
try:
    data, _ = s.recvfrom(64)
    with open("/tmp/kfw-ln-got", "wb") as f:
        f.write(data)
except socket.timeout:
    sys.exit(3)
EOF
}

# Control: a same-shape packet to the bridge's own address is received.
host_sink 198.18.9.1; SERVER=$!
sleep 0.3
inject 198.18.9.1
wait "$SERVER" || true
[ -f /tmp/kfw-ln-got ] || { echo "FAIL: control packet did not arrive; the fixture cannot measure the guard"; exit 1; }
echo "control: packet to 198.18.9.1 delivered"
rm -f /tmp/kfw-ln-got

# The guard: fresh packets from a ctrs bridge to 127/8 are dropped.
nft add table ip ctrs_ref_ln
nft add chain ip ctrs_ref_ln input '{ type filter hook input priority 0; policy accept; }'
nft add rule ip ctrs_ref_ln input iifname "ctrs*" ip daddr 127.0.0.0/8 'ct state & ( established | related ) == 0' 'ct status & dnat == 0' counter drop

# A same-shape packet to a non-loopback address still passes the chain.
nft add rule ip ctrs_ref_ln input iifname "ctrs*" counter accept
host_sink 198.18.9.1; SERVER=$!
sleep 0.2
inject 198.18.9.1
wait "$SERVER" || true
[ -f /tmp/kfw-ln-got ] || { echo "FAIL: packet to 198.18.9.1 was stopped by the guard chain"; exit 1; }
echo "guard passes non-loopback: delivered"
rm -f /tmp/kfw-ln-got

# The attack packet: the sink hears nothing and the drop counter fires.
host_sink 127.0.0.1; SERVER=$!
sleep 0.2
inject 127.0.0.1
set +e
wait "$SERVER"
guard_rc=$?
set -e
drops=$(nft list chain ip ctrs_ref_ln input | awk '/ct status.*counter/ && /drop/ { for (i=1;i<NF;i++) if ($i=="counter" && $(i+1)=="packets") print $(i+2) }')
echo "attack packet: sink rc=$guard_rc; guard drop counter=$drops"
[ ! -f /tmp/kfw-ln-got ] || { echo "FAIL: packet to 127.0.0.1 was delivered"; exit 1; }
[ "${drops:-0}" -ge 1 ] || { echo "FAIL: the guard drop rule did not match the attack packet"; exit 1; }
echo "PASS: $NAME"
