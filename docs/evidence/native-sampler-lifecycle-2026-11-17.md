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
trial directory. App/VM state, native counter ABI, collector version3, sampling
period, resource budgets and default builder are unchanged. The runner source
hash identifies this validation revision; do not pool it with unchecked prefixes.

The expected benefit is rejection of incomplete measurements. No runtime speedup
is predicted or claimed. A successfully requested collector stop remains valid;
even an unexpected early exit0 is incomplete and must fail the resource cells.

## Verification

The existing 43 collector/native-counter/ownership/reporter tests pass before
the change. After the repair, the affected 66-test selection passes with zero
failures or skips:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=bench/native python3.14 -m unittest \
  test_collect test_macos_counters test_ownership test_reporting \
  test_mixed_cycle test_w4_lifecycle
```

The new lifecycle cases use real short-lived child processes: early exit0,
early exit7 and graceful requested stop. Partial samples are valid-looking before
shutdown validation; afterward both early-exit resource cells are unknown and
the stderr message survives. The graceful control retains both resource totals.
No comprehensive suite, application sweep, release build or W11 was run.

Native collection-only proof `sampler-lifecycle-20261117-7dacf707` performs
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
It is not a fresh observer-overhead confirmation for this candidate. Current
`perf-gate-ready -s` exits75 due to swap use above its threshold. **Perf gate
deferred: host busy.** This short read-only proof explicitly sets timing and
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
import runner, collect
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
        row = {'mode': mode, 'sampler_exit': sampler.process.returncode, 'required_processes': len(engine.measurement_identity['required_processes']), 'summary': result, 'phase': phase, 'server_version': json.loads(cp.stdout)}
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

Frozen source receipts from the native pilot:

```json
{
  "kind": "native read-only sampler lifecycle proof",
  "source_hashes": {
    "bench/native/runner.py": "660fa7b0466be0a36b9885994d379c881d873c404163303bb6fa96ac8b5f59d0",
    "bench/native/collect.py": "5312f8cb051bb20a031d1f59fd8e03314c29ecc7f79b5885694db30b151f150c",
    "bench/native/macos_counters.py": "aeae97ef33bcb3f86a9f5898967bb8400ee2374c5eac1b8d5a81f74fe0949373",
    "bench/native/ownership.py": "e4bec89a1d9623e72fe6dbb5842942a1284c23ec04360b5817774a682ce11326"
  },
  "sampler_version": "3-native-rusage",
  "timing_eligible": false,
  "qualification_eligible": false
}
```
