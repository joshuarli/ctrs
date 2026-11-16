"""Pinned Marked watch/rebuild/test workflow; all engine effects use its endpoint."""
import hashlib
import json
import os
from pathlib import Path
import queue
import statistics
import subprocess
import sys
import tempfile
import threading
import time

FIXTURE = Path(__file__).parent / 'fixtures/w5-v2'
IMAGE = 'np-w5-marked:v2'


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


def check_image(engine):
    spec = contract()
    image = json.loads(engine.sh(['image', 'inspect', IMAGE]).stdout)[0]
    if image['Architecture'] != 'arm64':
        raise ValueError('W5 requires native ARM64 image')
    inputs = ('watch.mjs', 'edit.mjs', 'verify.mjs', 'workload.json')
    script = "const fs=require('node:fs'),c=require('node:crypto'),p=require('node:child_process');let files={};for(const f of JSON.parse(process.argv[1]))files[f]=c.createHash('sha256').update(fs.readFileSync(f)).digest('hex');console.log(JSON.stringify({node:process.version,npm:p.execFileSync('npm',['--version'],{encoding:'utf8'}).trim(),esbuild:require('esbuild/package.json').version,files}));"
    tools = json.loads(engine.sh(['run', '--rm', '--entrypoint', 'node', IMAGE, '-e', script, json.dumps(inputs)]).stdout)
    if tools['node'] != spec['tools']['node'] or tools['npm'] != spec['tools']['npm']:
        raise ValueError('W5 runtime tool version mismatch')
    if tools['files'] != {name: digest(FIXTURE / name) for name in inputs}:
        raise ValueError('W5 image does not match current fixture inputs; prepare it again')
    return {'image_id': image['Id'], 'layers': image['RootFS']['Layers'], 'tools': tools,
            'source_sha256': spec['source']['sha256'], 'dependency_lock_sha256': spec['source']['lock_sha256']}


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


def run_mode(engine, directory, mode, run_id, archive, iterations, phase, *, docker_cli):
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
                mount = f'{source.resolve()}:/src'
            else:
                engine.sh(['volume', 'create', '--label', label, volume])
                engine.sh(['run', '--rm', '--label', label, '-v', f'{volume}:/src', '--entrypoint', 'sh', IMAGE,
                           '-c', 'cp -a /opt/seed/. /src/'])
                mount = f'{volume}:/src'
            proc = subprocess.Popen([docker_cli, 'run', '--name', name, '--label', label,
                                     '--network', 'none', '-v', mount, IMAGE], env=engine.env(),
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
            initial = json.loads(engine.sh(['inspect', name]).stdout)[0]['State']
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
