# Check persistent disk mount failure and volume survival

Run this check on native ARM64 macOS. It creates disposable ctrs roots under
`.work/tmp/`, clones the baseline template with APFS clone-only copy, and leaves
proof artifacts there. It does not restart OrbStack or modify existing ctrs data.

Build the static proof program through an explicit engine endpoint:

```sh
mkdir -p "$PWD/.work/tmp/disk-proof"
env -u DOCKER_CONTEXT docker --host "unix://$HOME/.orbstack/run/docker.sock" run --rm \
  --platform linux/arm64 --network none --label dev.ctrs.campaign.fixture=disk-proof \
  -v "$PWD/bench/native/diagnostics:/src:ro" \
  -v "$PWD/.work/tmp/disk-proof:/out" \
  gcc@sha256:c5be79575f0886a3f8bdcf7cacc7de808ed56089975d43f54fda739a1d183d6c \
  gcc -O2 -static -std=c11 -Wall -Wextra -Werror -o /out/proof /src/volume_proof.c
```

Build the candidate guest in an isolated worktree. Supply its kernel,
initramfs and template directory, and a preserved baseline directory:

```sh
TMPDIR="$PWD/.work/tmp" python3.14 bench/native/diagnostics/disk_mount_pilot.py \
  --candidate-guest-dir <candidate-directory> \
  --baseline-guest-dir <baseline-directory> \
  --proof-binary .work/tmp/disk-proof/proof
```

The command must exit zero and print `PASS` with its artifact directory.
The invalid-disk leg requires rejection before a successful volume write and
verifies the entire invalid disk remains unchanged. The valid-disk leg writes
and fsyncs exact bytes, then reads them after a baseline-to-candidate guest
upgrade and a candidate restart. The named-volume metadata must remain equal.
The image layers differ by a disposable generation marker, so image-cache
rehydration cannot stand in for volume persistence.

Read the saved stdout, stderr, exit status, volume metadata and actual running
engine/boot identity for each leg. Keep failed artifacts. Remove only roots
whose `owner.json` identifies this check after the engine has stopped.

A passing run demonstrates these mount and normal restart paths. It does not
exercise host power loss, disk expansion, full-disk recovery or every historical
on-disk format. It is not a storage or performance comparison.
