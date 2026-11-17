"""Verify complete derived W8 transfers and exact native application outputs."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ci_jobs
import diagnostic_signals
import registry_portfolio
import runner
from diagnostics.registry_pilot import deploy, save


def require_missing_image(cp):
    if cp.returncode == 0:
        raise ValueError('derived image unexpectedly present before pull')
    if 'no such image:' not in cp.stderr.lower() or cp.stdout.strip() != '[]':
        raise ValueError('cannot establish derived image absence through image API')


def require_layers_transferred(layers, transfers):
    for layer in layers:
        delivered = sum(t['bytes'] for t in transfers if t['digest'] == layer['digest']
                        and t['method'] == 'GET' and t['complete'])
        if delivered < layer['size']:
            raise ValueError('layer not transferred completely: ' + layer['digest'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layout', type=Path, required=True)
    parser.add_argument('--ctrs-binary', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin' or os.uname().machine != 'arm64':
        parser.error('native ARM64 macOS only')
    runner.DOCKER = runner.find_docker()
    runner.CTRS_BIN = args.ctrs_binary.resolve()
    diagnostic_signals.install_cleanup_signals()
    layout = args.layout.resolve()
    receipt = json.loads((layout / 'receipt.json').read_text())
    contract = json.loads((runner.FIXTURES / 'w8-v2/portfolio.json').read_text())
    portfolio = registry_portfolio.prepare_layout(layout, {
        name: image['reference'] for name, image in receipt['images'].items()})
    run = 'w8-unique-' + time.strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(2)
    root = runner.RESULTS / run
    root.mkdir()
    save(root / 'plan.json', {'qualification_eligible': False, 'fixture_version': 'w8-v3',
        'receipt': receipt, 'reason': 'functional full-transfer/marker proof; timing, guest pre-content absence and resources unqualified'})
    (root / 'driver.py').write_bytes(Path(__file__).read_bytes())
    server = registry_portfolio.serve(portfolio, 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05})
    print('RESULTS', root, flush=True)
    try:
        thread.start()
        for name in ('ctrs', 'orbstack'):
            directory = root / name
            directory.mkdir()
            engine = runner.Engine(name, run)
            result = {'correctness': False, 'errors': [], 'pulls': [],
                      'pre_content_state': 'unknown below image API; no cache purge'}
            try:
                engine.ensure_up()
                refs = {}
                engine_transfer_start = len(portfolio.transfers)
                old_refs = ['np-fixture-api:' + runner.API_TAG, 'postgres:17-alpine',
                            'redis:7-alpine', 'np-w5-marked:v2']
                retained_before = json.loads(engine.sh(['image', 'inspect', *old_refs]).stdout)
                save(directory / 'retained-before.json', retained_before)
                for repository, digest in portfolio.manifests.items():
                    short = repository.rsplit('/', 1)[1]
                    image = receipt['images'][repository]
                    ref = f'127.0.0.1:{server.server_port}/{repository}@{digest}'
                    missing = engine.sh(['image', 'inspect', image['config']], check=False)
                    save(directory / (short + '-pre-image.json'), {
                        'exit': missing.returncode, 'stdout': missing.stdout, 'stderr': missing.stderr})
                    require_missing_image(missing)
                    begin = len(portfolio.transfers)
                    cp = engine.sh(['pull', ref], timeout=240, check=False)
                    transfers = portfolio.transfers[begin:]
                    result['pulls'].append({'ref': ref, 'exit': cp.returncode,
                        'stdout': cp.stdout, 'stderr': cp.stderr, 'transfers': transfers})
                    if cp.returncode:
                        raise ValueError('pull failed')
                    require_layers_transferred(image['layers'], portfolio.transfers[engine_transfer_start:])
                    markers = {item['digest']: item for item in receipt['layers']}
                    selected = [markers[layer['digest']] for layer in image['layers']]
                    container = runner.project_name(run, name, 'marker-' + short)
                    try:
                        marker_output = engine.sh(['run', '--rm', '--name', container, '--pull=never',
                            '--label', 'dev.ctrs.campaign.run=' + run, '--entrypoint', 'cat', ref,
                            *['/' + item['marker'] for item in selected]], timeout=90).stdout
                        if marker_output != ''.join(receipt['seed_sha256'] + '\n' +
                                item['source_diff_id'] + '\n' for item in selected):
                            raise ValueError('installed marker contents differ')
                    finally:
                        ci_jobs.cleanup(engine, container, run)
                    refs[short] = ref
                    save(directory / 'result.json', result)
                result['deployment'] = deploy(engine, refs, layout, directory, run, contract)
                retained_after = json.loads(engine.sh(['image', 'inspect', *old_refs]).stdout)
                save(directory / 'retained-after.json', retained_after)
                if [i['Id'] for i in retained_before] != [i['Id'] for i in retained_after]:
                    raise ValueError('retained image identity changed')
                result['correctness'] = True
                print(name, 'PASS full transfers, markers, exact application data, retained images', flush=True)
            except BaseException:
                result['errors'].append(traceback.format_exc())
                raise
            finally:
                try:
                    engine.stop()
                finally:
                    save(directory / 'result.json', result)
    finally:
        if thread.ident is not None:
            server.shutdown()
        server.server_close()
        thread.join(timeout=5) if thread.ident is not None else None
        save(root / 'transfers.json', portfolio.transfers)
        if thread.is_alive():
            raise RuntimeError('registry did not terminate')


if __name__ == '__main__':
    main()
