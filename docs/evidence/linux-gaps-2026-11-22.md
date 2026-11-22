# Linux losing-cell follow-ups, 2026-11-22

Follow-up to the [native Linux survey](linux-survey-2026-11-22.md), using a
fresh worktree at c1df6cd, the same frozen H3 runtime/images, host Docker and
CPUs 0–7. No product source change or engine candidate was made. These are
bounded causal controls, not a qualification cohort or pooled survey update.

Durable evidence: `/home/ubuntu/ctrs-evidence/linux-gaps-20261122/`; manifest:
`linux-gaps-2026-11-22.sha256`. Source bundle, schedules/freezes, executable
identities, scripts, all records/traces, full edit timestamps, perf data,
process/mount/budget snapshots and analysis are retained. Results were moved
atomically from disposable `.work` to the durable root; a compatibility symlink
keeps original trace paths resolvable. Existing frozen image/binary artifacts
remain in the survey evidence root and its committed manifest.

# W5 observer/cadence result

The matched 60-edit diagnostic has normal-observer bind medians C 0.172540 s,
D 0.106235 s; volume C 0.152945 s, D 0.207710 s. With only boundary contexts
removed, the same periodic sampler, same frozen app and 60 exact alternating
edits per mount give bind C 0.151253 s, D 0.150781 s; volume C 0.151163 s,
D 0.150955 s. No output, persistent-process or mount oracle was relaxed.
This is one pair per mode, diagnostic only, not an engine qualification or
replacement of the original pilot.

Reachability: `watch_loop.run_mode` enters `resource_phase` before starting
each edit timer, and exits it after receiving the streamed exact CLI-tested
output. The existing source calls `esbuild.context(...).watch()`. Its frozen
esbuild v0.25.3 backend is a polling watcher, not an inotify backend; the
matching release source is preserved as `esbuild-v0.25.3-watcher.go` (100 ms
sleep and dirty-path rebuild loop). No ctrs inotify optimization could reach
that backend. The release-source-to-binary correspondence is inferred from
the frozen identical official package/runtime identities, not a Go rebuild.

Actual boundary timings show median entry/exit C 0.232/0.807 ms versus D
22.231/22.600 ms. Actual inter-edit gaps are C 1.119 ms versus D 47.865 ms
for bind, while boundary-free gaps are 0.082/0.072 ms. Thus substantial Docker
observer work is outside the edit timer but changes the cadence at which
edits reach an already-running polling app. The boundary-free contrast tries
to disprove that explanation: the engine gap vanishes instead of persisting.
Volume transport continues to include ordinary exec work, as the contract
requires; it is not subtracted from measurements.

Conclusion: the pilot's measured host-observed latency remains true for its
observer cadence, but is not evidence of a slower native filesystem watcher.
The controls support an observer/cadence effect; no claim is made to identify
every timer/kernel scheduling contribution. There is no verified reachable
engine-specific cause warranting a product change. Do not add a synthetic
engine delay to game alignment with this polling workload. No engine candidate
or qualification cohort is justified, and no performance improvement is
claimed. Original normal five-edit diagnostics and the documented parameter
mistake remain preserved separately.

## W12 profile, attempted disproofs and decision

Two new alternating normal-observer pairs per layout remain independent from
the original three-pair survey. All eight are correct, host-admitted and strict
resource-valid. The following ranges are two actual paired ratios, not a CI
or qualification. They explicitly include the 22.073s native volume install.

| W12 control phase | ctrs median s | Docker median s | paired C/D range |
|---|---:|---:|---:|
| full-bind install_seconds | 13.4720 | 15.0439 | 0.832–0.965 |
| full-bind build_seconds | 15.4762 | 15.5274 | 0.968–1.031 |
| full-bind typecheck_seconds | 4.3380 | 4.6269 | 0.709–1.257 |
| full-bind test_discovery_seconds | 0.6917 | 0.6185 | 0.822–1.423 |
| full-bind warm_rebuild_seconds | 12.4862 | 11.1850 | 1.094–1.138 |
| full-bind multi_file_change_seconds | 15.9201 | 16.3885 | 0.891–1.066 |
| full-bind branch_switch_seconds | 16.2662 | 18.0852 | 0.875–0.929 |
| full-bind install_verification_seconds | 0.5022 | 0.7258 | 0.599–0.824 |
| full-bind workflow_seconds | 79.1528 | 82.2011 | 0.944–0.984 |
| all-volume install_seconds | 16.7580 | 13.3136 | 0.815–1.753 |
| all-volume build_seconds | 14.8812 | 14.8040 | 0.976–1.037 |
| all-volume typecheck_seconds | 3.9918 | 4.2386 | 0.924–0.963 |
| all-volume test_discovery_seconds | 0.6456 | 0.6323 | 1.008–1.035 |
| all-volume warm_rebuild_seconds | 12.0440 | 12.7870 | 0.857–1.049 |
| all-volume multi_file_change_seconds | 17.0665 | 16.1070 | 1.004–1.119 |
| all-volume branch_switch_seconds | 16.1744 | 16.6229 | 0.958–0.988 |
| all-volume install_verification_seconds | 0.5503 | 0.6468 | 0.827–0.882 |
| all-volume workflow_seconds | 82.1118 | 79.1522 | 0.993–1.079 |


Four separately instrumented complete workflows are also correct, admitted
and strict resource-valid, but their perturbed times are not scored or pooled.
The inherited daemon/agent or dockerd/containerd perf trees include actual
Node descendants. All four data files report zero lost samples. Aggregated
CPU shares (rounded; not exclusive wall time):

| Layout / engine | Node/npm userspace % | Node/npm kernel % | Runtime tree own processes % |
|---|---:|---:|---:|
| full-bind / ctrs | 90.83 | 8.73 | 0.01 |
| full-bind / Docker | 90.83 | 8.03 | 1.06 |
| all-volume / ctrs | 90.54 | 8.43 | 0.75 |
| all-volume / Docker | 89.69 | 8.42 | 1.81 |

Three proposed boundaries were checked before inventing an engine candidate:

1. **A fixed native materialization/daemon penalty explains install and warm
   rebuild losses.** The frozen image is prepared before the install/edit
   operations; the actual CPU samples overwhelmingly execute Node/npm, not
   the runtime. Full-bind install reverses to native wins in both new normal
   pairs (0.832–0.965); full workflow also reverses (0.944–0.984). Warm-rebuild
   still loses in both normal full-bind pairs, but not consistently in the
   separate instrumented control. This disproves a stable fixed daemon-cost
   explanation, not every possible kernel or filesystem contribution.
2. **Different effective CPU/memory ceilings or priorities throttle native
   Node.** Live label-verified container/group metadata has `cpu.max=max
   100000`, weight 100, `memory.max=max`, effective CPUs 0–7 and nice 0 on
   both engines. Sampled task-leader runqueue waits are C/D 14.35/11.13 s for
   full-bind and 14.53/14.76 s for volume. These are partial sums, not complete
   off-CPU attribution; they do not establish a native quota or starvation
   boundary. No host or Docker policy was altered.
3. **An extra native speculative-store-bypass mitigation taxes V8.** Native
   `seccomp::install` already uses `SECCOMP_FILTER_FLAG_SPEC_ALLOW`; all live
   captured task statuses agree on `thread vulnerable` for store bypass and
   `conditional enabled` for indirect branches on both engines. The suggested
   policy difference is absent. No security protection was disabled or changed.

The original phase losses remain in the survey. In particular native warm
full-bind rebuild is still slower in the two new normal controls, and volume
install is highly variable. Application/compiler CPU dominates, but dominance
alone does not prove that the engine cannot influence it. An exclusive cause
for the residuals is **not established**. Profiles have no complete off-CPU
or hardware-frequency attribution, and sampled cgroup CPU remains a lower
bound. Do not declare parity, erase the losses, or substitute profiler timings
for the normal records.

**Decision:** no profile-supported, reachable engine-specific change emerged
from these bounded controls. As for W3-v4, do not manufacture a product patch
or a meaningless B/C/D cohort without a candidate. No runtime change, no
optimization win, and no qualification claim. The call to stop without a
candidate is explicit; a further exploratory hypothesis would be new work,
not a silently promoted or reverted optimization.

Perf's installed kernel-specific wrapper and working PATH were checked after
the repeated report-only warning `Cannot load tips.txt file, please install
perf!`. Its optional `/usr/libexec/perf-core/tips.txt` UI resource is absent;
the installed collector works and all data files have zero lost samples.
The warning is retained, not hidden by manufacturing a resource or changing
host packages. JIT/native symbol coverage is incomplete; attribution above
uses process/DSO classes, not an unsupported JavaScript source-level claim.

## Checks and operational boundary

```
GAPS_AUDIT_OK: 16 correct/admitted/strict-resource-valid records; 480 matched-control exact W5 edits; four zero-lost-sample perf trees; CPU lower-bound and 0-7 identities retained
```

The 16 records include the retained two five-edit W5 diagnostics, two matched
60-edit W5 normal records, eight W12 controls and four separately instrumented
W12 profiles. Boundary-free W5 diagnostics additionally complete 240 exact
edit results, without phase CPU qualification. The initial five-edit diagnostic
parameter error is preserved in `w5-deviation.md`; it is not the matched contrast.
No record was replaced or excluded by performance. The preceding integrated
harness check at c1df6cd was `Ran 541 tests in 24.429s; OK (skipped=16)`;
these follow-ups only add evidence, so Rust/e2e and unchanged unit suites were
not rerun. The full workflows themselves exercise exact source/image/output
and cleanup assertions. No user-facing UI exists to visually verify.

Ctrs is stopped (`MainPID=0`, inactive); no benchmark containers/custom networks
or ctrs firewall rules remain. Host dockerd/containerd are still PID 599/487,
active since 2026-11-21 05:39:22 UTC, unrestarted and unreconfigured. No security
or resource boundary was weakened. Linux shares the host kernel and these
results do not close any macOS/OrbStack gate. Further residual attribution is
explicitly unknown, not a fabricated engine win or proof of parity.
