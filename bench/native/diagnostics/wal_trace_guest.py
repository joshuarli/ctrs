"""Owned tracefs capture for PostgreSQL fdatasync and guest block flushes."""
import argparse
import glob
import json
import os
from pathlib import Path
import re
import stat
import sys

TRACE = Path('/sys/kernel/tracing')
STATE = Path('/tmp')
SCHEMA = 'npwal-trace-v1'
LOSS_FIELDS = ('overrun', 'commit overrun', 'dropped events')
TAG_RE = re.compile(r'npwal[0-9a-f]{12}\Z')
_NO_PID = object()


def validate(tag, pid=_NO_PID):
    if not isinstance(tag, str) or not TAG_RE.fullmatch(tag):
        raise ValueError('tag must be npwal plus twelve lowercase hex digits')
    if pid is not _NO_PID and (not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1 or pid > 4194304):
        raise ValueError('backend PID must be an explicit guest-global PID in 2..4194304')


def event_definitions(tag):
    group = 'npwal_' + tag[5:]
    return [f'p:{group}/fdatasync __arm64_sys_fdatasync',
            f'r:{group}/fdatasync_ret __arm64_sys_fdatasync ret=$retval']


def marker_path(tag, state=STATE):
    return state / (tag + '.json')


def _write(path, value):
    fd = os.open(path, os.O_WRONLY)
    try:
        os.write(fd, (str(value) + '\n').encode())
    finally:
        os.close(fd)


def _read_json(path):
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise RuntimeError('missing or invalid ownership receipt') from exc
    if not isinstance(value, dict):
        raise RuntimeError('invalid ownership receipt')
    return value


def _device(path=Path('/dev/vda')):
    info = path.stat()
    if not stat.S_ISBLK(info.st_mode):
        raise RuntimeError('/dev/vda is not a block device')
    return f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}'


def _format(path):
    value = path.read_text()
    if 'dev_t dev;' not in value or 'rwbs[8]' not in value:
        raise RuntimeError(f'required block event fields absent: {path}')
    return value


def _owned(tag, trace=TRACE, state=STATE):
    validate(tag)
    instance = trace / 'instances' / tag
    marker = marker_path(tag, state)
    receipt = _read_json(marker)
    expected_defs = event_definitions(tag)
    if receipt.get('schema') != SCHEMA or receipt.get('tag') != tag or receipt.get('instance') != str(instance) or receipt.get('definitions') != expected_defs:
        raise RuntimeError('ownership receipt identity mismatch')
    validate(tag, receipt.get('pid'))
    group = 'npwal_' + tag[5:]
    flush_filter = f'dev == {receipt.get("device")} && rwbs ~ "*F*"'
    expected_filters = {'fdatasync': f'common_pid == {receipt["pid"]}',
                        'fdatasync_ret': f'common_pid == {receipt["pid"]}',
                        'block_rq_issue': flush_filter, 'block_rq_complete': flush_filter}
    expected_scope = {'backend_pid': receipt['pid'], 'device': '/dev/vda',
                      'device_number': receipt.get('device'), 'instance': str(instance)}
    if (not isinstance(receipt.get('device'), str) or
            not re.fullmatch(r'[0-9]+:[0-9]+', receipt['device']) or
            receipt.get('filters') != expected_filters or receipt.get('scope') != expected_scope):
        raise RuntimeError('ownership receipt scope or filters mismatch')
    if not instance.is_dir():
        raise RuntimeError('owned tracefs instance is missing')
    return receipt, instance, marker


def _global_definitions(trace):
    try:
        return (trace / 'kprobe_events').read_text().splitlines()
    except OSError as exc:
        raise RuntimeError('cannot inspect global kprobe ownership') from exc


def _remove_definition(trace, definition):
    name = definition.split(' ', 1)[0].split(':', 1)[1]
    command = '-:' + name
    _write(trace / 'kprobe_events', command)


def _rollback(trace, instance, definitions):
    # Remove only definitions this invocation successfully added and can still identify.
    for definition in reversed(definitions):
        actual = [line for line in _global_definitions(trace)
                  if line.split(' ', 1)[0] == definition.split(' ', 1)[0]]
        if actual == [definition]:
            _remove_definition(trace, definition)
    if instance.exists():
        instance.rmdir()


def setup(tag, pid, trace=TRACE, state=STATE):
    validate(tag, pid)
    instance = trace / 'instances' / tag
    marker = marker_path(tag, state)
    definitions = event_definitions(tag)
    if marker.exists():
        raise RuntimeError('ownership receipt already exists; refuse adoption')
    if instance.exists():
        raise RuntimeError('tracefs instance already exists; refuse adoption')
    global_lines = _global_definitions(trace)
    names = {line.split(' ', 1)[0] for line in global_lines}
    if any(definition.split(' ', 1)[0] in names for definition in definitions):
        raise RuntimeError('namespaced kprobe name already exists; refuse adoption')
    device = _device()
    block_events = ('block/block_rq_issue', 'block/block_rq_complete')
    formats = {name: _format(trace / 'events' / name / 'format') for name in block_events}
    owned_defs = []
    made_instance = False
    made_marker = False
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        with marker.open('x') as output:
            made_marker = True
            output.write(json.dumps({'schema': SCHEMA, 'tag': tag, 'pid': pid,
                                     'instance': str(instance), 'definitions': definitions,
                                     'device': device, 'formats': formats}, sort_keys=True))
        instance.mkdir()
        made_instance = True
        for definition in definitions:
            _write(trace / 'kprobe_events', definition)
            owned_defs.append(definition)
        actual = _global_definitions(trace)
        if any(actual.count(definition) != 1 for definition in definitions):
            raise RuntimeError('created kprobe definitions differ from requested definitions')
        formats.update({name: (instance / 'events' / name / 'format').read_text()
                        for name in (f'npwal_{tag[5:]}/fdatasync', f'npwal_{tag[5:]}/fdatasync_ret')})
        for event in (f'npwal_{tag[5:]}/fdatasync', f'npwal_{tag[5:]}/fdatasync_ret'):
            _write(instance / 'events' / event / 'filter', f'common_pid == {pid}')
        flush_filter = f'dev == {device} && rwbs ~ "*F*"'
        for event in block_events:
            _write(instance / 'events' / event / 'filter', flush_filter)
        # A fresh instance starts disabled and empty; no global trace buffer is touched.
        for event in (f'npwal_{tag[5:]}/fdatasync', f'npwal_{tag[5:]}/fdatasync_ret', *block_events):
            _write(instance / 'events' / event / 'enable', 0)
        _write(instance / 'tracing_on', 0)
        receipt = _read_json(marker)
        receipt['filters'] = {
            'fdatasync': f'common_pid == {pid}',
            'fdatasync_ret': f'common_pid == {pid}',
            'block_rq_issue': flush_filter,
            'block_rq_complete': flush_filter,
        }
        receipt['scope'] = {'backend_pid': pid, 'device': '/dev/vda', 'device_number': device,
                            'instance': str(instance)}
        marker.write_text(json.dumps(receipt, sort_keys=True))
        return {'status': 'setup', 'scope': receipt['scope'], 'filters': receipt['filters'], 'formats': formats}
    except Exception:
        if made_instance:
            try:
                _rollback(trace, instance, owned_defs)
            except OSError:
                pass
        if made_marker:
            marker.unlink(missing_ok=True)
        raise


def start(tag, trace=TRACE, state=STATE):
    receipt, instance, _ = _owned(tag, trace, state)
    if _global_definitions(trace).count(receipt['definitions'][0]) != 1 or _global_definitions(trace).count(receipt['definitions'][1]) != 1:
        raise RuntimeError('owned kprobe definition changed; refuse start')
    if (instance / 'tracing_on').read_text().strip() != '0':
        raise RuntimeError('owned instance is already running or has unknown tracing state')
    events = [f'npwal_{tag[5:]}/fdatasync', f'npwal_{tag[5:]}/fdatasync_ret',
              'block/block_rq_issue', 'block/block_rq_complete']
    try:
        for event in events:
            _write(instance / 'events' / event / 'enable', 1)
        _write(instance / 'tracing_on', 1)
    except Exception:
        try:
            _write(instance / 'tracing_on', 0)
            for event in events:
                _write(instance / 'events' / event / 'enable', 0)
        except OSError:
            pass
        raise
    return {'status': 'started', 'scope': receipt['scope']}


def loss_summary(stats_by_cpu):
    """Return loss=0 only when every CPU has all required, valid zero counters."""
    errors, normalized = [], {}
    if not stats_by_cpu:
        errors.append('no per-CPU trace statistics')
    for cpu, raw in stats_by_cpu.items():
        values = {}
        if raw is None:
            errors.append(f'cpu{cpu}: missing per-CPU stats file')
            normalized[str(cpu)] = values
            continue
        for field in LOSS_FIELDS:
            match = re.search(r'^' + re.escape(field) + r':\s*([0-9]+)\s*$', raw, re.MULTILINE)
            if match is None:
                errors.append(f'cpu{cpu}: missing or malformed {field}')
            else:
                values[field] = int(match.group(1))
                if values[field] != 0:
                    errors.append(f'cpu{cpu}: {field}={values[field]}')
        normalized[str(cpu)] = values
    if any('=' in error for error in errors):
        return {'status': 'loss', 'errors': errors, 'per_cpu': normalized}
    if errors:
        return {'status': 'unknown', 'errors': errors, 'per_cpu': normalized}
    return {'status': 'ok', 'errors': [], 'per_cpu': normalized}


def stop(tag, trace=TRACE, state=STATE):
    receipt, instance, _ = _owned(tag, trace, state)
    if (instance / 'tracing_on').read_text().strip() != '1':
        raise RuntimeError('owned instance is not running; refuse stop')
    _write(instance / 'tracing_on', 0)
    events = [f'npwal_{tag[5:]}/fdatasync', f'npwal_{tag[5:]}/fdatasync_ret',
              'block/block_rq_issue', 'block/block_rq_complete']
    for event in events:
        _write(instance / 'events' / event / 'enable', 0)
    raw_trace = (instance / 'trace').read_text()
    stats = {}
    for path in sorted(Path(p) for p in glob.glob(str(instance / 'per_cpu' / 'cpu*'))):
        match = re.fullmatch(r'cpu([0-9]+)', path.name)
        if match:
            stats_path = path / 'stats'
            stats[match.group(1)] = stats_path.read_text() if stats_path.is_file() else None
    loss = loss_summary(stats)
    result = {'status': loss['status'], 'scope': receipt['scope'], 'identity': {
        'tag': tag, 'backend_pid': receipt['pid'], 'definitions': receipt['definitions']},
        'raw_trace': raw_trace, 'per_cpu_loss': loss, 'event_formats': receipt['formats'],
        'filters': receipt['filters']}
    return result


def cleanup(tag, trace=TRACE, state=STATE):
    receipt, instance, marker = _owned(tag, trace, state)
    if (instance / 'tracing_on').read_text().strip() not in ('0', '1'):
        raise RuntimeError('owned instance tracing state is unknown')
    _write(instance / 'tracing_on', 0)
    events = [f'npwal_{tag[5:]}/fdatasync', f'npwal_{tag[5:]}/fdatasync_ret',
              'block/block_rq_issue', 'block/block_rq_complete']
    for event in events:
        _write(instance / 'events' / event / 'enable', 0)
    lines = _global_definitions(trace)
    for definition in receipt['definitions']:
        name = definition.split(' ', 1)[0]
        matches = [line for line in lines if line.split(' ', 1)[0] == name]
        if matches != [definition]:
            raise RuntimeError('owned kprobe changed or missing; refuse removal')
        _remove_definition(trace, definition)
        lines = _global_definitions(trace)
    instance.rmdir()
    marker.unlink()
    return {'status': 'cleaned', 'tag': tag, 'owned_events_removed': receipt['definitions']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('setup', 'start', 'stop', 'cleanup'))
    parser.add_argument('tag')
    parser.add_argument('pid', nargs='?', type=int)
    args = parser.parse_args(argv)
    if args.action == 'setup':
        if args.pid is None:
            parser.error('setup requires the explicit guest-global PostgreSQL backend PID')
        result = setup(args.tag, args.pid)
    elif args.pid is not None:
        parser.error('PID is accepted only by setup')
    elif args.action == 'start':
        result = start(args.tag)
    elif args.action == 'stop':
        result = stop(args.tag)
    else:
        result = cleanup(args.tag)
    print(json.dumps(result, sort_keys=True), flush=True)
    if args.action == 'stop' and result['status'] != 'ok':
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
