# Recoverable Linux checkpoint — 2026-11-22

The Linux adapter exists. Use `--lane linux-amd64`, engines `ctrs` and
`dockerd`, and W2/W6/W7/W13. Native Linux x86_64 only: no fallback or
emulation. This checkpoint preserves the 2026-11-21 pilot, including its
invalid samples; it is not a new cohort or a macOS qualification result.
The ARM64 macOS/OrbStack campaign and all its gates remain separate.

## Supported identity

| Component | Identity |
| --- | --- |
| Host | Ubuntu 22.04.5 LTS, x86_64, 8 CPUs, 33,655,406,592 bytes RAM |
| Kernel | `6.8.0-1060-aws` |
| Baseline | Docker Engine Community 29.9.2, commit `0367cbe`, API 1.56 |
| Storage/accounting | overlayfs, systemd cgroup driver, unified cgroup v2 |
| containerd | 2.4.2, `b7a25261e029d68978bbf290df0a62fc819b3c51` |
| runc | 1.5.2, `v1.5.2-0-g29dd3dc2` |
| docker-init | 0.19.0, `de40ad0` |
| Fixture | `linux-amd64-v1`, committed `bench/native/linux/fixtures.lock.json` |
| Sampler | `2-linux-cgroup-v2-memory-stat` |
| Historical harness | `c57ec0851496700dc4bc34f1bb869aba9de8a9cf` (pre-rebase identity) |
| Historical ctrs/agent source | `192d83e62b05fce6a6ac89fe0808b92d9cd3ff93` |
| Checkpoint base | `6bc5871efd91ad147480ac266294fa6d3522bb63` |

Historical executable SHA-256s, verified against the preserved bytes:

```text
5e80c7f8011af060a541b756d62ff2ffe6f79f9876b528c70925343e6a9202f7  ctrs
9acfbfcab8f0bc08ed13d0e0f33cb57fe2d496a97ad6e88ffe98cd09181a9420  ctrs-init
```

The harness never manages dockerd's lifecycle/configuration; normal baseline
endpoint is `/var/run/docker.sock`. `ctrs` is externally managed through an
absolute `CTRS_SOCKET`; Linux cold/fresh-directory/config-override lifecycle
is refused. Use `bench/native/linux/ctrs-engine.sh start|stop BINARY RUN_DIR`
for the delegated systemd/private-mount launcher (`RUN_DIR` under `.work/`).
On Linux the agent hard-codes `/var/lib/ctrs`; a dedicated bind mount is
necessary, not just `CTRS_DATA_DIR`. Forwarding coexistence is on main.

CPU uses cgroup `cpu.stat usage_usec`; memory records `memory.current`,
optional `memory.peak`, and `memory.stat` anon/file/kernel. Footprint analog
is peak coincident anon+kernel, **not** page-cache-inclusive memory.current.
Docker ownership includes docker.service, containerd.service, container
scopes and verified transients. Direct children of system.slice named
`system.slice:docker:<id>` are structurally Docker-owned, even empty/retired;
an unrelated process creating that name would be counted. ctrs cannot
overlap that set. Retired counters are retained; unverifiable members
invalidate samples. These are sampled lower bounds, not exited-task CPU
or physical-memory qualification. See the [lane contract](../campaign-native-performance.md#linux-lane-dockerd).

## Retrieval and immutable manifest

Persistent root on this VM: `/home/ubuntu/ctrs-evidence/linux-amd64-v1/`.
The committed [SHA-256 manifest](linux-amd64-v1.sha256) covers every top-level
artifact; `baseline-members.sha256` indexes every regular file in baseline.tar.
These are retained local evidence, **not** a claim of an off-host backup.
Copy them off the VM before retiring it, for example:

```sh
scp -r ubuntu@HOST:/home/ubuntu/ctrs-evidence/linux-amd64-v1 ./linux-amd64-v1
cd linux-amd64-v1
sha256sum -c /path/to/ctrs/docs/evidence/linux-amd64-v1.sha256
```

Contents:

- `images.tar`: frozen image archive, identical to the archive in baseline.tar.
- `baseline.tar`: `.work/native-perf/linux-amd64-v1` sources/archive;
  **all** existing `.work/native-perf/results` records and traces (including
  failed ownership attempts); `.work/linux-pilot-20261121` frozen design,
  commands, logs, analysis program/output and scorecard verifier; preparation
  log, smoke commands/verifiers and completed-lane note; exact ctrs/agent
  executables under `target/linux-x86_64/release/`.
- `source.bundle`: Git history including pre-rebase historical source IDs,
  collected with `git bundle create source.bundle --all --reflog`.
- `fixtures.lock.json`: unchanged committed Linux lock for independent comparison.
- `host-docker.json`, `kernel.txt`: actual tool/kernel identity receipts.
- `restore-command.sh`, `restore.log`: exact isolated restoration invocation
  and its output.

No old record was rewritten. In particular old `git_sha: unknown`, the three
invalid W13 resource trials, and all tool-limited flags remain as recorded.
The historical reason for each unknown SHA was not captured. Future Git
provenance commands explicitly trust only this repository for that invocation
(`git -c safe.directory=...`), including sudo, and reject failed/empty SHA
output rather than inventing a revision. An actual sudo invocation returned
`SUDO_GIT_SHA=6bc5871efd91ad147480ac266294fa6d3522bb63` on the checkpoint base.

## Restoration proof (no lock regeneration)

Extract into an empty scratch directory, verify every member, and recover
the old source, without reading the original `.work` trees:

```sh
mkdir -p .work/restored
tar -xf /home/ubuntu/ctrs-evidence/linux-amd64-v1/baseline.tar -C .work/restored
(cd .work/restored && sha256sum --quiet -c /home/ubuntu/ctrs-evidence/linux-amd64-v1/baseline-members.sha256)
git clone /home/ubuntu/ctrs-evidence/linux-amd64-v1/source.bundle .work/restored-source
git -C .work/restored-source cat-file -e c57ec0851496700dc4bc34f1bb869aba9de8a9cf^{commit}
git -C .work/restored-source cat-file -e 192d83e62b05fce6a6ac89fe0808b92d9cd3ff93^{commit}
```

Tested the existing archive restoration path using the **restored historical
executables**, an empty dedicated ctrs store, and a separate Docker API daemon
(`ctrs-restore-docker.service`, empty data/exec roots, separate Unix socket,
bridge none, iptables/ip6tables/ip-forward/ip-masq false). **This was not
complete Docker isolation:** the secondary daemon connected to the host's
`/run/containerd/containerd.sock` in namespace `moby`, as its journal shows.
Separate Docker data/exec roots alone did not isolate that dependency.
The host dockerd was not restarted/reconfigured. Because the supported harness
endpoint is fixed, a private mount namespace bind-mounted the owned Docker
socket over `/var/run/docker.sock` **only inside the restore process**.
The preserved script records all absolute paths. Equivalent command inside
that private namespace, with externally managed `CTRS_SOCKET`:

```sh
python3 bench/native/runner.py --lane linux-amd64 prepare \
  --linux-archive /home/ubuntu/ctrs-evidence/linux-amd64-v1/images.tar
```

Actual restore used the byte-identical images.tar extracted from baseline.tar.
Archive hash is checked against the existing lock before engine access; the
implementation loads both stores and verifies every frozen image identity.
No image build or lock generation occurred. Output:

```text
LEGACY_SOURCE_RESTORED
RESTORE_EXIT=0
246c0c6aca1d8c0a749f37b9281ec32735a326e414de872b45b1e77fa4f3b874  /home/ubuntu/repos/ctrs/.work/wt/linux-checkpoint/bench/native/linux/fixtures.lock.json
FROZEN_LOCK_UNCHANGED
```

The before/after lock hash matches the committed manifest. Both disposable
engines were stopped after verification; the host daemon remained active.
This proves local retrieval and archive loading, not an independent empty
Docker/containerd restoration or an off-host disaster-recovery test.

## Runtime blocker discovered immediately afterward

The next current-main build failed before compilation:

```text
docker: Error response from daemon: failed to set up container networking: failed to create endpoint boring_buck on network bridge: adding interface veth86dc897 to bridge docker0 failed: Device does not exist
LINUX_BUILD_EXIT=1
```

`docker0` was present before restoration but absent afterward. The host Docker
network metadata still describes bridge `docker0`, subnet `172.17.0.0/16`,
gateway `172.17.0.1`, and no attached containers. PID 599 and the original
service start timestamp remain unchanged. The exact deleting operation was
not traced; the secondary daemon's shared host networking/containerd is a
setup-isolation suspect, **not a confirmed cause**. The ctrs restore journal
shows image loads only, no agent/container startup, which weighs against
ctrs agent bridge cleanup executing in this restore.

No shared-host bridge repair or daemon restart was attempted without approval.
The integrated e2e/firewall pass has **not run**. Before resuming, authorize
repair of the existing Docker network and verify its normal operation. Use
a separate network namespace **and** private containerd/socket/namespaces for
the disposable e2e daemon, not merely separate Docker roots.
Incident receipts and the failed build log are retained under
`/home/ubuntu/ctrs-evidence/linux-integrated-20261122/` (`restore-dockerd.log`,
`host-links-after.json`, `host-bridge-metadata.json`, `host-docker-state.txt`,
`build.log`). The frozen baseline artifacts and manifest remain unchanged.
