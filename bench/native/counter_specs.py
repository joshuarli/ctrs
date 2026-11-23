"""Pinned W2 ARM64 probe definitions and ordered perf selector contract."""
import re

VERSION = 'w2-counters-v2-futex-commands'
WAKE_VERSION = 'w2-counters-v1-wake-entry'
KRETPROBE_MAXACTIVE = 4096
SYSCALLS = ('futex', 'read', 'write', 'epoll_pwait', 'recvfrom', 'sendto')
FUTEX_SELECTORS = (
    ('enter_futex', 'all', None),
    ('enter_futex', 'wait', 'op == 0 || op == 128 || op == 256 || op == 384'),
    ('enter_futex', 'wake', 'op == 1 || op == 129 || op == 257 || op == 385'),
    ('enter_futex', 'wait_bitset', 'op == 9 || op == 137 || op == 265 || op == 393'),
    ('exit_futex', 'returns', None),
    ('exit_futex', 'eagain', 'result == -11'),
    ('exit_futex', 'timeout', 'result == -110'),
    ('exit_futex', 'zero', 'result == 0'),
    ('exit_futex', 'positive', 'result > 0'),
)


def validate_tag(tag):
    if not re.fullmatch(r'np[0-9a-f]{12}', tag):
        raise ValueError('invalid owned trace group')


def futex_events(tag):
    validate_tag(tag)
    return {kind: tag + '_' + kind for kind in ('enter_futex', 'exit_futex')}


def futex_probe_definitions(tag):
    names = futex_events(tag)
    return [f'p:{tag}/{names["enter_futex"]} __arm64_sys_futex op=+8(%x0):u32',
            f'r{KRETPROBE_MAXACTIVE}:{tag}/{names["exit_futex"]} __arm64_sys_futex result=$retval:s64']


def probe_definitions(tag):
    entry, returned = futex_probe_definitions(tag)
    definitions = [entry]
    definitions.extend(f'p:{tag}/enter_{name} __arm64_sys_{name}' for name in SYSCALLS if name != 'futex')
    definitions.append(returned)
    return definitions


def selectors(tag):
    names = futex_events(tag)
    result = [{'label': name, 'event': name, 'filter': None} for name in ('task-clock', 'context-switches', 'cpu-migrations')]
    result.extend({'label': name + '_calls', 'event': tag + ':enter_' + name, 'filter': None} for name in SYSCALLS if name != 'futex')
    result.append({'label': 'api_generated_wakes', 'event': 'sched:sched_waking', 'filter': None})
    result.extend({'label': 'futex_' + label, 'event': tag + ':' + names[kind], 'filter': expression}
                  for kind, label, expression in FUTEX_SELECTORS)
    return result


def wake_selectors(tag):
    return [selector for selector in selectors(tag)
            if selector['label'] in ('api_generated_wakes', 'futex_wake')]
