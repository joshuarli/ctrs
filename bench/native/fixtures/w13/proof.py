import hashlib
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

runner.CTRS_BIN = Path('/Users/josh/d/ctrs/.work/wt/host-bound/.work/tmp/target/release/ctrs')
runner.DOCKER = runner.find_docker()
os.environ['CTRS_GUEST_DIR'] = '/Users/josh/d/ctrs/.work/wt/host-bound/guest/out'
for path, expected in ((runner.CTRS_BIN, 'd9465bc2b73b15e1318c1e7b27aecff7227edb1515670448cc0dd8ee1db55380'),
                       (Path(os.environ['CTRS_GUEST_DIR']) / 'initramfs.cpio', 'f3ab7344848d5bc5be6a7850c67c66c3b11e6a5e2081e0683792199b55b6ed38')):
    digest = hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
    print('sha256:', path, digest, flush=True)
    if digest != expected:
        raise ValueError('proof artifact hash mismatch')
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
                    metrics = rec['metrics']
                    attempt = metrics['attempts'][0] if metrics['attempts'] else None
                    controls = metrics.get('capacity_controls', {})
                    item = {'engine': engine.name, 'path': path, 'direction': direction,
                            'streams': streams, 'ok': rec['correctness']['ok'],
                            'errors': rec['validation_errors'],
                            'sha256_per_stream': rec.get('inputs', {}).get('sha256_per_stream'),
                            'verified_bytes': attempt['verified_bytes'] if attempt else None,
                            'receiver_hashes': [x.get('sha256') for x in attempt['receivers']] if attempt else [],
                            'capacity_controls': {key: {'ok': value['ok'], 'bytes_per_second': value['goodput_bytes_per_second']} for key, value in controls.items()}}
                    summary.append(item)
                    print(json.dumps(item), flush=True)
                    if not item['ok']:
                        raise RuntimeError('functional condition failed')
    print('SUMMARY_JSON=' + json.dumps(summary), flush=True)
finally:
    ctrs.stop()
