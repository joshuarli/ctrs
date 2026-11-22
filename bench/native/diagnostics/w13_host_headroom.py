"""Measure the W13 byte-exact tool on the Mac loopback, without an engine."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runner
import transfer


def measure(artifact, receipt, direction, streams, part, digest):
    port = runner.free_port()
    command = [sys.executable, str(transfer.TOOL)]
    server = subprocess.Popen([*command, 'server', '127.0.0.1', str(port), direction, str(streams),
                               str(artifact), str(part), digest, str(receipt)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        time.sleep(1)
        if server.poll() is not None:
            raise RuntimeError('W13 loopback server exited: ' + server.communicate()[1])
        client = subprocess.run([*command, 'client', '127.0.0.1', str(port), direction, str(streams),
                                 str(artifact), str(part), digest], capture_output=True, text=True,
                                timeout=120, check=True)
        _, error = server.communicate(timeout=120)
        if server.returncode:
            raise RuntimeError('W13 loopback server failed: ' + error)
        return transfer.transfer_result(json.loads(client.stdout), json.loads(receipt.read_text()),
                                        direction, streams, part, digest)
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        server.stderr.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempts', type=int, default=5, help='attempts per direction and stream count')
    parser.add_argument('--size-bytes', type=int, default=transfer.DEFAULT_SIZE, help='total bytes per attempt')
    args = parser.parse_args()
    if args.attempts < 1 or args.size_bytes <= 0 or args.size_bytes % 4:
        parser.error('attempts must be positive and size must be positive and divisible by four')
    settings = {'tool_sha256': hashlib.sha256(transfer.TOOL.read_bytes()).hexdigest(),
                'python': platform.python_version(), 'arch': platform.machine(), 'size_bytes': args.size_bytes}
    failed = False
    with tempfile.TemporaryDirectory(prefix='w13-loopback-') as scratch:
        root = Path(scratch)
        for streams in (1, 4):
            artifact = root / 'artifact.bin'
            part = args.size_bytes // streams
            prep = subprocess.run([sys.executable, str(transfer.TOOL), 'prepare', str(artifact), str(part)],
                                  capture_output=True, text=True, timeout=120, check=True)
            digest = prep.stdout.strip()
            for attempt in range(1, args.attempts + 1):
                directions = ('upload', 'download') if attempt % 2 else ('download', 'upload')
                for direction in directions:
                    receipt = root / f'{streams}-{attempt}-{direction}.json'
                    result = measure(artifact, receipt, direction, streams, part, digest)
                    failed |= not result['ok']
                    print(json.dumps({**settings, 'streams': streams, 'direction': direction, 'attempt': attempt,
                                      'sha256_per_stream': digest, **result}), flush=True)
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
