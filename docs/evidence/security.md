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
| 6 | VM death with daemon live, injected through the engine's own test hook (`CTRS_TEST_VM_CRASH=1` + SIGUSR2 → `force_stop` → `Event::Lost`); a sentinel engine with a live container runs beside it | `Event::Lost` boots a fresh VM and restarts `unless-stopped` containers; the old generation's `StartedAt` changes; the sentinel engine and its container are untouched | **PASS**: restarted container answers exec with a new generation; sentinel unchanged (`S12`). Supersedes the earlier `kill -9`-of-the-XPC-helper injection, which could not scope to one engine; see the addendum below | `conformance/failure.sh` S12; `crates/ctrs/src/main.rs`, `daemon/mod.rs`, `engine.rs`, `vmlink.rs` |
| 7 | Full e2e with all CTRS-21 changes in the guest and daemon | 480 + 1 | **481/481, 0 skipped** | `tests/e2e.sh` on fresh scratch engine |
| 8 | Guest console on unexpected VM stop | oops trace must survive the VM | **PASS**: `hvc0` captured to `<root>/vm-console.log` (previous boot `.prev`); `Event::Lost` emits the last 32 KiB into the daemon log; verified live under instance-scoped injection (`S12`) | `crates/ctrs/src/guest.rs`, `engine.rs`; live repro |
| 9 | SIGKILL at lifecycle steps: at rest; with a running container (no policy); between create and start (deterministic API-order); mid-run | engine consistent after restart; created container starts; dead no-policy container marked `Exited(255)` | **PASS — 10 assertions** (`S1`×4, `S2`×2, `S3`, `S4`×3); engine rebind waits for a real HTTP 200 on `/version`, not the socket file | `conformance/failure.sh` |
| 10 | SIGKILL mid-pull (public.ecr.aws/docker/library/postgres:17-alpine), recovery engine pulls again | pull completes; store digest-verified; no partial blob | **PASS — 2 assertions** (`S5`) | `conformance/failure.sh` |
| 11 | Disk-full on the image store: 64 MiB APFS sparse image symlinked in as `blobs/`+`tmp/`, `docker pull` of postgres:17-alpine via ECR Public | pull fails with an ENOSPC failure message, not any non-zero exit; no partial blobs left in `tmp/`; engine alive; no partial image; `containers.json` consistent; pull succeeds once space returns | **PASS — 7 assertions** (`S6`); partial blobs removed on writer drop | `conformance/failure.sh` |
| 12 | Container OOM (`--memory 24m`, awk doubling allocator) | kernel kills; exit 137; `inspect` shows `OOMKilled=true`; engine alive | **PASS** (`S7`) | `conformance/failure.sh` |
| 13 | `--restart always` on a failing command | restart with backoff; engine responsive; `rm -f` stops the loop | **PASS — RestartCount=6 in 6 s** (`S8`) | `conformance/failure.sh` |
| 14 | Rollback: published-port clash; unknown network on create+start | second publish refused; unknown network refused; first container unaffected; engine healthy after | **PASS** (`S9`) | `conformance/failure.sh` |
| 15 | Concurrent pulls of the same image (4×) | shared pull; all exit 0; image recorded once | **PASS — 2 assertions** (`S10`); when the registry answers 429 the scenario reports SKIP with the registry's own error, never a silent pass | `conformance/failure.sh` |
| 16 | Boundary spot checks: host socket 0600, data root 0700, and inside containers (default and `--privileged`): no `/var/run/docker.sock`, no `/mnt/mac`, no `/run/host-services/*`; container env carries no `CTRS_*`/`DOCKER_*` | unreachable | **PASS — 5 checks** | `conformance/isolation.sh` |

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
| VM death with daemon alive (`Event::Lost`) | containers marked `Exited(255)`, persisted; fresh VM boots; `always`/`unless-stopped` containers restart (verified by instance-scoped SIGUSR2 injection with a surviving sentinel engine, `S12`) |
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
- `conformance/watch.sh` — supervising harness for the silent daemon
  deaths: daemon as a child process under privileged-container churn;
  records OS exit code/signal, instance identity, VM generations, log
  tail to `.work/tmp/watch-reports/*.jsonl`; clean budget stop is success,
  any other exit is a failure with evidence
- `docs/security.md` (threat model) · the #50 restart gap (now fixed; see `docs/decisions.md`)
- `crates/ctrs/src/guest.rs`, `crates/ctrs/src/daemon/engine.rs`,
  `crates/ctrs-vmm/src/process.rs` (console capture)
- `crates/ctrs-init/src/linux/layers.rs` (fail-closed unpack)
- `crates/ctrs/src/daemon/mod.rs` (`root_lock`)
- `crates/ctrs-image/src/store.rs` (image index `INDEX_LOCK` + race test)
- `conformance/seccomp/run.sh` — also fixed `tests/e2e.sh` so the build-* checks re-create the buildkit builder on the current socket (a stale builder used to fail every build group with no hint why); verified by red→green

## Addendum: failure-harness qualification after the 2026-11-14 review

The original `S12` used `kill -9 $(pgrep -f Virtualization.VirtualMachine)`: it
signalled every matching helper on the host, with no association to the engine
under test, and could not guarantee an unrelated VZ VM survived. It has been
removed. (At the time it actually ran, only our scratch engines existed on
this Mac — OrbStack uses its own hypervisor, not Virtualization.framework —
so no unrelated VM was observed to die; but the checked-in command admitted
that outcome, and the qualification cannot rest on that luck.)

The replacement injects through the daemon's own test hook
(`CTRS_TEST_VM_CRASH=1` + SIGUSR2, blocked before any thread spawns): the
injected process kills its **own** VM via `VmLink::crash_for_test` →
`force_stop` and takes the same `Event::Lost` path as a helper death. A
sentinel engine with a live container proves scoping; the restart assert
requires a new container `StartedAt` generation and a successful `exec`.

Assertion repairs in the same pass:

- `S1` waits for a real HTTP 200 on `/version` from the rebound socket
  (previously any non-empty output passed, connection errors included).
- `S6` requires the ENOSPC text in the pull error and asserts `tmp/` is empty
  afterwards (previously any failed pull counted).
- `S12` fails if the sentinel's state is anything but `running` or changed
  (previously the only assert was on the restarted container).
- The harness no longer depends on anonymous registry quota for incidental
  pulls: images are loaded from a local tar (`.work/tmp/preload/`, built once
  from a throwaway engine). Pull-centric scenarios (S5, S6, S10) keep network
  pulls, from `public.ecr.aws/docker/library/…` (bit-identical official
  images); a 429 from the registry makes S10 SKIP with the registry's error,
  never a pass.
- `fresh_engine`/`recovery_engine` wait for the API to answer, not for the
  socket file, which can be a stale leftover (this was masking the old S1
  assert's weakness and then exposed a real race: the new assert failed once
  and the harness was fixed, not the assert weakened).

Full suite on 2026-11-14 after the repairs: **34 pass, 0 fail, 0 skip**;
no leaked engines or VZ helpers afterwards.
