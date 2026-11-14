# CTRS-21 — Security qualification: what was attacked, what held

Date: 2026-11-14. Harness: `conformance/seccomp/run.sh`, `conformance/failure.sh`
(new), `conformance/isolation.sh` (new), `tests/e2e.sh` (fresh engine,
481/481), in-VM fixtures built through the guest (fail-closed layer unpack,
negative control), scratch engines under `.work/tmp/` for every
kill/restart experiment. No host system state was modified; OrbStack was not
touched; no daemon was pointed at anything but scratch roots. The only
system objects created and removed were a 64 MiB APFS sparse image and its
mount, entirely inside `.work/tmp/` (`hdiutil`, detached at the end).

## Verdict

The engine fails closed in every fixture where the check exists, and the
fixtures all run green: 12 modes × 37 syscalls, 30 failure-injection
assertions, 5 boundary spot checks. **No P0/P1 findings remain open from
this slice.** The remaining gaps are known, written down, and none of them
is a silent hole: the nine silent daemon deaths (unproven root cause,
Virtualization.framework XPC helper) and the needs-Linux rows below. This is
not a security qualification of multi-tenant use; it is the honest boundary
statement for a single-user engine (see `docs/security.md`).

## Injection matrix (what was done, what happened)

| # | Injected failure | Expected | Result | Evidence |
| --- | --- | --- | --- | --- |
| 1 | Malicious OCI layer with `../escape` path (`ctrs21/evil-layer`), unpack in guest | layer refused, container create fails closed | **PASS (with fix)**: `unpack sha256:a7ea…: whiteout escapes the layer`, rc=1 | in-VM repro |
| 1n | Same fixture against the pre-fix guest (`unpack_in` boolean discarded) | silent partial rootfs accepted | **confirmed pre-fix behavior** (create succeeded, `../` entry silently dropped) — fixture discriminates | negative control |
| 1s | OCI layer with symlink `linkdir → /etc` and `linkdir/escape-evidence` | file must not land in `/etc` | **PASS**: `unpack … trying to unpack outside of destination path`, rc=1 | in-VM repro |
| 2 | Second engine started on a data root already in use | refused at boot, first engine unaffected | **PASS**: `the data root … is in use by another engine`, second exits 1 | `flock(2)` on `<root>/.lock` (new) |
| 3 | Daemon SIGKILL at rest (mid-steady-state), fresh engine on the same root | stale socket rebound; policy container back up | **PASS**: new engine boots VM (~1 s) and restarts `ctrs21-restart` (`unless-stopped`); the stale `.sock` is unlinked and rebound without `rm` (harness keeps it; the daemon rebinds itself) | live repro; `conformance/failure.sh` S1, S3 |
| 4 | Seccomp differential fixture: static probe replayed under default, `no-new-privileges`, `seccomp=unconfined`, `--privileged`, `SYS_ADMIN`, `SYS_BOOT`, `SYS_TIME`, `SYS_NICE`, `SYS_MODULE`, `SYS_PACCT`, `BPF`, `PERFMON` (×12 modes, 37 syscalls each) | vsock + io_uring denied in **all** modes; others denied except the per-cap relaxations; clone3 ENOSYS without SYS_ADMIN | **PASS — fixture green**: "all modes match the documented filter (vsock+io_uring denied for everyone; capabilities relax only their own rules)" | `conformance/seccomp/run.sh` |
| 5 | `seccomp=unconfined` lets mount(2) through (userns owner holds CAP_SYS_ADMIN in-ns) | — (observed, matches design) | Verified behavior: errno:14 (EFAULT), not EPERM — boundary only, as documented in code | seccomp run |
| 6 | VM death with daemon live (`kill -9` of the Virtualization.framework XPC helper; scratch engine) | `Event::Lost` boots a fresh VM and restarts `unless-stopped` containers; a no-policy container stays down | **PASS**: VM re-boots (148 ms), `ctrs21-restart` Up; `ctrs21-norestart` Exited (255); container `unless-stopped` restarted again in the harness run | live injection; `conformance/failure.sh` S12 |
| 7 | Full e2e with all CTRS-21 changes in the guest and daemon | 480 + 1 | **481/481, 0 skipped** | `tests/e2e.sh` on fresh scratch engine |
| 8 | Guest console on unexpected VM stop | oops trace must survive the VM | **PASS**: `hvc0` captured to `<root>/vm-console.log` (previous boot `.prev`); `Event::Lost` emits the last 32 KiB into the daemon log; verified live under `kill -9` of the VM helper | `crates/kiri/src/guest.rs`, `engine.rs`; live repro |
| 9 | SIGKILL at lifecycle steps: at rest; with a running container (no policy); between create and start (deterministic API-order); mid-run | engine consistent after restart; created container starts; dead no-policy container marked `Exited(255)` | **PASS — 13 assertions** (`S1`×4, `S2`×2, `S3`, `S4`×5) | `conformance/failure.sh` |
| 10 | SIGKILL mid-pull (postgres:17-alpine), recovery engine pulls again | pull completes; store digest-verified; no partial blob | **PASS** (`S5`) | `conformance/failure.sh` |
| 11 | Disk-full on the image store: 64 MiB APFS sparse image symlinked in as `blobs/`+`tmp/`, `docker pull postgres:17-alpine` | pull fails non-zero; engine alive; no partial image; `containers.json` consistent; pull succeeds once space returns | **PASS — 6 assertions** (`S6`); partial blobs removed on writer drop | `conformance/failure.sh` |
| 12 | Container OOM (`--memory 24m`, awk doubling allocator) | kernel kills; exit 137; `inspect` shows `OOMKilled=true`; engine alive | **PASS** (`S7`) | `conformance/failure.sh` |
| 13 | `--restart always` on a failing command | restart with backoff; engine responsive; `rm -f` stops the loop | **PASS — RestartCount=6 in 6 s** (`S8`) | `conformance/failure.sh` |
| 14 | Rollback: published-port clash; unknown network on create+start | second publish refused; unknown network refused; first container unaffected; engine healthy after | **PASS** (`S9`) | `conformance/failure.sh` |
| 15 | Concurrent pulls of the same image (4×) | shared pull; all exit 0; image recorded once | **PASS** (`S10`) | `conformance/failure.sh` |
| 16 | Boundary spot checks: host socket 0600, data root 0700, and inside containers (default and `--privileged`): no `/var/run/docker.sock`, no `/mnt/mac`, no `/run/host-services/*`; container env carries no `KIRI_*`/`DOCKER_*` | unreachable | **PASS — 5 checks** | `conformance/isolation.sh` |

## Seccomp differential, the important lines (raw, 2026-11-14)

| mode | socket(AF_VSOCK) | io_uring_setup/enter/register | clone3 | bpf | mount | acct | perf_event_open |
| --- | --- | --- | --- | --- | --- | --- | --- |
| default | EAFNOSUPPORT | EPERM | **ENOSYS** | EPERM | EPERM | EPERM | EPERM |
| no-new-privileges | EAFNOSUPPORT | EPERM | ENOSYS | EPERM | EPERM | EPERM | EPERM |
| seccomp=unconfined | EAFNOSUPPORT | EPERM | EINVAL | EINVAL (bad args) | EFAULT (allowed) | ENOSYS (kernel) | EFAULT (kernel) |
| --privileged | EAFNOSUPPORT | EPERM | EINVAL (bad args) | EINVAL (bad args) | EFAULT (allowed) | ENOSYS (kernel) | EFAULT (kernel) |
| SYS_ADMIN | EAFNOSUPPORT | EPERM | **EINVAL** (filter relaxed) | EPERM | EFAULT (allowed) | EPERM | EPERM |
| SYS_BOOT | EAFNOSUPPORT | EPERM | ENOSYS | EPERM | EPERM | EPERM | EPERM (reboot → EINVAL) |
| SYS_TIME | EAFNOSUPPORT | EPERM | ENOSYS | EPERM | EPERM | EPERM (settimeofday → OK, sets guest clock) | EPERM |
| SYS_NICE | EAFNOSUPPORT | EPERM | ENOSYS | EPERM | EPERM | EPERM | EPERM |
| SYS_MODULE | EAFNOSUPPORT | EPERM | ENOSYS | EPERM | EPERM | EPERM (init/finit/delete_module → ENOSYS, kernel compiled modules out) | EPERM |
| SYS_PACCT | EAFNOSUPPORT | EPERM | ENOSYS | EPERM | EPERM | **ENOSYS** (acct relaxed) | EPERM |
| BPF | EAFNOSUPPORT | EPERM | ENOSYS | **EINVAL** (relaxed) | EPERM | EPERM | EPERM |
| PERFMON | EAFNOSUPPORT | EPERM | ENOSYS | EPERM | EPERM | EPERM | **EFAULT** (relaxed) |

Read: the two rules that hold for everyone, including `--privileged` and
`seccomp=unconfined`, are the vsock control channel and `io_uring`. The rest
of the profile is capability-relaxation exactly as the code comments claim.
`kernel ENOSYS` entries (acct, mbind-family, syscall-family against a kernel
compiled without those features) are kernel answers, not filter answers.

## Restarts and crashes

| scenario | result |
| --- | --- |
| daemon boot with `unless-stopped` container recorded running | container restarted automatically (Docker semantics), verified (sigkill and clean restarts); also `S3` |
| VM death with daemon alive (`Event::Lost`) | containers marked `Exited(255)`, persisted; fresh VM boots; `always`/`unless-stopped` containers restart (verified by `kill -9` of the XPC helper, `S12`) |
| kill at lifecycle steps (at rest, between create and start, mid-run, mid-pull) | store consistent; created container startable; no-policy dead containers `Exited(255)`; stale socket rebound by the daemon itself |
| silent daemon death (9 this campaign) | engines died with zero log output; launchd/whatever supervises restart brings the daemon back; on return, `load()` restarts policy containers. Unproven root cause (VZ XPC helper); tracker in decisions |
| stale `.sock` after SIGKILL | unlinked and rebound by the recovery engine (harness keeps the file in place; rebind is the daemon's job) |

## Not tested here — needs Linux / owner action / impossible on this host

- Seccomp and namespaces on the x86_64 build and the x32 ABI mask
  (aarch64-only host; the x86_64 filter path is compile-checked, never
  executed).
- The malicious-layer unpack fixture against a **signed/qualified** guest;
  the negative control ran against the dev guest only.
- Mount propagation between host↔VM and symlink races during unpack — the
  guest agent calls `tar` with `set_unpack_xattrs`, `preserve_ownerships`,
  `set_overwrite`, and `unpack_in` (canonicalizes parents inside the
  destination); residual TOCTOU on shared virtiofs is inherent to the
  sharing mechanism, not fixable here.
- Concurrent pulls of **different** images racing the image-index
  read-modify-write: **found and fixed here**. The index (`images.json`)
  is rewritten per record without serialization, so last-writer-wins could
  drop an image (blobs stay safe: digest-verified, atomic rename). All
  index mutators (`put_image`, `set_pushed`, `remove_image`) now take one
  `INDEX_LOCK` across the read-modify-write; a regression test
  (`concurrent_put_image_keeps_every_image`, 8 threads × 8 images) fails
  without the lock and passes with it.
- Crash consistency of the **guest** ext4 image under host-side SIGKILL:
  the guest recovers (`recovery complete` in `vm-console.log`), but no
  forced-crash-during-guest-write injection was run; the VM's disk is a
  scratch clone of a template built by `mkfs.ext4`.
- Multi-tenant isolation: not claimed.

## Files

- `conformance/seccomp/Dockerfile`, `conformance/seccomp/run.sh`,
  `conformance/seccomp/fixtures/seccomp-probe.c` (static probe, in-repo)
- `conformance/failure.sh` — SIGKILL at lifecycle steps, mid-pull kill,
  disk-full via a 64 MiB APFS sparse image symlinked in as `blobs/`+`tmp/`
  (created, used and detached inside `.work/tmp/`), OOM, restart loop,
  rollback paths, concurrent pulls, VM-death restart (S12)
- `conformance/isolation.sh` — host socket 0600 / data root 0700 / no
  host socket, relay socket, virtiofs share, or engine env in a container
  (default and `--privileged`)
- `docs/security.md` (threat model) · `docs/issues.md` (#50 restart gap, now fixed)
- `crates/kiri/src/guest.rs`, `crates/kiri/src/daemon/engine.rs`,
  `crates/kiri-vmm/src/process.rs` (console capture)
- `crates/kiri-init/src/linux/layers.rs` (fail-closed unpack)
- `crates/kiri/src/daemon/mod.rs` (`root_lock`)
- `crates/kiri-image/src/store.rs` (image index `INDEX_LOCK` + race test)
- `conformance/seccomp/run.sh` — also fixed `tests/e2e.sh` so the build-* checks re-create the buildkit builder on the current socket (a stale builder used to fail every build group with no hint why); verified by red→green
