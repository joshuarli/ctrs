#!/usr/bin/env python3
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import uuid

root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(root / 'bench/native'))
import runner

runner.DOCKER = runner.find_docker()
spec = json.loads((Path(__file__).parent / 'workload.json').read_text())
scratch = root / '.work/tmp'
scratch.mkdir(parents=True, exist_ok=True)
os.environ['TMPDIR'] = str(scratch)
archive = scratch / 'kutt.tar.gz'
image_archive = scratch / 'w12-image.tar'
image = 'np-w12-kutt:proof'
run_id = 'w12prep' + uuid.uuid4().hex[:10]
engine = runner.Engine('orbstack', run_id)
if not archive.exists():
    with urllib.request.urlopen(spec['source']['url'], timeout=60) as response, archive.open('wb') as output:
        shutil.copyfileobj(response, output)
if hashlib.sha256(archive.read_bytes()).hexdigest() != spec['source']['sha256']:
    raise ValueError('source archive digest mismatch')
cp = engine.sh(['image', 'inspect', image], check=False)
if cp.returncode != 0:
    with tempfile.TemporaryDirectory(prefix='w12-prep-', dir=scratch) as directory:
        context = Path(directory)
        source = context / 'source'
        source.mkdir()
        subprocess.run(['tar', '-xzf', str(archive), '--strip-components=1', '-C', str(source)], check=True)
        if hashlib.sha256((source / 'package-lock.json').read_bytes()).hexdigest() != spec['source']['lock_sha256']:
            raise ValueError('source lock digest mismatch')
        cache = context / 'npm-cache'
        cache.mkdir()
        engine.sh(['run', '--rm', '--label', 'dev.ctrs.campaign.run=' + run_id,
                   '--platform', 'linux/arm64', '--mount', f'type=bind,src={source},dst=/source,readonly',
                   '--mount', f'type=bind,src={cache},dst=/cache', spec['tools']['image'],
                   'sh', '-ec', 'cp -a /source /app; cd /app; npm ci --legacy-peer-deps --cache /cache --no-audit --no-fund'], timeout=1800)
        shutil.copyfile(archive, context / 'source.tar.gz')
        shutil.copyfile(Path(__file__).parent / 'Dockerfile', context / 'Dockerfile')
        engine.sh(['build', '--platform', 'linux/arm64', '-t', image, str(context)], timeout=1800)
        cp = engine.sh(['image', 'inspect', image])
info = json.loads(cp.stdout)[0]
if info['Id'] != spec['prepared_image']['orbstack_id'] or info['RootFS']['Layers'] != spec['prepared_image']['diff_ids']:
    raise ValueError('prepared image does not match pinned image and must be reviewed before repinning')
engine.sh(['image', 'save', '--output', str(image_archive), image], timeout=600)
print(json.dumps({'image_id': info['Id'], 'diff_ids': info['RootFS']['Layers'], 'image_archive': str(image_archive)}))
