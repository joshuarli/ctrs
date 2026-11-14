#!/bin/sh
set -eu
echo "child: entered"
echo "child-interp-e_machine: $(od -A n -t x1 -j 18 -N 2 /proc/self/exe 2>/dev/null | tr -d ' \n')"
echo "computed: $(printf 'ctrs-arm64-qualification\n' | sha256sum | cut -d' ' -f1)"
echo "child: done"
