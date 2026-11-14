#!/bin/bash
# Conformance oracle for the daemon's hand-written HTTP/1.1 parser.
# Runs each fixture against a live scratch daemon; exits 1 on any failure.
# Budget: <5 minutes.
set -u
cd "$(dirname "$0")/.."
ROOT=$PWD
export CTRS_SOCKET=${CTRS_HTTP_SOCK:-$PWD/.work/tmp/ctrs14.sock}
export CTRS_DATA_DIR=$PWD/.work/tmp/ctrs14-data
export CTRS_STATE_DIR=$PWD/.work/tmp/ctrs14-state
export HOME=$PWD/.work/tmp/ctrs14-home
mkdir -p "$CTRS_DATA_DIR" "$CTRS_STATE_DIR" "$HOME"
rm -f "$CTRS_SOCKET"

if [ ! -x ./target/release/ctrs ]; then
  echo "http oracle: target/release/ctrs missing; building (cargo xtask host)"
  CARGO_ENCODED_RUSTFLAGS="" cargo xtask host || exit 2
fi

./target/release/ctrs daemon > .work/tmp/ctrs14-daemon.log 2>&1 < /dev/null &
DPID=$!
trap 'kill -TERM $DPID 2>/dev/null; wait $DPID 2>/dev/null || true' EXIT

for i in $(seq 1 90); do
  [ -S "$CTRS_SOCKET" ] && break
  sleep 1
done
[ -S "$CTRS_SOCKET" ] || { echo "http oracle: daemon did not create its socket"; exit 2; }


START=$(date +%s)
FAILED=0
for f in conformance/http/*.py; do
  case "$f" in *common.py) continue;; esac
  if ! python3 "$f" "$CTRS_SOCKET"; then
    FAILED=$((FAILED + 1))
  fi
done
END=$(date +%s)
echo "http oracle: $(($END - $START))s elapsed, $FAILED fixture(s) failed"
kill -TERM $DPID 2>/dev/null; wait $DPID 2>/dev/null || true
[ "$FAILED" -eq 0 ]
