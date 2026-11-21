#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(root / 'bench/native'))
import runner
import workspace

parser = argparse.ArgumentParser()
parser.add_argument('--engine', choices=('orbstack', 'ctrs', 'dockerd'))
condition = parser.add_mutually_exclusive_group()
condition.add_argument('--layout', choices=('full-bind', 'bind-source-volume-deps', 'all-volume'))
condition.add_argument('--mount', choices=('bind', 'volume'))
condition.add_argument('--all', action='store_true')
args = parser.parse_args()
if args.engine == 'dockerd':
    parser.error('W12 is unsupported for dockerd; use the Linux lane W2, W6, W7 or W13')
if args.all and args.engine or not args.all and (not args.engine or not (args.layout or args.mount)):
    parser.error('use --all or select --engine with --layout or --mount')
os.environ['TMPDIR'] = str(root / '.work/tmp')
os.environ['CTRS_GUEST_DIR'] = '/Users/josh/d/ctrs/guest/out'
runner.CTRS_BIN = Path('/Users/josh/d/ctrs/target/release/ctrs')
runner.DOCKER = runner.find_docker()
run_id = 'w12p' + uuid.uuid4().hex[:10]
ctx = runner.RunContext(run_id)
choices = [('layout', value) for value in ('full-bind', 'bind-source-volume-deps', 'all-volume')]
choices += [('mount', value) for value in ('bind', 'volume')]
engines = ('orbstack', 'ctrs') if args.all else (args.engine,)
for engine_name in engines:
    engine_root = runner.WORK / 'engines' / (run_id + '-' + engine_name)
    if engine_root.exists():
        raise RuntimeError('engine root already exists')
    engine = runner.Engine(engine_name, run_id, fresh_dir=engine_root, resource_lane='installed-default')
    try:
        if engine_name == 'ctrs':
            subprocess.run(['pgrep', '-fl', 'ctrs daemon'], check=False)
            engine.ensure_up()
            if engine.proc is None:
                raise RuntimeError('refusing to adopt a daemon')
            engine.sh(['image', 'load', '--input', str(root / '.work/tmp/w12-image.tar')], timeout=600)
        selected = choices if args.all else [('layout', args.layout)] if args.layout else [('mount', args.mount)]
        for kind, value in selected:
            rec = (workspace.trial_w12(ctx, engine, 'warm', layout=value) if kind == 'layout' else
                   workspace.trial_w12_watch(ctx, engine, 'warm', mount=value, edits=60))
            ctx.write(rec)
            metrics = rec['metrics']
            summary = {'engine': engine_name, kind: value, 'correctness': rec['correctness'],
                       'errors': rec['validation_errors'],
                       'phase_seconds': {key: phase['operation_wall_seconds'] for key, phase in rec['resources'].get('phases', {}).items()},
                       'files': metrics.get('files'), 'bytes': metrics.get('bytes'),
                       'dependency_count': metrics.get('dependency_count'),
                       'mounts': rec.get('inputs', {}).get('mounts'),
                       'backend': metrics.get('backend'), 'missed': metrics.get('missed'),
                       'stale': metrics.get('stale'), 'edit_count': len(metrics.get('edits', []))}
            print(json.dumps(summary), flush=True)
            if not rec['correctness']['ok']:
                sys.exit(1)
    finally:
        engine.stop()
