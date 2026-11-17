"""Capture bounded, owned Python attach/detach and futex trace events."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

TRACE = Path('/sys/kernel/tracing')
STATE = Path('/run/ctrs-w2-uprobes')
LIBRARY = Path('/usr/local/lib/libpython3.13.so.1.0')
LIBRARY_SHA256 = '1cf1fea4c287605d994fcde537ad7e6d078bb4325e12a34f19b783a5f2badc3b'
LIBRARY_SIZE = 5306944
BUFFER_KB = 4096
SCHEMA = 'w2-uprobes-v1'


def validate_tag(tag):
    if not isinstance(tag, str) or not re.fullmatch(r'npu[0-9a-f]{12}', tag):
        raise ValueError('tag must be npu plus twelve lowercase hex digits')


def parse_tids(text):
    if not isinstance(text, str) or not re.fullmatch(r'[1-9][0-9]*(,[1-9][0-9]*)*', text):
        raise ValueError('TIDS must be comma-separated positive global TIDs')
    tids = [int(item) for item in text.split(',')]
    if len(tids) > 128 or len(set(tids)) != len(tids) or any(t > 4194304 for t in tids):
        raise ValueError('TIDS must be unique, at most 128, and at most 4194304')
    return tids


def definitions(tag):
    validate_tag(tag)
    u = [f'{kind}:{tag}/{tag}_{name} {LIBRARY}:0x{offset:016x}'
         for name, offset in (('save', 0x177560), ('restore', 0x177a40))
         for kind, name in (('p', name), ('r', name + '_ret'))]
    k = [f'p:{tag}/{tag}_futex __arm64_sys_futex op=+8(%x0):u64',
         f'r4096:{tag}/{tag}_futex_ret __arm64_sys_futex ret=$retval:s64']
    return {'uprobe_events': u, 'kprobe_events': k}


def event_paths(tag):
    return [f'{tag}/{tag}_{name}' for name in
            ('save', 'save_ret', 'restore', 'restore_ret', 'futex', 'futex_ret')]


def pid_filter(tids):
    return ' || '.join(f'common_pid == {tid}' for tid in tids)


def library_identity():
    with LIBRARY.open('rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size != LIBRARY_SIZE:
            raise RuntimeError('pinned library identity or digest mismatch')
        digest = hashlib.sha256(stream.read(LIBRARY_SIZE + 1)).hexdigest()
        after = os.fstat(stream.fileno())
    current = LIBRARY.stat()
    def identity(info):
        return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]
    if (not stat.S_ISREG(before.st_mode) or identity(before) != identity(after) or
            identity(after) != identity(current) or before.st_size != LIBRARY_SIZE or digest != LIBRARY_SHA256):
        raise RuntimeError('pinned library identity or digest mismatch')
    return {'path': str(LIBRARY), 'stat': identity(before), 'sha256': digest}


def _write(path, value):
    fd = os.open(path, os.O_WRONLY)
    try:
        data = (str(value) + '\n').encode()
        if os.write(fd, data) != len(data):
            raise OSError('short tracefs write')
    finally:
        os.close(fd)


def _read_receipt(tag):
    try:
        receipt = json.loads((STATE / (tag + '.json')).read_text())
        tids = receipt['tids']
        if not isinstance(tids, list) or parse_tids(','.join(str(t) for t in tids)) != tids:
            raise ValueError('invalid tids')
        if (receipt['schema'] != SCHEMA or receipt['tag'] != tag or
                receipt['instance'] != str(TRACE / 'instances' / tag) or
                receipt['definitions'] != definitions(tag) or
                receipt['filter'] != pid_filter(tids) or
                receipt['library']['path'] != str(LIBRARY) or
                receipt['library']['sha256'] != LIBRARY_SHA256 or
                len(receipt['library']['stat']) != 5 or
                receipt['library']['stat'][2] != LIBRARY_SIZE or
                set(receipt['formats']) != set(event_paths(tag)) or
                set(receipt['filter_readback']) != set(event_paths(tag)) or
                not receipt['cpus'] or len(set(receipt['cpus'])) != len(receipt['cpus']) or
                any(not re.fullmatch(r'cpu[0-9]+', cpu) for cpu in receipt['cpus']) or
                receipt['phase'] not in ('setup', 'running', 'stopped') or
                receipt['buffer_kb'] != BUFFER_KB or '[mono]' not in receipt['trace_clock'].split()):
            raise ValueError('receipt mismatch')
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise RuntimeError('missing or invalid ownership receipt') from exc
    return receipt


def _check_definitions(tag, expected):
    for filename, wanted in expected.items():
        lines = (TRACE / filename).read_text().splitlines()
        group_lines = [line for line in lines if re.match(r'^[pr][0-9]*:' + re.escape(tag) + r'/', line)]
        if sorted(group_lines) != sorted(wanted):
            raise RuntimeError('owned probe definitions changed; refuse trace mutation')


def _owned(tag):
    validate_tag(tag)
    receipt = _read_receipt(tag)
    instance = TRACE / 'instances' / tag
    if not instance.is_dir():
        raise RuntimeError('owned instance missing')
    _check_definitions(tag, receipt['definitions'])
    return receipt, instance


def setup(tag, tids_text):
    validate_tag(tag)
    tids = parse_tids(tids_text)
    instance = TRACE / 'instances' / tag
    marker = STATE / (tag + '.json')
    if marker.exists() or instance.exists():
        raise RuntimeError('receipt or instance already exists; refuse adoption')
    defs = definitions(tag)
    for filename in defs:
        if any(re.match(r'^[pr][0-9]*:' + re.escape(tag) + r'/', line)
               for line in (TRACE / filename).read_text().splitlines()):
            raise RuntimeError('probe group already exists; refuse adoption')
    identity = library_identity()
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    created, made_instance, made_marker = [], False, False
    try:
        with marker.open('x') as output:
            made_marker = True
            output.write(json.dumps({'schema': SCHEMA, 'tag': tag, 'pending': True}))
        instance.mkdir()
        made_instance = True
        _write(instance / 'tracing_on', 0)
        _write(instance / 'trace_clock', 'mono')
        clock = (instance / 'trace_clock').read_text().strip()
        if '[mono]' not in clock.split():
            raise RuntimeError('monotonic trace clock unavailable')
        _write(instance / 'buffer_size_kb', BUFFER_KB)
        if int((instance / 'buffer_size_kb').read_text().strip()) != BUFFER_KB:
            raise RuntimeError('trace buffer size was not selected')
        for filename, lines in defs.items():
            for line in lines:
                _write(TRACE / filename, line)
                created.append((filename, line))
        _check_definitions(tag, defs)
        if library_identity() != identity:
            raise RuntimeError('pinned library changed during setup')
        filt = pid_filter(tids)
        formats, filter_readback = {}, {}
        cpus = sorted(p.name for p in (instance / 'per_cpu').glob('cpu[0-9]*')
                      if re.fullmatch(r'cpu[0-9]+', p.name))
        if not cpus:
            raise RuntimeError('missing per-CPU trace buffers')
        for event in event_paths(tag):
            root = instance / 'events' / event
            formats[event] = (root / 'format').read_text()
            if not formats[event].strip():
                raise RuntimeError('empty event format')
            _write(root / 'enable', 0)
            _write(root / 'filter', filt)
            filter_readback[event] = (root / 'filter').read_text().strip()
            if ''.join(filter_readback[event].split()) != ''.join(filt.split()):
                raise RuntimeError('event filter readback mismatch')
        receipt = {'schema': SCHEMA, 'tag': tag, 'tids': tids, 'instance': str(instance),
                   'definitions': defs, 'filter': filt, 'library': identity,
                   'formats': formats, 'filter_readback': filter_readback, 'cpus': cpus,
                   'trace_clock': clock, 'buffer_kb': BUFFER_KB, 'phase': 'setup'}
        marker.write_text(json.dumps(receipt, sort_keys=True))
        return {'status': 'setup', 'receipt': receipt}
    except Exception:
        try:
            partial = {filename: [line for f, line in created if f == filename] for filename in defs}
            _check_definitions(tag, partial)
            for filename, line in reversed(created):
                _write(TRACE / filename, '-:' + line.split()[0].split(':', 1)[1])
            if made_instance:
                instance.rmdir()
            if made_marker:
                marker.unlink(missing_ok=True)
        except Exception as exc:
            raise RuntimeError('setup rollback incomplete; receipt retained') from exc
        raise


def start(tag):
    receipt, instance = _owned(tag)
    if receipt['phase'] != 'setup':
        raise RuntimeError('capture cannot be restarted')
    if library_identity() != receipt['library']:
        raise RuntimeError('pinned library inode changed')
    if (instance / 'tracing_on').read_text().strip() != '0':
        raise RuntimeError('instance is not stopped')
    if '[mono]' not in (instance / 'trace_clock').read_text().split() or int((instance / 'buffer_size_kb').read_text().strip()) != BUFFER_KB:
        raise RuntimeError('trace clock or buffer changed')
    for event in event_paths(tag):
        root = instance / 'events' / event
        if ((root / 'filter').read_text().strip() != receipt['filter_readback'][event] or
                (root / 'format').read_text() != receipt['formats'][event] or
                (root / 'enable').read_text().strip() != '0'):
            raise RuntimeError('event configuration changed')
    receipt['phase'] = 'running'
    (STATE / (tag + '.json')).write_text(json.dumps(receipt, sort_keys=True))
    try:
        for event in event_paths(tag):
            _write(instance / 'events' / event / 'enable', 1)
        _write(instance / 'tracing_on', 1)
    except Exception:
        _write(instance / 'tracing_on', 0)
        for event in event_paths(tag):
            _write(instance / 'events' / event / 'enable', 0)
        raise
    return {'status': 'started', 'tag': tag}


def profile(text, tag, kind):
    names = {path.split('/')[1] for path in event_paths(tag)}
    names = {name for name in names if ('futex' in name) == (kind == 'kprobe')}
    rows, errors = {}, []
    for line in text.splitlines():
        parts = line.split()
        index = 0 if kind == 'kprobe' else 1
        if len(parts) <= index or parts[index] not in names:
            continue
        name = parts[index]
        if (name in rows or len(parts) != 3 or not parts[2].isdigit() or
                (kind == 'kprobe' and (not parts[1].isdigit() or parts[2] != '0')) or
                (kind == 'uprobe' and parts[0] != str(LIBRARY))):
            errors.append('invalid or duplicate profile row: ' + name)
        else:
            rows[name] = line
    errors.extend('missing profile row: ' + name for name in sorted(names - rows.keys()))
    return {'rows': rows, 'errors': errors}


def stop(tag):
    receipt, instance = _owned(tag)
    if receipt['phase'] != 'running' or (instance / 'tracing_on').read_text().strip() != '1':
        raise RuntimeError('instance is not running')
    _write(instance / 'tracing_on', 0)
    for event in event_paths(tag):
        _write(instance / 'events' / event / 'enable', 0)
    receipt['phase'] = 'stopped'
    (STATE / (tag + '.json')).write_text(json.dumps(receipt, sort_keys=True))
    stats, errors = {}, []
    try:
        clock = (instance / 'trace_clock').read_text().split()
        if '[mono]' not in clock:
            errors.append('trace clock changed or unavailable')
    except OSError:
        errors.append('trace clock changed or unavailable')
    try:
        if int((instance / 'buffer_size_kb').read_text().strip()) != receipt['buffer_kb']:
            errors.append('trace buffer size changed or unavailable')
    except (OSError, ValueError):
        errors.append('trace buffer size changed or unavailable')
    for event in event_paths(tag):
        root = instance / 'events' / event
        if ((root / 'filter').read_text().strip() != receipt['filter_readback'][event] or
                (root / 'format').read_text() != receipt['formats'][event]):
            errors.append('event configuration changed: ' + event)
    cpus = sorted(p for p in (instance / 'per_cpu').glob('cpu[0-9]*')
                  if re.fullmatch(r'cpu[0-9]+', p.name))
    if sorted(p.name for p in cpus) != receipt['cpus']:
        errors.append('per-CPU trace buffer coverage changed')
    for cpu in cpus:
        try:
            raw = (cpu / 'stats').read_text()
            stats[cpu.name] = raw
            for field in ('overrun', 'commit overrun', 'dropped events'):
                matches = re.findall(r'^' + re.escape(field) + r':\s*([0-9]+)\s*$', raw, re.M)
                if matches != ['0']:
                    errors.append(cpu.name + ': missing or nonzero ' + field)
        except OSError:
            errors.append(cpu.name + ': missing statistics')
    profiles = {}
    for kind in ('kprobe', 'uprobe'):
        try:
            profiles[kind] = profile((TRACE / (kind + '_profile')).read_text(), tag, kind)
        except OSError:
            profiles[kind] = {'rows': {}, 'errors': ['profile unavailable']}
        errors.extend(profiles[kind]['errors'])
    return {'status': 'invalid' if errors else 'ok', 'errors': errors,
            'raw_trace': (instance / 'trace').read_text(), 'per_cpu_stats': stats,
            'profiles': profiles, 'receipt': receipt}


def cleanup(tag):
    receipt, instance = _owned(tag)
    if (instance / 'tracing_on').read_text().strip() not in ('0', '1'):
        raise RuntimeError('unknown tracing state')
    _write(instance / 'tracing_on', 0)
    for event in event_paths(tag):
        _write(instance / 'events' / event / 'enable', 0)
    for filename, lines in receipt['definitions'].items():
        for line in lines:
            _write(TRACE / filename, '-:' + line.split()[0].split(':', 1)[1])
    instance.rmdir()
    (STATE / (tag + '.json')).unlink()
    return {'status': 'cleaned', 'tag': tag}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('setup', 'start', 'stop', 'cleanup'))
    parser.add_argument('tag')
    parser.add_argument('tids', nargs='?')
    args = parser.parse_args(argv)
    if (args.action == 'setup') != (args.tids is not None):
        parser.error('TIDS is required only for setup')
    result = setup(args.tag, args.tids) if args.action == 'setup' else globals()[args.action](args.tag)
    print(json.dumps(result, sort_keys=True), flush=True)
    return 2 if result['status'] == 'invalid' else 0


if __name__ == '__main__':
    sys.exit(main())
