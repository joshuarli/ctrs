"""Byte identity for the common native W7 HTTPie first-use input."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tarfile
import tempfile
import time

FIXTURE_VERSION = 'w7-httpie-imported-first-use-v1'


def archive_identity(path):
    with path.open('rb') as source:
        archive_hash = hashlib.file_digest(source, 'sha256').hexdigest()
    with tarfile.open(path, 'r:*') as archive:
        manifest = json.loads(member_bytes(archive, 'manifest.json'))
        if not isinstance(manifest, list) or len(manifest) != 1:
            raise ValueError('HTTPie archive must contain exactly one image')
        entry = manifest[0]
        tags = entry.get('RepoTags')
        if (not isinstance(tags, list) or len(tags) != 1 or not isinstance(tags[0], str)
                or not re.fullmatch(r'np-httpie-first-use:[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', tags[0])):
            raise ValueError('HTTPie archive must contain one owned campaign tag')
        raw_config = member_bytes(archive, entry['Config'])
        config = json.loads(raw_config)
        if (config.get('os'), config.get('architecture')) != ('linux', 'arm64'):
            raise ValueError('HTTPie archive image must be Linux ARM64')
        diff_ids = config['rootfs']['diff_ids']
        layers = entry['Layers']
        if (not diff_ids or len(diff_ids) != len(layers)
                or any(not re.fullmatch(r'sha256:[a-f0-9]{64}', value) for value in diff_ids)
                or any(not archive.getmember(layer).isfile() for layer in layers)):
            raise ValueError('HTTPie archive layer list differs from the config')
        if 'index.json' in archive.getnames():
            descriptors = json.loads(member_bytes(archive, 'index.json'))['manifests']
            if len(descriptors) != 1:
                raise ValueError('HTTPie OCI index must contain one image descriptor')
            descriptor = descriptors[0]
            annotations = descriptor.get('annotations', {})
            if (annotations.get('io.containerd.image.name') not in (None, f'docker.io/library/{tags[0]}')
                    or annotations.get('org.opencontainers.image.ref.name') not in (None, tags[0].split(':')[1])):
                raise ValueError('HTTPie OCI index refers to an image outside the campaign tag')
    return {'archive_sha256': archive_hash,
            'config_sha256': 'sha256:' + hashlib.sha256(raw_config).hexdigest(),
            'diff_ids': diff_ids, 'reference': tags[0]}


def member_bytes(archive, name):
    member = archive.getmember(name)
    if not member.isfile():
        raise ValueError(f'HTTPie archive member is not a regular file: {name}')
    with archive.extractfile(member) as source:
        return source.read()


def verify_loaded_image(image, identity):
    if ((image.get('Os'), image.get('Architecture')) != ('linux', 'arm64')
            or (image.get('RootFS') or {}).get('Layers') != identity['diff_ids']):
        raise ValueError('loaded HTTPie image differs from the frozen ARM64 rootfs')
    image_id = image.get('Id', '')
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', image_id):
        raise ValueError('loaded HTTPie image ID is unavailable')
    return image_id


def frozen_input(archive, receipt):
    identity = archive_identity(archive)
    if any(receipt.get(key) != value for key, value in identity.items()):
        raise ValueError('HTTPie archive differs from its freeze receipt')
    note = receipt.get('expected_note', '')
    orb_id = receipt.get('orbstack_image_id', '')
    if not re.fullmatch(r'incremental-1:[a-f0-9]{64}\n', note) or not re.fullmatch(r'sha256:[a-f0-9]{64}', orb_id):
        raise ValueError('HTTPie freeze receipt lacks the exact note or OrbStack image ID')
    return {**identity, 'expected_note': note}, orb_id


def loaded_id(engine, identity, expected):
    inspected, = json.loads(engine.sh(['image', 'inspect', identity['reference']], timeout=45).stdout)
    image_id = verify_loaded_image(inspected, identity)
    if image_id != expected:
        raise ValueError(f'{engine.name} loaded HTTPie image ID differs from its freeze receipt')
    return image_id


def inspect_trial(ctx, engine, name, directory, record, archive, identity, orb_id):
    import runner

    engine.ensure_up()
    reference = identity['reference']
    expected = orb_id if engine.name == 'orbstack' else identity['config_sha256']
    if engine.name == 'orbstack':
        loaded_id(engine, identity, expected)
    started = time.monotonic()
    imported = engine.sh(['image', 'load', '--input', str(archive)], timeout=300)
    record['metrics']['import_seconds'] = time.monotonic() - started
    (directory / 'import.log').write_text(imported.stdout + imported.stderr)
    image_id = loaded_id(engine, identity, expected)
    record['inputs'] = {'loaded_image_id': image_id}
    record['correctness']['checks']['image_bytes_verified'] = True
    sampler, trace = runner.start_sampler(engine, directory)
    try:
        owned = engine.measurement_identity
        if owned.get('error') or not owned.get('required_processes'):
            raise ValueError('HTTPie engine resource ownership is unverified')
        if engine.name == 'ctrs':
            daemons = [p['executable']['sha256'] for p in owned['required_processes'] if p['role'] == 'daemon']
            if daemons != [ctx.provenance['build_outputs']['ctrs_binary_sha256']]:
                raise ValueError('HTTPie ctrs daemon differs from the signed candidate')
        relays_before = runner.relay_counts(engine) if engine.name == 'ctrs' else None
        with runner.resource_phase(engine, record, 'first-use'):
            version = engine.sh(['run', '--rm', '--pull=never', '--name', name,
                                 '--label', f'dev.ctrs.campaign.run={ctx.run_id}', image_id, 'http', '--version'], timeout=60)
        if engine.name == 'ctrs':
            record['cpu_accounting'] = runner.cpu_accounting(relays_before, runner.relay_counts(engine))
    finally:
        runner.stop_sampler(sampler)
    phase = record['resources']['phases']['first-use']
    samples = [json.loads(line) for line in trace.read_text().splitlines()]
    receipt = runner.resource_cycles.phase_summary(owned, phase, samples)
    record['resources'].update(phase_receipts={'first-use': receipt}, trace=runner._trace_ref(trace),
                               ownership_verified=receipt['status'] == 'ok', resource_errors=receipt['errors'],
                               cpu_counter_scope='first-use boundary deltas', cpu_counters_complete=receipt['status'] == 'ok',
                               cpu_seconds_est=receipt['cpu_seconds'], footprint_field='phys_footprint',
                               peak_phys_footprint_bytes=receipt['peak_phys_footprint_bytes'])
    record['metrics']['httpie_first_use_s'] = phase['operation_wall_seconds']
    note = engine.sh(['run', '--rm', '--pull=never', '--name', name + '-note',
                      '--label', f'dev.ctrs.campaign.run={ctx.run_id}', image_id, 'cat', '/out/note.txt'], timeout=60)
    (directory / 'probe.json').write_text(json.dumps({'version': version.stdout, 'note': note.stdout}, indent=2) + '\n')
    record['correctness']['checks'].update(version_exact=version.stdout == '3.2.4\n',
                                          note_exact=note.stdout == identity['expected_note'])
    if not all(record['correctness']['checks'].values()):
        raise ValueError('HTTPie first-use version or rootfs note differed from the freeze receipt')
    record['engine_server_version'] = runner.safe_version(engine)
    info = runner.safe_engine_info(engine)
    if record['engine_server_version'] == 'unreachable' or not info:
        raise ValueError('HTTPie engine version or resource allocation unavailable')
    record['resources']['engine'] = info


def run_batch(args):
    import reporting
    import runner

    identity, orb_id = frozen_input(args.archive, json.loads(args.receipt.read_text()))
    run = 'httpie-first-use-' + secrets.token_hex(6)
    ctx = runner.RunContext(run)
    ctx.resource_lane = 'installed-default'
    ctx.workload_params = {'fixture_version': FIXTURE_VERSION, 'resource_lane': ctx.resource_lane,
                           'archive_sha256': identity['archive_sha256']}
    ctx.provenance['httpie_first_use_sha256'] = runner.sha256_file(Path(__file__))
    parent = runner.HOLD.parent
    parent.mkdir(parents=True, exist_ok=True)
    print(f'results: {ctx.jsonl}', flush=True)
    failed = False
    admitted = 0
    for pair in range(1, args.pairs + 1):
        runner.wait_for_quiet_host(4., 3600.)
        ctx.workload_id = runner.workload_id(run, 'W7', pair, 0)
        batch = []
        order = ('ctrs', 'orbstack') if pair % 2 else ('orbstack', 'ctrs')
        for index, role in enumerate(order):
            owned = Path(tempfile.mkdtemp(prefix='hf.', dir=parent)) if role == 'ctrs' else None
            if owned and len(os.fsencode(owned / 'run/docker.sock')) >= 104:
                owned.rmdir()
                raise ValueError('private HTTPie engine socket path is too long')
            engine = runner.Engine(role, run, fresh_dir=owned, resource_lane=ctx.resource_lane)
            directory = ctx.trial_dir(role, 'W7', 'imported')
            record = ctx.new_record(engine, 'W7', 'imported', directory)
            record.update(pair_id=pair, order_index=index, paired_inputs=identity)
            record['correctness']['ok'] = False
            name = f'{run}-{pair}'
            try:
                inspect_trial(ctx, engine, name, directory, record, args.archive, identity, orb_id)
                record['correctness']['ok'] = True
            except Exception as exc:
                record['validation_errors'].append(str(exc))
            finally:
                try:
                    if owned:
                        engine.stop()
                        if (owned / 'daemon.log').is_file():
                            shutil.copyfile(owned / 'daemon.log', directory / 'daemon.log')
                        shutil.rmtree(owned)
                    elif not record['correctness']['ok']:
                        cleanup = engine.sh(['ps', '-aq', '--filter', f'label=dev.ctrs.campaign.run={run}'], timeout=30)
                        if ids := cleanup.stdout.split():
                            engine.sh(['rm', '-f', *ids], timeout=30)
                except Exception as exc:
                    record['correctness']['ok'] = False
                    record['validation_errors'].append(f'HTTPie cleanup: {exc}')
                ctx.write(record)
            batch.append(record)
            print(f"pair {pair} {role}: {'OK' if record['correctness']['ok'] else 'FAIL'}", flush=True)
        correct = all(row['correctness']['ok'] for row in batch)
        failed |= not correct
        admitted += correct and all(reporting.host_contended(row) is None for row in batch)
    if archive_identity(args.archive)['archive_sha256'] != identity['archive_sha256']:
        raise ValueError('HTTPie frozen archive changed during the comparison')
    print(f'admitted: {admitted}/{args.pairs}', flush=True)
    return int(failed or admitted != args.pairs)
