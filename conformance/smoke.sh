#!/bin/bash
# Round-trip smoke for the headless engine on this Mac.
# Creates a private scratch data root + socket under .work/tmp/, boots the
# VM (kernel guest/out/Image, initramfs.cpio), and round-trips through the
# external docker CLI against the engine's Unix socket. Never touches
# OrbStack, /var/run/docker.sock, docker contexts, or ~/.kiri.
#
# Usage: conformance/smoke.sh
set -u
cd "$(dirname "$0")/.."
ROOT=$PWD
WORK=$ROOT/.work/tmp
DATA=$WORK/smoke-data
HOME_DIR=$WORK/smoke-home
SOCK=$WORK/smoke.sock
LOG=$WORK/smoke.log
: >"$LOG"
pass=0; fail=0
ok()  { printf 'PASS %s\n' "$1" | tee -a "$LOG"; pass=$((pass+1)); }
bad() { printf 'FAIL %s\n' "$1" | tee -a "$LOG"; fail=$((fail+1)); }
step() { printf -- '== %s (%s)\n' "$1" "$(date +%H:%M:%S)" | tee -a "$LOG"; }
t0=$(date +%s)

command -v docker >/dev/null || { echo 'docker CLI not on PATH' >&2; exit 2; }

STATE_BEFORE=""
[ ! -e "$HOME/.kiri" ] || STATE_BEFORE=$(find "$HOME/.kiri" -name '*.log' -o -name '*.txt' 2>/dev/null | sort | xargs stat -f '%m %N' 2>/dev/null | sort)
CTX_BEFORE=$(docker context ls --format '{{.Name}}|{{.Current}}' 2>/dev/null | sort)

step 'clean scratch'
rm -rf "$DATA" "$HOME_DIR"
mkdir -p "$DATA" "$HOME_DIR"
rm -f "$SOCK"

step 'build + ad-hoc sign host binary'
if cargo xtask host >>"$LOG" 2>&1; then
  BIN=$ROOT/target/release/kiri
  [ -x "$BIN" ] && ok 'host binary built + signed' || bad 'host binary missing'
else
  bad 'xtask host'
  BIN=""
fi

if [ -n "$BIN" ]; then
  step 'start daemon (scratch roots)'
  KIRI_DATA_DIR="$DATA" KIRI_SOCKET="$SOCK" HOME="$HOME_DIR" "$BIN" daemon >>"$LOG" 2>&1 &
  DPID=$!
  i=0
  for i in $(seq 1 90); do [ -S "$SOCK" ] && break; sleep 1; done
  if [ -S "$SOCK" ]; then ok "socket up after ${i}s"; else bad 'socket did not appear within 90s'; fi
  sleep 3
  rss_kb=$(ps -o rss= -p "$DPID" 2>/dev/null | tr -d ' ')
  [ -n "$rss_kb" ] && { echo "rss_daemon_kb=$rss_kb" >>"$LOG"; [ "$rss_kb" -le 30720 ] && ok "daemon idle RSS ${rss_kb}KB" || bad "daemon idle RSS ${rss_kb}KB (>30MB)"; }

  export DOCKER_HOST="unix://$SOCK"
  unset DOCKER_CONTEXT

  step 'api version'
  if out=$(perl -e 'alarm 30; exec @ARGV' docker version 2>&1); then
    grep -q '1\.47' <<<"$out" && ok 'api 1.47' || bad "api version: $(grep -i 'api version' <<<"$out" | head -1)"
  else bad "docker version: $out"; fi

  step 'run alpine true'
  t_run=$(date +%s)
  if out=$(perl -e 'alarm 180; exec @ARGV' docker run --rm alpine true 2>&1); then
    ok "run true ($(( $(date +%s) - t_run ))s)"
  else bad "run true: $out"; fi

  step 'run alpine false (exit code)'
  perl -e 'alarm 60; exec @ARGV' docker run --rm alpine false >/dev/null 2>&1; rc=$?
  [ "$rc" -ne 0 ] && ok "exit code $rc propagated" || bad 'exit code 0 for failing container'

  step 'pull cold/hot timing (alpine)'
  t_pull=$(date +%s); docker image rm alpine >/dev/null 2>&1; docker pull alpine >/dev/null 2>&1 && echo "pull_cold=$(( $(date +%s) - t_pull ))s" >>"$LOG"
  t_pull=$(date +%s); docker pull alpine >/dev/null 2>&1 && echo "pull_hot=$(( $(date +%s) - t_pull ))s" >>"$LOG"
  ok 'pull timings recorded'

  step 'exec / logs / rm'
  if docker run -d --name ctrs-smoke alpine sleep 60 >>"$LOG" 2>&1; then
    if perl -e 'alarm 30; exec @ARGV' docker exec ctrs-smoke true >>"$LOG" 2>&1; then ok 'exec'; else bad 'exec'; fi
    if perl -e 'alarm 30; exec @ARGV' docker logs ctrs-smoke >>"$LOG" 2>&1; then ok 'logs'; else bad 'logs'; fi
    docker rm -f ctrs-smoke >>"$LOG" 2>&1 && ok 'rm' || bad 'rm'
  else bad 'run -d'; fi

  step 'published port mapping'
  if docker run -d --name ctrs-smoke-port -p 127.0.0.1:18080:80 alpine sleep 30 >>"$LOG" 2>&1; then
    if out=$(perl -e 'alarm 15; exec @ARGV' docker port ctrs-smoke-port 80/tcp 2>&1) && [[ "$out" == 127.0.0.1:18080* ]]; then
      ok "port mapping: $out"
    else bad "port mapping: $out"; fi
    docker rm -f ctrs-smoke-port >>"$LOG" 2>&1
  else bad 'published port'; fi

  step 'SIGTERM daemon'
  kill -TERM "$DPID" 2>/dev/null
  i=0
  for i in $(seq 1 10); do kill -0 "$DPID" 2>/dev/null || break; sleep 1; done
  if kill -0 "$DPID" 2>/dev/null; then bad 'daemon did not exit within 10s of SIGTERM'; kill -9 "$DPID"; else ok "daemon exited after ${i}s"; fi
  pgrep -f 'kiri-init' >/dev/null && bad 'stale kiri-init process' || ok 'no stale agent'

  step 'host hygiene'
  CTX_AFTER=$(env -u DOCKER_HOST -u DOCKER_CONTEXT docker context ls --format '{{.Name}}|{{.Current}}' 2>/dev/null | sort)
  [ "$CTX_BEFORE" = "$CTX_AFTER" ] && ok 'docker contexts unchanged' || bad 'docker contexts CHANGED'
  STATE_AFTER=""
  [ ! -e "$HOME/.kiri" ] || STATE_AFTER=$(find "$HOME/.kiri" -name '*.log' -o -name '*.txt' 2>/dev/null | sort | xargs stat -f '%m %N' 2>/dev/null | sort)
  if [ "$STATE_BEFORE" = "$STATE_AFTER" ]; then
    ok '~/.kiri untouched'
  else
    bad '~/.kiri was written: '"$(diff <(printf '%s\n' "$STATE_BEFORE") <(printf '%s\n' "$STATE_AFTER") | tail -3 | tr '\n' ' ')"
  fi
fi

printf 'smoke_total=%ss\n' "$(( $(date +%s) - t0 ))" >>"$LOG"
printf 'smoke: %d pass, %d fail\n' "$pass" "$fail" | tee -a "$LOG"
[ "$fail" -eq 0 ]
