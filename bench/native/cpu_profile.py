"""Interpret native per-thread on-CPU samples separately from off-CPU waits."""
from collections import Counter
import math
import re

import sched_trace

VERSION = 'w2-cpu-v1-native-dwarf'
FREQUENCY = 49
PERIOD_NS = round(1_000_000_000 / FREQUENCY)
HEADER = re.compile(r'^\s*(\S+)\s+(\d+)/(\d+)\s+\[(\d+)\]\s+(\d+\.\d+):\s+cpu-clock:\s*(.*)$')
FRAME = re.compile(r'^\s*([0-9a-fA-F]+)\s+(.+?)\s+\((.*)\)\s*$')


def check_attachment(attached_tasks, phase_tasks, clock_ticks):
    delta = sched_trace.application_cpu_delta(attached_tasks, phase_tasks, clock_ticks, required_tids=attached_tasks)
    if delta['status'] != 'ok':
        raise ValueError('profiler attachment task identity changed: ' + repr(delta['errors']))


def analyze(text, *, tag, tasks_before, tasks_after, application_cpu, successful_operations, diagnostics='', raw_events=''):
    errors, samples = [], []
    current = None
    if re.search(r'lost|throttl', text + diagnostics, re.IGNORECASE):
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
            errors.append(f'unrecognized CPU trace line: {number}')
    if not samples or any(not sample['frames'] for sample in samples):
        errors.append('missing CPU samples or sample frames')
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
        leaves, inclusive = Counter(), Counter()
        for sample in selected:
            names = [frame['symbol'] + ' (' + frame['dso'] + ')' for frame in sample['frames']]
            leaves[names[0]] += 1
            inclusive.update(set(names))
        per_thread[tid] = {'samples': len(selected), 'cpu': delta,
            'leaf_counts': dict(leaves.most_common()), 'inclusive_counts': dict(inclusive.most_common()),
            'unknown_leaf_samples': sum(1 for sample in selected if sample['frames'][0]['symbol'] == '[unknown]'),
            'cost_per_success_estimates': None if not selected or delta['status'] != 'ok' or successful_operations <= 0 else
                {name: delta['cpu_seconds'] * count / len(selected) / successful_operations for name, count in leaves.most_common()}}
    return {'status': 'unknown' if errors else 'ok', 'errors': errors,
        'fixture_version': VERSION, 'sample_count': len(samples), 'nominal_sampling_hz': FREQUENCY,
        'fixed_cpu_clock_period_ns': PERIOD_NS, 'raw_event_coverage_checked': bool(raw_events),
        'successful_operations': successful_operations, 'application_cpu': application_cpu,
        'per_thread': None if errors else per_thread,
        'qualification_eligible': False,
        'limitations': 'native DWARF stacks, not Python source stacks; unknown/truncated frames retained; sparse samples and tick quantization limit attribution; per-thread leaf estimates use only this profile CPU; inclusive counts overlap; no off-CPU attribution or observer correction'}
