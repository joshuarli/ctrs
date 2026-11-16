"""Interpret filtered perf scheduler traces without mixing CPU and off-CPU time."""
from collections import Counter
from decimal import Decimal
import re

LINE = re.compile(r'^\s*(.*?)\s+(\d+)/(\d+)\s+\[(\d+)\]\s+(\d+\.\d{1,9}):\s+sched:(\w+):\s+(.*)$')
SWITCH = re.compile(r'^prev_comm=(.*?) prev_pid=(\d+) prev_prio=\d+ prev_state=(\S+) ==> next_comm=(.*?) next_pid=(\d+) next_prio=\d+$')
WAKE = re.compile(r'^comm=(.*?) pid=(\d+) prio=\d+ target_cpu=(\d+)$')
MIGRATE = re.compile(r'^comm=(.*?) pid=(\d+) prio=\d+ orig_cpu=(\d+) dest_cpu=(\d+)$')
EVENTS = {'sched_switch', 'sched_waking', 'sched_wakeup', 'sched_migrate_task'}


def task_identity(stat):
    tail = stat[stat.rfind(')') + 2:].split()
    return int(tail[19])


def parse(text, tag):
    events, errors = [], []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        if 'LOST' in line.upper():
            errors.append(f'loss record at line {number}')
            continue
        match = LINE.fullmatch(line)
        if not match:
            errors.append(f'unrecognized trace line {number}')
            continue
        comm, pid, tid, cpu, timestamp, kind, payload = match.groups()
        if kind not in EVENTS:
            errors.append(f'unsupported event at line {number}: {kind}')
            continue
        event = dict(kind=kind, ns_pid=int(pid), ns_tid=int(tid), cpu=int(cpu),
                     sample_comm=comm, time_ns=int(Decimal(timestamp) * 1_000_000_000))
        pattern = SWITCH if kind == 'sched_switch' else MIGRATE if kind == 'sched_migrate_task' else WAKE
        fields = pattern.fullmatch(payload)
        if not fields:
            errors.append(f'unrecognized payload at line {number}')
            continue
        if kind == 'sched_switch':
            prev_comm, prev, state, next_comm, next_tid = fields.groups()
            event.update(prev_comm=prev_comm, prev=int(prev), state=state,
                         next_comm=next_comm, next=int(next_tid))
            if prev_comm != tag and next_comm != tag:
                errors.append(f'event outside target filter: {number}')
        else:
            target_comm, target, first, *last = fields.groups()
            event.update(target_comm=target_comm, target=int(target))
            if kind == 'sched_migrate_task':
                event.update(orig_cpu=int(first), dest_cpu=int(last[0]))
            else:
                event['target_cpu'] = int(first)
            if target_comm != tag:
                errors.append(f'event outside target filter: {number}')
        if events and event['time_ns'] < events[-1]['time_ns']:
            errors.append(f'events out of order: {number}')
        events.append(event)
    if not events:
        errors.append('empty scheduler trace')
    return events, errors


def analyze(text, *, tag, tasks_before, tasks_after, global_main_tid=None):
    """Join stable tagged tasks. An optional global PID must share the trace's kernel namespace.

    Docker State.Pid can belong to another PID namespace. Scheduled time and
    wake transitions are not task CPU counters.
    """
    events, errors = parse(text, tag)
    mapping = {}
    targets = set()
    expected = set(tasks_before)
    if '1' not in expected or expected != set(tasks_after):
        errors.append('application task coverage changed')
    for tid in expected & set(tasks_after):
        try:
            before, after = tasks_before[tid], tasks_after[tid]
            if any(record['stat'].split(' ', 1)[0] != tid for record in (before, after)):
                errors.append(f'application stat PID differs from namespace TID: {tid}')
            if before['comm'].strip() != tag or after['comm'].strip() != tag:
                errors.append(f'untagged application task: {tid}')
            if task_identity(before['stat']) != task_identity(after['stat']):
                errors.append(f'application task start identity changed: {tid}')
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            errors.append(f'invalid application task identity: {tid}')
    for event in events:
        if event['kind'] == 'sched_switch':
            if event['prev_comm'] == tag:
                targets.add(event['prev'])
                if event['sample_comm'] != tag or event['ns_pid'] != 1:
                    errors.append('switch-out sample is not the tagged application')
                key = str(event['ns_tid'])
                if key not in expected:
                    errors.append(f'unrecognized namespace task: {key}')
                if key in mapping and mapping[key] != event['prev']:
                    errors.append(f'namespace task maps to multiple global TIDs: {key}')
                mapping[key] = event['prev']
            if event['next_comm'] == tag:
                targets.add(event['next'])
        else:
            targets.add(event['target'])
    if set(mapping) != expected or set(mapping.values()) != targets or len(set(mapping.values())) != len(mapping):
        errors.append('incomplete or ambiguous namespace/global task mapping')
    if global_main_tid is not None and mapping.get('1') != global_main_tid:
        errors.append('global main task differs from independently verified kernel PID')
    result = {'status': 'invalid' if errors else 'ok', 'errors': sorted(set(errors)),
              'namespace_to_global_tid': mapping, 'event_counts': dict(Counter(e['kind'] for e in events)),
              'global_main_tid_from_trace': mapping.get('1'),
              'identity_method': 'unique application tag + stable namespace task starts + switch-out namespace/global join',
              'cycles': [], 'on_cpu_intervals': [], 'incomplete': {},
              'totals_ns': None, 'coverage': None}
    if errors:
        return result
    running, sleeping = {}, {}
    seen_out = set()
    running_wake = {}
    overlap_counts = Counter()
    closed_cycles = 0
    migrations = Counter()
    incomplete = Counter()
    cycles = []
    on_cpu = []
    for event in events:
        now = event['time_ns']
        kind = event['kind']
        if kind == 'sched_switch':
            if event['prev_comm'] == tag:
                tid = event['prev']
                seen_out.add(tid)
                entered = running.pop(tid, None)
                if entered is None:
                    incomplete['initial_on_cpu_boundary'] += 1
                else:
                    on_cpu.append(dict(tid=tid, cpu=event['cpu'], start_ns=entered, end_ns=now, duration_ns=now-entered))
                if tid in sleeping:
                    incomplete['duplicate_switch_out'] += 1
                sleeping[tid] = dict(tid=tid, out_ns=now, state=event['state'],
                                     out_cpu=event['cpu'], waking_ns=running_wake.pop(tid, None), wakeup_ns=None)
                if sleeping[tid]['waking_ns'] is not None:
                    overlap_counts['waking_preceded_switch_out'] += 1
            if event['next_comm'] == tag:
                tid = event['next']
                if tid in running:
                    incomplete['duplicate_switch_in'] += 1
                running[tid] = now
                cycle = sleeping.pop(tid, None)
                if cycle is None:
                    incomplete['initial_off_cpu_boundary'] += 1
                    continue
                closed_cycles += 1
                cycle.update(in_ns=now, in_cpu=event['cpu'], off_cpu_ns=now-cycle['out_ns'])
                runnable = cycle['state'].startswith('R')
                if runnable:
                    if cycle['waking_ns'] is not None or cycle['wakeup_ns'] is not None:
                        incomplete['wake_during_runnable_cycle'] += 1
                        continue
                    cycle.update(blocked_ns=0, wake_transition_ns=0, wake_transition_off_cpu_ns=0,
                                 runnable_wait_ns=cycle['off_cpu_ns'])
                elif cycle['waking_ns'] is None or cycle['wakeup_ns'] is None:
                    incomplete['missing_wake_pair'] += 1
                    continue
                else:
                    out, waking, wakeup = cycle['out_ns'], cycle['waking_ns'], cycle['wakeup_ns']
                    if waking > wakeup or wakeup > now or out > wakeup:
                        incomplete['inconsistent_wake_order'] += 1
                        continue
                    cycle.update(blocked_ns=max(0, waking-out), wake_transition_ns=wakeup-waking,
                                 wake_transition_off_cpu_ns=wakeup-max(waking,out), runnable_wait_ns=now-wakeup)
                cycles.append(cycle)
        elif kind in ('sched_waking', 'sched_wakeup'):
            tid = event['target']
            cycle = sleeping.get(tid)
            if cycle is None:
                if tid in running:
                    if kind == 'sched_waking':
                        if tid in running_wake:
                            incomplete['duplicate_running_wake'] += 1
                        running_wake[tid] = now
                    elif tid in running_wake:
                        running_wake.pop(tid)
                        overlap_counts['wake_pair_completed_while_running'] += 1
                    else:
                        incomplete['unmatched_wake'] += 1
                else:
                    incomplete['unmatched_wake' if tid in seen_out else 'initial_wake_boundary'] += 1
                continue
            field = 'waking_ns' if kind == 'sched_waking' else 'wakeup_ns'
            if cycle[field] is not None:
                incomplete['duplicate_wake'] += 1
                cycle['ambiguous'] = True
            cycle[field] = now
        elif kind == 'sched_migrate_task':
            migrations[event['target']] += 1
    incomplete['final_running_wake_boundary'] += len(running_wake)
    incomplete['final_on_cpu_boundary'] += len(running)
    incomplete['final_off_cpu_boundary'] += len(sleeping)
    valid_cycles = [c for c in cycles if not c.get('ambiguous')]
    incomplete['ambiguous_cycles'] += len(cycles)-len(valid_cycles)
    boundary_counts = {'initial_on_cpu_boundary', 'initial_off_cpu_boundary', 'initial_wake_boundary',
                       'final_on_cpu_boundary', 'final_off_cpu_boundary', 'final_running_wake_boundary'}
    partial = (not valid_cycles or not on_cpu or
               any(value for key, value in incomplete.items() if key not in boundary_counts))
    result.update(status='partial' if partial else 'ok', cycles=valid_cycles, on_cpu_intervals=on_cpu, incomplete=dict(incomplete),
                  migrations_by_global_tid=dict(migrations), running_wake_observations=dict(overlap_counts),
                  totals_ns={'scheduled_running_observed': sum(v['duration_ns'] for v in on_cpu) if on_cpu else None,
                             **{key: sum(c[key] for c in valid_cycles) if valid_cycles else None for key in
                                ('off_cpu_ns', 'blocked_ns', 'wake_transition_ns', 'wake_transition_off_cpu_ns', 'runnable_wait_ns')}},
                  coverage={'complete_off_cpu_cycles': len(valid_cycles),
                            'closed_off_cpu_cycles': closed_cycles,
                            'complete_closed_cycle_fraction': len(valid_cycles)/closed_cycles if closed_cycles else None,
                            'discarded_or_boundary_events': sum(incomplete.values()),
                            'unobserved_boundary_time': 'unknown',
                            'scheduled_running_is_task_cpu_time': False,
                            'wake_transition_is_task_cpu_time': False})
    return result


def application_cpu_delta(before, after, clock_ticks_per_second, *, required_tids):
    """Sum stable API thread counters; profiler exec processes are outside this set."""
    errors = []
    if type(clock_ticks_per_second) is not int or clock_ticks_per_second <= 0:
        errors.append('missing guest clock tick frequency')
    required = set(required_tids)
    if not required or set(before) != required or set(after) != required:
        errors.append('API thread coverage changed')
    user = system = 0
    for tid in set(before) & set(after):
        try:
            a, b = before[tid], after[tid]
            if a['comm'] != b['comm'] or task_identity(a['stat']) != task_identity(b['stat']):
                raise ValueError('API task identity changed')
            values = []
            for record in (a, b):
                if record['stat'].split(' ', 1)[0] != tid:
                    raise ValueError('task stat PID differs from required TID')
                tail = record['stat'][record['stat'].rfind(')')+2:].split()
                values.append([int(tail[11]), int(tail[12])])
            if any(value < 0 for pair in values for value in pair):
                raise ValueError('negative task CPU counter')
            u, s = [values[1][i]-values[0][i] for i in (0, 1)]
            if min(u, s) < 0:
                raise ValueError('task CPU counter decreased')
            user += u
            system += s
        except (AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
            errors.append(f'{tid}: {exc}')
    return {'status': 'unknown' if errors else 'ok', 'errors': errors,
            'method': 'sum stable /proc/1/task/TID/stat utime/stime; excludes profiler processes',
            'clock_ticks_per_second': clock_ticks_per_second,
            'user_cpu_seconds': None if errors else user/clock_ticks_per_second,
            'system_cpu_seconds': None if errors else system/clock_ticks_per_second,
            'cpu_seconds': None if errors else (user+system)/clock_ticks_per_second,
            'counter_quantization_bound_cpu_seconds': None if errors else 2*len(before)/clock_ticks_per_second}
