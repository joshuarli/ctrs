# Integrated Linux runtime result — 2026-11-22

Native Linux amd64 only. This completes the checkpoint/runtime slices of
the Linux steering, not performance optimization or qualification. The
macOS/OrbStack campaign remains paused; all its gates remain open and
separate. No W2 optimization, HTTPie investigation or W13 rewrite was run.

## Identity and durable evidence

Current-main source/build: **`65b7bbd6ed5ca7bc803145e13983011eebe8321b`**,
including Linux forwarding coexistence and the Linux-aware e2e harness.
There were no product or harness edits in this runtime slice. One
coordinator serialized all builds, suites and restoration on this host.
Before landing, the documentation was rebased onto main
`123f29cadd0f4afcd3a85b3f6c307cc1255de66e`. Incoming changes were macOS
benchmark preflight/reporting/tests and documentation, not Rust runtime,
the Linux preparation implementation or `tests/e2e.sh`; the tested Linux
runtime remains the same. `rebase-changed-paths.txt` records that audit.

| Item | Identity |
| --- | --- |
| Host | Ubuntu 22.04.5 LTS, x86_64, 8 CPUs, 33,655,406,592 bytes RAM |
| Kernel / cgroups | `6.8.0-1060-aws`; cgroup v2, systemd driver |
| Docker Engine | 29.9.2, commit `0367cbe`, API 1.56, overlayfs |
| containerd | 2.4.2, `b7a25261e029d68978bbf290df0a62fc819b3c51` |
| runc / docker-init | 1.5.2 (`v1.5.2-0-g29dd3dc2`) / 0.19.0 (`de40ad0`) |
| ctrs binary SHA-256 | `e9a8dc2ce6b87e28cd736ff078e60a91d3f791097f3a0620647933f3f1160bd2` |
| ctrs-init SHA-256 | `9acfbfcab8f0bc08ed13d0e0f33cb57fe2d496a97ad6e88ffe98cd09181a9420` |

Historical checkpoint artifacts and the
[baseline manifest](linux-amd64-v1.sha256) remain unchanged. The
[checkpoint document](linux-amd64-checkpoint-2026-11-22.md) links this follow-up.
Fixture archive,
raw trials, traces, analysis, commands, binaries and source history remain
under `/home/ubuntu/ctrs-evidence/linux-amd64-v1/`, outside `.work/`.

This runtime slice is preserved at
**`/home/ubuntu/ctrs-evidence/linux-integrated-20261122/`**, covered by the
committed [runtime SHA-256 manifest](linux-integrated-2026-11-22.sha256).
It includes both current binaries, a current-source Git bundle, the exact
suite, all final and superseded logs, scripts, namespace/socket receipts,
and `README-commands.md` with full startup, execution and cleanup commands.
Copy that directory off the VM for independent retention; this is not a
public artifact URL. Verify after retrieval:

```sh
cd /path/to/retrieved/linux-integrated-20261122
sha256sum -c /path/to/checkout/docs/evidence/linux-integrated-2026-11-22.sha256
```

## Host bridge incident and repair

The earlier secondary restore daemon shared host containerd, and host
`docker0` disappeared. The deleting operation was not traced. Its cause
remains **unconfirmed**, not attributed conclusively to either engine.
With approval, repair was in place:

```sh
sudo -n ip link add name docker0 type bridge
sudo -n ip address add 172.17.0.1/16 dev docker0
sudo -n ip link set docker0 up
```

`docker run --rm alpine true` and a published nginx port both worked.
No restart was necessary. The current-main build then succeeded:

```sh
CARGO_ENCODED_RUSTFLAGS="" cargo xtask linux --arch amd64
```

`build.log` preserves the pre-repair failure; `build-after-repair.log`
preserves the successful build. Final post-cleanup verification in
`host-final.log` also records:

```text
HOST_ALPINE_TRUE_OK
HOST_PUBLISHED_PORT_OK
MainPID=599
ActiveState=active
ActiveEnterTimestamp=Sat 2026-11-21 05:39:22 UTC
docker0          UP             172.17.0.1/16 fe80::d054:5bff:fe40:3c8d/64
```

The published container was removed by a trap. Host dockerd and containerd
were never stopped, restarted or reconfigured. Host containerd remained
PID 487, with the same original active timestamp.

## Disposable ownership and commands

The suite uses fixed names, snapshot-difference cleanup and generic prune
labels. It was **not** run against the host Docker daemon.

- Ctrs used the committed `bench/native/linux/ctrs-engine.sh` launcher,
  a delegated systemd unit, private mount namespace and `/var/lib`, and
  dedicated data/state/socket/client/home directories under `.work/c`.
  PID 531762 was under
  `/system.slice/ctrs-bench-8a5b084aaec1.service/ctrs-host`; container
  cgroups were within the same unit. The unit was stopped after the
  suite and active firewall proof.
- Final Docker used netns `ctrs-e2e-d`, a unique **`e2e-d0`** bridge inside
  that namespace, private data/exec roots and socket, and its **own
  containerd** (`--address .work/d/c.sock`, separate `--root`/`--state`),
  explicitly passed via `--containerd`. Containerd namespaces were
  `ctrs-e2e-moby` and `ctrs-e2e-plugins`, not host `moby`.
- Final private containerd PID **579537** and dockerd PID **579606** shared
  `net:[4026532407]`, `mnt:[4026532264]`; host PIDs 487/599 used
  `net:[4026531840]`, `mnt:[4026531841]`. Private runtime bind mounts hid
  host `/run/containerd` and `/run/docker`; the host default containerd
  socket was absent inside them. CRI/NRI were disabled; final listeners
  were private paths, with distinct socket inodes from host endpoints.
- Temporary, comment-tagged host egress/NAT rules admitted only the
  owned `e2ed-h` namespace uplink, independently of ctrs exceptions.
  They were removed afterward. No shared-daemon global prune was run.

Startup preflights exposed conflicting bridge flags, a private-netns stub
resolver failure, residual `appnet`, and an unused NRI default-path
listener. These were setup limitations, not product results. The NRI
socket/directory were created during our preflight, stopped and removed;
the final configuration disabled it and isolated runtime mounts. The
complete final Docker suite was rerun afterward. All superseded logs and
the socket birth/ownership receipt are retained, not silently replaced.
Unused CRI dependent-plugin warnings in the final containerd journal are
from the deliberately disabled runtime plugin, not Docker failures.

Key execution commands from the worktree (full environment and startup
arguments are in archived `README-commands.md` and scripts):

```sh
R=$PWD
bench/native/linux/ctrs-engine.sh start "$R/target/linux-x86_64/release/ctrs" "$R/.work/c"
sudo -n bash .work/run-e2e-ctrs.sh
sudo -n bash .work/firewall-active.sh
bench/native/linux/ctrs-engine.sh stop "$R/target/linux-x86_64/release/ctrs" "$R/.work/c"
sudo -n unshare --mount --propagation private sh .work/in-docker-ns.sh env \
  PATH="$HOME/.local/share/ctrs-dev/bin:$HOME/.cargo/bin:$PATH" \
  HOME="$R/.work/home-d" DOCKER_CONFIG="$R/.work/client-d" TMPDIR="$R/.work/tmp" \
  CTRS_SOCKET="$R/.work/d/docker.sock" CTRS_BINARY="$R/target/linux-x86_64/release/ctrs" \
  CTRS_BUILDER=ctrs-integrated-docker bash tests/e2e.sh
```

## Current-main e2e results

| Engine | Passed | Failed | Skipped | Exact failures | Full log |
| --- | ---: | ---: | ---: | --- | --- |
| ctrs | **482** | **1** | **26** | `kernel-link-vrf` | `e2e-ctrs.log` |
| isolated dockerd | **471** | **2** | **30** | `kernel-link-vrf`, `cap-add-sys-admin` | `e2e-dockerd.log` |

Both suite exit codes are **1**, not unqualified green results. Totals
differ because of engine-specific assertions/skips, including CLI
dispatch. Applicable native image, lifecycle, network, terminal, copy,
build, security and kernel cases ran; excluded VM/macOS behavior is not
qualified by Linux success.

The supplied earlier post-fix result (482/1/26 and 470/3/30, including
Docker copy ownership) was not recorded as an integrated result on main.
This independent current-main rerun reproduces the ctrs row. The final
Docker row has one more pass: `cp-in-root-owner` is source-UID-dependent,
as below. Our initial complete Docker run was 470/3/30 because `appnet`
remained from the aborted DNS setup, not because of copy ownership. It is
preserved as `e2e-dockerd-initial-owned-network-leftover.log`; after owned
network cleanup, both later complete runs produced 471/2/30.

### Exact remaining failures and counterfactuals

| Case | Classification and evidence |
| --- | --- |
| `kernel-link-vrf`, both | **Host-unsupported kernel feature.** `Error: Unknown device type.` Host config has `CONFIG_NET_VRF=m`; `modinfo vrf` returns `Module vrf not found`. A direct host `ip link add ... type vrf` in an owned netns also fails, outside either engine/AppArmor. No ctrs defect isolated. |
| Docker `cap-add-sys-admin` | **Environment/security-profile limitation.** Default `docker-default (enforce)` gives `mount: mounting t on /mnt failed: Permission denied` (255). Otherwise identical `--cap-add SYS_ADMIN --security-opt apparmor=unconfined` prints `unconfined`, `mounted`, exit 0. Ctrs passes its normal capability test. |
| Earlier Docker `cp-in-root-owner` | **Docker behavioral difference plus source-UID/harness dependence.** Suite source files are UID 0 in this root-owned isolated test HOME, so Docker preserves 0:0 and passes. A separately created source explicitly verified as 1000:1000 copies as **1000:1000 on Docker**, **0:0 on ctrs**. The earlier expected root-owner assertion therefore fails with a nonroot-owned source, not a new ctrs defect. |
| Our initial Docker `network-create` | **Setup residue.** `network with name appnet already exists` after an aborted private DNS run. Removing only disposable state resolves it in the two subsequent complete suites. |

`classification.log` preserves the copy-owner, AppArmor and host-netns VRF
counterfactuals. No concrete ctrs product failure remained after excluding
the unsupported host VRF. No Docker-only behavior was changed in ctrs.

### Explicit skips

The 26 ctrs skips are: `start-restores-layer`;
`dns-default-bridge-gateway`, `dns-default-bridge-no-loopback`,
`dns-via-host-addr`; `host-internal-hostnet`, `host-internal-upload-eof`,
`host-internal-peer`; `build-resolvconf`, `build-no-public-resolver`; and
these 17 macOS bind-notification cases:
`bind-inotify-save`, `bind-inotify-save-rename`, `bind-inotify-replace`,
`bind-inotify-create`, `bind-inotify-rename`, `bind-inotify-delete`,
`bind-inotify-replace-self`, `bind-inotify-delete-self`,
`bind-inotify-content`, `bind-inotify-no-echo`, `bind-negative-create`,
`bind-made-here-mac-create`, `bind-mixed-writer`, `bind-root-churn`,
`bind-burst`, `bind-rescan-keeps-mounts`, `bind-root-renamed`.
These require the macOS VM disk/DNS/loopback/BuildKit relays or synthetic
bind-event forwarding. They are not Linux product failures or Linux
implementations of those Mac features.

Docker additionally skips `host-internal` (does not synthesize the alias),
`vsock-unconfined`, `vsock-privileged` (ctrs-specific vsock boundary), and
the aggregate `ctrs CLI dispatch` check. All skip reasons are printed in
the preserved logs; no supported failing check was relabeled as a skip.

### Every earlier named ctrs failure

The immutable historical summary is **380/73/0**. Its raw log contains
**74 distinct printed FAIL labels**, not 73; that historical discrepancy
was not rewritten or diagnosed. `reconcile.py` and `reconciliation.json`
name and map all 74 against the corrected suite and current full log:

- **61 present and no longer failing/skipped:** `image-inspect-arch`;
  `tty-is-pty`, `tty-term`, `tty-shell`, `tty-exit-code`, `exec-tty`;
  `default-ip`, `default-route`, `internet-http`, `internet-dns`,
  `internet-https`, `first-download-x8`, `download-while-others-start`,
  `host-net`, `host-internal`, `host-gateway`, `compose-dns`;
  `build`, `build-runs`, `build-arg`, `build-cached`, `build-network`,
  `build-dns`, `build-fails`, `build-ep-cmd`, `create-empty-cmd`;
  `rosetta-binary`, `native-again` (native amd64 here, not emulation);
  `unpriv-port-start`, `unpriv-ping-range`, `unpriv-listen-80`,
  `unpriv-sysctl-wins`, `unpriv-port-host-net`; `seccomp-on`,
  `seccomp-userns`, `seccomp-keyctl`, `seccomp-unconfined`,
  `seccomp-privileged-boundary`, `seccomp-exec`, `seccomp-fork`;
  `stdin-200mb`, `stdin-slow-reader`; `cap-default`, `cap-drop-all`,
  `cap-drop-net-raw-ping`, `cap-drop-net-raw`, `cap-add-net-admin`,
  `cap-add-sys-admin`; `read-only`, `read-only-tmpfs`, `read-only-volume`,
  `shm-size`, `shm-default`, `no-new-privs`; `udp-dns`,
  `udp-dns-tcp-same-port`, `udp-many`; `stop-signal`,
  `stop-signal-inspect`, `dispatch-engine-alive`, `dispatch-restart-container`.
- **12 not applicable, now explicit macOS/VM skips:**
  `start-restores-layer`, `dns-default-bridge-gateway`, `dns-via-host-addr`,
  `host-internal-hostnet`, `host-internal-upload-eof`, `host-internal-peer`,
  `bind-inotify-save-rename`, `bind-inotify-replace`, `bind-inotify-rename`,
  `bind-rescan-keeps-mounts`, `build-resolvconf`, `build-no-public-resolver`.
- **`kernel-setup`:** the old package/bootstrap prerequisite failure is
  gone; native kernel probes now execute, with only VRF unsupported.

The working setup includes native architecture/terminal expectations,
working forwarding/DNS/egress and Linux-aware harness semantics. The old
logs do not independently establish the root cause of every cascading
failure; passing the current assertion is not evidence that forwarding
alone caused or fixed all 61. The prior failure classes are reconciled,
not retroactively promoted into confirmed product diagnoses.

## Active firewall proof, not just restored bytes

Before starting ctrs, `firewall-setup.sh` created two owned netns/veth paths
(`fw-a`/`fw-b`, neither matching `ctrs*`). With explicit allow rules their
ping succeeded; a preexisting `DOCKER-USER` DROP then blocked it. Host
`FORWARD` policy was DROP throughout.

While ctrs was running, `firewall-active.log` records:

```text
NET_OK
NON_CTRS_DENIED_WHILE_CTRS_ACTIVE
DENY_REMOVAL_POSITIVE_CONTROL_OK
UNSOLICITED_NON_CTRS_TO_CTRS_DENIED
ACTIVE_FIREWALL_PROOF_OK
```

The ctrs probe resolved Alpine's CDN and installed curl. During-operation
counters show **6,324 packets** matching ctrs outbound, **7,582** matching
established/related return, and **4 packets / 336 bytes** hitting the
retained non-ctrs DROP. Removing only that DROP while ctrs remained active
made the non-ctrs ping succeed (2/2); it was then reinstated. A new inbound
flow from `fw-a` to an actual ctrs container (`172.18.0.2`) remained denied.
The only installed ctrs exceptions, readable through iptables-nft, were:

```text
-A DOCKER-USER -i ctrs+ -m comment --comment ctrs-linux-forward-outbound -j ACCEPT
-A DOCKER-USER -o ctrs+ -m conntrack --ctstate RELATED,ESTABLISHED -m comment --comment ctrs-linux-forward-return -j ACCEPT
```

They match the `ctrs*` interface prefix, not all forwarding, and return
traffic is state-restricted. They do not establish an identity guarantee
for some unrelated administrator-created interface also named `ctrs*`.
Live packet-policy proof was IPv4; no independent IPv6 deny/allow traffic
experiment was performed in this slice.

After ctrs stopped, `cmp` of pre/post `DOCKER-USER` and `FORWARD` snapshots
returned 0 for both: **`CTRS_FIREWALL_RESTORED_EXACTLY`**. The deny and
explicit control rules were retained until our separate proof cleanup.
Final `cleanup.log`/`final-cleanup.txt` show empty `DOCKER-USER`, the
original DROP-policy FORWARD/jumps, no ctrs tables/tagged rules/bridges,
no proof veth/netns or private engine processes/cgroups, and inactive
successful ctrs/private-engine units. Anonymous private Docker volumes
were removed; disposable `.work/c`, `.work/d`, `.work/r` stores were
deleted. Host has no containers/custom networks; its preexisting
`ctrs-cargo-amd64` cache volume was retained. Ordinary image/build cache
was not globally pruned. Kernel-module state was not unloaded/reset.

## Independent frozen restore and provenance follow-up

After e2e, the final isolated Docker/containerd (ordinary e2e cache, no
prepared API image) and a **fresh empty ctrs store** restored the same
persisted `images.tar` through the existing path:

```sh
sudo -n unshare --mount --propagation private bash .work/restore-owned.sh
```

Only inside this temporary mount namespace, that script binds the owned
Docker socket over the path required by the existing `dockerd` adapter;
it does not connect to the host Docker socket. It invokes:

```sh
python3 bench/native/runner.py --lane linux-amd64 prepare \
  --linux-archive /home/ubuntu/ctrs-evidence/linux-amd64-v1/images.tar
```

`restore-owned.log` records:

```text
INDEPENDENT_OWNED_RESTORE_EXIT=0
246c0c6aca1d8c0a749f37b9281ec32735a326e414de872b45b1e77fa4f3b874  /home/ubuntu/repos/ctrs/.work/wt/linux-integrated/bench/native/linux/fixtures.lock.json
FROZEN_LOCK_UNCHANGED
SUDO_GIT_SHA=65b7bbd6ed5ca7bc803145e13983011eebe8321b
```

The existing preparation path validated all frozen native image identities
in both independent stores. This resolves the earlier shared-containerd
restore limitation for independent image-store restoration; Docker's e2e
cache was not empty, so it is not an entirely empty Docker-cache proof.
No lock regeneration, new timed trials or historical-record edits occurred.
Future sudo provenance works; old `unknown` values remain unchanged.

Checkpoint code checks were `make test-bench`: **459 tests, OK, 15
skipped**. After the final rebase, `make test-bench` ran **463 tests in
27.036s, OK (skipped=15)**; full output is `test-bench-after-rebase.log`.
This slice changes documentation/evidence only; its relevant
live checks are the current-main build, both complete e2e suites, focused
classification controls, active firewall proof, independent restore and
post-cleanup host verification above. They do not close a performance gate.
