"""Pure interpretation of bounded W10 host probes and guest clock brackets."""
import errno
import hashlib
import math
import urllib.error


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
