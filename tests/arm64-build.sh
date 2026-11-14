#!/bin/bash
# Qualification runner for ARM64 builds on AMD64 Linux (qemu-accel.md).
#
#   bash tests/arm64-build.sh --case environment
#   bash tests/arm64-build.sh --case compatibility
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
  sed -n '2,16p' "$0" >&2
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
  for v in bash git od sha256sum grep sed cut sort timeout tar; do
    command -v "$v" >/dev/null 2>&1 && ok "tool $v" || miss "tool $v"
  done

  # Toolchain: the pin from rust-toolchain.toml, built through kache.
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

EXPECTED_SHA256=dd59e62b7ce111e08c38cfdc945da204e9014e078ef1fcfae9b0dabbc3543e17

# sha256("ctrs-arm64-qualification\n"): the fixture contract with
# tests/fixtures/arm64-build/shell-child-script/child.sh.

COMPAT_IMAGE_TAG_PREFIX=ctrsaccel/compat

case_compatibility() {
  echo "== compatibility"
  local t0=$SECONDS
  local fixture_dir="$ROOT/tests/fixtures/arm64-build/shell-child-script"
  local slow_fixture="$ROOT/tests/fixtures/arm64-build/slow"
  [ -f "$fixture_dir/Dockerfile.alpine" ] || miss "fixture $fixture_dir/Dockerfile.alpine"
  [ -f "$fixture_dir/Dockerfile.debian" ] || miss "fixture $fixture_dir/Dockerfile.debian"
  [ -x "$fixture_dir/build-id.sh" ] || miss "fixture $fixture_dir/build-id.sh (not executable)"
  [ -x "$fixture_dir/child.sh" ] || miss "fixture $fixture_dir/child.sh (not executable)"
  [ -f "$slow_fixture/Dockerfile" ] || miss "fixture $slow_fixture/Dockerfile"
  [ $FAIL = 0 ] || return 1

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
  case "$name" in
    environment) case_environment ;;
    compatibility) case_compatibility ;;
    identity)      note_unavailable "identity (planned: S2)" ;;
    platform)      note_unavailable "platform (planned: S3)" ;;
    cross)         note_unavailable "cross (planned: S4)" ;;
    lifecycle)     note_unavailable "lifecycle (planned: S5)" ;;
  esac
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
