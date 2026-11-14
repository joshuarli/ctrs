#!/bin/bash
# Qualification runner for ARM64 builds on AMD64 Linux (qemu-accel.md).
#
#   bash tests/arm64-build.sh --case environment
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
# untouched whatever the result.
set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
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

run_case() {
  local name=$1
  case "$name" in
    environment) case_environment ;;
    compatibility) note_unavailable "compatibility (planned: S1)" ;;
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
