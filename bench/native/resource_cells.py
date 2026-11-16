"""Explicit owned-process and owned-file resource acceptance cells."""
import math
import os
import stat
import statistics


COUNTERS = ('cputime_s', 'user_cpu_s', 'system_cpu_s', 'pkg_idle_wakeups',
            'interrupt_wakeups', 'footprint_bytes')


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def interval_summary(manifest, samples):
    """Summarize complete collector records; steady footprint is the sample median."""
    errors = []
    required = manifest.get('required_processes', [])
    ids = [p.get('pid') for p in required]
    if (not required or len(set(ids)) != len(ids) or
            any(not isinstance(p.get('pid'), int) or p.get('kernel_start_identity') is None
                or not p.get('start_identity') or not p.get('comm') for p in required)):
        errors.append('invalid required-process manifest')
    if manifest.get('engine') == 'ctrs' and not any(p.get('role') == 'vm' for p in required):
        errors.append('missing required VM in manifest')
    if len(samples) < 2:
        errors.append('at least two samples required')
    records = []
    times = []
    for index, sample in enumerate(samples):
        t = sample.get('monotonic')
        if not _number(t) or (times and t <= times[-1]):
            errors.append(f'invalid sample time: {index}')
        else:
            times.append(t)
        if sample.get('ownership_verified') is not True or sample.get('ownership_errors'):
            errors.append(f'unverified ownership: {index}')
        procs = sample.get('procs', [])
        actual = {p.get('pid'): p for p in procs}
        if len(actual) != len(procs) or set(actual) != set(ids):
            errors.append(f'required-process coverage differs: {index}')
        for expected in required:
            proc = actual.get(expected.get('pid'), {})
            if any(proc.get(k) != expected.get(k) for k in ('comm', 'start_identity', 'kernel_start_identity')):
                errors.append(f'process identity mismatch: {index} pid {expected.get("pid")}')
            if any(not _number(proc.get(k)) for k in COUNTERS):
                errors.append(f'missing counter: {index} pid {expected.get("pid")}')
            if proc.get('footprint_method') != 'rusage_info_v0.ri_phys_footprint' or not proc.get('counter_method'):
                errors.append(f'missing native method: {index} pid {expected.get("pid")}')
        records.append(actual)
    for before, after in zip(records, records[1:]):
        for pid in ids:
            for key in COUNTERS[:-1]:
                a, b = before.get(pid, {}).get(key), after.get(pid, {}).get(key)
                if _number(a) and _number(b) and b < a:
                    errors.append(f'counter decreased: {pid} {key}')
    result = {'status': 'unknown' if errors else 'ok', 'errors': errors,
              'required_processes': required, 'ownership_method': manifest.get('method'),
              'sample_provenance': [{k: s.get(k) for k in ('monotonic', 't', 'sampler_version',
                  'sampler_sha256', 'counter_module_sha256', 'ownership_method')} for s in samples],
              'counter_methods': sorted({p.get('counter_method') for s in samples for p in s.get('procs', []) if p.get('counter_method')}),
              'footprint_method': 'rusage_info_v0.ri_phys_footprint',
              'elapsed_s': None, 'cpu_seconds': None, 'user_cpu_seconds': None,
              'system_cpu_seconds': None, 'cpu_cores': None,
              'pkg_idle_wakeups_per_s': None, 'interrupt_wakeups_per_s': None,
              'steady_phys_footprint_bytes': None, 'peak_phys_footprint_bytes': None}
    if errors:
        return result
    elapsed = times[-1] - times[0]
    delta = {k: sum(records[-1][pid][k] - records[0][pid][k] for pid in ids) for k in COUNTERS[:-1]}
    footprints = [sum(record[pid]['footprint_bytes'] for pid in ids) for record in records]
    result.update(elapsed_s=elapsed, cpu_seconds=delta['cputime_s'],
                  user_cpu_seconds=delta['user_cpu_s'], system_cpu_seconds=delta['system_cpu_s'],
                  cpu_cores=delta['cputime_s'] / elapsed,
                  pkg_idle_wakeups_per_s=delta['pkg_idle_wakeups'] / elapsed,
                  interrupt_wakeups_per_s=delta['interrupt_wakeups'] / elapsed,
                  steady_phys_footprint_bytes=statistics.median(footprints),
                  peak_phys_footprint_bytes=max(footprints))
    return result


def compare_budget(baseline, candidate, *, absolute_tolerance, relative_tolerance):
    """Compare a higher-is-worse cell using the larger caller-provided tolerance."""
    if any(not _number(x) for x in (baseline, candidate, absolute_tolerance, relative_tolerance)):
        return {'status': 'unknown', 'allowed_increase': None, 'increase': None}
    allowed = max(absolute_tolerance, baseline * relative_tolerance)
    increase = candidate - baseline
    return {'status': 'pass' if increase <= allowed else 'fail',
            'allowed_increase': allowed, 'increase': increase}


def evaluate_cycles(initial, cleanup_values, *, warmup_cycles, minimum_cycles,
                    growth_budget, return_tolerance, reference_growth):
    """Bound every post-warmup cleanup allocation against a reference and initial state."""
    valid_counts = (isinstance(warmup_cycles, int) and not isinstance(warmup_cycles, bool)
                    and warmup_cycles >= 0 and isinstance(minimum_cycles, int)
                    and not isinstance(minimum_cycles, bool) and minimum_cycles >= 2)
    result = {'status': 'unknown', 'growth_status': 'unknown', 'return_status': 'unknown',
              'post_warmup_growth': None, 'return_difference': None}
    if (not valid_counts or not all(_number(x) for x in
            (initial, growth_budget, return_tolerance)) or
            not isinstance(reference_growth, (int, float)) or isinstance(reference_growth, bool)
            or not math.isfinite(reference_growth) or
            len(cleanup_values) - warmup_cycles < minimum_cycles or
            any(not _number(v) for v in cleanup_values)):
        return result
    post = cleanup_values[warmup_cycles:]
    growth = max(post) - post[0]
    returned = max(post) - initial
    growth_status = 'pass' if growth - reference_growth <= growth_budget else 'fail'
    return_status = 'pass' if returned <= return_tolerance else 'fail'
    result.update(status='pass' if growth_status == return_status == 'pass' else 'fail',
                  growth_status=growth_status, return_status=return_status,
                  post_warmup_growth=growth, return_difference=returned)
    return result


def allocation_snapshot(paths):
    """Stat only explicit owned regular files; allocation can include shared extents."""
    files, errors, seen = [], [], set()
    for path in paths:
        try:
            st = os.stat(path, follow_symlinks=False)
            if not stat.S_ISREG(st.st_mode):
                raise ValueError('not a regular file')
            identity = (st.st_dev, st.st_ino)
            if identity in seen:
                raise ValueError('duplicate file identity')
            seen.add(identity)
            blocks = getattr(st, 'st_blocks', None)
            if not _number(blocks):
                raise ValueError('st_blocks unavailable')
            fs = os.statvfs(path)
            files.append({'path': os.fspath(path), 'device': st.st_dev, 'inode': st.st_ino,
                          'logical_bytes': st.st_size, 'allocated_bytes': blocks * 512,
                          'filesystem_free_bytes': fs.f_bavail * fs.f_frsize})
        except (OSError, ValueError) as exc:
            errors.append(f'{os.fspath(path)}: {exc}')
    if not paths:
        errors.append('no owned paths')
    return {'status': 'unknown' if errors else 'ok', 'errors': errors, 'files': files,
            'allocated_bytes': None if errors else sum(f['allocated_bytes'] for f in files),
            'allocation_method': 'stat.st_blocks * 512; may include shared clone extents',
            'exclusive_allocated_bytes': None, 'exclusive_allocation_status': 'unsupported',
            'filesystem_free_method': 'statvfs.f_bavail * f_frsize'}
