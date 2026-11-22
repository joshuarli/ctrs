#!/usr/bin/env python3
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(root / 'bench/native'))
import runner
import workspace


def main():
    spec = workspace.source_contract()
    fixture = workspace.FIXTURE
    scratch = workspace.INPUTS
    scratch.mkdir(parents=True, exist_ok=True)
    os.environ['TMPDIR'] = str(scratch)
    source = runner.ensure_pinned_source({**spec['source'], 'file': 'kutt.tar.gz'}, scratch)
    target = scratch / 'w12-image.tar'
    expected = spec['prepared_image']['archive_sha256']
    if runner.sha256_file(target) != expected:
        runner.DOCKER = runner.find_docker()
        engine = runner.Engine('orbstack', 'w12-prepare')
        with tempfile.TemporaryDirectory(prefix='w12-prep-', dir=scratch) as directory:
            context = Path(directory) / 'context'
            context.mkdir()
            shutil.copyfile(source, context / 'source.tar.gz')
            shutil.copyfile(fixture / 'install-lock.json', context / 'package-lock.json')
            shutil.copyfile(fixture / 'Dockerfile', context / 'Dockerfile')
            built = context.parent / 'image.tar'
            engine.sh(['buildx', 'build', '--builder', 'default', '--no-cache',
                       '--platform', 'linux/arm64', '--provenance=false', '--sbom=false',
                       '--build-arg', 'SOURCE_DATE_EPOCH=0',
                       '--output', f'type=docker,dest={built},name=np-w12-kutt:v2,rewrite-timestamp=true',
                       str(context)], timeout=1800)
            actual = runner.sha256_file(built)
            if actual != expected:
                raise ValueError(f'prepared W12 archive differs from pin: {actual}')
            built.replace(target)
    print(json.dumps({'archive': str(target), 'sha256': expected}))


if __name__ == '__main__':
    main()
