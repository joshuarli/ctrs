import subprocess
import time
import uuid
from pathlib import Path
from fixtures.w14 import lifecycle_tool as tool

PORT_WAIT_LIMIT_SECONDS = 45


def ephemeral_ports_free():
    def sysctl(name):
        return int(subprocess.run(['sysctl', '-n', name], capture_output=True, text=True, check=True).stdout)
    size = sysctl('net.inet.ip.portrange.last') - sysctl('net.inet.ip.portrange.first') + 1
    return size - sysctl('net.inet.tcp.pcbcount')


def wait_for_client_ports(needed, free=ephemeral_ports_free, sleep=time.sleep, clock=time.monotonic):
    start = clock()
    while free() < needed:
        if clock() - start >= PORT_WAIT_LIMIT_SECONDS:
            break
        sleep(1)
    return clock() - start


SOURCE = (Path(__file__).parent / 'fixtures/w14/lifecycle_tool.py').read_text()


def trial_w14(ctx, engine, state, mode='fresh', clients=32, operations=100,
              chunks=50, interval=0.02, idle_seconds=30, timeout=5):
    import runner
    if mode not in ('fresh', 'persistent', 'streaming', 'cancel', 'idle-resume', 'reconnect'):
        raise ValueError('unknown lifecycle mode')
    if clients < 1 or operations < 1 or chunks < 2 or interval <= 0 or idle_seconds < 0 or timeout <= 0:
        raise ValueError('invalid lifecycle parameters')
    directory = ctx.trial_dir(engine.name, 'W14', state)
    rec = ctx.new_record(engine, 'W14', state, directory)
    rec['metrics'].update(fixture_version='w14-v3', mode=mode, clients=[], successes=0,
                          errors={}, server_open_connections=None, leaked_sessions=None)
    name = 'w14-' + uuid.uuid4().hex[:12]
    label = 'dev.ctrs.campaign.run=' + ctx.run_id
    owned = False
    sampler = trace = None
    try:
        engine.ensure_up()
        image, identity = runner.pinned_api_image(engine)
        rec.setdefault('inputs', {}).update(image_id=image, **identity)
        rec['paired_inputs'] = {**identity, 'fixture_sha256': runner.sha256_file(Path(__file__))}
        port = runner.free_port()
        engine.sh(['run', '-d', '--pull=never', '--name', name, '--label', label,
                   '-p', f'127.0.0.1:{port}:{port}', '--entrypoint', 'python3', image,
                   '-c', SOURCE, 'server', '0.0.0.0', str(port)], timeout=120)
        owned = True
        deadline = time.monotonic() + 30
        while True:
            try:
                tool.count('127.0.0.1', port)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
        if mode == 'fresh':
            rec['metrics']['client_port_wait_seconds'] = wait_for_client_ports(2 * clients * operations)
        sampler, trace = runner.start_sampler(engine, directory)
        result = tool.run('127.0.0.1', port, mode, clients, operations, chunks, interval,
                          idle_seconds, timeout, restart=lambda: engine.sh(['restart', name], timeout=120),
                          phase=lambda: runner.resource_phase(engine, rec, 'lifecycle'))
        rec['metrics'].update(result)
        rec['correctness']['checks'].update(results_exact=result['successes'] == result['expected_successes'] and not any(result['errors'].values()),
                                            no_leaked_sessions=result['leaked_sessions'] == 0)
        if not result['ok']:
            rec['correctness']['ok'] = False
            rec['validation_errors'].append('lifecycle results or cleanup failed')
    except Exception as exc:
        rec['correctness']['ok'] = False
        rec['validation_errors'].append(f'{type(exc).__name__}: {exc}')
    finally:
        if sampler:
            runner.stop_sampler(sampler)
            rec['resources'].update(runner.summarize_trace(trace))
        if owned:
            info = engine.sh(['inspect', name, '--format', '{{index .Config.Labels "dev.ctrs.campaign.run"}}'], check=False)
            if info.returncode or info.stdout.strip() != ctx.run_id:
                rec['correctness']['ok'] = False
                rec['validation_errors'].append('ownership verification failed: ' + name)
            elif engine.sh(['rm', '-f', name], check=False).returncode:
                rec['correctness']['ok'] = False
                rec['validation_errors'].append('cleanup failed: ' + name)
            else:
                rec['correctness']['checks']['owned_cleanup'] = True
    return rec
