# Linux HTTPie first use and transient ownership, 2026-11-22

Native amd64 Linux, CPUs **0–7**, Ubuntu 22.04.5, kernel
`6.8.0-1060-aws`, cgroup v2/systemd. Frozen host Docker 29.9.2
(`0367cbe`), dockerd/containerd PIDs 599/487, unrestarted. Baseline source
`75491e74607812005df77d5b14c18837aaffb8b1`; candidate source is that tree
plus preserved `h3.patch`. **H3 qualifies against baseline ctrs; it does not
beat Docker or close any macOS gate.** Coverage, parity, leadership,
reliability and reproducibility macOS gates remain open and unchanged.

## Inputs and state

Only first use is measured: the original W7
`docker run --rm --pull=never IMAGE http --version`, with equivalent explicit
`--cpuset-cpus 0-7`. Clients and all live engine processes have affinity 0–7.
Every trial requires exit 0, exact `3.2.4`, and the original incremental note.

Historical HTTPie config
`b98258af910b0ee8c254a665ec75293dda528bf44327cff8d23b2298bd31b6b5`
was reconstructed using retained source and cached Docker build vertices.
There was no new dependency resolution. The common saved archive is
`dbb2dac4a6d6e8f90f8ede8395038592fc3f706ec2e1a5025de1724cbb29bfde`;
both engines have identical config/rootfs input bytes. Docker's wrapper image
ID is `b5d73c6930d6ee20effd5aa62e5b1bd9efd04ff85b89db505bec13eebca60b06`.
See `image-freeze.json`, image inspections and preparation logs.

Build/load/preparation are **outside** first use. No uncached-build timing or
dependency-freeze claim is made. Docker already materializes these layers
during preparation; ctrs does it on first create. Before each native trial,
stop the owned daemon, remove only the three HTTPie-specific runtime layer
directories/markers by their compressed blob digests, restart, warm the
shared Python/API base and verify the three remain absent. Metadata/content
stay loaded; do not delete Docker layers or evict global page cache. This
models the pilot's preceding W2/base use, not a completely cold machine.
No work is moved from first use into preparation by the candidate.

## Phase evidence

Daemon event timestamps plus `strace -ff -ttt -T` of daemon/agent and
dockerd/containerd descendants resolve actual installs, durability barriers,
overlay mounts, API request reception, execve and the application's version
write. Corrected final traces are `profiles-v3/6-ctrs-strace` (B),
`7-dockerd-strace` (D), `10-ctrs-strace` (C); `phase-analysis.json` contains
raw boundaries. **Trace durations are perturbed, not cohort scores.**

| Traced boundary, ms | B | D | C |
| --- | ---: | ---: | ---: |
| Image materialization, first staged write → last durable layer | 2804.882 | 0 (already prepared) | 3323.213 |
| Observed rootfs overlay mount syscalls | 0.164 | 1.920 | 0.162 |
| Create residual, excluding materialization and pre-create overlay calls | 7.542 | 70.141 | 12.870 |
| Start request → execve entry | 23.846 | 234.353 | 29.946 |
| Process execve syscall | 0.970 | 0.604 | 0.187 |
| Interpreter/application init, execve return → version write | 341.019 | 367.090 | 419.331 |

These are **nested boundaries, not additive exclusive buckets**. Rootfs
metadata/namespace setup outside the observed overlay calls remains inside
create/start; a complete exclusive rootfs-preparation duration is not
isolated. Docker's start request header spans two reads. App init includes
the Python interpreter. Tracing magnifies file extraction, and even reverses
the candidate's apparent materialization result; do not score that reversal.

Profiler-off daemon lifecycle controls are more representative:

| Control, seconds | B | D | C |
| --- | ---: | ---: | ---: |
| Client → create event | 0.524 | 0.040 | 0.333 |
| Create → start event | 0.024 | 0.079 | 0.013 |
| Start → die event | 0.216 | 0.274 | 0.229 |
| Whole first use | 0.766 | 0.410 | 0.578 |

The dominant ctrs-specific phase is materialization before create, not
HTTPie's Python initialization. Reachable chain:
`Engine::create → ensure_layers → push_layer → send_layer → call`, waiting
for each `LayerStored`; the agent already has four install workers and FIFO
replies. Real cold traces show all three installs. A warm negative control
has no installs and fast create, disproving a cold-cache interpretation of
that control. The large package layer accounts for most extraction; its
worker performs 6,146 writes, while its traced syncfs is only tens of ms.
Inflater dispatch is verified by the frozen gzip media type and Cargo feature
tree; stack-level inflater CPU attribution is not established.

Two profiler-helper mistakes were caught and retained: the first reset used
diff IDs rather than compressed runtime digests; later supplemental nominal
candidate traces used a Python default argument bound to the baseline binary.
Those cells are not candidate phase evidence. Final cells pass the selected
binary explicitly and assert its live SHA. **Cohorts always passed the binary
explicitly and asserted live hashes; their state/identity checks were not
affected.** Original records/logs remain unchanged.

## Three predeclared attempts

Before each edit/cohort, `hypothesis-N.md` declared the mechanism and fixed
10-round schedule: even B,C,D, odd D,C,B. No profiler, extensions, replacements,
speed exclusions or relaxed thresholds. All use the same archive, baseline,
Docker, periodic 0.2s strict sampler and before/after host admission gates.
Primary is median paired first-use completion C/B; bootstrap95%, 2,000
whole-pair draws, seed 7. Win requires upper bound ≤0.95 and ten complete,
correct/resource-valid/admitted B/C pairs. Docker is frozen context, not a
parity prerequisite. Do not pool attempts or reinterpret this as p99.

1. **H1:** queue native streamed installs before waiting; preserve dedup,
   layer lock, four-worker cap, FIFO barrier, durability and existing fallback.
   Neutral; product reverted.
2. **H2:** switch the existing flate2 API from miniz_oxide to zlib-rs 0.6.8.
   Cargo tree verified the old backend; the alternative that zlib-rs was
   already active was disproved. Neutral; backend selection reverted.
3. **H3:** explicitly declared **two-component** materialization candidate:
   combine H1's bounded overlap with H2's faster decoder. Neither component
   is independently qualified. Final trace workers overlap; create follows
   the last durable completion. This was the final attempt.

zlib-rs is already pinned in Cargo.lock, Zlib licensed, maintained by the
Trifecta Tech Foundation project and supported directly by flate2. No new
system/C dependency, format, wire or runtime configuration is introduced.
Features unify with the host when host/agent build together; the agent gzip
backend also affects guest builds, whose macOS performance is unqualified.
Binary sizes: host 11,085,984 → 11,110,992 bytes (+0.226%); agent
4,203,336 → 4,228,480 (+0.598%). No build-speed claim.

Median [Q1,Q3], seconds; intervals describe the paired median ratio:

| Attempt | B | C | Frozen D | C/B [95% CI] | C/D [95% CI] | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| H1 | .635 [.629,.673] | .616 [.598,.644] | .440 [.426,.457] | .944 [.824,1.007] | 1.415 [1.366,1.479] | revert |
| H2 | .629 [.623,.640] | .533 [.525,.684] | .435 [.423,.457] | .848 [.835,.990] | 1.236 [1.176,1.631] | revert |
| H3 | .649 [.630,.702] | .492 [.489,.496] | .428 [.421,.498] | **.773 [.707,.786]** | 1.164 [1.036,1.180] | **promote** |

**90/90 correct, resource-valid and host-admitted; 10/10 B/C and C/D resource
pairs per attempt.** Retain slow outliers, including baseline .988s in H3.
H3 improves paired first use by 22.7%, but remains about 16% slower than Docker
by the paired median. No broader workflow or build win is implied.

## Resources and correctness

CPU below is first-use sampled lower-bound seconds, not complete exited-scope
CPU. Derived analysis explicitly marks `cpu_counters_complete: false` and
`is_sampled_lower_bound: true`; old records are not rewritten. All periodic
and phase ownership checks remain strict. Memory is sampled coincident
anon+kernel MiB, excluding file cache; memory.current remains raw/secondary.
Active samples lie wholly inside the operation; all ten trials per cell have
them. Increments are each trial's active peak/retained value minus its own
idle value, then summarized—not differences between aggregate medians.

| Attempt/variant | CPU s | Idle | Active peak | Active increment | Retained increment |
| --- | ---: | ---: | ---: | ---: | ---: |
| H1 B / C / D | .562 / .568 / .211 | 1.46 / 1.46 / 781.87 | 34.18 / 38.51 / 796.30 | 32.71 / 37.05 / 12.89 | 6.35 / 6.39 / 2.78 |
| H2 B / C / D | .553 / .454 / .204 | 1.47 / 1.47 / 777.15 | 36.65 / 18.93 / 790.42 | 35.20 / 17.46 / 12.31 | 6.39 / 6.34 / 1.45 |
| H3 B / C / D | .554 / .445 / .248 | 1.46 / 1.46 / 778.40 | 33.23 / 24.16 / 797.93 | 31.77 / 22.70 / 17.03 | 6.36 / 6.34 / 2.43 |

These short sampled peaks can miss maxima; Docker includes preexisting idle
service/kernel state. They do not establish broad memory efficiency.

Printed checks (full logs preserved):

```text
H1 host daemon: 155 passed; 0 failed; 2 ignored
H2 layer tests as root: 13 passed; 0 failed
H3 final host daemon: 155 passed; 0 failed; 2 ignored
H1/H2/H3 e2e subset, each: 135 passed, 0 failed, 17 skipped
```

Final promotion additionally restores three deferred-reply tests for independent
out-of-order results, an already-completed reply and an empty disconnected
channel; only cfg(test) code changes after the measured binary freeze.
The unchanged H2/H3 agent is byte-identical. The layer tests cover normal and
empty gzip archives, concatenated members, truncated-input cleanup, whiteouts,
xattrs and traversal. E2e extracts unchanged source assertions for run/config,
create/lifecycle/exec, volumes/binds, cp, save/load and diff/export/commit.
Seventeen skips are macOS bind-event cases. These are not full-e2e results.

## Section 5: five historical ownership failures

`historical-five.json` preserves the exact five source lines with hashes;
their resource-invalid verdicts are unchanged. Adjacent original samples,
member PIDs/start ticks and inode continuity are in
`historical-transition-context.json`. No executor/runc proof or weaker
ownership rule is introduced.

| Historical trial | Bad scope prefix | Adjacent sampled main PID / start ticks |
| --- | --- | --- |
| W13 pair 2 | 3c95faf5 | 439367 / 1088795 |
| W13 pair 4 | f65abf9c | 442733 / 1100562 |
| W13 pair 6 | 4805d4f6 | 445971 / 1112174 |
| W2 H1 pair 1 | b756e311 | 687711 / 12320356 |
| W2 H2 pair 0 | ef95bcb3 | 734738 / 12522826 |

All five errors come from the **nonempty unowned-process guard**, not the
empty-retired-cgroup proof branch. W13 pair 6 and both W2 scopes are verified
again with the same inode/main-process start ticks after the invalid sample.
This disproves a blanket explanation that these were simply unknown retired
empty groups. Failed samples did not save their offending member's /proc
reads; **the exact five per-event parent transitions cannot be reconstructed**.

A bounded diagnostic logs the actual collector's ordered stat/cgroup/cmdline
reads and exception locals without changing its decisions. Sixty short owned
container lifecycles yielded two failures: a live `runc:[2:INIT]` child whose
intermediate runc parent is already Z, and a same-start-tick child reparenting
from runc to shim during the stat sandwich. Observe checks start ticks but
does not stabilize PPID; Z parents are excluded. The resulting unowned member
invalidates the whole sample despite a verified shim one hop farther away.

To check reachability in the **reported workload**, not just container boot,
one frozen W2 run retained 50,000 ops/concurrency 8 and completed correctly.
Its existing DB scope `9e8af414...` failed on PID **839735**, start ticks
**12962863**, parent **839721**. The parent was a zombie runc (ticks 12962862),
absent from the snapshot/owned set; fresh reads link it to verified shim
**838780** in containerd.service. The child remained live in that DB scope.
The DB's compose healthcheck invokes `pg_isready` every 2s; a healthcheck/exec
startup ancestry gap is reachable while W2 runs. The child's exact shell
arguments were not captured, so that specific command attribution remains
inferred rather than verified. W13 likewise invokes docker exec for its
long-lived transfer helpers; an exact-input 1GiB × 3 diagnostic passed
correctness without reproducing a failure. No diagnostic timing is scored.

Thus **non-atomic ancestry discovery across short-lived exec/reparenting is
verified live, including W2**, and is a supported explanation for the five
historical failures, not a proven individual attribution of all five. Their
missing failing-instant PID data is the discriminator that cannot be recovered.
Strict rejection stays; no historical invalid is converted into a pass.
The aborted W2 diagnostic (duration=0 rejected by the client) is retained;
its corrected run uses the frozen pinned stack and positive duration argument.

## Preservation and replay

Durable root: `/home/ubuntu/ctrs-evidence/linux-httpie-20261122/`.
Manifest: [linux-httpie-2026-11-22.sha256](linux-httpie-2026-11-22.sha256).
It includes binaries, common HTTPie archive/context, source bundle/patches,
declarations, schedules/freezes, all 90 records, native resource traces,
profiles (including rejected controls), diagnostic transitions, analyses,
commands and verification logs. The older checkpoint/W2 roots remain intact.

```sh
scp -r ubuntu@HOST:/home/ubuntu/ctrs-evidence/linux-httpie-20261122 ./linux-httpie-20261122
cd linux-httpie-20261122
sha256sum -c /path/to/ctrs/docs/evidence/linux-httpie-2026-11-22.sha256
```

Restore source from `source.bundle` at baseline SHA above, then apply
`promoted-source.patch` (the measured `h3.patch` plus the restored reply tests);
or use the landed source. Restore the frozen Linux portfolio via
the checkpoint's documented `--linux-archive` path, load `httpie.tar` into
both engines untimed, and copy the preserved baseline/candidate binaries into
the controller paths. No lock regeneration, image rebuild or Docker layer
reset is needed. `profile.py`, `cohort.py h3`, `analyze.py h3`,
`analyze-phases.py` and the ownership helpers preserve commands/logic.
For a new run, change copied helpers' ROOT/E/run IDs and use a new evidence
directory; the controller refuses to overwrite existing records. Any separate
Docker daemon must follow the integrated-runtime private netns/containerd
isolation instructions, never adopt default sockets.

The performance gate's status subcommand has a GNU awk `load` identifier
error; its `-1` admission mode worked before and after every scored trial.
No global tool/environment change was made. Final cleanup, rebase/runtime
identity audit and integration checks are preserved in the final audit logs.

### Final integration

Rebased onto `ea35cab849d74e289fc8a5b71778673553be796c`. Incoming changes
do not alter crates, e2e assertions or the Linux sampler/adapter; runner
changes add W3 metadata only. Measured runtime inputs are unchanged. Final
host daemon tests include the three restored reply cases:

```text
test result: ok. 155 passed; 0 failed; 2 ignored
Ran 489 tests
OK (skipped=15)
FIVE_OLD_RECEIPTS_STILL_IDENTICAL_TO_ORIGINAL_SOURCE_LINES
WORKLOAD_DIAGNOSTICS [('create', 2), ('W2', 1), ('W13', 0)]
HTTPIE_FINAL_AUDIT_OK: 90 correct/resource-valid/admitted trials; exact live binaries, affinities, frozen image, copied traces; three declared decisions; final tests
NO_OWNED_PROCESS_CGROUP_FIREWALL_LINK_OR_BENCHMARK_CONTAINER_RESIDUE; DOCKER_PIDS_UNCHANGED
```

The first post-rebase offline run failed because sudo preparation owned the
two scratch result-parent directories. Correcting ownership of those two
owned directories, without changing records or tests, resolved it. Both logs
are retained. All scored trials and the original five receipts stay untouched.
