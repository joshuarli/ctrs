"""Pure interpretation of bounded W10 host probes and guest clock brackets."""
import errno
import hashlib
import math
import re
import urllib.error
from datetime import datetime, timedelta, timezone
from ipaddress import IPv4Address


def transport_error(exc):
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    return repr(exc), reason.errno if isinstance(reason, OSError) else None


def classify_failures(attempts, interrupted_ns, recovered_ns):
    expected, unexpected, host_address_errors = [], [], []
    for attempt in attempts:
        if attempt['ok']:
            continue
        if attempt.get('error_errno') == errno.EADDRNOTAVAIL:
            host_address_errors.append(attempt)
        if (not attempt.get('invalid_response')
                and attempt['ended_ns'] >= interrupted_ns and attempt['started_ns'] <= recovered_ns):
            expected.append(attempt)
        else:
            unexpected.append(attempt)
    return {'expected_outage_errors': expected, 'unexpected_errors': unexpected,
            'host_address_errors': host_address_errors,
            'host_client_valid': not host_address_errors}


def workload_metrics(attempts, interrupted_ns, recovered_ns, *, require_reads, require_writes):
    healthy = [attempt for attempt in attempts if attempt['ok'] and attempt['ended_ns'] < interrupted_ns]
    recovered = [attempt for attempt in attempts if attempt['ok'] and attempt['started_ns'] >= recovered_ns]
    for phase in (healthy, recovered):
        kinds = {attempt['kind'] for attempt in phase}
        if (require_reads and 'read' not in kinds) or (require_writes and 'write' not in kinds):
            raise ValueError('W10 needs completed load before interruption and after recovery')
    elapsed = sorted(attempt['ended_ns'] - attempt['started_ns'] for attempt in recovered)
    return {'recovered_p99_ms': elapsed[math.ceil(.99 * len(elapsed)) - 1] / 1e6,
            'recovered_requests_ok': len(recovered)}


def verify_persisted_items(rows, acknowledged, uncertain):
    original = {f'item-{i}': (i, hashlib.md5(str(i).encode()).hexdigest()) for i in range(1, 501)}
    allowed = {item['name']: item['payload'] for item in uncertain}
    required = original | {item['name']: (item['id'], item['payload']) for item in acknowledged}
    if len(required) != len(original) + len(acknowledged) or len(allowed) != len(uncertain) or allowed.keys() & required.keys():
        raise ValueError('duplicate attempted write identity')
    seen_names, seen_ids = set(), set()
    for identity, name, payload in rows:
        if type(identity) is not int or identity <= 0 or identity in seen_ids or name in seen_names:
            raise ValueError('duplicate or invalid persisted item identity')
        seen_names.add(name)
        seen_ids.add(identity)
        if name in required:
            if required[name] != (identity, payload):
                raise ValueError(f'persisted acknowledged item differs: {name}')
        elif name not in allowed or identity <= 500 or allowed[name] != payload:
            raise ValueError(f'unexpected persisted item: {name}')
    if required.keys() - seen_names:
        raise ValueError('persisted acknowledged items are missing')
    return len(seen_names & allowed.keys())


def clock_bracket(samples):
    if not samples:
        raise ValueError('no guest clock samples')
    sample = min(samples, key=lambda value: value['host_end_ns'] - value['host_begin_ns'])
    if sample['host_end_ns'] < sample['host_begin_ns']:
        raise ValueError('host clock moved backwards')
    return {'guest_minus_host_ns': sample['guest_ns'] - (sample['host_begin_ns'] + sample['host_end_ns']) // 2,
            'uncertainty_ns': (sample['host_end_ns'] - sample['host_begin_ns'] + 1) // 2}


def recovery_intervals(events):
    begin = events['start_command_begin_ns']
    returned = events['start_command_returned_ns']
    success = events['first_success_ns']
    if returned < begin or success < begin:
        raise ValueError('recovery events out of order')
    return {'start_command_s': (returned - begin) / 1e9,
            'restart_to_first_success_s': (success - begin) / 1e9,
            'command_and_ready_s': (max(success, returned) - begin) / 1e9,
            'after_command_to_first_success_s': max(0, success - returned) / 1e9,
            'success_preceded_command_return': success < returned}


REFUSAL_EVENT = re.compile(
    r'(\S+) DEBUG\s+guest refusal (cached|cache first hit|cache expired) ip=([\d.]+) port=(\d+)'
    r'(?: hits=(\d+) age_ms=(\d+))?(?: op=\S+)?\s*'
)


def api_backend(container, project):
    labels = container['Config']['Labels']
    if (labels.get('com.docker.compose.project') != project
            or labels.get('com.docker.compose.service') != 'api'):
        raise ValueError('W10 refusal trace requires the owned API container')
    settings = container['NetworkSettings']
    network, = settings['Networks'].values()
    binding, = settings['Ports']['8000/tcp']
    if binding['HostIp'] != '127.0.0.1' or not int(binding['HostPort']):
        raise ValueError('W10 refusal trace requires the published loopback API port')
    return {'container': container['Id'], 'ip': str(IPv4Address(network['IPAddress'])), 'port': 8000}


def refusal_recovery_trace(timeline, attempts, lines, backend):
    interrupted = timeline['kill_command_begin_ns']
    begin, returned = timeline['start_command_begin_ns'], timeline['start_command_returned_ns']
    if not interrupted <= begin <= returned <= timeline['first_success_ns']:
        raise ValueError('W10 refusal trace has inconsistent recovery markers')
    exact_reads = [attempt for attempt in attempts if attempt['kind'] == 'read' and attempt['ok'] is True
                   and returned <= attempt['started_ns'] <= attempt['ended_ns']]
    if not exact_reads:
        raise ValueError('W10 refusal trace has no exact post-restart read')
    first = min(exact_reads, key=lambda attempt: attempt['ended_ns'])
    offsets = [attempt['wall_ns'] - attempt['ended_ns'] for attempt in attempts
               if begin <= attempt['ended_ns'] <= first['ended_ns']]
    low, high = min(offsets), max(offsets)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    events = []
    for line in lines:
        match = REFUSAL_EVENT.fullmatch(line)
        if not match:
            continue
        timestamp, kind, ip, port, hits, age = match.groups()
        if (ip, int(port)) != (backend['ip'], backend['port']):
            continue
        elapsed = datetime.fromisoformat(timestamp) - epoch
        wall_ns = (elapsed // timedelta(microseconds=1)) * 1000
        earliest, latest = wall_ns - high, wall_ns + 999_999 - low
        if latest < interrupted or earliest > first['ended_ns']:
            continue
        event = {'event': kind, 'wall_time': timestamp,
                 'since_restart_start_ms_bounds': [(value - begin) / 1e6 for value in (earliest, latest)]}
        if hits is not None:
            event.update(hits=int(hits), age_ms=int(age))
        events.append(event)
    return {'backend': backend, 'clock_offset_observed_range_ns': [low, high],
            'first_exact_read_scope': first['scope'],
            'first_exact_read_start_ms': (first['started_ns'] - begin) / 1e6,
            'first_exact_read_end_ms': (first['ended_ns'] - begin) / 1e6,
            'start_command_return_ms': (returned - begin) / 1e6, 'events': events}


def owned_ctrs_processes(manifest, socket_path, child_pid, binary_sha256):
    if manifest['engine'] != 'ctrs' or manifest['socket'] != socket_path:
        raise ValueError('recovery socket is not owned by ctrs')
    processes = manifest['required_processes']
    roles = {process['role']: process for process in processes}
    if len(processes) != 2 or set(roles) != {'daemon', 'vm'}:
        raise ValueError('recovery needs one owned daemon and one VM helper')
    daemon, vm = roles['daemon'], roles['vm']
    if (daemon['pid'] != child_pid or daemon['executable']['sha256'] != binary_sha256
            or daemon['pid'] == vm['pid']):
        raise ValueError('recovery daemon is not the requested child')
    if {asset['path'].rsplit('/', 1)[-1] for asset in vm['boot_assets']} != {'Image', 'initramfs.cpio'}:
        raise ValueError('recovery needs both booted guest artifacts')
    return roles


def verify_ctrs_restart(before, after, disk_before, disk_after):
    if disk_after != disk_before:
        raise ValueError('recovery changed the owned guest disk identity')
    for role in ('daemon', 'vm'):
        old, new = before[role], after[role]
        if (old['pid'], old['kernel_start_identity']) == (new['pid'], new['kernel_start_identity']):
            raise ValueError(f'{role} process did not restart')
        if old['executable'] != new['executable']:
            raise ValueError(f'{role} loaded executable changed during recovery')
    if sorted(before['vm']['boot_assets'], key=lambda asset: asset['path']) != sorted(
            after['vm']['boot_assets'], key=lambda asset: asset['path']):
        raise ValueError('booted guest artifacts changed during recovery')
