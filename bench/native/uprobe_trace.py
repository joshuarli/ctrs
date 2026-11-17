"""Classify futex events against exported Python attach/detach spans."""
from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import Enum
import re

from diagnostics.w2_uprobes_guest import parse_tids, validate_tag


class _Position(Enum):
    UNKNOWN = 'unknown'
    OUTSIDE = 'outside'


@dataclass(frozen=True)
class _Export:
    name: str
    started_ns: int


@dataclass(frozen=True)
class _Futex:
    category: str
    started_ns: int


_LINE = re.compile(r'^\s*(\S+)-(\d+)\s+\[(\d+)\]\s+\S+\s+(\d+)\.([0-9]{1,9}):\s+(\w+):\s+(.*)$')


def analyze(capture, *, expected_comm):
    """Require complete capture coverage; return counts and explicit phase edges, never CPU cost."""
    if capture['status'] != 'ok' or capture['errors']:
        raise ValueError('capture coverage is invalid')
    receipt = capture['receipt']
    tag = receipt['tag']
    validate_tag(tag)
    tids = set(parse_tids(','.join(map(str, receipt['tids']))))
    cpus = {int(value.removeprefix('cpu')) for value in receipt['cpus']}
    exports = {pid: _Position.UNKNOWN for pid in tids}
    futexes = {pid: _Position.UNKNOWN for pid in tids}
    counts, categories, edges = Counter(), Counter(), Counter()
    returns, operations = defaultdict(Counter), defaultdict(Counter)
    intervals = Counter()
    observed, errors = set(), []
    first_ns = last_ns = None
    for line in capture['raw_trace'].splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        match = _LINE.fullmatch(line)
        if not match:
            errors.append('unparsed trace line')
            continue
        comm, pid, cpu, seconds, fraction, event, payload = match.groups()
        pid, cpu = int(pid), int(cpu)
        timestamp = int(seconds) * 1_000_000_000 + int(fraction.ljust(9, '0'))
        if comm != expected_comm or pid not in tids or cpu not in cpus or not event.startswith(tag + '_'):
            errors.append('foreign task, CPU or event')
            continue
        observed.add(pid)
        kind = event[len(tag) + 1:]
        counts[kind] += 1
        if first_ns is None:
            first_ns = timestamp
        last_ns = timestamp
        current = exports[pid]
        if kind in ('save', 'restore'):
            if isinstance(current, _Export):
                errors.append('nested exported calls')
            exports[pid] = _Export(kind, timestamp)
        elif kind in ('save_ret', 'restore_ret'):
            name = kind.removesuffix('_ret')
            if current is _Position.UNKNOWN:
                edges['leading_export_return'] += 1
            elif not isinstance(current, _Export):
                errors.append('unmatched interior exported return')
            elif current.name != name:
                errors.append('exported return kind mismatch')
            else:
                if timestamp < current.started_ns:
                    errors.append('negative exported interval')
                intervals[name] += 1
            exports[pid] = _Position.OUTSIDE
        elif kind == 'futex':
            if isinstance(futexes[pid], _Futex):
                errors.append('nested futex calls')
            operation = re.search(r'\bop=(0x[0-9a-fA-F]+|[0-9]+)', payload)
            if not operation:
                errors.append('missing futex operation')
                continue
            category = current.name if isinstance(current, _Export) else (
                'boundary_unknown' if current is _Position.UNKNOWN else 'outside_exports')
            categories[category] += 1
            operations[category][str(int(operation[1], 0))] += 1
            futexes[pid] = _Futex(category, timestamp)
        elif kind == 'futex_ret':
            result = re.search(r'\bret=(-?(?:0x[0-9a-fA-F]+|[0-9]+))', payload)
            if not result:
                errors.append('missing futex result')
                continue
            previous = futexes[pid]
            if previous is _Position.UNKNOWN:
                edges['leading_futex_return'] += 1
            elif not isinstance(previous, _Futex):
                errors.append('unmatched interior futex return')
            else:
                if timestamp < previous.started_ns:
                    errors.append('negative futex interval')
                returns[previous.category][str(int(result[1], 0))] += 1
                intervals['futex_' + previous.category] += 1
            futexes[pid] = _Position.OUTSIDE
        else:
            errors.append('unknown event')
    if observed != tids:
        errors.append('unobserved required trace tasks')
    edges['trailing_export_entry'] = sum(isinstance(value, _Export) for value in exports.values())
    edges['trailing_futex_entry'] = sum(isinstance(value, _Futex) for value in futexes.values())
    return {'status': 'invalid' if errors else 'ok', 'errors': errors,
            'events': dict(counts), 'futex_entry_categories': dict(categories),
            'futex_ops': {key: dict(value) for key, value in operations.items()},
            'futex_returns': {key: dict(value) for key, value in returns.items()},
            'phase_edges': dict(edges), 'complete_interval_count': dict(intervals),
            'trace_elapsed_seconds': (last_ns - first_ns) / 1e9 if first_ns is not None else None,
            'cpu_cost_attribution': False, 'qualification_eligible': False}
