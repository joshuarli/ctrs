# CTRS-21 — Security qualification: what was attacked, what held

Date: 2026-11-14. Harness: `conformance/seccomp/run.sh` (new), `tests/e2e.sh`
(fresh engine, 481/481), in-VM fixtures built through the guest (fail-closed
layer unpack, negative control), scratch engines under `.work/tmp/` for every
kill/restart experiment. No host system state was modified; OrbStack was not
touched; no daemon was pointed at anything but scratch roots.

## Verdict

The engine fails closed in every fixture where the check exists, and the
fixtures all run green. **No P0/P1 findings remain open from this slice.**
The gaps that remain are known, written down, and none of them is a silent
hole: restart-after-VM-death (#50 analysis), console capture, the nine
silent daemon deaths (unproven root cause, Virtualization.framework XPC
helper), and the needs-Linux rows below. This is not a security
qualification of multi-tenant use; it is the honest boundary statement for a
single-user engine (see `docs/security.md`).

## Injection matrix (what was done, what happened)

| # | Injected failure | Expected | Result | Evidence |
| --- | --- | --- | --- | --- |
| 1 | Malicious OCI layer with `../escape` path (`ctrs21/evil-layer`), unpack in guest | layer refused, container create fails closed | **PASS (with fix)**: `unpack sha256:a7ea…: whiteout escapes the layer`, rc=1 | in-VM repro |
| 1n | Same fixture against the pre-fix guest (`unpack_in` boolean discarded) | silent partial rootfs accepted | **confirmed pre-fix behavior** (create succeeded, `../` entry silently dropped) — fixture discriminates | negative control |
| 1s | OCI layer with symlink `linkdir → /etc` and `linkdir/escape-evidence` | file must not land in `/etc` | **PASS**: `unpack … trying to unpack outside of destination path`, rc=1 | in-VM repro |
| 2 | Second engine started on a data root already in use | refused at boot, first engine unaffected | **PASS**: `the data root … is in use by another engine`, second exits 1 | `flock(2)` on `<root>/.lock` (new) |
| 3 | Daemon SIGKILL at rest (mid-steady-state), fresh engine on the same root | stale socket rebound; policy container back up | **PASS**: new engine boots VM (144 ms) and restarts `ctrs21-restart` (`unless-stopped`); second test: stale `.sock` file unlinked and rebound without `rm` | live repro |
| 4 | Seccomp differential fixture: static probe replayed under default, `no-new-privileges`, `seccomp=unconfined`, `--privileged`, `SYS_ADMIN`, `SYS_BOOT`, `SYS_TIME`, `SYS_NICE`, `SYS_MODULE`, `SYS_PACCT`, `BPF`, `PERFMON` (x12 modes, 37 syscalls each) | vsock + io_uring denied in **all** modes; others denied except the per-cap relaxations; clone3 ENOSYS without SYS_ADMIN | **PASS — fixture green**: "all modes match the documented filter (vsock+io_uring denied for everyone; capabilities relax only their own rules)" | `conformance/seccomp/run.sh` |
| 5 | `seccomp=unconfined` lets mount(2) through (userns owner holds CAP_SYS_ADMIN in-ns) | — (observed, matches design) | Verified behavior: errno:14 (EFAULT), not EPERM — boundary only, as documented in code | seccomp run |
| 6 | Full e2e with all CTRS-21 changes in the guest and daemon | 480 + 1 | **481/481, 0 skipped** | `tests/e2e.sh` on fresh scratch engine |

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
| daemon boot with `unless-stopped` container recorded running | container restarted automatically (Docker semantics), verified twice (sigkill and clean restarts) |
| VM death with daemon alive (`Event::Lost`) | containers marked `Exited(255)`, persisted, **not** restarted — defect localized; fix lands with the CTRS-21 failure harness |
| silent daemon death (9 this campaign) | engines died with zero log output; launchd/whatever supervises restart brings the daemon back; on return, `load()` restarts policy containers. Unproven root cause (VZ XPC helper); tracker in decisions |
| stale `.sock` after SIGKILL | unlinked and rebound, fresh engine answers |

## Not tested here — needs Linux / owner action / impossible on this host

- Seccomp and namespaces on the x86_64 build and the x32 ABI mask
  (aarch64-only host; the x86_64 filter path is compile-checked, never
  executed).
- Multi-VM crash matrix (kill at every lifecycle step) — needs the CTRS-21
  failure harness, which does not exist yet on any host; partial coverage
  today: sigkill-at-rest and daemon boot restart only.
- VM death with a live daemon (`Event::Lost`) restart behavior — injectable
  only by forcing a VM crash; the nine silent deaths this campaign *did*
  kill the daemon with the VM.
- Disk-full on the scratch root (digest-verified store, but ENOSPC
  propagation through `ensure_layers` was not exercised).
- OOM-kill of containers (no privileged cgroup write path exercised).
- Network rollback paths (egress allowlists do not exist in ctrs — nothing
  to roll back).
- Mount propagation between host↔VM and symlink races during unpack — the
  guest agent calls `tar` with `set_unpack_xattrs`, `preserve_ownerships`,
  `set_overwrite`, and `unpack_in` (canonicalizes parents inside the
  destination); residual TOCTOU on shared virtiofs is inherent to the
  sharing mechanism, not fixable here.
- Concurrent pulls of the same image into one root (now bounded by the
  CTRS-21 root lock at engine scope; in-flight digest fetch deduplication
  is unchanged).
- The malicious-layer unpack fixture against a **signed/qualified** guest;
  the negative control ran against the dev guest only.

## Files

- `conformance/seccomp/Dockerfile`, `conformance/seccomp/run.sh`,
  `conformance/seccomp/fixtures/seccomp-probe.c` (static probe, in-repo)
- `docs/security.md` (threat model) · `docs/issues.md` (#50 restart gap)
- `crates/kiri-init/src/linux/layers.rs` (fail-closed unpack)
- `crates/kiri/src/daemon/mod.rs` (`root_lock`)
- `conformance/seccomp/run.sh` — also fixed `tests/e2e.sh` so the build-* checks re-create the buildkit builder on the current socket (a stale builder used to fail every build group with no hint why); verified by red→green |
