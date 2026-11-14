# Gate B — onboarding and lifecycle (CTRS-08)

Date: 2026-11-14 (macOS 27.2, Apple Silicon). Machine: the development host; the engine ran from scratch roots under `.work/tmp/` only. OrbStack untouched throughout (junior-* containers `Up` the whole run; `/var/run/docker.sock` never opened; no docker contexts created or edited).

## Result

Gate B is **green**: `docker run --rm alpine true`, `exec`, `logs`, published port, named volume, and a daemon restart cycle all pass; clean-env smoke and the full adapted e2e are green; SIGTERM teardown is clean and fast.

## What was verified, and how

| Check | Command / harness | Result |
| --- | --- | --- |
| Engine round-trip | `conformance/smoke.sh` | 15/15 (API 1.47, run exit codes, exec/logs/rm, published port `127.0.0.1:18080→80`, SIGTERM ≤ 2 s, no stale `ctrs-init`, contexts unchanged, `~/.ctrs` untouched, idle RSS 8.1 MB) |
| Docker-compat suite | `CTRS_SOCKET=$PWD/.work/tmp/e2e.sock tests/e2e.sh` | **480 passed, 0 failed, 0 skipped** — includes published ports, named/anonymous volumes (`vol-persist`), every restart policy, and the full network/IPAM/IPv6 matrix |
| Daemon restart cycle | create `keepme` (alpine echo) → SIGTERM → start engine → `docker start -a keepme` | record survived; printed `hi`; exit code path intact |
| SSH agent forwarding | container with `/run/host-services/ssh-auth.sock` mounted, `ssh-add -l` | delivered end-to-end: the agent answered ("The agent has no identities", correct for the empty host agent, exit 1) |
| Clean environment | `env -i HOME=<scratch> CTRS_DATA_DIR=<scratch> CTRS_SOCKET=<scratch> PATH=/usr/bin:/bin ./target/release/ctrs daemon`, then `docker run --rm alpine echo` | boots the VM, pulls alpine fresh, prints; no user shell config, no inherited env required |
| Private state | socket mode `srw-------`; store root forced `0700`; diag dirs `0700`/`0600`; data root unified to `~/.ctrs/data` | verified by file modes during the runs |
| SIGTERM teardown | `conformance/smoke.sh`; clean-env check above | 1–2 s to full exit; socket removed; no stale agent |
| OrbStack hygiene | before/after `docker ps -a`, `docker volume ls` | only the user's `junior-*` (redis, postgres+pgvector, versitygw) plus the `ctrs-kbuild` build volume; one transient third-party container (`bctl-guest-test`, image `bctl-guest-test`, 14 s lifetime) observed mid-run and identified via `docker events` — not this campaign's work |

## Findings

- The scratch daemon died **silently once** during CTRS-08 verification tooling, with no `engine shutting down` log line and no restart (SIGKILL-class, or an external reaper). It did not reproduce in the detached (`nohup`) relaunch that ran the green e2e. The cause is unproven; if it recurs it is a P1 defect and belongs in CTRS-21. Recorded in `docs/decisions.md`.
- The two `--ipv4=false` network checks in e2e now call the Engine API directly (the host docker CLI is 27.3.1; the flag landed in CLI 28).
- The docker CLI template for API version was wrong upstream (`.Server.ApiVersion`); fixed to `.Server.APIVersion`.
