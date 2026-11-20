import json
import threading
import time
from contextlib import contextmanager


def overlap_fraction(window, transfers):
    start, end = window
    if end <= start:
        return 0.0
    intervals = []
    for transfer in transfers:
        for receipt in transfer['receipts']:
            first = receipt.get('first_byte_seconds')
            duration = receipt.get('seconds')
            if first is None or duration is None or first < 0 or duration < first:
                continue
            left = max(start, transfer['host_end'] - duration + first)
            right = min(end, transfer['host_start'] + duration)
            if right > left:
                intervals.append((left, right))
    covered = 0.0
    cursor = start
    for left, right in sorted(intervals):
        covered += max(0.0, right - max(left, cursor))
        cursor = max(cursor, right)
    return covered / (end - start)


def trial_overlap(ctx, engine, state, concurrency=8, duration=20.0, write_ratio=0.3,
                  seed=1, operations=20000, size_bytes=1 << 30, repeats=1, streams=1,
                  lead_seconds=2.0, loops=96):
    import runner
    if lead_seconds < 0 or operations <= 0 or loops < 1 or repeats != 1:
        raise ValueError('invalid overlap parameters')
    directory = ctx.trial_dir(engine.name, 'W13-overlap', state)
    rec = ctx.new_record(engine, 'W13-overlap', state, directory)
    transfers = []
    ready = threading.Event()
    results = {}
    window = []
    current = []

    def observer(event, timestamp, data):
        if event == 'start':
            current[:] = [timestamp]
            ready.set()
        elif event == 'end':
            transfers.append({'host_start': current[0], 'host_end': timestamp,
                              'receipts': data['streams']})
        else:
            transfers[-1]['receipts'] = data
            (directory / 'w13-receipts.json').write_text(json.dumps(transfers, indent=2) + '\n')

    def transfer():
        try:
            results['transfer'] = runner.trial_w13(ctx, engine, state, size_bytes=size_bytes * loops, repeats=1, streams=streams,
                                                   artifact_bytes=size_bytes // streams)
        except Exception as exc:
            results['error'] = f'{type(exc).__name__}: {exc}'
        finally:
            ready.set()

    thread = threading.Thread(target=transfer)

    @contextmanager
    def workload():
        thread.start()
        ready.wait()
        if not current:
            raise RuntimeError(results.get('error', 'transfer did not start'))
        time.sleep(lead_seconds)
        window.append(time.monotonic())
        try:
            yield
        finally:
            window.append(time.monotonic())

    ctx.overlap_transfer_observer = observer
    ctx.overlap_workload = workload
    ctx.overlap_dir = directory
    try:
        w2 = runner.trial_w2(ctx, engine, state, concurrency, duration, write_ratio, seed,
                             operations, pinned_stack=True)
    finally:
        if thread.ident is not None:
            thread.join()
        del ctx.overlap_transfer_observer, ctx.overlap_workload, ctx.overlap_dir
    w13 = results.get('transfer', {})
    fraction = overlap_fraction(window, transfers) if len(window) == 2 else 0.0
    wm = w2.get('metrics', {})
    tm = w13.get('metrics', {})
    rec['metrics'].update(fixture_version='w13-overlap-v1', artifact_bytes=size_bytes, loops=loops,
                          w2_latency_p50_ms=wm.get('p50_ms'), w2_latency_p99_ms=wm.get('p99_ms'),
                          w2_rps=wm.get('rps'), transfer_goodput_bytes_per_second=tm.get('goodput_bytes_per_second'),
                          overlap_fraction=fraction)
    rec['overlap_timing'] = {'clock': 'host monotonic; conservative bounds from receiver durations',
                             'w2_window': window, 'transfers': transfers}
    checks = rec['correctness']['checks']
    checks['w2'] = w2.get('correctness', {}).get('ok', False)
    checks['w13'] = w13.get('correctness', {}).get('ok', False)
    checks['transfer_overlapping'] = fraction >= 0.95
    rec['correctness']['ok'] = all(checks.values())
    rec['validation_errors'].extend(w2.get('validation_errors', []))
    rec['validation_errors'].extend(w13.get('validation_errors', []))
    if 'error' in results:
        rec['validation_errors'].append(results['error'])
    if not checks['transfer_overlapping']:
        rec['validation_errors'].append('transfer_not_overlapping')
    rec['inputs'] = {'w2': w2.get('inputs', {}), 'w13': w13.get('inputs', {})}
    rec['resources'] = dict(w2.get('resources') or {})
    rec['paired_inputs'] = dict(w2.get('paired_inputs', {}))
    if rec['paired_inputs'] and w13.get('paired_inputs'):
        rec['paired_inputs']['transfer'] = dict(w13['paired_inputs'])
    (directory / 'w2-record.json').write_text(json.dumps(w2, indent=2) + '\n')
    (directory / 'w13-record.json').write_text(json.dumps(w13, indent=2) + '\n')
    return rec
