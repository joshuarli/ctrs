#!/bin/sh
set -eu
echo "build-id: entered"
echo "emulator-mount: $(test -e /dev/.buildkit_qemu_emulator && echo yes || echo no)"
echo "interp-e_machine: $(od -A n -t x1 -j 18 -N 2 /proc/self/exe 2>/dev/null | tr -d ' \n')"
/work/child.sh
echo "build-id: done"
echo "uname-supplementary: $(uname -m)"
