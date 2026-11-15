# Shared isolated-environment harness for the Linux-host proofs.
#
# Sourced by tests, never executed. Caller sets ROOT, SCRATCH, BIN (directory
# with AMD64 ctrs and ctrs-init) and D (default docker), then:
#
#   iso_endpoint_check            # local unix socket, linux/amd64; exits 2 otherwise
#   iso_bin_check                 # both executables are 64-bit x86-64 ELFs
#   iso_alloc_ports 3             # sets ISO_PORTS
#   iso_prepare NAME              # refuses pre-existing resources, scratch, DOCKER_CONFIG
#   iso_trap_install              # owns cleanup from here on
#   iso_start                     # starts the harness container, waits for its engine
#
# The harness container is privileged, has its own net/pid/mnt namespaces,
# carries the caller's BIN read-only at /opt/ctrs, and keeps its own ctrs
# state in a named volume. Host binfmt registrations are never touched.
# On exit (success, failure, INT/TERM) only the run's own recorded container
# and volumes are removed; failure logs (daemon.log, inspect.json) are
# preserved in the scratch directory when ISO_PRESERVE=1 or the exit code is
# non-zero. Refuses-before-create paths are side-effect free.

set -u

D=${D:-docker}
ISO_MINE=0
ISO_RC_FLAG=""
CONTAINER=""
VOL_STATE=""
VOL_STORE=""
WORK=""
ISO_PORTS=()

iso_abort() {
  if [ "$ISO_MINE" = 0 ]; then
    [ -n "$WORK" ] && rm -rf "$WORK"
    CONTAINER=""
    VOL_STATE=""
    VOL_STORE=""
  fi
  echo "isolated-env: $*" >&2
  exit 2
}

iso_endpoint_check() {
  if [ -n "${DOCKER_HOST:-}" ]; then
    ISO_CLIENT_HOST=$DOCKER_HOST
  else
    ISO_CTX=$("$D" context show 2>&1) || iso_abort "docker context show failed: $ISO_CTX"
    ISO_CLIENT_HOST=$("$D" context inspect "$ISO_CTX" --format '{{.Endpoints.docker.Host}}' 2>&1) || iso_abort "docker context inspect failed: $ISO_CLIENT_HOST"
  fi
  case "$ISO_CLIENT_HOST" in
    unix://*) ;;
    *) iso_abort "refusing to use a non-unix Docker endpoint ($ISO_CLIENT_HOST): this harness never talks to remote engines" ;;
  esac
  ISO_SERVER=$("$D" version --format '{{.Server.Os}}/{{.Server.Arch}}' 2>&1) || iso_abort "docker server not answering: $ISO_SERVER"
  [ "$ISO_SERVER" = "linux/amd64" ] || iso_abort "docker server is $ISO_SERVER, want linux/amd64"
  ISO_DOCKER_VERSION=$("$D" version --format '{{.Server.Version}}' 2>&1)
}

iso_bin_check() {
  BIN=$(cd "$BIN" 2>/dev/null && pwd) || iso_abort "BIN directory '$BIN' not found"
  for b in ctrs ctrs-init; do
    [ -x "$BIN/$b" ] || iso_abort "$BIN/$b missing or not executable"
    magic=$(od -A n -t x1 -N 4 "$BIN/$b" | tr -d ' \n')
    [ "$magic" = "7f454c46" ] || iso_abort "$BIN/$b is not an ELF binary"
    [ "$(od -A n -t x1 -j 4 -N 1 "$BIN/$b" | tr -d ' \n')" = "02" ] || iso_abort "$BIN/$b is not a 64-bit ELF binary"
    machine=$(od -A n -t x1 -j 18 -N 2 "$BIN/$b" | tr -d ' \n')
    [ "$machine" = "3e00" ] || iso_abort "$BIN/$b is not an x86-64 binary (e_machine 0x$machine)"
  done
}

iso_port_free() { ! (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

iso_port_in_list() {
  local item
  for item in ${ISO_PORTS[@]+"${ISO_PORTS[@]}"}; do
    [ "$item" = "$1" ] && return 0
  done
  return 1
}

iso_alloc_ports() {
  ISO_PORTS=()
  local tries=0 p
  while [ ${#ISO_PORTS[@]} -lt "$1" ] && [ $tries -lt 100 ]; do
    p=$((20000 + RANDOM % 20000))
    if iso_port_free "$p" && ! iso_port_in_list "$p"; then
      ISO_PORTS+=("$p")
    fi
    tries=$((tries + 1))
  done
  [ ${#ISO_PORTS[@]} = "$1" ] || iso_abort "could not allocate $1 free loopback ports"
}

# Checks the prefix is free, creates the scratch directory and the isolated
# client config. Anything this run goes on to create is removed by
# iso_cleanup; a pre-existing container or volume of the name is refused,
# never removed.
iso_prepare() {
  CONTAINER=$1
  VOL_STATE="$1-state"
  VOL_STORE="$1-store"
  if "$D" ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    iso_abort "container $CONTAINER already exists: refusing to touch it (pass a fresh PREFIX)"
  fi
  for v in "$VOL_STATE" "$VOL_STORE"; do
    if "$D" volume inspect "$v" >/dev/null 2>&1; then
      iso_abort "volume $v already exists: refusing to touch it (pass a fresh PREFIX)"
    fi
  done
  WORK=$SCRATCH/isolated-$1
  if [ -e "$WORK" ]; then
    iso_abort "scratch $WORK exists: remove it or pass a fresh PREFIX"
  fi
  mkdir -p "$WORK"
  printf '{"auths":{}}\n' > "$WORK/config.json"
  export DOCKER_CONFIG="$WORK"
  unset DOCKER_CONTEXT
  if ! "$D" image inspect alpine:3.22 >/dev/null 2>&1; then
    echo "pulling alpine:3.22 (harness tooling image)"
    "$D" pull -q alpine:3.22 >/dev/null || iso_abort "alpine:3.22 not available"
  fi
}

iso_trap_install() {
  ISO_MINE=1
  trap iso_cleanup EXIT
  trap iso_on_int INT
  trap iso_on_term TERM
}

iso_on_int() { ISO_RC_FLAG=130; exit 130; }
iso_on_term() { ISO_RC_FLAG=143; exit 143; }

iso_cleanup() {
  local rc=$?
  [ -n "$ISO_RC_FLAG" ] && rc=$ISO_RC_FLAG
  iso_release "$rc"
  exit "$rc"
}

# Releases the resources created by the last iso_prepare without exiting, so
# callers that run several harnesses in one process (`--all`) do not leak
# engines. `rc` is honored for the failure-preserve semantics.
iso_release() {
  local rc=${1:-0}
  [ "${ISO_MINE:-0}" = 1 ] || return 0
  local preserved=""
  if [ -n "$CONTAINER" ] && { [ "${ISO_PRESERVE:-0}" = 1 ] || [ "$rc" -ne 0 ]; } && "$D" inspect "$CONTAINER" >/dev/null 2>&1; then
    "$D" logs "$CONTAINER" > "$WORK/daemon.log" 2>&1 || true
    "$D" inspect "$CONTAINER" > "$WORK/inspect.json" 2>&1 || true
    preserved="$WORK"
  fi
  [ -n "$CONTAINER" ] && "$D" rm -f "$CONTAINER" >/dev/null 2>&1 || true
  [ -n "$VOL_STATE" ] && "$D" volume rm "$VOL_STATE" >/dev/null 2>&1 || true
  [ -n "$VOL_STORE" ] && "$D" volume rm "$VOL_STORE" >/dev/null 2>&1 || true
  if [ -n "$preserved" ]; then
    echo "failure logs preserved in $preserved"
  else
    [ -n "$WORK" ] && rm -rf "$WORK"
  fi
  CONTAINER=""
  VOL_STATE=""
  VOL_STORE=""
  WORK=""
  ISO_MINE=0
  export ISO_PRESERVE=0
  return 0
}

# Starts the privileged harness with BIN bound read-only at /opt/ctrs and a
# named volume for ctrs's state. Waits for the engine's socket (60 s).
# With ISO_BINFMT_ISOLATE=1 the daemon starts inside a private mount
# namespace whose /proc/sys/fs/binfmt_misc is a fresh, empty instance: no
# foreign handler can service anything in the namespace. The host's own
# registrations are never unmounted, disabled, reset or re-registered.
iso_start() {
  local extra=()
  local m
  for m in ${ISO_EXTRA_MOUNTS:-}; do
    extra+=(-v "$m")
  done
  local daemon_cmd="/opt/ctrs/ctrs daemon"
  if [ "${ISO_BINFMT_ISOLATE:-0}" = 1 ]; then
    daemon_cmd="unshare -m sh -c 'mount -t binfmt_misc none /proc/sys/fs/binfmt_misc && exec /opt/ctrs/ctrs daemon'"
  fi
  "$D" run -d --name "$CONTAINER" --privileged --tmpfs /run \
    -v "$VOL_STATE:/var/lib/ctrs" -e CTRS_DATA_DIR=/data -v "$VOL_STORE:/data" \
    -v "$BIN:/opt/ctrs:ro" "${extra[@]}" alpine:3.22 \
    sh -c "apk add -q ${ISO_PKGS:-docker-cli curl} >/dev/null 2>&1; exec $daemon_cmd" >/dev/null \
    || iso_abort "failed to start the harness container"
  local i
  for i in $(seq 60); do
    "$D" exec "$CONTAINER" sh -c 'DOCKER_HOST=unix:///root/.local/share/ctrs/run/docker.sock docker version' >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}

iso_engine_cmd() {
  local cmd=$1
  "$D" exec "$CONTAINER" sh -c "export DOCKER_HOST=unix:///root/.local/share/ctrs/run/docker.sock; $cmd"
}

# Registrations visible inside the harness (read-only probe), newline-joined.
iso_binfmt_state() {
  "$D" exec "$CONTAINER" sh -c 'ls /proc/sys/fs/binfmt_misc 2>/dev/null || echo unavailable'
}
