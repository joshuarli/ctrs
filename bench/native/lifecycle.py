import time
import uuid
from pathlib import Path
from fixtures.w14 import lifecycle_tool as tool

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
    rec['metrics'].update(fixture_version='w14-v1', mode=mode, clients=[], successes=0,
                          errors={}, server_open_connections=None, leaked_sessions=None)
    name = 'w14-' + uuid.uuid4().hex[:12]
    label = 'dev.ctrs.campaign.run=' + ctx.run_id
    owned = False
    sampler = trace = None
    try:
        engine.ensure_up()
        image = getattr(engine, 'w14_image_id', None)
        if not image:
            images = engine.sh(['images', '--format', '{{.Repository}} {{.ID}}']).stdout.splitlines()
            matches = [line.split()[1] for line in images if len(line.split()) >= 2 and line.split()[0].endswith('np-v5/api')]
            if not matches:
                raise ValueError('pinned API image not found')
            image = matches[0]
        rec.setdefault('inputs', {})['image_id'] = image
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
