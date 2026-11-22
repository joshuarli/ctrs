import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

import linux_cgroups

VERSION = 'linux-amd64-v1'
ENGINES = ('ctrs', 'orbstack', 'dockerd')
CASES = ('W1', 'W2', 'W3', 'W6', 'W7', 'W13')
HERE = Path(__file__).resolve().parent
LOCK = HERE / 'linux' / 'fixtures.lock.json'


def enabled():
    return os.environ.get('NP_BENCH_LANE') == 'linux-amd64'


def require_case(engine, case, cold=False):
    if engine not in ('ctrs', 'dockerd'):
        raise ValueError('Linux lane supports ctrs and dockerd only')
    if case not in CASES:
        raise ValueError('Linux lane supports only ' + ', '.join(CASES))
    if cold:
        raise ValueError('Linux engines are externally managed; cold/fresh_dir lifecycle is refused')


def socket_path(name, fresh_dir=None, overrides=None):
    if fresh_dir is not None or overrides:
        raise ValueError('Linux engines are externally managed; fresh_dir/configuration lifecycle is refused')
    if name == 'dockerd':
        return '/var/run/docker.sock'
    if name != 'ctrs':
        raise ValueError('Linux lane supports ctrs and dockerd only')
    endpoint = os.environ.get('CTRS_SOCKET')
    if not endpoint or not Path(endpoint).is_absolute():
        raise ValueError('externally managed Linux ctrs requires an absolute CTRS_SOCKET')
    if Path(endpoint).resolve() == Path('/var/run/docker.sock').resolve():
        raise ValueError('ctrs and dockerd must not share a socket')
    return endpoint


def read_lock():
    try:
        lock = json.loads(LOCK.read_text())
    except FileNotFoundError as exc:
        raise ValueError('Linux fixture lock missing; run runner.py --lane linux-amd64 prepare first') from exc
    if lock.get('fixture_version') != VERSION or lock.get('platform') != 'linux/amd64':
        raise ValueError('Linux fixture lane/platform mismatch')
    for name, expected in lock.get('files', {}).items():
        actual = hashlib.sha256((HERE / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError('Linux fixture changed after freeze: ' + name)
    return lock


def image(engine, role):
    pin = read_lock()['images'][role]
    reference = pin['ids'][engine.name]
    inspected, = json.loads(engine.sh(['image', 'inspect', reference]).stdout)
    if inspected['Architecture'] != 'amd64' or inspected['RootFS']['Layers'] != pin['diff_ids']:
        raise ValueError('Linux image differs from frozen fixture: ' + role)
    return reference, {'linux_fixture_version': VERSION,
                       'linux_lock_sha256': hashlib.sha256(LOCK.read_bytes()).hexdigest(),
                       'image_diff_ids': pin['diff_ids']}


def stack(engine, override):
    refs = {role: image(engine, role)[0] for role in ('api', 'db', 'cache')}
    override.write_text(json.dumps({'services': {k: {'image': v} for k, v in refs.items()}}))
    return refs, {'linux_fixture_version': VERSION,
                  'portfolio_sha256': hashlib.sha256(LOCK.read_bytes()).hexdigest(),
                  'seed_sha256': read_lock()['seed_sha256']}


def build_images(engine, roles):
    lock = read_lock()
    verified = {}
    for role in roles:
        reference, metadata = image(engine, role)
        tagged, = json.loads(engine.sh(['image', 'inspect', lock['images'][role]['reference']]).stdout)
        if tagged['Id'] != reference:
            raise ValueError('Linux build base tag changed after freeze: ' + role)
        verified[role] = metadata
    return verified


def prepare(engine_factory, work, runner, archive=None):
    if sys.platform != 'linux' or os.uname().machine != 'x86_64':
        raise ValueError('linux-amd64 requires a native x86_64 Linux host')
    if archive is not None:
        lock = read_lock()
        if runner.sha256_file(archive) != lock['archive_sha256']:
            raise ValueError('Linux fixture archive hash mismatch')
        for name in ('dockerd', 'ctrs'):
            engine = engine_factory(name, 'linux-restore')
            engine.ensure_up()
            engine.sh(['load', '-i', str(archive)], timeout=1200)
            for role in lock['images']:
                image(engine, role)
        return 0
    if LOCK.exists():
        raise ValueError('Linux fixture lock is already frozen; refusing implicit replacement')
    directory = work / 'linux-amd64-v1'
    directory.mkdir(parents=True, exist_ok=False)
    docker = engine_factory('dockerd', 'linux-prepare')
    ctrs = engine_factory('ctrs', 'linux-prepare')
    docker.ensure_up()
    ctrs.ensure_up()
    refs = {'db': 'postgres:17-alpine', 'cache': 'redis:7-alpine',
            'rust': runner.W6_RUST_IMAGE, 'gcc': runner.W6_IMAGE,
            'python': runner.W7_PYTHON_IMAGE, 'debian': runner.W7_DEBIAN_IMAGE}
    for ref in refs.values():
        docker.sh(['pull', '--platform', 'linux/amd64', ref], timeout=900)
    refs['api'] = 'np-linux-v1/api:prepared'
    docker.sh(['build', '--load', '--platform', 'linux/amd64', '-t', refs['api'],
               str(runner.API_DOCKERFILE_DIR)], timeout=1200)
    artifacts = {}
    inputs = {}
    runner.ensure_pinned_source(runner.W7_HTTPIE_SOURCE, directory)
    for role, source, dockerfile, artifact in (
            ('rust', runner.W6_RUST_SOURCE, runner.W6_DIR / 'rust/Dockerfile', '/src/target/release/hyperfine'),
            ('zlib', runner.W6_ZLIB_SOURCE, runner.W6_DIR / 'Dockerfile', '/src/libz.a')):
        context = directory / role
        context.mkdir()
        archive = runner.ensure_pinned_source(source, directory)
        shutil.copy(archive, context / source['file'])
        shutil.copy(dockerfile, context / 'Dockerfile')
        (context / 'stamp.txt').write_text(VERSION + '-untimed-reference\n')
        tag = 'np-linux-v1/reference-' + role + ':prepared'
        docker.sh(['build', '--load', '--platform', 'linux/amd64', '-t', tag, str(context)], timeout=3600)
        artifacts[role] = docker.sh(['run', '--rm', tag, 'sha256sum', artifact], timeout=120).stdout.split()[0]
        inputs[role] = {'source_sha256': source['sha256'], 'dockerfile_sha256': runner.sha256_file(dockerfile)}
        docker.sh(['rmi', tag])
    archive = directory / 'images.tar'
    docker.sh(['save', '-o', str(archive), *refs.values()], timeout=1200)
    ctrs.sh(['load', '-i', str(archive)], timeout=1200)
    images = {}
    for role, ref in refs.items():
        a, = json.loads(docker.sh(['image', 'inspect', ref]).stdout)
        b, = json.loads(ctrs.sh(['image', 'inspect', ref]).stdout)
        if a['Architecture'] != 'amd64' or b['Architecture'] != 'amd64' or a['RootFS']['Layers'] != b['RootFS']['Layers']:
            raise ValueError('prepared image bytes/architecture differ between engines: ' + role)
        images[role] = {'reference': ref, 'diff_ids': a['RootFS']['Layers'],
                        'ids': {'dockerd': a['Id'], 'ctrs': b['Id']}}
    lock = {'schema': 1, 'fixture_version': VERSION, 'platform': 'linux/amd64',
            'prepared_utc_epoch': time.time(), 'archive_sha256': runner.sha256_file(archive),
            'seed_sha256': runner.sha256_file(runner.W1_DIR / 'seed.sql'),
            'api_sources': {p.name: runner.sha256_file(p) for p in runner.API_DOCKERFILE_DIR.iterdir() if p.is_file()},
            'images': images, 'artifacts': artifacts, 'inputs': inputs,
            'host': linux_cgroups.host_metadata()}
    files = [runner.W6_DIR / 'Dockerfile', runner.W6_DIR / 'rust/Dockerfile',
             runner.W7_DIR / 'hyperfine/Dockerfile', runner.W7_DIR / 'httpie/Dockerfile',
             runner.W1_DIR / 'seed.sql', *[p for p in runner.API_DOCKERFILE_DIR.iterdir() if p.is_file()]]
    lock['files'] = {str(p.relative_to(HERE)): runner.sha256_file(p) for p in files}
    with LOCK.open('x') as output:
        output.write(json.dumps(lock, indent=2) + '\n')
    print('froze untimed Linux fixture lock:', LOCK, flush=True)
    return 0
