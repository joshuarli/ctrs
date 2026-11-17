"""W2 resource-cycle accounting; disk scope is explicit active backing files."""
import hashlib
import json
import math
import time
from pathlib import Path

import collect
import resource_cells as cells


BUDGETS = {
    'version': 'w2-resource-v2-counter-aligned-interval',
    'minimum_post_warmup_cycles': 5,
    'minimum_idle_seconds': 30,
    'minimum_reclaim_seconds': 30,
    'relative_tolerance': .03,
    'absolute_tolerances': {
        'cpu_cores': .01,
        'pkg_idle_wakeups_per_s': 5,
        'interrupt_wakeups_per_s': 5,
        'steady_phys_footprint_bytes': 16 * 1024 * 1024,
        'peak_phys_footprint_bytes': 16 * 1024 * 1024,
        'next_use_seconds': .010,
        'allocated_bytes': 16 * 1024 * 1024},
    'post_warmup_footprint_growth_bytes': 16 * 1024 * 1024,
    'post_warmup_disk_growth_bytes': 16 * 1024 * 1024,
    'scope': 'diagnostic budgets; final acceptance requires frozen inputs and exclusive paired runs'}


def boundary_sample(manifest, boundary):
    return {
        'monotonic': boundary['started_monotonic'],
        'cpu_sample_ended_monotonic': boundary['ended_monotonic'],
        'sampler_version': collect.SAMPLER_VERSION,
        'sampler_sha256': hashlib.sha256(Path(collect.__file__).read_bytes()).hexdigest(),
        'counter_module_sha256': hashlib.sha256(Path(collect.__file__).with_name('macos_counters.py').read_bytes()).hexdigest(),
        'ownership_method': manifest.get('method'),
        'ownership_verified': bool(manifest.get('required_processes')) and not boundary['errors'],
        'ownership_errors': boundary['errors'], 'procs': boundary['procs']}


def phase_summary(manifest, phase, samples):
    before, after = phase['before'], phase['after']
    failures = [s for s in samples if s.get('record_type') == 'sampler_exit']
    interior = [s for s in samples if s.get('record_type') != 'sampler_exit'
                and before['ended_monotonic'] < s['monotonic'] < after['started_monotonic']]
    result = cells.interval_summary(manifest, [boundary_sample(manifest, before), *interior, *failures,
                                              boundary_sample(manifest, after)])
    result.update(operation_started_monotonic=phase['operation_started_monotonic'],
                  operation_ended_monotonic=phase['operation_ended_monotonic'],
                  operation_wall_seconds=phase['operation_wall_seconds'],
                  boundary_collection_seconds=[b['ended_monotonic'] - b['started_monotonic'] for b in (before, after)],
                  interior_sample_count=len(interior),
                  peak_method='maximum sampled actual phys_footprint; not continuous high-water mark')
    return result


def idle_interval(manifest, seconds, output, interval=.2):
    if not all(math.isfinite(v) and v > 0 for v in (seconds, interval)):
        raise ValueError('positive interval and duration required')
    samples = []
    observer_start = time.process_time()
    with Path(output).open('w') as out:
        while True:
            sample = boundary_sample(manifest, collect.cpu_boundary(manifest))
            samples.append(sample)
            out.write(json.dumps(sample) + '\n')
            out.flush()
            elapsed = sample['monotonic'] - samples[0]['monotonic']
            if elapsed >= seconds:
                break
            time.sleep(min(interval, seconds - elapsed))
    result = cells.interval_summary(manifest, samples)
    result.update(observer_cpu_seconds=time.process_time() - observer_start,
                  requested_seconds=seconds, sample_count=len(samples),
                  maximum_boundary_collection_seconds=max(s['cpu_sample_ended_monotonic'] - s['monotonic'] for s in samples),
                  peak_method='maximum sampled actual phys_footprint; not continuous high-water mark')
    return result


def cycle_growth(initial, cycles):
    footprint = [c['reclaimed']['steady_phys_footprint_bytes'] if c['reclaimed']['status'] == 'ok' else None for c in cycles]
    disk = [c['allocation_reclaimed']['allocated_bytes'] if c['allocation_reclaimed']['status'] == 'ok' else None for c in cycles]
    arguments = dict(warmup_cycles=0, minimum_cycles=BUDGETS['minimum_post_warmup_cycles'], reference_growth=0)
    return {
        'footprint': cells.evaluate_cycles(initial.get('steady_phys_footprint_bytes'), footprint,
            growth_budget=BUDGETS['post_warmup_footprint_growth_bytes'],
            return_tolerance=BUDGETS['absolute_tolerances']['steady_phys_footprint_bytes'], **arguments),
        'active_disk_allocation': cells.evaluate_cycles(initial.get('allocated_bytes'), disk,
            growth_budget=BUDGETS['post_warmup_disk_growth_bytes'],
            return_tolerance=BUDGETS['absolute_tolerances']['allocated_bytes'], **arguments),
        'exclusive_allocation': {'status': 'unknown', 'reason': 'shared APFS extents not measured'},
        'build_cache': {'status': 'unknown', 'reason': 'active disk allocation does not isolate build cache'}}


def compare_runs(reference, candidate):
    """Describe aligned raw resource cells; this never establishes qualification."""
    result = {'qualification_eligible': False, 'status': 'unqualified',
              'reason': 'engine-block diagnostic; frozen inputs and exclusivity required',
              'idle': {}, 'cycles': [],
              'storage': {'status': 'unknown', 'reason': 'shared extents and unequal historical disk state'}}

    def compare(metric, a, b):
        return cells.compare_budget(a, b,
            absolute_tolerance=BUDGETS['absolute_tolerances'][metric],
            relative_tolerance=BUDGETS['relative_tolerance'])

    for metric in ('cpu_cores', 'pkg_idle_wakeups_per_s', 'interrupt_wakeups_per_s',
                   'steady_phys_footprint_bytes', 'peak_phys_footprint_bytes'):
        a, b = reference['initial_idle'], candidate['initial_idle']
        result['idle'][metric] = compare(metric, a.get(metric) if a['status'] == 'ok' else None,
                                        b.get(metric) if b['status'] == 'ok' else None)
    if len(reference['cycles']) != len(candidate['cycles']):
        result['reason'] = 'cycle coverage differs'
        return result
    for a, b in zip(reference['cycles'], candidate['cycles']):
        if a['index'] != b['index']:
            result['reason'] = 'cycle identities differ'
            result['cycles'] = []
            return result
        row = {'index': a['index'], 'reference_trial_id': a['work_trial_id'],
               'candidate_trial_id': b['work_trial_id'],
               'next_use_seconds': compare('next_use_seconds', a['next_use_seconds'], b['next_use_seconds'])}
        for phase in ('setup', 'workload', 'cleanup'):
            row[phase] = {}
            for metric in ('steady_phys_footprint_bytes', 'peak_phys_footprint_bytes'):
                old, new = a['phases'][phase], b['phases'][phase]
                row[phase][metric] = compare(metric, old.get(metric) if old['status'] == 'ok' else None,
                                              new.get(metric) if new['status'] == 'ok' else None)
        for metric in ('cpu_cores', 'pkg_idle_wakeups_per_s', 'interrupt_wakeups_per_s',
                       'steady_phys_footprint_bytes', 'peak_phys_footprint_bytes'):
            old, new = a['reclaimed'], b['reclaimed']
            row.setdefault('reclaimed', {})[metric] = compare(metric,
                old.get(metric) if old['status'] == 'ok' else None,
                new.get(metric) if new['status'] == 'ok' else None)
        result['cycles'].append(row)
    return result
