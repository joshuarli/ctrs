#!/bin/bash
# End-to-end tests: drives a running engine through the real docker CLI and
# checks every result. The engine is expected at $CTRS_SOCKET (a scratch
# socket; never a docker context, never OrbStack). How to get one:
#
#   conformance/smoke.sh          # boots the VM with scratch roots (recommended)
#   CTRS_DATA_DIR=... CTRS_SOCKET=... target/release/ctrs daemon &
#
# Usage:
#   CTRS_SOCKET=.work/tmp/smoke.sock tests/e2e.sh
#   SOAK=500 tests/e2e.sh   # plus a leak soak of 500 container runs
#
# Exits non-zero if any check fails.

set -u
SOCK=${CTRS_SOCKET:?set CTRS_SOCKET to the engine socket}
export DOCKER_HOST="unix://$SOCK"
unset DOCKER_CONTEXT
D=docker
PASS=0
FAIL=0
SKIP=0
FAILED=()

# t NAME EXPECTED COMMAND... : passes when the command's output (stdout+stderr,
# trimmed) contains EXPECTED.
t() {
  local name=$1 want=$2
  shift 2
  local got
  got=$(perl -e 'alarm 60; exec @ARGV' "$@" 2>&1 | tr -d '\r')
  if [[ "$got" == *"$want"* ]]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    FAILED+=("$name")
    printf '  FAIL %s\n    want: %s\n    got:  %s\n' "$name" "$want" "$(echo "$got" | head -5)"
  fi
}

# code NAME EXPECTED_EXIT COMMAND... : passes when the exit code matches.
code() {
  local name=$1 want=$2
  shift 2
  perl -e 'alarm 60; exec @ARGV' "$@" >/dev/null 2>&1
  local got=$?
  if [[ $got == "$want" ]]; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
    FAILED+=("$name")
    printf '  FAIL %s: exit %s, want %s\n' "$name" "$got" "$want"
  fi
}

section() { printf '\n== %s\n' "$1"; }
skip() { SKIP=$((SKIP + 1)); printf '  SKIP %s (%s)\n' "$1" "$2"; }
# Waits up to 10 s for a URL to answer, as you would for any freshly started server.
ready() { for _ in $(seq 50); do curl -s -m 1 -o /dev/null "$1" && return 0; sleep 0.2; done; return 1; }
# Waits until the nginx in container $1 serves (it starts a moment after run -d returns).
nginx_up() { for _ in $(seq 50); do $D exec "$1" wget -qO- -T 1 http://127.0.0.1/ >/dev/null 2>&1 && return 0; sleep 0.2; done; return 1; }
# The containers and networks that were here before the suite started are
# the user's: cleanup removes only what the suite made.
KEEP_C=" $($D ps -aq --no-trunc | tr '\n' ' ') "
KEEP_N=" $($D network ls -q --no-trunc --filter type=custom 2>/dev/null | tr '\n' ' ') "
cleanup() {
  for c in $($D ps -aq --no-trunc); do [[ "$KEEP_C" == *" $c "* ]] || $D rm -f "$c" >/dev/null 2>&1; done
  for n in $($D network ls -q --no-trunc --filter type=custom 2>/dev/null); do [[ "$KEEP_N" == *" $n "* ]] || $D network rm "$n" >/dev/null 2>&1; done
}

cleanup

section "engine"
t version-server "Ctrs" $D version
t version-api "1.47" $D version --format '{{.Server.APIVersion}}'
t info-os "Ctrs" $D info --format '{{.OperatingSystem}}'
t info-cgroup "2" $D info --format '{{.CgroupVersion}}'

section "images"
t pull-alpine "alpine:latest" $D pull alpine:latest
t pull-busybox "busybox" $D pull busybox
t pull-tag "3.21" $D pull alpine:3.21
t images-list "alpine" $D images
t image-inspect-arch "arm64" $D image inspect -f '{{.Architecture}}' alpine
t image-inspect-cmd "/bin/sh" $D image inspect -f '{{.Config.Cmd}}' alpine
code pull-missing 1 $D pull ctrs-does-not-exist/nope:none
t rmi "Untagged" $D rmi alpine:3.21
code rmi-missing 1 $D rmi alpine:3.21

section "run: output and exit codes"
t echo "hello" $D run --rm alpine echo hello
t args "a b c" $D run --rm alpine echo a b c
code exit-0 0 $D run --rm alpine true
code exit-1 1 $D run --rm alpine false
code exit-42 42 $D run --rm alpine sh -c 'exit 42'
code exit-127-missing 127 $D run --rm alpine no-such-binary
t missing-msg "executable file not found" $D run --rm alpine no-such-binary
t stderr "to-err" $D run --rm alpine sh -c 'echo to-err >&2'
t big-output "100000" bash -c "$D run --rm alpine sh -c 'seq 1 100000' | tail -1"
t output-bytes "5488895" bash -c "$D run --rm alpine sh -c 'seq 1 800000' | wc -c | tr -d ' '"
t killed-by-signal "137" $D run --rm alpine sh -c 'sh -c "kill -9 \$\$"; echo $?'

section "run: config"
t env "bar" $D run --rm -e FOO=bar alpine sh -c 'echo $FOO'
t env-image "PATH=/usr/local/sbin" $D run --rm alpine env
t workdir "/tmp" $D run --rm -w /tmp alpine pwd
t workdir-created "/made/here" $D run --rm -w /made/here alpine pwd
t user-numeric "uid=1000" $D run --rm -u 1000 alpine id
t user-name "uid=70(postgres)" $D run --rm -u postgres postgres:17-alpine id
t user-group "gid=0(root)" $D run --rm -u 1000:0 alpine id
t entrypoint "x" $D run --rm --entrypoint echo alpine x
t entrypoint-image "nginx version" $D run --rm nginx:alpine nginx -v
t hostname-is-id "" $D run --rm alpine hostname
t hostname-file "" $D run --rm alpine cat /etc/hostname
t pid1 "1" $D run --rm alpine sh -c 'echo $$'
t proc "PID" $D run --rm alpine ps
t dev-null "ok" $D run --rm alpine sh -c 'echo x > /dev/null && echo ok'
t dev-null-nonroot "ok" $D run --rm -u 1000 alpine sh -c 'echo x > /dev/null && head -c 1 /dev/urandom >/dev/null && echo ok'
# A non-root user can reopen its own stdio by path, as php-fpm and nginx
# open their logs; the pipes are the user's, as runc makes them.
t stdio-reopen-nonroot "in-ok" bash -c "echo in | $D run -i --rm -u 1000 alpine sh -c 'read x < /proc/self/fd/0 && : > /dev/stdout && : > /dev/stderr && : > /proc/self/fd/2 && echo \$x-ok'"
t stdio-reopen-exec "ok" bash -c "$D run -d --name stdioexec alpine sleep 60 >/dev/null && $D exec -u 1000 stdioexec sh -c 'echo ok > /dev/stderr'; $D rm -f stdioexec >/dev/null"
# Without -i, stdin is /dev/null, which stays root's and 0666.
t stdio-dev-null-kept "0:0:666 0:0:666" $D run --rm -u 1000 alpine sh -c 'stat -L -c %u:%g:%a /proc/self/fd/0 /dev/null | tr "\n" " "'
t dev-modes "crw-rw-rw-" $D run --rm alpine ls -l /dev/null
t dev-urandom "16" $D run --rm alpine sh -c 'head -c 16 /dev/urandom | wc -c'
t caps-dropped "Operation not permitted" $D run --rm alpine sh -c 'hostname newname 2>&1 || true; mount -t tmpfs t /mnt 2>&1'
t caps-chown "ok" $D run --rm alpine sh -c 'touch /f && chown 1:1 /f && echo ok'
t cgroup-view "cgroup2" $D run --rm alpine sh -c 'mount | grep cgroup2'
t name "named-one" $D run --rm --name named-one alpine sh -c 'echo named-one'
t python "3.13" $D run --rm python:3.13-alpine python -c 'import sys;print(sys.version)'
t node "v22" $D run --rm node:22-alpine node -v
t debian-image "Valkey server" $D run --rm valkey/valkey valkey-server --version

section "stdin and terminals"
t stdin-pipe "3" bash -c "printf 'a\nb\nc\n' | $D run -i --rm alpine wc -l"
t stdin-cat "round trip" bash -c "echo 'round trip' | $D run -i --rm alpine cat"
t stdin-large "1000000" bash -c "head -c 1000000 /dev/zero | $D run -i --rm alpine wc -c"
t tty-is-pty "/dev/pts/0" bash -c "script -q /dev/null $D run -it --rm alpine tty < /dev/null"
t tty-term "xterm" bash -c "script -q /dev/null $D run -it --rm alpine sh -c 'echo \$TERM' < /dev/null"
# Type after the shell is up: an interactive shell discards input typed before its first prompt.
t tty-shell "typed-42" bash -c "(sleep 1; printf 'echo typed-\$((6*7))\nexit\n') | script -q /dev/null $D run -it --rm alpine sh"
code tty-exit-code 5 bash -c "(sleep 1; printf 'exit 5\n') | script -q /dev/null $D run -it --rm alpine sh"
# The client half-closes right behind its input, and the process must see the end.
# A Mac can lose that on the daemon's socket, 1 to 5 runs in 100, hence the many
# runs. The hang is timed here: an alarm does not stop a docker client. Each run
# must also exit 0 and print its input, or runs that all fail would pass this.
if [ "${SLOW:-0}" = 1 ]; then
  hung=0 wrong=0 out=$(mktemp)
  for _ in $(seq 300); do
    echo in | $D run -i --rm --name e2e-stdin-end alpine cat >"$out" 2>&1 &
    p=$!
    for _ in $(seq 150); do kill -0 $p 2>/dev/null || break; sleep 0.1; done
    if kill -0 $p 2>/dev/null; then
      hung=$((hung + 1))
      kill -9 $p
      wait $p 2>/dev/null
      $D rm -f e2e-stdin-end >/dev/null 2>&1
    elif ! wait $p || [ "$(cat "$out")" != in ]; then
      wrong=$((wrong + 1))
      $D rm -f e2e-stdin-end >/dev/null 2>&1
    fi
  done
  rm -f "$out"
  t stdin-end-every-time "hung 0, wrong 0" echo "hung $hung, wrong $wrong"
fi

section "detached, logs, exec, lifecycle"
$D run -d --name web nginx:alpine >/dev/null
t ps-running "web" $D ps --format '{{.Names}} {{.Status}}'
t ps-up "Up" $D ps --format '{{.Status}}'
t inspect-running "true" $D inspect -f '{{.State.Running}}' web
t logs "Configuration complete" $D logs web
t exec "nginx version" $D exec web nginx -v
code exec-exit 3 $D exec web sh -c 'exit 3'
t exec-env "e-val" $D exec -e E=e-val web sh -c 'echo $E'
t exec-user "nginx" $D exec -u nginx web id -un
t exec-workdir "/etc" $D exec -w /etc web pwd
t exec-stdin "into exec" bash -c "echo 'into exec' | $D exec -i web cat"
t exec-tty "/dev/pts" bash -c "script -q /dev/null $D exec -it web tty < /dev/null"
t exec-sees-pid1 "nginx" $D exec web sh -c 'cat /proc/1/comm'
# Each container and each exec leads a session of its own, as with runc, so a
# program that signals its whole process group (Apache prefork's stop does)
# can't reach the engine's own processes (#191).
t session-own "SID=1" $D run --rm alpine sh -c 'echo SID=$(cut -d" " -f6 /proc/1/stat)'
t exec-session-own "own" $D exec web sh -c 's=$(cut -d" " -f6 /proc/$$/stat); [ "$s" = "$$" ] && echo own || echo "session $s, pid $$"'
t exec-same-fs "shared" bash -c "$D exec web sh -c 'echo shared > /tmp/x' && $D exec web cat /tmp/x"
t stop "web" $D stop web
t stopped-status "Exited" $D ps -a --format '{{.Status}}' --filter name=web
code exec-stopped 1 $D exec web true
t start "web" $D start web
t restarted-running "true" $D inspect -f '{{.State.Running}}' web
t restart "web" $D restart web
t kill "web" $D kill web
t killed-code "137" $D inspect -f '{{.State.ExitCode}}' web
code rm-running-refused 1 bash -c "$D start web >/dev/null && $D rm web"
t rm-force "web" $D rm -f web
code gone 1 $D inspect web
t create-then-start "created" bash -c "$D create --name c1 alpine echo hi >/dev/null && $D ps -a --filter name=c1 --format '{{.State}}'"
t start-attach "hi" $D start -a c1
t wait "0" bash -c "$D run -d --name w1 alpine sleep 0.3 >/dev/null; $D wait w1"
t name-conflict "already in use" bash -c "$D run -d --name dup alpine sleep 5 >/dev/null; $D run -d --name dup alpine sleep 5"
code inspect-missing 1 $D inspect no-such-container
t prefix-id "true" bash -c "id=\$($D run -d alpine sleep 5); $D inspect -f '{{.State.Running}}' \${id:0:6}"

section "restart policies and persistence"
t on-failure "2" bash -c "$D run -d --name flaky --restart on-failure:2 alpine sh -c 'exit 1' >/dev/null; sleep 2; $D inspect -f '{{.RestartCount}}' flaky"
t always "true" bash -c "$D run -d --name alw --restart always alpine sh -c 'sleep 0.2' >/dev/null; sleep 1.5; $D inspect -f '{{gt .RestartCount 0}}' alw"
t stop-ends-always "Exited" bash -c "$D stop alw >/dev/null; sleep 1; $D ps -a --filter name=alw --format '{{.Status}}'"
code rm-with-restart-refused 125 $D run --rm --restart always alpine true
# A stopped container whose image layer the guest lost (it deletes an
# unpacked layer that isn't whole at boot) starts again with its own data
# (the file it wrote on the first run is still there on the second):
# the layer is sent again, not "layer ... is not unpacked". busybox's single
# layer is the one with bin/busybox and no alpine-release.
t start-restores-layer "KEPT AGAIN" bash -c "$D rm -f relayer >/dev/null 2>&1; $D run --name relayer busybox:1.36 sh -c '[ -e /kept ] && echo AGAIN >> /kept || echo KEPT > /kept' && $D run --rm --privileged alpine sh -c 'mkdir -p /m && mount -t ext4 /dev/vda /m && for d in /m/layers/*/; do [ -e \$d/bin/busybox ] && [ ! -e \$d/etc/alpine-release ] && rm -rf \$d \${d%/}.done; done; umount /m' && $D start -a relayer >/dev/null && $D cp relayer:/kept - | tar -xO | tr '\\n' ' '; $D rm -f relayer >/dev/null"

section "networking"
t default-ip "172.17." $D run --rm alpine sh -c 'ip -4 addr show eth0'
t default-route "default via 172.17.0.1" $D run --rm alpine ip route
t lo "127.0.0.1" $D run --rm alpine sh -c 'ip -4 addr show lo'
t internet-http "Example Domain" $D run --rm alpine wget -qO- http://example.com
t internet-dns "Address" $D run --rm alpine nslookup example.com
# The default bridge in the VM names its gateway, not 127.0.0.11: BuildKit
# drops loopback nameservers from build steps and puts 8.8.8.8 in their place.
t dns-default-bridge-gateway "nameserver 172.17.0.1" $D run --rm alpine cat /etc/resolv.conf
code dns-default-bridge-no-loopback 1 $D run --rm alpine grep -q 127.0.0.11 /etc/resolv.conf
t internet-https "200" $D run --rm curlimages/curl:latest -s -o /dev/null -w '%{http_code}' https://www.google.com
# Each container gets the last one's address and MAC: its first download
# broke mid-TLS or stalled while the old one's veth lingered, and one that
# keeps running lost its gateway whenever the bridge's MAC moved.
APKIDX=https://dl-cdn.alpinelinux.org/alpine/v3.22/main/aarch64/APKINDEX.tar.gz
t first-download-x8 "8" bash -c "n=0; for i in \$(seq 8); do $D run --rm curlimages/curl:latest -s -m 20 -o /dev/null -w '%{exitcode}' $APKIDX | grep -qx 0 && n=\$((n+1)); done; echo \$n"
$D run -d --name dl curlimages/curl:latest sh -c "while true; do curl -s -m 10 -o /dev/null -w '%{exitcode} ' $APKIDX; done" >/dev/null
for _ in $(seq 6); do $D run --rm alpine true; sleep 1; done
code download-while-others-start 1 bash -c "$D logs dl 2>&1 | grep -qE '(^| )[1-9][0-9]* '"
$D rm -f dl >/dev/null
t none-net "lo" $D run --rm --network none alpine ip link
code none-no-internet 1 $D run --rm --network none alpine wget -qO- -T 2 http://example.com
t host-net "192.168.64." $D run --rm --network host alpine ip -4 addr show eth0
t hosts-file "localhost" $D run --rm alpine cat /etc/hosts
t add-host "1.2.3.4" $D run --rm --add-host foo:1.2.3.4 alpine getent hosts foo
$D run -d --name peer nginx:alpine >/dev/null
nginx_up peer
PEER_IP=$($D inspect -f '{{.NetworkSettings.IPAddress}}' peer)
t container-to-container "Welcome to nginx" $D run --rm alpine wget -qO- "http://$PEER_IP"
t default-bridge-no-names "bad address" $D run --rm alpine wget -qO- -T 2 http://peer
t network-create "" $D network create appnet
t network-ls "appnet" $D network ls
# The first free 172.x subnet: 172.18 on an empty engine, later if the user has networks.
t network-subnet "172." $D network inspect appnet -f '{{range .IPAM.Config}}{{.Subnet}}{{end}}'
$D run -d --name db --network appnet --network-alias database redis:7-alpine >/dev/null
$D run -d --name svc --network appnet nginx:alpine >/dev/null
sleep 0.5
t dns-name "PONG" $D run --rm --network appnet redis:7-alpine redis-cli -h db ping
t dns-alias "PONG" $D run --rm --network appnet redis:7-alpine redis-cli -h database ping
t dns-other "Welcome to nginx" $D run --rm --network appnet alpine wget -qO- http://svc
t dns-upstream "Address" $D run --rm --network appnet alpine nslookup example.com
t dns-resolvconf "nameserver 127.0.0.11" $D run --rm --network appnet alpine cat /etc/resolv.conf
# What a kind node's pods are given instead: host.docker.internal's address.
t dns-via-host-addr "Address" $D run --rm --network appnet alpine nslookup svc 198.19.248.254
t network-members "db" $D network inspect appnet -f '{{range .Containers}}{{.Name}} {{end}}'
code network-rm-in-use 1 $D network rm appnet
code network-dup 1 $D network create appnet
$D rm -f db svc >/dev/null
t network-rm "appnet" $D network rm appnet
code network-rm-builtin 1 $D network rm bridge
# --internal: no default route, so anything beyond the network fails at once
# (as with Docker), while the network itself still works.
$D network create --internal intnet >/dev/null
$D run -d --name intweb --network intnet nginx:alpine >/dev/null
nginx_up intweb
t internal-same-net "Welcome to nginx" $D run --rm --network intnet alpine wget -qO- -T 5 http://intweb
t internal-no-route "unreachable" $D run --rm --network intnet alpine sh -c 'ping -c 1 -W 2 1.1.1.1 2>&1; true'
t internal-no-default "none" $D run --rm --network intnet alpine sh -c 'ip route | grep -q default && echo default || echo none'
# An IPv4-only network: IPv6 is off on eth0 (no link-local), lo keeps ::1.
t v4-net-no-inet6 "none" $D run --rm --network intnet alpine sh -c 'ip -6 addr show eth0 | grep -q inet6 && echo some || echo none'
$D rm -f intweb >/dev/null; $D network rm intnet >/dev/null

section "networking options"
# IPAM: a chosen subnet, gateway, range and reserved address.
t ipam-create "" $D network create --subnet 10.231.0.0/24 --gateway 10.231.0.254 --ip-range 10.231.0.128/25 --aux-address router=10.231.0.200 -o com.example.x=1 --label team=net ipamnet
t ipam-inspect "10.231.0.0/24 10.231.0.254 10.231.0.128/25 map[router:10.231.0.200]" $D network inspect ipamnet -f '{{range .IPAM.Config}}{{.Subnet}} {{.Gateway}} {{.IPRange}} {{.AuxiliaryAddresses}}{{end}}'
t ipam-options "map[com.example.x:1]" $D network inspect ipamnet -f '{{.Options}}'
t ipam-from-range "10.231.0.128" $D run --rm --network ipamnet alpine ip -4 addr show eth0
t ipam-route "default via 10.231.0.254" $D run --rm --network ipamnet alpine ip route
t ipam-overlap "Pool overlaps with other one on this address space" $D network create --subnet 10.231.0.0/16 ipamnet2
t ipam-bad-gateway "no matching subnet for gateway" $D network create --subnet 10.232.0.0/24 --gateway 10.9.0.1 ipamnet3
# Fixed addresses (--ip, Compose ipv4_address) and MAC addresses.
$D run -d --name fixed --network ipamnet --ip 10.231.0.10 --mac-address 02:42:0a:e7:00:0a nginx:alpine >/dev/null
t static-ip "10.231.0.10" $D inspect -f '{{.NetworkSettings.Networks.ipamnet.IPAddress}}' fixed
t static-ipamconfig "10.231.0.10" $D inspect -f '{{.NetworkSettings.Networks.ipamnet.IPAMConfig.IPv4Address}}' fixed
t static-prefix "24" $D inspect -f '{{.NetworkSettings.Networks.ipamnet.IPPrefixLen}}' fixed
t static-mac "02:42:0a:e7:00:0a" $D exec fixed cat /sys/class/net/eth0/address
t static-in-use "Address already in use" $D run --rm --network ipamnet --ip 10.231.0.10 alpine true
t static-outside "no configured subnet" $D run --rm --network ipamnet --ip 10.9.0.10 alpine true
t static-default-bridge "user defined networks only" $D run --rm --ip 172.17.0.99 alpine true
$D network create --subnet 10.233.0.0/24 ipamnet4 >/dev/null
t static-connect "10.233.0.77" bash -c "$D network connect --ip 10.233.0.77 ipamnet4 fixed && $D exec fixed ip -4 addr show eth1"
# --network container: (Compose network_mode: service:x).
t netns-shared-ip "10.231.0.10" $D run --rm --network container:fixed alpine ip -4 addr show eth0
t netns-localhost "Welcome to nginx" $D run --rm --network container:fixed alpine wget -qO- http://127.0.0.1
FIXED_ID=$($D inspect -f '{{.Id}}' fixed)
FIXED_HOST=$($D inspect -f '{{.Config.Hostname}}' fixed)
t netns-hostname "$FIXED_HOST" $D run --rm --network container:fixed alpine hostname
t netns-hosts "10.231.0.10" $D run --rm --network container:fixed alpine cat /etc/hosts
t netns-mode "container:$FIXED_ID" bash -c "$D create --name side --network container:fixed alpine sleep 60 >/dev/null; $D inspect -f '{{.HostConfig.NetworkMode}}' side"
t netns-settings "map[]" $D inspect -f '{{.NetworkSettings.Networks}}' side
t netns-ports "conflicting options: port publishing and the container type network mode" $D run --rm -p 18190:80 --network container:fixed alpine true
t netns-hostname-refused "conflicting options: hostname and the network mode" $D run --rm -h x --network container:fixed alpine true
t netns-missing "No such container" $D run --rm --network container:nope alpine true
$D stop fixed >/dev/null
t netns-not-running "cannot join network of a non running container" $D start side
$D rm -f side >/dev/null
$D start fixed >/dev/null
# DNS settings: the default bridge gets the servers; user networks keep the
# embedded DNS at 127.0.0.11, which forwards to them.
t dns-default-bridge "nameserver 9.9.9.9" $D run --rm --dns 9.9.9.9 --dns-search corp.example --dns-option ndots:2 alpine cat /etc/resolv.conf
t dns-search "search corp.example" $D run --rm --dns-search corp.example alpine cat /etc/resolv.conf
t dns-options "options ndots:2" $D run --rm --dns-option ndots:2 alpine cat /etc/resolv.conf
t dns-user-net "nameserver 127.0.0.11" $D run --rm --network ipamnet --dns 9.9.9.9 alpine cat /etc/resolv.conf
t dns-user-net-forwards "Address" $D run --rm --network ipamnet --dns 9.9.9.9 alpine nslookup example.com
t dns-user-net-names "10.231.0.10" $D run --rm --network ipamnet --dns 9.9.9.9 alpine nslookup fixed
t dns-inspect "[9.9.9.9]" bash -c "$D create --name dnsc --dns 9.9.9.9 alpine true >/dev/null; $D inspect -f '{{.HostConfig.Dns}}' dnsc; $D rm dnsc >/dev/null"
t domainname "web.example.com" $D run --rm -h web --domainname example.com alpine sh -c 'hostname -f 2>/dev/null || cat /etc/hosts'
t domainname-uts "example.com" $D run --rm --domainname example.com alpine cat /proc/sys/kernel/domainname
# --link on the default bridge, which has no DNS.
$D run -d --name linked nginx:alpine >/dev/null
nginx_up linked
t link-alias "Welcome to nginx" $D run --rm --link linked:webby alpine wget -qO- http://webby
t link-name "Welcome to nginx" $D run --rm --link linked alpine wget -qO- http://linked
t link-hosts "webby" $D run --rm --link linked:webby alpine cat /etc/hosts
t link-inspect "/linked:/" bash -c "$D create --name linker --link linked:webby alpine true >/dev/null; $D inspect -f '{{.HostConfig.Links}}' linker; $D rm linker >/dev/null"
t link-missing "could not get container for nope" $D run --rm --link nope:x alpine true
$D rm -f fixed linked >/dev/null
$D network rm ipamnet ipamnet4 >/dev/null

section "IPv6 networks"
# --ipv6 without a subnet: a /64 from the engine's ULA pool, beside IPv4.
t ipv6-create "" $D network create --ipv6 v6net
t ipv6-enabled "true" $D network inspect v6net -f '{{.EnableIPv6}}'
t ipv6-pool "/64" $D network inspect v6net -f '{{range .IPAM.Config}}{{.Subnet}} {{end}}'
t ipv6-pool-ula " fd" $D network inspect v6net -f '{{range .IPAM.Config}} {{.Subnet}}{{end}}'
# A chosen subnet and gateway, as kind and Compose's ipam ask.
t ipv6-subnet "fd00:db8:7::/64 fd00:db8:7::fe" bash -c "$D network create --ipv6 --subnet fd00:db8:7::/64 --gateway fd00:db8:7::fe v6sub >/dev/null && $D network inspect v6sub -f '{{range .IPAM.Config}}{{.Subnet}} {{.Gateway}} {{end}}'"
t ipv6-overlap "Pool overlaps" $D network create --ipv6 --subnet fd00:db8:7::/80 v6dup
# IPv6-only (--ipv4=false), as Docker 28 has: no IPv4 address on eth0.
# The host docker CLI may predate --ipv4 (27.x): drive the API directly.
t ipv6-only-create "False" bash -c "curl -s --unix-socket '$SOCK' -X POST -H 'Content-Type: application/json' -d '{\"Name\":\"v6only\",\"EnableIPv6\":true,\"EnableIPv4\":false}' http://d/networks/create -o /dev/null && curl -s --unix-socket '$SOCK' http://d/networks/v6only | python3 -c 'import json,sys; print(json.load(sys.stdin)[\"EnableIPv4\"])'"
t ipv6-only-no-v4 "inet6 0" $D run --rm --network v6only alpine sh -c 'echo $(ip -6 addr show eth0 scope global | grep -o inet6 | head -1) $(ip -4 addr show eth0 | grep -c inet)'
$D network rm v6only >/dev/null
$D run -d --name v6a --network v6sub --network-alias v6web nginx:alpine >/dev/null
sleep 0.5
V6A=$($D inspect -f '{{.NetworkSettings.Networks.v6sub.GlobalIPv6Address}}' v6a)
t ipv6-address "fd00:db8:7::1" echo "$V6A"
t ipv6-prefix "64" $D inspect -f '{{.NetworkSettings.Networks.v6sub.GlobalIPv6PrefixLen}}' v6a
t ipv6-gateway "fd00:db8:7::fe" $D inspect -f '{{.NetworkSettings.Networks.v6sub.IPv6Gateway}}' v6a
t ipv6-ipv4-too "." $D inspect -f '{{.NetworkSettings.Networks.v6sub.IPAddress}}' v6a
t ipv6-members "$V6A/64" $D network inspect v6sub -f '{{range .Containers}}{{.IPv6Address}}{{end}}'
t ipv6-eth0 "inet6 fd00:db8:7::" $D exec v6a ip -6 addr show eth0
t ipv6-route "default via fd00:db8:7::fe" $D run --rm --network v6sub alpine ip -6 route
t ipv6-hosts "fd00:db8:7::" $D run --rm --network v6sub alpine cat /etc/hosts
t ipv6-ping "1 packets received" $D run --rm --network v6sub alpine ping -6 -c 1 -W 2 v6a
t ipv6-wget "Welcome to nginx" $D run --rm --network v6sub alpine wget -qO- -T 5 "http://[$V6A]"
t ipv6-aaaa "$V6A" $D run --rm --network v6sub alpine nslookup -type=AAAA v6web
t ipv6-a-still "Address" $D run --rm --network v6sub alpine nslookup -type=A v6a
# Fixed addresses (--ip6, Compose ipv6_address).
t ipv6-static "fd00:db8:7::99" bash -c "$D run -d --name v6fixed --network v6sub --ip6 fd00:db8:7::99 alpine sleep 60 >/dev/null; $D inspect -f '{{.NetworkSettings.Networks.v6sub.GlobalIPv6Address}} {{.NetworkSettings.Networks.v6sub.IPAMConfig.IPv6Address}}' v6fixed"
t ipv6-static-in-use "Address already in use" $D run --rm --network v6sub --ip6 fd00:db8:7::99 alpine true
t ipv6-static-outside "no configured subnet" $D run --rm --network v6sub --ip6 fd00:9::9 alpine true
# On an automatically allocated subnet too, as with Docker 29 (moby#51569).
t ipv6-static-pool "ok" bash -c "p=\$($D network inspect v6net -f '{{range .IPAM.Config}}{{.Subnet}} {{end}}' | grep -o '[0-9a-f:]*::/64' | sed 's|::/64||'); $D run --rm --network v6net --ip6 \${p}::9 alpine ip -6 addr show eth0 | grep -q \${p}::9/64 && echo ok"
t ipv6-static-v4-net "does not have IPv6 enabled" bash -c "$D network create v4only >/dev/null; $D run --rm --network v4only --ip6 fd00::9 alpine true; $D network rm v4only >/dev/null"
t ipv6-connect "inet6 fd00:db8:7::" bash -c "$D run -d --name v6late alpine sleep 60 >/dev/null && $D network connect v6sub v6late && $D exec v6late ip -6 addr show eth1"
# Egress: reaches IPv6 sites when the host has IPv6, fails fast otherwise.
code ipv6-egress-no-hang 0 bash -c "$D run --rm --network v6sub alpine sh -c 'wget -qO- -T 5 http://ipv6.google.com >/dev/null 2>&1; true'"
# The default bridge stays IPv4-only.
t ipv6-default-bridge "0" bash -c "$D run --rm alpine ip -6 addr show scope global | grep -c inet6"
$D rm -f v6a v6fixed v6late >/dev/null
t ipv6-rm "v6sub" $D network rm v6sub
$D network rm v6net >/dev/null

section "published ports"
$D run -d --name pub -p 18180:80 nginx:alpine >/dev/null; ready http://localhost:18180
t port-curl "Welcome to nginx" curl -s -m 5 http://localhost:18180
t port-ps "0.0.0.0:18180->80/tcp" $D ps --filter name=pub --format '{{.Ports}}'
t port-cmd "18180" $D port pub
t port-many "50" bash -c "for i in \$(seq 50); do curl -s -m 5 -o /dev/null -w '%{http_code}\n' http://localhost:18180; done | grep -c 200"
t port-parallel "20" bash -c "for i in \$(seq 20); do curl -s -m 10 -o /dev/null -w '%{http_code}\n' http://localhost:18180 & done; wait"
t port-big "10485760" bash -c "$D exec pub sh -c 'head -c 10485760 /dev/urandom > /usr/share/nginx/html/big.bin' && curl -s -m 30 -o /dev/null -w '%{size_download}' http://localhost:18180/big.bin"
t port-clash "port is already allocated" $D run -d --name pub2 -p 18180:80 nginx:alpine
t port-publish-all "80/tcp ->" bash -c "$D run -d --name puball -P nginx:alpine >/dev/null; $D port puball"
t port-ipv6-listed "[::]:18180" $D port pub 80
t port-ipv6-curl "Welcome to nginx" curl -sg -m 5 'http://[::1]:18180'
t port-ipv6-only "[::1]:18183" bash -c "$D run -d --name pub6 -p '[::1]:18183:80' nginx:alpine >/dev/null; $D port pub6"
t port-ipv6-only-curl "Welcome to nginx" bash -c "for i in \$(seq 50); do curl -sg -m 1 'http://[::1]:18183' && break; sleep 0.2; done"
code port-ipv6-only-not-v4 7 curl -s -m 2 http://127.0.0.1:18183
$D rm -f pub pub2 puball pub6 >/dev/null
code port-closed-after-stop 7 curl -s -m 2 http://localhost:18180

section "host.docker.internal"
python3 -m http.server 18999 --bind 127.0.0.1 >/dev/null 2>&1 &
HTTP_PID=$!
sleep 0.7
t host-internal "Directory listing" $D run --rm alpine wget -qO- http://host.docker.internal:18999/
t host-gateway "Directory listing" $D run --rm --add-host mac:host-gateway alpine wget -qO- http://mac:18999/
t host-internal-hostnet "Directory listing" $D run --rm --network host alpine wget -qO- http://host.docker.internal:18999/
kill $HTTP_PID
python3 -c '
import socket
l = socket.socket(); l.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); l.bind(("127.0.0.1", 18998)); l.listen(1)
c, _ = l.accept(); n = 0
while (b := c.recv(1 << 20)): n += len(b)
c.sendall(f"received {n}\n".encode()); c.close()
' >/dev/null 2>&1 &
EOF_PID=$!
sleep 0.5
t host-internal-upload-eof "received 67108864" $D run --rm alpine sh -c 'head -c 67108864 /dev/zero | nc host.docker.internal 18998'
kill $EOF_PID 2>/dev/null

section "volumes and bind mounts"
BIND=$(mktemp -d); echo "from the mac" > "$BIND/hello.txt"
t bind-read "from the mac" $D run --rm -v "$BIND:/data" alpine cat /data/hello.txt
t bind-write "from the container" bash -c "$D run --rm -v $BIND:/data alpine sh -c 'echo from the container > /data/out.txt' && cat $BIND/out.txt"
# A new file without owner read (Node's fs.cpSync creates with 0200) is made
# and ends with that mode (guest/kernel/patches/0003).
t bind-create-0200 "200 hi" bash -c "$D run --rm -v $BIND:/data alpine sh -c 'umask 577; echo hi > /data/w0200' && perl -e 'printf q(%o ), (stat shift)[2] & 07777' $BIND/w0200 && chmod u+r $BIND/w0200 && cat $BIND/w0200"
t bind-ro "Read-only file system" $D run --rm -v "$BIND:/data:ro" alpine sh -c 'echo x > /data/nope'
t bind-mount-flag "from the mac" $D run --rm --mount "type=bind,source=$BIND,target=/m" alpine cat /m/hello.txt
code bind-mount-missing 125 $D run --rm --mount type=bind,source=/ctrs/does/not/exist,target=/m alpine true
t bind-v-creates "made" bash -c "$D run --rm -v $BIND/new/dir:/n alpine true && [ -d $BIND/new/dir ] && echo made"
t bind-file "from the mac" $D run --rm -v "$BIND/hello.txt:/etc/greeting" alpine cat /etc/greeting
# Mac-side edits under a bind mount reach container inotify watchers
# (docs/design-bind-notify.md): save, atomic replace, create, rename, delete.
# A watch on a replaced or deleted file gets IN_DELETE_SELF, as on Linux.
# An in-place save is also a rename of the name onto itself, as on OrbStack.
WATCH=$(mktemp -d); echo one > "$WATCH/saved"; echo one > "$WATCH/replaced"; echo one > "$WATCH/renamed"; echo one > "$WATCH/deleted"
$D run -d --name e2e-inotify -v "$WATCH:/w" alpine inotifyd - /w:cndmy /w/replaced:D /w/deleted:D >/dev/null
sleep 1
echo two >> "$WATCH/saved"; echo two > "$WATCH/.tmp" && mv "$WATCH/.tmp" "$WATCH/replaced"
echo new > "$WATCH/created"; mv "$WATCH/renamed" "$WATCH/moved"; unlink "$WATCH/deleted"
sleep 2
INOTIFY=$($D logs e2e-inotify 2>&1)
t bind-inotify-save "saved" grep -E "^c.*/w.saved" <<<"$INOTIFY"
t bind-inotify-save-rename "saved" grep -E "^y.*/w.saved" <<<"$INOTIFY"
t bind-inotify-replace "replaced" grep -E "^n.*/w.replaced" <<<"$INOTIFY"
t bind-inotify-create "created" grep -E "^n.*/w.created" <<<"$INOTIFY"
t bind-inotify-rename "moved" grep -E "^n.*/w.moved" <<<"$INOTIFY"
t bind-inotify-delete "deleted" grep -E "^d.*/w.deleted" <<<"$INOTIFY"
t bind-inotify-replace-self "/w/replaced" grep -E "^D\s+/w/replaced$" <<<"$INOTIFY"
t bind-inotify-delete-self "/w/deleted" grep -E "^D\s+/w/deleted$" <<<"$INOTIFY"
t bind-inotify-content "two" $D exec e2e-inotify cat /w/saved
# The host's report of a container's own write is not raised again when
# the guest already holds the host's attributes for it
# (guest/kernel/patches/0015): here a stat right after the write.
$D exec e2e-inotify sh -c 'echo own > /w/own; stat /w/own >/dev/null'
sleep 2
t bind-inotify-no-echo "no echo" bash -c "$D logs e2e-inotify 2>&1 | grep -qE '^[my].*/w.own' && echo echoed || echo no echo"
$D rm -f e2e-inotify >/dev/null
# The guest caches missing names for a second (guest/kernel/patches/0007);
# a Mac-side create must still show at once to a container that keeps probing.
$D run -d --name e2e-negative -v "$WATCH:/w" alpine sh -c 'while true; do [ -e /w/late ]; sleep 0.01; done' >/dev/null
sleep 1
echo x > "$WATCH/late"; sleep 0.2
t bind-negative-create "seen" $D exec e2e-negative sh -c 'test -e /w/late && echo seen'
# Names missing from a directory the container just made are answered
# without asking the Mac (guest/kernel/patches/0013), and directories stay
# cached for ten seconds (0014); Mac-side changes inside them, including
# in a new subdirectory, and a Mac-side directory removal still show.
mkdir "$WATCH/gone"
$D exec e2e-negative sh -c 'mkdir /w/made && ls /w/gone && for n in a b c; do [ -e /w/made/$n ]; [ -e /w/made/sub/$n ]; done' >/dev/null
echo mac > "$WATCH/made/a"; mkdir "$WATCH/made/sub" && echo mac > "$WATCH/made/sub/b"; rmdir "$WATCH/gone"
WAIT_SEEN='for i in $(seq 30); do test -e /w/made/a && test -e /w/made/sub/b && ! test -e /w/gone && echo seen && break; sleep 0.1; done'
t bind-made-here-mac-create "seen" $D exec e2e-negative sh -c "$WAIT_SEEN"
$D rm -f e2e-negative >/dev/null
# Mixed writers (guest/kernel/patches/0015): a Mac edit right after the
# container's own write is raised and read, in place or as an atomic
# replace. A builder that re-reads the file on every event must end on the
# Mac's bytes, and so must a plain read.
MIX=$(mktemp -d); mkdir "$MIX/src"; echo base > "$MIX/src/inplace"; echo base > "$MIX/src/replaced"
$D run -d --name e2e-mix -v "$MIX:/w" alpine sh -c 'inotifyd - /w/src:cwnmy | while read -r e d n; do echo "$n $(cat /w/src/$n 2>/dev/null)"; done > /tmp/built' >/dev/null
sleep 1
$D exec e2e-mix sh -c 'echo guest > /w/src/inplace; echo guest > /w/src/replaced'
sleep 0.3
echo mac > "$MIX/src/inplace"; echo mac > "$MIX/src/.tmp" && mv "$MIX/src/.tmp" "$MIX/src/replaced"
WAIT_MIX='for i in $(seq 40); do [ "$(grep "^inplace " /tmp/built | tail -1)" = "inplace mac" ] && [ "$(grep "^replaced " /tmp/built | tail -1)" = "replaced mac" ] && break; sleep 0.1; done; echo "$(cat /w/src/inplace) $(cat /w/src/replaced) $(grep "^inplace " /tmp/built | tail -1 | cut -d" " -f2) $(grep "^replaced " /tmp/built | tail -1 | cut -d" " -f2)"'
t bind-mixed-writer "mac mac mac mac" $D exec e2e-mix sh -c "$WAIT_MIX"
# Watched-root churn: other containers' bind mounts come and go, which
# replaces the host's FSEvents stream; edits made meanwhile still arrive.
for i in 1 2 3 4; do
  OTHER=$(mktemp -d); $D run -d --name "e2e-churn$i" -v "$OTHER:/o" alpine sleep 30 >/dev/null
  echo "churn$i" > "$MIX/src/inplace"
  $D rm -f "e2e-churn$i" >/dev/null; rmdir "$OTHER"
done
WAIT_CHURN='for i in $(seq 40); do [ "$(grep "^inplace " /tmp/built | tail -1)" = "inplace churn4" ] && break; sleep 0.1; done; echo "$(cat /w/src/inplace) $(grep "^inplace " /tmp/built | tail -1 | cut -d" " -f2)"'
t bind-root-churn "churn4 churn4" $D exec e2e-mix sh -c "$WAIT_CHURN"
# A burst larger than the guest's queue (8,192 lines) is delivered or
# collapsed into a rescan; either way the final state shows.
mkdir "$MIX/burst"; (cd "$MIX/burst" && seq 1 20000 | xargs touch) ; echo last > "$MIX/src/inplace"
WAIT_BURST='for i in $(seq 100); do [ "$(ls /w/burst | wc -l)" = 20000 ] && [ "$(cat /w/src/inplace)" = last ] && break; sleep 0.1; done; echo "$(ls /w/burst | wc -l) $(cat /w/src/inplace)"'
t bind-burst "20000 last" $D exec e2e-mix sh -c "$WAIT_BURST"
# A rescan (the host lost events) revalidates the share's cached
# entries without detaching a volume mounted inside a bind mount, and
# renaming the bind root away and back (FSEvents root-changed) still lets
# a change made meanwhile show.
RS=$(mktemp -d); mkdir "$RS/proj"; echo one > "$RS/proj/f"
$D volume create e2e-rescan >/dev/null
$D run -d --name e2e-rescan --privileged -v "$RS/proj:/w" -v e2e-rescan:/w/deps alpine sh -c 'echo vol > /w/deps/marker; sleep 120' >/dev/null
sleep 1
$D exec e2e-rescan cat /w/f >/dev/null
echo two > "$RS/proj/f"
t bind-rescan-keeps-mounts "vol two" $D exec e2e-rescan sh -c 'echo "s /w" > /proc/ctrs/fsnotify && echo "$(cat /w/deps/marker) $(cat /w/f)"'
mv "$RS/proj" "$RS/moved"; echo three > "$RS/moved/f"; mv "$RS/moved" "$RS/proj"
t bind-root-renamed "three" $D exec e2e-rescan sh -c 'for i in $(seq 40); do [ "$(cat /w/f)" = three ] && break; sleep 0.1; done; cat /w/f'
$D rm -f e2e-rescan >/dev/null; $D volume rm e2e-rescan >/dev/null; rm -rf "$RS"
$D rm -f e2e-mix >/dev/null; rm -rf "$MIX"
t vol-persist "kept" bash -c "$D run --rm -v tvol:/v alpine sh -c 'echo kept > /v/f' && $D run --rm -v tvol:/v alpine cat /v/f"
t vol-ls "tvol" $D volume ls
t vol-inspect "/var/lib/ctrs/volumes/tvol/_data" $D volume inspect -f '{{.Mountpoint}}' tvol
t vol-copyup "index.html" $D run --rm -v thtml:/usr/share/nginx/html nginx:alpine ls /usr/share/nginx/html
t vol-nocopy-empty "0" $D run --rm --mount type=volume,source=tempty,target=/usr/share/nginx/html,volume-nocopy nginx:alpine sh -c 'ls /usr/share/nginx/html | wc -l'
# A new volume takes the image directory's owner, mode and files, as Docker
# does; redis runs as user redis and must be able to write /data.
t vol-copyup-owner "same:redis:redis 755" bash -c "i=\$($D run --rm redis:7-alpine stat -c '%U:%G %a' /data); v=\$($D run --rm -v towner:/data redis:7-alpine stat -c '%U:%G %a' /data); [ \"\$i\" = \"\$v\" ] && echo same:\$v || echo image \$i volume \$v"
t vol-copyup-tree "same" bash -c "i=\$($D run --rm alpine sh -c 'cd /etc/apk && { find . -exec stat -c \"%n %A %u %g\" {} +; find . -type f -exec md5sum {} +; } | sort | md5sum'); v=\$($D run --rm -v tapk:/etc/apk alpine sh -c 'cd /etc/apk && { find . -exec stat -c \"%n %A %u %g\" {} +; find . -type f -exec md5sum {} +; } | sort | md5sum'); [ \"\$i\" = \"\$v\" ] && echo same"
t vol-copyup-not-over "1 mine" bash -c "$D run --rm -v tkeep:/usr/share/nginx/html nginx:alpine sh -c 'rm /usr/share/nginx/html/*; echo mine > /usr/share/nginx/html/mine' && $D run --rm -v tkeep:/usr/share/nginx/html nginx:alpine sh -c 'echo \$(ls /usr/share/nginx/html | wc -l) \$(cat /usr/share/nginx/html/mine)'"
t redis-volume "PONG OK running" bash -c "$D run -d --name rv -v tredis:/data redis:7-alpine >/dev/null; for i in \$(seq 50); do $D exec rv redis-cli ping 2>/dev/null | grep -q PONG && break; sleep 0.2; done; p=\$($D exec rv redis-cli ping); s=\$($D exec rv redis-cli save); sleep 1; echo \$p \$s \$($D inspect -f '{{.State.Status}}' rv)"
# A volume over part of a bind (`./:/app` and `/app/node_modules`) is filled
# from the image, as Docker does, never from the host's folder under it.
t vol-copyup-under-bind "index.html" bash -c "h=\$(mktemp -d); mkdir \$h/html; echo mac > \$h/html/from-host.txt; $D run --rm -v \$h:/usr/share/nginx -v /usr/share/nginx/html nginx:alpine sh -c 'cd /usr/share/nginx/html; [ -e from-host.txt ] && echo from the host || ls'; rm -rf \$h"
$D rm -f rv >/dev/null 2>&1; $D volume rm towner tapk tkeep tredis >/dev/null 2>&1
t vol-in-use "in use" bash -c "$D run -d --name vu -v tvol:/v alpine sleep 30 >/dev/null; $D volume rm tvol"
$D rm -f vu >/dev/null
t vol-rm "tvol" $D volume rm tvol thtml tempty
t vol-create "made-vol" $D volume create made-vol
t tmpfs "size=10240k" $D run --rm --tmpfs /scratch:size=10m alpine sh -c 'mount | grep scratch'
t tmpfs-mount "tmpfs on /t" $D run --rm --mount type=tmpfs,target=/t alpine sh -c 'mount | grep " /t "'
t anon-from-image "volume:/var/lib/postgresql/data" bash -c "$D run -d --name pgv -e POSTGRES_PASSWORD=x postgres:17-alpine >/dev/null; $D inspect -f '{{range .Mounts}}{{.Type}}:{{.Destination}}{{end}}' pgv"
# Waits for the entrypoint's "init process complete" and then a working query,
# not for pg_isready: on first start Postgres runs a temporary server to
# initialise, which also answers, and then restarts.
t postgres-works "42" bash -c "for i in \$(seq 60); do $D logs pgv 2>&1 | grep -q 'init process complete' && $D exec pgv psql -U postgres -tAc 'select 1' >/dev/null 2>&1 && break; sleep 0.5; done; $D exec pgv psql -U postgres -tAc 'select 42'"
t rm-v-anon "gone" bash -c "n=\$($D volume ls -q | wc -l); $D rm -f -v pgv >/dev/null; m=\$($D volume ls -q | wc -l); [ \$m -lt \$n ] && echo gone"
t rm-anon-default-kept "kept" bash -c "$D run -d --name pgk -e POSTGRES_PASSWORD=x postgres:17-alpine >/dev/null; $D inspect -f '{{range .Mounts}}{{.Name}}{{end}}' pgk > /tmp/ctrs-e2e-pgk-vol; n=\$($D volume ls -q | wc -l); $D rm -f pgk >/dev/null; m=\$($D volume ls -q | wc -l); [ \$m -eq \$n ] && echo kept"
$D volume rm "$(cat /tmp/ctrs-e2e-pgk-vol 2>/dev/null)" >/dev/null 2>&1; rm -f /tmp/ctrs-e2e-pgk-vol
# Prune only what this suite labels: never the user's own volumes.
t vol-prune "prunev" bash -c "$D volume create --label ctrs-e2e=1 prunev >/dev/null; $D volume prune -af --filter label=ctrs-e2e=1"
$D volume rm made-vol >/dev/null 2>&1
rm -rf "$BIND"

section "filters"
$D run -d --name fa --label team=a --label tier=web alpine sleep 60 >/dev/null
$D run -d --name fb --label team=b alpine sleep 60 >/dev/null
$D run --name fx alpine sh -c 'exit 3' >/dev/null 2>&1
t filter-label "fa" $D ps --filter label=team=a --format '{{.Names}}'
t filter-label-none "0" bash -c "$D ps -q --filter label=team=zzz | wc -l | tr -d ' '"
t filter-label-and "1" bash -c "$D ps -q --filter label=team=a --filter label=tier=web | wc -l | tr -d ' '"
t filter-label-key "2" bash -c "$D ps -q --filter label=team | wc -l | tr -d ' '"
t filter-name "fb" $D ps --filter name=fb --format '{{.Names}}'
t filter-status-exited "fx" $D ps --filter status=exited --format '{{.Names}}'
t filter-exited-code "fx" $D ps -a --filter exited=3 --format '{{.Names}}'
t filter-ancestor "2" bash -c "$D ps -q --filter ancestor=alpine | wc -l | tr -d ' '"
t filter-network "2" bash -c "$D ps -q --filter network=bridge --filter label=team | wc -l | tr -d ' '"
t filter-network-other "0" bash -c "$D ps -q --filter network=none --filter label=team | wc -l | tr -d ' '"
t filter-id "fa" bash -c "$D ps --filter id=\$($D inspect -f '{{.Id}}' fa | cut -c1-12) --format '{{.Names}}'"
code filter-invalid 1 $D ps --filter bogus=1
t filter-images-ref "alpine" $D images --filter reference=alpine --format '{{.Repository}}'
t filter-images-ref-miss "0" bash -c "$D images -q --filter reference=nosuchimage | wc -l | tr -d ' '"
t filter-images-dangling "0" bash -c "$D images -q --filter dangling=true | wc -l | tr -d ' '"
$D network create --label team=a fnet >/dev/null
t filter-network-label "fnet" $D network ls --filter label=team=a --format '{{.Name}}'
t filter-network-type "fnet" $D network ls --filter type=custom --format '{{.Name}}'
t filter-network-builtin "bridge" $D network ls --filter type=builtin --format '{{.Name}}'
$D network rm fnet >/dev/null
$D volume create --label team=a fvol >/dev/null
$D volume create fvol2 >/dev/null
t filter-volume-label "fvol" $D volume ls --filter label=team=a --format '{{.Name}}'
t filter-volume-label-only "1" bash -c "$D volume ls -q --filter label=team=a | wc -l | tr -d ' '"
t filter-volume-dangling "fvol2" $D volume ls --filter dangling=true --format '{{.Name}}'
t filter-volume-prune-all "fvol" $D volume prune -af --filter label=team=a
t filter-volume-prune-label-only "fvol2" $D volume ls --format '{{.Name}}'
$D volume rm fvol2 >/dev/null
$D rm -f fa fb fx >/dev/null

section "compose"
# A container outside the project must not confuse Compose.
$D run -d --name bystander nginx:alpine >/dev/null
CP=$(mktemp -d)
cat > "$CP/compose.yaml" <<'YAML'
services:
  web:
    image: nginx:alpine
    ports: ["18380:80"]
    volumes: ["./html:/usr/share/nginx/html:ro"]
    depends_on: [cache]
  cache:
    image: redis:7-alpine
    volumes: ["cachedata:/data"]
volumes:
  cachedata: {}
YAML
mkdir -p "$CP/html" && echo "compose on ctrs" > "$CP/html/index.html"
t compose-up "Started" bash -c "cd $CP && $D compose -p ctrstest up -d 2>&1"
ready http://localhost:18380
t compose-port "compose on ctrs" curl -s -m 5 http://localhost:18380
t compose-dns "PONG" bash -c "cd $CP && $D compose -p ctrstest exec -T web sh -c 'apk add -q redis >/dev/null 2>&1; redis-cli -h cache ping || { cat /etc/resolv.conf; nslookup cache; ip addr show eth0; }'"
t compose-ps "running" bash -c "cd $CP && $D compose -p ctrstest ps --format '{{.State}}'"
t compose-down "Removed" bash -c "cd $CP && $D compose -p ctrstest down -v 2>&1"
t compose-clean "0" bash -c "$D ps -aq --filter label=com.docker.compose.project=ctrstest | wc -l | tr -d ' '"
t compose-bystander "bystander" $D ps --format '{{.Names}}'
$D rm -f bystander >/dev/null
rm -rf "$CP"

section "docker cp"
CPD=$(mktemp -d); mkdir -p "$CPD/dir/sub"; echo one > "$CPD/a.txt"; echo two > "$CPD/dir/sub/b.txt"
$D run -d --name cpc alpine sleep 120 >/dev/null
t cp-in-file "one" bash -c "$D cp $CPD/a.txt cpc:/tmp/ && $D exec cpc cat /tmp/a.txt"
t cp-in-dir "two" bash -c "$D cp $CPD/dir cpc:/tmp/ && $D exec cpc cat /tmp/dir/sub/b.txt"
t cp-in-rename "one" bash -c "$D cp $CPD/a.txt cpc:/tmp/renamed.txt && $D exec cpc cat /tmp/renamed.txt"
t cp-in-root-owner "0 0" bash -c "$D exec cpc stat -c '%u %g' /tmp/a.txt"
t cp-out-file "fromctr" bash -c "$D exec cpc sh -c 'echo fromctr > /etc/motd2' && $D cp cpc:/etc/motd2 $CPD/ && cat $CPD/motd2"
t cp-out-dir "deep" bash -c "$D exec cpc sh -c 'mkdir -p /opt/x/y; echo deep > /opt/x/y/z' && $D cp cpc:/opt/x $CPD/xx && cat $CPD/xx/y/z"
t cp-out-dir-contents "z" bash -c "mkdir $CPD/contents && $D cp cpc:/opt/x/y/. $CPD/contents && ls $CPD/contents"
t cp-out-stdout "alpine-release" bash -c "$D cp cpc:/etc/alpine-release - | tar -t"
t cp-out-symlink "-> " bash -c "$D exec cpc ln -sf /etc/alpine-release /tmp/rel && $D cp cpc:/tmp/rel - | tar -tv"
t cp-big "match" bash -c "head -c 30000000 /dev/urandom > $CPD/big && $D cp $CPD/big cpc:/tmp/big && a=\$(shasum -a 256 $CPD/big | cut -c1-64); b=\$($D exec cpc sha256sum /tmp/big | cut -c1-64); [ \$a = \$b ] && echo match"
code cp-missing 1 $D cp cpc:/nope "$CPD/"
code cp-into-missing-dir 1 $D cp "$CPD/a.txt" cpc:/nodir/
$D create --name cpcreated alpine cat /tmp/a.txt >/dev/null
t cp-into-created "one" bash -c "$D cp $CPD/a.txt cpcreated:/tmp/ && $D start -a cpcreated"
t cp-from-stopped "a.txt" bash -c "$D cp cpcreated:/tmp/a.txt - | tar -t"
$D rm -f cpc cpcreated >/dev/null; rm -rf "$CPD"

section "privileged"
t priv-caps "000001ffffffffff" $D run --rm --privileged alpine grep CapEff /proc/self/status
t priv-mount "mounted" $D run --rm --privileged alpine sh -c 'mount -t tmpfs t /mnt && echo mounted'
t priv-devices "fuse" $D run --rm --privileged alpine ls /dev
t priv-cgroup-rw "ok" $D run --rm --privileged alpine sh -c 'mkdir /sys/fs/cgroup/sub && echo ok'
t unpriv-no-mount "denied" $D run --rm alpine sh -c 'mount -t tmpfs t /mnt 2>/dev/null || echo denied'
t priv-inspect "true" bash -c "$D run -d --name pv --privileged alpine sleep 30 >/dev/null; $D inspect -f '{{.HostConfig.Privileged}}' pv"
t priv-exec-caps "000001ffffffffff" $D exec pv grep CapEff /proc/self/status
$D rm -f pv >/dev/null

section "kernel: netfilter, tc and interfaces"
# Every line of tests/kernel-features.sh (nftables expressions, the iptables
# matches and targets, ipset, IPVS, tc, ss, macvlan/WireGuard/IPsec...) is
# one check: Ctrs's guest kernel builds them all in, as it loads no modules.
KFEAT=$(perl -e 'alarm 180; exec @ARGV' $D run --rm --privileged -v "$(cd "$(dirname "$0")" && pwd)/kernel-features.sh:/k.sh:ro" alpine:3.22 sh /k.sh 2>&1 | tr -d '\r')
# One check per line; the line itself is what shows when it fails.
for name in $(printf '%s\n' "$KFEAT" | grep -E '^[a-z0-9-]+ (ok|FAIL)' | cut -d' ' -f1); do
  t "kernel-$name" "$name ok" bash -c 'printf "%s\n" "$1" | grep -E "^$2 (ok|FAIL)"' _ "$KFEAT" "$name"
done
printf '%s\n' "$KFEAT" | grep -qE '^[a-z0-9-]+ (ok|FAIL)' || t kernel-features "ok" printf '%s\n' "$KFEAT"

section "images: tag, save, load"
IMD=$(mktemp -d)
t tag "ctrs-test/alp:v1" bash -c "$D tag alpine ctrs-test/alp:v1 && $D images --format '{{.Repository}}:{{.Tag}}'"
t tag-same-id "same" bash -c "[ \"\$($D images -q alpine:latest)\" = \"\$($D images -q ctrs-test/alp:v1)\" ] && echo same"
t save "manifest.json" bash -c "$D save -o $IMD/a.tar ctrs-test/alp:v1 && tar -tf $IMD/a.tar"
t rmi-tag-only "Untagged" $D rmi ctrs-test/alp:v1
t alpine-still-there "alpine" $D images --format '{{.Repository}}'
t load "Loaded image: ctrs-test/alp:v1" $D load -i "$IMD/a.tar"
t load-runs "3." $D run --rm ctrs-test/alp:v1 cat /etc/alpine-release
t load-stdin "Loaded image" bash -c "$D rmi ctrs-test/alp:v1 >/dev/null; $D load < $IMD/a.tar"
code load-garbage 1 bash -c "echo nope | $D load"
$D rmi ctrs-test/alp:v1 >/dev/null 2>&1; rm -rf "$IMD"

section "docker build (BuildKit in the VM)"
BD=$(mktemp -d)
# BuildKit builder for the engine under test, addressed by its endpoint,
# never through a docker context. Re-point it every run: a scratch engine
# gets a fresh socket, and a builder left over from an earlier run would
# fail every build with no hint why.
BX=${CTRS_BUILDER:-ctrs-build-e2e}
# `rm -f` removes the config even when its endpoint is dead (it reports
# failure either way); a fresh builder is then created on the socket.
docker buildx rm -f "$BX" >/dev/null 2>&1 || true
docker buildx create --name "$BX" --driver docker-container --driver-opt default-load=true "unix://$SOCK" >/dev/null
printf 'FROM alpine\nRUN echo built > /built\nARG MSG=default\nRUN echo "$MSG" > /msg\nCOPY data.txt /data.txt\nCMD ["cat","/built","/msg","/data.txt"]\n' > "$BD/Dockerfile"
echo "from context" > "$BD/data.txt"
t build "importing to docker" bash -c "cd $BD && BUILDX_BUILDER=$BX perl -e 'alarm 300; exec @ARGV' $D build --build-arg MSG=hello -t ctrs-test/built . 2>&1"
t build-runs "from context" $D run --rm ctrs-test/built
t build-arg "hello" $D run --rm ctrs-test/built
t build-cached "CACHED" bash -c "cd $BD && BUILDX_BUILDER=$BX $D build --progress plain --build-arg MSG=hello -t ctrs-test/built . 2>&1"
t build-network "curl" bash -c "cd $BD && printf 'FROM alpine\nRUN apk add --no-cache curl\n' > Dockerfile.net && BUILDX_BUILDER=$BX perl -e 'alarm 300; exec @ARGV' $D build -f Dockerfile.net -t ctrs-test/net . >/dev/null 2>&1 && $D run --rm ctrs-test/net curl --version"
# Build steps keep Ctrs's resolver (and with it the Mac's): no 8.8.8.8.
t build-resolvconf "nameserver 172.17.0.1" bash -c "cd $BD && printf 'FROM alpine\nRUN cat /etc/resolv.conf\n' > Dockerfile.dns && BUILDX_BUILDER=$BX perl -e 'alarm 300; exec @ARGV' $D build --no-cache --progress plain -f Dockerfile.dns . 2>&1"
code build-no-public-resolver 1 bash -c "cd $BD && BUILDX_BUILDER=$BX perl -e 'alarm 300; exec @ARGV' $D build --no-cache --progress plain -f Dockerfile.dns . 2>&1 | grep -q 'nameserver 8.8.8.8'"
t build-dns "Address" bash -c "cd $BD && printf 'FROM alpine\nRUN nslookup example.com\n' > Dockerfile.lookup && BUILDX_BUILDER=$BX perl -e 'alarm 300; exec @ARGV' $D build --no-cache --progress plain -f Dockerfile.lookup . 2>&1"
t build-fails "exit code: 3" bash -c "cd $BD && printf 'FROM alpine\nRUN exit 3\n' > Dockerfile.bad && BUILDX_BUILDER=$BX $D build -f Dockerfile.bad . 2>&1"
printf 'FROM alpine\nENTRYPOINT ["/bin/echo"]\nCMD ["hello-from-image"]\n' > "$BD/Dockerfile.ep"
BUILDX_BUILDER=$BX $D build -f "$BD/Dockerfile.ep" -t ctrs-test/ep-cmd "$BD" >/dev/null 2>&1 || echo "  FAIL build-ep-cmd (image did not build)"
t create-empty-cmd "hello-from-image" bash -c "cid=\$(curl -s --unix-socket $SOCK -X POST -H 'Content-Type: application/json' -d '{\"Image\":\"ctrs-test/ep-cmd\",\"Cmd\":[]}' http://x/containers/create | python3 -c 'import json,sys; print(json.load(sys.stdin)[\"Id\"])') && curl -s --unix-socket $SOCK -X POST \"http://x/containers/\$cid/start\" -o /dev/null && sleep 1 && out=\$(curl -s --unix-socket $SOCK \"http://x/containers/\$cid/logs?stdout=true\") && echo \"\$out\" | grep -o hello-from-image; curl -s --unix-socket $SOCK -X DELETE \"http://x/containers/\$cid?force=true\" -o /dev/null"
$D rmi ctrs-test/built ctrs-test/net ctrs-test/ep-cmd >/dev/null 2>&1; rm -rf "$BD"

section "registry: login, push, pull"
REG=$(mktemp -d); export DOCKER_CONFIG_SAVED=${DOCKER_CONFIG:-}
# A throwaway client config: no keychain, nothing of the user's touched.
mkdir -p "$REG/cfg"; echo '{"auths":{}}' > "$REG/cfg/config.json"; ln -s ~/.docker/cli-plugins "$REG/cfg/cli-plugins"; ln -s ~/.docker/contexts "$REG/cfg/contexts"
$D run --rm httpd:2.4-alpine htpasswd -Bbn ctrsuser ctrspass > "$REG/htpasswd" 2>/dev/null
$D run -d --name reg -p 5055:5000 -v "$REG:/auth" -e REGISTRY_AUTH=htpasswd -e REGISTRY_AUTH_HTPASSWD_REALM=ctrs -e REGISTRY_AUTH_HTPASSWD_PATH=/auth/htpasswd registry:2 >/dev/null
ready http://localhost:5055/v2/
R="env DOCKER_CONFIG=$REG/cfg $D"
t login-wrong "incorrect username or password" bash -c "echo nope | $R login localhost:5055 -u ctrsuser --password-stdin 2>&1"
t login "Login Succeeded" bash -c "echo ctrspass | $R login localhost:5055 -u ctrsuser --password-stdin 2>&1"
t push "digest: sha256:" bash -c "$R tag alpine localhost:5055/team/alp:1 && $R push localhost:5055/team/alp:1 2>&1"
t push-again "already exists" bash -c "$R push localhost:5055/team/alp:1 2>&1"
# Deploy tools pin to the RepoDigest after a push: it must be the manifest the
# registry has, not the image ID or the index alpine was pulled from.
t push-repo-digest "same" bash -c "d=\$($R push localhost:5055/team/alp:1 2>&1 | sed -n 's/.*digest: \(sha256:[0-9a-f]*\).*/\1/p'); [ -n \"\$d\" ] && [ \"\$($R image inspect localhost:5055/team/alp:1 --format '{{index .RepoDigests 0}}')\" = localhost:5055/team/alp@\$d ] && echo same"
t pull-auth "3." bash -c "$R rmi localhost:5055/team/alp:1 >/dev/null && $R pull -q localhost:5055/team/alp:1 >/dev/null && $R run --rm localhost:5055/team/alp:1 cat /etc/alpine-release"
t pull-no-auth "pull access denied" bash -c "$R logout localhost:5055 >/dev/null; $R rmi localhost:5055/team/alp:1 >/dev/null; $R pull localhost:5055/team/alp:1 2>&1"
t push-no-auth "authentication required" bash -c "$R tag alpine localhost:5055/team/alp:2 && $R push localhost:5055/team/alp:2 2>&1"
# Not pushed, so no RepoDigest: not alpine's from Docker Hub, nor one made up.
t push-failed-no-digest "[]" $R image inspect localhost:5055/team/alp:2 --format '{{json .RepoDigests}}'
$D rmi localhost:5055/team/alp:2 >/dev/null 2>&1; $D rm -f reg >/dev/null; rm -rf "$REG"

section "limits, stats, top, pause, update"
$D run -d --name lim --memory 128m --cpus 0.5 --pids-limit 50 --cpu-shares 512 nginx:alpine >/dev/null; sleep 0.5
t limit-memory "134217728" $D exec lim cat /sys/fs/cgroup/memory.max
t limit-cpus "50000 100000" $D exec lim cat /sys/fs/cgroup/cpu.max
t limit-pids "50" $D exec lim cat /sys/fs/cgroup/pids.max
t limit-shares "20" $D exec lim cat /sys/fs/cgroup/cpu.weight
t limit-inspect "134217728 500000000 50" $D inspect -f '{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}} {{.HostConfig.PidsLimit}}' lim
t oom-kill "137" bash -c "$D run --rm --memory 32m alpine sh -c 'tail /dev/zero' >/dev/null 2>&1; echo \$?"
t stats "128MiB" $D stats --no-stream --format '{{.MemUsage}}' lim
t stats-pids "PIDS" $D stats --no-stream lim
t stats-stream "lim" bash -c "perl -e 'alarm 3; exec @ARGV' $D stats --format '{{.Name}}' lim 2>/dev/null | head -1"
t top "nginx: master process" $D top lim
t top-ps-titles "PPID" $D top lim
t pause "paused" bash -c "$D pause lim >/dev/null && $D inspect -f '{{.State.Status}}' lim"
t pause-ps "(Paused)" $D ps --filter name=lim --format '{{.Status}}'
t pause-exec-refused "is paused" $D exec lim true
t pause-filter "lim" $D ps --filter status=paused --format '{{.Names}}'
t unpause "running" bash -c "$D unpause lim >/dev/null && $D inspect -f '{{.State.Status}}' lim"
t unpause-works "Welcome" $D exec lim wget -qO- http://127.0.0.1
t update-memory "268435456" bash -c "$D update --memory 256m lim >/dev/null && $D exec lim cat /sys/fs/cgroup/memory.max"
t update-cpus "200000 100000" bash -c "$D update --cpus 2 lim >/dev/null && $D exec lim cat /sys/fs/cgroup/cpu.max"
t update-kept "268435456" bash -c "$D restart -t 1 lim >/dev/null && $D exec lim cat /sys/fs/cgroup/memory.max"
t update-restart-policy "always" bash -c "$D update --restart always lim >/dev/null && $D inspect -f '{{.HostConfig.RestartPolicy.Name}}' lim"
t stop-paused "exited" bash -c "$D pause lim >/dev/null; $D stop -t 2 lim >/dev/null && $D inspect -f '{{.State.Status}}' lim"
$D rm -f lim >/dev/null

section "rename, diff, export, commit, history"
$D run -d --name ren alpine sleep 120 >/dev/null
t rename "ren2" bash -c "$D rename ren ren2 && $D ps --format '{{.Names}}' --filter name=ren2"
code rename-taken 1 bash -c "$D run -d --name ren3 alpine sleep 60 >/dev/null; $D rename ren2 ren3"
$D rm -f ren3 >/dev/null
t diff-added "A /added" bash -c "$D exec ren2 sh -c 'echo hi > /added; rm /etc/motd; echo c >> /etc/profile' && $D diff ren2"
t diff-deleted "D /etc/motd" $D diff ren2
t diff-changed "C /etc/profile" $D diff ren2
t export "bin/busybox" bash -c "$D export ren2 | tar -t | grep -x bin/busybox"
t export-has-change "added" bash -c "$D export ren2 | tar -t | grep -x added"
t commit "sha256:" $D commit -c 'CMD ["cat","/added"]' -c 'ENV CTRS=1' ren2 ctrs-test/committed:1
t commit-runs "hi" $D run --rm ctrs-test/committed:1
t commit-env "CTRS=1" $D run --rm ctrs-test/committed:1 env
t commit-whiteout "gone" bash -c "$D run --rm ctrs-test/committed:1 sh -c 'test -e /etc/motd || echo gone'"
t history "docker commit" $D history ctrs-test/committed:1
t history-base "<missing>" $D history ctrs-test/committed:1
t commit-stopped "sha256:" bash -c "$D stop -t 1 ren2 >/dev/null && $D commit ren2 ctrs-test/committed:2"
$D rm -f ren2 >/dev/null; $D rmi ctrs-test/committed:1 ctrs-test/committed:2 >/dev/null 2>&1

section "network connect and disconnect"
$D network create na >/dev/null; $D network create nb >/dev/null
$D run -d --name multi --network na nginx:alpine >/dev/null; sleep 0.3
t connect "eth1" bash -c "$D network connect --alias web2 nb multi && $D exec multi ip -o link"
t connect-dns-alias "Welcome" $D run --rm --network nb alpine wget -qO- -T 3 http://web2
t connect-dns-name "Welcome" $D run --rm --network nb alpine wget -qO- -T 3 http://multi
t connect-inspect "na nb" bash -c "$D inspect -f '{{range \$k, \$v := .NetworkSettings.Networks}}{{\$k}} {{end}}' multi"
t connect-members "multi" $D network inspect nb -f '{{range .Containers}}{{.Name}}{{end}}'
t connect-survives-restart "eth1" bash -c "$D restart -t 1 multi >/dev/null && $D exec multi ip -o link"
code connect-twice 1 $D network connect nb multi
t disconnect "no-eth1" bash -c "$D network disconnect nb multi && ($D exec multi ip -o link | grep -q eth1 && echo still || echo no-eth1)"
t disconnect-dns-gone "bad address" $D run --rm --network nb alpine wget -qO- -T 2 http://web2
t compose-multi-net "PONG" bash -c "d=\$(mktemp -d); printf 'services:\n  db:\n    image: redis:7-alpine\n    networks: [back]\n  app:\n    image: redis:7-alpine\n    command: sh -c \"sleep 1; redis-cli -h db ping; sleep 30\"\n    networks: [front, back]\nnetworks:\n  front: {}\n  back: {}\n' > \$d/compose.yaml; cd \$d && $D compose -p ctrsnet up -d >/dev/null 2>&1; sleep 3; $D compose -p ctrsnet logs app; $D compose -p ctrsnet down >/dev/null 2>&1; rm -rf \$d"
$D rm -f multi >/dev/null; $D network rm na nb >/dev/null

section "events, prune, system df, search"
t events "start" bash -c "($D events --filter container=evt --format '{{.Action}}' & p=\$!; sleep 0.5; $D run --name evt alpine true >/dev/null; sleep 0.5; kill \$p) 2>/dev/null"
# The CLI rounds --since/--until durations to whole seconds; -1s is "a second from now".
t events-since "die" bash -c "$D events --since 30s --until=-1s --filter container=evt --format '{{.Action}} {{.Actor.Attributes.exitCode}}'"
t events-type "destroy" bash -c "$D rm evt >/dev/null; $D events --since 30s --until=-1s --filter type=container --filter event=destroy --format '{{.Action}}'"
t events-json "timeNano" bash -c "$D events --since 30s --until=-1s --format '{{json .}}' | head -1"
# Prune only what this suite labels: never the user's stopped containers.
t container-prune "Total reclaimed space" bash -c "$D create --name prunable --label ctrs-e2e=1 alpine >/dev/null; $D container prune -f --filter label=ctrs-e2e=1"
code pruned-gone 1 $D inspect prunable
t system-df "Images" $D system df
t system-df-v "VOLUME NAME" $D system df -v
# Real sizes, measured on the engine's disk: a volume and a container that
# each hold 20 MiB (it once reported every volume as unknown, every
# container as 0 and images at their download size).
t system-df-sizes "SIZES-OK" bash -c "$D rm -f e2e-dfc >/dev/null 2>&1; $D volume rm e2e-dfv >/dev/null 2>&1; $D run --rm -v e2e-dfv:/d alpine sh -c 'head -c 20971520 /dev/urandom > /d/f' && $D run --name e2e-dfc alpine sh -c 'head -c 20971520 /dev/urandom > /f' && curl -s --unix-socket $(printf %q "$SOCK") http://ctrs/system/df | python3 -c 'import json,sys; d=json.load(sys.stdin); v=[x[\"UsageData\"][\"Size\"] for x in d[\"Volumes\"] if x[\"Name\"]==\"e2e-dfv\"]; c=[x[\"SizeRw\"] for x in d[\"Containers\"] if \"/e2e-dfc\" in x[\"Names\"]]; i=[x for x in d[\"Images\"] if x[\"Size\"]<=0]; print(\"SIZES-OK\" if v and v[0]>=20971520 and c and c[0]>=20971520 and not i and d[\"LayersSize\"]>0 else (v, c, len(i)))'; $D rm -f e2e-dfc >/dev/null; $D volume rm e2e-dfv >/dev/null"
t search "alpine" $D search alpine --limit 3
t search-official "[OK]" $D search --filter is-official=true alpine --limit 3

section "amd64 images (Rosetta)"
t rosetta-uname "x86_64" $D run --rm --platform linux/amd64 alpine uname -m
t rosetta-binary "x86-64" bash -c "$D run --rm --platform linux/amd64 alpine sh -c 'apk add -q --no-cache file >/dev/null 2>&1; file /bin/busybox'"
t rosetta-inspect "linux/amd64" $D image inspect -f '{{.Os}}/{{.Architecture}}' alpine
t rosetta-amd64-only-repo "x86_64" $D run --rm amd64/alpine:3.22 uname -m
t rosetta-node "v22" $D run --rm --platform linux/amd64 node:22-alpine node --version
t native-again "aarch64" bash -c "$D pull -q --platform linux/arm64 alpine >/dev/null && $D pull -q --platform linux/arm64 node:22-alpine >/dev/null && $D run --rm alpine uname -m"
$D rmi amd64/alpine:3.22 >/dev/null 2>&1

section "security: seccomp, capabilities, read-only"
# Docker's two defaults in a container's own network: any port and ping
# without root. --sysctl wins; host networking keeps the VM's own.
t unpriv-port-start "0" $D run --rm alpine cat /proc/sys/net/ipv4/ip_unprivileged_port_start
t unpriv-ping-range "0	2147483647" $D run --rm alpine cat /proc/sys/net/ipv4/ping_group_range
t unpriv-listen-80 "listening" $D run --rm -u 1000 alpine sh -c 'nc -lk -p 80 >/dev/null 2>&1 & sleep 0.5; netstat -ltn | grep -q ":80 " && echo listening'
t unpriv-sysctl-wins "1024" $D run --rm --sysctl net.ipv4.ip_unprivileged_port_start=1024 alpine cat /proc/sys/net/ipv4/ip_unprivileged_port_start
t unpriv-port-host-net "1024" $D run --rm --network host alpine cat /proc/sys/net/ipv4/ip_unprivileged_port_start
t seccomp-on "Seccomp:	2" $D run --rm alpine grep Seccomp: /proc/self/status
t seccomp-userns "not permitted" $D run --rm alpine unshare -U true
t seccomp-keyctl "not permitted" bash -c "$D run --rm alpine sh -c 'apk add -q keyutils >/dev/null 2>&1; keyctl show 2>&1'"
t seccomp-unconfined "userns-ok" $D run --rm --security-opt seccomp=unconfined alpine unshare -U echo userns-ok
t seccomp-privileged-boundary "Seccomp:	2" $D run --rm --privileged alpine grep Seccomp: /proc/self/status
t vsock-unconfined "Address family not supported" $D run --rm --security-opt seccomp=unconfined python:3.13-alpine python -c 'import socket; socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)'
t vsock-privileged "Address family not supported" $D run --rm --privileged python:3.13-alpine python -c 'import socket; socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)'
t seccomp-exec "Seccomp:	2" bash -c "$D run -d --name sec alpine sleep 30 >/dev/null; $D exec sec grep Seccomp: /proc/self/status"
$D rm -f sec >/dev/null
t seccomp-threads "threads ok" $D run --rm python:3.13-alpine python -c 'import threading; t=threading.Thread(target=print,args=("threads ok",)); t.start(); t.join()'
t stdin-200mb "200000000" bash -c "head -c 200000000 /dev/zero | $D run --rm -i alpine wc -c"
t stdin-slow-reader "30000000" bash -c "head -c 30000000 /dev/zero | $D run --rm -i alpine sh -c 'sleep 2; wc -c'"
t seccomp-fork "node ok" $D run --rm node:22-alpine node -e 'require("child_process").execSync("true"); console.log("node ok")'
t cap-default "00000000a80425fb" $D run --rm alpine grep CapEff /proc/self/status
t cap-drop-all "0000000000000000" $D run --rm --cap-drop ALL alpine grep CapEff /proc/self/status
# ping needs no NET_RAW: it uses ping sockets, which ping_group_range opens
# to every group, as on Docker. Without them, dropping NET_RAW stops it.
t cap-drop-net-raw-ping "round-trip" $D run --rm --cap-drop NET_RAW alpine ping -c1 -W1 127.0.0.1
t cap-drop-net-raw "permission denied" $D run --rm --cap-drop NET_RAW --sysctl net.ipv4.ping_group_range="1 0" alpine ping -c1 -W1 127.0.0.1
t cap-add-net-admin "ok" bash -c "$D run --rm --cap-add NET_ADMIN alpine sh -c 'ip link set lo mtu 1400 && echo ok'"
t cap-add-sys-admin "mounted" $D run --rm --cap-add SYS_ADMIN alpine sh -c 'mount -t tmpfs t /mnt && echo mounted'
t cap-inspect "NET_ADMIN]" bash -c "$D create --name capi --cap-add NET_ADMIN alpine >/dev/null; $D inspect -f '{{.HostConfig.CapAdd}}' capi; $D rm capi >/dev/null"
code cap-unknown 125 $D run --rm --cap-add NOPE alpine true
t read-only "Read-only file system" $D run --rm --read-only alpine touch /x
t read-only-tmpfs "ok" bash -c "$D run --rm --read-only --tmpfs /tmp alpine sh -c 'touch /tmp/x && echo ok'"
t read-only-volume "ok" bash -c "$D run --rm --read-only -v rovol:/data alpine sh -c 'touch /data/x && echo ok'; $D volume rm rovol >/dev/null"
t shm-size "256.0M" $D run --rm --shm-size 256m alpine df -h /dev/shm
t shm-default "64.0M" $D run --rm alpine df -h /dev/shm
t no-new-privs "NoNewPrivs:	1" $D run --rm --security-opt no-new-privileges alpine grep NoNewPrivs /proc/self/status

section "UDP ports"
$D run -d --name dns -p 15354:53/udp -p 15354:53/tcp alpine sh -c 'apk add -q dnsmasq >/dev/null 2>&1; dnsmasq -k --address=/ctrs.test/10.9.8.7' >/dev/null
for _ in $(seq 40); do dig +short +time=1 +tries=1 @127.0.0.1 -p 15354 ctrs.test 2>/dev/null | grep -q 10.9.8.7 && break; sleep 0.3; done
t udp-dns "10.9.8.7" dig +short +time=2 +tries=1 @127.0.0.1 -p 15354 ctrs.test
t udp-dns-tcp-same-port "10.9.8.7" dig +short +tcp +time=2 @127.0.0.1 -p 15354 ctrs.test
t udp-many "20" bash -c "n=0; for i in \$(seq 20); do dig +short +time=2 +tries=1 @127.0.0.1 -p 15354 ctrs.test | grep -q 10.9.8.7 && n=\$((n+1)); done; echo \$n"
t udp-port-listed "53/udp -> 0.0.0.0:15354" $D port dns
t udp-inspect "53/udp" $D inspect -f '{{json .NetworkSettings.Ports}}' dns
$D rm -f dns >/dev/null
code udp-port-free-after 0 bash -c "python3 -c 'import socket; s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.bind((\"0.0.0.0\", 15354))'"

section "stop signal"
t stop-signal "got USR1" bash -c "$D run -d --name sig --stop-signal USR1 alpine sh -c 'trap \"echo got USR1; exit 0\" USR1; while :; do sleep 0.1; done' >/dev/null; sleep 0.5; $D stop -t 5 sig >/dev/null; $D logs sig; $D rm -f sig >/dev/null"
t stop-signal-inspect "exited (0)" bash -c "$D run -d --name sig2 --stop-signal SIGRTMIN+3 alpine sh -c 'trap \"exit 0\" 37; while :; do sleep 0.1; done' >/dev/null; sleep 0.5; $D stop -t 5 sig2 >/dev/null; $D ps -a --filter name=sig2 --format '{{.Status}}' | tr A-Z a-z | cut -c1-10; $D rm -f sig2 >/dev/null"


section "errors"
t bad-image-name "invalid" $D run --rm 'UPPER/case' true
code no-such-image-pull 125 $D run --rm ctrs-test/no-such-image:none true

section "ctrs CLI dispatch (engine vs container)"
# `ctrs stop CONTAINER` must stop the container, not the engine; the engine's
# own lifecycle lives under `ctrs engine`.
CTRS=$(cd "$(dirname "$0")/.." && pwd)/target/release/ctrs
if [ -x "$CTRS" ]; then
  ki() { CTRS_SOCKET="$SOCK" perl -e 'alarm 120; exec @ARGV' "$CTRS" "$@"; }
  $D run -d --name ci-dispatch-a alpine sleep 120 >/dev/null 2>&1
  $D run -d --name ci-dispatch-b alpine sleep 120 >/dev/null 2>&1
  ki stop ci-dispatch-a >/dev/null 2>&1
  t dispatch-stop-container "exited" $D inspect -f '{{.State.Status}}' ci-dispatch-a
  t dispatch-engine-alive "ci-dispatch-b" $D ps --format '{{.Names}}' --filter name=ci-dispatch-b
  t dispatch-engine-responds "OK" bash -c "printf 'GET /_ping HTTP/1.0\r\n\r\n' | curl -s --unix-socket '$SOCK' http://d/_ping"
  ki start ci-dispatch-a >/dev/null 2>&1
  t dispatch-restart-container "running" $D inspect -f '{{.State.Status}}' ci-dispatch-a
  code dispatch-bare-stop-refused 1 env CTRS_SOCKET="$SOCK" "$CTRS" stop
  code dispatch-engine-bogus 1 env CTRS_SOCKET="$SOCK" "$CTRS" engine bogus
  t dispatch-engine-status "running" env CTRS_SOCKET="$SOCK" "$CTRS" engine status
  $D rm -f ci-dispatch-a ci-dispatch-b >/dev/null 2>&1
else
  skip 'ctrs CLI dispatch' 'target/release/ctrs not built'
fi

cleanup

if [ "${SOAK:-0}" -gt 0 ]; then
  section "soak: $SOAK containers, checking for leaks"
  DPID=$(pgrep -f 'release/ctrs daemon' | head -1)
  fp() { footprint "$DPID" 2>/dev/null | sed -n 's/.*Footprint: \([0-9.]* [KMG]*B\).*/\1/p' | head -1; }
  fds() { lsof -p "$DPID" 2>/dev/null | wc -l | tr -d ' '; }
  guest() { $D run --rm --network host alpine sh -c 'echo "$(ls /var/lib/ctrs/containers 2>/dev/null | wc -l) $(ls -d /sys/fs/cgroup/ctrs/*/ 2>/dev/null | wc -l) $(ip -o link | grep -c " kv") $(ls /run/ctrs 2>/dev/null | wc -l) $(awk "/MemTotal/{t=\$2} /MemAvailable/{a=\$2} END{print t-a}" /proc/meminfo)"' 2>/dev/null; }
  # The balloon's pages count as used inside the guest; take them out.
  ballooned() { curl -s --unix-socket "$SOCK" http://d/info | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d["CtrsMemoryCeiling"] - d["CtrsMemoryTarget"]) // 1024)'; }
  # Warm up, then take the baseline.
  for i in $(seq 20); do $D run --rm alpine true >/dev/null 2>&1; done
  read -r c0 g0 v0 r0 m0 <<<"$(guest)"; m0=$((m0 - $(ballooned)))
  f0=$(fds); fp0=$(fp)
  echo "  start: daemon $fp0, $f0 fds; guest: $c0 container dirs, $g0 cgroups, $v0 veths, $r0 run dirs, $m0 kB used"
  t0=$(date +%s)
  failures=0
  al() { perl -e 'alarm 20; exec @ARGV' "$@"; }
  for i in $(seq "$SOAK"); do
    case $((i % 5)) in
      0) al $D run --rm --network none alpine true >/dev/null 2>&1 || failures=$((failures + 1)) ;;
      1) al $D run --rm alpine sh -c 'echo x' >/dev/null 2>&1 || failures=$((failures + 1)) ;;
      2)
        out=$(echo in | al $D run -i --rm alpine cat 2>&1)
        if [ "$out" != "in" ]; then
          failures=$((failures + 1))
          echo "  run $i: stdin case got [$out]; still running:"
          for c in $($D ps -q); do
            echo "    $($D inspect -f '{{.Name}} {{.Config.Cmd}}' "$c"): $(al $D exec "$c" ls -l /proc/1/fd 2>&1 | tr '\n' ' ')"
          done
        fi
        ;;
      3) id=$(al $D run -d alpine sleep 30) && al $D exec "$id" true >/dev/null 2>&1 && al $D rm -f "$id" >/dev/null 2>&1 || failures=$((failures + 1)) ;;
      4) al $D run --rm -p 18190:80 alpine true >/dev/null 2>&1 || failures=$((failures + 1)) ;;
    esac
  done
  secs=$(($(date +%s) - t0))
  sleep 1
  read -r c1 g1 v1 r1 m1 <<<"$(guest)"; m1=$((m1 - $(ballooned)))
  f1=$(fds); fp1=$(fp)
  echo "  end:   daemon $fp1, $f1 fds; guest: $c1 container dirs, $g1 cgroups, $v1 veths, $r1 run dirs, $m1 kB used"
  echo "  $SOAK runs in ${secs}s, $failures failed"
  t soak-no-failures "0" echo "$failures"
  t soak-container-dirs "$c0" echo "$c1"
  t soak-cgroups "$g0" echo "$g1"
  # veths from just before the soak may still be on their way out; never more.
  t soak-veths "ok" bash -c "[ $v1 -le $v0 ] && echo ok || echo 'veths $v0 -> $v1'"
  t soak-run-dirs "$r0" echo "$r1"
  # Allow some slack for kernel caches; a leak of a few hundred containers
  # would show as far more than 16 extra fds or 32 MB.
  t soak-fds "ok" bash -c "[ $f1 -le $((f0 + 16)) ] && echo ok || echo 'fds $f0 -> $f1'"
  t soak-guest-memory "ok" bash -c "[ $m1 -le $((m0 + 32768)) ] && echo ok || echo 'guest used $m0 -> $m1 kB'"
fi

printf '\n%d passed, %d failed, %d skipped\n' "$PASS" "$FAIL" "$SKIP"
for f in "${FAILED[@]+"${FAILED[@]}"}"; do echo "  failed: $f"; done
[ "$FAIL" -eq 0 ]
