#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import uuid

root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(root / 'bench/native'))
import runner
import workspace

runner.DOCKER = runner.find_docker()
spec = workspace.source_contract()
run_id = 'w12id-' + uuid.uuid4().hex[:8]
engine_root = runner.WORK / 'engines' / run_id
if engine_root.exists():
    raise RuntimeError('proof engine root already exists')
expected = [spec['source']['sha256'], spec['source']['lock_sha256'], spec['install_lock_sha256']]
result = {}
for name in ('orbstack', 'ctrs'):
    engine = runner.Engine(name, run_id, fresh_dir=engine_root, resource_lane='installed-default')
    try:
        engine.ensure_up()
        if name == 'ctrs' and engine.proc is None:
            raise RuntimeError('refusing to adopt a daemon')
        image = spec['prepared_image'][name + '_id']
        workspace.ensure_image(engine, image, spec)
        cp = engine.sh(['run', '--rm', '--label', f'dev.ctrs.campaign.run={run_id}',
                        '--network', 'none', '--entrypoint', 'sha256sum', image,
                        '/fixture/source.tar.gz', '/fixture/source/package-lock.json',
                        '/fixture/install-lock.json'], timeout=60)
        hashes = [line.split()[0] for line in cp.stdout.splitlines()]
        if hashes != expected:
            raise ValueError(f'{name} W12 source or dependency lock differs from pin')
        result[name] = {'image_id': image, 'input_hashes': hashes}
    finally:
        engine.stop()
print(json.dumps(result, indent=2))
