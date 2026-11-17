"""Matched W2 per-thread syscall/wake counters with raw profiler-off/on controls."""
import argparse
import json
import os
import re
from pathlib import Path
import secrets
import select
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import collect
import counter_specs
import diagnostic_signals
import ownership
import perf_counts
import cpu_profile
import runner
import sched_trace
from resource_pilot import host_snapshot
from w2_scheduler_app import parse_api_cpus

PIN = json.loads((runner.FIXTURES / 'w8-v2/portfolio.json').read_text())
TOOLS_SHA = '475ad5495772fa311084f9e15335c18aeffce3e8cb138c3d11e3f9a12b06883b'
HELPER = Path(__file__).with_name('w2_counter_guest.py')
BOOTSTRAP = Path(__file__).with_name('w2_scheduler_app.py')


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def frame(proc, event):
    if not select.select([proc.stdout], [], [], 15)[0]:
        raise RuntimeError('phase helper response deadline')
    line = proc.stdout.readline()
    if not line:
        raise RuntimeError('phase helper exited without frame')
    result = json.loads(line)
    if result['event'] != event:
        raise ValueError('unexpected phase helper frame')
    return result


def task_affinities(tasks, requested):
    if not tasks:
        raise ValueError('no API tasks for affinity validation')
    effective = {}
    for tid, task in tasks.items():
        lines = [line.split(':', 1)[1].strip() for line in task['status'].splitlines()
                 if line.startswith('Cpus_allowed_list:')]
        if len(lines) != 1 or not lines[0]:
            raise ValueError('missing or ambiguous API task affinity')
        cpus = set()
        for part in lines[0].split(','):
            match = re.fullmatch(r'([0-9]+)(?:-([0-9]+))?', part)
            if not match:
                raise ValueError('malformed API task affinity')
            start = int(match.group(1)); end = int(match.group(2) or start)
            if end < start or cpus.intersection(range(start, end + 1)):
                raise ValueError('malformed API task affinity')
            cpus.update(range(start, end + 1))
        if requested is not None and cpus != set(requested):
            raise ValueError('API task affinity differs from request: ' + tid)
        effective[tid] = sorted(cpus)
    return effective


def trial(engine, refs, archive, root, mode, operations, run, profile_kind='counters', api_cpus=None):
    directory = root / mode; directory.mkdir()
    project = runner.project_name(run, engine.name, mode)
    tag = 'np' + secrets.token_hex(6)
    port = runner.free_port(); base = f'http://127.0.0.1:{port}'
    override = directory / 'compose.json'
    save(override, {'services': {**{service: {'image': refs[image]} for service, image in (('db', 'postgres'), ('cache', 'redis'))},
         'api': {'image': refs['api'], 'privileged': True, 'command': ['python', '-u', '/diagnostics/w2_scheduler_app.py'],
                 'environment': {'NP_SCHED_TAG': tag, **({'NP_API_CPUS': ','.join(map(str, api_cpus))} if api_cpus is not None else {})}, 'volumes': [str(path.resolve()) + ':/diagnostics/' + path.name + ':ro' for path in (HELPER, BOOTSTRAP, Path(counter_specs.__file__))]}}})
    def compose(args):
        return engine.sh(['compose', '-f', str(runner.COMPOSE_FILE), '-f', str(override), '-p', project, *args],
                         env_extra={'NP_API_PORT': str(port), 'NP_API_TAG': runner.API_TAG}, timeout=120)
    api = None
    phase = profiler = profiler_log = phase_log = None
    version = cpu_profile.VERSION if profile_kind == 'cpu' else counter_specs.VERSION
    if api_cpus is not None:
        version += '-api-affinity-v1'
    result = {'fixture_version': version, 'profile_kind': profile_kind, 'profile_identity': version + ('-' + ','.join(map(str, api_cpus)) if api_cpus is not None else ''), 'mode': mode, 'qualification_eligible': False, 'errors': [], 'cleanup_errors': [], 'requested_api_cpus': list(api_cpus) if api_cpus is not None else None, 'effective_api_cpus': {}}
    def helper(action, *extra, check=True):
        cp = engine.sh(['exec', '--privileged', api, 'python', '/diagnostics/w2_counter_guest.py', action, tag, *extra], timeout=15, check=False)
        (directory / (action + '.stdout')).write_text(cp.stdout)
        (directory / (action + '.stderr')).write_text(cp.stderr)
        if check and cp.returncode:
            raise RuntimeError('guest helper failed: ' + action + ': ' + cp.stderr)
        return cp
    try:
        compose(['up', '-d', '--no-build', '--pull', 'never'])
        if runner.wait_health(base, 60)[0] is None:
            raise RuntimeError('application readiness')
        api = compose(['ps', '-q', 'api']).stdout.strip()
        if not api or '\n' in api:
            raise ValueError('ambiguous API identity')
        for service, image in (('api', 'api'), ('db', 'postgres'), ('cache', 'redis')):
            cid = compose(['ps', '-q', service]).stdout.strip()
            info = json.loads(engine.sh(['inspect', cid]).stdout)[0]
            save(directory / (service + '-inspect.json'), info)
            if info['Config']['Image'] != refs[image]:
                raise ValueError('service image differs from pinned ref')
            installed = json.loads(engine.sh(['image', 'inspect', refs[image]]).stdout)[0]
            pin = PIN['images']['np-v2/' + image]
            save(directory / (service + '-image.json'), installed)
            if installed['Architecture'] != 'arm64' or refs[image] not in installed['RepoDigests'] or installed['RootFS']['Layers'] != pin['diff_ids']:
                raise ValueError('installed service content identity differs from pin')
        hashes = json.loads(engine.sh(['exec', api, 'python', '-c',
            "import pathlib,hashlib,json;print(json.dumps({p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in ['/app/app.py','/app/requirements.txt']}))"]).stdout)
        if hashes != PIN['api_files_sha256']:
            raise ValueError('API application inputs differ')
        engine.sh(['cp', str(archive), api + ':/tmp/np-tools.tgz'])
        helper('prepare')
        save(directory / 'guest-hardware.json', json.loads(helper('hardware').stdout))
        if engine.name == 'ctrs':
            (directory / 'guest-console.log').write_bytes((engine.dir / 'data/vm-console.log').read_bytes())
        engine.sh(['exec', '--privileged', api, 'mount', '-t', 'tracefs', 'tracefs', '/sys/kernel/tracing'])
        def load(label, count, write_ratio):
            out = directory / (label + '.json')
            cp = subprocess.run([sys.executable, str(runner.LOAD_PY), '--url', base, '--concurrency', '4',
                '--operations', str(count), '--write-ratio', str(write_ratio), '--seed', '7', '--out', str(out)],
                capture_output=True, text=True, timeout=90)
            (directory / (label + '.stdout')).write_text(cp.stdout)
            (directory / (label + '.stderr')).write_text(cp.stderr)
            summary = json.loads(out.read_text())
            if cp.returncode or summary['errors'] or summary['requests_ok'] != count:
                raise RuntimeError('fixed application work failed: ' + label)
            return summary
        load('warmup', 1000, 0)
        snapshot = "import pathlib,json;print(json.dumps({p.name:{f:(p/f).read_text() for f in ['comm','stat','status']} for p in pathlib.Path('/proc/1/task').iterdir()}))"
        tasks = json.loads(engine.sh(['exec', api, 'python', '-c', snapshot]).stdout)
        if any(task['comm'].strip() != tag for task in tasks.values()):
            raise ValueError('API task tag mismatch')
        save(directory / 'tasks-warm.json', tasks)
        result['effective_api_cpus']['warm'] = task_affinities(tasks, api_cpus)
        identity = ownership.discover(engine.name, Path(engine.socket.removeprefix('unix://')), engine.dir)
        save(directory / 'running-engine.json', identity)
        if engine.name == 'ctrs' and [p['executable']['sha256'] for p in identity['required_processes'] if p['role'] == 'daemon'] != [runner.sha256_file(runner.CTRS_BIN)]:
            raise ValueError('adopted daemon differs from requested binary')
        if mode == 'on':
            if profile_kind == 'cpu':
                args = ['/tmp/np-tools/usr/bin/perf', 'record', '--no-inherit', '-t', ','.join(tasks),
                        '-e', 'cpu-clock', '-c', str(cpu_profile.PERIOD_NS), '--call-graph', 'dwarf,16384',
                        '--sample-cpu', '--clockid', 'mono', '-m', '256', '--delay=-1',
                        '--control', 'fifo:/tmp/np-count/control,/tmp/np-count/ack', '-o', '/tmp/np-count/cpu.data']
            else:
                helper('probes')
                args = ['/tmp/np-tools/usr/bin/perf', 'stat', '-j', '--per-thread', '--no-inherit', '-t', ','.join(tasks),
                        '--delay=-1', '--control', 'fifo:/tmp/np-count/control,/tmp/np-count/ack', '-o', '/tmp/np-count/stat.json']
                spec = counter_specs.selectors(tag)
                save(directory / 'selectors.json', spec)
                for selector in spec:
                    args += ['-e', selector['event']]
                    if selector['filter']:
                        args += ['--filter', selector['filter']]
            profiler_log = (directory / 'profiler.log').open('wb')
            profiler = subprocess.Popen([runner.DOCKER, 'exec', '--privileged', api, 'python', '/diagnostics/w2_counter_guest.py',
                'launch', tag, *args], env=engine.env(), stdout=profiler_log, stderr=subprocess.STDOUT)
        host_snapshot(directory, 'before')
        phase_log = (directory / 'phase.stderr').open('wb')
        phase = subprocess.Popen([runner.DOCKER, 'exec', '-i', '--privileged', api, 'python', '/diagnostics/w2_counter_guest.py',
            'phase', tag, mode], env=engine.env(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=phase_log, text=True)
        before = frame(phase, 'ready'); save(directory / 'phase-before.json', before)
        result['effective_api_cpus']['before'] = task_affinities(before['tasks'], api_cpus)
        cpu_profile.check_attachment(tasks, before['tasks'], before['clock_ticks'])
        host_before = collect.cpu_boundary(identity)
        started = time.monotonic()
        summary = load('work', operations, .3)
        ended = time.monotonic()
        host_after = collect.cpu_boundary(identity)
        phase.stdin.write('STOP\n'); phase.stdin.flush(); phase.stdin.close()
        after = frame(phase, 'done'); save(directory / 'phase-after.json', after)
        host_snapshot(directory, 'after')
        result['effective_api_cpus']['after'] = task_affinities(after['tasks'], api_cpus)
        if phase.wait(timeout=15):
            raise RuntimeError('phase helper exit failed')
        delta = sched_trace.application_cpu_delta(before['tasks'], after['tasks'], before['clock_ticks'], required_tids=tasks)
        if delta['status'] != 'ok':
            raise ValueError('API CPU coverage invalid: ' + repr(delta))
        host_cpu = collect.cpu_delta(host_before, host_after)
        if host_cpu['errors']:
            raise ValueError('host CPU coverage invalid: ' + repr(host_cpu['errors']))
        save(directory / 'host-cpu.json', host_cpu)
        result.update(application_cpu=delta, host_cpu=host_cpu, successful_operations=operations,
            application_cpu_seconds_per_success=delta['cpu_seconds'] / operations,
            workload_host_started_monotonic=started, workload_host_ended_monotonic=ended,
            workload_wall_seconds=ended - started, helper_counter_window_seconds=after['counter_window_seconds'],
            phase_scope='live helper window encloses same fixed load-driver launch/completion; host CPU boundaries bracket only load driver; both exclude setup and verification',
            reads_ok=summary['reads_ok'], writes_ok=summary['writes_ok'], tag=tag)
        if mode == 'on':
            helper('stop')
            code = profiler.wait(timeout=15)
            result['profiler_exit'] = code
            if code not in (0, 130):
                raise RuntimeError('profiler exit failed')
            if profile_kind == 'cpu':
                engine.sh(['cp', api + ':/tmp/np-count/cpu.data', str(directory / 'cpu.data')])
                script = engine.sh(['exec', '--privileged', api, 'env', 'LD_LIBRARY_PATH=/tmp/np-tools/lib/aarch64-linux-gnu',
                    '/tmp/np-tools/usr/bin/perf', 'script', '--ns', '--show-lost-events',
                    '-F', 'comm,pid,tid,cpu,time,event,ip,sym,dso', '-i', '/tmp/np-count/cpu.data'], timeout=60)
                (directory / 'cpu.txt').write_text(script.stdout)
                (directory / 'cpu-script.stderr').write_text(script.stderr)
                raw = engine.sh(['exec', '--privileged', api, 'env', 'LD_LIBRARY_PATH=/tmp/np-tools/lib/aarch64-linux-gnu',
                    '/tmp/np-tools/usr/bin/perf', 'script', '-D', '-i', '/tmp/np-count/cpu.data'], timeout=60)
                (directory / 'cpu-raw-events.txt').write_text(raw.stdout)
                (directory / 'cpu-raw-events.stderr').write_text(raw.stderr)
                if not raw.stdout:
                    raise ValueError('missing raw CPU event audit')
                profiler_log.flush()
                profile = cpu_profile.analyze(script.stdout, tag=tag, tasks_before=before['tasks'], tasks_after=after['tasks'],
                    application_cpu=delta, successful_operations=operations,
                    diagnostics=(directory / 'profiler.log').read_text() + script.stderr + raw.stderr, raw_events=raw.stdout)
                save(directory / 'cpu-profile.json', profile)
                if profile['status'] != 'ok':
                    raise ValueError('CPU profile coverage invalid: ' + repr(profile['errors']))
                result['cpu_profile'] = profile
            else:
                engine.sh(['cp', api + ':/tmp/np-count/stat.json', str(directory / 'stat.json')])
                counts = perf_counts.summarize_detail((directory / 'stat.json').read_text(), tag=tag, required_tids=tasks, successful_operations=operations)
                save(directory / 'counts.json', counts)
                if counts['status'] != 'ok':
                    raise ValueError('event counter coverage invalid: ' + repr(counts['errors']))
                profile = json.loads(helper('probe-profile').stdout)
                if profile['status'] != 'ok':
                    raise ValueError('probe miss coverage invalid')
                result['probe_profile'] = profile
                result['counts'] = counts
        db = compose(['ps', '-q', 'db']).stdout.strip()
        rows = json.loads(engine.sh(['exec', db, 'psql', '-U', 'app', '-d', 'app', '-At', '-c',
            'SELECT json_agg(json_build_array(name,payload)) FROM items']).stdout)
        save(directory / 'persisted-items.json', rows)
        writes = [json.loads(line) for line in (directory / 'work.json.writes.jsonl').read_text().splitlines()]
        if not runner.exact_w2_items(rows, writes):
            raise ValueError('exact persisted application data differs')
        if ownership.discover(engine.name, Path(engine.socket.removeprefix('unix://')), engine.dir) != identity:
            raise ValueError('running process/artifact identity changed')
        result['correctness'] = True
    except BaseException as exc:
        result['errors'].append(repr(exc)); result['correctness'] = False
        raise
    finally:
        for proc, label in ((phase, 'phase'), (profiler, 'profiler')):
            try:
                if proc is not None and proc.poll() is None:
                    if label == 'profiler':
                        helper('stop')
                    else:
                        proc.stdin.close() if proc.stdin and not proc.stdin.closed else None
                    proc.wait(timeout=15)
            except Exception as exc:
                result['cleanup_errors'].append(label + ': ' + repr(exc))
                if proc is not None and proc.poll() is None:
                    proc.kill(); proc.wait(timeout=5)
        try:
            if api and mode == 'on' and profile_kind == 'counters':
                helper('cleanup')
        except Exception as exc:
            result['cleanup_errors'].append('probes: ' + repr(exc))
        try:
            compose(['down', '-v', '--remove-orphans'])
        except Exception as exc:
            result['cleanup_errors'].append('compose: ' + repr(exc))
        for log in (profiler_log, phase_log):
            if log is not None:
                log.close()
        if result['cleanup_errors']:
            result['correctness'] = False
        save(directory / 'result.json', result)
    if result['cleanup_errors']:
        raise RuntimeError('owned diagnostic cleanup failed')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tools-archive', type=Path, required=True)
    parser.add_argument('--image-refs', type=Path, required=True)
    parser.add_argument('--ctrs-binary', type=Path, required=True)
    parser.add_argument('--operations', type=int, default=5000)
    parser.add_argument('--engines', default='ctrs,orbstack')
    parser.add_argument('--api-cpus', type=parse_api_cpus, default=None, help='explicit comma-separated guest API CPU IDs')
    parser.add_argument('--profile-kind', choices=('counters', 'cpu'), default='counters')
    parser.add_argument('--mode-order', choices=('off,on', 'on,off'), default='off,on')
    args = parser.parse_args()
    engines = args.engines.split(',')
    if not 1 <= args.operations <= 100000 or len(set(engines)) != len(engines) or any(name not in ('ctrs', 'orbstack') for name in engines):
        parser.error('require 1..100000 operations and distinct supported engines')
    if sys.platform != 'darwin' or os.uname().machine != 'arm64':
        parser.error('native ARM64 macOS only')
    archive = args.tools_archive.resolve()
    if runner.sha256_file(archive) != TOOLS_SHA or runner.sha256_file(runner.LOAD_PY) != PIN['w2_load_sha256']:
        parser.error('profiler/workload input differs from pin')
    supplied = json.loads(args.image_refs.read_text())
    refs = {name: supplied[name] for name in ('api', 'postgres', 'redis')}
    for name, ref in refs.items():
        if '@' not in ref or ref.rsplit('@', 1)[-1] != PIN['images']['np-v2/' + name]['manifest']:
            parser.error('service reference differs from pin')
    diagnostic_signals.install_cleanup_signals()
    runner.DOCKER = runner.find_docker(); runner.CTRS_BIN = args.ctrs_binary.resolve()
    run = ('w2-affinity-cpu-' if args.profile_kind == 'cpu' else 'w2-affinity-count-') if args.api_cpus is not None else ('w2-cpu-' if args.profile_kind == 'cpu' else 'w2-count-')
    run = run + time.strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(2)
    root = runner.RESULTS / run; root.mkdir()
    sources = root / 'source'; sources.mkdir()
    hashes = {}
    for path in (Path(__file__), HELPER, BOOTSTRAP, runner.LOAD_PY, Path(perf_counts.__file__), Path(cpu_profile.__file__), Path(counter_specs.__file__), Path(sched_trace.__file__), runner.FIXTURES / 'w8-v2/portfolio.json'):
        (sources / path.name).write_bytes(path.read_bytes()); hashes[path.name] = runner.sha256_file(path)
    save(root / 'plan.json', {'fixture_version': (cpu_profile.VERSION if args.profile_kind == 'cpu' else counter_specs.VERSION) + ('-api-affinity-v1' if args.api_cpus is not None else ''),
        'requested_api_cpus': list(args.api_cpus) if args.api_cpus is not None else None,
        'profile_identity': (cpu_profile.VERSION if args.profile_kind == 'cpu' else counter_specs.VERSION) + ('-api-affinity-v1-' + ','.join(map(str, args.api_cpus)) if args.api_cpus is not None else ''),
        'profile_kind': args.profile_kind, 'fixed_cpu_clock_period_ns': cpu_profile.PERIOD_NS if args.profile_kind == 'cpu' else None,
        'mode_order': args.mode_order.split(','), 'engine_order': engines,
        'operations': args.operations, 'refs': refs, 'tools_sha256': TOOLS_SHA, 'source_sha256': hashes,
        'qualification_eligible': False, 'reason': 'functional counter pilot; foreign host load and unfrozen candidate',
        'comparison_label': 'functional capacity-disclosed diagnostic; allocation equality not asserted',
        'ctrs_requested_cpus': os.environ.get('CTRS_CPUS'), 'ctrs_requested_memory_mib': os.environ.get('CTRS_MEMORY_MIB'),
        'observer_confirmation_budget': {'application_cpu_relative': .05, 'workload_wall_relative': .05,
            'required': 'exclusive host; interleaved confirmations; CPU difference above counter quantization'},
        'scope': 'separate per-API-thread cpu-clock sampling with native DWARF stacks; no syscall probes; zero loss required' if args.profile_kind == 'cpu' else
                 'matched stock ARM64 syscall-entry kprobes on both engines; per-API-thread attachment; no sampled trace buffer/loss; missing counts invalidate'})
    print('RESULTS', root, flush=True)
    for name in engines:
        directory = root / name; directory.mkdir()
        engine = runner.Engine(name, run)
        host_snapshot(directory, 'before')
        try:
            engine.ensure_up()
            records = [trial(engine, refs, archive, directory, mode, args.operations, run, args.profile_kind, args.api_cpus) for mode in args.mode_order.split(',')]
            save(directory / 'observer-raw-control.json', {**{record['mode']: record for record in records}, 'overhead_verdict': 'inconclusive',
                'reason': 'individual diagnostic block; host exclusivity and observer confirmation not certified; raw records only, no median-ratio correction'})
        finally:
            try:
                engine.stop()
            finally:
                host_snapshot(directory, 'after')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
