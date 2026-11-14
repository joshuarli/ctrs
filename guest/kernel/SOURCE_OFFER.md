# Guest kernel source offer

The ctrs guest kernel is Linux under GPL-2.0-only. The complete corresponding
source is the upstream Linux release below plus the patches and configuration
in this repository (`guest/kernel/`), which together with the build script
rebuild the shipped kernel exactly.

The exact upstream tarball is:

`https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-<version>.tar.xz`

where `<version>` is the `KVER` pinned in `guest/kernel/build.sh`. The archive
with the ctrs patches already applied is reproducible from this checkout with:

```sh
scripts/ci/kernel-source.sh target/ctrs-VERSION-kernel-source.tar.xz
```

This offer is valid for three years from the date of each release. The guest
kernel is a separate work from the Apache-2.0 ctrs application.
