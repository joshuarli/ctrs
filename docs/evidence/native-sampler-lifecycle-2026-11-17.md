# Sampler lifecycle repair and checkpoint reconciliation

The owner resumed the native macOS campaign after cleanup on 2026-11-17.
Reviewed checkpoint `94f19a8` is an ancestor of the current tree. The accounting
repair already landed at `0f5724f`, ownership at `84923be`, explicit phases at
`eaf72fb`, native counters at `d9d6b98`, and fixed-work W2 at `5354aa7`.
Real W4/W5/W8/W9 and representative short W11 fixtures also landed. The latest
queue keeps these implementations and their evidence, without treating them as
final qualification. Cleanup/history merges introduce no product changes.

## Demonstrated defect and bounded change

A collector can terminate after emitting two valid resource samples. Baseline
`stop_sampler` ignores the process exit status and `summarize_trace` sees an
ordinary complete-looking prefix. An actual child exit7 reproduction retained
CPU3.0s, physical footprint100100B and an empty error list. This is a measurement
failure, not a small engine or a performance win.

The sampler handle now owns its child, trace and stderr path. Shutdown checks
that the collector was still running, exited successfully after the request,
and did not require forced termination. Otherwise it appends the actual terminal
status/error to the trace. Existing summarization invalidates CPU and physical
acceptance cells while preserving original samples. Stderr is retained in the
trial directory. App/VM state, native counter ABI, sampling period, resource budgets and default builder are
unchanged. Collector version4 adds a stop acknowledgment with its own PID,
version and signal-receipt monotonic time. The parent requires that receipt
to match the current stop request. This closes a liveness-check/signal race
identified by independent review; an observed exit0 alone is insufficient. The runner source
hash identifies this validation revision; do not pool it with unchecked prefixes.

The expected benefit is rejection of incomplete measurements. No runtime speedup
is predicted or claimed. A successfully requested collector stop remains valid;
even an unexpected early exit0 is incomplete and must fail the resource cells.

## Verification

The existing 43 collector/native-counter/ownership/reporter tests pass before
the change. After the correction, the affected 87-test selection passes with zero
failures or skips:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=bench/native python3.14 -m unittest \
  test_collect test_macos_counters test_ownership test_reporting \
  test_mixed_cycle test_w4_lifecycle test_resource_cycles test_resource_cells \
  test_registry_variant_pilot test_resource_pilot
```

The new lifecycle cases use real short-lived child processes: early exit0,
early exit7 and graceful requested stop. Partial samples are valid-looking before
shutdown validation; afterward both early-exit resource cells are unknown and
the stderr message survives. The graceful control retains both resource totals.
The deterministic race regression supplies an observed running result followed
by a successfully exited child; a missing current acknowledgment invalidates
the prefix. Resource-phase consumers also retain the sampler error and return
unknown cells, rather than raising a missing-timestamp error or accepting just
the independent boundaries. The final native proof checks these phase cells.
No comprehensive suite, application sweep, release build or W11 was run.

Initial collection-only proof `sampler-lifecycle-20261117-7dacf707` uses the
first repair and remains separate. Final v4 proof
`sampler-lifecycle-20261117-be72920f` performs
read-only server-version calls on the existing OrbStack socket. Every case
identifies both actual processes by PID/kernel start identity and hashes their
loaded executables. Short operation CPU boundaries are complete. The normal
sampler reports complete counters including the large helper; early successful
exit and SIGKILL preserve their observed terminal statuses and invalidate totals.

| Case | Child exit | Required processes | CPU/physical acceptance cells |
| --- | ---: | ---: | --- |
| Requested stop | 0 | 2 | Complete |
| Early stop | 0 | 2 | Unknown; explicit error |
| Early kill | -9 | 2 | Unknown; explicit error |

The original 20-trial v3 sampler-on/off diagnostic remains in the historical
[measurement evidence](native-performance.md#native-sampler-v3-short-calibration-accepted-for-diagnostic-iteration).
It is not a fresh observer-overhead confirmation for this candidate. The ordinary
`perf-gate-ready` exits0; this does not establish exclusivity. A saved snapshot
finds unrelated Niceforge smolvm at98.8% CPU and the unrelated
`bctl-r7-qualify` VM still running. The separate `-s` lane-admission advisory
exits75 on swap use and explicitly says it is not a timing-gate result.
**Perf gate deferred: host busy.** This short read-only proof explicitly sets timing and
qualification eligibility false and does not measure application observer cost.
No unrelated workload or shared daemon was stopped. Clean equal-work W2 and
observer confirmation remain next; original contaminated batches stay invalid.

## Native reproduction

Run the following from the primary checkout on ARM64 macOS with OrbStack already
running. It observes that service and terminates only its own sampler children;
it does not start/restart engines or modify containers. Raw output is optional
under `.work/native-perf/results/`. The script records source hashes and both
host gates; it always refuses to label this functional proof qualified timing.

```python
import hashlib, json, signal, subprocess, sys, time, uuid
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, 'bench/native')
import runner, collect, resource_cycles
root = runner.RESULTS / ('sampler-lifecycle-20261117-' + uuid.uuid4().hex[:8])
root.mkdir(parents=True)
def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')
def gate(label):
    p = subprocess.run(['perf-gate-ready'] + (['-1'] if label == 'after' else []), capture_output=True, text=True)
    save(root / (label + '-gate.json'), {'exit': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
files = ['bench/native/' + p for p in ['runner.py', 'collect.py', 'macos_counters.py', 'ownership.py']]
save(root / 'plan.json', {'kind': 'native read-only sampler lifecycle proof', 'source_hashes': {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files}, 'sampler_version': collect.SAMPLER_VERSION, 'timing_eligible': False, 'qualification_eligible': False})
gate('before')
records = []
for mode in ['requested-stop', 'early-zero', 'early-kill']:
    directory = root / mode
    directory.mkdir()
    engine = SimpleNamespace(name='orbstack', socket='unix:///Users/josh/.orbstack/run/docker.sock', dir=directory)
    sampler, trace = runner.start_sampler(engine, directory)
    try:
        deadline = time.monotonic() + 8
        while not trace.exists() or len(trace.read_text().splitlines()) < 2:
            if sampler.process.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('native sampler did not produce two samples')
            time.sleep(.03)
        rec = {'resources': {}}
        with runner.resource_phase(engine, rec, 'read-only-server-version'):
            cp = subprocess.run(['docker', '--host', engine.socket, 'version', '--format', '{{json .Server.Version}}'], capture_output=True, text=True, timeout=10, check=True)
            if not json.loads(cp.stdout):
                raise RuntimeError('missing server version')
        if mode != 'requested-stop':
            sampler.process.send_signal(signal.SIGTERM if mode == 'early-zero' else signal.SIGKILL)
            sampler.process.wait(timeout=5)
        runner.stop_sampler(sampler)
        result = runner.summarize_trace(trace)
        phase = rec['resources']['phases']['read-only-server-version']
        assert phase['cpu_seconds'] is not None and not phase['errors'], phase
        assert len(engine.measurement_identity['required_processes']) >= 2
        if mode == 'requested-stop':
            assert result['cpu_seconds_est'] is not None and result['peak_phys_footprint_bytes'] > 0 and not result['resource_errors'], result
        else:
            assert result['cpu_seconds_est'] is None and result['peak_phys_footprint_bytes'] is None and result['resource_errors'], result
        phase_cells = resource_cycles.phase_summary(engine.measurement_identity, phase, [json.loads(line) for line in trace.read_text().splitlines()])
        assert phase_cells['status'] == ('ok' if mode == 'requested-stop' else 'unknown'), phase_cells
        row = {'phase_cells': phase_cells, 'mode': mode, 'sampler_exit': sampler.process.returncode, 'required_processes': len(engine.measurement_identity['required_processes']), 'summary': result, 'phase': phase, 'server_version': json.loads(cp.stdout)}
        save(directory / 'result.json', row)
        records.append(row)
        print(mode, 'passed', 'samples=', result['samples'], flush=True)
    finally:
        if sampler.process.poll() is None:
            runner.stop_sampler(sampler)
gate('after')
save(root / 'result.json', {'status': 'passed', 'records': records, 'timing_eligible': False, 'qualification_eligible': False, 'workload_scope': 'read-only server version requests; no application overhead verdict'})
print(root, flush=True)
```

Frozen source receipts from the final native pilot:

```json
{
  "kind": "native read-only sampler lifecycle proof",
  "source_hashes": {
    "bench/native/runner.py": "c8616fac1c63705301e80d7f785d40bc84b48004ec7f5a8d1193a123f96038a7",
    "bench/native/collect.py": "2d0a3b4f491dee15566405d24f1a9eb40639637de9e3707198aba256691d9fdf",
    "bench/native/macos_counters.py": "aeae97ef33bcb3f86a9f5898967bb8400ee2374c5eac1b8d5a81f74fe0949373",
    "bench/native/ownership.py": "e4bec89a1d9623e72fe6dbb5842942a1284c23ec04360b5817774a682ce11326"
  },
  "sampler_version": "4-native-rusage",
  "timing_eligible": false,
  "qualification_eligible": false
}
```

## Independent completion review

Reviewer `usrw_67e419fc-9656-407e-ba02-8c1a768c28ad` identified the first repair's
liveness/signal race, then reviewed `bf9582f..ef22cc9` and all relevant callers.
The correction review found no additional demonstrated defect. It left the
checkout unchanged. Its54 tests ran on the earlier bf9582f tree; they do not
substitute for the parent's87 correction tests and final native proof. The
reviewer assessed forced-stop and receipt edge cases from source. The empty
ignored review directory was inspected and discarded when retiring its checkout.

The bounded measurement source repair is accepted. Fresh application observer
confirmation and all performance/resource qualification remain open. The normal
timing gate's exit0 did not override the independently observed foreign load.

## Fixed-work application-control admission

The scratch-only v3 calibration driver is superseded by the tracked
`diagnostics/sampler_pilot.py` entrypoint. It reuses the pinned common W2 service
images and existing exact-state runner. Boundary-only controls retain ownership
and setup/workload/cleanup CPU boundaries while spawning no periodic observer;
periodic controls use sampler v4 unchanged. The existing default remains periodic.
ResourceEngine accepts an explicit isolated root for this consumer. No product
CLI, dependency, guest asset, persisted runtime format or default changes.

The bounded functional admission is one alternating off/on pair per engine,
1000 exact operations per trial, concurrency4 and write ratio0.3: four trials,
4000 measured useful operations. The same seed/work mix must match across modes
and engines. Require actual image/boot/process identity, exact persisted data,
complete CPU boundaries, valid periodic traces, owned stack cleanup, stopped
ctrs processes and registry-thread termination. Compute observer ratios from
raw workload-phase CPU and successful counts, never published medians.

This first batch deliberately remains timing/qualification ineligible under the
known foreign activity. It can validate instrumentation and real control flow;
it cannot pass observer-overhead budgets or an engine-performance gate. The
finite job is `.work/tmp/sampler-v4-functional-20261117/job`, with20-minute
fixed deadline and frozen scripts/layout/boot inputs. Source command:

```python
import sys
from pathlib import Path
sys.path.insert(0, 'bench/native')
from diagnostics.sampler_pilot import run_calibration
run_calibration(run_id='sampler-v4-functional-20261117',
    portfolio_layout=Path('.work/native-perf/inputs/w8-portfolio-v2/layout'),
    ctrs_binary=Path('.work/tmp/readiness-main-target/release/ctrs'),
    pairs=1, operations=1000)
```

Use a new run ID/output and rebuild the pinned layout from the tracked portfolio
instructions if scratch is absent. The admitted child discloses2CPU/8192MiB and
the accepted explicit guest assets for ctrs; each engine's own off/on pair keeps
its resources fixed. This does not compare the engines' allocation envelopes.
The source supports a predeclared five-pair batch later, with fresh exclusive
host admission and no replacement of failed/contaminated pairs.
