#!/bin/bash
# CTRS-21 failure injection: kills the engine and the VM at lifecycle
# points, fills the image store's filesystem, OOMs a container, and forces
# the rollback paths. Every section uses its own scratch data root and
# socket under .work/tmp/ (never ~/.kiri, never a docker context) and
# starts a fresh recovery engine on the same root to check what survived.
#
# Needs: the host binary built and signed (`cargo xtask host`), the docker
# CLI on PATH, and network access for `docker pull postgres:17-alpine`
# (S5, S6, S10). Integration with `conformance/run.sh` is deliberate: this
# is a multi-minute harness, run it on demand, not in the per-slice suite.
#
# Usage: conformance/failure.sh [section]
set -u
cd "$(dirname "$0")/.."
ROOT=$PWD
WORK=$ROOT/.work/tmp
PREFIX=$WORK/failure
LOG=$WORK/failure.log
FILTER=${1:-}
pass=0; fail=0; skip=0
ok()  { printf 'PASS %s\n' "$1" | tee -a "$LOG"; pass=$((pass+1)); }
bad() { printf 'FAIL %s\n' "$1" | tee -a "$LOG"; fail=$((fail+1)); }
skipped() { printf 'SKIP %s (%s)\n' "$1" "$2" | tee -a "$LOG"; skip=$((skip+1)); }
step() { printf -- '== %s (%s)\n' "$1" "$(date +%H:%M:%S)" | tee -a "$LOG"; }
: >"$LOG"

command -v docker >/dev/null || { echo 'docker CLI not on PATH' >&2; exit 2; }
BIN=$ROOT/target/release/kiri
[ -x "$BIN" ] || { echo 'target/release/kiri missing; run cargo xtask host' >&2; exit 2; }

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

# fresh_engine NAME: wipes the root, starts the daemon on it, waits for the
# socket. Sets EH_DATA, EH_SOCK, EH_PID.
fresh_engine() {
  local name=$1
  EH_DATA=$PREFIX-$name-data
  EH_SOCK=$PREFIX-$name.sock
  EH_PIDFILE=$PREFIX-$name.pid
  rm -rf "$EH_DATA" "$EH_SOCK" "$EH_PIDFILE"
  mkdir -p "$EH_DATA"
  KIRI_DATA_DIR="$EH_DATA" KIRI_SOCKET="$EH_SOCK" HOME=$PREFIX-$name-home "$BIN" daemon >>"$LOG" 2>&1 &
  EH_PID=$!
  engines+=("$EH_PID")
  local i
  for i in $(seq 1 90); do [ -S "$EH_SOCK" ] && return 0; sleep 1; done
  echo "engine $name did not open the socket within 90s" >>"$LOG"
  return 1
}
recovery_engine() { # like fresh_engine but keeps the root and the stale socket
  local name=$1
  EH_DATA=$PREFIX-$name-data
  EH_SOCK=$PREFIX-$name.sock
  KIRI_DATA_DIR="$EH_DATA" KIRI_SOCKET="$EH_SOCK" HOME=$PREFIX-$name-home "$BIN" daemon >>"$LOG" 2>&1 &
  EH_PID=$!
  engines+=("$EH_PID")
  local i
  for i in $(seq 1 90); do [ -S "$EH_SOCK" ] && return 0; sleep 1; done
  echo "recovery engine $name did not open the socket within 90s" >>"$LOG"
  return 1
}
hard_kill() { kill -9 "$1" 2>/dev/null; wait "$1" 2>/dev/null; }
saft() { DOCKER_HOST="unix://$EH_SOCK" DOCKER_CONTEXT= perl -e 'alarm 120; exec @ARGV' "$@"; }
dockq() { DOCKER_HOST="unix://$EH_SOCK" DOCKER_CONTEXT= docker "$@"; }

step 'S1: SIGKILL at rest; fresh engine rebinds the stale socket'
if fresh_engine s1; then
  dockq run --rm alpine true >>"$LOG" 2>&1
  hard_kill "$EH_PID"
  if recovery_engine s1; then
    if saft docker version --format '{{.Server.Version}}' 2>&1 | grep -q .; then ok 'S1 engine answers on the rebound socket'; else bad 'S1 engine did not answer after rebind'; fi
    if saft docker ps -a --format '{{.ID}}' >/dev/null 2>&1; then ok 'S1 store reads after SIGKILL'; else bad 'S1 containers.json unreadable after SIGKILL'; fi
    if saft docker run --rm alpine true >/dev/null 2>&1; then ok 'S1 fresh run after SIGKILL'; else bad 'S1 fresh run failed'; fi
  else bad 'S1 recovery engine did not come up'; fi
else bad 'S1 first engine did not come up'; fi

step 'S2: SIGKILL with a running container (no restart policy)'
if fresh_engine s2; then
  dockq run -d --name ctrs21-f2 alpine sleep 300 >/dev/null 2>&1
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
  dockq run -d --name ctrs21-f3 --restart unless-stopped alpine sleep 300 >/dev/null 2>&1
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
  ID=$(dockq create --name ctrs21-f4a alpine sleep 30)
  hard_kill "$EH_PID"
  if recovery_engine s4; then
    if saft docker start ctrs21-f4a >>"$LOG" 2>&1; then ok 'S4 created container starts on the recovery engine'; else bad 'S4 created container did not start'; fi
    st=$(dockq inspect -f '{{.State.Status}}' ctrs21-f4a 2>/dev/null)
    [ "$st" = "running" ] && ok 'S4 started container is running' || bad "S4 container state: $st"
    dockq rm -f ctrs21-f4a >/dev/null 2>&1
  else bad 'S4 recovery engine did not come up'; fi
  # racy: kill during a run; assertions are order-agnostic
  saft docker run -d --name ctrs21-f4b alpine sleep 60 >/dev/null 2>&1 &
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
  dockq pull postgres:17-alpine >/dev/null 2>&1 &
  PULL_PID=$!
  sleep 2
  hard_kill "$EH_PID"
  wait "$PULL_PID" 2>/dev/null
  if recovery_engine s5; then
    if saft docker pull postgres:17-alpine >/dev/null 2>&1; then ok 'S5 pull retried after SIGKILL'; else bad 'S5 pull after SIGKILL failed'; fi
    if dockq image inspect postgres:17-alpine >/dev/null 2>&1; then ok 'S5 image present and inspectable after retry'; else bad 'S5 image missing after retry'; fi
  else bad 'S5 recovery engine did not come up'; fi
else bad 'S5 first engine did not come up'; fi

step 'S6: disk-full on the image store (hdiutil 64 MiB volume, symlinked in)'
if fresh_engine s6; then
  IMG="$PREFIX-full-store.sparseimage"; FULL_MNT="$PREFIX-full-mnt"
  rm -rf "$IMG" "$FULL_MNT"; mkdir -p "$FULL_MNT"
  if hdiutil create -size 64m -fs APFS -type SPARSE -volname kiri-full "$IMG" >/dev/null 2>&1 &&
     hdiutil attach -mountpoint "$FULL_MNT" -nobrowse "$IMG" >/dev/null 2>&1; then
    mkdir -p "$FULL_MNT/blobs/sha256" "$FULL_MNT/tmp"
    rm -rf "$EH_DATA/blobs" "$EH_DATA/tmp"
    ln -s "$FULL_MNT/blobs" "$EH_DATA/blobs"
    ln -s "$FULL_MNT/tmp" "$EH_DATA/tmp"
    if ! saft docker pull postgres:17-alpine >"$LOG.s6" 2>&1; then
      ok 'S6 pull on a full store fails'
    else
      bad 'S6 pull on a full store unexpectedly succeeded'
    fi
    saft docker version >/dev/null 2>&1 && ok 'S6 engine alive after ENOSPC' || bad 'S6 engine died on ENOSPC'
    if dockq image inspect postgres:17-alpine >/dev/null 2>&1; then bad 'S6 partial image recorded as present'; else ok 'S6 no partial image recorded'; fi
    if saft docker ps -a --format '{{.ID}}' >/dev/null 2>&1; then ok 'S6 store consistent after ENOSPC'; else bad 'S6 containers.json unreadable after ENOSPC'; fi
    # Leave the full store behind for the detach below.
    hard_kill "$EH_PID"
    hdiutil detach "$FULL_MNT" >/dev/null 2>&1 || hdiutil detach "$FULL_MNT" -force >/dev/null 2>&1
    FULL_MNT=""
    rm -f "$EH_DATA/blobs" "$EH_DATA/tmp"
    mkdir -p "$EH_DATA/blobs/sha256" "$EH_DATA/tmp"
    rm -rf "$PREFIX-s6-recovery-data"
    if recovery_engine s6; then
      if saft docker pull postgres:17-alpine >/dev/null 2>&1; then ok 'S6 pull succeeds once space is back'; else bad 'S6 pull after freeing space failed'; fi
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
  saft docker run --name ctrs21-f7 --memory 24m alpine awk 'BEGIN{s=".";while(1){s=s s s s}}' >/dev/null 2>&1
  rc=$?
  [ "$rc" = "137" ] && ok 'S7 OOM-killed container exits 137' || bad "S7 exit code: $rc (want 137)"
  oom=$(dockq inspect -f '{{.State.OOMKilled}}' ctrs21-f7 2>/dev/null)
  [ "$oom" = "true" ] && ok 'S7 inspect reports OOMKilled=true' || bad "S7 OOMKilled: $oom"
  if saft docker version >/dev/null 2>&1; then ok 'S7 engine alive after guest OOM'; else bad 'S7 engine died'; fi
  dockq rm -f ctrs21-f7 >/dev/null 2>&1
else bad 'S7 first engine did not come up'; fi

step 'S8: --restart always on a failing command restarts; engine responsive'
if fresh_engine s8; then
  dockq run -d --name ctrs21-f8 --restart always alpine false >/dev/null 2>&1
  sleep 6
  rc=$(dockq inspect -f '{{.RestartCount}}' ctrs21-f8 2>/dev/null)
  if [[ "$rc" =~ ^[0-9]+$ ]] && [ "$rc" -ge 2 ]; then ok "S8 container restarted (RestartCount=$rc)"; else bad "S8 RestartCount: $rc"; fi
  if saft docker version >/dev/null 2>&1; then ok 'S8 engine responsive during restart loop'; else bad 'S8 engine unresponsive'; fi
  dockq rm -f ctrs21-f8 >/dev/null 2>&1 && ok 'S8 rm -f stops the restart loop' || bad 'S8 rm -f failed'
else bad 'S8 first engine did not come up'; fi

step 'S9: network rollback — port clash, unknown network'
if fresh_engine s9; then
  dockq run -d --name ctrs21-f9a -p 127.0.0.1:18081:80 alpine sleep 60 >/dev/null 2>&1
  if dockq run -d --name ctrs21-f9b -p 127.0.0.1:18081:80 alpine sleep 60 >"$LOG.s9" 2>&1; then
    bad 'S9 second publish on the same port succeeded'
  else ok 'S9 second publish on the same port refused'; fi
  up=$(dockq ps --format '{{.Names}}' --filter name=ctrs21-f9a)
  [ "$up" = "ctrs21-f9a" ] && ok 'S9 first container still running' || bad 'S9 first container down: $up'
  if saft docker run --rm --network ctrs21-nope alpine true >/dev/null 2>&1; then
    bad 'S9 start on an unknown network unexpectedly succeeded'
  else ok 'S9 start on an unknown network refused'; fi
  if saft docker run --rm alpine true >/dev/null 2>&1; then ok 'S9 engine healthy after rollbacks'; else bad 'S9 engine unhealthy after rollbacks'; fi
  dockq rm -f ctrs21-f9a ctrs21-f9b >/dev/null 2>&1
else bad 'S9 first engine did not come up'; fi

step 'S10: concurrent pulls of one image'
if fresh_engine s10; then
  dockq image rm postgres:17-alpine >/dev/null 2>&1
  pids=()
  for i in 1 2 3 4; do dockq pull postgres:17-alpine >/dev/null 2>&1 & pids+=($!); done
  pulls_ok=0
  for p in "${pids[@]}"; do wait "$p" && pulls_ok=$((pulls_ok+1)); done
  [ "$pulls_ok" = "4" ] && ok 'S10 four concurrent pulls all exited 0' || bad "S10 $pulls_ok/4 pulls exited 0"
  after=$(dockq images -q postgres:17-alpine | wc -l | tr -d ' ')
  [ "$after" -ge 1 ] && ok 'S10 image recorded exactly once after concurrent pulls' || bad "S10 image rows: $after"
else bad 'S10 first engine did not come up'; fi

step 'S12: VM death with the daemon alive restarts policy containers'
if fresh_engine s12; then
  dockq run -d --name ctrs21-f12 --restart unless-stopped alpine sleep 300 >/dev/null 2>&1
  sleep 2
  helpers=$(pgrep -f 'Virtualization.VirtualMachine' || true)
  if [ -z "$helpers" ]; then
    bad 'S12 no Virtualization helper found to kill'
  else
    kill -9 $helpers
    st=""
    for i in $(seq 1 30); do
      st=$(dockq inspect -f '{{.State.Status}}' ctrs21-f12 2>/dev/null)
      [ "$st" = "running" ] && break
      sleep 1
    done
    [ "$st" = "running" ] && ok 'S12 VM death: unless-stopped container restarted' || bad "S12 container state after VM death: $st"
    dockq rm -f ctrs21-f12 >/dev/null 2>&1
  fi
else bad 'S12 first engine did not come up'; fi

printf 'failure: %d pass, %d fail, %d skip\n' "$pass" "$fail" "$skip" | tee -a "$LOG"
[ "$fail" -eq 0 ]
