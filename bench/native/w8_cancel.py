"""Interrupt one owned W8 pull after partial blob delivery and verify retry."""
import json
from pathlib import Path
import secrets
import signal
import subprocess
import time

import ci_jobs
from diagnostics import registry_variant_pilot as pilot, w8_under_pull
import registry_portfolio
import registry_variant
import runner


REPOSITORY = 'np-v5/marked'
FIXTURE_VERSION = 'w8-cancel-v1'


def cancel_pull(engine, ref, portfolio, pause, layer, directory):
    with (directory / 'cancel.stdout').open('wb') as out, (directory / 'cancel.stderr').open('wb') as err:
        process = subprocess.Popen([runner.DOCKER, 'pull', ref], env=engine.env(),
                                   stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        try:
            deadline = time.monotonic() + 30
            while not pause.started.wait(.1):
                if process.poll() is not None:
                    raise ValueError('pull exited without delivering the partial blob')
                if time.monotonic() >= deadline:
                    raise TimeoutError('pull did not request the selected fixture blob')
            if process.poll() is not None or pause.finished.is_set():
                raise ValueError('partial delivery ended before the planned interruption')
            cancelled = time.monotonic()
            process.send_signal(signal.SIGINT)
            if process.wait(timeout=pause.timeout) == 0:
                raise ValueError('interrupt returned a successful pull')
            if (not pause.finished.wait(pause.timeout) or pause.disconnected_at is None
                    or pause.disconnected_at < cancelled):
                raise ValueError('registry did not observe the transfer close after interruption')
            matching = [event for event in portfolio.transfers if event['digest'] == layer['digest']
                        and event['repository'] == pause.key[0] and event['method'] == 'GET']
            if (sum(0 < event['bytes'] < layer['size'] for event in matching) != 1
                    or any(event['complete'] for event in matching)):
                raise ValueError('registry did not retain exact partial-transfer evidence')
            return {'exit': process.returncode, 'signal_sent_monotonic': cancelled,
                    'peer_disconnected_monotonic': pause.disconnected_at, 'transfers': matching}
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


def retained(engine, pins, path):
    refs = [w8_under_pull.baseline_image_reference(engine.name, pin)[1] for pin in pins.values()]
    observed = json.loads(engine.sh(['image', 'inspect', *refs]).stdout)
    pilot.save(path, observed)
    w8_under_pull.require_baseline_images(engine.name, pins, observed)


def verify_retry(engine, ref, image, receipt, run):
    observed = json.loads(engine.sh(['image', 'inspect', ref]).stdout)
    w8_under_pull.require_baseline_images(engine.name, {REPOSITORY: image}, observed)
    markers = {item['digest']: item for item in receipt['layers']}
    selected = [markers[layer['digest']] for layer in image['layers'] if layer['digest'] in markers]
    container = runner.project_name(run, engine.name, 'retry')
    try:
        result = engine.sh(['run', '--rm', '--pull=never', '--name', container,
                            '--label', 'dev.ctrs.campaign.run=' + run, '--entrypoint', 'cat', ref,
                            *['/' + item['marker'] for item in selected]], timeout=90)
        expected = ''.join(receipt['seed_sha256'] + '\n' + item['source_diff_id'] + '\n' for item in selected)
        if result.stdout != expected:
            raise ValueError('retry marker contents differ')
    finally:
        ci_jobs.cleanup(engine, container, run)


def remove_owned_image(engine, ref, image):
    inspected = engine.sh(['image', 'inspect', ref], check=False)
    if inspected.returncode:
        pilot.require_missing_image(inspected)
        return
    w8_under_pull.require_baseline_images(engine.name, {REPOSITORY: image}, json.loads(inspected.stdout))
    engine.sh(['image', 'rm', '--no-prune', ref])
    pilot.require_missing_image(engine.sh(['image', 'inspect', ref], check=False))


def run_cancel(args):
    contract = json.loads((runner.FIXTURES / 'w8-v5/portfolio.json').read_text())
    target = {**contract, 'images': {REPOSITORY: contract['images'][REPOSITORY]}}
    run = 'w8-cancel-' + secrets.token_hex(6)
    ctx = runner.RunContext(run)
    directory = ctx.results_dir
    layout = directory / 'variant'
    seed = secrets.token_bytes(32)
    receipt = registry_variant.prepare_variant(args.layout, target, layout, seed,
                                               retain_other_layers=args.content == 'retained')
    image = receipt['images'][REPOSITORY]
    changed = {item['digest'] for item in receipt['layers']}
    layer = max((item for item in image['layers'] if item['digest'] in changed), key=lambda item: item['size'])
    cancellation = registry_portfolio.prepare_layout(layout, {REPOSITORY: image['reference']})
    retry = registry_portfolio.prepare_layout(layout, {REPOSITORY: image['reference']})
    pause = registry_portfolio.TransferPause(REPOSITORY, layer['digest'])
    engine = runner.Engine(args.engine, run)
    result = {'fixture_version': FIXTURE_VERSION, 'state': args.content, 'engine': args.engine, 'target_layer': layer,
              'measurement_valid': False, 'correctness': False, 'errors': []}
    refs = []
    print(f'results: {directory}', flush=True)
    try:
        engine.ensure_up()
        retained(engine, contract['images'], directory / 'retained-before.json')
        pilot.require_variant_absent(engine, image, directory / 'candidate-before.json')
        with registry_portfolio.running_registry(cancellation, pause=pause) as cancel_server, \
                registry_portfolio.running_registry(retry) as retry_server:
            cancel_ref = f'127.0.0.1:{cancel_server.server_port}/{REPOSITORY}@{image["manifest"]}'
            retry_ref = f'127.0.0.1:{retry_server.server_port}/{REPOSITORY}@{image["manifest"]}'
            pilot.require_missing_image(engine.sh(['image', 'inspect', cancel_ref], check=False))
            refs.append(cancel_ref)
            result['cancellation'] = cancel_pull(engine, cancel_ref, cancellation, pause, layer, directory)
            pilot.require_missing_image(engine.sh(['image', 'inspect', cancel_ref], check=False))
            pilot.require_variant_absent(engine, image, directory / 'candidate-after-cancel.json')
            retained(engine, contract['images'], directory / 'retained-after-cancel.json')
            pilot.require_missing_image(engine.sh(['image', 'inspect', retry_ref], check=False))
            refs.append(retry_ref)
            engine.sh(['pull', retry_ref], timeout=240)
            pilot.require_layers_transferred([layer], retry.transfers)
            verify_retry(engine, retry_ref, image, receipt, run)
        result['correctness'] = True
    except Exception as exc:
        result['errors'].append(str(exc))
    finally:
        for ref in refs:
            try:
                remove_owned_image(engine, ref, image)
            except Exception as exc:
                result['errors'].append(f'cleanup {ref}: {exc}')
        if refs:
            try:
                retained(engine, contract['images'], directory / 'retained-after-cleanup.json')
            except Exception as exc:
                result['errors'].append(f'cleanup: {exc}')
        try:
            engine.stop()
        except Exception as exc:
            result['errors'].append(f'engine stop: {exc}')
        result['correctness'] = result['correctness'] and not result['errors']
        result['cancel_transfers'] = cancellation.transfers
        result['retry_transfers'] = retry.transfers
        pilot.save(directory / 'result.json', result)
    return int(not result['correctness'])
