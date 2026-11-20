#!/bin/bash
set -u
SOCK=${CTRS_SOCKET:?set CTRS_SOCKET to the scratch engine socket}
DATA=${CTRS_DATA_DIR:?set CTRS_DATA_DIR to the scratch engine data directory}
LOG=${CTRS_DAEMON_LOG:?set CTRS_DAEMON_LOG to the scratch daemon log}
GATE=${CTRS_TEST_FSEVENTS_GATE:?set CTRS_TEST_FSEVENTS_GATE to the daemon test gate}
export DOCKER_HOST="unix://$SOCK"
unset DOCKER_CONTEXT
ROOT="$PWD/.work/tmp/watch-recovery-fixture-$$"
mkdir -p "$ROOT" "$(dirname "$GATE")"
FAIL=0
for CASE in host-loss guest-overflow; do
  TREE="$ROOT/$CASE"
  CONTROL="$ROOT/$CASE-control"
  mkdir -p "$TREE" "$CONTROL"
  python3 - "$TREE" <<'PY'
import os, sys
p = sys.argv[1]
for i in range(22000):
    with open(os.path.join(p, f'f{i:05}'), 'w') as f:
        f.write('before\n')
PY
  docker run -d --name "wr-$CASE" -v "$TREE:/w" -v "$CONTROL:/noise" -v "$(dirname "$GATE"):/gate" alpine sh -c '
    mkdir /tmp/derived
    cp -R /w/. /tmp/derived/
    inotifyd - /w:cwnmyd | while read -r ev dir name; do
      [ -n "$name" ] || continue
      if [ -f "$dir/$name" ]; then cp "$dir/$name" "/tmp/derived/$name"; else rm -f "/tmp/derived/$name"; fi
    done &
    sleep 1
    touch /tmp/ready
    wait
  ' >/dev/null || { echo "FAIL $CASE: container start"; FAIL=1; continue; }
  ready=0
  for i in $(seq 1 300); do
    if docker exec "wr-$CASE" test -e /tmp/ready 2>/dev/null; then ready=1; break; fi
    sleep 1
  done
  if [ "$ready" != 1 ]; then echo "FAIL $CASE: watcher not ready"; FAIL=1; docker rm -f "wr-$CASE" >/dev/null; continue; fi
  if ! docker exec "wr-$CASE" sh -c 'diff -rq /w /tmp/derived >/dev/null'; then
    echo "FAIL $CASE: initial artifact differs"; FAIL=1; docker rm -f "wr-$CASE" >/dev/null; continue
  fi
  printf 'preflight\n' > "$TREE/f00000"
  preflight=0
  for i in $(seq 1 30); do
    if docker exec "wr-$CASE" sh -c '[ "$(cat /tmp/derived/f00000 2>/dev/null)" = preflight ]'; then preflight=1; break; fi
    sleep 1
  done
  if [ "$preflight" != 1 ]; then echo "FAIL $CASE: watcher preflight"; FAIL=1; docker rm -f "wr-$CASE" >/dev/null; continue; fi
  echo "PASS $CASE: initial artifact and live watcher"
  LOG_OFFSET=$(($(wc -c < "$LOG") + 1))
  CONSOLE_OFFSET=$(($(wc -c < "$DATA/vm-console.log") + 1))
  if [ "$CASE" = host-loss ]; then
    touch "$GATE"
    triggered=0
    for i in $(seq 1 100); do
      if tail -c +"$LOG_OFFSET" "$LOG" | rg -q 'test gate suppressed bind mount change notifications'; then triggered=1; break; fi
      sleep .1
    done
  else
    python3 - "$CONTROL" <<'PY' &
import os, sys
for i in range(40000):
    with open(os.path.join(sys.argv[1], f'n{i:05}'), 'w') as f: f.write('x')
PY
    BURST=$!
    triggered=0
    for i in $(seq 1 300); do
      if tail -c +"$CONSOLE_OFFSET" "$DATA/vm-console.log" | rg -q 'host change events did not fit; the share is rescanned'; then triggered=1; break; fi
      sleep .1
    done
  fi
  if ! python3 - "$TREE" "$ROOT/names" <<'PY2'
import os, sys
p = sys.argv[1]
names = [e.name for e in os.scandir(p)]
assert len(names) > 21002
modified, deleted = names[21000:21002]
with open(os.path.join(p, modified), 'w') as f: f.write('after\n')
os.unlink(os.path.join(p, deleted))
for i in range(1000):
    created = f'new-{i:04}'
    path = os.path.join(p, created)
    with open(path, 'w') as f: f.write('new\n')
    if [e.name for e in os.scandir(p)].index(created) >= 20000: break
    os.unlink(path)
else: raise RuntimeError('could not place creation past the reconciliation limit')
with open(sys.argv[2], 'w') as f: f.write(f'{modified} {deleted} {created}\n')
PY2
  then echo "FAIL $CASE: fixture order"; FAIL=1; fi
  read -r MODIFIED DELETED CREATED < "$ROOT/names"
  if [ "$CASE" = host-loss ]; then sleep 2; unlink "$GATE"; else wait "$BURST"; fi
  if [ "$triggered" != 1 ]; then
    echo "FAIL $CASE: loss condition not observed"; FAIL=1
  elif [ "$CASE" = host-loss ]; then
    tail -c +"$LOG_OFFSET" "$LOG" | rg -m 1 'test gate suppressed bind mount change notifications'
  else
    tail -c +"$CONSOLE_OFFSET" "$DATA/vm-console.log" | rg -m 1 'host change events did not fit; the share is rescanned'
  fi
  converged=0
  deadline=$((SECONDS + 30))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if docker exec "wr-$CASE" sh -c '[ "$(cat "/tmp/derived/$1" 2>/dev/null)" = after ] && [ ! -e "/tmp/derived/$2" ] && [ "$(cat "/tmp/derived/$3" 2>/dev/null)" = new ]' sh "$MODIFIED" "$DELETED" "$CREATED" 2>/dev/null; then
      if docker exec "wr-$CASE" sh -c 'diff -rq /w /tmp/derived >/dev/null' 2>/dev/null; then converged=1; fi
      break
    fi
    sleep 1
  done
  if [ "$converged" = 1 ] && [ "$triggered" = 1 ]; then echo "PASS $CASE: loss observed and watcher converged"; else echo "FAIL $CASE: watcher did not converge within 30 seconds"; FAIL=1; fi
  docker rm -f "wr-$CASE" >/dev/null
 done
exit "$FAIL"
