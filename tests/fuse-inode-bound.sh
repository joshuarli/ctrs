#!/bin/bash
# Regression for the guest's live virtiofs inode bound (kernel patch 0017).
# Virtualization.framework holds one host descriptor per inode the guest has
# looked up, so walking a bind-mounted tree larger than the bound must leave
# the engine's VM process under the bound plus a margin, every file must
# still read back correctly, files held open across the walk must stay
# usable, and the count must fall back after the guest drops its caches.
#
#   CTRS_SOCKET=... CTRS_DATA_DIR=... tests/fuse-inode-bound.sh
#
# CTRS_TEST_BOUND_FILES (default 150000) sets the tree size,
# CTRS_TEST_BOUND (default: the guest's /proc/ctrs/fuse_inodes bound, else
# 65536) the expected bound, CTRS_TEST_BOUND_MARGIN (default 8192) the
# allowed excess.
set -u
SOCK=${CTRS_SOCKET:?set CTRS_SOCKET to the scratch engine socket}
DATA=$(cd "${CTRS_DATA_DIR:?set CTRS_DATA_DIR to the scratch engine data directory}" && pwd -P)
export DOCKER_HOST="unix://$SOCK"
unset DOCKER_CONTEXT
FILES=${CTRS_TEST_BOUND_FILES:-150000}
MARGIN=${CTRS_TEST_BOUND_MARGIN:-8192}
LABEL=dev.ctrs.campaign.run=${CTRS_TEST_LABEL:-fuse-inode-bound}
ROOT="$PWD/.work/tmp/fuse-inode-bound-$$"
if [ -e "$ROOT" ]; then echo "FAIL: fixture already exists"; exit 1; fi
mkdir -p "$ROOT/tree"
CREATED_CONTAINERS=()
SAMPLER=
cleanup() {
  [ -n "$SAMPLER" ] && kill "$SAMPLER" 2>/dev/null
  for container in ${CREATED_CONTAINERS[@]+"${CREATED_CONTAINERS[@]}"}; do docker rm -f "$container" >/dev/null 2>&1 || :; done
  python3 - "$ROOT" <<'CLEAN'
import os, sys
for path, dirs, files in os.walk(sys.argv[1], topdown=False):
    for name in files: os.unlink(os.path.join(path, name))
    for name in dirs: os.rmdir(os.path.join(path, name))
os.rmdir(sys.argv[1])
CLEAN
}
trap cleanup EXIT

VM_PID=
for pid in $(pgrep -f 'com.apple.Virtualization.VirtualMachine'); do
  if lsof -p "$pid" -Fn 2>/dev/null | grep -qF "n$DATA/"; then VM_PID=$pid; break; fi
done
if [ -z "$VM_PID" ]; then echo "FAIL: no VM process holds files under $DATA"; exit 1; fi
fds() { lsof -p "$VM_PID" -Ff 2>/dev/null | grep -c '^f'; }

cat > "$ROOT/walk.rs" <<'RUST'
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;

fn walk(dir: &Path, out: &mut Vec<std::path::PathBuf>) {
    let mut entries: Vec<_> = std::fs::read_dir(dir).unwrap().map(|e| e.unwrap().path()).collect();
    entries.sort();
    for path in entries {
        let meta = std::fs::symlink_metadata(&path).unwrap();
        if meta.is_dir() { walk(&path, out) } else { out.push(path) }
    }
}

fn check(root: &Path, path: &Path) -> bool {
    let want = format!("{}\n", path.strip_prefix(root).unwrap().display());
    matches!(std::fs::read_to_string(path), Ok(got) if got == want)
}

fn main() {
    let root = std::path::PathBuf::from(std::env::args().nth(1).unwrap());
    let started = std::time::Instant::now();
    let mut files = Vec::new();
    walk(&root, &mut files);
    let walked = started.elapsed().as_secs_f64();
    let mut held: Vec<_> = files.iter().take(64).map(|p| (p.clone(), std::fs::File::open(p).unwrap())).collect();
    let mut bad = 0usize;
    for path in &files {
        if !check(&root, path) { bad += 1; if bad <= 5 { eprintln!("bad {}", path.display()) } }
    }
    for path in files.iter().rev().take(2000) {
        if std::fs::metadata(path).is_err() || !check(&root, path) { bad += 1 }
    }
    let mut held_bad = 0usize;
    for (path, file) in held.iter_mut() {
        let mut got = String::new();
        let want = format!("{}\n", path.strip_prefix(&root).unwrap().display());
        if file.seek(SeekFrom::Start(0)).is_err() || file.read_to_string(&mut got).is_err() || got != want { held_bad += 1 }
    }
    println!("files {} bad {} held_bad {} walk_s {:.1} total_s {:.1}", files.len(), bad, held_bad, walked, started.elapsed().as_secs_f64());
}
RUST
RUSTC_WRAPPER='' CARGO_ENCODED_RUSTFLAGS='' rustc --edition=2024 --target aarch64-unknown-linux-musl -C linker=rust-lld -O "$ROOT/walk.rs" -o "$ROOT/walk" || exit 1

python3 - "$ROOT/tree" "$FILES" <<'PY' || { echo "FAIL: fixture tree"; exit 1; }
import os, sys
root, count = sys.argv[1], int(sys.argv[2])
for i in range(count):
    d = f'd{i // 1000:04}'
    if i % 1000 == 0: os.mkdir(os.path.join(root, d))
    rel = f'{d}/f{i % 1000:04}'
    with open(os.path.join(root, rel), 'w') as f: f.write(rel + '\n')
PY

KNOB=$(docker run --rm --label "$LABEL" alpine cat /proc/ctrs/fuse_inodes 2>/dev/null) || KNOB=
read -r LIVE KERNEL_BOUND <<< "${KNOB:-- -}"
BOUND=${CTRS_TEST_BOUND:-}
if [ -z "$BOUND" ]; then
  if [[ "${KERNEL_BOUND:-}" =~ ^[0-9]+$ ]] && [ "$KERNEL_BOUND" -gt 0 ]; then BOUND=$KERNEL_BOUND; else BOUND=65536; fi
fi
LIMIT=$((BOUND + MARGIN))
if [ "$FILES" -le "$LIMIT" ]; then echo "FAIL: tree of $FILES files does not exceed bound $BOUND + $MARGIN"; exit 1; fi
BEFORE=$(fds)
printf 'vm pid %s, bound %s (kernel: %s), files %s, fds before %s\n' "$VM_PID" "$BOUND" "${KNOB:-none}" "$FILES" "$BEFORE"

FAIL=0
PEAK_FILE="$ROOT/peak"
echo "$BEFORE" > "$PEAK_FILE"
( peak=$BEFORE; while :; do n=$(fds); [ "$n" -gt "$peak" ] && { peak=$n; echo "$peak" > "$PEAK_FILE"; }; sleep 1; done ) &
SAMPLER=$!
OUT=$(docker run --rm --label "$LABEL" -v "$ROOT/tree:/t:ro" -v "$ROOT/walk:/walk:ro" alpine /walk /t 2>&1)
RC=$?
kill "$SAMPLER" 2>/dev/null; wait "$SAMPLER" 2>/dev/null; SAMPLER=
PEAK=$(cat "$PEAK_FILE")
AFTER=$(fds)
echo "walk: $OUT"
printf 'fds peak %s, after walk %s, limit %s\n' "$PEAK" "$AFTER" "$LIMIT"
if [ "$RC" != 0 ] || ! [[ "$OUT" == *"files $FILES bad 0 held_bad 0 "* ]]; then
  echo "FAIL read-back: every file and every held-open file reads its own path"; FAIL=1
else echo "PASS read-back: $FILES files and 64 held-open files read correctly"; fi
if [ "$PEAK" -gt "$LIMIT" ] || [ "$AFTER" -gt "$LIMIT" ]; then
  echo "FAIL bound: VM process descriptors exceeded $LIMIT (peak $PEAK, after $AFTER)"; FAIL=1
else echo "PASS bound: VM process descriptors stayed at or under $LIMIT (peak $PEAK)"; fi

DROP=$(docker run --rm --privileged --label "$LABEL" -v "$ROOT/tree:/t:ro" alpine sh -c 'set -e; mkdir -p /tmp/p; mount -t proc proc /tmp/p; sync; echo 2 > /tmp/p/sys/vm/drop_caches; cat /proc/ctrs/fuse_inodes 2>/dev/null || :') || DROP=failed
sleep 2
RECOVERED=$(fds)
printf 'after drop_caches: fds %s (guest %s)\n' "$RECOVERED" "${DROP:-none}"
if [ "$DROP" = failed ]; then
  echo "FAIL recovery: cannot drop guest caches"; FAIL=1
elif [ "$RECOVERED" -gt $((BEFORE + 4096)) ]; then
  echo "FAIL recovery: descriptors did not return near $BEFORE after drop_caches ($RECOVERED)"; FAIL=1
else echo "PASS recovery: descriptors returned to $RECOVERED"; fi
exit "$FAIL"
