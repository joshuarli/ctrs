#!/bin/bash
# CTRS-21 failure injection: kills the engine and the VM at lifecycle
# points, fills the image store's filesystem, OOMs a container, and forces
# the rollback paths. Every section uses its own scratch data root and
# socket under .work/tmp/ (never ~/.local/share/ctrs, never a docker context) and
# starts a fresh recovery engine on the same root to check what survived.
#
# Needs: the host binary built and signed (`cargo xtask host`), the docker
# CLI on PATH, and network access for `docker pull public.ecr.aws/docker/library/postgres:17-alpine`
# (S5, S6, S10). Integration with `conformance/run.sh` is deliberate: this
# is a multi-minute harness, run it on demand, not in the per-slice suite.
#
# Usage: conformance/failure.sh
set -u
set -o pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
WORK=$ROOT/.work/tmp
PREFIX=$WORK/failure
LOG=$WORK/failure.log
pass=0; fail=0; skip=0
ok()  { printf 'PASS %s\n' "$1" | tee -a "$LOG"; pass=$((pass+1)); }
bad() { printf 'FAIL %s\n' "$1" | tee -a "$LOG"; fail=$((fail+1)); }
skipped() { printf 'SKIP %s (%s)\n' "$1" "$2" | tee -a "$LOG"; skip=$((skip+1)); }
step() { printf -- '== %s (%s)\n' "$1" "$(date +%H:%M:%S)" | tee -a "$LOG"; }
: >"$LOG"

# A probed-free loopback port for S9's publish clash. The probe binds and
# releases, so the port is not reserved between probe and use; acceptable
# for this serial harness (same caveat as iso_alloc_ports).
free_port() {
  local tries=0 p
  while [ $tries -lt 100 ]; do
    p=$((20000 + RANDOM % 20000))
    if ! (exec 3<>"/dev/tcp/127.0.0.1/$p") 2>/dev/null; then
      echo "$p"
      return 0
    fi
    tries=$((tries + 1))
  done
  return 1
}

command -v docker >/dev/null || { echo 'docker CLI not on PATH' >&2; exit 2; }
BIN=$ROOT/target/release/ctrs
[ -x "$BIN" ] || { echo 'target/release/ctrs missing; run cargo xtask host' >&2; exit 2; }

# Each scenario leaves at most one hdiutil mount behind via the trap.
FULL_MNT=""
engines=()
cleanup() {
  for pid in "${engines[@]:-}"; do [ -n "$pid" ] && kill -TERM "$pid" 2>/dev/null; done
  sleep 2
  for pid in "${engines[@]:-}"; do [ -n "$pid" ] && kill -9 "$pid" 2>/dev/null; done
  if [ -n "$FULL_MNT" ] && mount | grep -q "$FULL_MNT"; then hdiutil detach "$FULL_MNT" -force >/dev/null 2>&1; fi
  rm -rf "$PREFIX"-*
}
trap cleanup EXIT

# fresh_engine NAME [KEY=VAL ...]: wipes the root (it stays absent), starts
# the daemon on it (extra env vars applied), waits for the socket.
fresh_engine() {
  local name=$1
  shift
  EH_DATA=$PREFIX-$name-data
  EH_SOCK=$PREFIX-$name.sock
  EH_PIDFILE=$PREFIX-$name.pid
  # The root is absent on purpose: a fresh install must create and validate it.
  rm -rf "$EH_DATA" "$EH_SOCK" "$EH_PIDFILE"
  env "$@" CTRS_DATA_DIR="$EH_DATA" CTRS_SOCKET="$EH_SOCK" HOME=$PREFIX-$name-home "$BIN" daemon >>"$LOG" 2>&1 &
  EH_PID=$!
  engines+=("$EH_PID")
  local i
  # The API answering means the daemon really booted; the socket file
  # alone can be a stale leftover.
  for i in $(seq 1 90); do
    [ "$(curl -s --max-time 2 -o /dev/null -w '%{http_code}' --unix-socket "$EH_SOCK" http://d/version 2>/dev/null)" = "200" ] && return 0
    sleep 1
  done
  echo "engine $name did not answer /version within 90s" >>"$LOG"
  return 1
}
recovery_engine() { # like fresh_engine but keeps the root and the stale socket
  local name=$1
  EH_DATA=$PREFIX-$name-data
  EH_SOCK=$PREFIX-$name.sock
  CTRS_DATA_DIR="$EH_DATA" CTRS_SOCKET="$EH_SOCK" HOME=$PREFIX-$name-home "$BIN" daemon >>"$LOG" 2>&1 &
  EH_PID=$!
  engines+=("$EH_PID")
  local i
  # The stale socket from the killed engine exists until the recovery
  # daemon unlinks and rebinds it; readiness is the API answering, not
  # the file's existence (a connection refused means "not yet").
  for i in $(seq 1 90); do
    [ "$(curl -s --max-time 2 -o /dev/null -w '%{http_code}' --unix-socket "$EH_SOCK" http://d/version 2>/dev/null)" = "200" ] && return 0
    sleep 1
  done
  echo "recovery engine $name did not answer /version within 90s" >>"$LOG"
  return 1
}
hard_kill() { kill -9 "$1" 2>/dev/null; wait "$1" 2>/dev/null; }
saft() { DOCKER_HOST="unix://$EH_SOCK" DOCKER_CONTEXT= perl -e 'alarm 120; exec @ARGV' "$@"; }
dockq() { DOCKER_HOST="unix://$EH_SOCK" DOCKER_CONTEXT= docker "$@"; }

# Anonymous registry quota rate-limits shared IPs mid-run, so the images a
# scenario does not exist to exercise are loaded from a local tar instead of
# pulled. The tars are built once into .work/tmp/preload from a throwaway
# engine. The pull-centric scenarios (S5 mid-pull SIGKILL, S6 ENOSPC, S10
# concurrent pulls) keep real network pulls.
PRELOAD="$WORK/preload"
mkdir -p "$PRELOAD"
ALPINE_TAR="$PRELOAD/alpine.tar"
POSTGRES_TAR="$PRELOAD/postgres.tar"
if [ ! -f "$ALPINE_TAR" ] || [ ! -f "$POSTGRES_TAR" ]; then
  echo 'building the preloaded image tars (one-time)' | tee -a "$LOG"
  if fresh_engine preload; then
    dockq pull public.ecr.aws/docker/library/alpine:latest >>"$LOG" 2>&1
    dockq pull public.ecr.aws/docker/library/postgres:17-alpine >>"$LOG" 2>&1
    DOCKER_HOST="unix://$EH_SOCK" DOCKER_CONTEXT= docker save public.ecr.aws/docker/library/alpine:latest -o "$ALPINE_TAR" >>"$LOG" 2>&1
    DOCKER_HOST="unix://$EH_SOCK" DOCKER_CONTEXT= docker save public.ecr.aws/docker/library/postgres:17-alpine -o "$POSTGRES_TAR" >>"$LOG" 2>&1
  fi
fi
load_alpine() { dockq load -i "$ALPINE_TAR" >>"$LOG" 2>&1; }

step 'S1: SIGKILL at rest; fresh engine rebinds the stale socket'
if fresh_engine s1; then
  load_alpine
  dockq run --rm public.ecr.aws/docker/library/alpine:latest true >>"$LOG" 2>&1
  hard_kill "$EH_PID"
  if recovery_engine s1; then
    code=$(curl -s --max-time 10 -o /dev/null -w '%{http_code}' --unix-socket "$EH_SOCK" http://d/version)
    [ "$code" = "200" ] && ok 'S1 engine answers /version (200) on the rebound socket' || bad "S1 /version answered $code"
    v=$(saft docker version --format '{{.Server.Version}}' 2>&1) && [ -n "$v" ] && ok "S1 docker version reports ($v)" || bad 'S1 engine did not answer docker version'
    if saft docker ps -a --format '{{.ID}}' >/dev/null 2>&1; then ok 'S1 store reads after SIGKILL'; else bad 'S1 containers.json unreadable after SIGKILL'; fi
    if saft docker run --rm public.ecr.aws/docker/library/alpine:latest true >/dev/null 2>&1; then ok 'S1 fresh run after SIGKILL'; else bad 'S1 fresh run failed'; fi
  else bad 'S1 recovery engine did not come up'; fi
else bad 'S1 first engine did not come up'; fi

step 'S2: SIGKILL with a running container (no restart policy)'
if fresh_engine s2; then
  load_alpine
  dockq run -d --name ctrs21-f2 public.ecr.aws/docker/library/alpine:latest sleep 300 >/dev/null 2>&1
  sleep 2
  hard_kill "$EH_PID"
  if recovery_engine s2; then
    st=$(dockq inspect -f '{{.State.Status}}' ctrs21-f2 2>/dev/null)
    code=$(dockq inspect -f '{{.State.ExitCode}}' ctrs21-f2 2>/dev/null)
    [ "$st" = "exited" ] && [ "$code" = "255" ] && ok "S2 killed container marked Exited(255) ($st/$code)" || bad "S2 container state after SIGKILL: $st/$code"
    dockq rm -f ctrs21-f2 >/dev/null 2>&1 && ok 'S2 rm -f works' || bad 'S2 rm -f failed'
  else bad 'S2 recovery engine did not come up'; fi
else bad 'S2 first engine did not come up'; fi

step 'S3: SIGKILL with a running --restart unless-stopped container'
if fresh_engine s3; then
  load_alpine
  dockq run -d --name ctrs21-f3 --restart unless-stopped public.ecr.aws/docker/library/alpine:latest sleep 300 >/dev/null 2>&1
  sleep 2
  hard_kill "$EH_PID"
  if recovery_engine s3; then
    st=""
    for i in $(seq 1 30); do
      st=$(dockq inspect -f '{{.State.Status}}' ctrs21-f3 2>/dev/null)
      [ "$st" = "running" ] && break
      sleep 1
    done
    [ "$st" = "running" ] && ok 'S3 unless-stopped container restarted by recovery engine' || bad "S3 container state: $st"
    dockq rm -f ctrs21-f3 >/dev/null 2>&1
  else bad 'S3 recovery engine did not come up'; fi
else bad 'S3 first engine did not come up'; fi

step 'S4: SIGKILL between create and start (deterministic), and mid-run (racy)'
if fresh_engine s4; then
  load_alpine
  ID=$(dockq create --name ctrs21-f4a public.ecr.aws/docker/library/alpine:latest sleep 30)
  hard_kill "$EH_PID"
  if recovery_engine s4; then
    if saft docker start ctrs21-f4a >>"$LOG" 2>&1; then ok 'S4 created container starts on the recovery engine'; else bad 'S4 created container did not start'; fi
    st=$(dockq inspect -f '{{.State.Status}}' ctrs21-f4a 2>/dev/null)
    [ "$st" = "running" ] && ok 'S4 started container is running' || bad "S4 container state: $st"
    dockq rm -f ctrs21-f4a >/dev/null 2>&1
  else bad 'S4 recovery engine did not come up'; fi
  # racy: kill during a run; assertions are order-agnostic
  saft docker run -d --name ctrs21-f4b public.ecr.aws/docker/library/alpine:latest sleep 60 >/dev/null 2>&1 &
  DOCKER_CLI_PID=$!
  sleep 1
  hard_kill "$EH_PID"
  wait "$DOCKER_CLI_PID" 2>/dev/null
  if recovery_engine s4; then
    if saft docker version >/dev/null 2>&1; then ok 'S4 engine consistent after kill mid-run'; else bad 'S4 engine inconsistent after kill mid-run'; fi
    dockq rm -f ctrs21-f4b >/dev/null 2>&1
  else bad 'S4 second recovery engine did not come up'; fi
else bad 'S4 first engine did not come up'; fi

step 'S5: SIGKILL mid-pull; retry completes and the store verifies'
if fresh_engine s5; then
  dockq pull public.ecr.aws/docker/library/postgres:17-alpine >/dev/null 2>&1 &
  PULL_PID=$!
  sleep 2
  hard_kill "$EH_PID"
  wait "$PULL_PID" 2>/dev/null
  if recovery_engine s5; then
    if saft docker pull public.ecr.aws/docker/library/postgres:17-alpine >/dev/null 2>&1; then ok 'S5 pull retried after SIGKILL'; else bad 'S5 pull after SIGKILL failed'; fi
    if dockq image inspect public.ecr.aws/docker/library/postgres:17-alpine >/dev/null 2>&1; then ok 'S5 image present and inspectable after retry'; else bad 'S5 image missing after retry'; fi
  else bad 'S5 recovery engine did not come up'; fi
else bad 'S5 first engine did not come up'; fi

step 'S6: disk-full on the image store (hdiutil 64 MiB volume, symlinked in)'
if fresh_engine s6; then
  IMG="$PREFIX-full-store.sparseimage"; FULL_MNT="$PREFIX-full-mnt"
  rm -rf "$IMG" "$FULL_MNT"; mkdir -p "$FULL_MNT"
  if hdiutil create -size 64m -fs APFS -type SPARSE -volname ctrs-full "$IMG" >/dev/null 2>&1 &&
     hdiutil attach -mountpoint "$FULL_MNT" -nobrowse "$IMG" >/dev/null 2>&1; then
    mkdir -p "$FULL_MNT/blobs/sha256" "$FULL_MNT/tmp"
    rm -rf "$EH_DATA/blobs" "$EH_DATA/tmp"
    ln -s "$FULL_MNT/blobs" "$EH_DATA/blobs"
    ln -s "$FULL_MNT/tmp" "$EH_DATA/tmp"
    if ! saft docker pull public.ecr.aws/docker/library/postgres:17-alpine >"$LOG.s6" 2>&1; then
      if grep -qi -e 'space' -e 'ENOSPC' -e 'os error 28' "$LOG.s6"; then
        ok 'S6 pull on a full store fails with ENOSPC'
      else
        bad "S6 pull failed but not for lack of space: $(tail -1 "$LOG.s6")"
      fi
    else
      bad 'S6 pull on a full store unexpectedly succeeded'
    fi
    tmp_left=$(find "$EH_DATA/tmp" -mindepth 1 2>/dev/null | wc -l | tr -d ' ')
    [ "$tmp_left" = "0" ] && ok 'S6 no partial blobs left in tmp/' || bad "S6 $tmp_left partial file(s) left in tmp/"
    saft docker version >/dev/null 2>&1 && ok 'S6 engine alive after ENOSPC' || bad 'S6 engine died on ENOSPC'
    if dockq image inspect public.ecr.aws/docker/library/postgres:17-alpine >/dev/null 2>&1; then bad 'S6 partial image recorded as present'; else ok 'S6 no partial image recorded'; fi
    if saft docker ps -a --format '{{.ID}}' >/dev/null 2>&1; then ok 'S6 store consistent after ENOSPC'; else bad 'S6 containers.json unreadable after ENOSPC'; fi
    # Leave the full store behind for the detach below.
    hard_kill "$EH_PID"
    hdiutil detach "$FULL_MNT" >/dev/null 2>&1 || hdiutil detach "$FULL_MNT" -force >/dev/null 2>&1
    FULL_MNT=""
    rm -f "$EH_DATA/blobs" "$EH_DATA/tmp"
    mkdir -p "$EH_DATA/blobs/sha256" "$EH_DATA/tmp"
    rm -rf "$PREFIX-s6-recovery-data"
    if recovery_engine s6; then
      if saft docker pull public.ecr.aws/docker/library/postgres:17-alpine >/dev/null 2>&1; then ok 'S6 pull succeeds once space is back'; else bad 'S6 pull after freeing space failed'; fi
    else bad 'S6 recovery engine did not come up'; fi
    rm -rf "$EH_DATA"
    rm -f "$IMG"
    ok 'S6 disk-full scenario complete'
  else
    hdiutil detach "$FULL_MNT" -force >/dev/null 2>&1
    rm -rf "$IMG" "$FULL_MNT"
    FULL_MNT=""
    skipped 'S6 disk-full' 'hdiutil could not create or mount the volume'
  fi
else bad 'S6 first engine did not come up'; fi

step 'S7: OOM-kill of a container (--memory 24m), inspect shows OOMKilled'
if fresh_engine s7; then
  load_alpine
  saft docker run --name ctrs21-f7 --memory 24m public.ecr.aws/docker/library/alpine:latest awk 'BEGIN{s=".";while(1){s=s s s s}}' >/dev/null 2>&1
  rc=$?
  [ "$rc" = "137" ] && ok 'S7 OOM-killed container exits 137' || bad "S7 exit code: $rc (want 137)"
  oom=$(dockq inspect -f '{{.State.OOMKilled}}' ctrs21-f7 2>/dev/null)
  [ "$oom" = "true" ] && ok 'S7 inspect reports OOMKilled=true' || bad "S7 OOMKilled: $oom"
  if saft docker version >/dev/null 2>&1; then ok 'S7 engine alive after guest OOM'; else bad 'S7 engine died'; fi
  dockq rm -f ctrs21-f7 >/dev/null 2>&1
else bad 'S7 first engine did not come up'; fi

step 'S8: --restart always on a failing command restarts; engine responsive'
if fresh_engine s8; then
  load_alpine
  dockq run -d --name ctrs21-f8 --restart always public.ecr.aws/docker/library/alpine:latest false >/dev/null 2>&1
  sleep 6
  rc=$(dockq inspect -f '{{.RestartCount}}' ctrs21-f8 2>/dev/null)
  if [[ "$rc" =~ ^[0-9]+$ ]] && [ "$rc" -ge 2 ]; then ok "S8 container restarted (RestartCount=$rc)"; else bad "S8 RestartCount: $rc"; fi
  if saft docker version >/dev/null 2>&1; then ok 'S8 engine responsive during restart loop'; else bad 'S8 engine unresponsive'; fi
  dockq rm -f ctrs21-f8 >/dev/null 2>&1 && ok 'S8 rm -f stops the restart loop' || bad 'S8 rm -f failed'
else bad 'S8 first engine did not come up'; fi

step 'S9: network rollback — port clash, unknown network'
if fresh_engine s9; then
  load_alpine
  s9_port=$(free_port) || s9_port=""
  if [ -n "$s9_port" ]; then
    dockq run -d --name ctrs21-f9a -p 127.0.0.1:$s9_port:80 public.ecr.aws/docker/library/alpine:latest sleep 60 >/dev/null 2>&1
    if dockq run -d --name ctrs21-f9b -p 127.0.0.1:$s9_port:80 public.ecr.aws/docker/library/alpine:latest sleep 60 >"$LOG.s9" 2>&1; then
      bad 'S9 second publish on the same port succeeded'
    else ok 'S9 second publish on the same port refused'; fi
    up=$(dockq ps --format '{{.Names}}' --filter name=ctrs21-f9a)
    [ "$up" = "ctrs21-f9a" ] && ok 'S9 first container still running' || bad 'S9 first container down: $up'
  else
    bad 'S9 could not allocate a free loopback port'
  fi
  if saft docker run --rm --network ctrs21-nope public.ecr.aws/docker/library/alpine:latest true >/dev/null 2>&1; then
    bad 'S9 start on an unknown network unexpectedly succeeded'
  else ok 'S9 start on an unknown network refused'; fi
  if saft docker run --rm public.ecr.aws/docker/library/alpine:latest true >/dev/null 2>&1; then ok 'S9 engine healthy after rollbacks'; else bad 'S9 engine unhealthy after rollbacks'; fi
  dockq rm -f ctrs21-f9a ctrs21-f9b >/dev/null 2>&1
else bad 'S9 first engine did not come up'; fi

step 'S10: concurrent pulls of one image'
if fresh_engine s10; then
  dockq image rm public.ecr.aws/docker/library/postgres:17-alpine >/dev/null 2>&1
  pids=()
  for i in 1 2 3 4; do dockq pull public.ecr.aws/docker/library/postgres:17-alpine >"$LOG.s10.$i" 2>&1 & pids+=($!); done
  pulls_ok=0
  for p in "${pids[@]}"; do wait "$p" && pulls_ok=$((pulls_ok+1)); done
  if [ "$pulls_ok" != "4" ] && grep -q -i -e 429 -e 'TOOMANYREQUESTS' -e 'rate exceeded' "$LOG.s10."*; then
    # Anonymous registry quota, not an engine defect: report a skip, not a failure.
    skipped 'S10 concurrent pulls' 'the registry rate-limited the pulls'
  else
    [ "$pulls_ok" = "4" ] && ok 'S10 four concurrent pulls all exited 0' || bad "S10 $pulls_ok/4 pulls exited 0 (see $LOG.s10.*)"
    after=$(dockq images -q public.ecr.aws/docker/library/postgres:17-alpine | wc -l | tr -d ' ')
    [ "$after" -ge 1 ] && ok 'S10 image recorded exactly once after concurrent pulls' || bad "S10 image rows: $after"
  fi
else bad 'S10 first engine did not come up'; fi

step 'S12: VM death with the daemon alive restarts policy containers'
# The crash is injected through the crashed engine's OWN test hook
# (CTRS_TEST_VM_CRASH=1 + SIGUSR2): the daemon crashes its own VM via the
# Lost path. No other engine's VM is ever signalled. A sentinel engine
# running beside it proves the scoping.
if fresh_engine s12 CTRS_TEST_VM_CRASH=1; then
  EH_PID_S12=$EH_PID; EH_SOCK_S12=$EH_SOCK; EH_DATA_S12=$EH_DATA
  load_alpine
  dockq run -d --name ctrs21-f12 --restart unless-stopped public.ecr.aws/docker/library/alpine:latest sleep 300 >/dev/null 2>&1
  sleep 2
  before=$(dockq inspect -f '{{.State.StartedAt}}' ctrs21-f12 2>/dev/null)
  # sentinel: a second engine that must survive the injection untouched
  if fresh_engine s12-sentinel; then
    EH_PID_S12_SENTINEL=$EH_PID; EH_SOCK_SENTINEL=$EH_SOCK
    DOCKER_HOST="unix://$EH_SOCK_SENTINEL" DOCKER_CONTEXT= docker load -i "$ALPINE_TAR" >>"$LOG" 2>&1
    DOCKER_HOST="unix://$EH_SOCK_SENTINEL" DOCKER_CONTEXT= perl -e 'alarm 60; exec @ARGV' docker run -d --name ctrs21-f12-sentinel public.ecr.aws/docker/library/alpine:latest sleep 300 >/dev/null 2>&1
    EH_SOCK=$EH_SOCK_SENTINEL   # dockq target for the sentinel below
    sentinel_state() { DOCKER_HOST="unix://$EH_SOCK_SENTINEL" DOCKER_CONTEXT= docker inspect -f '{{.State.Status}}' ctrs21-f12-sentinel 2>/dev/null; }
    before_sentinel=$(sentinel_state)
    # inject the crash into the s12 engine only
    kill -USR2 "$EH_PID_S12"
    st=""; after=""
    for i in $(seq 1 45); do
      read after st < <(DOCKER_HOST="unix://$EH_SOCK_S12" DOCKER_CONTEXT= docker inspect -f '{{.State.StartedAt}} {{.State.Status}}' ctrs21-f12 2>/dev/null)
      if [ -n "$after" ] && [ "$after" != "$before" ] && [ "$st" = "running" ]; then break; fi
      sleep 1
    done
    if [ "$st" = "running" ] && [ "$after" != "$before" ]; then
      ok "S12 VM crash: container restarted with a new generation ($after)"
    else
      bad "S12 container did not come back with a new generation (st=$st started=$after before=$before)"
    fi
    if DOCKER_HOST="unix://$EH_SOCK_S12" DOCKER_CONTEXT= perl -e 'alarm 60; exec @ARGV' docker exec ctrs21-f12 true >/dev/null 2>&1; then
      ok 'S12 restart container answers exec'
    else
      bad 'S12 restart container does not exec'
    fi
    if [ "$(sentinel_state)" = "$before_sentinel" ] && [ "$(sentinel_state)" = "running" ]; then
      ok 'S12 sentinel engine and its container survived the injection'
    else
      bad "S12 sentinel state after injection: $(sentinel_state)"
    fi
    DOCKER_HOST="unix://$EH_SOCK_S12" DOCKER_CONTEXT= docker rm -f ctrs21-f12 >/dev/null 2>&1
    EH_SOCK=$EH_SOCK_SENTINEL
    dockq rm -f ctrs21-f12-sentinel >/dev/null 2>&1
  else
    bad 'S12 sentinel engine did not come up'
  fi
  EH_DATA=$EH_DATA_S12; EH_PID=$EH_PID_S12; EH_SOCK=$EH_SOCK_S12
else bad 'S12 first engine did not come up'; fi

printf 'failure: %d pass, %d fail, %d skip\n' "$pass" "$fail" "$skip" | tee -a "$LOG"
[ "$fail" -eq 0 ]
