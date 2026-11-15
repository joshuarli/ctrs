# Campaign: native-workload benchmarking and unattended performance hillclimb

**Status:** executable steering specification, not a benchmark result. **Date:** 2026-11-14. **Target:** \`ctrs\` versus stock Docker Engine on native Linux, and Docker Desktop on native-architecture macOS. **Execution:** unattended, evidence-gated, one writer. **Scope exclusion:** absolutely no CPU emulation or cross-architecture builds.

## Mission and honest victory condition

Make ctrs **faster, more resource-efficient, and at least as correct and reliable as the best applicable stock Docker installation** across a frozen, representative matrix of *real application workflows*. Treat "better on all counts" as a demanding engineering target, **not** a marketing claim or license to cherry-pick metrics.

- Measure end-to-end user outcomes: a real app becoming healthy, a real build/test pipeline finishing with the right outputs, a database-backed service serving correct responses under load, or a working multi-service stack recovering from failure.
- Score *latency, throughput, tail latency, CPU time, total physical memory, storage amplification, startup/teardown, long-run stability, and behavioral parity*. A regression in an important dimension cannot be erased by a larger win elsewhere.
- A **strict win** is a statistically supported improvement in a specified workload/metric, not a numerical result barely outside noise. **Non-inferior** means a defensible absence of material regression, not a strict win. **Unsupported**, **failed**, and **untested** are never wins.
- The final matrix must show every cell, including Docker wins, ties, crashes, missing features, and incomplete host coverage. Claim "universal win" **only** if *every predeclared comparable cell* is a strict win and all correctness/security/reliability gates are green on every in-scope platform. Otherwise report exactly how much of the matrix ctrs dominates and why the rest is red/indeterminate.
- Do not chase performance by weakening POSIX/Docker semantics, filesystem durability, isolation, cache correctness, TLS validation, resource accounting, or the existing limits that protect against DoS.

## In scope / out of scope

**In scope**
1. **Bare-metal/native Linux amd64**: ctrs agent directly on the Linux host versus rootful, stable Docker Engine CE + its normal containerd/runc stack. Run both on the same physical host, separately, with their own sockets and clean data roots. Native Linux arm64 is an additional mandatory lane **when suitable hardware is available**.
2. **Apple Silicon macOS**: ctrs with its existing Apple Virtualization.framework Linux/arm64 guest versus current Docker Desktop running **native linux/arm64** workloads. Mac virtualization is hardware-assisted, same-ISA execution, **not emulation**. Test Docker Desktop's stable Apple Virtualization.framework + VirtioFS configuration. Add its Docker VMM configuration as a **second, independently identified competitor** when the installed version supports it; it is not permissible to benchmark only a slower legacy backend. The "best Docker" bar is the better eligible configuration for the workload, with compatibility and maturity disclosed.
3. Single-container applications, multi-container Compose, normal registry and image workflows, native multi-stage builds, local development bind mounts, persistent data, networking, and long-running services.
4. Performance **and** completion/restart/cancellation/error behavior under realistic concurrency.

**Absolutely out of scope**
- QEMU, FEX, Rosetta, binfmt_misc handlers, BuildKit cross-platform workers, multi-platform manifests *as a build target*, \`--platform\` targeting a foreign ISA, and any AMD64↔ARM64 performance comparisons. The presence of old emulation tests in this repo is irrelevant to this campaign: **do not execute, tune, or extend them**.
- Windows, WSL, Docker Desktop on Linux, nested benchmark engines in a privileged Docker container, Colima, and per-task microVM exploration.
- Microbenchmark *scores*: \`alpine true\` loops, \`/_ping\`, naked API CRUD, \`dd /dev/zero\`, \`iperf3\`, synthetic syscall counts, zero-byte image/layer benchmarks, and hand-crafted "hello world" HTTP echo servers. Old \`bench/suite.sh\`, \`bench/api.sh\`, \`bench/compare.sh\`, \`scripts/perf.py\` and \`bench/arm64-build.sh\` are **not** this campaign's scoreboard. Internal profiling may isolate a suspect code path after an application-level loss has been demonstrated, but only the application result justifies promotion.
- GPU, Kubernetes, Swarm, remote TCP API, and unsupported Docker capabilities whose implementation would overwhelm the scoped optimization campaign.

Reject a workload at preflight if the image's actual architecture does not match the physical host, the guest uses an emulator, or the test is being run through a nested engine. Record \`uname -m\`, \`docker image inspect\` architecture, ctrs-selected OCI platform, and Docker's selected platform. No "fall back and keep timing."

## Why a new suite is necessary

Read before acting:
- \`docs/architecture.md\`, \`docs/development.md\`, \`docs/security.md\`, \`docs/evidence/closeout.md\`, \`docs/evidence/net.md\`, \`docs/decisions.md\`, \`tests/e2e.sh\`, \`conformance/failure.sh\`, and \`bench/ubuntu-2026-10-26.md\`.
- The old Ubuntu comparison is **WSL 2**, not a native-host proof. Its strong lifecycle and file-I/O results are hypotheses, not the new baseline. The old report also records published-port losses versus Docker and an initially invalid stdin test; do not extrapolate its rankings.
- Linux host compilation exists, but the prior campaign explicitly parked native Linux **runtime qualification** (N-1). This is a **phase-zero blocker for Linux claims**, not permission to substitute WSL.
- The macOS closeout reported **nine unexplained silent daemon deaths**; \`conformance/watch.sh\` is the evidence surface. A crash in a long-running workload is an immediate failed gate, irrespective of speed.
- \`docs/evidence/net.md\` shows that macOS published ports sometimes use the slower **vsock relay** due to local-network privacy/routing; test the actual transport and permission state. Never bypass OS privacy controls to win a benchmark.
- \`crates/ctrs/src/daemon/builder.rs\` currently pins managed BuildKit **v0.35.0**; Docker Engine 29.9.3 bundled BuildKit **v0.34.2** (as of this document). Do not attribute a newer BuildKit's independent speed to ctrs's runtime. Use both a stock/default user-experience comparison and a controlled, matched-BuildKit comparison.
- \`crates/ctrs/src/daemon/http.rs\` is thread-per-connection; \`ports.rs\` has relay/NAT routing and explicit connection/rate limits; \`ctrs-image\` manages the registry/blob store; \`ctrs-init\` owns container lifecycle, mounts, and cgroups. These are **profiling candidates**, not authorized optimizations without workload evidence.
- Previous Mac evidence recorded substantial memory in the Virtualization.framework helper beyond daemon RSS. Count the *whole* engine footprint, including helpers, guest, managed builder, and any always-on services; do the corresponding accounting for Docker/Desktop/containerd.

Use the latest stable official Docker package **at baseline freeze**; 29.9.3 is the current Engine 29 release on 2026-11-14, not a permanently pinned "latest." Capture exact Engine, CLI, Compose, buildx, BuildKit, containerd, runc, Desktop/VMM versions, kernel, distribution, host CPU/RAM, filesystem, storage device, and ctrs commit. A new Docker release after freeze starts a **new** comparison campaign, never silently changes the control.

References: https://docs.docker.com/engine/release-notes/29/ ; https://docs.docker.com/build/builders/drivers/docker-container/ ; https://docs.docker.com/desktop/features/vmm/ .

## Deliverable: one lean, reproducible native benchmark harness

Create \`bench/native/\`, not another metrics framework. Prefer **Python 3 standard library + POSIX-ish shell + existing Docker CLI/Compose/buildx**, pinned for reproducibility; use no dashboard service, required external SaaS, Python dependency bundle, or new Rust rendering engine. A small native load driver from an existing well-maintained tool is acceptable if **pinned by digest/version** and used identically for both engines. End-to-end correctness assertions live with the workload, not in the report formatter.

Suggested file contract (implement and update it if evidence demands a simpler shape):

| Path | Responsibility |
| --- | --- |
| \`bench/native/README.md\` | Requirements, host isolation, invocation, cleanup, limitations |
| \`bench/native/cases.toml\` | Immutable scenario IDs; input digests, workloads, load/concurrency, metrics, thresholds |
| \`bench/native/assets.lock\` | Exact source commits, image digests, seed dataset checksums, tool versions |
| \`bench/native/runner.py\` | \`preflight\`, \`baseline\`, \`compare\`, \`holdout\`, \`report\`; stdlib and subprocesses |
| \`bench/native/fixtures/\` | Reproducible application stacks and ground-truth assertions |
| \`bench/native/collect.py\` | Cross-platform sampling with explicit missing/unsupported fields |
| \`bench/native/schema.json\` | Versioned, validated, machine-readable result schema |
| \`docs/evidence/native-performance.md\` | Human-readable maintained scorecard, methodology, full losing cells |

Keep all sampled traces, flamegraphs, full logs, data roots and large JSONL results under \`.work/native-perf/\` (gitignored). Commit **only** the source, lockfiles, compact summaries, source/host revision IDs, trial counts, confidence intervals, failed experiments, and checksums sufficient to audit a run. Do not publish untrusted workload secrets.

### Host and competitor contract

- Use one host per native-ISA/platform lane; never compare absolute times from different machines. Two engines do **not** run workload trials simultaneously. Balance order across paired trials: ABBA/BAAB or a seeded randomized balanced crossover; record the seed and wall-clock order.
- Use the **same** Docker CLI/Compose/buildx versions, application image digests, native platform, CPU and memory budgets, storage class/filesystem, bind source and destination, DNS upstream, port exposure, and load-generator settings. The \`ctrs\` wrapper itself invokes Docker's CLI; do not time it against a different Docker binary.
- Use dedicated, uniquely named ports, networks, volumes, socket paths, and state directories. Never call \`docker system prune\` on the user's existing daemon, alter the active Docker context, replace \`/var/run/docker.sock\`, or reuse production data. Never disable firewalls, EDR, privacy prompts, TLS verification, or seccomp for convenience.
- On Linux benchmark ctrs **natively** (not as a child of Docker); benchmark official \`dockerd\` in the same privilege mode. No benchmark-side containerization of either engine. The registry server/load generator can be independent but must be held identical and accounted for separately.
- On Mac pin the VMM backend and resource allocation and use identical native ARM64 images; disclose Apple VZ versus Docker VMM differences. When the Docker VMM beta cannot run a fixture correctly, report that exact failure and compare the working stable VZ lane; never count an incompatible Docker failure as a speed win.
- Run Docker's **normal installed configuration** against ctrs's normal configuration as the primary user-visible lane. A second **matched-resource/matched-BuildKit** lane separates engine effects from optional feature defaults. Neither lane may replace the other; pin kernel, builder, drivers, cache semantics and persistent-state choices in the report.
- Do not put shared application caches outside the timed boundary for one engine only. Freeze and declare cold/warm state *per engine*. Engine-cold (empty image/BuildKit store) is not necessarily OS page-cache-cold; label it honestly. For cached builds, assert reuse of identical layers and outputs. Use independent local registry mirrors to remove WAN noise; report WAN observations separately as descriptive, never promotion evidence.
- Power, background load, free disk, CPU frequency/thermal throttling and host updates must be sampled. Do not silently discard outliers; use predeclared invalidation criteria such as competing host load or thermal-state mismatch, then rerun both sides of the pair.

## Frozen real-workload scorecard

Implement **at least** the following workload families before tuning. These are *complete user tasks*; a request/operation inside them may be instrumented but cannot be a standalone victory metric. All source trees/datasets/images and build artifacts must be checksum-pinned. If a proposed upstream app lacks a runnable, native build, pick another representative real app and record the substitution **before** collecting the baseline.

| ID | Real user-visible transaction | Scored output and integrity check |
| --- | --- | --- |
| **W1: web stack bring-up** | \`docker compose up\` for a nontrivial API + Postgres + Redis (or cache) using named volumes, env, private network, published port and real readiness logic | Time from command to successful app HTTP health + successful DB/cache roundtrip; startup failures; persisted records after restart |
| **W2: API service under load** | Sustained mixed read/write authenticated JSON API traffic against seeded DB state; realistic response sizes/concurrency; host→published-port and container→container paths | Correct responses/state, completed requests/s, p50/p95/p99 end-user latency, errors/timeouts, host CPU-s and total memory |
| **W3: persistent transactional workload** | Real migrations + seeded Postgres tables + read/write transaction mix + checkpoint + restart + verification | End-to-end completion, p95 transactions, WAL/fsync durability, no lost/duplicated rows, disk growth and write amplification |
| **W4: worker queue** | API ingests actual tasks, cache/queue distributes them to 1/4/16 workers, workers produce checksummed outputs and retries | Time to complete a fixed batch, duplicates/loss, queue lag p95/p99, CPU time/RAM and graceful shutdown |
| **W5: monorepo edit→test loop** | Bind-mount a real TypeScript/pnpm or similar application repo; install dependencies, edit a file, rebuild affected code, run tests and watch/reload | Human-action→correct rebuilt/tested result, missed file changes, workspace integrity; host bind and named-volume cases separate |
| **W6: compiled application CI** | Real Rust (and, when practical, Python) repository checkout→dependency install→compile→unit/integration test→package; run image and verify artifact | Cold and warm CI wall time, successful tests, artifact SHA, CPU-s, disk amplification, peak/steady memory |
| **W7: native container image build** | Real multi-stage Dockerfiles for at least two languages using \`docker buildx build\`; test empty cache, warmed cache, and one-file incremental change; load/run final image | Build→usable artifact time, OCI identity/output semantics, cache-hit correctness and BuildKit lifetime costs |
| **W8: real image deployment** | Fetch and verify a pinned portfolio of realistic multi-layer app/DB images from a controlled local OCI registry, create networks/volumes and deploy | Empty-store→healthy time, digest verification, failed/cancelled pulls, reused layers, allocated bytes; fixed registry throughput |
| **W9: parallel CI and churn** | Parallel real build/test jobs (1/4/8/16 as host capacity allows), each with temporary networks, writable layers, mounts, logs and artifact export | Completed valid jobs/min, p95 job finish, container/FD/cgroup leaks, errors, cleanup latency and storage reclaimed |
| **W10: failure + recovery** | Kill/restart engine/agent/container during real web/DB/queue work, restart host service, repeat, check recovered writes and healthy responses | Recovery time, lost data, stuck resources, duplicate executions, retries and sustained p99 after recovery |
| **W11: 12–24 h mixed soak** | Continual low/medium API, queue, DB, build and teardown load with periodic bursts and real application assertions | Zero silent daemon deaths, no unbounded resident-memory/FD/disk growth, steady-state p95/p99, bounded background CPU |

The harness must also keep **held-out, never-tuned** variants: a different real application, different source tree, larger seeded dataset and an unfamiliar network/bind-mount mix. Holdout parameters and acceptance are frozen with the baseline; do not repeatedly tune against holdout failures. Workload coverage must include both stateless and stateful, I/O- and CPU-heavy, low and high concurrency. Revisit **which real applications represent those families before baseline freeze**, never afterward merely to improve a score.

### Measured state matrix

For every applicable W1–W10 case, separate:
- **First-ever/cold** (new independent data root, no engine image/layer/build cache); initialization or VM wake included as the user experiences it. Record first install/setup independently from normal launches, not hidden as a free amortized step.
- **Steady/warm** (identical pre-pulled data, hot daemon/builder); existing volumes preserved or reset as the fixture contract specifies.
- **Parallel/saturated** at 1/4/8/16 jobs or the highest safe equal-capacity setting; list excluded levels.
- **Host filesystem versus engine-managed named volume** when the workload depends on filesystem performance; never pool those results.

Do not manufacture a "cold" condition by deleting the shared operating-system page cache for just one competitor.

### Required measurements per completed trial

- Wall time to *verified successful task completion*; p50/p95/p99 for HTTP/queue/transaction **under a fixed valid load**, completed correct transactions/second, throughput to a defined saturation/error SLO, timeout/error rates.
- Total host **CPU-seconds** spent by the engine ecosystem plus workload and its required guest/VM/containerd/shims, and incremental per-task CPU-seconds after subtracting the measured idle baseline. Do not score raw system-call counts.
- Peak and idle **memory footprint of the entire engine** (daemon, guest/VM helper, containerd, shims, managed BuildKit), plus peak application footprint separately. On Linux use PSS/cgroup where supported; on macOS use physical footprint/VM allocation and report shared-memory ambiguity instead of summing double-counted RSS.
- Persistent disk bytes allocated, temporary peak, image/layer duplication, cleanup reclamation, write amplification where measurable, and verified durability after restart.
- Idle CPU, number of leaked sockets/FDs/cgroups, startup and shutdown success, unexpected exit count, resource pressure and optional joules/task if equivalent platform counters are available.
- For Docker API/Compose/buildx compatibility: response/exit codes, logs, signal handling, healthchecks, mounts/permissions, network isolation, volume and cache content, cancellation/retry behavior. A fast error is a **failed task**, not a low latency sample.

Store one JSONL record per trial with schema version, host ID, engine config, source SHA, workload ID, cache state, native architecture, order seed, complete timestamps, inputs/digests, success and correctness hashes, raw latency distribution or histogram, resource trace references, and validation errors. Never convert a missing observation to zero.

## Statistical decision procedure (freeze before any optimization)

1. **Pilot** three paired trials per state to detect broken fixtures, glaring regressions and natural variability. Pilot numbers **cannot** be promoted as wins.
2. **Baseline** a minimum of **10 valid paired repetitions** per scored case/state, with randomized/ABBA order and enough work per trial to include realistic startup, service warmup and workload saturation. For expensive multi-hour or soak cases, use predeclared smaller replication and explicitly lower confidence; never call them statistically decisive.
3. Summarize paired *ratios* for ctrs/Docker (less is better for latency/resource, inverse for throughput), median effect, p95/p99 where applicable, and a **bootstrap 95% confidence interval over whole paired trials**. Preserve each observed trial, including losses.
4. A measured cell is **strict win** only if the complete 95% confidence interval clears a predeclared material threshold: at least **5%** better for latency/throughput/CPU/RAM/disk, or a more meaningful workload-specific SLO improvement defined before baseline. **Statistical tie / indeterminate** if the evidence cannot distinguish them. A **loss** is a reliably worse result outside a **3% non-inferiority margin**, or any correctness/security/reliability failure. Small apparent advantages inside noise are not wins.
5. Freeze a balanced rollup for prioritization only: W1–W10 have **equal family weight**, first aggregate within a family across its predeclared states, then use a geometric mean of **valid** normalized throughput/latency improvements. **Never** use that rollup to hide a losing cell or claim full coverage. Report metric-family wins/losses next to the rollup.
6. End-to-end performance promotion requires: (a) affected-workload integrity gates pass, (b) full relevant regression and conformance suites pass, (c) ≥5% statistically credible improvement in a *real task* **or** a previously failing semantics/reliability gate is corrected with no material performance regression, (d) no statistically credible >3% deterioration in any predeclared critical metric, (e) no newly unsupported/failed case, (f) an independent holdout check at milestone/final gates. A failure of any hard gate means reject/revert, regardless of mean speed.
7. A platform without sufficient measurements is **unqualified**, not green. Do not silently use macOS evidence to justify a Linux optimization or vice versa. Baseline versus Docker version and VMM variant remain attached to the metric forever.

Avoid sequential peeking: tune with a designated development set and keep a frozen independent confirmation/holdout set for promotion gates. If the 95% interval overlaps the margin, gather a predeclared additional paired batch or declare "inconclusive"; do not rerun until favorable.

## Mandatory hard gates before judging performance

**G0 — host, isolation, environment.** Verify physical/native architecture; no emulator; suitable host load; qualified native Linux root/control paths; locked Docker versions and VMM settings; dedicated sockets/state directories; no shared customer volumes; stable local registry. The preflight must *fail closed*. On an unavailable bare-metal Linux machine, continue coding the harness and Mac lane, then mark Linux **needs native host**. Never substitute WSL or a privileged container and call it qualified.

**G1 — parity and data correctness.** \`cargo check --workspace\`, \`cargo test --workspace\`, \`conformance/smoke.sh\`, \`conformance/run.sh\`, \`tests/e2e.sh\`, \`conformance/failure.sh\`, \`conformance/isolation.sh\`, native \`tests/linux-host.sh\` where applicable, and focused IPv6/security tests on the host that supports them. Do not treat a "plan runner" printing steps as a successful executed suite. Native host and macOS proof are independent. Do not weaken a parity assertion because Docker passed and ctrs failed.

**G2 — long-run reliability.** Real workload W10/W11, not ping, must survive planned daemon restarts, SIGTERM, container crashes, builder cancellation, host disk-pressure recovery (in isolated scratch), and concurrency; zero unexplained daemon deaths for qualified runs. The nine historical unexplained macOS deaths remain an explicit risk until a reproducible closeout verifies they are gone, not merely unobserved for one minute.

**G3 — security and cleanup.** Socket permissions, secret-bearing state files, image/archive extraction budgets, durable layer/index writes, namespace/cgroup isolation, seccomp, firewall rule ownership, no host bind escape, no orphaned helper/VM, correct cleanup after failure. Security controls may never be disabled as an optimization. Fix a discovered gate regression before continuing measurement.

**G4 — externally reproducible win.** Reproduce a passing candidate after a fresh binary build and a cold scratch root; compare against the frozen stock Docker version with the same workload and native ISA on the same host. Repeat on all available in-scope host lanes. An optimization with only a local one-off benchmark is not accepted.

## Unattended sequence and scope of authority

### Phase A: groundwork / stop obvious false claims

1. Inspect the implementation, benchmark scripts, conformance tests and evidence docs above. Inventory every supported Docker API/app feature required by W1–W11. Reject unsupported cases as **coverage gaps**, not benchmark successes.
2. Qualify an actual native Linux runtime before making Linux performance claims; on macOS run current conformance and record whether the previously documented daemon deaths recur. Record Docker VMM availability and macOS Local Network permission/state without modifying it.
3. Select **pinned real applications** for W1–W11, construct fixtures, seed data and an independent local OCI registry. Implement the clean root/socket isolation, native architecture guard, exact-output assertions, dual competitor configuration, snapshot/cleanup and raw JSONL reporter.
4. Run the preflight and a **no-op control** (same engine/config against itself in balanced order) to establish harness noise. The no-op control is a methodology validation, not a performance workload/score. Refuse to score unstable host conditions.

**Deliverable:** benchmark harness, frozen lockfiles, \`README\`, native preflight transcript, valid/blocked lane register.

### Phase B: an honest Docker baseline

1. Run the whole W1–W10 matrix on current ctrs and the **best eligible stock Docker** configuration, plus two Docker Desktop backends on Mac when supported. Capture the actual native ISA and all config versions.
2. Repeat selected build workloads using identical pinned BuildKit image/driver on both engines as an **attribution control**. Report the stock/default experience separately; account for ctrs's managed builder idle/startup lifecycle. Do not blame or credit the container engine for BuildKit's own algorithm without isolation.
3. Run W11 once at an appropriate duration on both engines. Finalize which cells are slow, which fail correctness, which leak, and which are unqualified. Put the full baseline matrix under \`docs/evidence/native-performance.md\`.

**Deliverable:** baseline plus Pareto frontier of credible bottlenecks, not a cherry-picked speed leaderboard.

### Phase C: hillclimb — one bottleneck, one hypothesis, one proven change

Select the **highest-impact losing real-workload cell**: severity × frequency × ability to improve without weakening a hard gate. For each iteration:

1. Reproduce the loss in the actual fixture and rule out load-generator saturation, cache/dataset drift, platform mismatch, version drift and known macOS network-permission effects.
2. Profile the *real workload while it runs*: Linux \`perf\`/eBPF or equivalent sampling; macOS Instruments/host memory tools and guest traces where supported; filesystem and network counters. Profiling is diagnostic; **no substitute microbenchmark scoreboard**.
3. Form exactly one falsifiable bottleneck hypothesis and choose the **smallest** code change (one subsystem). Write its expected observable W-ID/metric improvement and suspected side effects into the experiment log.
4. Experiment in an isolated worktree, using a reproducible release build and dedicated engine data root. Execute the affected workload against **both ctrs-before and ctrs-after** on the same host; compare to the already pinned Docker reference. Then run correctness, targeted regressions, and the complete promoted scorecard as required by the statistical policy.
5. If green and materially better, commit to \`main\` (Conventional Commit) and record the before/after matrix and experiment ID. If it fails, **revert the experiment**, record the failure and proceed to the next hypothesis. Do not pile failed speculative "optimizations" into main.
6. After each accepted slice, rebaseline ctrs HEAD and choose the next worst credible cell. Do not switch the Docker control mid-loop. A gate-fixing correctness or security patch may land without a performance win if it causes no material performance regression and has a reproduced test.

**Hypothesis queue, not permission to rewrite prematurely:**
- **Mac app-facing networking:** \`daemon/ports.rs\`, guest relay, actual VZ NAT availability, long-tail connections and backpressure; preserve per-peer/session DoS bounds and OS permission semantics.
- **Linux published ports and DNS:** loopback proxy versus kernel forwarding, connection setup under W2/W9, guest/host DNS relays, networking state cleanup; preserve firewall ownership/isolation.
- **Dev-loop bind mounts:** VZ virtiofs path, metadata round trips, layer/overlay lookup, file-watch correctness under W5; never "optimize" by stale-caching edits.
- **BuildKit lifecycle:** builder first-start, image import/export, cache reuse, context transfer, idle lifetime, OCI layer storage; distinguish external BuildKit work from ctrs work in W6/W7.
- **Image distribution/unpack:** registry client, dedup, compression/checksum paths, tar extraction, host↔guest stream, fsync batching where safe; preserve digest verification/durable writes in W8.
- **Parallelism/control plane:** thread-per-connection \`daemon/http.rs\`, locks, per-container state serialization, guest \`poll()\` scheduling, cgroup/exec supervision under W9 and W11. Prefer bounded concurrency proven by the workload; no cargo-cult async runtime.
- **Memory and cold/wake:** VZ helper/guest balloon, idle image/builder caches, resident layers and orphan helpers; optimize **total physical footprint**, not just daemon RSS.
- **Real recovery:** eliminate lost/stdin/log/port operations, unexpected XPC/daemon deaths, stale resources and stuck creates from W10/W11 before performance work resumes.

Keep footprint/complexity small. Prefer deleting unnecessary copies, redundant round trips, incorrect waits or duplication over speculative heavy new subsystems. No mandatory containerd, runc, Tokio, Hyper, desktop UI, remote engine or altered data formats.

### Phase D: adversarial remeasurement and closeout

- Re-run all core native workload cases against frozen Docker and the pre-campaign ctrs baseline **on fresh scratch roots**, with the candidate binary rebuilt from clean source. Execute the **held-out real app/dataset** exactly once for confirmation, or mark inconclusive and stop tuning it.
- Validate app outputs, transaction logs, file-watch behavior, persistent volumes and service restart semantics. Soak W11. Repeat on each available qualified native host. A Mac-only success does not close Linux.
- Write a **loss-first** report: host + versions, exact fixtures, commands, matrix of strict wins/ties/losses/unsupported, weighted aggregate, tail latencies, CPU-s, total physical memory, disk, reliability, BuildKit-controlled findings, applied commits, rejected experiments, and unresolved blocking features. Make the row labels and denominators explicit.
- Stop when all applicable cases achieve **measured strict dominance** and G0–G4 pass, **or** when no credible improvement remains after three failed/neutral hypotheses per remaining bottleneck, 30 total candidate changes, a hard environment blocker, or a correctness/security/reliability gate that cannot be resolved in scope. **Stop means report honestly**, not quietly declare victory.
- No tags, releases, remote pushes of user data, mass \`prune\`, Docker daemon reconfiguration outside isolated scratch, workstation sleep, or production host changes. Respect pre-existing Docker resources and user projects. Unattended permission applies to *in-repo code/bench source and verified commits*, not destructive host actions.

## Steering prompt for the execution agent

> You are the sole performance engineer for \`joshuarli/ctrs\`. Read \`AGENTS.md\` and this entire campaign, especially native architecture exclusion, benchmark fairness, hard gates and the no-microbenchmark rule. Build a lean, fully reproducible benchmark suite for real native-host Docker workloads. Qualify Linux natively when a real native Linux host is available; on Apple Silicon use only native ARM64 containers inside the existing hardware-virtualized Linux guest. Compare against pinned, current Docker Engine CE on Linux and current Docker Desktop stable Apple VZ and, when eligible, Docker VMM on Mac. Never use FEX, QEMU, Rosetta, binfmt or cross-architecture builds. Run the full app/CI/Compose/database/queue/bind-mount/image/failure matrix with correctness hashes and full engine-ecosystem resource accounting. Publish every loss and limitation, including Docker wins. Profile actual losing workloads, hypothesize narrowly, optimize one subsystem, repeat valid paired A/B runs, and land only genuinely beneficial, fully tested slices on main. Keep iterating unattended until strict workload dominance or an explicit stop condition; leave a rigorous handoff, not invented benchmark results. You must not use \`alpine true\`, empty HTTP, \`dd\`, \`iperf\`, \`/_ping\`, or other microbenchmarks as the optimization score. If hardware, OS permissions or a Docker backend are unavailable, deliver the executable harness and mark the affected lane blocked; never substitute an emulator or claim a win.

## Initial acceptance checklist (for the first executor session)

- [ ] Read current repository and prior evidence; identify Linux runtime and Mac daemon-death blockers.
- [ ] Create pinned, real application fixtures with deterministic correctness assertions for W1–W11.
- [ ] Implement fail-closed native-ISA and privileged-nested-engine rejection, isolated cleanup, and competitor/version lock.
- [ ] Get a clean \`cargo test --workspace\` plus each executable applicable parity suite; distinguish a plan from an actual run.
- [ ] Produce a real Docker-versus-ctrs baseline **on whichever native hosts are truly available**, with valid trials and all losing/unsupported cells.
- [ ] Execute a full, evidence-based optimization/promotion iteration only after baseline validity.
- [ ] Commit compact results and update the loss-first scorecard; make unavailable lanes explicit.
