#!/bin/bash
set -u
SOCK=${CTRS_SOCKET:?set CTRS_SOCKET to the scratch engine socket}
DATA=${CTRS_DATA_DIR:?set CTRS_DATA_DIR to the scratch engine data directory}
LOG=${CTRS_DAEMON_LOG:?set CTRS_DAEMON_LOG to the scratch daemon log}
GATE=${CTRS_TEST_FSEVENTS_GATE:?set CTRS_TEST_FSEVENTS_GATE to the daemon test gate}
export DOCKER_HOST="unix://$SOCK"
unset DOCKER_CONTEXT
ROOT="$PWD/.work/tmp/watch-recovery-fixture-$$"
if [ -e "$ROOT" ] || [ -e "$GATE" ] || [ -e "$GATE.overflow" ]; then
  echo "FAIL: fixture or gate already exists"
  exit 1
fi
mkdir -p "$(dirname "$GATE")"
mkdir "$ROOT"
CREATED_CONTAINERS=()
CREATED_VOLUMES=()
cleanup() {
  for container in ${CREATED_CONTAINERS[@]+"${CREATED_CONTAINERS[@]}"}; do docker rm -f "$container" >/dev/null 2>&1 || :; done
  for volume in ${CREATED_VOLUMES[@]+"${CREATED_VOLUMES[@]}"}; do docker volume rm "$volume" >/dev/null 2>&1 || :; done
  if [ -e "$GATE" ]; then unlink "$GATE"; fi
  if [ -e "$GATE.overflow" ]; then unlink "$GATE.overflow"; fi
  python3 - "$ROOT" <<'CLEAN'
import os, sys
root = sys.argv[1]
for path, dirs, files in os.walk(root, topdown=True):
    os.chmod(path, 0o700)
    for name in dirs:
        item = os.path.join(path, name)
        if not os.path.islink(item): os.chmod(item, 0o700)
for path, dirs, files in os.walk(root, topdown=False):
    for name in files: os.unlink(os.path.join(path, name))
    for name in dirs:
        item = os.path.join(path, name)
        if os.path.islink(item): os.unlink(item)
        else: os.rmdir(item)
os.rmdir(root)
CLEAN
}
trap cleanup EXIT
cat > "$ROOT/watch-probe.rs" <<'RUST'
use std::ffi::CString;
use std::io::{Read, Write};
use std::os::fd::FromRawFd;
use std::os::raw::{c_char, c_int};

unsafe extern "C" {
    fn inotify_init1(flags: c_int) -> c_int;
    fn inotify_add_watch(fd: c_int, path: *const c_char, mask: u32) -> c_int;
}

fn main() {
    let fd = unsafe { inotify_init1(0) };
    assert!(fd >= 0);
    let path = CString::new(std::env::args().nth(1).unwrap()).unwrap();
    let mode = std::env::args().nth(2).unwrap_or_default();
    let mask = if mode == "oneshot" { 0x80000004 } else { 0xfff };
    assert!(unsafe { inotify_add_watch(fd, path.as_ptr(), mask) } >= 0);
    if mode == "check" { println!("ADDED"); return; }
    let mut file = unsafe { std::fs::File::from_raw_fd(fd) };
    println!("READY");
    std::io::stdout().flush().unwrap();
    let mut bytes = [0u8; 65536];
    loop {
        let n = file.read(&mut bytes).unwrap();
        let mut offset = 0;
        while offset + 16 <= n {
            let mask = u32::from_ne_bytes(bytes[offset + 4..offset + 8].try_into().unwrap());
            let len = u32::from_ne_bytes(bytes[offset + 12..offset + 16].try_into().unwrap()) as usize;
            if offset + 16 + len > n { break; }
            let name = &bytes[offset + 16..offset + 16 + len];
            let end = name.iter().position(|b| *b == 0).unwrap_or(name.len());
            println!("{mask:08x} {}", String::from_utf8_lossy(&name[..end]));
            offset += 16 + len;
        }
        std::io::stdout().flush().unwrap();
    }
}
RUST
RUSTC_WRAPPER='' CARGO_ENCODED_RUSTFLAGS='' rustc --edition=2024 --target aarch64-unknown-linux-musl -C linker=rust-lld -O "$ROOT/watch-probe.rs" -o "$ROOT/watch-probe" || exit 1
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
  CONTAINER="wr-$CASE-$$"
  CONTAINER_ID=$(docker run -d --name "$CONTAINER" -e WATCH_BRANCH="$BRANCH" -v "$TREE:/w" -v "$CONTROL:/noise" -v "$(dirname "$GATE"):/gate" alpine sh -c '
    mkdir /tmp/derived
    cp -R /w/. /tmp/derived/
    inotifyd - /w:cwnmyd "/w/$WATCH_BRANCH:cwnmyd" | while read -r ev dir name; do
      [ -n "$name" ] || continue
      printf "%s %s %s\n" "$ev" "$dir" "$name" >> /tmp/events
      dest="/tmp/derived${dir#/w}/$name"
      if [ -f "$dir/$name" ]; then cp "$dir/$name" "$dest"; else unlink "$dest" 2>/dev/null || :; fi
    done &
    sleep 1
    touch /tmp/ready
    wait
  ') || { echo "FAIL $CASE: container start"; FAIL=1; continue; }
  CREATED_CONTAINERS+=("$CONTAINER_ID")
  CONTAINER=$CONTAINER_ID
  ready=0
  for i in $(seq 1 300); do
    if docker exec "$CONTAINER" test -e /tmp/ready 2>/dev/null; then ready=1; break; fi
    sleep 1
  done
  if [ "$ready" != 1 ]; then echo "FAIL $CASE: watcher not ready"; FAIL=1; docker rm -f "$CONTAINER" >/dev/null; continue; fi
  if ! docker exec "$CONTAINER" sh -c 'diff -rq /w /tmp/derived >/dev/null'; then
    echo "FAIL $CASE: initial artifact differs"; FAIL=1; docker rm -f "$CONTAINER" >/dev/null; continue
  fi
  printf 'preflight\n' > "$TREE/f00000"
  preflight=0
  for i in $(seq 1 30); do
    if docker exec "$CONTAINER" sh -c '[ "$(cat /tmp/derived/f00000 2>/dev/null)" = preflight ]'; then preflight=1; break; fi
    sleep 1
  done
  if [ "$preflight" != 1 ]; then echo "FAIL $CASE: watcher preflight"; FAIL=1; docker rm -f "$CONTAINER" >/dev/null; continue; fi
  echo "PASS $CASE: initial artifact and live watcher"
  if [ -z "${CTRS_WATCH_ORIGINAL_ONLY:-}" ]; then
    COUNTER=$(docker exec "$CONTAINER" cat /proc/ctrs/watch_bytes) || COUNTER=
    read -r BYTES LIMIT <<< "$COUNTER"
    if [[ ! "$BYTES" =~ ^[0-9]+$ || ! "$LIMIT" =~ ^[0-9]+$ ]] || [ "$BYTES" -le 0 ] || [ "$BYTES" -gt "$LIMIT" ]; then
      echo "FAIL $CASE: invalid 22000-name memory counter: $COUNTER"; FAIL=1
    else echo "MEMORY 22000 $CASE: $COUNTER"; fi
  fi
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
    then echo "FAIL $CASE: added-name order"; FAIL=1; docker rm -f "$CONTAINER" >/dev/null; continue; fi
    ADDED=$(cat "$ROOT/added")
    added_seen=0
    for i in $(seq 1 30); do
      if docker exec "$CONTAINER" sh -c '[ "$(cat "/tmp/derived/$1" 2>/dev/null)" = added ]' sh "$ADDED"; then added_seen=1; break; fi
      sleep 1
    done
    if [ "$added_seen" != 1 ]; then echo "FAIL $CASE: added-name preflight"; FAIL=1; docker rm -f "$CONTAINER" >/dev/null; continue; fi
  fi
  if [ -n "${CTRS_TEST_DROP_DCACHE:-}" ] || { [ "$CASE" = guest-overflow ] && [ -z "${CTRS_WATCH_ORIGINAL_ONLY:-}" ]; }; then
    docker exec --privileged "$CONTAINER" sh -c 'set -e; mkdir -p /tmp/recovery-proc; mount -t proc proc /tmp/recovery-proc; sync; echo 2 > /tmp/recovery-proc/sys/vm/drop_caches; umount /tmp/recovery-proc' || { echo "FAIL $CASE: cannot drop guest caches"; FAIL=1; docker rm -f "$CONTAINER" >/dev/null; continue; }
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
    docker rm -f "$CONTAINER" >/dev/null
    continue
  fi
  read -r MODIFIED DELETED CREATED < "$ROOT/names"
  if [ -n "${CTRS_TEST_ACCESS_WHILE_LOST:-}" ]; then
    sleep 2
    if ! docker exec "$CONTAINER" sh -c '[ "$(cat "/w/$1" 2>/dev/null)" = after ] && [ ! -e "/w/$2" ]' sh "$MODIFIED" "$DELETED"; then
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
    # The daemon flushes the buffered gate events on the next FSEvents
    # callback, which can arrive after the guest's rescan. Wait for that
    # flush before asserting that each real event was captured.
    for i in $(seq 1 300); do
      if tail -c +"$LOG_OFFSET" "$LOG" | rg -q 'test gate delivered guest overflow batch'; then break; fi
      sleep .1
    done
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
    if docker exec "$CONTAINER" sh -c '[ "$(cat "/tmp/derived/$1" 2>/dev/null)" = after ] && [ ! -e "/tmp/derived/$2" ] && [ "$(cat "/tmp/derived/$3" 2>/dev/null)" = new ] && [ "$(cat "/tmp/derived/$4/modified" 2>/dev/null)" = after ] && [ ! -e "/tmp/derived/$4/deleted" ] && [ "$(cat "/tmp/derived/$4/created" 2>/dev/null)" = new ]' sh "$MODIFIED" "$DELETED" "$CREATED" "$BRANCH" 2>/dev/null; then
      if docker exec "$CONTAINER" sh -c 'diff -rq /w /tmp/derived >/dev/null' 2>/dev/null; then converged=1; fi
      break
    fi
    sleep 1
  done
  if [ "$CASE" = guest-overflow ] && tail -c +"$LOG_OFFSET" "$LOG" | rg -q 'bind mount change notifications were lost; the guest revalidates|test overflow gate capacity exceeded'; then
    echo "FAIL $CASE: host loss or test gate overflow"; FAIL=1
  fi
  if [ "$converged" = 1 ] && [ "$triggered" = 1 ]; then
    for expected in "[cmy] $MODIFIED" "d $DELETED" "n $CREATED"; do
      read -r mask name <<< "$expected"
      if ! docker exec "$CONTAINER" sh -c 'mask=$1; name=$2; while read -r ev dir item; do case "$ev" in $mask*) [ "$item" = "$name" ] && exit 0;; esac; done < /tmp/events; exit 1' sh "$mask" "$name"; then
        echo "FAIL $CASE: missing event $mask for $name"; FAIL=1
      fi
    done
    echo "PASS $CASE: loss observed and watcher converged"
  else
    echo "FAIL $CASE: watcher did not converge within 30 seconds"
    docker exec "$CONTAINER" sh -c 'for f in "$1" "$2" "$3" "$4/modified" "$4/deleted" "$4/created"; do printf "%s " "$f"; if [ -e "/tmp/derived/$f" ]; then cat "/tmp/derived/$f" 2>/dev/null || :; else echo missing; fi; done; echo events:; tail -20 /tmp/events' sh "$MODIFIED" "$DELETED" "$CREATED" "$BRANCH" || :
    FAIL=1
  fi
  if [ "$converged" = 1 ] || [ -z "${CTRS_KEEP_WATCH_FAILURE:-}" ]; then docker rm -f "$CONTAINER" >/dev/null; fi
 done
if { [ -z "${CTRS_WATCH_CASE:-}" ] || [ "${CTRS_WATCH_CASE:-}" = extra ]; } && [ -z "${CTRS_WATCH_ORIGINAL_ONLY:-}" ]; then
  EXTRA="$ROOT/extra"
  mkdir -p "$EXTRA/nested" "$EXTRA/denied" "$EXTRA/old-dir"
  printf 'before\n' > "$EXTRA/atomic"
  printf 'before\n' > "$EXTRA/race-a"
  VOLUME="wr-volume-$$"
  if docker volume inspect "$VOLUME" >/dev/null 2>&1; then
    echo "FAIL extra: volume name already exists"; FAIL=1
  elif ! docker volume create "$VOLUME" >/dev/null; then
    echo "FAIL extra: volume creation"; FAIL=1
  else
    CREATED_VOLUMES+=("$VOLUME")
    P1=$(docker run -d --privileged -v "$EXTRA:/w" -v "$VOLUME:/w/nested" -v "$ROOT/watch-probe:/probe:ro" alpine /probe /w) || P1=
    P2=$(docker run -d -v "$EXTRA:/w" -v "$ROOT/watch-probe:/probe:ro" alpine /probe /w) || P2=
    [ -z "$P1" ] || CREATED_CONTAINERS+=("$P1")
    [ -z "$P2" ] || CREATED_CONTAINERS+=("$P2")
    ready=0
    if [ -n "$P1" ] && [ -n "$P2" ]; then
      for i in $(seq 1 300); do
        if docker logs "$P1" 2>&1 | rg -q READY && docker logs "$P2" 2>&1 | rg -q READY; then ready=1; break; fi
        sleep .1
      done
    fi
    if [ "$ready" != 1 ]; then
      echo "FAIL extra: watchers not ready"; FAIL=1
    else
      docker exec "$P1" sh -c 'echo volume > /w/nested/sentinel; cat /w/atomic >/dev/null; echo guest > /w/guest-kept; echo guest > /w/guest-replaced; echo guest > /w/own; stat /w/own >/dev/null; a=$(stat -c %i /w/guest-kept); b=$(ls -ia /w | awk "\$2 == \"guest-kept\" { print \$1 }"); [ "$a" = "$b" ]' || { echo "FAIL extra: guest-created inode identity"; FAIL=1; }
      for i in $(seq 1 100); do
        if docker logs "$P1" 2>&1 | rg -q '^00000100 guest-kept$' && docker logs "$P2" 2>&1 | rg -q '^00000100 guest-kept$'; then break; fi
        sleep .1
      done
      sleep 1
      BEFORE1=$(($(docker logs "$P1" 2>&1 | wc -l) + 1))
      BEFORE2=$(($(docker logs "$P2" 2>&1 | wc -l) + 1))
      chmod 000 "$EXTRA/denied"
      LOG_OFFSET=$(($(wc -c < "$LOG") + 1))
      touch "$GATE"
      printf 'signal\n' > "$EXTRA/signal"
      triggered=0
      for i in $(seq 1 100); do
        if tail -c +"$LOG_OFFSET" "$LOG" | rg -q 'test gate suppressed bind mount change notifications'; then triggered=1; break; fi
        sleep .1
      done
      printf 'after\n' > "$EXTRA/replacement"
      mv "$EXTRA/replacement" "$EXTRA/atomic"
      printf 'replacement\n' > "$EXTRA/new-guest"
      mv "$EXTRA/new-guest" "$EXTRA/guest-replaced"
      rmdir "$EXTRA/old-dir"
      mkdir "$EXTRA/new-dir"
      docker exec "$P1" sh -c 'i=0; while [ "$i" -lt 100 ]; do mv /w/race-a /w/race-b 2>/dev/null || :; mv /w/race-b /w/race-a 2>/dev/null || :; i=$((i+1)); done' >/dev/null 2>&1 &
      RACE_PID=$!
      unlink "$GATE"
      printf 'wake\n' > "$EXTRA/wake"
      lookup=0
      for i in $(seq 1 100); do
        if docker exec "$P1" sh -c '[ "$(cat /w/atomic 2>/dev/null)" = after ]'; then lookup=1; break; fi
        sleep .05
      done
      if [ "$lookup" != 1 ]; then echo "FAIL extra: lookup after rescan"; FAIL=1; fi
      wait "$RACE_PID" || FAIL=1
      observed=0
      for i in $(seq 1 300); do
        if docker logs "$P1" 2>&1 | rg -q '^00000200 atomic$' && docker logs "$P1" 2>&1 | rg -q '^00000100 atomic$' &&
           docker logs "$P2" 2>&1 | rg -q '^00000200 atomic$' && docker logs "$P2" 2>&1 | rg -q '^00000100 atomic$' &&
           docker logs "$P1" 2>&1 | tail -n +"$BEFORE1" | rg -q '^00000200 guest-replaced$' && docker logs "$P1" 2>&1 | tail -n +"$BEFORE1" | rg -q '^00000100 guest-replaced$' &&
           docker logs "$P2" 2>&1 | tail -n +"$BEFORE2" | rg -q '^00000200 guest-replaced$' && docker logs "$P2" 2>&1 | tail -n +"$BEFORE2" | rg -q '^00000100 guest-replaced$' &&
           docker logs "$P1" 2>&1 | rg -q '^40000200 old-dir$' && docker logs "$P1" 2>&1 | rg -q '^40000100 new-dir$' &&
           docker logs "$P2" 2>&1 | rg -q '^40000200 old-dir$' && docker logs "$P2" 2>&1 | rg -q '^40000100 new-dir$'; then observed=1; break; fi
        sleep .1
      done
      if [ "$triggered" != 1 ] || [ "$observed" != 1 ]; then
        echo "FAIL extra: replacement, directory events, or loss trigger"; docker logs "$P1" 2>&1 | tail -20; docker logs "$P2" 2>&1 | tail -20; FAIL=1
      else
        echo "PASS extra: replacement and directory events reached both watchers during guest rename"
      fi
      if docker logs "$P1" 2>&1 | tail -n +"$BEFORE1" | rg -q '^000000(02|40|80) own$'; then
        echo "FAIL extra: guest write was echoed during recovery"; FAIL=1
      else echo "PASS extra: guest write echo suppressed"; fi
      if docker logs "$P1" 2>&1 | tail -n +"$BEFORE1" | rg -q '^00000[12]00 guest-kept$' || docker logs "$P2" 2>&1 | tail -n +"$BEFORE2" | rg -q '^00000[12]00 guest-kept$'; then
        echo "FAIL extra: guest-created name falsely reported replaced"
        echo "watcher 1 after line $BEFORE1:"; docker logs "$P1" 2>&1 | tail -n +"$BEFORE1" | rg 'guest-kept' || :
        echo "watcher 2 after line $BEFORE2:"; docker logs "$P2" 2>&1 | tail -n +"$BEFORE2" | rg 'guest-kept' || :
        FAIL=1
      else echo "PASS extra: guest-created inode identity retained"; fi
      if ! docker exec "$P1" sh -c '[ "$(cat /w/nested/sentinel)" = volume ]'; then
        echo "FAIL extra: nested volume detached"; FAIL=1
      else
        echo "PASS extra: nested volume retained"
      fi
      unreadable=0
      for i in $(seq 1 300); do
        if tail -c +"$LOG_OFFSET" "$LOG" | rg -q 'reconciliation skipped an unreadable entry'; then unreadable=1; break; fi
        sleep .1
      done
      chmod 700 "$EXTRA/denied"
      if [ "$unreadable" != 1 ]; then echo "FAIL extra: unreadable directory was not observed"; FAIL=1
      else echo "PASS extra: unreadable directory skipped"; fi
      P3=$(docker run -d -v "$EXTRA:/w" -v "$ROOT/watch-probe:/probe:ro" alpine /probe /w/atomic) || P3=
      [ -z "$P3" ] || CREATED_CONTAINERS+=("$P3")
      ready=0
      for i in $(seq 1 100); do
        if [ -n "$P3" ] && docker logs "$P3" 2>&1 | rg -q READY; then ready=1; break; fi
        sleep .1
      done
      if [ "$ready" != 1 ]; then echo "FAIL extra: per-file watcher not ready"; FAIL=1
      elif ! docker exec --privileged "$P1" sh -c 'set -e; mkdir -p /tmp/recovery-proc; mount -t proc proc /tmp/recovery-proc; sync; echo 2 > /tmp/recovery-proc/sys/vm/drop_caches; umount /tmp/recovery-proc'; then
        echo "FAIL extra: cannot drop per-file dentry"; FAIL=1
      else
        LOG_OFFSET=$(($(wc -c < "$LOG") + 1))
        touch "$GATE"
        printf 'file-watch\n' > "$EXTRA/file-replacement"
        mv "$EXTRA/file-replacement" "$EXTRA/atomic"
        triggered=0
        for i in $(seq 1 100); do
          if tail -c +"$LOG_OFFSET" "$LOG" | rg -q 'test gate suppressed bind mount change notifications'; then triggered=1; break; fi
          sleep .1
        done
        unlink "$GATE"
        printf 'wake\n' > "$EXTRA/file-wake"
        overflow=0
        for i in $(seq 1 300); do
          if docker logs "$P3" 2>&1 | rg -q '^00004000 '; then overflow=1; break; fi
          sleep .1
        done
        if [ "$triggered" = 1 ] && [ "$overflow" = 1 ]; then echo "PASS extra: reclaimed per-file watch reported overflow"
        else echo "FAIL extra: reclaimed per-file watch silent"; FAIL=1; fi
      fi
      [ -z "$P3" ] || docker rm -f "$P3" >/dev/null 2>&1 || :
    fi
    [ -z "$P1" ] || docker rm -f "$P1" >/dev/null 2>&1 || :
    [ -z "$P2" ] || docker rm -f "$P2" >/dev/null 2>&1 || :
  fi

fi

if { [ -z "${CTRS_WATCH_CASE:-}" ] || [ "${CTRS_WATCH_CASE:-}" = oneshot ]; } && [ -z "${CTRS_WATCH_ORIGINAL_ONLY:-}" ]; then
  mkdir -p "$ROOT/unreachable/a/b"
  ONESHOT=$(docker run -d --privileged -v "$ROOT/unreachable:/orphan" -v "$ROOT/watch-probe:/probe:ro" alpine /probe /orphan/a/b oneshot) || ONESHOT=
  [ -z "$ONESHOT" ] || CREATED_CONTAINERS+=("$ONESHOT")
  ready=0
  for i in $(seq 1 100); do
    if [ -n "$ONESHOT" ] && docker logs "$ONESHOT" 2>&1 | rg -q READY; then ready=1; break; fi
    sleep .1
  done
  if [ "$ready" != 1 ]; then echo "FAIL oneshot: watcher not ready"; FAIL=1
  elif ! docker exec --privileged "$ONESHOT" sh -c 'set -e; mkdir -p /tmp/recovery-proc; mount -t proc proc /tmp/recovery-proc; sync; echo 2 > /tmp/recovery-proc/sys/vm/drop_caches; umount /tmp/recovery-proc' ||
       ! mv "$ROOT/unreachable/a" "$ROOT/displaced" ||
       ! docker exec "$ONESHOT" sh -c 'echo "s /orphan" > /proc/ctrs/fsnotify'; then
    echo "FAIL oneshot: rescan setup"; FAIL=1
  else
    fired=0
    for i in $(seq 1 200); do
      if docker logs "$ONESHOT" 2>&1 | rg -q '^(00000004|40000004) '; then fired=1; break; fi
      sleep .1
    done
    if [ "$fired" != 1 ]; then echo "FAIL oneshot: unreachable watch did not receive attrib"; FAIL=1
    elif ! perl -e 'alarm 5; exec @ARGV' docker exec "$ONESHOT" /probe /orphan check | rg -q '^ADDED$'; then
      echo "FAIL oneshot: subsequent watch blocked"; FAIL=1
    else echo "PASS oneshot: attrib delivered and subsequent watch added"; fi
  fi
  [ -z "$ONESHOT" ] || docker rm -f "$ONESHOT" >/dev/null 2>&1 || :
fi

if { [ -z "${CTRS_WATCH_CASE:-}" ] || [ "${CTRS_WATCH_CASE:-}" = cap ]; } && [ -z "${CTRS_WATCH_ORIGINAL_ONLY:-}" ]; then
  LARGE="$ROOT/large"
  mkdir "$LARGE"
  if ! python3 - "$LARGE" <<'LARGE'
import os, sys
p = sys.argv[1]
for i in range(200000):
    fd = os.open(os.path.join(p, f'f{i:06}'), os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(fd)
LARGE
  then echo "FAIL cap: cannot create 200000 names"; FAIL=1
  else
    LARGE_WATCH=$(docker run -d --privileged -v "$LARGE:/w" -v "$ROOT/watch-probe:/probe:ro" alpine /probe /w) || LARGE_WATCH=
    [ -z "$LARGE_WATCH" ] || CREATED_CONTAINERS+=("$LARGE_WATCH")
    ready=0
    for i in $(seq 1 600); do
      if [ -n "$LARGE_WATCH" ] && docker logs "$LARGE_WATCH" 2>&1 | rg -q READY; then ready=1; break; fi
      sleep .1
    done
    if [ "$ready" != 1 ]; then echo "FAIL cap: 200000-name watch not ready"; FAIL=1
    else
      COUNTER=$(docker exec "$LARGE_WATCH" cat /proc/ctrs/watch_bytes) || COUNTER=
      read -r BYTES LIMIT <<< "$COUNTER"
      if [[ ! "$BYTES" =~ ^[0-9]+$ || ! "$LIMIT" =~ ^[0-9]+$ ]] || [ "$BYTES" -le 0 ] || [ "$BYTES" -gt "$LIMIT" ]; then
        echo "FAIL cap: invalid 200000-name memory counter: $COUNTER"; FAIL=1
      else echo "MEMORY 200000: $COUNTER"; fi
    fi
    [ -z "$LARGE_WATCH" ] || docker rm -f "$LARGE_WATCH" >/dev/null 2>&1 || :
    if ! python3 - "$LARGE" <<'LONG'
import os, sys
p = sys.argv[1]
for i in range(200000):
    name = f'f{i:06}'
    os.rename(os.path.join(p, name), os.path.join(p, name + 'x' * 210))
LONG
    then echo "FAIL cap: cannot create long names"; FAIL=1
    else
      CONSOLE_OFFSET=$(($(wc -c < "$DATA/vm-console.log") + 1))
      CAP_WATCH=$(docker run -d --privileged -v "$LARGE:/w" -v "$ROOT/watch-probe:/probe:ro" alpine /probe /w) || CAP_WATCH=
      [ -z "$CAP_WATCH" ] || CREATED_CONTAINERS+=("$CAP_WATCH")
      ready=0
      for i in $(seq 1 600); do
        if [ -n "$CAP_WATCH" ] && docker logs "$CAP_WATCH" 2>&1 | rg -q READY; then ready=1; break; fi
        sleep .1
      done
      if [ "$ready" != 1 ]; then echo "FAIL cap: degraded watch not ready"; FAIL=1
      else
        if ! tail -c +"$CONSOLE_OFFSET" "$DATA/vm-console.log" | rg -q 'watched directory name retention exhausted'; then echo "FAIL cap: missing degradation log"; FAIL=1; fi
        LOG_OFFSET=$(($(wc -c < "$LOG") + 1))
        touch "$GATE"
        printf 'changed\n' >> "$LARGE/$(python3 -c 'print("f000000" + "x" * 210)')"
        triggered=0
        for i in $(seq 1 100); do
          if tail -c +"$LOG_OFFSET" "$LOG" | rg -q 'test gate suppressed bind mount change notifications'; then triggered=1; break; fi
          sleep .1
        done
        unlink "$GATE"
        printf 'wake\n' > "$LARGE/wake"
        if [ "$triggered" != 1 ]; then echo "FAIL cap: loss trigger"; FAIL=1; fi
        overflow=0
        for i in $(seq 1 600); do
          if docker logs "$CAP_WATCH" 2>&1 | rg -q '^00004000 ' && docker logs "$CAP_WATCH" 2>&1 | rg -q '^[04]0000004 '; then overflow=1; break; fi
          sleep .1
        done
        if [ "$overflow" = 1 ]; then echo "PASS cap: IN_Q_OVERFLOW and IN_ATTRIB"; else echo "FAIL cap: missing overflow or attrib"; FAIL=1; fi
      fi
      [ -z "$CAP_WATCH" ] || docker rm -f "$CAP_WATCH" >/dev/null 2>&1 || :
    fi
  fi
fi

exit "$FAIL"
