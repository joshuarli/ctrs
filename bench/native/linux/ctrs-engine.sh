#!/bin/sh
set -eu
action=${1:?usage: ctrs-engine.sh start|stop BINARY RUN_DIR}
binary=$(realpath "${2:?binary path required}")
run=$(realpath -m "${3:?run directory required}")
case "$run" in
  */.work/*) ;;
  *) echo 'run directory must be under .work/' >&2; exit 2 ;;
esac
unit=ctrs-bench-$(printf %s "$run" | sha256sum | cut -c1-12)
case "$action" in
  start)
    test -x "$binary"
    test -x "$(dirname "$binary")/ctrs-init"
    sudo -n install -d -o root -g root "$run" "$run/home" "$run/data" "$run/state" "$run/tmp" "$run/varlib/ctrs"
    sudo -n systemd-run --unit="$unit" --property=Delegate=yes --property=KillMode=mixed --property=TimeoutStopSec=30 \
      -- /usr/bin/unshare --mount --propagation private /bin/sh -eu -c '
        run=$1
        binary=$2
        mount --bind "$run/varlib" /var/lib
        exec env HOME="$run/home" CTRS_DATA_DIR="$run/data" CTRS_STATE_DIR="$run/state" CTRS_SOCKET="$run/docker.sock" CTRS_AGENT="$(dirname "$binary")/ctrs-init" TMPDIR="$run/tmp" "$binary" daemon
      ' sh "$run" "$binary"
    printf 'CTRS_SOCKET=%s/docker.sock\nCTRS_UNIT=%s.service\n' "$run" "$unit"
    ;;
  stop)
    sudo -n systemctl stop "$unit.service"
    ;;
  *) echo 'action must be start or stop' >&2; exit 2 ;;
esac
