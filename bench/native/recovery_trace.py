"""Pure interpretation of bounded W10 host probes and guest clock brackets."""
import errno
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
        if attempt['ended_ns'] >= interrupted_ns and attempt['started_ns'] <= recovered_ns:
            expected.append(attempt)
        else:
            unexpected.append(attempt)
    return {'expected_outage_errors': expected, 'unexpected_errors': unexpected,
            'host_address_errors': host_address_errors,
            'host_client_valid': not host_address_errors}


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
