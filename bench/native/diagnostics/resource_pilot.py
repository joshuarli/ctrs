"""Bounded W2 resource cycles; functional diagnostics never qualify performance."""
import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import diagnostic_signals
import mixed_cycle
import ownership
import resource_cells
import resource_cycles
import runner


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def host_snapshot(directory, label):
    for command, suffix in ((['perf-gate-ready'] + (['-1'] if label == 'after' else []), 'gate'),
                            (['ps', '-axo', 'pid,ppid,%cpu,lstart,command'], 'processes'),
                            (['pmset', '-g', 'therm'], 'thermal'), (['pmset', '-g', 'batt'], 'power')):
        try:
            cp = subprocess.run(command, capture_output=True, text=True, timeout=15)
            save(directory / f'{label}-{suffix}.json', {'command': command, 'exit': cp.returncode,
                 'stdout': cp.stdout, 'stderr': cp.stderr, 'observed_utc': runner.utcnow()})
        except Exception as exc:
            save(directory / f'{label}-{suffix}.json', {'command': command, 'error': str(exc)})


def active_disk_paths(engine, identity, supplied):
    paths = tuple(Path(p).absolute() for p in supplied) if supplied else (engine.dir / 'data/vm/data.img',)
    opened = {f.get('n') for p in identity['required_processes'] for f in ownership.open_files(p['pid'])}
    if any(str(p) not in opened or p.is_symlink() or not p.is_file() for p in paths):
        raise ValueError('every explicit backing file must be a regular, nonsymlink file open by the owned engine')
    snapshot = resource_cells.allocation_snapshot(paths)
    if snapshot['status'] != 'ok':
        raise ValueError(snapshot['errors'])
    return paths


def load_refs(path):
    refs = json.loads(path.read_text())
    if not isinstance(refs, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in refs.items()):
        raise ValueError('image refs must be an object of strings')
    mixed_cycle.validate_refs(refs)
    return refs


def verify_images(engine, refs, directory):
    for name in ('api', 'postgres', 'redis'):
        ref = refs[name]
        info = json.loads(engine.sh(['image', 'inspect', ref]).stdout)[0]
        pin = mixed_cycle.PIN['images']['np-v2/' + name]
        if info['Architecture'] != 'arm64' or ref not in info['RepoDigests'] or info['RootFS']['Layers'] != pin['diff_ids']:
            raise ValueError('installed image identity differs from pin: ' + name)
        save(directory / (name + '-image.json'), info)


def verify_binary(identity, binary_hash):
    if [p['executable']['sha256'] for p in identity['required_processes'] if p['role'] == 'daemon'] != [binary_hash]:
        raise ValueError('running daemon differs from requested binary')


class ResourceEngine(runner.Engine):
    def __init__(self, name, run_id, refs, directory):
        super().__init__(name, run_id)
        self.override = directory / 'compose-override.json'
        save(self.override, {'services': {service: {'image': refs[image]} for service, image in
             (('api', 'api'), ('db', 'postgres'), ('cache', 'redis'))}})

    def compose(self, project, args, env_extra=None, timeout=300):
        if args[:1] == ['up']:
            args = [*args, '--no-build', '--pull', 'never']
        return self.sh(['compose', '-f', str(runner.COMPOSE_FILE), '-f', str(self.override),
                        '-p', project, *args], env_extra=env_extra, timeout=timeout, check=False)


def warmup_api(engine, ref):
    command = "import json,hashlib,pathlib;print(json.dumps({p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest() for p in ['/app/app.py','/app/requirements.txt']}))"
    actual = json.loads(engine.sh(['run', '--rm', '--pull=never', ref, 'python', '-c', command], timeout=90).stdout)
    if actual != mixed_cycle.PIN['api_files_sha256']:
        raise ValueError('API contents differ from pin')
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image-refs', type=Path, required=True)
    parser.add_argument('--ctrs-binary', type=Path, required=True)
    parser.add_argument('--engines', default='ctrs,orbstack')
    parser.add_argument('--cycles', type=int, default=5)
    parser.add_argument('--operations', type=int, default=50000)
    parser.add_argument('--next-use-operations', type=int, default=1000)
    parser.add_argument('--idle-seconds', type=float, default=30)
    parser.add_argument('--reclaim-seconds', type=float, default=30)
    parser.add_argument('--orbstack-storage-file', type=Path, action='append', default=[])
    args = parser.parse_args()
    engines = args.engines.split(',')
    if (not engines or len(set(engines)) != len(engines) or any(e not in ('ctrs', 'orbstack') for e in engines)
            or not 1 <= args.cycles <= 10 or not 1 <= args.operations <= 1000000
            or not 1 <= args.next_use_operations <= 1000000
            or not all(math.isfinite(v) and 0 < v <= 120 for v in (args.idle_seconds, args.reclaim_seconds))):
        parser.error('require distinct valid engines, 1..10 cycles, 1..1000000 operations and finite durations in (0,120]')
    if 'orbstack' in engines and not args.orbstack_storage_file:
        parser.error('supply the actual open OrbStack active backing file(s); no guessed storage root')
    try:
        refs = load_refs(args.image_refs)
        binary = args.ctrs_binary.resolve(strict=True)
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise ValueError('ctrs binary must be an executable regular file')
        binary_hash = runner.sha256_file(binary)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    if sys.platform != 'darwin' or os.uname().machine != 'arm64':
        parser.error('native ARM64 macOS only')
    diagnostic_signals.install_cleanup_signals()
    runner.CTRS_BIN = binary
    runner.DOCKER = runner.find_docker()
    run_id = 'w2-resources-' + time.strftime('%Y%m%dT%H%M%S')
    ctx = runner.RunContext(run_id)
    ctx.design = 'resource-diagnostic'
    root = ctx.results_dir
    sources = root / 'source'
    sources.mkdir()
    source_hashes = {}
    for path in (Path(__file__), Path(runner.__file__), Path(resource_cycles.__file__),
                 Path(resource_cells.__file__), Path(ownership.__file__), runner.COLLECT,
                 runner.BENCH / 'macos_counters.py', runner.LOAD_PY, Path(mixed_cycle.__file__),
                 runner.COMPOSE_FILE, runner.FIXTURES / 'w1/seed.sql',
                 runner.FIXTURES / 'w8-v2/portfolio.json', runner.FIXTURES / 'w11-v2/worker-pin.json'):
        data = path.read_bytes()
        (sources / path.name).write_bytes(data)
        source_hashes[path.name] = runner.sha256_file(sources / path.name)
    save(root / 'plan.json', {'args': vars(args) | {'orbstack_storage_file': list(map(str, args.orbstack_storage_file)),
         'image_refs': str(args.image_refs), 'ctrs_binary': str(binary)},
         'image_refs': refs, 'image_refs_sha256': runner.sha256_file(args.image_refs),
         'ctrs_binary_sha256': binary_hash, 'budgets': resource_cycles.BUDGETS, 'driver_sha256': runner.sha256_file(Path(__file__)),
         'saved_source_sha256': source_hashes,
         'warmup_operations': args.operations,
         'resource_cycles_sha256': runner.sha256_file(Path(resource_cycles.__file__)),
         'qualification_eligible': False, 'reason': 'functional resource pilot; engine blocks and exclusivity not certified',
         'comparison_label': 'resource-matched default build driver',
         'storage_scope': 'explicit active backing files, inclusive shared extents; whole installed storage unknown'})
    print('RESULTS', root, flush=True)
    for name in engines:
        directory = root / name
        directory.mkdir()
        engine = ResourceEngine(name, run_id, refs, directory)
        summary = {'engine': name, 'qualification_eligible': False, 'cycles': [], 'errors': []}
        try:
            engine.ensure_up()
            inventory = engine.sh(['ps', '--no-trunc', '--format', '{{json .}}']).stdout
            (directory / 'containers-before.jsonl').write_text(inventory)
            if inventory.strip():
                raise RuntimeError('active containers contaminate the resource interval; none were stopped')
            identity = ownership.discover(name, Path(engine.socket.removeprefix('unix://')), engine.dir)
            save(directory / 'running-engine.json', identity)
            if name == 'ctrs':
                verify_binary(identity, binary_hash)
            verify_images(engine, refs, directory)
            save(directory / 'api-source.json', warmup_api(engine, refs['api']))
            paths = active_disk_paths(engine, identity, args.orbstack_storage_file if name == 'orbstack' else [])

            def trial(state, operations):
                rec = runner.trial_w2(ctx, engine, state, 4, 20, .3, 7, operations, allocation_paths=paths)
                rec['measurement_valid'] = False
                rec['measurement_errors'] = ['resource diagnostic; not an exclusive frozen qualification']
                ctx.write(rec)
                if not rec['correctness']['ok']:
                    raise RuntimeError(f'W2 correctness failed: {rec["trial_id"]}: {rec["validation_errors"]}')
                trace = runner.WORK / rec['resources']['trace']
                samples = [json.loads(line) for line in trace.read_text().splitlines()]
                manifest = json.loads((trace.parent / 'ownership.json').read_text())
                rec['resources']['phase_cells'] = {p: resource_cycles.phase_summary(manifest, v, samples)
                    for p, v in rec['resources']['phases'].items()}
                save(trace.parent / 'resource-cells.json', rec['resources']['phase_cells'])
                if any(v['status'] != 'ok' for v in rec['resources']['phase_cells'].values()):
                    raise RuntimeError(f'incomplete phase counters: {rec["trial_id"]}')
                return rec

            warm = trial('resource-warmup', args.operations)
            summary['warmup_trial_id'] = warm['trial_id']
            host_snapshot(directory, 'before')
            initial = resource_cycles.idle_interval(identity, args.idle_seconds, directory / 'initial-idle.jsonl')
            initial_allocation = resource_cells.allocation_snapshot(paths)
            summary.update(initial_idle=initial, initial_allocation=initial_allocation,
                           storage_paths=list(map(str, paths)))
            for index in range(args.cycles):
                work = trial(f'resource-cycle-{index}', args.operations)
                reclaimed = resource_cycles.idle_interval(identity, args.reclaim_seconds, directory / f'cycle-{index}-reclaim.jsonl')
                allocation = resource_cells.allocation_snapshot(paths)
                next_use = trial(f'resource-next-use-{index}', args.next_use_operations)
                phases = next_use['resources']['phases']
                summary['cycles'].append({'index': index, 'work_trial_id': work['trial_id'],
                    'phases': work['resources']['phase_cells'], 'allocation': work['resources']['disk_allocation'],
                    'reclaimed': reclaimed, 'allocation_reclaimed': allocation,
                    'next_use_trial_id': next_use['trial_id'],
                    'next_use_seconds': sum(phases[p]['operation_wall_seconds'] for p in ('setup', 'workload')),
                    'next_use_scope': 'stack setup/readiness plus fixed successful operations; includes command cost; excludes owned cleanup'})
                save(directory / 'summary.json', summary)
            current = ownership.discover(name, Path(engine.socket.removeprefix('unix://')), engine.dir)
            if current != identity:
                raise RuntimeError('running process or artifact identity changed')
            remaining = engine.sh(['ps', '--no-trunc', '--format', '{{json .}}']).stdout
            (directory / 'containers-after.jsonl').write_text(remaining)
            if remaining.strip():
                raise RuntimeError('unexpected active containers after owned cleanup')
            summary['growth'] = resource_cycles.cycle_growth(initial | {'allocated_bytes': initial_allocation['allocated_bytes']}, summary['cycles'])
            summary['coverage_complete'] = (initial['status'] == 'ok' and initial_allocation['status'] == 'ok'
                and all(c['reclaimed']['status'] == 'ok' and c['allocation_reclaimed']['status'] == 'ok' for c in summary['cycles']))
            budgets = resource_cycles.BUDGETS
            summary['minimum_duration_and_cycles_met'] = (
                args.cycles >= budgets['minimum_post_warmup_cycles']
                and args.idle_seconds >= budgets['minimum_idle_seconds']
                and args.reclaim_seconds >= budgets['minimum_reclaim_seconds'])
            print(name, 'functional coverage', summary['coverage_complete'], flush=True)
        except BaseException as exc:
            summary['errors'].append(str(exc))
            raise
        finally:
            host_snapshot(directory, 'after')
            try:
                engine.stop()
            finally:
                save(directory / 'summary.json', summary)
    if set(engines) == {'ctrs', 'orbstack'}:
        reports = {name: json.loads((root / name / 'summary.json').read_text()) for name in engines}
        save(root / 'budget-diagnostic.json', resource_cycles.compare_runs(reports['orbstack'], reports['ctrs']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
