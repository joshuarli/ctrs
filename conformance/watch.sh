#!/bin/bash
# Watches the daemon itself for silent exits. Starts it as a child of this
# script, churns privileged containers (the observed death signature: bursts
# of privileged containers finishing in the seconds before the daemon vanishes),
# and records what the OS says killed it — exit code or signal — plus the
# instance identity (pid, data root, socket, kernel boot id), the number of
# VM generations the engine went through, and the last log lines before the
# end. A clean SIGTERM stop is success; any other death exits 1 with a
# report. Never touches OrbStack, docker contexts, or ~/.kiri.
#
# Usage: conformance/watch.sh   (env: WATCH_SECONDS=600, WATCH_CHURN=1)
set -u
set -o pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD
WORK=$ROOT/.work/tmp
TS=$(date +%s)
DATA=$WORK/watch-$TS-data
SOCK=$WORK/watch-$TS.sock
HOME_DIR=$WORK/watch-$TS-home
LOG=$WORK/watch-$TS.log
REPORT_DIR=$WORK/watch-reports
mkdir -p "$HOME_DIR" "$REPORT_DIR"

SECONDS_BUDGET=${WATCH_SECONDS:-600}
CHURN=${WATCH_CHURN:-1}
ALPINE=public.ecr.aws/docker/library/alpine:latest

command -v docker >/dev/null || { echo 'docker CLI not on PATH' >&2; exit 2; }
BIN=$ROOT/target/release/kiri
[ -x "$BIN" ] || { echo 'target/release/kiri missing; run cargo xtask host' >&2; exit 2; }

: >"$LOG"
KIRI_DATA_DIR="$DATA" KIRI_SOCKET="$SOCK" HOME="$HOME_DIR" "$BIN" daemon >>"$LOG" 2>&1 &
DPID=$!
START=$(date +%s)
boot_id=$(sysctl -n kern.boottime 2>/dev/null || echo unknown)

cleanup() {
  kill -TERM "$DPID" 2>/dev/null
  for i in $(seq 1 10); do kill -0 "$DPID" 2>/dev/null || break; sleep 1; done
  kill -9 "$DPID" 2>/dev/null
  rm -rf "$DATA" "$HOME_DIR" "$SOCK"
}
trap cleanup EXIT

for i in $(seq 1 90); do [ -S "$SOCK" ] && break; sleep 1; done
[ -S "$SOCK" ] || { echo 'watch: daemon did not start' >&2; exit 2; }

if [ "$CHURN" = 1 ]; then
  DOCKER_HOST="unix://$SOCK" DOCKER_CONTEXT= perl -e 'alarm 300; exec @ARGV' docker pull "$ALPINE" >>"$LOG" 2>&1 || { echo 'watch: pull failed' >&2; exit 2; }
fi

churned=0
while kill -0 "$DPID" 2>/dev/null && [ $(( $(date +%s) - START )) -lt "$SECONDS_BUDGET" ]; do
  if [ "$CHURN" = 1 ]; then
    DOCKER_HOST="unix://$SOCK" DOCKER_CONTEXT= perl -e 'alarm 60; exec @ARGV' docker run --rm --privileged "$ALPINE" true >>"$LOG" 2>&1
    churned=$((churned + 1))
  else
    sleep 5
  fi
done

END=$(date +%s)
if kill -0 "$DPID" 2>/dev/null; then
  stop_reason=budget
  kill -TERM "$DPID" 2>/dev/null
else
  stop_reason=death
fi
wait "$DPID"
rc=$?
elapsed=$((END - START))
sig=0
code="$rc"
if [ "$rc" -gt 128 ]; then sig=$((rc - 128)); code="-1"; fi
vm_boots=$(grep -c 'VM booted' "$LOG" 2>/dev/null || true)
report="$REPORT_DIR/watch-$TS.jsonl"
printf '{"ts":%s,"pid":%s,"data_dir":"%s","socket":"%s","boot_id":"%s","elapsed_s":%s,"exit_code":%s,"signal":%s,"vm_boots":%s,"churned":%s,"stop_reason":"%s"}\n' \
  "$TS" "$DPID" "$DATA" "$SOCK" "$boot_id" "$elapsed" "$code" "$sig" "$vm_boots" "$churned" "$stop_reason" > "$report"

echo "watch: daemon pid $DPID, exit code ${code}, signal ${sig}, after ${elapsed}s, $churned churned, $vm_boots VM boot(s), stop ${stop_reason}"
echo "watch: report $report"
echo "watch: last log lines:"
tail -20 "$LOG"

# Dying before the budget is not an anomaly only if this script asked it to
# (stop_reason=budget). Everything else is a silent death and fails.
if [ "$stop_reason" = budget ]; then
  echo 'watch: no anomaly; daemon lived for the full budget'
  exit 0
fi
echo 'watch: UNEXPECTED DAEMON EXIT' >&2
exit 1
