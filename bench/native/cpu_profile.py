"""Interpret native per-thread on-CPU samples separately from off-CPU waits."""
from collections import Counter
import math
import re

import sched_trace

VERSION = 'w2-cpu-v1-native-dwarf'
LEAF_VERSION = 'w2-cpu-v1-native-leaf'
LEAF_PROFILES = {'cpu-leaf': (LEAF_VERSION, 49),
                 'cpu-leaf-25': ('w2-cpu-v1-native-leaf-25hz', 25)}
PROFILES = {'cpu': (VERSION, 49), **LEAF_PROFILES}
HEADER = re.compile(r'^\s*(\S+)\s+(\d+)/(\d+)\s+\[(\d+)\]\s+(\d+\.\d+):\s+cpu-clock:\s*(.*)$')
FRAME = re.compile(r'^\s*([0-9a-fA-F]+)\s+(.+?)\s+\((.*)\)\s*$')


def check_attachment(attached_tasks, phase_tasks, clock_ticks):
    delta = sched_trace.application_cpu_delta(attached_tasks, phase_tasks, clock_ticks, required_tids=attached_tasks)
    if delta['status'] != 'ok':
        raise ValueError('profiler attachment task identity changed: ' + repr(delta['errors']))


def period_ns(kind):
    return round(1_000_000_000 / PROFILES[kind][1])


def analyze(text, *, tag, tasks_before, tasks_after, application_cpu, successful_operations,
            diagnostics='', raw_events='', profile_kind='cpu'):
    version, frequency = PROFILES[profile_kind]
    leaf_only = profile_kind in LEAF_PROFILES
    errors, samples = [], []
    current = None
    if re.search(r'lost|throttl', diagnostics, re.IGNORECASE):
        errors.append('loss/throttle diagnostic present')
    if raw_events:
        if re.search(r'PERF_RECORD_(?:LOST|THROTTLE|UNTHROTTLE)', raw_events):
            errors.append('raw loss/throttle record present')
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            current = None
            continue
        header = HEADER.fullmatch(line)
        if header:
            comm, pid, tid, cpu, timestamp, remainder = header.groups()
            current = {'tid': tid, 'cpu': int(cpu), 'timestamp': timestamp, 'frames': []}
            samples.append(current)
            if comm != tag or pid != '1' or tid not in tasks_before:
                errors.append(f'sample outside tagged API tasks: {number}')
            if not remainder:
                continue
            line = remainder
        frame = FRAME.fullmatch(line)
        if frame and current is not None:
            address, symbol, dso = frame.groups()
            current['frames'].append({'ip': address, 'symbol': symbol, 'dso': dso})
        else:
            if re.search(r'lost|throttl', line, re.IGNORECASE):
                errors.append('loss/throttle diagnostic present')
            errors.append(f'unrecognized CPU trace line: {number}')
    if not samples or any(not sample['frames'] for sample in samples):
        errors.append('missing CPU samples or sample frames')
    if leaf_only:
        if not raw_events:
            errors.append('missing raw CPU event audit')
        if any(len(sample['frames']) > 1 for sample in samples):
            errors.append('leaf-only trace contains a call stack')
    if raw_events and len(re.findall(r'\bPERF_RECORD_SAMPLE\b', raw_events)) != len(samples):
        errors.append('raw/decoded sample count mismatch')
    if type(successful_operations) is not int or successful_operations <= 0:
        errors.append('invalid successful operation denominator')
    cpu_seconds = application_cpu.get('cpu_seconds')
    if application_cpu.get('status') != 'ok' or not isinstance(cpu_seconds, (int, float)) or not math.isfinite(cpu_seconds) or cpu_seconds < 0:
        errors.append('missing application CPU coverage')
    per_thread = {}
    if set(tasks_before) != set(tasks_after):
        errors.append('application task coverage changed')
    for tid in tasks_before.keys() & tasks_after.keys():
        a, b = tasks_before[tid], tasks_after[tid]
        if a['comm'].strip() != tag or b['comm'].strip() != tag:
            errors.append('API task tag changed: ' + tid)
        delta = sched_trace.application_cpu_delta({tid: a}, {tid: b}, application_cpu.get('clock_ticks_per_second'), required_tids=[tid])
        if delta['status'] != 'ok':
            errors.extend(delta['errors'])
        selected = [sample for sample in samples if sample['tid'] == tid and sample['frames']]
        if leaf_only and not selected:
            errors.append('leaf-only trace has no samples for API thread: ' + tid)
        leaves, inclusive = Counter(), Counter()
        for sample in selected:
            names = [frame['symbol'] + ' (' + frame['dso'] + ')' for frame in sample['frames']]
            leaves[names[0]] += 1
            if not leaf_only:
                inclusive.update(set(names))
        per_thread[tid] = {'samples': len(selected), 'cpu': delta,
            'leaf_counts': dict(leaves.most_common()),
            'unknown_leaf_samples': sum(1 for sample in selected if sample['frames'][0]['symbol'] == '[unknown]'),
            'cost_per_success_estimates': None if errors or not selected or delta['status'] != 'ok' else
                {name: delta['cpu_seconds'] * count / len(selected) / successful_operations for name, count in leaves.most_common()}}
        if not leaf_only:
            per_thread[tid]['inclusive_counts'] = dict(inclusive.most_common())
    return {'status': 'unknown' if errors else 'ok', 'errors': errors,
        'fixture_version': version, 'sample_count': len(samples), 'nominal_sampling_hz': frequency,
        'fixed_cpu_clock_period_ns': period_ns(profile_kind), 'raw_event_coverage_checked': bool(raw_events),
        'successful_operations': successful_operations, 'application_cpu': application_cpu,
        'per_thread': None if errors else per_thread,
        'qualification_eligible': False,
        'limitations': ('native sampled leaf PCs; unresolved symbols retained; no inclusive counts'
                        if leaf_only else 'native DWARF stacks, not Python source stacks; unknown/truncated frames retained; inclusive counts overlap')
                       + '; sparse samples and tick quantization limit attribution; per-thread leaf estimates use only this profile CPU; no off-CPU attribution or observer correction'}
