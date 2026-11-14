# Parity register — ctrs vs upstream Kiri / Docker Engine API

Seed: 2026-11-13 (CTRS-05), from the pinned upstream `docs/features.md` ("What works", `lines 9–89`) and the Docker API 1.47 surface implemented in `crates/kiri/src/daemon/api.rs`. Statuses: `open` (unverified), `pass`, `fail`, `intentional-diff` (deleted or deliberately changed, with reason and slice), `n-env` (parked on Needs environment — see campaign doc).

Every row must reach `pass` or documented `intentional-diff` before Gate J. A behavior with no test is not done.

| ID | Behavior (source) | Upstream proof | Status | Evidence |
| --- | --- | --- | --- | --- |
| P-001 | Container lifecycle: `run` flags (`--rm -d -it -e -u -w --name --restart --entrypoint`) (features.md:10) | tests/e2e.sh | pass | CTRS-04/08 smoke + e2e ; e2e 2026-11-14 |
| P-002 | Exit codes and stdout/stderr of `run` returned to caller | tests/e2e.sh | pass | CTRS-04/08 ; e2e 2026-11-14 |
| P-003 | `exec` | tests/e2e.sh | pass | CTRS-04/08 ; e2e 2026-11-14 |
| P-004 | `logs` (follow, tail, stdout+stderr) | tests/e2e.sh | pass | CTRS-04/08 ; e2e 2026-11-14 |
| P-005 | `attach` (upgrade/hijack semantics) | tests/e2e.sh | open | CTRS-14/15 |
| P-006 | `stop`/`kill`/`restart`/`wait` | tests/e2e.sh | pass | CTRS-04/08 ; e2e 2026-11-14 |
| P-007 | `rename` | tests/e2e.sh | pass | adapted e2e (CTRS-08) ; e2e 2026-11-14 |
| P-008 | `pause`/`unpause` | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-009 | `update` (resource limits) | tests/e2e.sh | pass | e2e (CTRS-08) ; e2e 2026-11-14 |
| P-010 | `stats` | tests/e2e.sh | pass | e2e (CTRS-08) ; e2e 2026-11-14 |
| P-011 | `top` | tests/e2e.sh | pass | e2e (CTRS-08) ; e2e 2026-11-14 |
| P-012 | `diff` | tests/e2e.sh | pass | e2e (CTRS-08) ; e2e 2026-11-14 |
| P-013 | `export` | tests/e2e.sh | pass | e2e (CTRS-08) ; e2e 2026-11-14 |
| P-014 | `commit` | tests/e2e.sh | pass | e2e (CTRS-08) ; e2e 2026-11-14 |
| P-015 | `cp` both directions, running and stopped | tests/e2e.sh | pass | e2e (CTRS-08) ; e2e 2026-11-14 |
| P-016 | `container prune` | tests/e2e.sh | pass | e2e (CTRS-08) ; e2e 2026-11-14 |
| P-017 | Filters on every list surface | tests/e2e.sh | pass | e2e (CTRS-08) ; e2e 2026-11-14 |
| P-018 | Records survive a daemon restart | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-020 | `--memory`/`--cpus`/`--cpu-shares`/`--pids-limit`/`--shm-size` (features.md:15) | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-021 | Default capabilities + default seccomp profile | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-022 | `--cap-add`/`--cap-drop`, `--privileged`, `--read-only`, `seccomp=unconfined`, `no-new-privileges` | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-023 | Even `--privileged`/unconfined keeps the host boundary: no vsock sockets, no io_uring | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-030 | Default bridge (features.md:21) | tests/e2e.sh | pass | CTRS-04/08/17 ; e2e 2026-11-14 |
| P-031 | User networks with DNS by name and alias | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-032 | `network connect`/`disconnect` | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-033 | `--network host` and `--network none` | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-034 | `-p`/`-P` TCP+UDP published ports; all interfaces; `127.0.0.1:port:port` stays local | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-035 | `--add-host`, `host.docker.internal` | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-036 | `--network container:<name>` (Compose share-net; restart keeps old netns until peer restarts — upstream semantics) | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-037 | IPAM: `--subnet`/`--gateway`/`--ip-range`/`--aux-address`, `--ip`, `--mac-address` | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-038 | `--dns`/`--dns-search`/`--dns-option`/`--domainname` | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-039 | IPv6 networks (`--subnet` or `fd00::/8` /64); default bridge stays IPv4-only | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-040 | `http://<name>.kiri.local` with TLS CA in `~/.kiri/tls` | tests/e2e.sh | intentional-diff | domains/TLS CA deleted (CTRS-07) |
| P-041 | Reconnect after Mac sleep; ports republish after wake | tests/e2e.sh | open | CTRS-17/21 |
| P-050 | Named and anonymous volumes; `volume` commands (features.md:40) | tests/e2e.sh | pass | CTRS-04/08 ; e2e 2026-11-14 |
| P-051 | Bind mounts of Mac paths (virtiofs), write durability, host↔guest propagation | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-052 | `--tmpfs`, `--mount` | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-053 | Layer whiteouts; mount-path safety; write durability | unit tests (kiri-init layers) | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-060 | `pull` with `docker login` credentials (features.md:42) | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-061 | `push` | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-062 | `tag`, `history`, `image prune`, `system df`, `search` | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-063 | `save`, `load` | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-064 | Manifest index digest verification | unit tests (kiri-image) | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-065 | `--platform`; amd64 images via Rosetta on arm64 | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-066 | Partial/corrupt blob handling; registry retries; redirects; bearer auth | unit tests (kiri-image) | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-070 | `docker build` / `buildx build` through BuildKit in a Kiri container (features.md:45) | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-071 | amd64 build steps via Rosetta | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-072 | Compose: `up`/`down`/`ps`/`logs`/`exec`; multiple networks; events (features.md:48) | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-073 | BuildKit `host-gateway` unsupported (upstream known issue, features.md:106) | documented | intentional-diff | upstream known issue; documented, not a fork regression (docs/upstream.md) |
| P-080 | `~/Kiri` Finder/NFS browsing (features.md:49) | tests/e2e.sh | intentional-diff | deleted (CTRS-07) |
| P-081 | SSH agent forwarding at `/run/host-services/ssh-auth.sock` | tests/e2e.sh | pass | mount + handshake 2026-11-14: container `ssh-add -l` against mounted socket answers (empty host agent) |
| P-090 | Memory balloon; VM sleeps after idle; daemon RSS floor (features.md:52) | tests/e2e.sh | pass | e2e 2026-11-14 (480/0/0) + smoke (15/15) |
| P-100 | The window (all UI) (features.md:54) | tests/e2e.sh (n/a) | intentional-diff | deleted (CTRS-07) |
| P-101 | Menu bar (features.md:61) | n/a | intentional-diff | deleted (CTRS-07) |
| P-102 | Kubernetes: `kiri k8s start`, k3s, kubectl context (features.md:63) | n/a | intentional-diff | deleted (CTRS-07) |
| P-103 | Linux machines: `kiri machine create` (features.md:65) | n/a | intentional-diff | deleted (CTRS-07) |
| P-104 | The app: `Kiri.app`, updater, DMG, notarization, feeds (features.md:67) | n/a | intentional-diff | deleted (CTRS-06/07); notarization is N-4 |
| P-105 | Linux hosts: same engine, no VM; musl artifacts (features.md:71) | tests/linux-host.sh | n-env | build target kept; runtime proof is N-1 |
| P-106 | Windows/WSL2: `kiri-win.exe`, npipe, msi (features.md:77) | n/a | intentional-diff | deleted (CTRS-06) |
| P-107 | `kiri import` (from OrbStack/Docker Desktop) (features.md:77) | n/a | intentional-diff | deleted (CTRS-07) |
| P-108 | Setup creates docker context + LaunchAgent automatically | n/a | intentional-diff | headless fork never creates contexts (CTRS-08) |
| P-110 | `build --add-host name:host-gateway` fails with docker-container builder (features.md:106) | documented upstream known issue | intentional-diff | upstream known issue; documented, not a fork regression (docs/upstream.md) |
