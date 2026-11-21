#!/bin/bash
# Qualification runner for ARM64 builds on AMD64 Linux (qemu-accel.md).
#
#   bash tests/arm64-build.sh --case environment
#   bash tests/arm64-build.sh --case compatibility
#   bash tests/arm64-build.sh --case identity
#   bash tests/arm64-build.sh --case platform
#   bash tests/arm64-build.sh --case cross
#   bash tests/arm64-build.sh --case lifecycle
#   bash tests/arm64-build.sh --case environment --require-no-binfmt
#   bash tests/arm64-build.sh --all
#   bash tests/arm64-build.sh --list
#
# Exits 0 when every selected case passes, 1 when a case fails or a required
# prerequisite is missing, 2 on usage errors. Cases that are not implemented
# yet report UNAVAILABLE and make --all fail closed: an unimplemented or
# unavailable case never counts as qualification. The environment case never
# starts, provisions, upgrades or inspects-mutating ctrs's builder; binfmt
# registrations are read, never written, and the host's handlers are left
# untouched whatever the result. Build cases run in a disposable isolated
# environment (own prefix, volume and ports, removed on exit) under
# tests/lib/isolated-env.sh; host handlers are never registered, reset or
# unmounted by any case.
set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
D=${D:-docker}
SCRATCH=$ROOT/.work/tmp/qemu-accel
mkdir -p "$SCRATCH"
REQUIRE_NO_BINFMT=0
ALL=0
LIST=0
SELECTED=()
PASS=0
FAIL=0
UNAVAILABLE=0

usage() {
  sed -n '2,18p' "$0" >&2
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --case) [ $# -ge 2 ] || usage; SELECTED+=("$2"); shift 2 ;;
    --case=*) SELECTED+=("${1#*=}"); shift ;;
    --all) ALL=1; shift ;;
    --require-no-binfmt) REQUIRE_NO_BINFMT=1; shift ;;
    --list) LIST=1; shift ;;
    -h|--help) usage ;;
    *) echo "unknown argument: $1" >&2; usage ;;
  esac
done

ALL_CASES=(environment compatibility identity platform cross lifecycle)

if [ $LIST = 1 ]; then
  printf '%s\n' "${ALL_CASES[@]}"
  exit 0
fi
if [ $ALL = 1 ]; then
  SELECTED=("${ALL_CASES[@]}")
fi
if [ ${#SELECTED[@]} -eq 0 ]; then
  echo "select at least one case (--case NAME, repeatable) or --all" >&2
  exit 2
fi
for c in "${SELECTED[@]}"; do
  found=0
  for known in "${ALL_CASES[@]}"; do [ "$c" = "$known" ] && found=1; done
  [ $found = 1 ] || { echo "unknown case: $c (list with --list)" >&2; exit 2; }
done

ok()   { PASS=$((PASS + 1)); printf '  ok   %s\n' "$1"; }
info() { printf '  info %s\n' "$1"; }
miss() { printf '  MISS %s\n' "$1"; FAIL=$((FAIL + 1)); }
note_unavailable() { printf '  UNV  %s\n' "$1"; UNAVAILABLE=$((UNAVAILABLE + 1)); }

elf_machine() { od -A n -t x1 -j 18 -N 2 "$1" | tr -d ' \n'; }
elf_class()   { od -A n -t x1 -j 4 -N 1 "$1" | tr -d ' \n'; }

case_environment() {
  echo "== environment"
  local t0
  t0=$SECONDS

  local rev dirty
  rev=$(git -C "$ROOT" rev-parse HEAD 2>&1) || { miss "git revision ($rev)"; rev=""; }
  if [ -n "$rev" ]; then
    dirty=$(git -C "$ROOT" status --short | wc -l | tr -d ' ')
    if [ "$dirty" = 0 ]; then ok "git revision ${rev:0:12} (clean)"; else info "git revision ${rev:0:12} ($dirty modified/untracked paths)"; fi
  fi

  local karch mload
  karch=$(uname -m); mload=$(cut -d' ' -f1 /proc/loadavg)
  [ "$karch" = x86_64 ] && ok "host architecture x86_64" || miss "host architecture $karch (want x86_64)"
  local cpu model cores
  model=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ *//')
  cores=$(nproc)
  ok "cpu $model ($cores cores, load $mload)"
  ok "kernel $(uname -r)"

  local v
  for v in bash git od sha256sum grep sed cut sort timeout tar jaq; do
    command -v "$v" >/dev/null 2>&1 && ok "tool $v" || miss "tool $v"
  done

  if command -v cargo >/dev/null 2>&1; then
    local cv want
    cv=$(cargo --version 2>&1)
    ok "cargo $cv"
    want=$(sed -n 's/^channel = "\(.*\)"/\1/p' "$ROOT/rust-toolchain.toml")
    local rv
    rv=$(rustc --version 2>&1)
    case "$rv" in
      *"${want#nightly-}"*|*nightly*) ok "rustc $rv" ;;
      *) miss "rustc $rv (want channel $want)" ;;
    esac
  else
    miss "cargo"
  fi
  command -v kache >/dev/null 2>&1 && ok "kache $(kache --version 2>&1 | head -1)" || miss "kache (rustc wrapper not on PATH)"

  # Docker: a local unix socket serving linux/x86_64, with buildx.
  if command -v docker >/dev/null 2>&1; then
    local host server dversion ctx
    if [ -n "${DOCKER_HOST:-}" ]; then
      host=$DOCKER_HOST
    else
      ctx=$(docker context show 2>&1) || ctx=""
      host=$(docker context inspect "$ctx" --format '{{.Endpoints.docker.Host}}' 2>&1) || host=""
    fi
    case "$host" in
      unix://*) ok "docker endpoint $host" ;;
      *) miss "docker endpoint '$host' (want a local unix socket)" ;;
    esac
    server=$(docker version --format '{{.Server.Os}}/{{.Server.Arch}}' 2>&1) || server=""
    [ "$server" = "linux/amd64" ] && ok "docker server $server" || miss "docker server '$server' (want linux/amd64)"
    dversion=$(docker version --format '{{.Server.Version}}' 2>&1) || dversion="unknown"
    ok "docker server version $dversion"
    if docker buildx version >/dev/null 2>&1; then
      ok "docker buildx $(docker buildx version)"
    else
      miss "docker buildx"
    fi
    local outer
    outer=$(docker ps -a --format '{{.Names}} {{.Labels}}' 2>&1 | grep -E 'ctrs-build|dev.ctrs.builder' || true)
    if [ -n "$outer" ]; then info "outer engine ctrs-builder-like containers (read-only): $(echo "$outer" | head -3)"; else info "no ctrs-builder-like container on the outer engine (read-only)"; fi
  else
    miss "docker"
  fi

  # AMD64 artifacts (target/linux-x86_64/release) from `cargo xtask linux --arch amd64`.
  local d="$ROOT/target/linux-x86_64/release"
  for b in ctrs ctrs-init; do
    if [ -x "$d/$b" ]; then
      local m
      m=$(elf_machine "$d/$b")
      if [ "$(elf_class "$d/$b")" = 02 ] && [ "$m" = 3e00 ]; then
        ok "AMD64 artifact $d/$b"
      else
        miss "artifact $d/$b (not a 64-bit x86-64 ELF, e_machine 0x$m)"
      fi
    else
      miss "artifact $d/$b (build: cargo xtask linux --arch amd64)"
    fi
  done

  # binfmt state: read only. Foreign handlers are an observation, never a fix.
  local handlers=()
  if [ -d /proc/sys/fs/binfmt_misc ]; then
    for h in /proc/sys/fs/binfmt_misc/*; do
      [ -f "$h" ] || continue
      case "$(basename "$h")" in register|status) continue ;; esac
      local name flags interpreter
      name=$(basename "$h")
      flags=$(sed -n 's/^flags: //p' "$h" 2>/dev/null)
      interpreter=$(sed -n 's/^interpreter //p' "$h" 2>/dev/null)
      handlers+=("$name(${interpreter:-unknown} ${flags})")
    done
  fi
  if [ ${#handlers[@]} -eq 0 ]; then
    info "binfmt_misc: no registrations found"
  else
    for h in "${handlers[@]}"; do info "binfmt_misc registration: $h"; done
    if [ "$REQUIRE_NO_BINFMT" = 1 ]; then
      miss "foreign binfmt registrations present and --require-no-binfmt was passed"
    else
      info "host binfmt state is not clean-room proof; positive outcomes here do not prove binfmt independence"
    fi
  fi

  info "environment checked in $((SECONDS - t0))s"
}

binfmt_fingerprint() {
  local f
  for f in /proc/sys/fs/binfmt_misc/*; do
    [ -f "$f" ] || continue
    case "${f##*/}" in
      register) continue ;;
    esac
    sha256sum "$f" 2>/dev/null
  done | sha256sum | awk '{print $1}'
}

# Can a fresh binfmt_misc instance be mounted in a private mount namespace
# without the host's registrations being visible? Read-only: the probe
# container is discarded and never registers, unmounts or resets anything.
binfmt_isolation_probe() {
  local out foreign
  out=$("$D" run --rm --privileged alpine:3.22 sh -c 'unshare -m sh -c "mkdir -p /tmp/bm && mount -t binfmt_misc none /tmp/bm && ls /tmp/bm"' 2>/dev/null) || { echo unavailable; return 0; }
  foreign=$(printf '%s\n' "$out" | grep -v -E '^(register|status)$' | grep -c .)
  [ "$foreign" = 0 ] && echo isolated || echo shared
}

wait_builder_ready() {
  local name=$1 window=$2
  local deadline=$((SECONDS + window)) probe
  while :; do
    if probe=$(isoc "docker exec $name buildctl debug workers" 2>&1); then
      return 0
    fi
    [ "$SECONDS" -lt "$deadline" ] || break
    sleep 0.2
  done
  miss "builder did not answer after docker restart within ${window}s; last probe: ${probe:-no output}"
  isoc "docker inspect $name --format '{{json .State}}'" 2>&1
  isoc "docker logs --tail 30 $name" 2>&1
  return 1
}

IDENTITY_IMAGE_TAG_PREFIX=ctrsaccel/identity

# The managed identity contract under test (must match daemon/builder.rs;
# the unit test pins the same constants — drift fails loudly here).
PIN_REF="moby/buildkit@sha256:aa632b921ef07411d2cb77292cd34213d4f7b384001d6fceef1e1f25bf9752bb"
PIN_CONFIG_AMD64="sha256:04715b97f7210e7d3fa070701cc44fbd15b2bfceeecf060b2bbba8237c60a9fb"
STALE_REF="moby/buildkit:v0.34.2"
TAG_REF="moby/buildkit:buildx-stable-1"
MANAGED="buildx_buildkit_ctrs-build0"
BUILDER_VOLUME="${MANAGED}_state"
VOLUME_DATA="/var/lib/ctrs/volumes/$BUILDER_VOLUME/_data"
UNROUTABLE_NS="nameserver 198.51.100.1"

# S2 reconciliation, end to end, in a disposable harness. The upgrade drift
# (a builder created by a previous ctrs release, then seen by this one) is
# simulated by forging the builder's record in the engine's state store while
# the harness daemon is stopped — the only state a previous release's ctrs
# could have left behind that the public API refuses to create today.
# (Paused builders are not persisted as such, and a "running" record is
# reconciled to exited at boot, so the stale-running/paused refusal paths are
# covered by unit tests; they cannot be planted here honestly.)
case_identity() {
  echo "== identity"
  local t0=$SECONDS
  local fixture_dir="$ROOT/tests/fixtures/arm64-build/shell-child-script"
  [ -f "$fixture_dir/Dockerfile.alpine" ] || { miss "fixture $fixture_dir/Dockerfile.alpine"; return 1; }
  BIN=${BIN:-$ROOT/target/linux-x86_64/release}
  [ -x "$BIN/ctrs" ] || { miss "AMD64 artifacts at $BIN (build: cargo xtask linux --arch amd64)"; return 1; }
  [ "$(uname -m)" = x86_64 ] || { note_unavailable "identity: pin config checks are AMD64-specific (managed() picks the arm64 identity on arm64 hosts)"; return 1; }

  ISO_PKGS="docker-cli curl docker-cli-buildx"
  ISO_EXTRA_MOUNTS="$ROOT/tests/fixtures:/fixtures:ro"
  local id_prefix=${PREFIX:-ctrs-identity-$$-$RANDOM}
  source "$ROOT/tests/lib/isolated-env.sh"
  iso_endpoint_check
  iso_bin_check
  iso_prepare "$id_prefix"
  iso_trap_install
  local host_ctx_before
  host_ctx_before=$("$D" context show 2>&1) || host_ctx_before=""
  iso_start || { miss "harness engine did not answer in 60 s"; ISO_PRESERVE=1; return 1; }

  local SOCK=unix:///root/.local/share/ctrs/run/docker.sock
  local SOCKPATH=${SOCK#unix://}
  isoc() { iso_engine_cmd "$*"; }
  local idty_rc=0
  local BUILD_LOGDIR="$WORK"

  wait_engine() {
    local i
    for i in $(seq 60); do
      "$D" exec "$CONTAINER" sh -c "DOCKER_HOST=$SOCK docker version" >/dev/null 2>&1 && return 0
      sleep 1
    done
    echo "isolated-env: engine did not come back after restart" >&2
    return 1
  }

  forge_builder() {
    # $1: "stale" (owned, image -> v0.34.2, still labelled) or "foreign" (label dropped)
    local mode=$1
    "$D" stop "$CONTAINER" >/dev/null || return 1
    "$D" run --rm -v "$VOL_STORE:/s" alpine:3.22 sh -c "
      cp /s/containers.json /s/containers.json.bak
      sed -i 's|moby/buildkit@sha256:aa632b921ef07411d2cb77292cd34213d4f7b384001d6fceef1e1f25bf9752bb|$STALE_REF|g' /s/containers.json
      sed -i 's|\"image_id\":\"$PIN_CONFIG_AMD64\"|\"image_id\":\"$STALE_IMAGE_ID\"|g' /s/containers.json
      if [ \"$mode\" = foreign ]; then
        sed -i 's|\"dev.ctrs.builder\"|\"dev.ctrs.other\"|g' /s/containers.json
      fi
      test \"\$(grep -c '$STALE_REF' /s/containers.json)\" != 0 || { echo forge-stale-miss >&2; exit 3; }
      test \"\$(grep -c '$STALE_IMAGE_ID' /s/containers.json)\" != 0 || { echo forge-id-miss >&2; exit 3; }
      if [ \"$mode\" = foreign ]; then
        test \"\$(grep -c dev.ctrs.builder /s/containers.json)\" = 0 || { echo forge-label-miss >&2; exit 3; }
      fi
    " || { echo "forge failed" >&2; "$D" start "$CONTAINER" >/dev/null; return 1; }
    "$D" start "$CONTAINER" >/dev/null || return 1
    wait_engine
  }

  run_build() { # $1: log name, $2: tag
    local log="$BUILD_LOGDIR/build-$1.log"
    if iso_engine_cmd "DOCKER_BUILDKIT=0 docker build --platform linux/amd64 -t $2 -f /fixtures/arm64-build/shell-child-script/Dockerfile.alpine /fixtures/arm64-build/shell-child-script" > "$log" 2>&1; then
      grep -qF "Successfully built" "$log" && return 0
      echo "build $1: legacy builder output missing" >&2; return 1
    fi
    echo "build $1 failed (log: $log)" >&2; tail -4 "$log" >&2
    return 1
  }

  # -- Phase A: fresh install, then matching restart ----------------------
  local present
  present=$(iso_engine_cmd "docker ps -a --filter name=^${MANAGED}\$ -q")
  [ -z "$present" ] && ok "fresh install: no builder before the first build" || { miss "builder exists before first build ($present)"; idty_rc=1; }

  local report
  report=$(iso_engine_cmd "curl -s --unix-socket $SOCKPATH http://localhost/ctrs/builder")
  case "$report" in
    *'"present":false'*) ok "fresh install: diagnostics report no builder" ;;
    *) miss "fresh install: diagnostics present field wrong: $report"; idty_rc=1 ;;
  esac

  if run_build a-provision "$IDENTITY_IMAGE_TAG_PREFIX/a:prov-$RANDOM"; then
    ok "classic build provisions the builder on first need"
  else
    miss "fresh-install build failed"; ISO_PRESERVE=1; return 1
  fi
  local id_a
  id_a=$(iso_engine_cmd "docker inspect $MANAGED --format '{{.Id}}'")
  local image_a
  image_a=$(iso_engine_cmd "docker inspect $MANAGED --format '{{.Image}}'")
  [ "$image_a" = "$PIN_CONFIG_AMD64" ] && ok "builder runs the pinned image ($image_a)" || { miss "builder image $image_a, want $PIN_CONFIG_AMD64"; idty_rc=1; }
  report=$(iso_engine_cmd "curl -s --unix-socket $SOCKPATH http://localhost/ctrs/builder")
  for need in '"matches_desired":true' '"buildkit_version":"v0.35.0"' '"emulator_version":"QEMU 10.2.3"' '"upgrade":"none"'; do
    case "$report" in
      *"$need"*) ok "diagnostics: $need" ;;
      *) miss "diagnostics missing $need in: $report"; idty_rc=1 ;;
    esac
  done
  if iso_engine_cmd "docker exec $MANAGED buildkitd --version" 2>&1 | grep -qF "v0.35.0"; then
    ok "managed builder reports buildkitd v0.35.0"
  else
    miss "managed builder version probe failed"; idty_rc=1
  fi

  # Matching restart: a stopped builder from the pin is reused, never replaced.
  isoc "docker stop $MANAGED" >/dev/null
  if run_build b-reuse "$IDENTITY_IMAGE_TAG_PREFIX/b:reuse-$RANDOM"; then
    local id_b
    id_b=$(iso_engine_cmd "docker inspect $MANAGED --format '{{.Id}}'")
    [ "$id_b" = "$id_a" ] && ok "matching stopped builder reused after restart" || { miss "stopped builder was replaced ($id_a -> $id_b)"; idty_rc=1; }
    grep -qF "CACHED" "$BUILD_LOGDIR/build-b-reuse.log" && ok "build cache reused across builder restart" || { miss "restart build did not hit the build cache"; idty_rc=1; }
  else
    miss "restart build failed"; idty_rc=1
  fi
  if isoc "docker restart $MANAGED" >/dev/null 2>&1; then
    if wait_builder_ready "$MANAGED" 30; then
      ok "docker restart of the managed builder: start through the pin gate clean"
    else
      idty_rc=1
    fi
  else
    miss "docker restart of the managed builder refused"; idty_rc=1
  fi

  local harness_ctx_before
  harness_ctx_before=$(iso_engine_cmd "docker context show") || harness_ctx_before=""

  # -- Phase B: stale local tag record is detected, never consulted -------
  if isoc "docker pull $TAG_REF" >/dev/null 2>&1; then
    ok "stale tag candidate $TAG_REF pulled through ctrs"
    local tag_cfg tag_mp
    tag_cfg=$(iso_engine_cmd "docker image inspect $TAG_REF --format '{{.Id}}'")
    tag_mp=$(iso_engine_cmd "curl -s --unix-socket $SOCKPATH http://localhost/ctrs/builder" | grep -o '"matches_pin":[a-z]*' | head -1 | cut -d: -f2)
    local expect=true
    [ "$tag_cfg" = "$PIN_CONFIG_AMD64" ] || expect=false
    [ "$tag_mp" = "$expect" ] && ok "diagnostics tag.matches_pin=$tag_mp (tag ${tag_cfg:0:19} vs pin $PIN_CONFIG_AMD64)" || { miss "tag.matches_pin=$tag_mp, want $expect"; idty_rc=1; }
    if run_build c-staletag "$IDENTITY_IMAGE_TAG_PREFIX/c:stale-$RANDOM"; then
      local image_c
      image_c=$(iso_engine_cmd "docker inspect $MANAGED --format '{{.Image}}'")
      [ "$image_c" = "$PIN_CONFIG_AMD64" ] && ok "provisioning unaffected by the stale tag record" || { miss "builder image drifted with the tag ($image_c)"; idty_rc=1; }
    else
      miss "build after stale-tag pull failed"; idty_rc=1
    fi
  else
    miss "pull of $TAG_REF failed"; idty_rc=1
  fi

  # -- Phase C: failed pull on upgrade leaves the stale builder in place --
  if ! isoc "docker pull $STALE_REF" >/dev/null 2>&1; then
    miss "pull of $STALE_REF failed"; idty_rc=1
  fi
  local STALE_IMAGE_ID
  STALE_IMAGE_ID=$(iso_engine_cmd "docker image inspect $STALE_REF --format '{{.Id}}'")
  [ -n "$STALE_IMAGE_ID" ] || { miss "could not resolve the stale image id"; ISO_PRESERVE=1; return 1; }

  # The stale builder this reconcile must handle was created by a previous
  # ctrs from $STALE_REF: stop the matching builder, forge the record to
  # look like it (daemon restart reconciles it to exited stale), then the
  # pin record can be removed.
  iso_engine_cmd "docker stop $MANAGED" >/dev/null
  iso_engine_cmd "mkdir -p $VOLUME_DATA" >/dev/null
  iso_engine_cmd "echo -n ctrs-sentinel-$$ > $VOLUME_DATA/ctrs-sentinel" >/dev/null

  if ! forge_builder stale; then
    miss "forging the stale builder record"; ISO_PRESERVE=1; return 1
  fi
  local forged_id
  forged_id=$(iso_engine_cmd "docker inspect $MANAGED --format '{{.Id}}'")
  local exec_out
  exec_out=$(iso_engine_cmd "docker exec $MANAGED true" 2>&1)
  if printf '%s' "$exec_out" | grep -qF "stopped and stale"; then
    ok "stale stopped builder refused by the exec gate"
  else
    miss "stale stopped builder exec: want the gate's refusal, got: $exec_out"; idty_rc=1
  fi

  local removed_pin=1
  if ! iso_engine_cmd "docker rmi $PIN_REF" > "$BUILD_LOGDIR/rmi-pin.log" 2>&1; then
    note_unavailable "failed pull: ctrs refused to remove the pin record by digest ($(head -1 "$BUILD_LOGDIR/rmi-pin.log"))"
    removed_pin=0
  fi
  local blackholed=0
  if [ $removed_pin = 1 ]; then
    iso_engine_cmd "cp /etc/resolv.conf /etc/resolv.conf.orig" >/dev/null
    iso_engine_cmd "printf '$UNROUTABLE_NS\\n' > /etc/resolv.conf" >/dev/null
    blackholed=1
  fi

  if [ $blackholed = 1 ]; then
    if run_build d-pullfail "ctrsaccel/identity/d:pullfail-$RANDOM"; then
      miss "failed pull was not surfaced: the build succeeded with DNS blackholed"; idty_rc=1
    else
      if grep -qF "aa632b921ef07411d2cb77292cd34213d4f7b384001d6fceef1e1f25bf9752bb" "$BUILD_LOGDIR/build-d-pullfail.log"; then
        ok "failed pull surfaced to the caller (build failed citing the pin)"
      else
        miss "build failed but did not cite the pin (log: $BUILD_LOGDIR/build-d-pullfail.log)"; idty_rc=1
      fi
    fi
    local ghost
    ghost=$(iso_engine_cmd "docker ps -a --filter name=^${MANAGED}\$ --format '{{.Names}} {{.Status}}'")
    case "$ghost" in
      "$MANAGED "*) ok "stale builder untouched by the failed pull ($ghost)" ;;
      *) miss "stale builder missing after failed pull (got: $ghost)"; idty_rc=1 ;;
    esac
    isoc "cat $VOLUME_DATA/ctrs-sentinel" >/dev/null && ok "cache volume intact after failed pull" || { miss "cache volume lost after failed pull"; idty_rc=1; }
    if ! iso_engine_cmd "cat /etc/resolv.conf.orig > /etc/resolv.conf" >/dev/null; then
      miss "resolv.conf restore failed"; ISO_PRESERVE=1; return 1
    fi
    if iso_engine_cmd "grep -q 198.51.100.1 /etc/resolv.conf" >/dev/null; then
      miss "resolv.conf still points at the blackhole after restore"; ISO_PRESERVE=1; return 1
    fi
    blackholed=0
  else
    info "skipping the DNS-blackhole pull test (pin record removal refused)"
  fi

  # -- Phase D: stale stopped -> replaced, cache and old id ---------------
  if run_build e-replace "$IDENTITY_IMAGE_TAG_PREFIX/e:replace-$RANDOM"; then
    local id_e
    id_e=$(iso_engine_cmd "docker inspect $MANAGED --format '{{.Id}}'")
    [ "$id_e" != "$forged_id" ] && ok "stale stopped builder replaced by the pin" || { miss "stale builder was reused ($forged_id)"; idty_rc=1; }
    local image_e
    image_e=$(iso_engine_cmd "docker inspect $MANAGED --format '{{.Image}}'")
    [ "$image_e" = "$PIN_CONFIG_AMD64" ] && ok "replacement runs the pinned image" || { miss "replacement image $image_e, want $PIN_CONFIG_AMD64"; idty_rc=1; }
  else
    miss "build across a stale-stopped builder failed"; idty_rc=1
  fi
  if iso_engine_cmd "docker inspect $forged_id" >/dev/null 2>&1; then
    miss "old (stale) container id is still resolvable"; idty_rc=1
  else
    ok "old container id no longer resolves (inspect)"
  fi
  if iso_engine_cmd "docker exec $forged_id buildctl version" >/dev/null 2>&1; then
    miss "old container id accepted an exec"; idty_rc=1
  else
    ok "old container id no longer accepts an exec (container gone)"
  fi
  if iso_engine_cmd "docker start $forged_id" >/dev/null 2>&1; then
    miss "old container id accepted a start"; idty_rc=1
  else
    ok "old container id no longer accepts a start (container gone)"
  fi
  local sentinel
  sentinel=$(iso_engine_cmd "cat $VOLUME_DATA/ctrs-sentinel") || sentinel=""
  [ "$sentinel" = "ctrs-sentinel-$$" ] && ok "cache volume preserved across the replacement" || { miss "cache sentinel $sentinel, want ctrs-sentinel-$$"; idty_rc=1; }

  # -- Phase D2: interrupted replacement recovers from pin + volume -------
  iso_engine_cmd "docker rm -f $MANAGED" >/dev/null
  iso_engine_cmd "mkdir -p $VOLUME_DATA && echo -n ctrs-sentinel2-$$ > $VOLUME_DATA/ctrs-sentinel2" >/dev/null
  if run_build f-recreate "$IDENTITY_IMAGE_TAG_PREFIX/f:recreate-$RANDOM"; then
    local sentinel2
    sentinel2=$(iso_engine_cmd "cat $VOLUME_DATA/ctrs-sentinel2") || sentinel2=""
    local id_f
    id_f=$(iso_engine_cmd "docker inspect $MANAGED --format '{{.Id}}'")
    local image_f
    image_f=$(iso_engine_cmd "docker inspect $MANAGED --format '{{.Image}}'")
    [ "$sentinel2" = "ctrs-sentinel2-$$" ] && ok "interrupted replacement: cache volume survived re-creation" || { miss "interrupted-replacement sentinel $sentinel2"; idty_rc=1; }
    [ "$image_f" = "$PIN_CONFIG_AMD64" ] && ok "interrupted replacement: builder re-created from the pin ($id_f)" || { miss "re-created image $image_f"; idty_rc=1; }
  else
    miss "interrupted-replacement build failed"; idty_rc=1
  fi

  # -- Phase E: ownership conflict is refused actionably ------------------
  # The foreign container must exist as a real record before the forge; the
  # engine refuses to create one through the public API.
  iso_engine_cmd "mkdir -p $VOLUME_DATA && echo -n ctrs-sentinel3-$$ > $VOLUME_DATA/ctrs-sentinel3" >/dev/null
  iso_engine_cmd "docker stop $MANAGED" >/dev/null
  if ! forge_builder foreign; then
    miss "forging the foreign builder record"; ISO_PRESERVE=1; return 1
  fi
  if run_build g-foreign "ctrsaccel/identity/g:foreign-$RANDOM"; then
    miss "build against a foreign same-name builder was NOT refused"; idty_rc=1
  else
    if grep -qF "without ctrs" "$BUILD_LOGDIR/build-g-foreign.log"; then
      ok "foreign same-name container refused the build (actionable message)"
    else
      miss "foreign refusal message unexpected (log: $BUILD_LOGDIR/build-g-foreign.log)"; idty_rc=1
    fi
  fi
  local start_out
  start_out=$(iso_engine_cmd "docker start $MANAGED" 2>&1)
  if printf '%s' "$start_out" | grep -qF "without ctrs"; then
    ok "foreign same-name container refused by the start gate"
  else
    miss "foreign same-name container start: want the gate's refusal, got: $start_out"; idty_rc=1
  fi
  local exec_out
  exec_out=$(iso_engine_cmd "docker exec $MANAGED true" 2>&1)
  if printf '%s' "$exec_out" | grep -qF "without ctrs"; then
    ok "foreign same-name container refused by the exec gate"
  else
    miss "foreign same-name container exec: want the gate's refusal, got: $exec_out"; idty_rc=1
  fi
  report=$(iso_engine_cmd "curl -s --unix-socket $SOCKPATH http://localhost/ctrs/builder")
  case "$report" in
    *'"upgrade":"conflict"'*) ok "diagnostics report the ownership conflict" ;;
    *) miss "diagnostics did not report the conflict: $report"; idty_rc=1 ;;
  esac
  local foreign_id
  foreign_id=$(iso_engine_cmd "docker inspect $MANAGED --format '{{.Id}}'")
  # The operator removes the foreign container; the next build provisions fresh.
  iso_engine_cmd "docker rm -f $MANAGED" >/dev/null
  if run_build h-provision "$IDENTITY_IMAGE_TAG_PREFIX/h:replace-$RANDOM"; then
    ok "after operator removal, the next build provisions from the pin"
  else
    miss "provisioning after operator removal failed"; idty_rc=1
  fi
  sentinel=$(iso_engine_cmd "cat $VOLUME_DATA/ctrs-sentinel3") || sentinel=""
  [ "$sentinel" = "ctrs-sentinel3-$$" ] && ok "cache volume kept across the conflict cycle" || { miss "conflict-cycle sentinel $sentinel"; idty_rc=1; }

  # -- Phase F: simultaneous callers serialize on one builder -------------
  iso_engine_cmd "docker rm -f $MANAGED" >/dev/null
  local log_a="$BUILD_LOGDIR/par-a.log" log_b="$BUILD_LOGDIR/par-b.log"
  iso_engine_cmd "DOCKER_BUILDKIT=0 docker build --platform linux/amd64 -t $IDENTITY_IMAGE_TAG_PREFIX/i:par-a-$$ -f /fixtures/arm64-build/shell-child-script/Dockerfile.alpine /fixtures/arm64-build/shell-child-script" > "$log_a" 2>&1 &
  local par_a=$!
  iso_engine_cmd "DOCKER_BUILDKIT=0 docker build --platform linux/amd64 -t $IDENTITY_IMAGE_TAG_PREFIX/i:par-b-$$ -f /fixtures/arm64-build/shell-child-script/Dockerfile.alpine /fixtures/arm64-build/shell-child-script" > "$log_b" 2>&1 &
  local par_b=$!
  local par_rc=0
  wait $par_a || par_rc=1
  wait $par_b || par_rc=1
  if [ $par_rc = 0 ] && grep -qF "Successfully built" "$log_a" && grep -qF "Successfully built" "$log_b"; then
    ok "two simultaneous callers both built successfully"
  else
    miss "simultaneous callers failed (logs: $log_a, $log_b)"; tail -3 "$log_a"; tail -3 "$log_b"; idty_rc=1
  fi
  local count
  count=$(iso_engine_cmd "docker ps -a --filter name=^${MANAGED}\$ -q | wc -l")
  [ "$count" = 1 ] && ok "simultaneous callers produced exactly one builder" || { miss "builder count after parallel builds: $count"; idty_rc=1; }

  # -- Phase G: buildx entry point against the reconciled builder ---------
  if ! iso_engine_cmd "docker buildx create --name ctrs-build --driver docker-container --driver-opt default-load=true $SOCK" >/dev/null 2>&1; then
    miss "buildx create ctrs-build"; idty_rc=1
  else
    local buildx_log="$BUILD_LOGDIR/buildx.log"
    if iso_engine_cmd "DOCKER_BUILDKIT=1 docker buildx build --builder ctrs-build --progress plain --platform linux/arm64 --load -t $IDENTITY_IMAGE_TAG_PREFIX/j:buildx-$$ -f /fixtures/arm64-build/shell-child-script/Dockerfile.alpine /fixtures/arm64-build/shell-child-script" > "$buildx_log" 2>&1 && grep -qF "computed: $EXPECTED_SHA256" "$buildx_log"; then
      ok "buildx entry point reconciles against the managed builder (arm64 build, correct hash)"
    else
      miss "buildx build failed (log: $buildx_log)"; tail -4 "$buildx_log"; idty_rc=1
    fi
  fi

  # -- Phase H: stale running/paused are unit-covered, not plantable ------
  info "stale running/paused refusal paths: unit-tested (dead running records reconcile to exited at boot; paused is not persisted), not plantable end-to-end here"

  # -- Final: selection, context, and diagnostics unchanged ---------------
  local host_ctx_after harness_ctx_after
  host_ctx_after=$("$D" context show 2>&1) || host_ctx_after=""
  if [ -z "$host_ctx_before" ]; then
    note_unavailable "host docker context probe failed"
  elif [ "$host_ctx_before" = "$host_ctx_after" ]; then
    ok "host docker context unchanged ($host_ctx_after)"
  else
    miss "host docker context changed ($host_ctx_before -> $host_ctx_after)"; idty_rc=1
  fi
  harness_ctx_after=$(iso_engine_cmd "docker context show") || harness_ctx_after=""
  if [ -z "$harness_ctx_before" ]; then
    note_unavailable "harness docker context probe failed"
  elif [ "$harness_ctx_before" = "$harness_ctx_after" ]; then
    ok "harness docker context unchanged ($harness_ctx_before)"
  else
    miss "harness docker context changed"; idty_rc=1
  fi
  report=$(iso_engine_cmd "curl -s --unix-socket $SOCKPATH http://localhost/ctrs/builder")
  case "$report" in
    *'"matches_desired":true'*'"upgrade":"none"'*) ok "final diagnostics: builder matches the pin" ;;
    *) miss "final diagnostics unexpected: $report"; idty_rc=1 ;;
  esac

  info "identity checked in $((SECONDS - t0))s"
  if [ $idty_rc = 0 ]; then
    ok "identity case passed"
    return 0
  fi
  miss "identity case failed"
  ISO_PRESERVE=1
  return 1
}

# S3: platform normalization and image metadata. Focused regression tests
# plus a real export/load/inspect round trip in a disposable harness.
BASE_ALPINE=alpine@sha256:49340b346798875b5592e5d420241f2f9cfba5f47e62ebb1446a1b34734e898f

inspect_oci_export() {
  local oci_dir=$1
  if ! command -v jaq >/dev/null 2>&1; then
    miss "OCI inspection requires jaq on PATH"
    return 1
  fi
  local platform_index="$oci_dir/index.json"
  local hop with_platform nested architectures
  for hop in 1 2 3; do
    if ! with_platform=$(jaq -er '[.manifests[] | select(.platform != null)] | length' "$platform_index" 2>&1); then
      miss "OCI index parsing failed ($platform_index): $with_platform"
      return 1
    fi
    [ "$with_platform" != 0 ] && break
    if ! nested=$(jaq -er '[.manifests[] | select(.mediaType == "application/vnd.oci.image.index.v1+json")] | .[0].digest' "$platform_index" 2>&1); then
      miss "OCI index has no platform entries or readable nested index ($platform_index): $nested"
      return 1
    fi
    platform_index="$oci_dir/blobs/sha256/${nested#sha256:}"
  done
  if ! architectures=$(jaq -cer '[.manifests[].platform.architecture] | sort' "$platform_index" 2>&1); then
    miss "OCI platform parsing failed ($platform_index): $architectures"
    return 1
  fi
  local oci_rc=0
  if [ "$architectures" = '["amd64","arm64"]' ]; then
    ok "OCI index carries linux/amd64 and linux/arm64 entries"
  else
    miss "OCI index does not carry both entries: $(cat "$platform_index")"; oci_rc=1
  fi
  local darch manifest_blob cfg_digest cfg_os cfg_arch
  for darch in amd64 arm64; do
    if ! manifest_blob=$(jaq -er ".manifests[] | select(.platform.architecture == \"$darch\") | .digest" "$platform_index" 2>&1); then
      miss "OCI $darch manifest lookup failed: $manifest_blob"; oci_rc=1; continue
    fi
    if ! cfg_digest=$(jaq -er '.config.digest' "$oci_dir/blobs/sha256/${manifest_blob#sha256:}" 2>&1); then
      miss "OCI $darch config lookup failed: $cfg_digest"; oci_rc=1; continue
    fi
    local cfg_path="$oci_dir/blobs/sha256/${cfg_digest#sha256:}"
    if ! cfg_os=$(jaq -er '.os' "$cfg_path" 2>&1); then
      miss "OCI $darch config OS parsing failed: $cfg_os"; oci_rc=1; continue
    fi
    if ! cfg_arch=$(jaq -er '.architecture' "$cfg_path" 2>&1); then
      miss "OCI $darch config architecture parsing failed: $cfg_arch"; oci_rc=1; continue
    fi
    if [ "$cfg_os" = linux ] && [ "$cfg_arch" = "$darch" ]; then
      ok "OCI $darch manifest config is $cfg_os/$cfg_arch"
    else
      miss "OCI $darch manifest config is $cfg_os/$cfg_arch"; oci_rc=1
    fi
  done
  return "$oci_rc"
}

case_platform() {
  echo "== platform"
  local t0=$SECONDS
  local plat_rc=0

  echo "-- focused regression tests (host cargo)"
  local tlog="$SCRATCH/platform-cargo.log"
  : > "$tlog"
  local group
  for group in "ctrs-image registry::tests" "ctrs-image archive::tests" "ctrs daemon::builder::tests"; do
    if ! cargo test -p ${group%% *} ${group#* } >> "$tlog" 2>&1; then
      miss "cargo test -p $group (log: $tlog)"; plat_rc=1
    else
      ok "cargo test -p $group"
    fi
  done

  BIN=${BIN:-$ROOT/target/linux-x86_64/release}
  [ -x "$BIN/ctrs" ] || { miss "AMD64 artifacts at $BIN (build: cargo xtask linux --arch amd64)"; return 1; }
  [ "$(uname -m)" = x86_64 ] || { note_unavailable "platform: AMD64 host required for the OCI export check"; return 1; }

  ISO_PKGS="docker-cli curl docker-cli-buildx"
  local rt_prefix=${PREFIX:-ctrs-platform-$$-$RANDOM}
  local tag="ctrsaccel/platform-rt:$$"
  source "$ROOT/tests/lib/isolated-env.sh"
  iso_endpoint_check
  iso_bin_check
  iso_prepare "$rt_prefix"
  iso_trap_install
  iso_start || { miss "harness engine did not answer in 60 s"; ISO_PRESERVE=1; return 1; }
  local SOCK=unix:///root/.local/share/ctrs/run/docker.sock
  isoc() { iso_engine_cmd "$*"; }

  echo "-- arm64 single-platform image (digest-pinned base, no RUN)"
  printf 'FROM %s\n' "$BASE_ALPINE" > "$WORK/ctx-Dockerfile"
  isoc "mkdir -p /ctx"
  "$D" cp "$WORK/ctx-Dockerfile" "$CONTAINER:/ctx/Dockerfile" >/dev/null \
    || { miss "copying the context into the harness"; ISO_PRESERVE=1; return 1; }
  if ! isoc "DOCKER_BUILDKIT=0 docker build --platform linux/arm64 -t $tag /ctx" > "$WORK/build-rt.log" 2>&1; then
    miss "arm64 classic build (log: $WORK/build-rt.log)"; tail -5 "$WORK/build-rt.log"; ISO_PRESERVE=1; return 1
  fi
  ok "arm64 image built ($tag)"

  echo "-- save / rmi / load round trip"
  if ! isoc "docker save $tag > /root/rt.tar" >/dev/null 2>&1; then
    miss "docker save $tag"; ISO_PRESERVE=1; return 1
  fi
  if ! isoc "docker rmi $tag" >/dev/null 2>&1; then
    miss "docker rmi $tag"; plat_rc=1
  fi
  if isoc "docker load < /root/rt.tar" > "$WORK/load.log" 2>&1; then
    ok "single-platform image loads (docker format)"
  else
    miss "single-platform load failed (log: $WORK/load.log)"; tail -4 "$WORK/load.log"; ISO_PRESERVE=1; return 1
  fi
  local arch
  arch=$(isoc "docker image inspect $tag --format '{{.Architecture}}'") || arch=""
  [ "$arch" = "arm64" ] && ok "loaded image reports architecture arm64" || { miss "loaded image architecture: '$arch'"; plat_rc=1; }

  echo "-- create mismatch"
  local tag_json
  tag_json=$(isoc "curl -s --unix-socket ${SOCK#unix://} -w '\n%{http_code}' -X POST 'http://localhost/containers/create?platform=linux/amd64&name=rt-mismatch-$$' -H 'Content-Type: application/json' -d '{\"Image\": \"$tag\"}'")
  case "$tag_json" in
    *"for linux/amd64"*) ok "create with platform=linux/amd64 against an arm64 image is refused: $(head -1 <<< "$tag_json")" ;;
    *) miss "create mismatch: want the daemon's platform refusal, got: $tag_json"; plat_rc=1 ;;
  esac
  tag_json=$(isoc "curl -s --unix-socket ${SOCK#unix://} -w '\n%{http_code}' -X POST 'http://localhost/containers/create?platform=linux/arm64&name=rt-match-$$' -H 'Content-Type: application/json' -d '{\"Image\": \"$tag\"}'")
  case "$tag_json" in
    *'"Id"'*) ok "create with platform=linux/arm64 matches" ;;
    *) miss "create with matching platform was refused: $tag_json"; plat_rc=1 ;;
  esac
  isoc "docker rm rt-match-$$" >/dev/null 2>&1 || true

  echo "-- two-platform OCI export and inspection"
  if ! isoc "DOCKER_BUILDKIT=1 docker buildx create --name ctrs-build --driver docker-container --driver-opt default-load=true $SOCK" >/dev/null 2>&1; then
    miss "buildx create ctrs-build"; plat_rc=1
  fi
  if isoc "DOCKER_BUILDKIT=1 docker buildx build --builder ctrs-build --provenance=false --platform linux/amd64,linux/arm64 --output type=oci,dest=/root/export.oci.tar -f /ctx/Dockerfile /ctx" > "$WORK/oci-export.log" 2>&1; then
    ok "two-platform OCI export built"
  else
    miss "two-platform OCI export failed (log: $WORK/oci-export.log)"; tail -5 "$WORK/oci-export.log"; plat_rc=1
  fi
  if "$D" cp "$CONTAINER:/root/export.oci.tar" "$WORK/export.oci.tar" >/dev/null 2>&1; then
    local oci_dir="$WORK/oci-extract"
    mkdir -p "$oci_dir"
    tar -xf "$WORK/export.oci.tar" -C "$oci_dir"
    inspect_oci_export "$oci_dir" || plat_rc=1
  else
    miss "could not copy the OCI export out of the harness"; plat_rc=1
  fi

  echo "-- multi-platform local load is refused"
  local load_err
  if load_err=$(isoc "docker load < /root/export.oci.tar" 2>&1); then
    miss "multi-platform OCI load unexpectedly succeeded"; plat_rc=1
  else
    case "$load_err" in
      *"no manifest.json"*|*"not an image archive"*) ok "multi-platform OCI load fails clearly: $(head -1 <<< "$load_err")" ;;
      *) miss "multi-platform OCI load message unexpected: $load_err"; plat_rc=1 ;;
    esac
  fi

  isoc "docker rmi -f $tag" >/dev/null 2>&1 || true

  info "platform checked in $((SECONDS - t0))s"
  if [ $plat_rc = 0 ]; then
    ok "platform case passed"
    return 0
  fi
  miss "platform case failed"
  ISO_PRESERVE=1
  return 1
}

# Pinned cross toolchain (rustc 1.96.1, gcc 12.4.0, aarch64 musl), build-only.
CROSS_BUILDER_IMAGE=messense/rust-musl-cross:aarch64-musl@sha256:02e790506c5f15a533bc05b3af8719b16a8a2314480f6f0fdc0166432035d9b4

case_cross() {
  echo "== cross"
  local t0=$SECONDS
  local cross_rc=0

  case "$(uname -m)" in
    x86_64)  local host_plat=linux/amd64 host_triple=x86_64-unknown-linux-gnu ;;
    aarch64) local host_plat=linux/arm64 host_triple=aarch64-unknown-linux-gnu ;;
    *)       note_unavailable "cross: host architecture $(uname -m) cannot qualify the cross path"; return 1 ;;
  esac

  echo "-- xtask argument parsing (no Docker is spawned)"
  if (cd "$ROOT" && CARGO_ENCODED_RUSTFLAGS='' cargo test -q -p xtask) > "$SCRATCH/cross-xtask.log" 2>&1; then
    ok "cargo test -p xtask"
  else
    miss "cargo test -p xtask (log: $SCRATCH/cross-xtask.log)"; cross_rc=1
  fi
  local out rc
  out=$(cd "$ROOT" && CARGO_ENCODED_RUSTFLAGS='' cargo run -q -p xtask -- linux --arch banana 2>&1); rc=$?
  if [ $rc = 2 ] && case "$out" in *"not supported"*) true ;; *) false ;; esac; then
    ok "--arch banana refused with exit 2"
  else
    miss "--arch banana: exit $rc, output: $out"; cross_rc=1
  fi
  out=$(cd "$ROOT" && CARGO_ENCODED_RUSTFLAGS='' cargo run -q -p xtask -- linux --arch arm64 --arch amd64 2>&1); rc=$?
  [ $rc = 2 ] && ok "conflicting --arch refused with exit 2" || { miss "conflicting --arch: exit $rc, output: $out"; cross_rc=1; }
  out=$(cd "$ROOT" && CARGO_ENCODED_RUSTFLAGS='' cargo run -q -p xtask -- linux --arch 2>&1); rc=$?
  [ $rc = 2 ] && ok "--arch without a value refused with exit 2" || { miss "--arch without a value: exit $rc, output: $out"; cross_rc=1; }

  echo "-- default Linux execution on an AMD64 host (bare xtask, no flag)"
  if (cd "$ROOT" && CARGO_ENCODED_RUSTFLAGS='' cargo xtask linux) > "$SCRATCH/cross-amd64.log" 2>&1; then
    ok "bare cargo xtask linux"
  else
    miss "bare cargo xtask linux (log: $SCRATCH/cross-amd64.log)"; cross_rc=1
  fi
  local machine
  machine=$(elf_machine "$ROOT/target/linux-x86_64/release/ctrs" 2>/dev/null)
  [ "$machine" = 3e00 ] && ok "default AMD64 ctrs e_machine 0x3e00" || { miss "default AMD64 ctrs e_machine 0x$machine (want 0x3e00)"; cross_rc=1; }
  machine=$(elf_machine "$ROOT/target/linux-x86_64/release/ctrs-init" 2>/dev/null)
  [ "$machine" = 3e00 ] && ok "default AMD64 ctrs-init e_machine 0x3e00" || { miss "default AMD64 ctrs-init e_machine 0x$machine (want 0x3e00)"; cross_rc=1; }

  echo "-- explicit ARM64 output"
  if (cd "$ROOT" && CARGO_ENCODED_RUSTFLAGS='' cargo xtask linux --arch arm64) > "$SCRATCH/cross-arm64.log" 2>&1; then
    ok "cargo xtask linux --arch arm64"
  else
    miss "cargo xtask linux --arch arm64 (log: $SCRATCH/cross-arm64.log)"; cross_rc=1
  fi
  machine=$(elf_machine "$ROOT/target/linux/release/ctrs" 2>/dev/null)
  [ "$machine" = b700 ] && ok "explicit ARM64 ctrs e_machine 0xb700" || { miss "explicit ARM64 ctrs e_machine 0x$machine (want 0xb700)"; cross_rc=1; }
  machine=$(elf_machine "$ROOT/target/linux/release/ctrs-init" 2>/dev/null)
  [ "$machine" = b700 ] && ok "explicit ARM64 ctrs-init e_machine 0xb700" || { miss "explicit ARM64 ctrs-init e_machine 0x$machine (want 0xb700)"; cross_rc=1; }

  echo "-- examples cross-build on the build platform, never under a target emulator"
  if ! "$D" buildx version >/dev/null 2>&1; then
    note_unavailable "cross: docker buildx not available for the example builds"
    return 1
  fi
  local rust_tag="ctrsaccel/cross-rust:$$" cpp_tag="ctrsaccel/cross-cpp:$$"
  if DOCKER_BUILDKIT=1 "$D" buildx build --progress plain --no-cache --platform linux/arm64 --load -t "$rust_tag" -f "$ROOT/examples/cross/rust-musl/Dockerfile" "$ROOT/examples/cross/rust-musl" > "$SCRATCH/cross-rust.log" 2>&1; then
    ok "rust-musl example built ($rust_tag)"
  else
    miss "rust-musl example build failed (log: $SCRATCH/cross-rust.log)"; tail -5 "$SCRATCH/cross-rust.log"; cross_rc=1
  fi
  if DOCKER_BUILDKIT=1 "$D" buildx build --progress plain --no-cache --platform linux/arm64 --load -t "$cpp_tag" -f "$ROOT/examples/cross/c-cpp-musl/Dockerfile" "$ROOT/examples/cross/c-cpp-musl" > "$SCRATCH/cross-cpp.log" 2>&1; then
    ok "c-cpp-musl example built ($cpp_tag)"
  else
    miss "c-cpp-musl example build failed (log: $SCRATCH/cross-cpp.log)"; tail -5 "$SCRATCH/cross-cpp.log"; cross_rc=1
  fi
  grep -qF "build platform $host_plat; target linux/arm64; triple aarch64-unknown-linux-musl" "$SCRATCH/cross-rust.log" \
    && ok "rust build ran on $host_plat, target linux/arm64" \
    || { miss "rust build platform/target line missing from $SCRATCH/cross-rust.log"; cross_rc=1; }
  grep -qF "host=$host_triple target=aarch64-unknown-linux-musl" "$SCRATCH/cross-rust.log" \
    && ok "rust build scripts ran on $host_triple, not under emulation" \
    || { miss "rust build host/target line missing from $SCRATCH/cross-rust.log"; cross_rc=1; }
  grep -qF "build platform $host_plat; target linux/arm64; triple aarch64-unknown-linux-musl" "$SCRATCH/cross-cpp.log" \
    && ok "C/C++ build ran on $host_plat, target linux/arm64" \
    || { miss "C/C++ build platform/target line missing from $SCRATCH/cross-cpp.log"; cross_rc=1; }

  echo "-- the target images run and report as linux/arm64"
  local img out_img meta
  for img in "$rust_tag cross-fixture: fixture target ok (42 via build.rs C linkage)" "$cpp_tag cross-fixture: C++ musl static ok (42)"; do
    local tag="${img%% *}" want="${img#* }"
    out_img=$("$D" run --rm --platform linux/arm64 "$tag" 2>&1) \
      && [ "$out_img" = "$want" ] \
      && ok "$tag runs: $out_img" \
      || { miss "$tag output: '$out_img' (want '$want')"; cross_rc=1; }
    meta=$("$D" image inspect -f '{{.Os}}/{{.Architecture}}' "$tag" 2>&1)
    [ "$meta" = "linux/arm64" ] \
      && ok "$tag metadata linux/arm64" \
      || { miss "$tag metadata: '$meta' (want linux/arm64)"; cross_rc=1; }
  done

  echo "-- release artifacts are statically linked AArch64"
  local probe b
  for b in ctrs ctrs-init; do
    probe=$("$D" run --rm -v "$ROOT:/src:ro" "$CROSS_BUILDER_IMAGE" sh -c 'readelf -h /src/target/linux/release/$1; echo INTERPS: $(readelf -lW /src/target/linux/release/$1 | grep -c INTERP || true)' _ "$b" 2>&1)
    if grep -q 'Class:.*ELF64' <<< "$probe" && grep -q 'Type:.*EXEC' <<< "$probe" && grep -q 'Machine:.*AArch64' <<< "$probe" && [ "$(tail -n1 <<< "$probe")" = "INTERPS: 0" ]; then
      ok "readelf $b: ELF64 EXEC AArch64, no INTERP header"
    else
      miss "readelf $b: $(grep -E 'Class|Type|Machine|INTERPS' <<< "$probe" | tr '\n' ' ')"
      cross_rc=1
    fi
  done

  echo "-- outputs and caches are per architecture"
  "$D" volume inspect ctrs-cargo-aarch64-musl >/dev/null 2>&1 \
    && ok "cargo cache volume ctrs-cargo-aarch64-musl exists" \
    || { miss "cargo cache volume ctrs-cargo-aarch64-musl missing"; cross_rc=1; }
  "$D" volume inspect ctrs-cargo-amd64 >/dev/null 2>&1 \
    && ok "cargo cache volume ctrs-cargo-amd64 exists" \
    || { miss "cargo cache volume ctrs-cargo-amd64 missing"; cross_rc=1; }
  grep -q 'TARGETARCH' "$ROOT/examples/cross/rust-musl/Dockerfile" \
    && grep -q 'TARGETARCH' "$ROOT/examples/cross/c-cpp-musl/Dockerfile" \
    && ok "example Dockerfiles select the target via TARGETARCH" \
    || { miss "example Dockerfiles do not reference TARGETARCH"; cross_rc=1; }

  "$D" rmi "$rust_tag" "$cpp_tag" >/dev/null 2>&1 || true

  info "cross checked in $((SECONDS - t0))s"
  if [ $cross_rc = 0 ]; then
    ok "cross case passed"
    return 0
  fi
  miss "cross case failed"
  return 1
}

case_lifecycle() {
  echo "== lifecycle"
  local t0=$SECONDS
  local life_rc=0

  [ "$(uname -m)" = x86_64 ] || { note_unavailable "lifecycle: AMD64 host required"; return 1; }

  BIN=${BIN:-$ROOT/target/linux-x86_64/release}
  [ -x "$BIN/ctrs" ] || { miss "AMD64 artifacts at $BIN (build: cargo xtask linux --arch amd64)"; return 1; }

  local iso_state
  iso_state=$(binfmt_isolation_probe) || iso_state=unavailable
  local emulator_proof=1
  [ "$iso_state" = isolated ] && emulator_proof=0
  if [ "$REQUIRE_NO_BINFMT" = 1 ] && [ "$emulator_proof" != 0 ]; then
    miss "binfmt isolation unavailable ($iso_state); handler-free proof refused"
    return 1
  fi

  ISO_PKGS="docker-cli curl docker-cli-buildx"
  local life_prefix=${PREFIX:-ctrs-life-$$-$RANDOM}
  local tag_amd="ctrsaccel/life-amd64:$$" tag_arm="ctrsaccel/life-arm64:$$"
  local tag_cancel="ctrsaccel/life-cancel:$$" tag_after="ctrsaccel/life-after-cancel:$$"
  local tag_fail="ctrsaccel/life-fail-target:$$" tag_worker="ctrsaccel/life-worker:$$"
  local tag_cache="ctrsaccel/life-cache:$$"
  source "$ROOT/tests/lib/isolated-env.sh"
  iso_endpoint_check
  iso_bin_check
  iso_prepare "$life_prefix"
  iso_trap_install
  iso_start || { miss "harness engine did not answer in 60 s"; ISO_PRESERVE=1; return 1; }
  local SOCK=unix:///root/.local/share/ctrs/run/docker.sock
  isoc() { iso_engine_cmd "$*"; }
  [ "$(isoc "docker version --format '{{.Server.Os}}/{{.Server.Arch}}'")" = "linux/amd64" ] \
    && ok "isolated engine linux/amd64" \
    || { miss "isolated engine did not report linux/amd64"; ISO_PRESERVE=1; return 1; }

  if ! isoc "docker buildx create --name ctrs-build --driver docker-container --driver-opt default-load=true $SOCK" >/dev/null 2>&1; then
    miss "buildx create ctrs-build"
    ISO_PRESERVE=1
    return 1
  fi
  ok "buildx ctrs-build created"

  echo "-- concurrent builds (distinct architecture tags)"
  if ! isoc "mkdir -p /lc-concurrent && printf 'FROM %s\nRUN echo lifecycle-concurrency-ok\n' \"$BASE_ALPINE\" > /lc-concurrent/Dockerfile"; then
    miss "concurrent-build context setup failed"
    ISO_PRESERVE=1
    return 1
  fi
  ( isoc "DOCKER_BUILDKIT=0 docker build --platform linux/amd64 -t $tag_amd /lc-concurrent" > "$WORK/concurrent-amd64.log" 2>&1; echo $? > "$WORK/concurrent-amd64.rc" ) &
  ( isoc "DOCKER_BUILDKIT=0 docker build --platform linux/arm64 -t $tag_arm /lc-concurrent" > "$WORK/concurrent-arm64.log" 2>&1; echo $? > "$WORK/concurrent-arm64.rc" ) &
  wait
  local rc_amd rc_arm
  rc_amd=$(cat "$WORK/concurrent-amd64.rc")
  rc_arm=$(cat "$WORK/concurrent-arm64.rc")
  if [ "$rc_amd" = 0 ] && grep -qF "Successfully built" "$WORK/concurrent-amd64.log"; then
    ok "concurrent amd64 build succeeded"
  else
    miss "concurrent amd64 build failed (log: $WORK/concurrent-amd64.log)"; tail -4 "$WORK/concurrent-amd64.log" | sed 's/^/    /'; life_rc=1
  fi
  if [ "$rc_arm" = 0 ] && grep -qF "Successfully built" "$WORK/concurrent-arm64.log"; then
    ok "concurrent arm64 build succeeded"
  else
    miss "concurrent arm64 build failed (log: $WORK/concurrent-arm64.log)"; tail -4 "$WORK/concurrent-arm64.log" | sed 's/^/    /'; life_rc=1
  fi
  local meta_amd meta_arm
  meta_amd=$(isoc "docker image inspect -f '{{.Os}}/{{.Architecture}}' $tag_amd" 2>&1)
  meta_arm=$(isoc "docker image inspect -f '{{.Os}}/{{.Architecture}}' $tag_arm" 2>&1)
  [ "$meta_amd" = "linux/amd64" ] && ok "tag $tag_amd reports linux/amd64" || { miss "tag $tag_amd reports: $meta_amd"; life_rc=1; }
  [ "$meta_arm" = "linux/arm64" ] && ok "tag $tag_arm reports linux/arm64" || { miss "tag $tag_arm reports: $meta_arm"; life_rc=1; }

  echo "-- slow build fixture (cancellation / worker failure)"
  if ! isoc "mkdir -p /lc-slow && printf 'FROM %s\nRUN echo arm64-qualification-slow-marker && sleep 20 && echo arm64-qualification-slow-\"\"done\n' \"$BASE_ALPINE\" > /lc-slow/Dockerfile && tar -C /lc-slow -cf /lc-slow/ctx.tar Dockerfile"; then
    miss "slow-build context setup failed"
    ISO_PRESERVE=1
    return 1
  fi

  echo "-- cancellation (POST /build/cancel, 60 s deadline)"
  isoc "timeout 150 curl -sN --unix-socket /root/.local/share/ctrs/run/docker.sock -X POST 'http://localhost/build?t=$tag_cancel&platform=linux/arm64&buildid=life-cancel-$$' -H 'Content-Type: application/x-tar' --data-binary @/lc-slow/ctx.tar" > "$WORK/cancel.log" 2>&1 &
  local client_pid=$!
  local ready procs i
  ready=0
  for i in $(seq 90); do
    procs=$(isoc "docker exec $MANAGED pgrep -af 'sleep 20' 2>/dev/null || true")
    [ -n "$procs" ] && { ready=1; break; }
    sleep 0.5
  done
  if [ "$ready" = 1 ]; then
    ok "slow build reached its RUN step"
  else
    miss "slow build never reached its RUN step (log: $WORK/cancel.log)"
    kill $client_pid 2>/dev/null; wait $client_pid 2>/dev/null || true
    ISO_PRESERVE=1
    return 1
  fi
  local cancel_t=$SECONDS
  isoc "curl -sN --unix-socket /root/.local/share/ctrs/run/docker.sock -X POST 'http://localhost/build/cancel?id=life-cancel-$$'" > "$WORK/cancel-req.log" 2>&1
  local seen=""
  for i in $(seq 120); do
    procs=$(isoc "docker exec $MANAGED pgrep -af 'buildctl|sleep 20' 2>/dev/null || true")
    [ -z "$procs" ] && { seen=1; break; }
    sleep 0.5
  done
  local cancel_dt=$((SECONDS - cancel_t))
  wait $client_pid 2>/dev/null || true
  if grep -qF "arm64-qualification-slow-done" "$WORK/cancel.log"; then
    miss "build ran to completion despite the cancel (slow-done marker present)"
    life_rc=1
  else
    ok "build did not run to completion (slow-done marker absent)"
  fi
  if [ -n "$seen" ]; then
    ok "build interrupted within the 60 s cancellation deadline (${cancel_dt}s)"
  else
    miss "build processes still running ${cancel_dt}s after cancel: $procs"
    life_rc=1
  fi
  local tags
  tags=$(isoc "docker images --format '{{.Repository}}:{{.Tag}}'")
  case "$tags" in
    *"life-cancel:"*) miss "cancelled build published $tag_cancel"; life_rc=1 ;;
    *) ok "cancelled build published no image" ;;
  esac
  isoc "docker ps" >/dev/null 2>&1 && ok "engine answered after cancellation" || { miss "engine did not answer after cancellation"; life_rc=1; }
  if isoc "DOCKER_BUILDKIT=0 docker build --platform linux/arm64 -t $tag_after /lc-slow" > "$WORK/after-cancel.log" 2>&1 && grep -qF "Successfully built" "$WORK/after-cancel.log"; then
    ok "a subsequent build succeeds after cancellation"
  else
    miss "subsequent build failed after cancellation (log: $WORK/after-cancel.log)"
    tail -4 "$WORK/after-cancel.log" | sed 's/^/    /'
    life_rc=1
  fi

  echo "-- worker failure mid-build"
  isoc "DOCKER_BUILDKIT=0 docker build --no-cache --platform linux/arm64 -t $tag_worker /lc-slow" > "$WORK/worker.log" 2>&1 &
  local wpid=$!
  local wready=0
  for i in $(seq 90); do
    procs=$(isoc "docker exec $MANAGED pgrep -af 'sleep 20' 2>/dev/null || true")
    [ -n "$procs" ] && { wready=1; break; }
    sleep 0.5
  done
  if [ "$wready" = 1 ]; then
    if isoc "docker stop $MANAGED" >/dev/null 2>&1; then
      ok "managed builder stopped mid-build (worker failure injected)"
    else
      miss "could not stop the managed builder"
      life_rc=1
    fi
  else
    miss "worker-failure build never reached its RUN step (log: $WORK/worker.log)"
    life_rc=1
  fi
  wait $wpid
  local wrc=$?
  [ $wrc != 0 ] && ok "build failed when its worker died (exit $wrc)" || { miss "build unexpectedly succeeded after the worker died (log: $WORK/worker.log)"; life_rc=1; }
  local ps_a
  ps_a=$(isoc "docker ps -a --format '{{.Names}}'")
  case "$ps_a" in
    *"$MANAGED"*) ok "builder record kept after worker failure" ;;
    *) miss "builder record lost after worker failure"; life_rc=1 ;;
  esac
  if isoc "DOCKER_BUILDKIT=0 docker build --platform linux/arm64 -t ctrsaccel/life-worker2:$$ /lc-slow" > "$WORK/worker2.log" 2>&1 && grep -qF "Successfully built" "$WORK/worker2.log"; then
    ok "build succeeds once the worker is restarted (ensure_running reuses the stopped matching builder)"
  else
    miss "build did not recover after worker failure (log: $WORK/worker2.log)"
    tail -4 "$WORK/worker2.log" | sed 's/^/    /'
    life_rc=1
  fi

  echo "-- failed target execution"
  if ! isoc "mkdir -p /lc-fail && printf 'FROM %s\nRUN echo arm64-qualification-fail-marker; exit 23\n' \"$BASE_ALPINE\" > /lc-fail/Dockerfile"; then
    miss "fail-target context setup failed"
    ISO_PRESERVE=1
    return 1
  fi
  local fail_out fail_rc
  fail_out=$(isoc "DOCKER_BUILDKIT=0 docker build --no-cache --platform linux/arm64 -t $tag_fail /lc-fail" 2>&1)
  fail_rc=$?
  if [ $fail_rc != 0 ] && printf '%s\n' "$fail_out" | grep -qE 'exit code[:=]? ?23|exit 23'; then
    ok "failed RUN surfaces the target exit code 23"
  else
    miss "failed target execution: rc=$fail_rc, output: $(printf '%s\n' "$fail_out" | tail -3 | tr '\n' ' ')"
    life_rc=1
  fi
  tags=$(isoc "docker images --format '{{.Repository}}:{{.Tag}}'")
  case "$tags" in
    *"life-fail-target:"*) miss "failed build published $tag_fail"; life_rc=1 ;;
    *) ok "failed build published no image" ;;
  esac
  if isoc "DOCKER_BUILDKIT=0 docker build --platform linux/amd64 -t ctrsaccel/life-native-ok:$$ /lc-concurrent" > "$WORK/native-ok.log" 2>&1 && grep -qF "Successfully built" "$WORK/native-ok.log"; then
    ok "native amd64 build remains functional after the target failure"
  else
    miss "native amd64 build failed after the target failure (log: $WORK/native-ok.log)"
    life_rc=1
  fi

  echo "-- cache reuse across a daemon restart"
  if ! isoc "mkdir -p /lc-cache && printf 'FROM %s\nRUN echo lifecycle-cache-warm > /warm\nRUN echo lifecycle-cache-sentinel > /sentinel\n' \"$BASE_ALPINE\" > /lc-cache/Dockerfile"; then
    miss "cache context setup failed"
    ISO_PRESERVE=1
    return 1
  fi
  if ! isoc "DOCKER_BUILDKIT=0 docker build --platform linux/arm64 -t $tag_cache /lc-cache" > "$WORK/cache-1.log" 2>&1; then
    miss "cache-warming build failed (log: $WORK/cache-1.log)"
    ISO_PRESERVE=1
    return 1
  fi
  if ! "$D" restart "$CONTAINER" >/dev/null 2>&1; then
    miss "harness daemon restart failed"
    ISO_PRESERVE=1
    return 1
  fi
  local ready_again=0
  for i in $(seq 60); do
    "$D" exec "$CONTAINER" sh -c 'DOCKER_HOST=unix:///root/.local/share/ctrs/run/docker.sock docker version' >/dev/null 2>&1 && { ready_again=1; break; }
    sleep 1
  done
  if [ "$ready_again" = 1 ]; then
    ok "daemon answered after restart"
  else
    miss "daemon did not answer within 60 s of the restart"
    life_rc=1
  fi
  if isoc "DOCKER_BUILDKIT=0 docker build --platform linux/arm64 -t $tag_cache /lc-cache" > "$WORK/cache-2.log" 2>&1; then
    ok "build after daemon restart succeeded"
  else
    miss "post-restart build failed (log: $WORK/cache-2.log)"
    tail -4 "$WORK/cache-2.log" | sed 's/^/    /'
    life_rc=1
  fi
  grep -qF "CACHED" "$WORK/cache-2.log" && ok "build cache hit after daemon restart" || { miss "no CACHED lines in the post-restart build (log: $WORK/cache-2.log)"; life_rc=1; }

  echo "-- emulator diagnostics (fault injection in disposable builder state)"
  if [ "$emulator_proof" != 0 ]; then
    info "binfmt isolation not provable on this host ($iso_state): the bundled emulator is not exercised; arm64 RUN fault-injection proof stays Needs environment"
    if [ "$REQUIRE_NO_BINFMT" = 1 ]; then
      miss "handler-free proof unavailable ($iso_state)"
      life_rc=1
    fi
  fi
  # Fault injection valid wherever the harness builder runs: diagnostics are
  # read-only probes of the disposable builder's filesystem.
  local emu=/usr/bin/buildkit-qemu-aarch64
  if isoc "docker exec $MANAGED sh -c 'test -e $emu'"; then
    for fault in missing nonexec corrupt; do
      isoc "docker exec $MANAGED sh -c 'cp $emu ${emu}.qual-bak'" >/dev/null 2>&1 || { miss "could not back up the bundled emulator"; life_rc=1; continue; }
      case "$fault" in
        missing) isoc "docker exec $MANAGED sh -c 'rm $emu'" >/dev/null 2>&1 || miss "could not remove the emulator for the $fault fault" ;;
        nonexec) isoc "docker exec $MANAGED sh -c 'chmod 000 $emu'" >/dev/null 2>&1 || miss "could not chmod the emulator for the $fault fault" ;;
        corrupt) isoc "docker exec $MANAGED sh -c 'printf garbage-not-elf > ${emu}.qual-corrupt && cp ${emu}.qual-corrupt $emu && chmod 755 $emu && rm -f ${emu}.qual-corrupt'" >/dev/null 2>&1 || miss "could not corrupt the emulator for the $fault fault" ;;
      esac
      local diag_fault
      diag_fault=$(isoc "curl -s --unix-socket /root/.local/share/ctrs/run/docker.sock http://localhost/ctrs/builder")
      case "$fault" in
        missing|nonexec)
          case "$diag_fault" in
            *'"status":"absent"'*) ok "diagnostics name the missing capability ($fault)" ;;
            *) miss "diagnostics for the $fault emulator do not report absent: $(printf '%s' "$diag_fault" | tail -c 200)"; life_rc=1 ;;
          esac ;;
        corrupt)
          case "$diag_fault" in
            *'"status":"unusable"'*) ok "diagnostics name the corrupt emulator as unusable" ;;
            *) miss "diagnostics for the corrupt emulator do not report unusable: $(printf '%s' "$diag_fault" | tail -c 200)"; life_rc=1 ;;
          esac ;;
      esac
      case "$diag_fault" in
        *'"remediation":"rebuild the managed builder from the pinned image'*) ok "diagnostics carry the remediation ($fault)" ;;
        *) miss "diagnostics for the $fault emulator lack the remediation text"; life_rc=1 ;;
      esac
      if isoc "DOCKER_BUILDKIT=0 docker build --platform linux/amd64 -t ctrsaccel/life-native-$fault:$$ /lc-concurrent" > "$WORK/native-emu.log" 2>&1 && grep -qF "Successfully built" "$WORK/native-emu.log"; then
        ok "native amd64 build remains functional ($fault emulator)"
      else
        miss "native amd64 build failed with the $fault emulator (log: $WORK/native-emu.log)"
        life_rc=1
      fi
      isoc "docker exec $MANAGED sh -c 'cp ${emu}.qual-bak $emu && chmod 755 $emu && rm -f ${emu}.qual-bak'" >/dev/null 2>&1 || { miss "could not restore the bundled emulator after the $fault fault"; life_rc=1; }
      local diag_ok
      diag_ok=$(isoc "curl -s --unix-socket /root/.local/share/ctrs/run/docker.sock http://localhost/ctrs/builder")
      case "$diag_ok" in
        *'"status":"ok"'*) ok "diagnostics report the emulator ok after restore ($fault)" ;;
        *) miss "diagnostics did not report ok after restoring the emulator ($fault): $(printf '%s' "$diag_ok" | tail -c 200)"; life_rc=1 ;;
      esac
    done
  else
    info "bundled emulator not found in the managed builder ($emu); fault injection skipped"
  fi

  echo "-- cleanup"
  local remaining
  remaining=$(isoc "docker ps -a --format '{{.Names}}'")
  [ -n "$remaining" ] && info "containers after the case: $(printf '%s' "$remaining" | tr '\n' ' ')"
  isoc "docker rmi -f $tag_amd $tag_arm $tag_cancel $tag_after $tag_fail $tag_worker ctrsaccel/life-worker2:$$ $tag_cache ctrsaccel/life-native-ok:$$ ctrsaccel/life-native-missing:$$ ctrsaccel/life-native-nonexec:$$ ctrsaccel/life-native-corrupt:$$" >/dev/null 2>&1 || true

  info "lifecycle checked in $((SECONDS - t0))s"
  if [ $life_rc = 0 ]; then
    ok "lifecycle case passed"
    return 0
  fi
  miss "lifecycle case failed"
  ISO_PRESERVE=1
  return 1
}

EXPECTED_SHA256=dd59e62b7ce111e08c38cfdc945da204e9014e078ef1fcfae9b0dabbc3543e17

# sha256("ctrs-arm64-qualification\n"): the fixture contract with
# tests/fixtures/arm64-build/shell-child-script/child.sh.

COMPAT_IMAGE_TAG_PREFIX=ctrsaccel/compat

case_compatibility() {
  echo "== compatibility"
  local t0=$SECONDS
  local failures_before=$FAIL
  local fixture_dir="$ROOT/tests/fixtures/arm64-build/shell-child-script"
  local slow_fixture="$ROOT/tests/fixtures/arm64-build/slow"
  [ -f "$fixture_dir/Dockerfile.alpine" ] || miss "fixture $fixture_dir/Dockerfile.alpine"
  [ -f "$fixture_dir/Dockerfile.debian" ] || miss "fixture $fixture_dir/Dockerfile.debian"
  [ -x "$fixture_dir/build-id.sh" ] || miss "fixture $fixture_dir/build-id.sh (not executable)"
  [ -x "$fixture_dir/child.sh" ] || miss "fixture $fixture_dir/child.sh (not executable)"
  [ -f "$slow_fixture/Dockerfile" ] || miss "fixture $slow_fixture/Dockerfile"
  [ "$FAIL" = "$failures_before" ] || return 1

  BIN=${BIN:-$ROOT/target/linux-x86_64/release}
  [ -x "$BIN/ctrs" ] || { miss "AMD64 artifacts at $BIN (build: cargo xtask linux --arch amd64)"; return 1; }

  ISO_PKGS="docker-cli curl docker-cli-buildx"
  ISO_EXTRA_MOUNTS="$ROOT/tests/fixtures:/fixtures:ro"
  local compat_prefix=${PREFIX:-ctrs-compat-$$-$RANDOM}
  if [ "$REQUIRE_NO_BINFMT" = 1 ]; then
    local iso_state
    iso_state=$(binfmt_isolation_probe) || iso_state=unavailable
    if [ "$iso_state" != isolated ]; then
      miss "foreign handlers cannot be isolated on this host ($iso_state); handler-free proof unavailable"
      return 1
    fi
    ISO_BINFMT_ISOLATE=1
    ok "binfmt isolation probe: fresh instance has no foreign registrations"
  fi
  source "$ROOT/tests/lib/isolated-env.sh"
  iso_endpoint_check
  iso_bin_check
  iso_prepare "$compat_prefix"
  iso_trap_install
  local host_binfmt_before
  host_binfmt_before=$(binfmt_fingerprint)
  echo "compat: prefix $compat_prefix, host binfmt fingerprint ${host_binfmt_before:0:16}… (read-only)"
  iso_start || { miss "harness engine did not answer in 60 s"; ISO_PRESERVE=1; return 1; }

  local SOCK=unix:///root/.local/share/ctrs/run/docker.sock
  local server
  server=$(iso_engine_cmd "docker version --format '{{.Server.Os}}/{{.Server.Arch}}'" 2>&1) || { miss "engine not reachable ($server)"; ISO_PRESERVE=1; return 1; }
  [ "$server" = "linux/amd64" ] && ok "isolated engine $server" || { miss "isolated engine $server"; ISO_PRESERVE=1; return 1; }

  if ! iso_engine_cmd "docker buildx create --name ctrs-build --driver docker-container --driver-opt default-load=true $SOCK" >/dev/null 2>&1; then
    miss "docker buildx create ctrs-build"
    ISO_PRESERVE=1
    return 1
  fi
  ok "buildx ctrs-build created (docker-container driver, default-load)"

  local compat_rc=0
  local EMU_YES=0 EMU_NO=0
  compat_build() {
    # $1=entry, $2=dockerfile basename, $3=platform, $4=tag, $5=elf-path, $6=expectMachine
    local entry=$1 df=$2 platform=$3 tag=$4 elfpath=$5 want_machine=$6
    local log="$WORK/build-$entry-$df-${platform//\//-}.log"
    local build_cmd
    case "$entry" in
      buildx)
        build_cmd="DOCKER_BUILDKIT=1 docker buildx build --builder ctrs-build --progress plain --no-cache --platform $platform --load -t $tag -f /fixtures/arm64-build/shell-child-script/$df /fixtures/arm64-build/shell-child-script"
        ;;
      classic)
        build_cmd="DOCKER_BUILDKIT=0 docker build --no-cache --platform $platform -t $tag -f /fixtures/arm64-build/shell-child-script/$df /fixtures/arm64-build/shell-child-script"
        ;;
      *) echo "compat_build: unknown entry $entry" >&2; return 2 ;;
    esac
    if ! iso_engine_cmd "$build_cmd" > "$log" 2>&1; then
      printf '  FAIL compat build %s %s %s (log: %s)\n' "$entry" "$df" "$platform" "$log"
      tail -5 "$log" | sed 's/^/    /'
      ISO_PRESERVE=1
      return 1
    fi
    # The classic path is only proven when ctrs's legacy /build API answered;
    # its closing lines are the legacy CLI's stream output.
    if [ "$entry" = classic ] && ! grep -qF "Successfully built" "$log"; then
      printf '  FAIL compat classic %s %s: legacy /build output missing ("Successfully built")\n' "$df" "$platform"
      head -5 "$log" | sed 's/^/    /'
      ISO_PRESERVE=1
      return 1
    fi
    local need
    for need in "build-id: entered" "child: entered" "computed: $EXPECTED_SHA256" "child: done" "build-id: done"; do
      if ! grep -qF "$need" "$log"; then
        printf '  FAIL compat build %s %s %s: missing %q in log\n' "$entry" "$df" "$platform" "$need"
        tail -5 "$log" | sed 's/^/    /'
        ISO_PRESERVE=1
        return 1
      fi
    done
    local base="${df%.alpine}"; base="${base%.debian}"
    local mount_expect="no"
    if [ "$platform" != "linux/amd64" ]; then
      if [ "${ISO_BINFMT_ISOLATE:-0}" = 1 ]; then
        mount_expect="yes"
      else
        mount_expect=""
      fi
    fi
    if [ -n "$mount_expect" ]; then
      if ! grep -qF "emulator-mount: $mount_expect" "$log"; then
        printf '  FAIL compat build %s %s %s: want emulator-mount: %s\n' "$entry" "$df" "$platform" "$mount_expect"
        ISO_PRESERVE=1
        return 1
      fi
    else
      case "$(grep -oE 'emulator-mount: (yes|no)' "$log" | head -1 | awk '{print $2}')" in
        yes) EMU_YES=$((EMU_YES + 1)) ;;
        no)  EMU_NO=$((EMU_NO + 1)) ;;
        *)   printf '  FAIL compat build %s %s %s: emulator-mount line missing\n' "$entry" "$df" "$platform"; ISO_PRESERVE=1; return 1 ;;
      esac
    fi
    local arch_expect=arm64; [ "$platform" = "linux/amd64" ] && arch_expect=amd64
    local meta
    meta=$(iso_engine_cmd "docker image inspect -f '{{.Os}}/{{.Architecture}}' $tag" 2>&1) || { miss "inspect $tag ($meta)"; return 1; }
    [ "$meta" = "linux/$arch_expect" ] && ok "image metadata $tag → $meta" || { miss "image metadata $tag → $meta (want linux/$arch_expect)"; return 1; }
    local cid
    cid=$(iso_engine_cmd "docker create --name elfcheck-$$-$RANDOM $tag" 2>&1) || { miss "docker create $tag ($cid)"; return 1; }
    cid=$(echo "$cid" | tr -d '\r')
    local tmpbase="/tmp/efface-$$-$RANDOM-$(basename "$elfpath")"
    if ! iso_engine_cmd "docker cp $cid:$elfpath $tmpbase" >/dev/null 2>&1; then
      printf '  FAIL compat elf %s %s %s: nested docker cp %s failed\n' "$entry" "$df" "$platform" "$elfpath"
      iso_engine_cmd "docker rm -f $cid" >/dev/null 2>&1
      ISO_PRESERVE=1
      return 1
    fi
    local host_file="$WORK/efcheck-$entry-$df-${platform//\//-}"
    if ! "$D" cp "$CONTAINER:$tmpbase" "$host_file" >/dev/null 2>&1; then
      printf '  FAIL compat elf %s %s %s: docker cp %s → host failed\n' "$entry" "$df" "$platform" "$elfpath"
      iso_engine_cmd "docker rm -f $cid" >/dev/null 2>&1
      ISO_PRESERVE=1
      return 1
    fi
    iso_engine_cmd "rm -f $tmpbase" >/dev/null 2>&1
    iso_engine_cmd "docker rm -f $cid" >/dev/null 2>&1
    local machine
    machine=$(od -A n -t x1 -j 18 -N 2 "$host_file" | tr -d ' \n')
    [ "$machine" = "$want_machine" ] && ok "target ELF architecture $tag ($elfpath) → 0x$machine" || { miss "target ELF $tag ($elfpath) → 0x$machine (want 0x$want_machine)"; return 1; }
    ok "compat build $entry $df $platform"
    return 0
  }

  compat_matrix() {
    local entry=$1
    compat_build "$entry" Dockerfile.alpine linux/amd64   "$COMPAT_IMAGE_TAG_PREFIX/musl:amd64-${RANDOM}" /bin/busybox 3e00 || compat_rc=1
    compat_build "$entry" Dockerfile.alpine linux/arm64   "$COMPAT_IMAGE_TAG_PREFIX/musl:arm64-${RANDOM}" /bin/busybox b700 || compat_rc=1
    compat_build "$entry" Dockerfile.debian linux/arm64   "$COMPAT_IMAGE_TAG_PREFIX/glibc:arm64-${RANDOM}" /bin/dash b700 || compat_rc=1
  }
  compat_matrix buildx
  compat_matrix classic

  # Version proof: the managed builder must be the frozen candidate.
  local bv
  bv=$(iso_engine_cmd "docker exec buildx_buildkit_ctrs-build0 buildkitd --version" 2>&1)
  case "$bv" in
    *v0.35.0*) ok "managed builder is the frozen candidate ($bv)" ;;
    *) miss "managed builder version: $bv (want v0.35.0)"; compat_rc=1 ;;
  esac

  # Process evidence: a deliberately slow build whose RUN step carries a
  # marker; the poller records the emulator's argv from the kernel while it
  # is running (out-of-band of BuildKit's own output).
  local slow_log="$WORK/build-buildx-slow.log"
  local slow_tag="$COMPAT_IMAGE_TAG_PREFIX/slow:arm64-$RANDOM"
  "$D" exec "$CONTAINER" sh -c "export DOCKER_HOST=$SOCK; DOCKER_BUILDKIT=1 docker buildx build --builder ctrs-build --progress plain --no-cache --platform linux/arm64 --load -t $slow_tag -f /fixtures/arm64-build/slow/Dockerfile /fixtures/arm64-build/slow" > "$slow_log" 2>&1 &
  local slow_pid=$!
  local slow_seen=""
  for _ in $(seq 80); do
    local listing
    listing=$(iso_engine_cmd 'for p in /proc/[0-9]*; do tr "\0" " " < "$p/cmdline" 2>/dev/null; echo; done')
    case "$listing" in
      *qemu*slow-marker*)
        slow_seen=$(printf '%s\n' "$listing" | grep -E 'qemu.*slow-marker' | head -1)
        break
        ;;
    esac
    kill -0 $slow_pid 2>/dev/null || break
    sleep 0.5
  done
  wait $slow_pid
  local slow_rc=$?
  if [ $slow_rc -ne 0 ]; then
    printf '  FAIL compat slow build (log: %s)\n' "$slow_log"
    tail -5 "$slow_log" | sed 's/^/    /'
    ISO_PRESERVE=1
    compat_rc=1
  elif [ -z "$slow_seen" ]; then
    printf '  FAIL compat process evidence: no emulator process running the marker step observed\n'
    ISO_PRESERVE=1
    compat_rc=1
  else
    ok "process evidence: $slow_seen"
  fi

  local host_binfmt_after
  host_binfmt_after=$(binfmt_fingerprint)
  [ "$host_binfmt_before" = "$host_binfmt_after" ] && ok "host binfmt registrations unchanged ($(echo "$host_binfmt_before" | cut -c1-16)…)" || { miss "host binfmt registrations changed during the run"; compat_rc=1; }

  if [ "${ISO_BINFMT_ISOLATE:-0}" = 1 ]; then
    local inside
    inside=$(iso_binfmt_state | grep -v -E '^(register|status)$' | grep -c .)
    [ "$inside" = 0 ] && ok "isolated binfmt instance: no foreign registrations" || { miss "isolated binfmt instance has $inside foreign registration(s)"; compat_rc=1; }
  else
    info "arm64 builds were served with the host binfmt handler visible ($EMU_NO shared-handler, $EMU_YES bundled-emulator); handler-free proof requires --require-no-binfmt on an isolated host"
  fi

  info "compatibility checked in $((SECONDS - t0))s"
  if [ $compat_rc = 0 ]; then
    ok "compatibility case passed"
    return 0
  fi
  miss "compatibility case failed"
  return 1
}

run_case() {
  local name=$1
  ISO_PRESERVE=0
  local rc=0
  case "$name" in
    environment) case_environment ;;
    compatibility) case_compatibility ;;
    identity)      case_identity ;;
    platform)      case_platform ;;
    cross)         case_cross ;;
    lifecycle)     case_lifecycle ;;
  esac
  rc=$?
  [ "${ISO_MINE:-0}" = 1 ] && iso_release "$rc"
  return $rc
}



for c in "${SELECTED[@]}"; do
  run_case "$c"
done

echo "----"
if [ $UNAVAILABLE -gt 0 ]; then
  echo "runner: $PASS passed, $FAIL failed, $UNAVAILABLE unavailable"
  exit 1
fi
echo "runner: $PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
