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
printf 'fixture: %s\n' "$ROOT"
FAIL=0
for CASE in host-loss guest-overflow; do
  if [ -n "${CTRS_WATCH_CASE:-}" ] && [ "$CTRS_WATCH_CASE" != "$CASE" ]; then continue; fi
  ADDED=
  TREE="$ROOT/$CASE"
  CONTROL="$ROOT/$CASE-control"
  mkdir -p "$TREE" "$CONTROL"
  if ! python3 - "$TREE" "$ROOT/branch" <<'PY'
import os, sys
p = sys.argv[1]
for i in range(22000):
    with open(os.path.join(p, f'f{i:05}'), 'w') as f:
        f.write('before\n')
for i in range(1000):
    branch = f'branch-{i:04}'
    directory = os.path.join(p, branch)
    os.mkdir(directory)
    if [e.name for e in os.scandir(p)].index(branch) >= 20500: break
    os.rmdir(directory)
else: raise RuntimeError('could not place a directory past the reconciliation limit')
for name in ('modified', 'deleted'):
    with open(os.path.join(directory, name), 'w') as f: f.write('before\n')
with open(sys.argv[2], 'w') as f: f.write(branch)
PY
  then echo "FAIL $CASE: fixture tree or traversal order"; FAIL=1; continue; fi
  BRANCH=$(cat "$ROOT/branch")
  docker run -d --name "wr-$CASE" -e WATCH_BRANCH="$BRANCH" -v "$TREE:/w" -v "$CONTROL:/noise" -v "$(dirname "$GATE"):/gate" alpine sh -c '
    mkdir /tmp/derived
    cp -R /w/. /tmp/derived/
    inotifyd - /w:cwnmyd "/w/$WATCH_BRANCH:cwnmyd" | while read -r ev dir name; do
      [ -n "$name" ] || continue
      dest="/tmp/derived${dir#/w}/$name"
      if [ -f "$dir/$name" ]; then cp "$dir/$name" "$dest"; else unlink "$dest" 2>/dev/null || :; fi
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
  if [ -n "${CTRS_TEST_PIN_ADDED:-}" ]; then
    if ! python3 - "$TREE" "$ROOT/added" <<'PY'
import os, sys
for i in range(1000):
    name = f'added-{i:04}'
    path = os.path.join(sys.argv[1], name)
    with open(path, 'w') as f: f.write('added\n')
    if [e.name for e in os.scandir(sys.argv[1])].index(name) >= 20000: break
    os.unlink(path)
else: raise RuntimeError('could not place added name past the reconciliation limit')
with open(sys.argv[2], 'w') as f: f.write(name)
PY
    then echo "FAIL $CASE: added-name order"; FAIL=1; docker rm -f "wr-$CASE" >/dev/null; continue; fi
    ADDED=$(cat "$ROOT/added")
    added_seen=0
    for i in $(seq 1 30); do
      if docker exec "wr-$CASE" sh -c '[ "$(cat "/tmp/derived/$1" 2>/dev/null)" = added ]' sh "$ADDED"; then added_seen=1; break; fi
      sleep 1
    done
    if [ "$added_seen" != 1 ]; then echo "FAIL $CASE: added-name preflight"; FAIL=1; docker rm -f "wr-$CASE" >/dev/null; continue; fi
  fi
  if [ -n "${CTRS_TEST_DROP_DCACHE:-}" ]; then
    docker exec --privileged "wr-$CASE" sh -c 'set -e; mkdir -p /tmp/recovery-proc; mount -t proc proc /tmp/recovery-proc; sync; echo 2 > /tmp/recovery-proc/sys/vm/drop_caches; umount /tmp/recovery-proc' || { echo "FAIL $CASE: cannot drop guest caches"; FAIL=1; docker rm -f "wr-$CASE" >/dev/null; continue; }
  fi
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
    touch "$GATE.overflow"
    triggered=0
    for i in $(seq 1 100); do
      if tail -c +"$LOG_OFFSET" "$LOG" | rg -q 'test gate collecting bind mount changes for guest overflow'; then triggered=1; break; fi
      sleep .1
    done
  fi
  if ! python3 - "$TREE" "$ROOT/names" "${ADDED:-}" "$BRANCH" <<'PY2'
import os, sys
p = sys.argv[1]
names = [e.name for e in os.scandir(p)]
assert len(names) > 21002
modified, deleted = [name for name in names[21000:] if name.startswith('f')][:2]
if sys.argv[3]:
    deleted = sys.argv[3]
    assert names.index(deleted) >= 20000
with open(os.path.join(p, modified), 'w') as f: f.write('after\n')
os.unlink(os.path.join(p, deleted))
for i in range(1000):
    created = f'new-{i:04}'
    path = os.path.join(p, created)
    with open(path, 'w') as f: f.write('new\n')
    if [e.name for e in os.scandir(p)].index(created) >= 20000: break
    os.unlink(path)
else: raise RuntimeError('could not place creation past the reconciliation limit')
with open(os.path.join(p, sys.argv[4], 'modified'), 'w') as f: f.write('after\n')
os.unlink(os.path.join(p, sys.argv[4], 'deleted'))
with open(os.path.join(p, sys.argv[4], 'created'), 'w') as f: f.write('new\n')
assert [e.name for e in os.scandir(p)].index(sys.argv[4]) >= 20000
with open(sys.argv[2], 'w') as f: f.write(f'{modified} {deleted} {created}\n')
PY2
  then
    echo "FAIL $CASE: fixture order"; FAIL=1
    if [ "$CASE" = host-loss ]; then unlink "$GATE"; else unlink "$GATE.overflow"; fi
    docker rm -f "wr-$CASE" >/dev/null
    continue
  fi
  read -r MODIFIED DELETED CREATED < "$ROOT/names"
  if [ -n "${CTRS_TEST_ACCESS_WHILE_LOST:-}" ]; then
    sleep 2
    if ! docker exec "wr-$CASE" sh -c '[ "$(cat "/w/$1" 2>/dev/null)" = after ] && [ ! -e "/w/$2" ]' sh "$MODIFIED" "$DELETED"; then
      echo "FAIL $CASE: direct-read revalidation was not observed"; FAIL=1
    fi
  fi
  if [ "$CASE" = host-loss ]; then
    sleep 2; unlink "$GATE"
  else
    sleep 2; unlink "$GATE.overflow"
    for i in $(seq 1 100); do
      if tail -c +"$CONSOLE_OFFSET" "$DATA/vm-console.log" | rg -q 'host change events did not fit; the share is rescanned'; then break; fi
      sleep .1
    done
    if ! tail -c +"$CONSOLE_OFFSET" "$DATA/vm-console.log" | rg -q 'host change events did not fit; the share is rescanned'; then triggered=0; fi
  fi
  if [ "$triggered" != 1 ]; then
    echo "FAIL $CASE: loss condition not observed"; FAIL=1
  elif [ "$CASE" = host-loss ]; then
    tail -c +"$LOG_OFFSET" "$LOG" | rg -m 1 'test gate suppressed bind mount change notifications'
  else
    tail -c +"$CONSOLE_OFFSET" "$DATA/vm-console.log" | rg -m 1 'host change events did not fit; the share is rescanned'
    for captured_path in "$TREE/$MODIFIED" "$TREE/$DELETED" "$TREE/$CREATED" "$TREE/$BRANCH/modified" "$TREE/$BRANCH/deleted" "$TREE/$BRANCH/created"; do
      if ! tail -c +"$LOG_OFFSET" "$LOG" | rg -F -q "path=$captured_path"; then
        echo "FAIL $CASE: real event was not captured: $captured_path"; FAIL=1
      fi
    done
  fi
  converged=0
  deadline=$((SECONDS + 30))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if docker exec "wr-$CASE" sh -c '[ "$(cat "/tmp/derived/$1" 2>/dev/null)" = after ] && [ ! -e "/tmp/derived/$2" ] && [ "$(cat "/tmp/derived/$3" 2>/dev/null)" = new ] && [ "$(cat "/tmp/derived/$4/modified" 2>/dev/null)" = after ] && [ ! -e "/tmp/derived/$4/deleted" ] && [ "$(cat "/tmp/derived/$4/created" 2>/dev/null)" = new ]' sh "$MODIFIED" "$DELETED" "$CREATED" "$BRANCH" 2>/dev/null; then
      if docker exec "wr-$CASE" sh -c 'diff -rq /w /tmp/derived >/dev/null' 2>/dev/null; then converged=1; fi
      break
    fi
    sleep 1
  done
  if [ "$CASE" = guest-overflow ] && tail -c +"$LOG_OFFSET" "$LOG" | rg -q 'bind mount change notifications were lost; the guest revalidates|test overflow gate capacity exceeded'; then
    echo "FAIL $CASE: host loss or test gate overflow"; FAIL=1
  fi
  if [ "$converged" = 1 ] && [ "$triggered" = 1 ]; then echo "PASS $CASE: loss observed and watcher converged"; else echo "FAIL $CASE: watcher did not converge within 30 seconds"; FAIL=1; fi
  if [ "$converged" = 1 ] || [ -z "${CTRS_KEEP_WATCH_FAILURE:-}" ]; then docker rm -f "wr-$CASE" >/dev/null; fi
 done
exit "$FAIL"
