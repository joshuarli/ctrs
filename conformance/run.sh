#!/bin/bash
# Docker Engine API conformance runner.
#
# Fixtures live in conformance/fixtures/<name>.sh. Each fixture:
#   - runs against the engine at $DOCKER_HOST (unix:// path)
#   - prints a line "ok" and exits 0 on success, or prints a reason and exits non-zero
# With zero fixtures this prints the current plan and exits 0.
#
# Usage:
#   DOCKER_HOST=unix:///path/to.sock conformance/run.sh [fixture-substring]
set -u
cd "$(dirname "$0")/.."
FIXTURES=conformance/fixtures
FILTER=${1:-}
PASS=0; FAIL=0; RAN=0
shopt -s nullglob
for f in "$FIXTURES"/*.sh; do
  name=$(basename "$f" .sh)
  [ -n "$FILTER" ] && [[ "$name" != *"$FILTER"* ]] && continue
  RAN=$((RAN + 1))
  if out=$("$f" 2>&1); then
    out=$(printf '%s' "$out" | tail -1)
    if [ "$out" = "ok" ]; then PASS=$((PASS + 1)); else printf 'PASS %s (%s)\n' "$name" "$out"; PASS=$((PASS + 1)); fi
  else
    FAIL=$((FAIL + 1)); printf 'FAIL %s\n  %s\n' "$name" "$(printf '%s' "$out" | tail -3)"
  fi
done
if [ "$RAN" -eq 0 ]; then
  printf 'conformance: 0 fixtures under %s\n' "$FIXTURES"
  printf 'plan: fixtures are added by CTRS-05 (harness), CTRS-08 (e2e adaptation),\n'
  printf 'CTRS-11 (firewall netns), CTRS-14 (HTTP/1.1 interoperability), CTRS-16 (OCI),\n'
  printf 'CTRS-21 (failure injection). Runner contract: see fixture headers.\n'
  exit 0
fi
printf 'conformance: %d run, %d pass, %d fail\n' "$RAN" "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
