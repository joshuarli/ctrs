# Installing ctrs

ctrs is not distributed as an installer; there is no pkg, no Homebrew tap,
no systemd package, and no launchd service by default. You build or copy a
single binary and run it. Everything ctrs writes lives in one private data
root.

## macOS (Apple Silicon)

Build from source:

```sh
cargo xtask host    # target/release/ctrs, ad-hoc signed with com.apple.security.virtualization
```

or use a locally built `.work/release/ctrs-aarch64-apple-darwin` artifact
from this repository (local builds only — there is no public download yet;
see `docs/evidence/release.md` for its sha256 and entitlements).

Then:

```sh
mkdir -p ~/.local/bin
cp target/release/ctrs ~/.local/bin/ctrs   # or any directory on PATH
ctrs daemon &                              # or: ctrs engine start
DOCKER_HOST=unix://$HOME/.local/share/ctrs/run/docker.sock docker run --rm alpine echo hello
```

Requirements and notes:

- The binary must be signed with the `com.apple.security.virtualization`
  entitlement — the guest VM will not start without it. `cargo xtask host`
  does this for you (ad-hoc signature). If you re-sign with your own
  identity, keep the entitlement or the engine is useless.
- The guest kernel and initramfs are required assets: build them with
  `cargo xtask kernel`, `cargo xtask guest` (see `docs/development.md`).
  They land in `guest/out/` (gitignored).
- Intel Macs: cross-build with `--arch x86_64` (`cargo xtask host --arch
  x86_64`, kernel via `cargo xtask kernel --arch x86_64`); x86-64 is
  smoke-tested only on Intel hardware and is not qualified (N-3).
- Rosetta support (running amd64 containers) is shared into the guest
  automatically when Rosetta is installed.
- The engine never creates a docker context. `DOCKER_HOST=unix://…` (or
  `ctrs run …`, which sets it) is the whole integration.
- To run at login, see `docs/launchd.md` for an optional user agent
  (not a LaunchDaemon; ctrs does not need root).

## Linux

No systemd requirement. The static binaries are built in a container:

```sh
cargo xtask linux            # host arch (arm64 on Apple Silicon): target/linux/release/{ctrs,ctrs-init}
cargo xtask linux --arch amd64
cargo xtask linux --arch arm64   # cross-compiled on the build platform (Linux hosts)
```

or use the locally prepared x86_64/aarch64 Linux artifacts recorded in
`docs/evidence/release.md` (local builds only — there is no public download
yet; see its sha256s). The binaries need a host with:

- a kernel with clone3, cgroup v2, overlayfs, and nf_tables/rtnetlink
  (roughly 5.3+; the agent hand-encodes its netlink/nftables messages —
  no external `nft`/`ip` helpers needed);
- root, or a delegated cgroup v2 subtree plus `CAP_SYS_ADMIN`-class
  capabilities — the agent runs as root on the host kernel and owns the
  container namespaces; nothing sandboxed is supported;
- `iptables`/`nftables`-class networking handled by the agent's own
  netlink code — no external nft/`ip` helpers are needed;
- musl static binaries: copy `ctrs` and `ctrs-init` onto the host; no
  package installation at runtime.

Run it foreground as root:

```sh
sudo ./ctrs daemon
DOCKER_HOST=unix:///root/.local/share/ctrs/run/docker.sock docker run --rm alpine echo hello
```

When the engine runs as root its data root resolves against root's home
(`/root/.local/share/ctrs`); set `CTRS_DATA_DIR`/`CTRS_SOCKET` explicitly
to keep the state where you want it.

The native Linux path is not yet runtime-qualified (N-1); treat it as a
compile-tested preview. macOS is the qualified platform.

## Uninstall

There is nothing to revert: ctrs installs no system files, no services, no
docker contexts, and no shell configuration. To remove it:

1. Stop the engine: `ctrs engine stop` (or `kill` the daemon; the VM exits
   with it).
2. Remove the binary: `rm ~/.local/bin/ctrs` (or wherever you put it).
3. **Destroy the private state** — this deletes every pulled image,
   container record and the VM disk; back up anything you want first:
   - default install: `rm -rf ~/.local/share/ctrs`
   - with `CTRS_DATA_DIR` set: also `rm -rf "$CTRS_DATA_DIR"` (image store,
      VM data, data-root `.lock`)
   - with `CTRS_STATE_DIR` set: also remove that directory (vm.json, logs)
   - the daemon's own state directory is always `$HOME/.local/share/ctrs`
     (e.g. `builder.json`) even when the other two are redirected — remove
     it too; uninstalling with only a custom `CTRS_DATA_DIR` leaves it behind
4. If you installed the optional launchd example, remove it:
   `launchctl bootout gui/$UID ~/Library/LaunchAgents/<file>.plist` and
   `rm ~/Library/LaunchAgents/<file>.plist`.
5. If you built guest assets in the repo, `guest/out/` is disposable
   (`git clean`); `.work/` is scratch.

Nothing else exists to clean up: no `/etc/resolver` entries, no
`/var/run/docker.sock`, no group memberships (unlike the
`docker`-group model).

The uninstall steps were verified on a scratch install: a throwaway
`CTRS_DATA_DIR` with a container run, the binary, the data root and the
state directory under the scratch `HOME` removed — the scratch tree was
left with no private state, and the real `~/.local/share/ctrs` was
untouched (and did not exist before the check).
