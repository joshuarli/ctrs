import json
import os
from pathlib import Path
import subprocess
import sys
import time

NATIVE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NATIVE))
import runner
from transfer import trial_w13

runner.CTRS_BIN = Path('/Users/josh/d/ctrs/target/release/ctrs')
runner.DOCKER = runner.find_docker()
os.environ['CTRS_GUEST_DIR'] = '/Users/josh/d/ctrs/guest/out'
run_id = 'w13-proof-' + str(int(time.time()))
ctx = runner.RunContext(run_id)
orb = runner.Engine('orbstack', run_id)
ctrs = runner.Engine('ctrs', run_id)
summary = []
try:
    existing = subprocess.run(['pgrep', '-fl', 'ctrs daemon'], capture_output=True, text=True)
    print('pgrep -fl ctrs daemon exit', existing.returncode, flush=True)
    for line in existing.stdout.splitlines():
        if 'ctrs daemon' in line and 'codex exec' not in line:
            print('pgrep:', line, flush=True)
    if ctrs.sh(['version'], timeout=10, check=False).returncode == 0:
        raise RuntimeError('ctrs endpoint already active; refusing adoption')
    rows = orb.sh(['images', '--no-trunc', '--format', '{{.Repository}} {{.ID}}']).stdout.splitlines()
    matches = [row.split() for row in rows if row.split() and row.split()[0].endswith('np-v5/api')]
    matches.sort(key=lambda x: (x[0] != 'np-v5/api', x[0], x[1]))
    if not matches:
        raise RuntimeError('API image missing')
    orb.w13_image_id = matches[0][1]
    archive = Path(os.environ['TMPDIR']) / (run_id + '.tar')
    orb.sh(['save', '-o', str(archive), orb.w13_image_id], timeout=300)
    ctrs.ensure_up()
    load = ctrs.sh(['load', '-i', str(archive)], timeout=300)
    print('docker save/load:', orb.w13_image_id, load.stdout.strip(), flush=True)
    ctrs.w13_image_id = load.stdout.strip().split()[-1]
    archive.unlink()
    for engine in (orb, ctrs):
        for path in ('published-port', 'container-to-container', 'container-to-mac'):
            for direction in ('upload', 'download'):
                for streams in (1, 4):
                    rec = trial_w13(ctx, engine, 'warm', path=path, direction=direction,
                                    streams=streams, size_bytes=256 * 1024**2, repeats=1)
                    ctx.write(rec)
                    item = {'engine': engine.name, 'path': path, 'direction': direction,
                            'streams': streams, 'ok': rec['correctness']['ok'],
                            'image_id': engine.w13_image_id, 'errors': rec['validation_errors'],
                            'metrics': rec['metrics']}
                    summary.append(item)
                    print(json.dumps(item), flush=True)
                    if not item['ok']:
                        raise RuntimeError('functional condition failed')
    print('SUMMARY_JSON=' + json.dumps(summary), flush=True)
finally:
    ctrs.stop()
