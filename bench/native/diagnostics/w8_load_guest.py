"""Run the pinned W2 worker with completion callback receipts."""
import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import time
from urllib.parse import urlsplit


class Recorder:
    def __init__(self, output, directory):
        self.output = output
        self.directory = directory
        self.lock = threading.Lock()
        self.sequence = 0

    def append(self, latency):
        with self.lock:
            now = time.monotonic()
            self.output.write(json.dumps({'sequence': self.sequence, 'completion_monotonic': now, 'latency_ms': latency}) + '\n')
            if self.sequence == 0:
                temporary = self.directory / 'readiness.tmp'
                temporary.write_text(json.dumps({'completion_monotonic': now}) + '\n')
                os.replace(temporary, self.directory / 'readiness.json')
            self.sequence += 1


def main():
    worker_path, expected_hash, url, directory = sys.argv[1:]
    directory = Path(directory)
    if hashlib.sha256(Path(worker_path).read_bytes()).hexdigest() != expected_hash:
        raise ValueError('W2 worker hash differs from pin')
    spec = importlib.util.spec_from_file_location('pinned_w2', worker_path)
    load = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(load)
    target = urlsplit(url)
    counts = dict(reads=0, writes=0, errors=0)
    class Journal(list):
        def __init__(self, stream):
            super().__init__()
            self.stream = stream

        def append(self, item):
            self.stream.write(json.dumps(item) + '\n')
            super().append(item)

    stop = threading.Event()
    begin = time.monotonic()
    with (directory / 'completions.jsonl').open('w', buffering=1) as output, \
            (directory / 'accepted-writes.jsonl').open('w', buffering=1) as write_stream, \
            (directory / 'client-errors.jsonl').open('w', buffering=1) as error_stream:
        writes, errors = Journal(write_stream), Journal(error_stream)
        recorder = Recorder(output, directory)
        timer = threading.Timer(900, stop.set)
        try:
            timer.start()
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(load.worker, i, (target.hostname, target.port), 900, .3, 7000 + i,
                    recorder, counts, stop, errors, begin, operations=12500, writes=writes) for i in range(4)]
                for future in futures:
                    future.result()
        finally:
            timer.cancel()
            timer.join()
            (directory / 'client-result.json').write_text(json.dumps({'counts': counts, 'errors': errors,
                'writes': writes, 'elapsed_seconds': time.monotonic() - begin}) + '\n')
    if counts['errors'] or counts['reads'] + counts['writes'] != 50000:
        raise RuntimeError('fixed client work failed or expired')


if __name__ == '__main__':
    main()
