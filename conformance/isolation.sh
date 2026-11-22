#!/bin/bash
# CTRS-21 boundary spot checks: the host's control socket and the guest's
# host-services relays must not leak into a container, default or
# --privileged. Reuses $CTRS_SOCKET when set, else boots a scratch engine
# (never ~/.local/share/ctrs, never a docker context). Exits non-zero on any miss.
set -u
cd "$(dirname "$0")/.."
ROOT=$PWD
WORK=$ROOT/.work/tmp
OWN_ENGINE=0
pass=0; fail=0
host_env_pattern='^(CTRS_[^=]*|DOCKER_HOST|DOCKER_CONTEXT)='
ok()  { printf 'PASS %s\n' "$1"; pass=$((pass+1)); }
bad() { printf 'FAIL %s\n' "$1"; fail=$((fail+1)); }

if [ -z "${CTRS_SOCKET:-}" ]; then
  DATA=$WORK/isolation-data; HOME_DIR=$WORK/isolation-home; SOCK=$WORK/isolation.sock
  rm -rf "$DATA" "$HOME_DIR" "$SOCK"; mkdir -p "$DATA" "$HOME_DIR"
  CTRS_DATA_DIR="$DATA" CTRS_SOCKET="$SOCK" HOME="$HOME_DIR" "$ROOT/target/release/ctrs" daemon >>"$WORK/isolation.log" 2>&1 &
  DPID=$!
  OWN_ENGINE=1
  i=0; for i in $(seq 1 90); do [ -S "$SOCK" ] && break; sleep 1; done
  [ -S "$SOCK" ] || { echo 'engine did not open the socket' >&2; kill -9 $DPID 2>/dev/null; exit 2; }
  export CTRS_SOCKET="$SOCK"
fi
export DOCKER_HOST="unix://$CTRS_SOCKET"
unset DOCKER_CONTEXT
perl -e 'alarm 300; exec @ARGV' docker pull alpine >/dev/null 2>&1
[ "$OWN_ENGINE" = "1" ] && DATA_ROOT="$DATA" || DATA_ROOT=${CTRS_DATA_DIR:-}

mode() { stat -f '%Lp' "$1" 2>/dev/null; }

m=$(mode "$CTRS_SOCKET")
[ "$m" = "600" ] && ok 'I1 host socket is 0600' || bad "I1 host socket mode: $m (want 600)"
if [ -n "$DATA_ROOT" ]; then
  m=$(mode "$DATA_ROOT")
  [ "$m" = "700" ] && ok 'I2 data root is 0700' || bad "I2 data root mode: $m (want 700)"
else
  echo 'note: set CTRS_DATA_DIR to check the data root of a reused engine'
fi

check() { # NAME [DOCKER-ARGS...]
  local name=$1; shift
  local got leaks
  if got=$(perl -e 'alarm 120; exec @ARGV' docker run --rm "$@" alpine sh -c \
    'for p in /var/run/docker.sock /run/docker.sock /mnt/mac /run/host-services /run/host-services/ssh-auth.sock /run/host-services/docker.sock; do [ -e "$p" ] && echo "present:$p"; done; env | grep -E "^(CTRS_|DOCKER_HOST|DOCKER_CONTEXT)" || true' 2>&1); then
    leaks=$(printf '%s\n' "$got" | grep -E "^present:|$host_env_pattern" || true)
    if [ -z "$leaks" ]; then ok "$name"; else bad "$name ($leaks)"; fi
  else
    bad "$name (docker run exited $?: $got)"
  fi
}
check 'I3 default container sees no host socket, relay, or virtiofs share'
check 'I4 privileged container sees no host socket, relay, or virtiofs share' --privileged

if container_env=$(perl -e 'alarm 120; exec @ARGV' docker run --rm alpine env 2>&1); then
  env_leak=$(printf '%s\n' "$container_env" | grep -E "$host_env_pattern" || true)
  [ -z "$env_leak" ] && ok 'I5 container env carries no host engine variables' || bad "I5 env leak: $env_leak"
else
  bad "I5 reading container env (docker run exited $?: $container_env)"
fi

if [ "$OWN_ENGINE" = "1" ]; then
  kill -TERM "$DPID" 2>/dev/null
  i=0; for i in $(seq 1 10); do kill -0 "$DPID" 2>/dev/null || break; sleep 1; done
  kill -0 "$DPID" 2>/dev/null && kill -9 "$DPID"
  rm -rf "$WORK/isolation-data" "$WORK/isolation-home" "$WORK/isolation.sock" "$WORK/isolation.log"
fi
printf 'isolation: %d pass, %d fail\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
