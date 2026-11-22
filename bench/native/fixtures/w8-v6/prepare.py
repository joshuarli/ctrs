#!/usr/bin/env python3
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

root = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(root / 'bench/native'))
import registry_portfolio
import runner
import watch_loop


def build(engine, context, tag, archive, extra=()):
    engine.sh(['buildx', 'build', '--builder', 'default', '--no-cache',
               '--platform', 'linux/arm64', '--provenance=false', '--sbom=false',
               '--build-arg', 'SOURCE_DATE_EPOCH=0', *extra,
               '--output', f'type=docker,dest={archive},name={tag},rewrite-timestamp=true',
               str(context)], timeout=1800)
    engine.sh(['image', 'load', '--input', str(archive)], timeout=900)


def fixture_tag(repository, reference):
    return f"np-w8-portable/{repository.removeprefix('np-v6/')}:{reference}"


def construct(engine, parent, fixture, contract):
    api = parent / 'api'
    api.mkdir()
    shutil.copyfile(fixture / 'Dockerfile.api', api / 'Dockerfile')
    shutil.copyfile(fixture / 'api-requirements.lock', api / 'requirements.lock')
    for destination, expected in contract['api_files_sha256'].items():
        filename = Path(destination).name
        source = runner.API_DOCKERFILE_DIR / filename
        if runner.sha256_file(source) != expected:
            raise ValueError(f'API fixture differs from pin: {filename}')
        shutil.copyfile(source, api / filename)

    marked = parent / 'marked'
    marked_source = marked / 'source'
    marked_source.mkdir(parents=True)
    marked_fixture = watch_loop.contract()
    source = marked_fixture['source']
    archive = runner.ensure_pinned_source({**source, 'file': f"marked-{source['version']}.tar.gz"},
                                          runner.WORK / 'inputs')
    subprocess.run(['tar', '-xzf', str(archive), '--strip-components=1',
                    '-C', str(marked_source)], check=True)
    if runner.sha256_file(marked_source / 'package-lock.json') != source['lock_sha256']:
        raise ValueError('Marked lock differs from pin')
    shutil.copyfile(fixture / 'Dockerfile.marked', marked / 'Dockerfile')
    for filename in ('workload.json', 'watch.mjs', 'verify.mjs', 'edit.mjs'):
        shutil.copyfile(runner.FIXTURES / 'w5-v2' / filename, marked / filename)

    tags = {}
    for name, pin in contract['images'].items():
        image = name.removeprefix('np-v6/')
        tags[image] = fixture_tag(name, pin['layout_reference'])
    build(engine, api, tags['api'], parent / 'api.tar')
    build(engine, marked, tags['marked'], parent / 'marked.tar',
          ('--build-arg', f"NODE_IMAGE={marked_fixture['tools']['image']}"))
    for image in ('postgres', 'redis'):
        ref = f"{image}@{contract['images'][f'np-v6/{image}']['manifest']}"
        engine.sh(['pull', '--platform', 'linux/arm64', ref], timeout=600)
        engine.sh(['image', 'tag', ref, tags[image]])

    raw_layout = parent / 'docker-layout'
    raw_layout.mkdir()
    archive = parent / 'docker-save.tar'
    engine.sh(['image', 'save', '--platform', 'linux/arm64', '--output', str(archive),
               tags['api'], tags['postgres'], tags['redis'], tags['marked']], timeout=900)
    with tarfile.open(archive) as saved:
        saved.extractall(raw_layout, filter='data')

    output = parent / 'output'
    layout = output / 'layout'
    layout.mkdir(parents=True)
    archive = output / 'portfolio.tar'
    write_archive(raw_layout, archive, contract)
    with tarfile.open(archive) as saved:
        saved.extractall(layout, filter='data')
    return output


def write_archive(layout, archive, contract):
    registry_portfolio.prepare_pinned_portfolio(layout, contract)
    descriptors = json.loads((layout / 'index.json').read_text())['manifests']
    index = []
    manifest = []
    blobs = set()
    for repository, pin in contract['images'].items():
        reference = pin['layout_reference']
        selected, = [item for item in descriptors
                     if item.get('annotations', {}).get('org.opencontainers.image.ref.name') == reference]
        index.append({'digest': pin['manifest'], 'size': selected['size'],
                      'mediaType': selected['mediaType'],
                      'platform': {'os': 'linux', 'architecture': 'arm64'},
                      'annotations': {'org.opencontainers.image.ref.name': reference}})
        description = layout / 'blobs/sha256' / pin['manifest'].removeprefix('sha256:')
        image = json.loads(description.read_text())
        config = 'blobs/sha256/' + pin['config'].removeprefix('sha256:')
        layers = ['blobs/sha256/' + layer['digest'].removeprefix('sha256:')
                  for layer in image['layers']]
        tag = fixture_tag(repository, reference)
        manifest.append({'Config': config, 'RepoTags': [tag], 'Layers': layers})
        blobs.update((description.relative_to(layout).as_posix(), config, *layers))
    metadata = {
        'index.json': {'schemaVersion': 2, 'mediaType': registry_portfolio.OCI_INDEX, 'manifests': index},
        'manifest.json': manifest,
        'oci-layout': {'imageLayoutVersion': '1.0.0'},
    }
    with tarfile.open(archive, mode='w', format=tarfile.USTAR_FORMAT) as saved:
        for name in sorted(blobs):
            source = layout / name
            entry = tarfile.TarInfo(name)
            entry.size = source.stat().st_size
            with source.open('rb') as stream:
                saved.addfile(entry, stream)
        for name, value in metadata.items():
            data = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            saved.addfile(entry, io.BytesIO(data))


def main():
    fixture = Path(__file__).parent
    contract = json.loads((fixture / 'portfolio.json').read_text())
    destination = runner.WORK / 'inputs' / 'w8-portfolio-v6'
    if not destination.exists():
        runner.DOCKER = runner.find_docker()
        engine = runner.Engine('orbstack', 'w8-v6-prepare')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='w8-v6-', dir=destination.parent) as directory:
            built = construct(engine, Path(directory), fixture, contract)
            actual = runner.sha256_file(built / 'portfolio.tar')
            if actual != contract['archive_sha256']:
                raise ValueError(f'W8 v6 archive differs from pin: {actual}')
            built.rename(destination)
    registry_portfolio.prepare_pinned_portfolio(destination / 'layout', contract)
    if runner.sha256_file(destination / 'portfolio.tar') != contract['archive_sha256']:
        raise ValueError('W8 v6 archive differs from pin')
    print(destination / 'layout')


if __name__ == '__main__':
    main()
