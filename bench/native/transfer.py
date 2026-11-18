import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

TOOL = Path(__file__).parent / 'fixtures/w13/transfer_tool.py'
SOURCE = TOOL.read_text()
DEFAULT_SIZE = 1024 ** 3


def tool_limited(goodput, host_capacity, container_capacity):
    return goodput > 0.5 * min(host_capacity, container_capacity)


def trial_w13(ctx, engine, state, path='published-port', direction='upload', streams=1,
              size_bytes=DEFAULT_SIZE, repeats=3):
    import runner
    if path not in ('published-port', 'container-to-container', 'container-to-mac'):
        raise ValueError('unknown transfer path')
    if direction not in ('upload', 'download') or streams not in (1, 4) or size_bytes <= 0 or size_bytes % streams or repeats < 1:
        raise ValueError('invalid transfer parameters')
    directory = ctx.trial_dir(engine.name, 'W13', state)
    rec = ctx.new_record(engine, 'W13', state, directory)
    token = 'w13-' + uuid.uuid4().hex[:12]
    label = 'dev.ctrs.campaign.run=' + ctx.run_id
    resources = []
    sampler = trace = None
    image = getattr(engine, 'w13_image_id', None)
    rec['metrics'].update(fixture_version='w13-v1', path=path, direction=direction,
                          streams=streams, size_bytes=size_bytes, repeats=repeats,
                          controlled_egress='unsupported: no owned external endpoint', attempts=[])
    try:
        engine.ensure_up()
        if not image:
            images = engine.sh(['images', '--format', '{{.Repository}} {{.ID}}']).stdout.splitlines()
            matches = [line.split()[1] for line in images if line.split() and line.split()[0].endswith('np-v5/api')]
            if not matches:
                raise ValueError('pinned API image not found')
            image = matches[0]
        rec.setdefault('inputs', {})['image_id'] = image
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
            hashes[location] = invoke(location, ['prepare', filename, part])
        if len(set(hashes.values())) != 1:
            raise ValueError('prepared artifact hashes differ')
        digest = hashes['host']
        rec['inputs'].update(seed='w13-v1-seed-2026', sha256_per_stream=digest,
                             sender_storage='host local disk or container tmpfs', image_id=image)
        sampler, trace = runner.start_sampler(engine, directory)
        def transfer(server_where, client_where, host, bind, run_direction):
            server_file = str(host_file) if server_where == 'host' else guest_file
            client_file = str(host_file) if client_where == 'host' else guest_file
            result = str(directory / (uuid.uuid4().hex + '.json')) if server_where == 'host' else '/w13/' + uuid.uuid4().hex + '.json'
            args = ['server', bind, port, run_direction, streams, server_file, part, digest, result]
            proc = subprocess.Popen(command(server_where, args), env=engine.env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                time.sleep(1)
                if proc.poll() is not None:
                    raise RuntimeError('server exited: ' + proc.communicate()[1])
                data = json.loads(invoke(client_where, ['client', host, port, run_direction, streams, client_file, part, digest], timeout=600))
                out, err = proc.communicate(timeout=120)
                if proc.returncode:
                    raise RuntimeError(f'server exit {proc.returncode}: {err}')
                received = json.loads(Path(result).read_text() if server_where == 'host' else engine.sh(['exec', server_where, 'cat', result]).stdout)
                checks = received if run_direction == 'upload' else data['streams']
                if len(checks) != streams or sorted(x['id'] for x in checks) != [str(i) for i in range(streams)]:
                    raise ValueError('stream identities mismatch')
                data['receivers'] = checks
                data['verified_bytes'] = sum(x['bytes'] for x in checks if not x['error'])
                data['ok'] = all(x['error'] is None and x['bytes'] == part and x['sha256'] == digest for x in checks)
                data['goodput_bytes_per_second'] = data['verified_bytes'] / data['seconds'] if data['ok'] else None
                return data
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
        if path == 'published-port':
            server_where, client_where, host, bind = server, 'host', '127.0.0.1', '0.0.0.0'
        elif path == 'container-to-container':
            server_where, client_where, host, bind = server, client, server, '0.0.0.0'
        else:
            server_where, client_where, host, bind = 'host', client, 'host.docker.internal', '0.0.0.0'
        rec['metrics']['server_bind_address'] = bind
        for i in range(repeats):
            with runner.resource_phase(engine, rec, f'transfer_{i + 1}'):
                attempt = transfer(server_where, client_where, host, bind, direction)
            cpu = rec['resources']['phases'][f'transfer_{i + 1}']['cpu_seconds']
            attempt['engine_cpu_seconds_per_verified_gib'] = cpu / (attempt['verified_bytes'] / 1024**3) if cpu is not None and attempt['ok'] else None
            attempt['tool_limited'] = tool_limited(attempt['goodput_bytes_per_second'], host_control['goodput_bytes_per_second'], guest_control['goodput_bytes_per_second']) if attempt['ok'] else None
            rec['metrics']['attempts'].append(attempt)
            if not attempt['ok']:
                rec['correctness']['ok'] = False
                rec['validation_errors'].append('transfer integrity failure')
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
        if host_file.exists() if 'host_file' in locals() else False:
            host_file.unlink()
