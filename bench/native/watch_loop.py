"""Pinned Marked watch/rebuild/test workflow; all engine effects use its endpoint."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import queue
import statistics
import subprocess
import sys
import tarfile
import tempfile
import threading
import time

import linux_lane

FIXTURE = Path(__file__).parent / 'fixtures/w5-v2'
IMAGE = 'np-w5-marked:v2'
RECEIPT_VERSION = 'w5-v3-marked-receipts'
MIN_TAIL_EDITS = 60


def contract():
    value = json.loads((FIXTURE / 'workload.json').read_text())
    if value['schema_version'] != 1:
        raise ValueError('unsupported W5 workload schema')
    return value


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_image(engine, archive, scratch):
    spec = contract()
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch, prefix='w5-build-') as temporary:
        context = Path(temporary)
        subprocess.run([sys.executable, str(FIXTURE / 'prepare.py'), str(archive), str(context / 'source')], check=True)
        for name in ('Dockerfile', 'watch.mjs', 'edit.mjs', 'verify.mjs', 'workload.json'):
            (context / name).write_bytes((FIXTURE / name).read_bytes())
        engine.sh(['buildx', 'build', '--builder', 'default', '--load', '--platform', 'linux/arm64',
                   '--build-arg', f"NODE_IMAGE={spec['tools']['image']}", '-t', IMAGE, str(context)], timeout=600)


def prepare_shared_image(engine, source_archive, image_archive):
    if image_archive.is_file():
        engine.sh(['image', 'load', '--input', str(image_archive)], timeout=180)
    else:
        prepare_image(engine, source_archive, image_archive.parent)
        engine.sh(['image', 'save', '--output', str(image_archive), IMAGE], timeout=180)
        if not image_archive.is_file():
            raise ValueError('W5 image export missing')


def pinned_source(archive):
    source = contract()['source']
    if not archive.is_file() or digest(archive) != source['sha256']:
        raise ValueError('W5 pinned source unavailable')
    files = {}
    lock = None
    root = f"{source['name']}-{source['version']}"
    with tarfile.open(archive, 'r:gz') as source_archive:
        for member in source_archive:
            path = PurePosixPath(member.name)
            if not path.parts or path.parts[0] != root or '..' in path.parts:
                raise ValueError('unexpected path in pinned W5 archive')
            if member.isdir():
                continue
            name = path.relative_to(root).as_posix()
            if not member.isfile() or name in files or name == '.':
                raise ValueError('nonregular or duplicate file in pinned W5 archive')
            with source_archive.extractfile(member) as file:
                data = file.read()
            files[name] = hashlib.sha256(data).hexdigest()
            if name == 'package-lock.json':
                lock = json.loads(data)
    if files.get('package-lock.json') != source['lock_sha256']:
        raise ValueError('W5 dependency lock SHA256 mismatch')
    return {'files': files, 'esbuild': lock['packages']['node_modules/esbuild']['version'],
            'source_sha256': source['sha256'], 'dependency_lock_sha256': source['lock_sha256']}


def check_image(engine, source):
    spec = contract()
    reference = linux_lane.workload_image(engine, 'marked')[0] if linux_lane.enabled() else IMAGE
    image = json.loads(engine.sh(['image', 'inspect', reference]).stdout)[0]
    if image['Architecture'] != ('amd64' if linux_lane.enabled() else 'arm64'):
        raise ValueError('W5 requires the lane native image')
    inputs = ('watch.mjs', 'edit.mjs', 'verify.mjs', 'workload.json')
    script = "const fs=require('node:fs'),c=require('node:crypto'),p=require('node:child_process');let files={};for(const f of JSON.parse(process.argv[1]))files[f]=c.createHash('sha256').update(fs.readFileSync(f)).digest('hex');console.log(JSON.stringify({node:process.version,npm:p.execFileSync('npm',['--version'],{encoding:'utf8'}).trim(),esbuild:require('esbuild/package.json').version,files}));"
    tools = json.loads(engine.sh(['run', '--rm', '--pull=never', '--network', 'none', '--entrypoint', 'node',
                                  image['Id'], '-e', script, json.dumps(inputs)]).stdout)
    if (tools['node'] != spec['tools']['node'] or tools['npm'] != spec['tools']['npm']
            or tools['esbuild'] != source['esbuild']):
        raise ValueError('W5 runtime tool version mismatch')
    if tools['files'] != {name: digest(FIXTURE / name) for name in inputs}:
        raise ValueError('W5 image does not match current fixture inputs; prepare it again')
    return {'image_id': image['Id'], 'layers': image['RootFS']['Layers'], 'tools': tools,
            'source_sha256': source['source_sha256'], 'dependency_lock_sha256': source['dependency_lock_sha256']}


def verify_mounted_inputs(engine, name, mode, mount_source, image_id, source, directory):
    inspected = json.loads(engine.sh(['inspect', name]).stdout)[0]
    mounts = [mount for mount in inspected['Mounts'] if mount['Destination'] == '/src']
    identity_key = 'Name' if mode == 'volume' else 'Source'
    if (inspected['Image'] != image_id or len(mounts) != 1 or mounts[0]['Type'] != mode
            or mounts[0].get(identity_key) != mount_source or mounts[0].get('RW') is not True):
        raise ValueError('W5 watcher image or mount identity mismatch')
    script = (FIXTURE / 'mounted-inputs.mjs').read_text()
    observed = json.loads(engine.sh(['exec', name, 'node', '--input-type=module', '-e',
                                    script, '/src', '/opt/app']).stdout)
    receipt = {'image_id': image_id, 'mount': mounts[0], 'source_sha256': source['source_sha256'],
               'observed': observed}
    (directory / 'mounted-inputs.json').write_text(json.dumps(receipt, indent=2) + '\n')
    expected_app = {name: sha for name, sha in source['files'].items()
                    if name.startswith('bin/') or name in ('package.json', 'package-lock.json')}
    if observed != {'mounted_files': source['files'], 'app_files': expected_app}:
        raise ValueError('W5 mounted source or installed CLI/lock differs from pinned archive')
    return inspected['State']


def edit_source(root, state, spec):
    if state not in ('original', 'edited'):
        raise ValueError('invalid W5 source state')
    path = Path(root) / spec['edit']['path']
    if path.is_symlink() or not path.is_file():
        raise ValueError('W5 source must be a regular file')
    old = spec['edit']['original' if state == 'edited' else 'edited']
    new = spec['edit'][state]
    text = path.read_text()
    if text.count(old) != 1 or new in text:
        raise ValueError('unexpected renderer source; refusing edit')
    path.write_text(text.replace(old, new))


def validate_event(event, state, spec):
    if (event.get('event') != 'tested' or event.get('state') != state or
            event.get('output') != spec['test'][state]):
        raise ValueError(f'W5 unexpected rebuild/test result: {event}')


def run_mode(engine, directory, mode, run_id, archive, iterations, phase, *, docker_cli, image_id, source_receipt):
    if mode not in ('bind', 'volume') or iterations < 1:
        raise ValueError('invalid W5 mode or edit count')
    spec = contract()
    directory.mkdir(parents=True, exist_ok=True)
    name = f'np-{run_id}-{engine.name}-{mode}'
    volume = name + '-src'
    label = f'dev.ctrs.campaign.run={run_id}'
    proc = thread = None
    events = queue.Queue(maxsize=32)
    errors = []
    stream_errors = []
    edits = []
    primary = None
    started = time.monotonic()
    out = (directory / 'watcher.jsonl').open('w')
    err = (directory / 'stderr.log').open('wb')
    try:
        with phase('setup'):
            if mode == 'bind':
                source = directory / 'source'
                subprocess.run([sys.executable, str(FIXTURE / 'prepare.py'), str(archive), str(source)], check=True)
                mount_source = str(source.resolve())
            else:
                engine.sh(['volume', 'create', '--label', label, volume])
                info = json.loads(engine.sh(['volume', 'inspect', volume]).stdout)[0]
                if (info.get('Labels') or {}).get('dev.ctrs.campaign.run') != run_id:
                    raise ValueError('W5 volume population ownership mismatch')
                engine.sh(['run', '--rm', '--pull=never', '--network', 'none', '--label', label, '-v',
                           f'{volume}:/src', '--entrypoint', 'sh', image_id, '-c', 'cp -a /opt/seed/. /src/'])
                mount_source = volume
            proc = subprocess.Popen([docker_cli, 'run', '--pull=never', '--name', name, '--label', label,
                                     '--network', 'none', '-v', f'{mount_source}:/src', image_id], env=engine.env(),
                                    stdout=subprocess.PIPE, stderr=err, text=True, bufsize=1)
            def reader():
                try:
                    for line in proc.stdout:
                        received = time.monotonic()
                        out.write(line)
                        out.flush()
                        events.put_nowait((received, line))
                except Exception as exc:
                    stream_errors.append(str(exc))
                finally:
                    try:
                        events.put_nowait((time.monotonic(), None))
                    except queue.Full:
                        pass
            thread = threading.Thread(target=reader)
            thread.start()
            def receive(state):
                received, line = events.get(timeout=120)
                if line is None or stream_errors:
                    raise RuntimeError(f'W5 watcher exited or stream failed: {stream_errors}')
                validate_event(json.loads(line), state, spec)
                return received
            initial_event = receive('original')
        with phase('verify-inputs'):
            initial = verify_mounted_inputs(engine, name, mode, mount_source, image_id, source_receipt, directory)
            if initial['Pid'] <= 0 or not initial['Running']:
                raise ValueError('W5 watcher is not running')
        for index in range(iterations):
            state = 'edited' if index % 2 == 0 else 'original'
            with phase(f'edit-{index}'):
                begin = time.monotonic()
                if mode == 'bind':
                    edit_source(source, state, spec)
                else:
                    engine.sh(['exec', name, 'node', '/opt/app/edit.mjs', '/src', state])
                command_end = time.monotonic()
                received = receive(state)
            edits.append({'state': state, 'edit_started': begin, 'edit_command_returned': command_end,
                          'tested_event_received': received, 'edit_to_result_s': received - begin,
                          'command_s': command_end - begin})
        final = json.loads(engine.sh(['inspect', name]).stdout)[0]['State']
        if not final['Running'] or final['Pid'] != initial['Pid'] or final['StartedAt'] != initial['StartedAt']:
            raise ValueError('W5 watcher process restarted')
        if not events.empty() or stream_errors:
            raise ValueError('unexpected W5 duplicate event or stream error')
    except Exception as exc:
        primary = exc
    finally:
        with phase('cleanup'):
            def remove_container():
                info = engine.sh(['inspect', name], check=False)
                if info.returncode == 0:
                    if json.loads(info.stdout)[0]['Config']['Labels'].get('dev.ctrs.campaign.run') != run_id:
                        raise ValueError('W5 container cleanup ownership mismatch')
                    engine.sh(['rm', '-f', name])
            def finish_client():
                if proc:
                    try:
                        code = proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        proc.terminate()
                        try:
                            code = proc.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            code = proc.wait(timeout=5)
                    (directory / 'planned-stop-exit.txt').write_text(str(code))
                if thread:
                    thread.join(timeout=5)
                    if thread.is_alive():
                        raise RuntimeError('W5 output reader did not exit')
            def remove_volume():
                if mode == 'volume':
                    info = engine.sh(['volume', 'inspect', volume], check=False)
                    if info.returncode == 0:
                        if json.loads(info.stdout)[0]['Labels'].get('dev.ctrs.campaign.run') != run_id:
                            raise ValueError('W5 volume cleanup ownership mismatch')
                        engine.sh(['volume', 'rm', volume])
            for action in (remove_container, finish_client, remove_volume):
                try:
                    action()
                except Exception as exc:
                    errors.append(str(exc))
            if thread is None or not thread.is_alive():
                out.close()
            err.close()
            (directory / 'cleanup.json').write_text(json.dumps({'errors': errors}))
    if primary:
        raise primary
    if errors:
        raise RuntimeError('; '.join(errors))
    result = {'mode': mode, 'setup_s': initial_event - started, 'edits': edits,
              'median_s': statistics.median(e['edit_to_result_s'] for e in edits),
              'interval': 'host edit begin to exact tested event received; includes volume exec transport'}
    (directory / 'result.json').write_text(json.dumps(result, indent=2))
    return result
