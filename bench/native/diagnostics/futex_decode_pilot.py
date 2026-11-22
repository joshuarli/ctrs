"""Validate futex argument/return decoding against identical fixed C calls."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ci_jobs
import counter_specs
import diagnostic_signals
import ownership
import runner
from syscall_pilot import frame, save, TOOLS_SHA, PIN

BINARY_SHA = '42d52c709e8268620cfcb27bd0e890db3b9a81a8bf9506844c9343b94678992a'
SOURCE_SHA = '1992dab6655a851ba4a8f6a7a312558beda9b9c478f869655b08fd4f5155da8c'
HELPER = Path(__file__).with_name('w2_counter_guest.py')
SOURCE = Path(__file__).with_name('futex_calls.c')
SELECTORS = counter_specs.FUTEX_SELECTORS


def trial(engine, ref, archive, binary, root, count):
    directory = root / engine.name; directory.mkdir()
    name = root.name + '-' + engine.name
    tag = 'np' + secrets.token_hex(6)
    event = counter_specs.futex_events(tag)
    definitions = counter_specs.futex_probe_definitions(tag)
    created = []
    phase = profiler = phase_log = profiler_log = None
    result = {'errors': [], 'cleanup_errors': [], 'qualification_eligible': False}
    def sh(args, *, timeout=15):
        cp = engine.sh(['exec', '--privileged', name, *args], check=False, timeout=timeout)
        if cp.returncode:
            raise RuntimeError(cp.stdout + cp.stderr)
        return cp
    def helper(action, *extra):
        return sh(['python', '/diagnostics/w2_counter_guest.py', action, tag, *extra])
    def probe_command(command):
        return sh(['python', '-c', "import os,sys;fd=os.open('/sys/kernel/tracing/kprobe_events',os.O_WRONLY);os.write(fd,(sys.argv[1]+chr(10)).encode());os.close(fd)", command])
    def probes():
        return sh(['python', '-c', "from pathlib import Path;print(Path('/sys/kernel/tracing/kprobe_events').read_text())"]).stdout.splitlines()
    def remove_probe(definition):
        key = definition.split(' ', 1)[0]
        matches = [line for line in probes() if line.split(' ', 1)[0] == key]
        if matches and matches != [definition]:
            raise ValueError('probe ownership changed; refuse deletion')
        if matches:
            probe_command('-:' + key.split(':', 1)[1])
    try:
        engine.ensure_up()
        info = json.loads(engine.sh(['image', 'inspect', ref]).stdout)[0]
        if info['Architecture'] != 'arm64' or ref not in info['RepoDigests'] or info['RootFS']['Layers'] != PIN['images']['np-v6/api']['diff_ids']:
            raise ValueError('C proof runtime image differs from pin')
        engine.sh(['run', '-d', '--pull=never', '--name', name, '--label', 'dev.ctrs.campaign.run=' + root.name,
            '--privileged', '--network', 'none', '-v', str(HELPER.resolve()) + ':/diagnostics/w2_counter_guest.py:ro',
            '-v', str(Path(counter_specs.__file__).resolve()) + ':/diagnostics/counter_specs.py:ro',
            '-v', str(binary) + ':/proof:ro', '--entrypoint', '/proof', ref, tag, str(count)])
        executable = sh(['python', '-c', "import pathlib,hashlib;print(hashlib.sha256(pathlib.Path('/proc/1/exe').read_bytes()).hexdigest())"]).stdout.strip()
        if executable != BINARY_SHA:
            raise ValueError('actual running C executable differs from pin')
        save(directory / 'running-engine.json', ownership.discover(engine.name, Path(engine.socket.removeprefix('unix://')), engine.dir))
        engine.sh(['cp', str(archive), name + ':/tmp/np-tools.tgz'])
        helper('prepare'); sh(['mount', '-t', 'tracefs', 'tracefs', '/sys/kernel/tracing'])
        if any(':' + tag + '/' in line for line in probes()):
            raise ValueError('owned probe group collision')
        for definition in definitions:
            probe_command(definition); created.append(definition)
        if any(definition not in probes() for definition in definitions):
            raise ValueError('registered probe definitions differ')
        save(directory / 'probes.json', definitions)
        for kind in event:
            (directory / (kind + '-format.txt')).write_text(sh(['cat', f'/sys/kernel/tracing/events/{tag}/{event[kind]}/format']).stdout)
        command = ['/tmp/np-tools/usr/bin/perf', 'stat', '-j', '--per-thread', '--no-inherit', '-t', '1', '--delay=-1',
                   '--control', 'fifo:/tmp/np-count/control,/tmp/np-count/ack', '-o', '/tmp/np-count/stat.json']
        for kind, label, expression in SELECTORS:
            command += ['-e', tag + ':' + event[kind]]
            if expression:
                command += ['--filter', expression]
        save(directory / 'selectors.json', [{'event': tag + ':' + event[kind], 'label': label, 'filter': expression} for kind, label, expression in SELECTORS])
        profiler_log = (directory / 'profiler.log').open('wb')
        profiler = subprocess.Popen([runner.DOCKER, 'exec', '--privileged', name, 'python', '/diagnostics/w2_counter_guest.py',
            'launch', tag, *command], env=engine.env(), stdout=profiler_log, stderr=subprocess.STDOUT)
        phase_log = (directory / 'phase.stderr').open('wb')
        phase = subprocess.Popen([runner.DOCKER, 'exec', '-i', '--privileged', name, 'python', '/diagnostics/w2_counter_guest.py',
            'phase', tag, 'on'], env=engine.env(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=phase_log, text=True)
        before = frame(phase, 'ready'); save(directory / 'phase-before.json', before)
        sh(['python', '-c', "from pathlib import Path;Path('/tmp/np-futex-go').write_text('G')"])
        wait = "import time,pathlib;p=pathlib.Path('/tmp/np-futex-result.json');end=time.monotonic()+10\nwhile not p.exists() and time.monotonic()<end:time.sleep(.01)\nassert p.exists();print(p.read_text())"
        proof = json.loads(sh(['python', '-c', wait]).stdout)
        if proof != {'calls': 3*count, 'wait': 2*count, 'wake': count, 'eagain': count, 'timeout': count, 'zero': count, 'cpu': 0}:
            raise ValueError('C fixed primitive results differ')
        phase.stdin.write('STOP\n'); phase.stdin.flush(); phase.stdin.close()
        after = frame(phase, 'done'); save(directory / 'phase-after.json', after)
        if phase.wait(timeout=15):
            raise RuntimeError('phase helper failed')
        helper('stop'); code = profiler.wait(timeout=15)
        if code not in (0, 130):
            raise RuntimeError('profiler failed')
        engine.sh(['cp', name + ':/tmp/np-count/stat.json', str(directory / 'stat.json')])
        rows = [json.loads(line) for line in (directory / 'stat.json').read_text().splitlines() if line.strip()]
        if len(rows) != len(SELECTORS) or [row['event'] for row in rows] != [tag + ':' + event[kind] for kind, _, _ in SELECTORS]:
            raise ValueError('pinned perf selector block order/coverage differs')
        if any(float(row['pcnt-running']) != 100 or float(row['event-runtime']) <= 0 or row['thread'] != tag + '-1' for row in rows):
            raise ValueError('thread/event counter coverage incomplete')
        actual = {label: float(row['counter-value']) for (_, label, _), row in zip(SELECTORS, rows)}
        expected = dict(all=3*count, wait=2*count, wake=count, wait_bitset=0, returns=3*count,
                        eagain=count, timeout=count, zero=count, positive=0)
        if actual != expected:
            raise ValueError('argument/return decode counts differ: ' + repr(actual))
        profile = sh(['cat', '/sys/kernel/tracing/kprobe_profile']).stdout.splitlines()
        owned = [line.split() for line in profile if line.split()[0] in event.values()]
        save(directory / 'probe-profile.json', owned)
        if len(owned) != 2 or any(int(line[-1]) != 0 for line in owned):
            raise ValueError('probe miss coverage invalid')
        for definition in created.copy():
            remove_probe(definition)
            created.remove(definition)
        if any(':' + tag + '/' in line for line in probes()):
            raise ValueError('owned probe remains')
        result['owned_probes_absent'] = True
        stopped = engine.sh(['exec', '--privileged', name, 'python', '-c',
            "from pathlib import Path;Path('/tmp/np-futex-go').write_text('S')"], check=False, timeout=15)
        save(directory / 'stop-writer.json', {'exit': stopped.returncode, 'stdout': stopped.stdout, 'stderr': stopped.stderr,
             'expected_137': 'PID1 may exit before the writer exec; the C process must still exit 0'})
        if stopped.returncode not in (0, 137):
            raise RuntimeError('C stop writer failed: ' + repr(stopped.returncode))
        exited = engine.sh(['wait', name], timeout=15).stdout.strip()
        if exited != '0':
            raise RuntimeError('C primitive process exit failed: ' + exited)
        result.update(correctness=True, proof=proof, counts=actual, exit=0, profiler_exit=code,
                      purpose='fixed-count argument/return and selector-order conformance; no latency/CPU verdict')
    except BaseException as exc:
        result['errors'].append(repr(exc)); result['correctness'] = False
        raise
    finally:
        for proc, label in ((phase, 'phase'), (profiler, 'profiler')):
            try:
                if proc and proc.poll() is None:
                    if label == 'profiler':
                        helper('stop')
                    elif proc.stdin and not proc.stdin.closed:
                        proc.stdin.close()
                    proc.wait(timeout=15)
            except Exception as exc:
                result['cleanup_errors'].append(label + ': ' + repr(exc))
                if proc and proc.poll() is None:
                    proc.kill(); proc.wait(timeout=5)
        for definition in created:
            try:
                remove_probe(definition)
            except Exception as exc:
                result['cleanup_errors'].append('probe: ' + repr(exc))
        try:
            ci_jobs.cleanup(engine, name, root.name)
        finally:
            engine.stop()
            for log in (profiler_log, phase_log):
                if log:
                    log.close()
            if result['cleanup_errors']:
                result['correctness'] = False
            save(directory / 'result.json', result)
    if result['cleanup_errors']:
        raise RuntimeError('decoder cleanup failed')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proof-binary', type=Path, required=True)
    parser.add_argument('--tools-archive', type=Path, required=True)
    parser.add_argument('--image-refs', type=Path, required=True)
    parser.add_argument('--ctrs-binary', type=Path, required=True)
    args = parser.parse_args()
    binary, archive = args.proof_binary.resolve(), args.tools_archive.resolve()
    if sys.platform != 'darwin' or os.uname().machine != 'arm64':
        parser.error('native ARM64 macOS only')
    if runner.sha256_file(binary) != BINARY_SHA or runner.sha256_file(SOURCE) != SOURCE_SHA or runner.sha256_file(archive) != TOOLS_SHA:
        parser.error('C/tool input differs from validated pin')
    ref = json.loads(args.image_refs.read_text())['api']
    if '@' not in ref or ref.rsplit('@', 1)[1] != PIN['images']['np-v6/api']['manifest']:
        parser.error('runtime image differs from pin')
    diagnostic_signals.install_cleanup_signals()
    runner.DOCKER = runner.find_docker(); runner.CTRS_BIN = args.ctrs_binary.resolve()
    run = 'futex-decode-' + time.strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(2)
    root = runner.RESULTS / run; root.mkdir()
    for path in (Path(__file__), SOURCE, HELPER, Path(counter_specs.__file__)):
        (root / path.name).write_bytes(path.read_bytes())
    save(root / 'plan.json', {'fixture_version': 'futex-decoder-v1', 'calls_per_kind': 100,
         'source_sha256': SOURCE_SHA, 'binary_sha256': BINARY_SHA, 'tools_sha256': TOOLS_SHA,
         'runtime_ref': ref, 'qualification_eligible': False,
         'method': 'identical ARM64 static C binary; CPU0 affinity; explicit FIFO work boundaries; count correctness only',
         'return_probe_maxactive': counter_specs.KRETPROBE_MAXACTIVE, 'require_missed_probes': 0})
    print('RESULTS', root, flush=True)
    for name in ('ctrs', 'orbstack'):
        trial(runner.Engine(name, run), ref, archive, binary, root, 100)
    print('PASS', root, flush=True)


if __name__ == '__main__':
    main()
