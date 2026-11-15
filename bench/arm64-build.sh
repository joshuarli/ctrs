#!/bin/bash
# S6 benchmark for ARM64 builds on AMD64 Linux (qemu-accel.md).
# Equivalent-work comparison of three ways to build the same workload:
#
#   A  the unchanged preparation baseline + its actual old pin
#      (moby/buildkit:buildx-stable-1 @ sha256:c5f8862f52499773af85bc07695b2379ef08e8002352b0df2c4864c91d78dabe,
#      v0.34.2 content — recorded as a negative baseline when it fails; never a zero-time denominator)
#   B  the qualified pinned emulation (moby/buildkit@sha256:aa632b921ef07411d2cb77292cd34213d4f7b384001d6fceef1e1f25bf9752bb)
#   C  native cross-compilation of the same workload/output (the same qualified builder,
#      BUILD_PLATFORM=linux/amd64; identical toolchain, flags and Dockerfile)
#
# States: cold (all layers invalid), incremental (exactly one source file touched,
# in a scratch copy — the fixture stays frozen), layer-hit (no source change).
# A compiler-cache state is reported as unavailable — no compiler cache is
# configured anywhere in this qualification; it is never counted as a hit.
#
# Five valid samples per (path, state), rotated (A/B/C, B/C/A, C/A/B).
# Provisioning (builder create, pull, bootstrap) is measured separately and
# excluded from samples. Every timed group is gated by perf-gate-ready before
# and after (overlapping load invalidates the group; the run is deferred,
# never passed). Builders are created fresh per (workload, mode, path) phase,
# pinned per path, and removed on exit — ctrs's managed builder and every
# user builder are never touched. Per-sample ELF machine, image architecture,
# golden output and (per phase) process-tree cgroup memory.peak are recorded.
# Cold samples include registry downloads (no shared cache between phases);
# this is identical across paths and documented in the report.
#
#   bash bench/arm64-build.sh             # 5 samples per (path, state), all states
#   bash bench/arm64-build.sh --all-states --samples 5   # explicit: every state, N samples (the default)
#   bash bench/arm64-build.sh --verify    # short pilot + accounting checks
#   bash bench/arm64-build.sh --samples N # N samples per (path, state)
#   bash bench/arm64-build.sh --keep      # keep builders/images (debugging)
#   bash bench/arm64-build.sh --list      # paths and states
#
# Exit codes: 0 ok, 1 failure, 2 usage, 75 host busy (deferred, never passed).
# The report lands in bench/out/<run-id>/{samples.tsv,provisioning.tsv,summary.md,machine.txt}.
set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
BENCH=$ROOT/bench
SCRATCH=$ROOT/.work/tmp/bench
OUT_BASE=$BENCH/results

PIN_A=moby/buildkit:buildx-stable-1@sha256:c5f8862f52499773af85bc07695b2379ef08e8002352b0df2c4864c91d78dabe
PIN_B=moby/buildkit@sha256:aa632b921ef07411d2cb77292cd34213d4f7b384001d6fceef1e1f25bf9752bb

VERIFY=0
SAMPLES=5
KEEP=0
LIST=0

while [ $# -gt 0 ]; do
  case "$1" in
    --all-states) shift ;;
    --verify) VERIFY=1; shift ;;
    --samples) [ $# -ge 2 ] || { echo "--samples needs a value" >&2; exit 2; }
               case "$2" in (*[!0-9]*|'') echo "--samples must be a positive integer" >&2; exit 2 ;; esac
               [ "$2" -ge 1 ] || { echo "--samples must be >= 1" >&2; exit 2; }
               SAMPLES=$2; shift 2 ;;
    --samples=*) SAMPLES=${1#*=}
               case "$SAMPLES" in (*[!0-9]*|'') echo "--samples must be a positive integer" >&2; exit 2 ;; esac
               [ "$SAMPLES" -ge 1 ] || { echo "--samples must be >= 1" >&2; exit 2; }
               shift ;;
    --keep) KEEP=1; shift ;;
    --list) LIST=1; shift ;;
    -h|--help) sed -n '2,30p' "$0" >&2; exit 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

WORKLOADS=(rust-workload c-cpp-workload)
STATES=(cold incremental layer-hit)
PATHS=(A B C)
D=${DOCKER:-docker}

if [ "$LIST" = 1 ]; then
  printf 'paths:   A (old pin %s)\n         B (qualified pin %s)\n         C (cross, same qualified builder, BUILD_PLATFORM=linux/amd64)\n' "$PIN_A" "$PIN_B"
  printf 'states:  cold, incremental, layer-hit (compiler-cache: unavailable)\n'
  printf 'samples: %d per (path, state), rotated\n' "$SAMPLES"
  exit 0
fi

[ "$VERIFY" = 1 ] && SAMPLES=1

RUN_ID=$(date -u +%Y%m%dT%H%M%SZ)
OUT="$OUT_BASE/$RUN_ID"
WORK="$SCRATCH/$RUN_ID"
mkdir -p "$OUT" "$WORK"

BASE_TAG=ctrsaccel/bench
CREATED_BUILDERS=()
CREATED_TAGS=()
FAILURES=0
SAMPLES_RUN=0
SAMPLES_VALID=0
SAMPLES_REJECTED=0
declare -a NOTES=()

cleanup() {
  if [ "$KEEP" = 0 ]; then
    local b t
    for b in ${CREATED_BUILDERS[@]+"${CREATED_BUILDERS[@]}"}; do
      "$D" buildx rm "$b" >/dev/null 2>&1 || true
    done
    for t in ${CREATED_TAGS[@]+"${CREATED_TAGS[@]}"}; do
      "$D" rmi -f "$t" >/dev/null 2>&1 || true
    done
  fi
}
trap cleanup EXIT

gate_before() {
  local label=$1
  if ! command -v perf-gate-ready >/dev/null 2>&1; then
    echo "perf-gate-ready not available; refusing to run timed groups" >&2
    exit 2
  fi
  if ! perf-gate-ready > "$WORK/gate.log" 2>&1; then
    echo "host busy before $label; deferred, never a pass:" >&2
    cat "$WORK/gate.log" >&2
    exit 75
  fi
}

gate_after() {
  local label=$1
  if ! perf-gate-ready -1 > "$WORK/gate-after.log" 2>&1; then
    echo "NOTE: $label overlapped a load spike; this group is invalidated, results below are not reportable"
    return 1
  fi
  return 0
}

command -v "$D" >/dev/null 2>&1 || { echo "docker not available" >&2; exit 2; }
command -v sha256sum >/dev/null 2>&1 || { echo "sha256sum not available" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "python3 not available" >&2; exit 2; }
if ! [ -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ]; then
  echo "no qemu-aarch64 binfmt handler: A, B and the target-platform final stages cannot execute" >&2
  exit 2
fi
load1=$(cut -d' ' -f1 /proc/loadavg)
nproc_count=$(nproc)
model=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ *//')
echo "host: $(uname -srm), $model x $nproc_count, load $load1"

echo "-- verifying fixture checksums"
for d in "${WORKLOADS[@]}"; do
  (cd "$BENCH/arm64/$d" && sha256sum -c -s SHA256SUMS) || { echo "fixture $d checksum mismatch" >&2; exit 1; }
  echo "  $d ok (golden: $(cat "$BENCH/arm64/$d/GOLDENS"))"
done

{
  echo "run $RUN_ID"
  echo "host: $(uname -s -r -m)"
  echo "cpu: $model x $nproc_count"
  echo "load1 at start: $load1"
  echo "docker: $("$D" version --format '{{.Server.Os}}/{{.Server.Arch}} {{.Server.Version}}')"
  echo "buildx: $("$D" buildx version)"
  echo "qemu-aarch64: $(tr '\n' ' ' < /proc/sys/fs/binfmt_misc/qemu-aarch64)"
  echo "samples per (path, state): $SAMPLES (rotated)"
} > "$OUT/machine.txt"

builder_image_for() { case $1 in A) echo "$PIN_A" ;; B|C) echo "$PIN_B" ;; esac; }
build_platform_for() { case $1 in A|B) echo linux/arm64 ;; C) echo linux/amd64 ;; esac; }
sample_order() {
  case $(( $1 % 3 )) in
    0) printf 'A B C\n' ;;
    1) printf 'B C A\n' ;;
    2) printf 'C A B\n' ;;
  esac
}
builder_name() { printf 'bench-%s-%s-%s' "$1" "$2" "$3" | tr '.' '-' | tr 'A-Z' 'a-z'; }

phase_peak() {
  local name=$1
  local full p
  full=$("$D" inspect -f '{{.Id}}' "buildx_buildkit_${name}0" 2>/dev/null) || { echo 0; return 0; }
  for p in "/sys/fs/cgroup/docker/buildx/$full/memory.peak" "/sys/fs/cgroup/docker/$full/memory.peak"; do
    [ -r "$p" ] && { cat "$p"; return 0; }
  done
  echo 0
}

echo "-- creating per-phase builders (fresh state)"
: > "$OUT/provisioning.tsv"
printf 'builder\tpath\tworkload\tmode\tprovision_ms\tbuildkitd\tidle_peak_bytes\n' >> "$OUT/provisioning.tsv"
declare -a ALL_BUILDERS=()
for w in "${WORKLOADS[@]}"; do
  for mode in "${STATES[@]}"; do
    for path in "${PATHS[@]}"; do
      name=$(builder_name "$path" "$w" "$mode")
      t0=$(python3 -c 'import time; print(time.time())')
      if ! "$D" buildx create --name "$name" --driver docker-container --driver-opt "image=$(builder_image_for "$path"),default-load=true" >/dev/null; then
        echo "  provisioning failed: $name (buildx create)" >&2; FAILURES=$((FAILURES + 1)); NOTES+=("provision failed: $name create"); continue
      fi
      CREATED_BUILDERS+=("$name")
      ALL_BUILDERS+=("$name")
      if ! "$D" buildx inspect --builder "$name" --bootstrap >/dev/null 2>&1; then
        echo "  provisioning failed: $name (bootstrap)" >&2; FAILURES=$((FAILURES + 1)); NOTES+=("provision failed: $name bootstrap"); continue
      fi
      t1=$(python3 -c 'import time; print(time.time())')
      bver=$("$D" exec "buildx_buildkit_${name}0" buildkitd --version 2>&1)
      provision_ms=$(python3 -c "print(f'{($t1 - $t0) * 1000:.0f}')")
      idle_peak=$(phase_peak "$name")
      printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$path" "$w" "$mode" "$provision_ms" "${bver:-unknown}" "$idle_peak" >> "$OUT/provisioning.tsv"
      echo "  $name (${provision_ms} ms, ${bver:-unknown})"
    done
  done
done

echo "-- measuring (start gate)"
gate_before "timed groups"
SAMPLES_FILE="$OUT/samples.tsv"
printf 'workload\tpath\tstate\tround\twall_s\telf_machine\timage_arch\timage_id\tgolden_ok\tphase_peak_bytes\n' > "$SAMPLES_FILE"
busy=0
for w in "${WORKLOADS[@]}"; do
  golden=$(cat "$BENCH/arm64/$w/GOLDENS")
  fixture="$BENCH/arm64/$w"
  for mode in "${STATES[@]}"; do
    for round in $(seq 1 "$SAMPLES"); do
      read -r -a rotated <<< "$(sample_order "$round")"
      for path in "${rotated[@]}"; do
        tag="${BASE_TAG}/${w}:${path}-${mode}-${round}"
        builder=$(builder_name "$path" "$w" "$mode")
        if ! perf-gate-ready > "$WORK/gate-sample.log" 2>&1; then
          printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$w" "$path" "$mode" "$round" "" "" "" "" "busy" "" >> "$SAMPLES_FILE"
          SAMPLES_RUN=$((SAMPLES_RUN + 1))
          SAMPLES_REJECTED=$((SAMPLES_REJECTED + 1))
          printf '  SKIP %s %s %s r%s: host busy, sample discarded\n' "$w" "$path" "$mode" "$round"
          NOTES+=("busy sample discarded: $w $path $mode r$round")
          busy=$((busy + 1))
          continue
        fi
        ctx="$fixture"
        if [ "$mode" = incremental ]; then
          ctx="$WORK/ctx-$w-$mode-$round"
          rm -rf "$ctx"
          cp -a "$fixture" "$ctx"
          case "$w" in
            c-cpp-workload) printf '// incremental sample %s\n' "$round" >> "$ctx/t-120.c" ;;
            rust-workload)  printf '// incremental sample %s\n' "$round" >> "$ctx/workload-app/src/main.rs" ;;
          esac
        fi
        bopts=()
        [ "$mode" = cold ] && bopts+=(--no-cache)
        t0=$(python3 -c 'import time; print(time.time())')
        "$D" buildx build --progress plain --builder "$builder" ${bopts[@]+"${bopts[@]}"} --platform linux/arm64 --build-arg "BUILD_PLATFORM=$(build_platform_for "$path")" --load -t "$tag" "$ctx" > "$WORK/build-$w-$mode-$path-$round.log" 2>&1
        rc=$?
        t1=$(python3 -c 'import time; print(time.time())')
        if ! perf-gate-ready -1 > "$WORK/gate-sample-after.log" 2>&1; then
          printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$w" "$path" "$mode" "$round" "" "" "" "" "busy-after" "" >> "$SAMPLES_FILE"
          SAMPLES_RUN=$((SAMPLES_RUN + 1))
          SAMPLES_REJECTED=$((SAMPLES_REJECTED + 1))
          printf '  DISCARD %s %s %s r%s: host busy right after the build, sample discarded\n' "$w" "$path" "$mode" "$round"
          NOTES+=("busy-after sample discarded: $w $path $mode r$round")
          busy=$((busy + 1))
          continue
        fi
        wall=$(python3 -c "print(f'{$t1 - $t0:.3f}')")
        SAMPLES_RUN=$((SAMPLES_RUN + 1))
        if [ $rc = 0 ]; then
          cid=$("$D" create --name "bench-elf-$$-$RANDOM" "$tag" 2>/dev/null)
          elf=not-checked
          case "$w" in
            c-cpp-workload) binpath=/c-workload ;;
            rust-workload)  binpath=/rust-workload ;;
          esac
          if [ -n "$cid" ] && "$D" cp "$cid:$binpath" "$WORK/elf-$w-$mode-$path-$round" >/dev/null 2>&1; then
            elf=$(od -A n -t x1 -j 18 -N 2 "$WORK/elf-$w-$mode-$path-$round" | tr -d ' \n')
          fi
          [ -n "$cid" ] && "$D" rm -f "$cid" >/dev/null 2>&1 || true
          arch=$("$D" image inspect -f '{{.Os}}/{{.Architecture}}' "$tag" 2>/dev/null)
          imgid=$("$D" image inspect -f '{{.Id}}' "$tag" 2>/dev/null)
          out=$("$D" run --rm --platform linux/arm64 "$tag" 2>&1)
          golden_ok=no
          if [ "$out" = "$golden" ]; then golden_ok=yes
          elif [ "$arch" != "linux/arm64" ]; then golden_ok=arch-mismatch; fi
        else
          elf=not-built arch=build-failed imgid=unavailable golden_ok=build-failed
        fi
        peak=$(phase_peak "$builder")
        printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
          "$w" "$path" "$mode" "$round" "$wall" "$elf" "${arch:-unknown}" "${imgid:-unknown}" "$golden_ok" "$peak" >> "$SAMPLES_FILE"
        CREATED_TAGS+=("$tag")
        if [ $rc = 0 ] && [ "$golden_ok" = yes ] && [ "$elf" = b700 ]; then
          SAMPLES_VALID=$((SAMPLES_VALID + 1))
          printf '  %s %s %s r%s: wall %ss, golden ok, elf b700, peak %s\n' "$w" "$path" "$mode" "$round" "$wall" "$peak"
        else
          SAMPLES_REJECTED=$((SAMPLES_REJECTED + 1))
          printf '  REJECTED %s %s %s r%s (rc=%s golden=%s elf=%s; log %s)\n' "$w" "$path" "$mode" "$round" "$rc" "$golden_ok" "$elf" "$WORK/build-$w-$mode-$path-$round.log"
          NOTES+=("rejected sample: $w $path $mode r$round (rc=$rc golden=$golden_ok elf=$elf)")
        fi
      done
    done
  done
done
gate_after "timed groups" || { echo "timed groups ran but the trailing gate tripped; samples overlapping foreign load were already discarded per sample" >&2; }

printf 'compiler-cache state: unavailable (no compiler cache configured in this qualification; never counted as a hit)\n' >> "$OUT/provisioning.tsv"

python3 - "$SAMPLES_FILE" "$OUT" "$SAMPLES" <<'PYEOF'
import sys, statistics, collections
samples_file, out_dir, want = sys.argv[1], sys.argv[2], int(sys.argv[3])
rows = []
with open(samples_file) as f:
    next(f)
    for line in f:
        parts = line.rstrip('\n').split('\t')
        if len(parts) == 10:
            rows.append(parts)
by = collections.defaultdict(list)
for w, path, state, rnd, wall, elf, arch, imgid, golden, peak in rows:
    if golden == 'yes' and elf == 'b700':
        by[(w, path, state)].append(float(wall))
total_valid = sum(len(v) for v in by.values())
lines = ['# benchmark summary\n\n',
         f'samples recorded: {len(rows)}; valid (golden + elf b700): {total_valid}; rejected: {len(rows) - total_valid}\n\n',
         '| workload | path | state | n | median s | min s | max s |\n|---|---|---|---|---|---|---|\n']
for (w, path, state), vals in sorted(by.items()):
    lines.append(f'| {w} | {path} | {state} | {len(vals)} | {statistics.median(vals):.3f} | {min(vals):.3f} | {max(vals):.3f} |\n')
insufficient = [(w, p, s, len(v)) for (w, p, s), v in by.items() if len(v) < want]
all_cells = [(w, p, s) for w in ['rust-workload', 'c-cpp-workload'] for p in ['A', 'B', 'C'] for s in ['cold', 'incremental', 'layer-hit']]
missing = [cell for cell in all_cells if cell not in by]
bad = sorted(insufficient) + sorted(missing)
if bad:
    lines.append('\nINSUFFICIENT valid samples per (workload, path, state): want at least %d\n' % want)
    for w, p, s, n in insufficient:
        lines.append(f'- {w} {p} {s}: {n}/{want} valid\n')
    for w, p, s in missing:
        lines.append(f'- {w} {p} {s}: 0/{want} valid\n')
lines.append('\ncompiler-cache state: unavailable (no compiler cache configured; never counted as a hit)\n')
with open(f'{out_dir}/summary.md', 'w') as f:
    f.write(''.join(lines))
print(''.join(lines))
PYEOF

{
  echo
  echo "samples recorded: $SAMPLES_RUN (valid $SAMPLES_VALID, rejected $SAMPLES_REJECTED)"
  echo "failures: $FAILURES"
  for n in ${NOTES[@]+"${NOTES[@]}"}; do echo "note: $n"; done
  echo "machine: $(cat "$OUT/machine.txt" | head -5 | tr '\n' ' ')"
} >> "$OUT/summary.md"

echo "== $RUN_ID"
cat "$OUT/summary.md"

if grep -q '^INSUFFICIENT' "$OUT/summary.md"; then
  echo "bench: insufficient valid samples per (workload, path, state) — the host was too busy; rerun on a quieter host" >&2
  FAILURES=$((FAILURES + 1))
fi

if [ "$VERIFY" = 1 ]; then
  echo "-- verify: accounting and report"
  expected=$(( ${#WORKLOADS[@]} * ${#STATES[@]} * ${#PATHS[@]} * SAMPLES ))
  [ "$SAMPLES_RUN" = "$expected" ] && echo "  sample accounting ok ($SAMPLES_RUN)" || { echo "  sample accounting off: want $expected, ran $SAMPLES_RUN"; FAILURES=$((FAILURES + 1)); }
  for mode in cold layer-hit incremental; do
    grep -q $'\t'"$mode"$'\t' "$SAMPLES_FILE" && echo "  state $mode present" || { echo "  state $mode missing"; FAILURES=$((FAILURES + 1)); }
  done
  if awk -F'\t' 'NR>1 && $10 != "0" { found=1 } END { exit !found }' "$SAMPLES_FILE"; then
    echo "  process-tree memory collection present"
  else
    echo "  process-tree memory collection missing"; FAILURES=$((FAILURES + 1))
  fi
  cold_line=$(awk -F'\t' '$3 == "cold" && $9 == "yes" {print NR": "$5}' "$SAMPLES_FILE" | head -1)
  layer_line=$(awk -F'\t' '$3 == "layer-hit" && $9 == "yes" {print NR": "$5}' "$SAMPLES_FILE" | head -1)
  [ -n "$cold_line" ] && [ -n "$layer_line" ] && echo "  cache-mode distinctions observable (cold ${cold_line##*: }s vs layer-hit ${layer_line##*: }s wall)" || { echo "  cache modes not observable"; FAILURES=$((FAILURES + 1)); }
  [ -s "$OUT/summary.md" ] && echo "  report generated at $OUT/summary.md" || { echo "  report missing"; FAILURES=$((FAILURES + 1)); }
  [ -e "$OUT/machine.txt" ] && echo "  machine metadata recorded" || { echo "  machine metadata missing"; FAILURES=$((FAILURES + 1)); }
fi

if [ "$FAILURES" != 0 ]; then
  echo "bench: $FAILURES failure(s); report preserved in $OUT" >&2
  exit 1
fi
echo "bench: all checks passed ($SAMPLES_RUN samples; report $OUT)"
