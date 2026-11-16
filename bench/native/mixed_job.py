#!/usr/bin/env python3
"""Launch one unqualified mixed-duration diagnostic under durable_job."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import secrets
import sys
import tempfile
import time

import durable_job

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DRAIN_SECONDS = 900
CLEANUP_SECONDS = 900
MAX_DIAGNOSTIC_SECONDS = 3600


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--duration', type=float, required=True)
    parser.add_argument('--engine', choices=('ctrs', 'orbstack'), required=True)
    parser.add_argument('--portfolio-layout', type=Path, required=True)
    parser.add_argument('--worker-layout', type=Path, required=True)
    parser.add_argument('--ctrs-binary', type=Path, required=True)
    parser.add_argument('--compose-plugin', type=Path, required=True, help='actual docker-compose plugin selected by Docker')
    parser.add_argument('--input', type=Path, action='append', default=[], help='additional executable or asset used by this host')
    parser.add_argument('--qualification', action='store_true')
    args = parser.parse_args()
    if args.qualification:
        parser.error('qualification refused: frozen candidate, assets, workload, final matrix and readiness evidence schema/proof are missing; 12-hour qualification is not authorized')
    if not math.isfinite(args.duration) or not 0 < args.duration <= MAX_DIAGNOSTIC_SECONDS:
        parser.error('diagnostic duration must be finite and within 1 hour')
    if sys.platform != 'darwin' or os.uname().machine != 'arm64':
        parser.error('native ARM64 macOS only')
    docker = shutil.which('docker')
    if not docker:
        parser.error('docker executable unavailable')
    paths = [Path(sys.executable), Path(docker), args.compose_plugin, args.ctrs_binary, *args.input]
    paths += [Path(found) for name in ('ps', 'lsof', 'pmset', 'footprint', 'perf-gate-ready')
              if (found := shutil.which(name))]
    paths += list(HERE.glob('*.py')) + list((HERE / 'diagnostics').glob('*.py'))
    paths += [p for p in (HERE / 'fixtures').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    paths += [HERE / name for name in ('cases.toml', 'assets.lock', 'schema.json')]
    for layout in (args.portfolio_layout, args.worker_layout):
        if not layout.is_dir():
            parser.error(f'layout missing: {layout}')
        paths += [p for p in layout.rglob('*') if p.is_file()]
    template = None
    boot_assets = {}
    if args.engine == 'ctrs':
        binary = args.ctrs_binary.resolve(strict=True)
        repo = next((p for p in binary.parents if (p / 'Cargo.lock').is_file() and (p / 'guest').is_dir()), REPO)
        guest = Path(os.environ.get('CTRS_GUEST_DIR', str(repo / 'guest/out')))
        paths += [guest / name for name in ('Image', 'initramfs.cpio')]
        boot_assets = {str((guest / name).resolve()): durable_job.receipt(guest / name) for name in ('Image', 'initramfs.cpio')}
        template = guest / 'data.img'
        if not template.is_file():
            template = guest / '../data.img'
        if not template.is_file():
            template = guest / 'data.img.tgz'
        paths.append(template)
    receipts = [durable_job.receipt(p, sparse=template is not None and p == template.resolve() and p.suffix != '.tgz')
                for p in sorted({p.resolve(strict=True) for p in paths})]
    now = time.time()
    work = now + args.duration
    drain = work + DRAIN_SECONDS
    hard = drain + CLEANUP_SECONDS
    argv = [str(Path(sys.executable).resolve()), str(HERE / 'diagnostics/mixed_pilot.py'),
            '--portfolio-layout', str(args.portfolio_layout.resolve()), '--worker-layout', str(args.worker_layout.resolve()),
            '--ctrs-binary', str(args.ctrs_binary.resolve()), '--engines', args.engine,
            '--work-deadline-epoch', str(work), '--drain-deadline-epoch', str(drain), '--cleanup-deadline-epoch', str(hard - 5)]
    if boot_assets:
        engine_root = args.job.parent.resolve() / ('mx-' + secrets.token_hex(6))
        if len(os.fsencode(str(engine_root / 'run/docker.sock'))) >= 104:
            parser.error('job parent path leaves no room for an isolated macOS Unix socket')
        argv += ['--ctrs-root', str(engine_root)]
        argv += ['--expected-boot-assets', json.dumps({path: {'inode': entry['identity'][1], 'size': entry['identity'][2], 'sha256': entry['sha256']}
                                                    for path, entry in boot_assets.items()})]
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8') as receipt_file:
        json.dump(receipts, receipt_file)
        receipt_file.flush()
        durable_job.launch(args.job, hard, receipt_file.name, argv, interrupt_grace_seconds=CLEANUP_SECONDS)
    return 0


if __name__ == '__main__':
    sys.exit(main())
