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
# mutation and removes only the resources it recorded, on success, failure
# and INT/TERM alike. Failure logs (daemon container logs, inspect data) are
# preserved under .work/tmp/qemu-accel/.
set -u

D=${D:-docker}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
BIN=${BIN:-$ROOT/target/linux-x86_64/release}
PREFIX=${PREFIX:-ctrs-lh-$$-$RANDOM}
SCRATCH=$ROOT/.work/tmp/qemu-accel
WORK=""
FAIL=0
PASS=0
CONTAINER=""
VOL_STATE=""
VOL_STORE=""
PORTS=()

usage() { echo "usage: BIN=<dir-with-amd64-ctrs> [PREFIX=name] [D=docker] bash tests/linux-host.sh" >&2; exit 2; }
MINE=0
die() {
  # Before the prefix is proven ours (MINE=0): the EXIT trap is not installed
  # and the requested name may belong to a stranger, so nothing here removes
  # it or reads its logs; our scratch goes away. After the prefix is proven
  # ours (MINE=1): the EXIT trap owns cleanup, including failure logs.
  if [ "$MINE" = 0 ]; then
    [ -n "$WORK" ] && rm -rf "$WORK"
    CONTAINER=""
    VOL_STATE=""
    VOL_STORE=""
  fi
  echo "linux-host: $*" >&2
  exit 2
}

[[ "$PREFIX" =~ ^[a-z0-9][a-z0-9_.-]{0,40}$ ]] || usage
command -v "$D" >/dev/null 2>&1 || die "docker CLI '$D' not found"

# --- Endpoint: refuse anything but a local unix socket serving linux/amd64.
if [ -n "${DOCKER_HOST:-}" ]; then
  CLIENT_HOST=$DOCKER_HOST
else
  CTXCTX=$($D context show 2>&1) || die "docker context show failed: $CTXCTX"
  CLIENT_HOST=$($D context inspect "$CTXCTX" --format '{{.Endpoints.docker.Host}}' 2>&1) || die "docker context inspect failed: $CLIENT_HOST"
fi
case "$CLIENT_HOST" in
  unix://*) ;;
  *) die "refusing to use a non-unix Docker endpoint ($CLIENT_HOST): this harness never talks to remote engines" ;;
esac
SERVER=$($D version --format '{{.Server.Os}}/{{.Server.Arch}}' 2>&1) || die "docker server not answering: $SERVER"
[ "$SERVER" = "linux/amd64" ] || die "docker server is $SERVER, want linux/amd64"
DOCKER_VERSION=$($D version --format '{{.Server.Version}}' 2>&1)

# --- Inputs: both executables must be AMD64 ELF (e_machine 0x3e).
BIN=$(cd "$BIN" 2>/dev/null && pwd) || die "BIN directory '$BIN' not found"
for b in ctrs ctrs-init; do
  [ -x "$BIN/$b" ] || die "$BIN/$b missing or not executable"
  magic=$(od -A n -t x1 -N 4 "$BIN/$b" | tr -d ' \n')
  [ "$magic" = "7f454c46" ] || die "$BIN/$b is not an ELF binary"
  class=$(od -A n -t x1 -j 4 -N 1 "$BIN/$b" | tr -d ' \n')
  [ "$class" = "02" ] || die "$BIN/$b is not a 64-bit ELF binary"
  machine=$(od -A n -t x1 -j 18 -N 2 "$BIN/$b" | tr -d ' \n')
  [ "$machine" = "3e00" ] || die "$BIN/$b is not an x86-64 binary (e_machine 0x$machine)"
done

# --- Port allocation: probe from a random base, keep three free loopback ports.
port_free() { ! (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
alloc_port() {
  local tries=0 p
  while [ $tries -lt 50 ]; do
    p=$((20000 + RANDOM % 20000))
    if port_free "$p" && [[ ! " ${PORTS[*]-} " == *" $p "* ]]; then
      PORTS+=("$p"); echo "$p"; return 0
    fi
    tries=$((tries + 1))
  done
  return 1
}
PORT_HTTP=$(alloc_port) || die "no free port for the HTTP check"
PORT_HTTP6=$(alloc_port) || die "no free port for the IPv6 HTTP check"
PORT_UDP=$(alloc_port) || die "no free port for the UDP check"

CONTAINER=$PREFIX
VOL_STATE="${PREFIX}-state"
VOL_STORE="${PREFIX}-store"

# --- Isolation: isolated client config, nothing of the user's reused.
WORK=$SCRATCH/linux-host-$PREFIX
if [ -e "$WORK" ]; then die "scratch $WORK exists: remove it or pick another PREFIX"; fi
mkdir -p "$WORK"
printf '{"auths":{}}\n' > "$WORK/config.json"
export DOCKER_CONFIG="$WORK"
unset DOCKER_CONTEXT

# --- Validate the prefix is free before any mutation.
if $D ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then die "container $CONTAINER already exists: refusing to touch it (set PREFIX to a fresh name)"; fi
for v in "$VOL_STATE" "$VOL_STORE"; do
  if $D volume inspect "$v" >/dev/null 2>&1; then die "volume $v already exists: refusing to touch it (set PREFIX to a fresh name)"; fi
done
if ! $D image inspect alpine:3.22 >/dev/null 2>&1; then
  echo "pulling alpine:3.22 (harness tooling image)"
  $D pull -q alpine:3.22 >/dev/null || die "alpine:3.22 not available"
fi

# --- Recorded-resource cleanup: removes only what this run recorded.
RC_FLAG=""
on_int() { RC_FLAG=130; exit 130; }
on_term() { RC_FLAG=143; exit 143; }
cleanup() {
  local rc=$?
  if [ -n "$RC_FLAG" ]; then rc=$RC_FLAG; fi
  local preserved=""
  if [ "$FAIL" != 0 ] || [ $rc -ne 0 ]; then
    if [ -n "$CONTAINER" ] && $D inspect "$CONTAINER" >/dev/null 2>&1; then
      $D logs "$CONTAINER" > "$WORK/daemon.log" 2>&1 || true
      $D inspect "$CONTAINER" > "$WORK/inspect.json" 2>&1 || true
      preserved="$WORK"
    fi
  fi
  [ -n "$CONTAINER" ] && $D rm -f "$CONTAINER" >/dev/null 2>&1 || true
  [ -n "$VOL_STATE" ] && $D volume rm "$VOL_STATE" >/dev/null 2>&1 || true
  [ -n "$VOL_STORE" ] && $D volume rm "$VOL_STORE" >/dev/null 2>&1 || true
  if [ -n "$preserved" ]; then
    echo "failure logs preserved in $preserved"
  else
    rm -rf "$WORK"
  fi
  exit $rc
}
MINE=1
trap cleanup EXIT
trap on_int INT
trap on_term TERM

echo "linux-host: prefix $PREFIX, ports $PORT_HTTP/$PORT_HTTP6/$PORT_UDP, BIN $BIN, docker $DOCKER_VERSION"
$D run -d --name "$CONTAINER" --privileged --tmpfs /run -v "$VOL_STATE:/var/lib/ctrs" -e CTRS_DATA_DIR=/data -v "$VOL_STORE:/data" \
  -v "$BIN:/opt/ctrs:ro" alpine:3.22 sh -c 'apk add -q docker-cli curl >/dev/null 2>&1; exec /opt/ctrs/ctrs daemon' >/dev/null || die "failed to start the harness container"
for _ in $(seq 60); do $D exec "$CONTAINER" sh -c 'DOCKER_HOST=unix:///root/.local/share/ctrs/run/docker.sock docker version' >/dev/null 2>&1 && break; sleep 1; done

SOCK=unix:///root/.local/share/ctrs/run/docker.sock
t() {
  local name=$1 want=$2; shift 2
  local got
  got=$($D exec "$CONTAINER" sh -c "export DOCKER_HOST=$SOCK; $*" 2>&1 | tr -d '\r')
  if [[ "$got" == *"$want"* ]]; then PASS=$((PASS + 1)); else FAIL=$((FAIL + 1)); printf '  FAIL %s\n    want: %s\n    got:  %s\n' "$name" "$want" "$(echo "$got" | head -3)"; fi
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
