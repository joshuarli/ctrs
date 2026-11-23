#!/bin/bash
# Compatibility regression for highly compressible layers. A zstd default for
# loaded images was rejected because a valid 2 GiB layer compressed so well
# that the guest's unchanged expansion cap (256x compressed, at least 1 GiB)
# refused it on first use. The original fixture artifacts were deleted; this
# is a deterministic equivalent of their documented construction: one 64 KiB
# high-entropy block repeated 32,768 times as a single file.
#
# Checks, against a scratch engine:
#   1. classic POST /build, then first use returns the exact payload SHA-256;
#   2. the default buildx --load (docker-container driver on the engine) does
#      the same;
#   3. an explicit compression=zstd load is refused, at load or at first use
#      and then again (nothing partial is reused), and leaves no staged or
#      half-unpacked layer in CTRS_LAYER_ROOT when that is set (Linux host);
#   4. the default image still runs after the refusal.
#
#   CTRS_SOCKET=... tests/layer-expansion.sh
#   CTRS_SOCKET=... CTRS_LAYER_ROOT=<data>/layers tests/layer-expansion.sh
#
# Needs about 12 GiB free on the engine's disk: builder snapshot, exported
# blob, image store and unpacked layer of the 2 GiB payload.
set -u
SOCK=${CTRS_SOCKET:?set CTRS_SOCKET to the scratch engine socket}
export DOCKER_HOST="unix://$SOCK"
unset DOCKER_CONTEXT DOCKER_DEFAULT_PLATFORM
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export TMPDIR=${TMPDIR:-$REPO/.work/tmp}
mkdir -p "$TMPDIR"
WORK=$(mktemp -d "$TMPDIR/layer-expansion.XXXXXX")
RUN=$$
CLASSIC=ctrs-test/expansion-classic:$RUN
BUILDX=ctrs-test/expansion-buildx:$RUN
ZSTD=ctrs-test/expansion-zstd:$RUN
BX=ctrs-expansion-$RUN
FAIL=0
cleanup() {
  docker rmi -f "$CLASSIC" "$BUILDX" "$ZSTD" >/dev/null 2>&1
  docker buildx rm -f "$BX" >/dev/null 2>&1
  rm -rf "$WORK"
}
trap cleanup EXIT
pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s: %s\n' "$1" "$2"; FAIL=$((FAIL + 1)); }
skip() { printf '  skip %s: %s\n' "$1" "$2"; }

FREE_KIB=$(docker run --rm alpine:3.22 df -Pk / | awk 'NR == 2 { print $4 }')
if [ -z "$FREE_KIB" ] || [ "$FREE_KIB" -lt $((12 * 1024 * 1024)) ]; then
  echo "FAIL: the engine disk needs 12 GiB free (has ${FREE_KIB:-unknown} KiB)"
  exit 1
fi

mkdir -p "$WORK/ctx"
WANT=$(python3 - "$WORK/ctx/block" <<'GEN'
import hashlib, sys
x, mask, block = 0x9E3779B97F4A7C15, (1 << 64) - 1, bytearray()
for _ in range(65536):
    x ^= (x << 13) & mask
    x ^= x >> 7
    x ^= (x << 17) & mask
    block.append(x & 0xFF)
open(sys.argv[1], "wb").write(block)
digest = hashlib.sha256()
for _ in range(32768):
    digest.update(block)
print(digest.hexdigest())
GEN
) || { echo "FAIL: fixture generation"; exit 1; }
cat > "$WORK/ctx/Dockerfile" <<'DOCKERFILE'
FROM alpine:3.22
COPY block /block
RUN cp /block /payload && for i in $(seq 15); do cat /payload /payload > /next && mv /next /payload; done && rm /block
DOCKERFILE
echo "payload sha256 $WANT"

payload_sum() { docker run --rm "$1" sha256sum /payload 2>&1 | cut -c1-64; }

tar -C "$WORK/ctx" -cf "$WORK/ctx.tar" .
curl -sS --unix-socket "$SOCK" -X POST -H 'Content-Type: application/x-tar' \
  --data-binary "@$WORK/ctx.tar" "http://x/build?t=$CLASSIC" > "$WORK/classic.log"
if grep -q '"error' "$WORK/classic.log" || ! docker image inspect "$CLASSIC" >/dev/null 2>&1; then
  fail classic-build "$(tail -c 400 "$WORK/classic.log")"
elif [ "$(payload_sum "$CLASSIC")" = "$WANT" ]; then pass classic-build-first-use
else fail classic-build-first-use "payload sha256 differs"; fi

docker buildx create --name "$BX" --driver docker-container --driver-opt default-load=true "unix://$SOCK" >/dev/null
if ! BUILDX_BUILDER=$BX docker build -t "$BUILDX" "$WORK/ctx" > "$WORK/buildx.log" 2>&1; then
  fail buildx-load "$(tail -5 "$WORK/buildx.log")"
elif [ "$(payload_sum "$BUILDX")" = "$WANT" ]; then pass buildx-load-first-use
else fail buildx-load-first-use "payload sha256 differs"; fi

leftovers() { find "$CTRS_LAYER_ROOT" -maxdepth 1 \( -name '.tmp-*' -o -name '.blob-*' \) | head -3; }
if ! docker buildx build --builder "$BX" \
    --output "type=docker,name=$ZSTD,compression=zstd,force-compression=true" "$WORK/ctx" > "$WORK/zstd.log" 2>&1; then
  if grep -q 'allowed size' "$WORK/zstd.log"; then pass zstd-load-refused
  else fail zstd-load "$(tail -5 "$WORK/zstd.log")"; fi
else
  FIRST=$(docker run --rm "$ZSTD" true 2>&1); FIRST_STATUS=$?
  docker run --rm "$ZSTD" true >/dev/null 2>&1; SECOND_STATUS=$?
  if [ "$FIRST_STATUS" -ne 0 ] && [ "$SECOND_STATUS" -ne 0 ]; then pass zstd-first-use-refused-twice
  else fail zstd-first-use-refused-twice "exits $FIRST_STATUS/$SECOND_STATUS: $FIRST"; fi
  printf '    refusal: %s\n' "$(printf '%s' "$FIRST" | tail -1)"
  if [ -z "${CTRS_LAYER_ROOT:-}" ]; then skip zstd-refusal-cleanup "CTRS_LAYER_ROOT unset"
  elif [ -z "$(leftovers)" ]; then pass zstd-refusal-cleanup
  else fail zstd-refusal-cleanup "$(leftovers)"; fi
fi

if [ "$(payload_sum "$BUILDX")" = "$WANT" ]; then pass default-image-after-refusal
else fail default-image-after-refusal "payload sha256 differs"; fi

echo "failures: $FAIL"
[ "$FAIL" -eq 0 ]
