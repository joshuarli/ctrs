"""Owned W2 probe lifecycle and live phase boundary helper inside the API namespace."""
import ctypes
import json
import os
from pathlib import Path
import re
import select
import signal
import sys
import tarfile
import time

from counter_specs import probe_definitions, futex_events
ROOT = Path('/tmp/np-count')
TRACE = Path('/sys/kernel/tracing')
SYSLOG_ACTION_READ_ALL = 3
SYSLOG_ACTION_SIZE_BUFFER = 10


def kernel_log():
    libc = ctypes.CDLL(None, use_errno=True)
    libc.klogctl.argtypes = (ctypes.c_int, ctypes.c_void_p, ctypes.c_int)
    libc.klogctl.restype = ctypes.c_int
    size = libc.klogctl(SYSLOG_ACTION_SIZE_BUFFER, None, 0)
    if size < 0:
        raise OSError(ctypes.get_errno(), 'kernel log size query failed')
    if not 0 < size <= 16 * 1024 * 1024:
        raise ValueError('kernel log buffer size outside diagnostic bound')
    buffer = ctypes.create_string_buffer(size)
    length = libc.klogctl(SYSLOG_ACTION_READ_ALL, buffer, size)
    if length < 0:
        raise OSError(ctypes.get_errno(), 'kernel log read failed')
    return buffer.raw[:length].decode('utf-8', errors='replace')


def snapshot(tag):
    tasks = {p.name: {name: (p / name).read_text() for name in ('comm', 'stat', 'status')}
             for p in Path('/proc/1/task').iterdir()}
    if not tasks or any(task['comm'].strip() != tag for task in tasks.values()):
        raise ValueError('API thread tag coverage differs')
    return tasks


def command(line):
    fd = os.open(TRACE / 'kprobe_events', os.O_WRONLY)
    try:
        os.write(fd, (line + '\n').encode())
    finally:
        os.close(fd)


def control(action):
    writer = os.open(ROOT / 'control', os.O_RDWR)
    reader = os.open(ROOT / 'ack', os.O_RDWR | os.O_NONBLOCK)
    try:
        os.write(writer, action.encode() + b'\n')
        if not select.select([reader], [], [], 5)[0] or os.read(reader, 100) != b'ack\n\0':
            raise RuntimeError('missing exact perf control acknowledgement')
    finally:
        os.close(writer)
        os.close(reader)


def main():
    action, tag = sys.argv[1:3]
    if not re.fullmatch(r'np[0-9a-f]{12}', tag):
        raise ValueError('invalid owned trace group')
    definitions = probe_definitions(tag)
    if action == 'prepare':
        ROOT.mkdir()
        tarfile.open('/tmp/np-tools.tgz').extractall('/tmp/np-tools', filter='data')
        os.mkfifo(ROOT / 'control'); os.mkfifo(ROOT / 'ack')
    elif action == 'hardware':
        print(json.dumps({'cpuinfo': Path('/proc/cpuinfo').read_text(),
                          'meminfo': Path('/proc/meminfo').read_text(),
                          'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                          'kernel': list(os.uname()), 'kernel_log': kernel_log()}), flush=True)
    elif action == 'probes':
        if any(':' + tag + '/' in line for line in (TRACE / 'kprobe_events').read_text().splitlines()):
            raise RuntimeError('trace group already exists; refuse adoption')
        (ROOT / 'owned.json').write_text(json.dumps({'tag': tag, 'created': []}))
        created = []
        for definition in definitions:
            command(definition)
            created.append(definition)
            (ROOT / 'owned.json').write_text(json.dumps({'tag': tag, 'created': created}))
        actual = (TRACE / 'kprobe_events').read_text().splitlines()
        if any(definition not in actual for definition in definitions):
            raise RuntimeError('created probe definitions differ')
        print(json.dumps({'owned': created}), flush=True)
    elif action == 'cleanup':
        if not (ROOT / 'owned.json').exists():
            return
        owned = json.loads((ROOT / 'owned.json').read_text())
        if owned['tag'] != tag or any(line not in definitions for line in owned['created']):
            raise RuntimeError('probe ownership receipt mismatch')
        for definition in owned['created']:
            name = definition.split(' ', 1)[0]
            actual = (TRACE / 'kprobe_events').read_text().splitlines()
            matches = [line for line in actual if line.split(' ', 1)[0] == name]
            if matches and matches != [definition]:
                raise RuntimeError('probe definition changed; refuse removal')
            if matches:
                command('-:' + name.split(':', 1)[1])
        if any(':' + tag + '/' in line for line in (TRACE / 'kprobe_events').read_text().splitlines()):
            raise RuntimeError('owned probe remains after cleanup')
        print(json.dumps({'owned_probes_absent': True}), flush=True)
    elif action == 'probe-profile':
        names = set(futex_events(tag).values())
        rows = [line.split() for line in (TRACE / 'kprobe_profile').read_text().splitlines() if line.split()[0] in names]
        if len(rows) != len(names) or any(len(row) != 3 or int(row[-1]) != 0 for row in rows):
            raise RuntimeError('missing probe profile or missed kretprobe instances')
        print(json.dumps({'status': 'ok', 'rows': rows, 'missed': 0}), flush=True)
    elif action == 'launch':
        stat = Path('/proc/self/stat').read_text()
        (ROOT / 'perf-pid.json').write_text(json.dumps({'pid': os.getpid(), 'start': stat[stat.rfind(')')+2:].split()[19]}))
        os.environ['LD_LIBRARY_PATH'] = '/tmp/np-tools/lib/aarch64-linux-gnu'
        os.execv('/tmp/np-tools/usr/bin/perf', sys.argv[3:])
    elif action == 'stop':
        pid = json.loads((ROOT / 'perf-pid.json').read_text())
        proc = Path('/proc') / str(pid['pid'])
        stat = (proc / 'stat').read_text()
        if stat[stat.rfind(')')+2:].split()[19] != pid['start'] or (proc / 'cmdline').read_bytes().split(b'\0')[0] != b'/tmp/np-tools/usr/bin/perf':
            raise RuntimeError('profiler process/start identity changed')
        os.kill(pid['pid'], signal.SIGINT)
    elif action == 'phase':
        enabled = sys.argv[3] == 'on'
        before = snapshot(tag)
        if enabled:
            control('enable')
        begin = time.monotonic()
        capacity = {'online_cpus': Path('/sys/devices/system/cpu/online').read_text().strip(),
                    'mem_total_kib': int(Path('/proc/meminfo').read_text().splitlines()[0].split()[1]),
                    'kernel': os.uname().release}
        print(json.dumps({'event': 'ready', 'tasks': before, 'clock_ticks': os.sysconf('SC_CLK_TCK'),
                          'guest_monotonic': begin, 'guest_capacity': capacity}), flush=True)
        if not select.select([sys.stdin], [], [], 120)[0] or sys.stdin.readline() != 'STOP\n':
            raise RuntimeError('missing bounded workload stop command')
        if enabled:
            control('disable')
        end = time.monotonic()
        print(json.dumps({'event': 'done', 'tasks': snapshot(tag), 'guest_monotonic': end,
                          'counter_window_seconds': end - begin, 'clock': 'guest CLOCK_MONOTONIC'}), flush=True)
    else:
        raise ValueError('unknown helper command')


if __name__ == '__main__':
    main()
