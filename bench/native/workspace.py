"""Pinned W12 workspace fixture helpers and trial entry points."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

FIXTURE = Path(__file__).parent / 'fixtures' / 'w12'
INPUTS = Path(__file__).resolve().parents[2] / '.work' / 'tmp'
WATCH_DEADLINE_SECONDS = 10.0
BUILD_PHASES = ('install', 'build', 'typecheck', 'test-discovery', 'warm-rebuild',
                'multi-file-change', 'branch-switch')


def source_contract():
    spec = json.loads((FIXTURE / 'workload.json').read_text())
    if spec['fixture_version'] != 'w12-v1':
        raise ValueError('unexpected W12 fixture version')
    for name, expected in spec['patch'].items():
        if hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest() != expected:
            raise ValueError('W12 patch hash mismatch')
    return spec


def verify_output(actual, expected):
    if actual != expected:
        raise ValueError(f'W12 output mismatch: expected {expected!r}, got {actual!r}')
    return True


def classify_result(expected, observed, timed_out):
    if observed == expected:
        return 'correct'
    if timed_out and observed is None:
        return 'missed'
    return 'stale'


def observed_stale(actual, expected, previous, diagnostic_ok):
    changed_wrong = actual is not None and actual != previous and actual != expected
    changed_without_valid_diagnostics = actual == expected and actual != previous and not diagnostic_ok
    return changed_wrong or changed_without_valid_diagnostics


def phase_metrics(phases):
    walls = {name: phases[name]['operation_wall_seconds'] for name in BUILD_PHASES}
    metrics = {name.replace('-', '_') + '_seconds': value for name, value in walls.items()}
    metrics['workflow_seconds'] = sum(walls.values())
    return metrics


def ensure_image(engine, image, spec):
    cp = engine.sh(['image', 'inspect', image], check=False, timeout=60)
    if cp.returncode != 0:
        engine.sh(['image', 'load', '--input', str(INPUTS / 'w12-image.tar')], timeout=900)
        cp = engine.sh(['image', 'inspect', image], timeout=60)
    inspected = json.loads(cp.stdout)[0]
    if inspected['Id'] != image or inspected['Architecture'] != 'arm64' or inspected['RootFS']['Layers'] != spec['prepared_image']['diff_ids']:
        raise ValueError('W12 image identity mismatch')


def verify_burst(seconds):
    if not 0 <= seconds <= .05:
        raise ValueError('W12 burst writes exceeded 50 ms')


def edit_plan(paths, edits=60):
    if len(paths) < 10 or len(set(paths)) != len(paths) or edits < 60:
        raise ValueError('W12 watch requires 60 edits across at least 10 distinct files')
    kinds = ('save', 'atomic', 'create_import', 'rename', 'delete', 'burst')
    result = []
    for i in range(edits):
        kind = kinds[i % len(kinds)]
        selected = [paths[(i + j) % len(paths)] for j in range(5 if kind == 'burst' else 1)]
        result.append({'sequence': i, 'kind': kind, 'paths': selected,
                       'token': f'w12-watch-{i:03d}'})
    return result


def digest(data):
    return hashlib.sha256(data).hexdigest()


def filesystem_counts(run):
    script = '''const fs=require('fs'),path=require('path');let count=0,bytes=0,deps=0;
function walk(d){for(const e of fs.readdirSync(d,{withFileTypes:true})){const p=path.join(d,e.name);if(e.isDirectory())walk(p);else if(e.isFile()){count++;bytes+=fs.statSync(p).size}}}
function packages(d){if(!fs.existsSync(d))return;for(const e of fs.readdirSync(d,{withFileTypes:true})){if(!e.isDirectory())continue;let p=path.join(d,e.name);if(e.name.startsWith('@')){for(const s of fs.readdirSync(p,{withFileTypes:true})){if(s.isDirectory())pkg(path.join(p,s.name))}}else pkg(p)}}
function pkg(p){if(fs.existsSync(path.join(p,'package.json')))deps++;packages(path.join(p,'node_modules'))}
walk('/app');packages('/app/node_modules');console.log(JSON.stringify({files:count,bytes,dependency_count:deps}));'''
    counts = json.loads(run(['node', '-e', script]).stdout)
    if counts['dependency_count'] < 400:
        raise ValueError('W12 installed fewer than 400 dependencies')
    return counts


def discard_source(engine, container, source):
    if source.exists() and engine.sh(['inspect', container], check=False, timeout=60).returncode != 0:
        shutil.rmtree(source)


def ready_image(engine, image, label, spec):
    result = engine.sh(['run', '--rm', '--label', label, '--network', 'none',
                        '--entrypoint', 'node', image, '--version'], timeout=120)
    if result.stdout.strip() != spec['tools']['node']:
        raise ValueError('W12 runtime readiness version mismatch')


def trial_w12(ctx, engine, state, layout='full-bind'):
    import os
    import subprocess
    import runner

    if layout not in ('full-bind', 'bind-source-volume-deps', 'all-volume'):
        raise ValueError('unknown W12 layout')
    trial_dir = ctx.trial_dir(engine.name, 'W12', state)
    rec = ctx.new_record(engine, 'W12', state, trial_dir)
    rec['metrics'].update(fixture_version='w12-v1', layout=layout)
    rec['inputs'] = {}
    spec = source_contract()
    label = 'dev.ctrs.campaign.run=' + ctx.run_id
    token = hashlib.sha256(rec['trial_id'].encode()).hexdigest()[:16]
    name = 'w12-' + token
    volume_names = []
    container_created = False
    sampler = trace = None
    image = spec['prepared_image'][engine.name + '_id']
    source = trial_dir / 'source'
    archive = INPUTS / 'kutt.tar.gz'
    phase = lambda name: runner.resource_phase(engine, rec, name)

    def run(args, timeout=900):
        return engine.sh(['exec', name, *args], timeout=timeout)

    def add_volume(suffix, destination, mounts):
        volume = name + '-' + suffix
        engine.sh(['volume', 'create', '--label', label, volume])
        volume_names.append(volume)
        mounts.extend(['--mount', f'type=volume,src={volume},dst={destination}'])

    def build():
        run(['sh', '-ec', './node_modules/.bin/tsc --project tsconfig.json && ./node_modules/.bin/copyfiles -f "server/mail/*.html" production-server/mail && ./node_modules/.bin/next build client/'])

    def output():
        script = (FIXTURE / 'receipt.js').read_text()
        return json.loads(run(['node', '-e', script]).stdout)

    def typecheck():
        cp = run(['./node_modules/.bin/tsc', '--noEmit', '-p', 'tsconfig.json'])
        if cp.stdout.strip() or cp.stderr.strip():
            raise ValueError('W12 typecheck returned diagnostics')

    def patch(reverse=False):
        script = '''const fs=require('fs'),crypto=require('crypto');
const items=JSON.parse(process.argv[1]),reverse=process.argv[2]==='true';
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
for(const item of items){const p='/app/'+item.path,old=fs.readFileSync(p),add=Buffer.from(item.append);
if(sha(old)!==(reverse?item.changed_sha256:item.base_sha256))throw Error('patch input mismatch '+p);
const next=reverse?old.subarray(0,old.length-add.length):Buffer.concat([old,add]);
if(sha(next)!==(reverse?item.base_sha256:item.changed_sha256))throw Error('patch output mismatch '+p);
fs.writeFileSync(p,next)}'''
        run(['node', '-e', script, (FIXTURE / 'patch.json').read_text(), str(reverse).lower()])

    try:
        if not archive.is_file() or digest(archive.read_bytes()) != spec['source']['sha256']:
            raise ValueError('W12 source archive missing or differs from pin')
        engine.ensure_up()
        ensure_image(engine, image, spec)
        ready_image(engine, image, label, spec)
        sampler, trace = runner.start_sampler(engine, trial_dir)
        if engine.measurement_identity.get('error') or not engine.measurement_identity.get('required_processes'):
            raise ValueError('W12 engine resource ownership is unverified')
        expected = spec['receipts']
        mounts = []
        with phase('setup'):
            if layout == 'all-volume':
                add_volume('source', '/app', mounts)
            else:
                source.mkdir()
                subprocess.run(['tar', '-xzf', str(archive), '--strip-components=1', '-C', str(source)], check=True)
                mounts.extend(['--mount', f'type=bind,src={source.resolve()},dst=/app'])
                if layout == 'bind-source-volume-deps':
                    add_volume('deps', '/app/node_modules', mounts)
                    add_volume('server', '/app/production-server', mounts)
                    add_volume('client', '/app/client/.next', mounts)
            engine.sh(['run', '-d', '--name', name, '--label', label, '--network', 'none',
                       *mounts, '-w', '/app', image, 'sleep', 'infinity'])
            container_created = True
            if layout == 'all-volume':
                run(['sh', '-ec', 'cp -a /fixture/source/. /app/'])
            inspected = json.loads(engine.sh(['inspect', name]).stdout)[0]
            if inspected['Config']['Labels'].get('dev.ctrs.campaign.run') != ctx.run_id:
                raise ValueError('W12 container ownership mismatch')
            if inspected['HostConfig']['NetworkMode'] != 'none':
                raise ValueError('W12 installation requires network none')
            observed = {m['Destination']: m for m in inspected['Mounts']}
            required = {'/app': ('volume', volume_names[0])} if layout == 'all-volume' else {'/app': ('bind', str(source.resolve()))}
            if layout == 'bind-source-volume-deps':
                required.update({'/app/node_modules': ('volume', volume_names[0]),
                                 '/app/production-server': ('volume', volume_names[1]),
                                 '/app/client/.next': ('volume', volume_names[2])})
            if set(observed) != set(required):
                raise ValueError('W12 mount destinations differ from requested layout')
            for destination, (kind, identity) in required.items():
                mount = observed[destination]
                if mount['Type'] != kind or mount.get('Name' if kind == 'volume' else 'Source') != identity or not mount.get('RW'):
                    raise ValueError(f'W12 mount identity mismatch: {destination}')
            rec['inputs']['mounts'] = inspected['Mounts']
            rec['inputs']['image_id'] = image
            rec['inputs']['diff_ids'] = spec['prepared_image']['diff_ids']
            rec['inputs']['cache'] = 'offline npm cache present; node_modules cold'
            rec['inputs']['phase_cache_state'] = {'setup': 'node_modules cold', 'install': 'node_modules cold',
                'build': 'node_modules warm', 'typecheck': 'node_modules warm',
                'test-discovery': 'node_modules warm', 'warm-rebuild': 'node_modules warm',
                'multi-file-change': 'node_modules warm', 'branch-switch': 'node_modules warm'}
            rec['inputs']['tools'] = {'node': run(['node', '--version']).stdout.strip(),
                                      'npm': run(['npm', '--version']).stdout.strip()}
            checks = run(['sha256sum', '/fixture/source.tar.gz', '/app/package-lock.json']).stdout.splitlines()
            if [line.split()[0] for line in checks] != [spec['source']['sha256'], spec['source']['lock_sha256']]:
                raise ValueError('W12 source or lock hash mismatch')
            run(['test', '-d', '/fixture/npm-cache/_cacache'])
            rec['inputs']['source_sha256'] = spec['source']['sha256']
            rec['inputs']['dependency_lock_sha256'] = spec['source']['lock_sha256']
            if rec['inputs']['tools'] != {'node': spec['tools']['node'], 'npm': spec['tools']['npm']}:
                raise ValueError('W12 tool version mismatch')
        with phase('install'):
            run(['npm', 'ci', '--offline', '--legacy-peer-deps', '--cache', '/fixture/npm-cache', '--no-audit', '--no-fund'])
            rec['metrics'].update(filesystem_counts(run))
        with phase('build'):
            build()
            rec['inputs']['initial_output'] = output()
            verify_output(rec['inputs']['initial_output'], expected['base'])
        with phase('typecheck'):
            typecheck()
        with phase('test-discovery'):
            cp = run(['./node_modules/.bin/jest', '--listTests', '--runInBand'])
            tests = sorted(line.removeprefix('/app/') for line in cp.stdout.splitlines() if line.strip())
            verify_output(tests, expected['tests'])
            rec['inputs']['tests'] = tests
        with phase('warm-rebuild'):
            build()
            verify_output(output(), expected['base'])
        with phase('multi-file-change'):
            patch()
            build()
            typecheck()
            verify_output(output(), expected['changed'])
        with phase('branch-switch'):
            patch(True)
            build()
            typecheck()
            verify_output(output(), expected['base'])
        rec['correctness']['checks']['exact_outputs'] = True
        rec['metrics'].update(phase_metrics(rec['resources']['phases']))
        rec['correctness']['ok'] = True
    except Exception as exc:
        rec['correctness']['ok'] = False
        rec['validation_errors'].append(str(exc))
    finally:
        try:
            if sampler is not None:
                with phase('cleanup'):
                    if container_created:
                        info = json.loads(engine.sh(['inspect', name]).stdout)[0]
                        if info['Config']['Labels'].get('dev.ctrs.campaign.run') != ctx.run_id:
                            raise ValueError('refusing to remove unowned W12 container')
                        engine.sh(['rm', '-f', name])
                    for volume in volume_names:
                        info = json.loads(engine.sh(['volume', 'inspect', volume]).stdout)[0]
                        if info.get('Labels', {}).get('dev.ctrs.campaign.run') != ctx.run_id:
                            raise ValueError('refusing to remove unowned W12 volume')
                        engine.sh(['volume', 'rm', volume])
        except Exception as exc:
            rec['correctness']['ok'] = False
            rec['validation_errors'].append('cleanup: ' + str(exc))
        if sampler is not None:
            runner.stop_sampler(sampler)
            rec['resources'].update(runner.summarize_trace(trace) if trace else {})
        discard_source(engine, name, source)
    return rec


def trial_w12_watch(ctx, engine, state, mount='bind', edits=60):
    import os
    import re
    import subprocess
    import time
    import runner

    if mount not in ('bind', 'volume'):
        raise ValueError('unknown W12 watch mount')
    trial_dir = ctx.trial_dir(engine.name, 'W12-watch', state)
    rec = ctx.new_record(engine, 'W12-watch', state, trial_dir)
    rec['metrics'].update(fixture_version='w12-watch-v2', mount=mount, backend='fs.watch',
                          edit_transport='host filesystem' if mount == 'bind' else 'docker exec',
                          missed=0, stale=0, edits=[])
    spec = source_contract()
    paths = [item['path'] for item in json.loads((FIXTURE / 'patch.json').read_text())]
    plan = edit_plan(paths, edits)
    token = hashlib.sha256(rec['trial_id'].encode()).hexdigest()[:16]
    name, volume = 'w12w-' + token, 'w12w-' + token + '-source'
    label = 'dev.ctrs.campaign.run=' + ctx.run_id
    source = trial_dir / 'source'
    image = spec['prepared_image'][engine.name + '_id']
    created = vol_created = False
    sampler = trace = None
    phase = lambda label: runner.resource_phase(engine, rec, label)

    def run(args, timeout=900):
        return engine.sh(['exec', name, *args], timeout=timeout)

    def apply_host(actions):
        starts = []
        for action in actions:
            starts.append(time.monotonic())
            target = source / action['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            if action['kind'] == 'delete':
                target.unlink()
            elif action['kind'] == 'rename':
                (source / action['from']).rename(target)
                target.write_text(action['content'])
            elif action['kind'] == 'atomic':
                temporary = target.with_name(target.name + '.w12-tmp')
                temporary.write_text(action['content'])
                temporary.replace(target)
            else:
                target.write_text(action['content'])
        return starts, time.monotonic() - starts[0]

    def apply(actions):
        if mount == 'bind':
            return apply_host(actions)
        else:
            script = (FIXTURE / 'watch-edit.js').read_text()
            started = time.monotonic()
            receipt = json.loads(run(['node', '-e', script, json.dumps(actions)]).stdout)
            starts = [started + offset / 1000 for offset in receipt['starts_ms']]
            return starts, (receipt['completed_ms'] - receipt['starts_ms'][0]) / 1000

    def evaluate(items):
        script = (FIXTURE / 'watch-eval.js').read_text()
        return json.loads(run(['node', '-e', script, json.dumps(items)], timeout=30).stdout)

    def source_value(path, token):
        original = base_sources[path]
        symbol = 'w12WatchValue' + hashlib.sha256(path.encode()).hexdigest()[:12]
        return original + f'\nexport const {symbol} = "{token}";\n'

    try:
        archive = INPUTS / 'kutt.tar.gz'
        if not archive.is_file() or digest(archive.read_bytes()) != spec['source']['sha256']:
            raise ValueError('W12 source archive missing or differs from pin')
        engine.ensure_up()
        ensure_image(engine, image, spec)
        ready_image(engine, image, label, spec)
        sampler, trace = runner.start_sampler(engine, trial_dir)
        if engine.measurement_identity.get('error') or not engine.measurement_identity.get('required_processes'):
            raise ValueError('W12 watcher resource ownership is unverified')
        source.mkdir()
        subprocess.run(['tar', '-xzf', str(archive), '--strip-components=1', '-C', str(source)], check=True)
        base_sources = {path: (source / path).read_text() for path in paths}
        with phase('setup'):
            if mount == 'volume':
                engine.sh(['volume', 'create', '--label', label, volume])
                vol_created = True
                mount_arg = f'type=volume,src={volume},dst=/app'
            else:
                mount_arg = f'type=bind,src={source.resolve()},dst=/app'
            engine.sh(['run', '-d', '--name', name, '--label', label, '--network', 'none',
                       '--mount', mount_arg, '-w', '/app', image, 'sleep', 'infinity'])
            created = True
            if mount == 'volume':
                run(['sh', '-ec', 'cp -a /fixture/source/. /app/'])
            info = json.loads(engine.sh(['inspect', name]).stdout)[0]
            if info['Config']['Labels'].get('dev.ctrs.campaign.run') != ctx.run_id or info['HostConfig']['NetworkMode'] != 'none':
                raise ValueError('W12 watcher ownership or network mismatch')
            mounts = info['Mounts']
            if len(mounts) != 1 or mounts[0]['Destination'] != '/app' or mounts[0]['Type'] != mount or not mounts[0].get('RW'):
                raise ValueError('W12 watcher mount mismatch')
            if mounts[0].get('Name' if mount == 'volume' else 'Source') != (volume if mount == 'volume' else str(source.resolve())):
                raise ValueError('W12 watcher mount identity mismatch')
            rec['inputs'] = {'image_id': image, 'mounts': info['Mounts'], 'cache': 'offline npm cache present; node_modules cold'}
            rec['inputs']['phase_cache_state'] = {'setup': 'node_modules cold', 'edits': 'node_modules warm'}
            checks = run(['sha256sum', '/fixture/source.tar.gz', '/app/package-lock.json']).stdout.splitlines()
            if [line.split()[0] for line in checks] != [spec['source']['sha256'], spec['source']['lock_sha256']]:
                raise ValueError('W12 watcher source or lock hash mismatch')
            run(['test', '-d', '/fixture/npm-cache/_cacache'])
            rec['inputs'].update(source_sha256=spec['source']['sha256'], dependency_lock_sha256=spec['source']['lock_sha256'], diff_ids=spec['prepared_image']['diff_ids'])
            run(['npm', 'ci', '--offline', '--legacy-peer-deps', '--cache', '/fixture/npm-cache', '--no-audit', '--no-fund'])
            rec['metrics'].update(filesystem_counts(run))
            tools = {'node': run(['node', '--version']).stdout.strip(), 'npm': run(['npm', '--version']).stdout.strip()}
            if tools != {'node': spec['tools']['node'], 'npm': spec['tools']['npm']}:
                raise ValueError('W12 watcher tool version mismatch')
            rec['inputs']['tools'] = tools
            base_importer = 'server/w12watch/importer.ts'
            apply([{'kind': 'write', 'path': base_importer,
                    'content': 'export const value = "w12-watch-initial";\n'}])
            run(['sh', '-ec', 'mkdir -p /tmp/w12; ./node_modules/.bin/tsc --project tsconfig.json'])
            initial = evaluate([{'path': base_importer, 'content': 'export const value = "w12-watch-initial";\n'}])
            if any(item['actual'] != item['expected'] for item in initial):
                raise ValueError('watch output oracle disagrees with initial TypeScript compilation')
            engine.sh(['exec', '-d', '-e', 'TSC_WATCHFILE=UseFsEvents', '-e', 'TSC_WATCHDIRECTORY=UseFsEvents', name,
                       'sh', '-ec', './node_modules/.bin/tsc --watch -p tsconfig.json --pretty false --preserveWatchOutput > /tmp/w12/watch.log 2>&1'])
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                log = run(['cat', '/tmp/w12/watch.log'], timeout=15).stdout
                if 'Watching for file changes' in log and 'Found 0 errors' in log:
                    break
                time.sleep(.2)
            else:
                raise TimeoutError('W12 watcher did not become ready')
        with phase('edits'):
            for event in plan:
                kind, marker = event['kind'], event['token']
                actions, items = [], []
                if kind in ('save', 'atomic', 'burst'):
                    for index, path in enumerate(event['paths']):
                        content = source_value(path, marker + '-' + str(index))
                        actions.append({'kind': 'atomic' if kind == 'atomic' else 'write', 'path': path, 'content': content})
                        items.append({'path': path, 'content': content})
                elif kind == 'create_import':
                    content = f'export const value = "{marker}";\n'
                    importer = f'export {{ value }} from "./created";\nexport const marker = "{marker}";\n'
                    actions = [{'kind': 'write', 'path': 'server/w12watch/created.ts', 'content': content},
                               {'kind': 'write', 'path': base_importer, 'content': importer}]
                    items = [{'path': action['path'], 'content': action['content']} for action in actions]
                elif kind == 'rename':
                    content = f'export const value = "{marker}";\n'
                    importer = f'export {{ value }} from "./renamed";\nexport const marker = "{marker}";\n'
                    actions = [{'kind': 'rename', 'from': 'server/w12watch/created.ts', 'path': 'server/w12watch/renamed.ts', 'content': content},
                               {'kind': 'write', 'path': base_importer, 'content': importer}]
                    items = [{'path': action['path'], 'content': action['content']} for action in actions]
                else:
                    importer = f'export const value = "{marker}";\n'
                    actions = [{'kind': 'delete', 'path': 'server/w12watch/renamed.ts'},
                               {'kind': 'write', 'path': base_importer, 'content': importer}]
                    items = [{'path': base_importer, 'content': importer}]
                previous = evaluate(items)
                log_offset = len(run(['cat', '/tmp/w12/watch.log'], timeout=15).stdout)
                started = time.monotonic()
                write_starts, write_span = apply(actions)
                applied = time.monotonic()
                if kind == 'burst':
                    verify_burst(write_span)
                deadline = time.monotonic() + WATCH_DEADLINE_SECONDS
                stale = [False] * len(items)
                first_correct = [None] * len(items)
                while True:
                    current = evaluate(items)
                    observed = time.monotonic()
                    log = run(['cat', '/tmp/w12/watch.log'], timeout=15).stdout
                    diagnostics = re.findall(r'Found (\d+) errors?\. Watching for file changes\.', log[log_offset:])
                    diagnostic_ok = bool(diagnostics) and diagnostics[-1] == '0'
                    for index, (item, old) in enumerate(zip(current, previous)):
                        if item['actual'] == item['expected'] and diagnostic_ok and first_correct[index] is None:
                            first_correct[index] = observed
                        if observed_stale(item['actual'], item['expected'], old['actual'], diagnostic_ok):
                            stale[index] = True
                    if all(value is not None for value in first_correct):
                        break
                    if observed >= deadline:
                        break
                    time.sleep(.1)
                for index, item in enumerate(current):
                    status = classify_result(True, True if first_correct[index] is not None else (False if stale[index] else None), True)
                    if status != 'correct':
                        rec['metrics'][status] += 1
                    action_index = next((i for i, action in enumerate(actions)
                                         if item['path'] in (action['path'], action.get('from'))), 0)
                    host_start = write_starts[action_index] if mount == 'bind' else started
                    rec['metrics']['edits'].append({'sequence': event['sequence'], 'kind': kind,
                        'path': item['path'], 'host_started_monotonic': host_start,
                        'host_applied_monotonic': applied,
                        'observed_monotonic': first_correct[index] or observed,
                        'write_span_seconds': write_span,
                        'write_start_offsets_seconds': [value - write_starts[0] for value in write_starts],
                        'status': status, 'output': item})
        latencies = sorted(item['observed_monotonic'] - item['host_started_monotonic']
                           for item in rec['metrics']['edits'] if item['status'] == 'correct')
        rec['metrics'].update(results=len(rec['metrics']['edits']), correct=len(latencies),
                              deadline_seconds=WATCH_DEADLINE_SECONDS,
                              observation='host docker exec poll every 0.1 s; latency includes exec round trips',
                              edit_to_result_p50_s=latencies[len(latencies) // 2] if latencies else None,
                              edit_to_result_p95_s=latencies[int(.95 * (len(latencies) - 1))] if latencies else None)
        rec['correctness']['checks']['watch_run_completed'] = len(rec['metrics']['edits']) >= edits
        rec['correctness']['ok'] = rec['correctness']['checks']['watch_run_completed']
    except Exception as exc:
        rec['correctness']['ok'] = False
        rec['validation_errors'].append(str(exc))
    finally:
        try:
            if sampler is not None:
                with phase('cleanup'):
                    if created:
                        info = json.loads(engine.sh(['inspect', name]).stdout)[0]
                        if info['Config']['Labels'].get('dev.ctrs.campaign.run') != ctx.run_id:
                            raise ValueError('refusing to remove unowned W12 watcher')
                        engine.sh(['rm', '-f', name])
                    if vol_created:
                        info = json.loads(engine.sh(['volume', 'inspect', volume]).stdout)[0]
                        if info.get('Labels', {}).get('dev.ctrs.campaign.run') != ctx.run_id:
                            raise ValueError('refusing to remove unowned W12 volume')
                        engine.sh(['volume', 'rm', volume])
        except Exception as exc:
            rec['correctness']['ok'] = False
            rec['validation_errors'].append('cleanup: ' + str(exc))
        if sampler is not None:
            runner.stop_sampler(sampler)
            rec['resources'].update(runner.summarize_trace(trace) if trace else {})
        discard_source(engine, name, source)
    return rec
