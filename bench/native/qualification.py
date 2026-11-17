"""Frozen evidence admission for the native macOS qualification workloads."""
import json
import hashlib
import math
from pathlib import Path
import re
import socket
import time
import tomllib

import durable_job
import mixed_resources
import runner
from mixed_cycle import PIN


CASES = tuple(f'W{i}' for i in range(1, 12))
DIMENSIONS = ('application', 'cpu_efficiency', 'physical_memory', 'idle_cpu',
              'idle_wakes', 'reclamation', 'next_use', 'allocated_storage',
              'resource_growth', 'recovery', 'correctness', 'persistence',
              'durability', 'reliability')
PREREQUISITES = ('representative_pinned_workloads', 'valid_resource_accounting',
                 'running_artifact_identity', 'correctness_resolved',
                 'durability_contract', 'resource_gates_implemented',
                 'observer_overhead', 'host_conditions', 'complete_cell_contract')
STATUSES = frozenset(('win', 'parity', 'loss', 'inconclusive', 'invalid', 'unmeasured'))
COMPARISONS = frozenset(('installed-default', 'resource-matched-default-driver',
                        'identical-builder'))
W11_REQUIRED_DIMENSIONS = frozenset((
    'correctness', 'persistence', 'durability', 'resource_growth', 'reliability',
))
MINIMUM_WORK_SECONDS = 12 * 60 * 60
MAX_DIAGNOSTIC_WORK_SECONDS = 15 * 60
MAX_EXCLUSIVITY_REVIEW_SECONDS = 5 * 60


class ReadinessError(ValueError):
    pass


def _object(value, label):
    if not isinstance(value, dict):
        raise ReadinessError(label + ' must be an object')
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ReadinessError(label + ' must be a nonempty string')
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReadinessError('duplicate readiness field: ' + key)
        result[key] = value
    return result


def require_readiness(path, *, required_paths, assets_path, sparse_paths=(), admission_epoch=None):
    """Verify a frozen declaration and receipts; reviewers own its scientific attestations.

    The matrix records unknowns and losses before qualification. Readiness never
    promotes those cells or substitutes for completed comparative measurements.
    """
    try:
        doc = _object(json.loads(Path(path).read_text(), object_pairs_hook=_unique), 'readiness')
        assets = tomllib.loads(Path(assets_path).read_text())
        if doc.get('schema') != 1 or type(doc.get('schema')) is not int:
            raise ReadinessError('unsupported readiness schema')
        if doc.get('scope') != 'native-arm64-macos' or doc.get('freeze_status') != 'frozen':
            raise ReadinessError('require a frozen native ARM64 macOS candidate')
        if assets.get('freeze', {}).get('status') != 'frozen':
            raise ReadinessError('assets.lock is not frozen')
        if re.fullmatch(r'[0-9a-f]{40}', str(doc.get('runtime_revision'))) is None:
            raise ReadinessError('runtime_revision must identify the built runtime source')
        checked = {}
        sparse = {str(Path(p).resolve(strict=True)) for p in sparse_paths}

        def receipt(value, label):
            item = _object(value, label)
            name = _text(item.get('path'), label + '.path')
            if not Path(name).is_absolute() or str(Path(name).resolve(strict=True)) != name:
                raise ReadinessError(label + ' must name its canonical absolute file')
            if name in sparse and item.get('hash_method') != 'sparse-extent-v1':
                raise ReadinessError(label + ' requires an explicit sparse receipt')
            if name in checked and checked[name] != item:
                raise ReadinessError('conflicting receipt: ' + name)
            if name not in checked:
                durable_job.check_receipt(item)
                checked[name] = item
            return item

        artifacts = _object(doc.get('artifacts'), 'artifacts')
        if set(artifacts) != {'ctrs_binary', 'guest_kernel', 'guest_initramfs'}:
            raise ReadinessError('require exactly the running binary and boot artifacts')
        for name in ('ctrs_binary', 'guest_kernel', 'guest_initramfs'):
            receipt(artifacts.get(name), 'artifacts.' + name)
        versions = _object(doc.get('engine_versions'), 'engine_versions')
        for name in ('ctrs', 'orbstack'):
            _text(versions.get(name), 'engine_versions.' + name)
        tools = _object(doc.get('tools'), 'tools')
        for name in runner.TOOL_CONTRACTS:
            tool = _object(tools.get(name), 'tools.' + name)
            _text(tool.get('version'), 'tools.' + name + '.version')
            receipt(tool.get('artifact'), 'tools.' + name + '.artifact')
        for name, contract in runner.TOOL_CONTRACTS.items():
            field = contract['asset_version']
            if assets.get('tools', {}).get(field) != tools[name]['version']:
                raise ReadinessError('assets.lock tool version differs from readiness: ' + field)
        for name in ('postgres', 'redis', 'api_base', 'fixture_api'):
            if re.fullmatch(r'.+@sha256:[0-9a-f]{64}', str(assets.get('images', {}).get(name))) is None:
                raise ReadinessError('unfrozen service image: ' + name)
        for name, image in (('postgres', 'np-v2/postgres'), ('redis', 'np-v2/redis'), ('fixture_api', 'np-v2/api')):
            if not assets['images'][name].endswith('@' + PIN['images'][image]['manifest']):
                raise ReadinessError('assets.lock service image differs from running portfolio: ' + name)
        inputs = doc.get('inputs')
        if not isinstance(inputs, list) or not inputs:
            raise ReadinessError('require frozen runtime and application inputs')
        input_names = set()
        for item in inputs:
            name = receipt(item, 'inputs')['path']
            if name in input_names:
                raise ReadinessError('duplicate input: ' + name)
            input_names.add(name)
        required = {str(Path(p).resolve(strict=True)) for p in (*required_paths, assets_path)}
        if required - input_names:
            raise ReadinessError('missing frozen inputs: ' + ', '.join(sorted(required - input_names)))
        for name, item in artifacts.items():
            if item['path'] not in input_names:
                raise ReadinessError('artifact absent from frozen inputs: ' + name)
        for name, tool in tools.items():
            if tool['artifact']['path'] not in input_names:
                raise ReadinessError('tool absent from frozen inputs: ' + name)
        fixtures = _object(doc.get('fixtures'), 'fixtures')
        if set(fixtures) != set(CASES):
            raise ReadinessError('require versioned W1 through W11 fixtures')
        for name, fixture in fixtures.items():
            fixture = _object(fixture, 'fixtures.' + name)
            _text(fixture.get('version'), 'fixtures.' + name + '.version')
            receipt(fixture.get('evidence'), 'fixtures.' + name + '.evidence')
        prerequisites = _object(doc.get('prerequisites'), 'prerequisites')
        if set(prerequisites) != set(PREREQUISITES):
            raise ReadinessError('incomplete prerequisite evidence')
        for name, proof in prerequisites.items():
            proof = _object(proof, 'prerequisites.' + name)
            if proof.get('status') != 'pass':
                raise ReadinessError('unmet prerequisite: ' + name)
            receipt(proof.get('evidence'), 'prerequisites.' + name + '.evidence')
        host_review = _object(json.loads(Path(prerequisites['host_conditions']['evidence']['path']).read_text(),
                                        object_pairs_hook=_unique), 'host conditions review')
        admitted = time.time() if admission_epoch is None else admission_epoch
        observed, expires = host_review.get('observed_epoch'), host_review.get('expires_epoch')
        clocks = (observed, expires, admitted)
        if (any(type(value) not in (int, float) or not math.isfinite(value) for value in clocks)
                or not observed <= admitted <= expires
                or expires - observed > MAX_EXCLUSIVITY_REVIEW_SECONDS):
            raise ReadinessError('host conditions review is stale or has invalid clocks')
        if (host_review.get('kind') != 'native-host-conditions-review'
                or host_review.get('host_id') != socket.gethostname()
                or host_review.get('conclusion') not in ('exclusive', 'bounded-noise')):
            raise ReadinessError('host conditions review does not establish this admission')
        if host_review['conclusion'] == 'bounded-noise':
            _text(host_review.get('noise_policy'), 'disclosed background noise policy')
            _text(host_review.get('analysis_policy'), 'noise analysis and invalidation policy')
        _text(host_review.get('reviewer'), 'host conditions reviewer')
        observations = host_review.get('observations')
        if not isinstance(observations, list) or not observations:
            raise ReadinessError('host conditions review lacks actual observations')
        for observation in observations:
            receipt(observation, 'host conditions observation')
        durability = _object(doc.get('durability'), 'durability')
        for name in ('failure_model', 'ctrs_guarantee', 'orbstack_guarantee'):
            _text(durability.get(name), 'durability.' + name)
        if durability.get('comparable') is not True:
            raise ReadinessError('durability guarantees are not comparable')
        receipt(durability.get('evidence'), 'durability.evidence')
        comparison = _object(doc.get('comparison'), 'comparison')
        if comparison.get('label') not in COMPARISONS or comparison.get('builder_driver') != 'docker':
            raise ReadinessError('require a disclosed comparison using the default build driver')
        for name in ('ctrs_cpus', 'ctrs_memory_mib'):
            if type(comparison.get(name)) is not int or comparison[name] <= 0:
                raise ReadinessError('invalid resource budget: ' + name)
        envelopes = _object(comparison.get('engine_resources'), 'comparison.engine_resources')
        if set(envelopes) != {'ctrs', 'orbstack'}:
            raise ReadinessError('require both declared engine resource envelopes')
        for name, envelope in envelopes.items():
            envelope = _object(envelope, 'engine resource envelope: ' + name)
            if any(type(envelope.get(key)) is not int or envelope[key] <= 0 for key in ('ncpu', 'mem_total_bytes')):
                raise ReadinessError('invalid engine resource envelope: ' + name)
        if envelopes['ctrs']['ncpu'] != comparison['ctrs_cpus']:
            raise ReadinessError('configured ctrs CPU count differs from its declared envelope')
        if comparison['label'] == 'resource-matched-default-driver' and not runner.resource_cells.engine_budget_matches(envelopes['ctrs'], envelopes['orbstack']):
            raise ReadinessError('resource-matched comparison has unequal resource envelopes')
        contract = _object(doc.get('cell_contract'), 'cell_contract')
        workloads, dimensions, identities = set(), set(), set()
        for name, specification in contract.items():
            _text(name, 'cell id')
            specification = _object(specification, 'cell_contract.' + name)
            workload, dimension = specification.get('workload'), specification.get('dimension')
            if workload not in CASES or dimension not in DIMENSIONS:
                raise ReadinessError('unknown workload or dimension in cell: ' + name)
            if specification.get('fixture_version') != fixtures[workload]['version']:
                raise ReadinessError('cell fixture version differs: ' + name)
            for field in ('metric', 'state', 'load', 'unit'):
                _text(specification.get(field), 'cell_contract.' + name + '.' + field)
            identity = tuple(specification[field] for field in ('workload', 'dimension', 'metric', 'state', 'load'))
            if identity in identities:
                raise ReadinessError('duplicate declared measurement cell: ' + name)
            identities.add(identity)
            workloads.add(workload); dimensions.add(dimension)
        if workloads != set(CASES) or dimensions != set(DIMENSIONS):
            raise ReadinessError('cell contract omits a required workload or dimension')
        w11_dimensions = {dimension for workload, dimension, *_ in identities if workload == 'W11'}
        if missing := W11_REQUIRED_DIMENSIONS - w11_dimensions:
            raise ReadinessError('W11 is missing required dimensions: ' + ', '.join(sorted(missing)))
        review_path = prerequisites['complete_cell_contract']['evidence']['path']
        review = _object(json.loads(Path(review_path).read_text(), object_pairs_hook=_unique), 'cell contract review')
        digest = hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if (review.get('kind') != 'native-cell-contract-review' or review.get('conclusion') != 'complete'
                or review.get('cell_contract_sha256') != digest):
            raise ReadinessError('cell contract lacks a matching completeness review')
        _text(review.get('reviewer'), 'cell contract reviewer')
        matrix = _object(doc.get('matrix'), 'matrix')
        if set(matrix) != set(contract):
            raise ReadinessError('status matrix must cover every declared measurement cell exactly')
        for name, cell in matrix.items():
            cell = _object(cell, 'matrix.' + name)
            if cell.get('status') not in STATUSES:
                raise ReadinessError('invalid cell status: ' + name)
            if contract[name]['dimension'] in ('correctness', 'persistence', 'durability') and cell['status'] in ('loss', 'invalid'):
                raise ReadinessError('unresolved hard failure in matrix: ' + name)
            if cell['status'] != 'unmeasured':
                receipt(cell.get('evidence'), 'matrix.' + name + '.evidence')
            elif cell.get('evidence') is not None:
                receipt(cell['evidence'], 'matrix.' + name + '.evidence')
        return doc
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        if isinstance(exc, ReadinessError):
            raise
        raise ReadinessError('invalid frozen readiness: ' + str(exc)) from exc


def leg_issues(record, *, work_deadline, completed_monotonic):
    """Check completed W11 hard requirements; independent scientific review remains required."""
    issues = []
    correctness = record.get('correctness', {})
    if (correctness.get('ok') is not True or record.get('validation_errors')
            or not correctness.get('checks') or any(value is not True for value in correctness['checks'].values())):
        issues.append('mixed workload correctness failed or lacks completed checks')
    resources = record.get('resources', {})
    numeric = [resources.get(key) for key in ('peak_phys_footprint_bytes', 'cpu_seconds_est')]
    if (resources.get('ownership_verified') is not True or resources.get('cpu_counters_complete') is not True
            or resources.get('resource_errors') != [] or resources.get('footprint_field') != 'phys_footprint'
            or resources.get('sampler_version') != mixed_resources.collect.SAMPLER_VERSION
            or any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in numeric)):
        issues.append('incomplete whole-engine resource accounting')
    growth = resources.get('cycle_growth', {})
    identity = record.get('running_identity', {})
    required = identity.get('required_processes', [])
    ids = [process.get('pid') for process in required]
    if (identity.get('engine') != record.get('engine') or not required or len(set(ids)) != len(ids)
            or any(type(process.get('pid')) is not int or process.get('pid') <= 0
                   or type(process.get('kernel_start_identity')) is not int or not process.get('start_identity')
                   for process in required)
            or not any(process.get('role') == 'daemon' for process in required)
            or (record.get('engine') == 'ctrs' and not any(process.get('role') == 'vm' for process in required))
            or growth.get('plan', {}).get('manifest') != identity):
        issues.append('incomplete or inconsistent running process identity')
    if (record.get('fixture_version') != mixed_resources.VERSION
            or growth.get('version') != mixed_resources.VERSION
            or growth.get('plan', {}).get('budgets') != mixed_resources.BUDGETS):
        issues.append('resource observation fixture or budgets differ from the frozen contract')
    else:
        checked = mixed_resources.summarize(growth['plan'], growth.get('observations', []))
        if not checked['minimum_coverage_met'] or any(checked[key]['status'] != 'pass' for key in
                ('physical_footprint', 'file_descriptors', 'active_disk_allocation')):
            issues.append('post-warmup resource growth failed or is unknown')
    started = resources.get('phases', {}).get('cycle_0_mixed_work', {}).get('operation_started_monotonic')
    if (type(started) not in (int, float) or type(work_deadline) not in (int, float)
            or type(completed_monotonic) not in (int, float)
            or not all(math.isfinite(value) for value in (started, work_deadline, completed_monotonic))
            or not completed_monotonic >= work_deadline >= started + MINIMUM_WORK_SECONDS):
        issues.append('fewer than twelve hours of mixed-work exposure or incomplete deadline')
    return issues
