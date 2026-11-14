#!/bin/bash
# ctrs on a Linux host: runs the Linux build (cargo xtask linux --arch amd64)
# as the host engine inside a privileged container on the current Docker
# engine (ctrs works), then drives it with the docker CLI from inside. No VM
# is involved: containers run on that Linux kernel directly.
#
#   BIN=<dir with AMD64 ctrs and ctrs-init> bash tests/linux-host.sh
#
# BIN defaults to target/linux-x86_64/release (`cargo xtask linux --arch
# amd64`). Both executables are validated as AMD64 before anything is
# created. PREFIX names every resource the run makes (container, two volumes,
# ports); it defaults to a unique per-run name. The wrapper validates the
# Docker endpoint (a local unix socket serving linux/amd64) before any
# mutation; cleanup removes only what this run recorded, on success,
# failure, INT/TERM alike. Failure logs (daemon container logs, inspect
# data) are preserved under .work/tmp/qemu-accel/.
set -u

D=${D:-docker}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
BIN=${BIN:-$ROOT/target/linux-x86_64/release}
PREFIX=${PREFIX:-ctrs-lh-$$-$RANDOM}
SCRATCH=$ROOT/.work/tmp/qemu-accel
mkdir -p "$SCRATCH"
FAIL=0
PASS=0
ISO_PRESERVE=0

[[ "$PREFIX" =~ ^[a-z0-9][a-z0-9_.-]{0,40}$ ]] || { echo "usage: BIN=<dir-with-amd64-ctrs> [PREFIX=name] [D=docker] bash tests/linux-host.sh" >&2; exit 2; }

source "$ROOT/tests/lib/isolated-env.sh"

iso_endpoint_check
iso_bin_check
iso_alloc_ports 3
PORT_HTTP=${ISO_PORTS[0]}
PORT_HTTP6=${ISO_PORTS[1]}
PORT_UDP=${ISO_PORTS[2]}
iso_prepare "$PREFIX"
iso_trap_install

echo "linux-host: prefix $PREFIX, ports $PORT_HTTP/$PORT_HTTP6/$PORT_UDP, BIN $BIN, docker $ISO_DOCKER_VERSION"
iso_start || { echo "linux-host: the engine did not answer in 60 s" >&2; ISO_PRESERVE=1; exit 1; }

SOCK=unix:///root/.local/share/ctrs/run/docker.sock
t() {
  local name=$1 want=$2; shift 2
  local got
  got=$($D exec "$CONTAINER" sh -c "export DOCKER_HOST=$SOCK; $*" 2>&1 | tr -d '\r')
  if [[ "$got" == *"$want"* ]]; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); ISO_PRESERVE=1; printf '  FAIL %s\n    want: %s\n    got:  %s\n' "$name" "$want" "$(echo "$got" | head -3)"; fi
}
t server-os "linux" "docker version --format '{{.Server.Os}}'"
t run "3." "docker run --rm alpine cat /etc/alpine-release"
t home "/root" "docker run --rm alpine sh -c 'echo \$HOME'"
t internet "Example Domain" "docker run --rm alpine wget -qO- -T 10 http://example.com"
t port "Welcome to nginx" "docker run -d --name web -p $PORT_HTTP:80 nginx:alpine >/dev/null; for i in \$(seq 30); do curl -s localhost:$PORT_HTTP && break; sleep 0.3; done"
t exec "nginx version" "docker exec web nginx -v"
# A container and an exec each lead their own session, so killpg from inside
# never reaches the daemon (#191).
t session-own "SID=1" "docker run --rm alpine sh -c 'echo SID=\$(cut -d\" \" -f6 /proc/1/stat)'"
t exec-session-own "own" "docker exec web sh -c 's=\$(cut -d\" \" -f6 /proc/\$\$/stat); [ \"\$s\" = \"\$\$\" ] && echo own || echo \"session \$s\"'"
t cp "copied" "echo copied > /tmp/x && docker cp /tmp/x web:/tmp/x && docker exec web cat /tmp/x"
t stats "web" "docker stats --no-stream --format '{{.Name}}'"
t network-dns "PONG" "docker network create lhn >/dev/null 2>&1; docker run -d --name db --network lhn redis:7-alpine >/dev/null; sleep 1; docker run --rm --network lhn redis:7-alpine redis-cli -h db ping"
t bind-host-path "3." "docker run --rm -v /etc:/h:ro alpine cat /h/alpine-release"
t volume "kept" "docker run --rm -v lhv:/d alpine sh -c 'echo kept > /d/f' && docker run --rm -v lhv:/d alpine cat /d/f"
t memory-limit "67108864" "docker run --rm --memory 64m alpine cat /sys/fs/cgroup/memory.max"
t seccomp "Seccomp:	2" "docker run --rm alpine grep Seccomp: /proc/self/status"
t udp "10.9.8.7" "docker run -d --name dns -p $PORT_UDP:53/udp alpine sh -c 'apk add -q dnsmasq >/dev/null 2>&1; dnsmasq -k --address=/ctrs.test/10.9.8.7' >/dev/null; for i in \$(seq 40); do out=\$(nslookup -port=$PORT_UDP ctrs.test 127.0.0.1 2>/dev/null) && break; sleep 0.5; done; echo \"\$out\" | grep -o 10.9.8.7"
t ipv6-network "true" "docker network create --ipv6 --subnet fd00:4c:1::/64 lh6 >/dev/null && docker network inspect lh6 -f '{{.EnableIPv6}}'"
t ipv6-ping "1 packets received" "docker run -d --name v6a --network lh6 nginx:alpine >/dev/null; docker run --rm --network lh6 alpine ping -6 -c 1 -W 2 v6a"
t ipv6-wget "Welcome to nginx" "docker run --rm --network lh6 alpine wget -qO- -T 5 'http://[fd00:4c:1::2]'"
t ipv6-host-nat "masquerade" "apk add -q nftables >/dev/null 2>&1; nft list table ip6 ctrs"
t ipv6-port "Welcome to nginx" "docker run -d --name web6 -p $PORT_HTTP6:80 nginx:alpine >/dev/null; for i in \$(seq 30); do curl -sg 'http://[::1]:$PORT_HTTP6' && break; sleep 0.3; done"
t ipv6-cleanup "gone" "docker rm -f v6a web6 >/dev/null; docker network rm lh6 >/dev/null; for i in \$(seq 20); do nft list table ip6 ctrs >/dev/null 2>&1 || { echo gone; break; }; sleep 0.1; done"
t ipv6-forwarding-restored "0" "cat /proc/sys/net/ipv6/conf/all/forwarding"
# A build's --add-host host-gateway is the bridge gateway, as for docker run (not the Mac VM's 198.19.248.254).
t build-host-gateway "GW-OK" "gw=\$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}'); mkdir -p /bhg && printf 'FROM alpine:3.21\\nRUN grep -w hgw /etc/hosts\\n' > /bhg/Dockerfile && DOCKER_BUILDKIT=0 docker build --no-cache --add-host hgw:host-gateway /bhg 2>&1 | grep -q \"\$gw\" && echo GW-OK"
# A privileged container must not touch the host's /dev. The kernel has one
# devtmpfs, so mount it, put ptmx back as the device it should be, run a
# privileged container and look again: once, ptmx became a link into the
# host's /dev/pts and no user on the machine could open a terminal.
t privileged-host-ptmx "character special file" "mkdir -p /hostdev && mount -t devtmpfs none /hostdev && { [ -c /hostdev/ptmx ] || { rm -f /hostdev/ptmx && mknod -m 666 /hostdev/ptmx c 5 2 && chgrp 5 /hostdev/ptmx; }; } && docker run --rm --privileged alpine true && stat -c %F /hostdev/ptmx; umount /hostdev"
t privileged-devices "DEVS-OK" "docker run --rm --privileged alpine sh -c 'test -c /dev/kmsg && test -c /dev/null && test -L /dev/ptmx && test -c /dev/pts/ptmx && echo DEVS-OK'"
t privileged-tty "/dev/pts/0" "docker run --rm -t --privileged alpine tty"
t cleanup "web" "docker rm -f web db dns"
echo "$PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
