import json
import statistics
from contextlib import nullcontext
from pathlib import Path
import subprocess
import sys
import time
import uuid

TOOL = Path(__file__).parent / 'fixtures/w13/transfer_tool.py'
SOURCE = TOOL.read_text()
FIXTURE_VERSION = 'w13-v3'
DEFAULT_SIZE = 1024 ** 3


def tool_limited(goodput, host_capacity, container_capacity, path='published-port'):
    """Whether the transfer tool, not the engine, may bound the result: the
    tool's loopback capacity at every end the path uses, halved for headroom."""
    capacity = container_capacity if path == 'container-to-container' else min(host_capacity, container_capacity)
    return goodput > 0.5 * capacity



def transfer_result(data, received, direction, streams, part, digest):
    checks = received if direction == 'upload' else data['streams']
    errors = [x.get('error') or x.get('ack_error') for x in data['streams'] + received
              if x.get('error') or x.get('ack_error')]
    identities = len(checks) == streams and sorted(x['id'] for x in checks) == [str(i) for i in range(streams)]
    if not identities:
        errors.append('stream identities mismatch')
    ok = identities and not errors and all(x.get('bytes') == part and x.get('sha256') == digest for x in checks)
    if not ok and not errors:
        errors.append('byte count or hash mismatch')
    data['receivers'] = checks
    data['partial_bytes'] = sum(x.get('bytes') or 0 for x in checks if x.get('bytes') is not None)
    data['partial_bytes_complete'] = len(checks) == streams and all(x.get('bytes') is not None for x in checks)
    data['verified_bytes'] = sum(x['bytes'] for x in checks if x.get('error') is None
                                 and x.get('bytes') == part and x.get('sha256') == digest)
    data['ok'] = ok
    data['errors'] = errors
    data['goodput_bytes_per_second'] = data['verified_bytes'] / data['seconds'] if ok else None
    return data


def record_attempt(rec, attempt):
    rec['metrics']['attempts'].append(attempt)
    if not attempt['ok']:
        rec['correctness']['ok'] = False
        rec['validation_errors'].extend(attempt.get('errors', ['transfer integrity failure']))

def trial_w13(ctx, engine, state, path='published-port', direction='upload', streams=1,
              size_bytes=DEFAULT_SIZE, repeats=3, artifact_bytes=None):
    import runner
    if path not in ('published-port', 'container-to-container', 'container-to-mac'):
        raise ValueError('unknown transfer path')
    if direction not in ('upload', 'download') or streams not in (1, 4) or size_bytes <= 0 or size_bytes % streams or repeats < 1:
        raise ValueError('invalid transfer parameters')
    directory = ctx.trial_dir(engine.name, 'W13', state)
    rec = ctx.new_record(engine, 'W13', state, directory)
    rec['workload_params']['fixture_version'] = FIXTURE_VERSION
    token = 'w13-' + uuid.uuid4().hex[:12]
    label = 'dev.ctrs.campaign.run=' + ctx.run_id
    resources = []
    sampler = trace = None
    rec['metrics'].update(fixture_version=FIXTURE_VERSION, path=path, direction=direction,
                          streams=streams, size_bytes=size_bytes, repeats=repeats,
                          controlled_egress='unsupported: no owned external endpoint', attempts=[])
    try:
        engine.ensure_up()
        image, identity = runner.pinned_api_image(engine)
        rec.setdefault('inputs', {}).update(image_id=image, **identity)
        network = token + '-net'
        engine.sh(['network', 'create', '--label', label, network])
        resources.append(('network', network))
        names = [token + '-server', token + '-client']
        port = runner.free_port()
        for index, name in enumerate(names):
            cmd = ['run', '-d', '--pull=never', '--name', name, '--label', label,
                   '--network', network, '--tmpfs', '/w13:rw,size=2g']
            if index == 0 and path == 'published-port':
                cmd += ['-p', f'127.0.0.1:{port}:{port}']
            cmd += ['--entrypoint', 'python3', image, '-c', 'import time; time.sleep(86400)']
            engine.sh(cmd, timeout=120)
            resources.append(('container', name))
        server, client = names
        host_file = directory / 'artifact.bin'
        guest_file = '/w13/artifact.bin'
        def command(where, args):
            if where == 'host':
                return [sys.executable, str(TOOL), *map(str, args)]
            return [runner.DOCKER, 'exec', where, 'python3', '-c', SOURCE, *map(str, args)]
        def invoke(where, args, timeout=300):
            p = subprocess.run(command(where, args), env=engine.env(), capture_output=True, text=True, timeout=timeout)
            if p.returncode:
                raise RuntimeError(f'{where} {args[0]} exit {p.returncode}: {p.stderr}')
            return p.stdout.strip()
        part = size_bytes // streams
        hashes = {}
        for location in ('host', server, client):
            filename = str(host_file) if location == 'host' else guest_file
            hashes[location] = invoke(location, ['prepare', filename, min(part, artifact_bytes or part)])
        if len(set(hashes.values())) != 1:
            raise ValueError('prepared artifact hashes differ')
        digest = hashes['host']
        rec['inputs'].update(seed='w13-v1-seed-2026', sha256_per_stream=digest,
                             sender_storage='host local disk or container tmpfs', image_id=image)
        rec['paired_inputs'] = {**identity, 'sha256_per_stream': digest, 'tool_sha256': runner.sha256_file(TOOL)}
        sampler, trace = runner.start_sampler(engine, directory)
        def transfer(server_where, client_where, host, bind, run_direction, phase=nullcontext):
            server_file = str(host_file) if server_where == 'host' else guest_file
            client_file = str(host_file) if client_where == 'host' else guest_file
            result = str(directory / (uuid.uuid4().hex + '.json')) if server_where == 'host' else '/w13/' + uuid.uuid4().hex + '.json'
            args = ['server', bind, port, run_direction, streams, server_file, part, digest, result]
            proc = subprocess.Popen(command(server_where, args), env=engine.env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                time.sleep(1)
                if proc.poll() is not None:
                    raise RuntimeError('server exited: ' + proc.communicate()[1])
                with phase():
                    observer = getattr(ctx, 'overlap_transfer_observer', None) if phase is not nullcontext else None
                    if observer:
                        observer('start', time.monotonic(), None)
                    data = json.loads(invoke(client_where, ['client', host, port, run_direction, streams, client_file, part, digest], timeout=600))
                    if observer:
                        observer('end', time.monotonic(), data)
                    out, err = proc.communicate(timeout=120)
                if proc.returncode:
                    raise RuntimeError(f'server exit {proc.returncode}: {err}')
                received = json.loads(Path(result).read_text() if server_where == 'host' else engine.sh(['exec', server_where, 'cat', result]).stdout)
                if observer:
                    observer('receipts', time.monotonic(), received)
                return transfer_result(data, received, run_direction, streams, part, digest)
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try: proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill(); proc.wait()
        published_port = port
        port = runner.free_port()
        host_control = transfer('host', 'host', '127.0.0.1', '127.0.0.1', direction)
        port = runner.free_port()
        guest_control = transfer(server, server, '127.0.0.1', '127.0.0.1', direction)
        port = published_port if path == 'published-port' else runner.free_port()
        rec['metrics']['capacity_controls'] = {'host': host_control, 'container': guest_control}
        if not host_control['ok'] or not guest_control['ok']:
            raise ValueError('capacity control failed')
        rec['correctness']['checks']['capacity_controls_exact'] = True
        if path == 'published-port':
            server_where, client_where, host, bind = server, 'host', '127.0.0.1', '0.0.0.0'
        elif path == 'container-to-container':
            server_where, client_where, host, bind = server, client, server, '0.0.0.0'
        else:
            server_where, client_where, host, bind = 'host', client, 'host.docker.internal', '127.0.0.1'
        rec['metrics']['server_bind_address'] = bind
        relay_group = {'published-port': 'published', 'container-to-mac': 'host_bound'}.get(path)
        for i in range(repeats):
            relays_before = runner.relay_counts(engine) if relay_group else None
            started = time.monotonic()
            try:
                attempt = transfer(server_where, client_where, host, bind, direction,
                                   lambda: runner.resource_phase(engine, rec, f'transfer_{i + 1}'))
            except Exception as exc:
                attempt = {'ok': False, 'seconds': time.monotonic() - started,
                           'verified_bytes': 0, 'partial_bytes': None,
                           'partial_bytes_complete': False, 'receivers': [],
                           'errors': [f'{type(exc).__name__}: {exc}'],
                           'goodput_bytes_per_second': None}
            if relay_group:
                attempt['transport'] = runner.relay_delta(relays_before, runner.relay_counts(engine), relay_group)
            cpu = rec['resources'].get('phases', {}).get(f'transfer_{i + 1}', {}).get('cpu_seconds')
            attempt['engine_cpu_seconds_per_verified_gib'] = cpu / (attempt['verified_bytes'] / 1024**3) if cpu is not None and attempt['ok'] else None
            attempt['tool_limited'] = tool_limited(attempt['goodput_bytes_per_second'], host_control['goodput_bytes_per_second'], guest_control['goodput_bytes_per_second'], path) if attempt['ok'] else None
            record_attempt(rec, attempt)
        attempts = rec['metrics']['attempts']
        rec['correctness']['checks']['transfers_byte_exact'] = all(x['ok'] for x in attempts)
        if all(x['ok'] for x in attempts):
            rec['metrics'].update(
                goodput_bytes_per_second=statistics.median(x['goodput_bytes_per_second'] for x in attempts),
                completion_seconds=statistics.median(x['seconds'] for x in attempts),
                tool_limited=any(x['tool_limited'] for x in attempts))
            transports = [x.get('transport') for x in attempts]
            if transports and all(t is not None for t in transports):
                rec['metrics']['transport'] = {k: sum(t.get(k, 0) for t in transports) for k in transports[0]}
            cpu = [x['engine_cpu_seconds_per_verified_gib'] for x in attempts]
            if all(value is not None for value in cpu):
                rec['metrics']['cpu_seconds_per_verified_gib'] = statistics.median(cpu)
        return rec
    except Exception as exc:
        rec['correctness']['ok'] = False
        rec['validation_errors'].append(str(exc))
        return rec
    finally:
        if sampler:
            runner.stop_sampler(sampler)
            rec['resources'].update(runner.summarize_trace(trace))
        for kind, name in reversed(resources):
            field = '{{index .Config.Labels "dev.ctrs.campaign.run"}}' if kind == 'container' else '{{index .Labels "dev.ctrs.campaign.run"}}'
            args = ['inspect', name, '--format', field] if kind == 'container' else ['network', 'inspect', name, '--format', field]
            info = engine.sh(args, check=False)
            if info.returncode or info.stdout.strip() != ctx.run_id:
                rec['correctness']['ok'] = False
                rec['validation_errors'].append('ownership verification failed: ' + name)
            else:
                args = ['rm', '-f', name] if kind == 'container' else ['network', 'rm', name]
                removed = engine.sh(args, check=False)
                if removed.returncode:
                    rec['correctness']['ok'] = False
                    rec['validation_errors'].append('cleanup failed: ' + name)
        rec['correctness']['checks']['owned_cleanup'] = not any(
            error.startswith(('ownership verification failed', 'cleanup failed')) for error in rec['validation_errors'])
        (directory / 'artifact.bin').unlink(missing_ok=True)
