#!/usr/bin/env python3
"""Launch one finite mixed-workload diagnostic or frozen qualification leg."""
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
import mixed_resources
import qualification

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DRAIN_SECONDS = 900
CLEANUP_SECONDS = 900


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=Path, required=True)
    parser.add_argument('--duration', type=float, required=True,
                        help='seconds from launch to the work cutoff, including setup')
    parser.add_argument('--engine', choices=('ctrs', 'orbstack'), required=True)
    parser.add_argument('--portfolio-layout', type=Path, required=True)
    parser.add_argument('--worker-layout', type=Path, required=True)
    parser.add_argument('--ctrs-binary', type=Path, required=True)
    parser.add_argument('--compose-plugin', type=Path, required=True, help='actual docker-compose plugin selected by Docker')
    parser.add_argument('--input', type=Path, action='append', default=[], help='additional executable or asset used by this host')
    parser.add_argument('--qualification', action='store_true', help='launch one frozen 12-hour leg')
    parser.add_argument('--readiness', type=Path, help='reviewed frozen declaration for qualification')
    parser.add_argument('--orbstack-storage-file', type=Path, action='append', default=[],
                        help='owned backing file for an OrbStack qualification leg; repeat to cover multiple files')
    args = parser.parse_args()
    if not math.isfinite(args.duration) or args.duration <= 0:
        parser.error('--duration must be finite and positive')
    if args.qualification:
        if args.readiness is None:
            parser.error('qualification requires --readiness')
        if args.duration <= qualification.MINIMUM_WORK_SECONDS:
            parser.error('qualification --duration must include twelve hours plus setup time')
        if (args.engine == 'orbstack') != bool(args.orbstack_storage_file):
            parser.error('only OrbStack qualification requires --orbstack-storage-file')
    elif args.readiness is not None or args.orbstack_storage_file:
        parser.error('--readiness and --orbstack-storage-file require --qualification')
    elif args.duration > qualification.MAX_DIAGNOSTIC_WORK_SECONDS:
        parser.error('diagnostic duration is limited to fifteen minutes')
    if sys.platform != 'darwin' or os.uname().machine != 'arm64':
        parser.error('native ARM64 macOS only')
    docker = shutil.which('docker')
    if not docker:
        parser.error('docker executable unavailable')
    paths = [Path(sys.executable), Path(docker), args.compose_plugin, args.ctrs_binary, *args.input]
    paths += [Path(found) for name in ('ps', 'lsof', 'pmset', 'footprint', 'perf-gate-ready')
              if (found := shutil.which(name))]
    receipts = {}
    qualification_args = []
    if args.qualification:
        try:
            frozen, readiness_receipt = qualification.require_leg_readiness(
                args.readiness, ctrs_binary=args.ctrs_binary, guest=Path(os.environ['CTRS_GUEST_DIR']),
                portfolio_layout=args.portfolio_layout, worker_layout=args.worker_layout)
            for tool, binary in (('docker', Path(docker)), ('compose', args.compose_plugin)):
                if frozen['tools'][tool]['artifact']['path'] != str(binary.resolve(strict=True)):
                    raise qualification.ReadinessError('requested tool differs from the freeze: ' + tool)
            receipts = {item['path']: item for item in (*frozen['inputs'], readiness_receipt)}
            qualification_args = ['--qualification', '--readiness', readiness_receipt['path'],
                                  '--resource-observation-seconds',
                                  str(mixed_resources.BUDGETS['minimum_observation_seconds'])]
            for path in args.orbstack_storage_file:
                qualification_args += ['--orbstack-storage-file', str(path.resolve(strict=True))]
        except (OSError, KeyError, ValueError) as exc:
            parser.error('qualification refused: ' + str(exc))
    else:
        paths += list(HERE.glob('*.py')) + list((HERE / 'diagnostics').glob('*.py'))
        paths += [p for p in (HERE / 'fixtures').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
        paths += [HERE / name for name in ('cases.toml', 'assets.lock', 'schema.json')]
        for layout in (args.portfolio_layout, args.worker_layout):
            if not layout.is_dir():
                parser.error(f'layout missing: {layout}')
            paths += [p for p in layout.rglob('*') if p.is_file()]
    template = None
    boot_assets = {}
    if args.engine == 'ctrs' and not args.qualification:
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
    for path in sorted({p.resolve(strict=True) for p in paths}):
        if str(path) not in receipts:
            sparse = template is not None and path == template.resolve() and path.suffix != '.tgz'
            receipts[str(path)] = durable_job.receipt(path, sparse=sparse)
    now = time.time()
    work = now + args.duration
    drain = work + DRAIN_SECONDS
    hard = drain + CLEANUP_SECONDS
    argv = [str(Path(sys.executable).resolve()), str(HERE / 'diagnostics/mixed_pilot.py'),
            '--portfolio-layout', str(args.portfolio_layout.resolve()), '--worker-layout', str(args.worker_layout.resolve()),
            '--ctrs-binary', str(args.ctrs_binary.resolve()), '--engines', args.engine,
            '--work-deadline-epoch', str(work), '--drain-deadline-epoch', str(drain),
            '--cleanup-deadline-epoch', str(hard - 5), *qualification_args]
    if args.engine == 'ctrs':
        engine_root = args.job.parent.resolve() / ('mx-' + secrets.token_hex(6))
        if len(os.fsencode(str(engine_root / 'run/docker.sock'))) >= 104:
            parser.error('job parent path leaves no room for an isolated macOS Unix socket')
        argv += ['--ctrs-root', str(engine_root)]
    if boot_assets:
        argv += ['--expected-boot-assets', json.dumps({path: {'inode': entry['identity'][1], 'size': entry['identity'][2], 'sha256': entry['sha256']}
                                                    for path, entry in boot_assets.items()})]
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8') as receipt_file:
        json.dump(list(receipts.values()), receipt_file)
        receipt_file.flush()
        durable_job.launch(args.job, hard, receipt_file.name, argv, interrupt_grace_seconds=CLEANUP_SECONDS)
    return 0


if __name__ == '__main__':
    sys.exit(main())
