"""W4 queue latency receipts around the pinned deterministic artifact workload."""
import argparse
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import time
from uuid import UUID

if __package__:
    from . import app
else:
    import app


def guest_clock(proc=Path('/proc'), *, now=time.monotonic_ns):
    boot = str(UUID((proc / 'sys/kernel/random/boot_id').read_text().strip()))
    offsets = [line.split() for line in (proc / 'self/timens_offsets').read_text().splitlines()]
    monotonic = [fields[1:] for fields in offsets if fields and fields[0] == 'monotonic']
    if len(monotonic) != 1 or len(monotonic[0]) != 2:
        raise ValueError('expected exactly one monotonic namespace offset')
    seconds, nanoseconds = map(int, monotonic[0])
    if not 0 <= nanoseconds < 1_000_000_000:
        raise ValueError('invalid monotonic namespace offset nanoseconds')
    offset = seconds * 1_000_000_000 + nanoseconds
    return boot, lambda: now() - offset


def handler(host, port, clock_id, *, now=time.monotonic_ns):
    class Handler(app.handler(host, port)):
        def do_POST(self):
            if self.path != '/jobs':
                self.reply(404, {'error': 'not found'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= app.MAX_BODY:
                    raise ValueError('invalid body length')
                payload = self.rfile.read(length)
                if len(payload) != length:
                    raise ValueError('truncated body')
                value = app.validate_batch(json.loads(payload))
            except (ValueError, TypeError) as exc:
                self.reply(400, {'error': str(exc)})
                return
            try:
                redis = app.Redis(host, port)
                try:
                    redis.command('RPUSH', app.QUEUE, app.encode({
                        'batch': value, 'clock': clock_id, 'enqueued_ns': now(),
                    }))
                finally:
                    redis.close()
            except (OSError, RuntimeError) as exc:
                self.reply(503, {'error': str(exc)})
                return
            self.reply(202, {'id': value['id']})
    return Handler


def worker(host, port, output_dir, clock_id, *, now=time.monotonic_ns):
    artifacts = output_dir / 'artifacts'
    timings = output_dir / 'timings'
    artifacts.mkdir(exist_ok=True)
    timings.mkdir(exist_ok=True)
    redis = app.Redis(host, port)
    try:
        while (item := redis.command('LPOP', app.QUEUE)) is not None:
            record = json.loads(item)
            value = app.validate_batch(record['batch'])
            job = value['id']
            if record['clock'] != clock_id:
                raise ValueError(f'job {job} was enqueued on a different guest clock')
            for name, content in zip(app.filenames(job), app.artifacts(value), strict=True):
                with (artifacts / name).open('xb') as output:
                    output.write(content)
            completed = now()
            with (timings / f'{job}.json').open('xb') as timing:
                timing.write(app.encode({'job': job, 'clock': clock_id,
                                         'enqueued_ns': record['enqueued_ns'],
                                         'completed_ns': completed}))
    finally:
        redis.close()


def verify(host, port, output_dir, clock_id):
    verified = app.verify(host, port, output_dir / 'artifacts')
    timings = output_dir / 'timings'
    if {path.name for path in timings.iterdir()} != {f'{job}.json' for job in range(verified)}:
        raise ValueError('missing or extra queue timing receipts')
    records = []
    for job in range(verified):
        path = timings / f'{job}.json'
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'invalid timing file for job {job}')
        records.append(json.loads(path.read_text()))
    receipt = {'verified': verified, 'clock': clock_id, 'timings': records}
    completed_latencies(receipt)
    return receipt


def completed_latencies(receipt):
    records = receipt['timings']
    clock_id = receipt['clock']
    if (type(receipt['verified']) is not int or receipt['verified'] != app.JOBS
            or not isinstance(records, list) or len(records) != app.JOBS
            or not isinstance(clock_id, str) or not clock_id):
        raise ValueError('incomplete queue timing receipt')
    latencies = []
    for job, record in enumerate(records):
        start, end = record['enqueued_ns'], record['completed_ns']
        if (type(record['job']) is not int or record['job'] != job or record['clock'] != clock_id
                or type(start) is not int or type(end) is not int or not 0 <= start <= end):
            raise ValueError(f'invalid queue timing for job {job}')
        latencies.append(end - start)
    return latencies


def pending(host, port, clock_id):
    redis = app.Redis(host, port)
    try:
        items = redis.command('LRANGE', app.QUEUE, 0, app.JOBS)
    finally:
        redis.close()
    records = [json.loads(item) for item in items]
    if len(records) != app.JOBS:
        raise ValueError('queued job count differs from submitted work')
    for job, row in enumerate(records):
        if (app.validate_batch(row['batch']) != app.batch(job) or row['clock'] != clock_id
                or type(row['enqueued_ns']) is not int or row['enqueued_ns'] < 0):
            raise ValueError(f'queued job {job} differs from submitted work')
    return [{'job': job, 'clock': row['clock'], 'enqueued_ns': row['enqueued_ns']}
            for job, row in enumerate(records)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('serve', 'submit', 'worker', 'verify', 'pending'))
    parser.add_argument('--redis-host', default='redis')
    parser.add_argument('--redis-port', type=int, default=6379)
    parser.add_argument('--url', default='http://app:8080')
    parser.add_argument('--output-dir', type=Path, default=Path('/output'))
    args = parser.parse_args()
    if args.command == 'submit':
        app.submit(args.url)
        return
    clock_id, now = guest_clock()
    if args.command == 'serve':
        ThreadingHTTPServer(('0.0.0.0', 8080), handler(
            args.redis_host, args.redis_port, clock_id, now=now)).serve_forever()
    elif args.command == 'worker':
        worker(args.redis_host, args.redis_port, args.output_dir, clock_id, now=now)
    elif args.command == 'pending':
        print(json.dumps(pending(args.redis_host, args.redis_port, clock_id)))
    else:
        print(json.dumps(verify(args.redis_host, args.redis_port, args.output_dir, clock_id)))


if __name__ == '__main__':
    main()
