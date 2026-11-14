# CTRS-20 — Upstream issue triage against the pin (`99b63c07`)

Date: 2026-11-14. Dispositions: **#121 fixed with test (in-VM verified);
#134 closed — fixed by CTRS-14, re-verified green today; #50 documented
known-issue with mitigations (crash lifecycle work routed to CTRS-21, where
the crash harness lives); #199 not-reproducible on this host (macOS 27.2) —
known-issue against macOS 15.x.**

Pinned upstream: Kiri `99b63c07fc003d3dcd8e03c76891ba747b5c984f` (2026-11-14).
All repros ran on the CTRS-17/20 scratch engines (never on a user VM or
OrbStack): a fresh engine (`.work/tmp/ctrs20.sock`) or the conformance
scratch daemon.

## #121 — Command is ignored when starting a container from testcontainers

**Fixed.** The reporter's container (`mongo:8-noble`) showed argv
`[docker-entrypoint.sh]` instead of `[docker-entrypoint.sh mongod]`;
`docker-entrypoint.sh` died at `line 4: 1: unbound variable` (the image's
`Cmd` never reached the process).

Root cause: Kiri's create path mapped `Cmd: []` (the empty array) to
`Some(vec![])` and kept it, so the image's `Cmd` was never restored.
testcontainers (docker-java `ContainerDef.java`) always serializes
`Cmd: new String[0]` — an explicit empty array, never a missing key. Moby's
merge (`daemon/commit.go: merge`) treats `len == 0` as "unset":

```go
if len(userConf.Entrypoint) == 0 {
    if len(userConf.Cmd) == 0 {
        userConf.Cmd = imageConf.Cmd
    }
    ...
}
```

so with `Cmd: []` the image's `Cmd` is restored and the container runs the
image's intended command; Kiri's `strings()` short-circuited that fallback.
The CLI path (`docker run`) sends no `Cmd` key at all and worked, which is
why the UI-run container was fine while the testcontainers one was not.

Fix: `merge_entry_cmd()` in `crates/kiri/src/daemon/api.rs` — a missing or
EMPTY Entrypoint falls back to the image's entrypoint; a missing or empty
Cmd falls back to the image's Cmd, unless an Entrypoint was given (an
explicit Entrypoint drops the image's Cmd — Docker semantics, kept). Table
driven unit test covers all nine merge combinations against moby's merge.

Verification:

- New failing-then-passing case in the VM: raw `POST /containers/create`
  with `{"Image":"ctrs20/ep-cmd","Cmd":[]}` → argv
  `[/bin/echo hello-from-image]`, exit 0 (was: argv
  `[/bin/echo]`, prints a bare newline).
- Full matrix re-verified in-VM (absent/absent, `Cmd: []`, `Cmd: [x]`,
  explicit `Entrypoint`, explicit both, `Entrypoint: []`) — all match
  moby's merge semantics.
- Regression test: `daemon::api::tests::entry_cmd_merge_matches_docker`.
- e2e: `create-empty-cmd` fixture runs the reporter's exact request shape
  against a fresh engine and asserts the logs (suite now exercises the
  empty-array shape via the API).

Not changed: an explicit `Entrypoint` (non-empty) still drops the image's
`Cmd`, matching moby. The UI run/CLI paths are unchanged.

## #134 — HTTP uploads: handle Expect and preserve chunked request boundaries

**Closed — fixed by CTRS-14, re-verified here.** All four asks:

1. interim `100 Continue` before the body is read, buffered and streamed
   paths — implemented (`read_request` takes the writer; negative control
   in the oracle: without the fix, `expect-100-continue` fails).
2. buffered chunked with trailers — the chunked decoder is shared by both
   paths; trailer bytes can no longer leak into the next request on a
   keep-alive connection (`chunked-framing` fixture fails on the old
   parser).
3. header-size bound for chunk-size lines (64 B) and trailer lines (8 KiB,
   32 fields) — enforced in `read_capped_line`/`consume_trailers`.
4. per-chunk CRLF — verified in both the buffered path and the streamed
   `Body` reader (`read_chunk_crlf`).

Plus: contradictory framing (CL+TE, mismatched/non-numeric repeated CL)
rejected pre-dispatch; identical repeated CL accepted (`conflicting-content-length`
fixture; CL+TE stricter than Docker, per the CTRS-14 disposition).

Re-verified today: `conformance/http.sh` 10/10 green with the current build
(`expect-100-continue`, `chunked-framing`, `conflicting-content-length`,
`keep-alive`, `streaming-uploads`, …). Residual, unchanged and noted in
CTRS-14: `Next::Close` may leave a padded body tail unread — legal HTTP
(`Connection: close`), flagged, not fixed.

## #50 — VM stops several times a day under load (skb_segment BUG)

**Documented known-issue, split into its two distinct halves.**

The kernel half: the guest reports `kernel BUG at net/core/skbuff.c:4854!`
in `skb_segment` → `tcp_gso_segment` → `ip_forward` on a GRO-merged
virtio-net packet. `panic=-1` reboots the guest and the daemon logs
`the VM stopped unexpectedly`. Not reproduced here (postgres+Playwright-class
load; our container↔container iperf3 hit 125–149 Gbps without a fault —
the trigger is timing-specific to GRO/GSO on the forward path). Changing
GRO/GSO blindly would trade the line-rate the CTRS-17 evidence just measured;
the kernel-side question belongs to a kernel decision, not this campaign.

The restart half is **a real defect, localized exactly — documented, not
fixed, by design:**

- Daemon boot honors the policy (Docker semantics): `Engine::load` restarts
  every `always` / `unless-stopped` container (unless manually stopped),
  exactly as Docker does when its daemon restarts. Verified live: this
  session's engine restart auto-started `buildx_buildkit_default`
  (`unless-stopped`) with no manual action.
- VM *death while the daemon lives* does not: the `Event::Lost` handler
  (`engine.rs`, the `Event::Lost` arm) marks every running container
  `Exited(255)` with `vm_stopped = true` and persists them — and never
  consults the restart policy or schedules `start_inner`. The VM reboots
  on the next request; the containers stay `Exited`. This is precisely the
  reporter's "stays Exited (255) until someone starts it by hand", and it
  is not documented anywhere else.
- The reporter's ask "restart `--restart always`/`unless-stopped`
  containers when the next VM boots" is implementable in a few lines of
  `Event::Lost` (reuse the policy scan `load` uses), but it can only be
  verified by forcing a VM death while the daemon lives — a crash-path
  experiment that CTRS-21's failure-injection harness
  (`conformance/failure.sh`) is built to run safely. An untested patch to
  the crash handler is the one thing this campaign may not ship; the fix is
  therefore tracked for CTRS-21 with the exact defect location named here.

Mitigation until then: any restart-critical container is restarted on
*daemon* restart already (restart the Kiri app/engine and it comes back —
same path as Docker's own daemon restart); a VM-death with a live daemon
still requires a manual `docker start`. The console is also discarded in
production (`apple.rs: console: None` → the virtio console attachment is
dropped), so an oops leaves no trace; console capture on unexpected VM stop
is part of the CTRS-21 route as well. If the Oops recurs, report
"guest kernel BUG at net/core/skbuff.c:4854 in skb_segment on ip_forward"
against kernel 6.18.58 — a kernel-side (or virtio-net feature-side) fix,
not a Kiri one. CTRS-04 crash parity is unaffected: the VM recovers on the
next request (sleep/wake measured 149–155 ms, CTRS-17).

## #199 — linux/amd64 containers crash: "rosetta error: unhandled auxillary vector type 29"

**Not reproduced on this host; known-issue against macOS 15.x; host-dependent,
not engine-dependent.**

- Host: macOS 27.2 (26B123). Mechanism confirmed in-tree:
  `VZLinuxRosettaDirectoryShare` + binfmt_misc `:rosetta:M::…:CF`
  (`kiri-init/src/linux/mod.rs:385`), registered when Rosetta is installed.
- Repro attempts (all pass, exit 0): `uname -m` on `linux/amd64` images
  `alpine:3.20`, `debian:bookworm-slim`, `ubuntu:24.04` — prints `x86_64`.
  The reporter's host was macOS 15.8.3 (24H241), where Rosetta appears not
  to tolerate `AT_RSEQ_ALIGN` (auxv type 29, rseq ABI v2, emitted by
  kernels ≥ 6.15).
- The guest kernel (6.18.58) is identical in both reports; the delta is
  the host's Rosetta. No Kiri-side code change can sanitize an auxv entry
  before Rosetta traps on it (binfmt `CF` executes rosetta directly on the
  amd64 image; filtering would require an injected setuid helper in the
  guest exec path — unverifiable on this host and disproportionate).

Disposition: wontfix-by-apple class (or an Apple Rosetta update) — this
host is already fixed by its macOS version. Users on macOS 15.8.3 should
upgrade macOS (this exact auxv crash is absent on 27.2); running amd64
images through another runtime remains a workaround. Retest when Apple
ships any Rosetta update (tracked alongside N-5 in the needs-owner list).
CTRS-17-note: Kiri's Rosetta share is i.e. unrelated to the vsock/NAT
finding; amd64 works where the host Rosetta cooperates.
