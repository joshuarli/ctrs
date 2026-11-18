#!/usr/bin/env python3
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(root / 'bench/native'))
import runner

runner.CTRS_BIN = Path('/Users/josh/d/ctrs/target/release/ctrs')
runner.DOCKER = runner.find_docker()
os.environ['CTRS_GUEST_DIR'] = '/Users/josh/d/ctrs/guest/out'
os.environ['TMPDIR'] = str(root / '.work/tmp')
run_id = 'w12-id-' + uuid.uuid4().hex[:8]
engine_root = runner.WORK / 'engines' / run_id
archive = root / '.work/tmp' / (run_id + '.tar')
if engine_root.exists() or archive.exists():
    raise RuntimeError('proof paths already exist')
subprocess.run(['pgrep', '-fl', '^/.*ctrs daemon$'], check=False)
orb = runner.Engine('orbstack', run_id)
ctrs = runner.Engine('ctrs', run_id, fresh_dir=engine_root, resource_lane='installed-default')
try:
    orb_info = json.loads(orb.sh(['image', 'inspect', 'np-w12-kutt:proof']).stdout)[0]
    pinned = json.loads((Path(__file__).parent / 'workload.json').read_text())['prepared_image']
    if orb_info['Id'] != pinned['orbstack_id'] or orb_info['RootFS']['Layers'] != pinned['diff_ids']:
        raise RuntimeError('OrbStack image differs from the pinned fixture')
    orb.sh(['image', 'save', '--output', str(archive), 'np-w12-kutt:proof'], timeout=600)
    ctrs.ensure_up()
    if ctrs.proc is None:
        raise RuntimeError('refusing to adopt a daemon')
    ctrs.sh(['image', 'load', '--input', str(archive)], timeout=600)
    ctrs_info = json.loads(ctrs.sh(['image', 'inspect', 'np-w12-kutt:proof']).stdout)[0]
    result = {'orbstack_id': orb_info['Id'], 'ctrs_id': ctrs_info['Id'],
              'orbstack_diffids': orb_info['RootFS']['Layers'],
              'ctrs_diffids': ctrs_info['RootFS']['Layers']}
    for engine, other in ((orb, ctrs_info['Id']), (ctrs, orb_info['Id'])):
        command = ['image', 'inspect', other]
        cp = engine.sh(command, timeout=30, check=False)
        result[engine.name + '_inspect_other'] = {'command': command,
            'exit': cp.returncode, 'stdout': cp.stdout, 'stderr': cp.stderr}
    print(json.dumps(result, indent=2))
    if result['orbstack_diffids'] != result['ctrs_diffids']:
        raise RuntimeError('image layers differ')
    if result['orbstack_id'] != result['ctrs_id']:
        raise RuntimeError('identical exported image has different engine image IDs')
finally:
    ctrs.stop()
