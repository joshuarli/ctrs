"""Post-cleanup resource observations for bounded mixed cycles."""
import copy
import ctypes
import hashlib
import math
import os
from pathlib import Path
import sys
import time

import collect
import macos_counters
import ownership
import resource_cells as cells
import resource_cycles
from macos_counters import Counters

VERSION = 'w11-v4-post-cleanup-resources'
BUDGETS = {'warmup_cycles': 1, 'minimum_post_warmup_cycles': 5,
           'minimum_observation_seconds': 30, 'physical_footprint_bytes': 16 * 1024 * 1024,
           'file_descriptors': 16, 'active_disk_allocation_bytes': 16 * 1024 * 1024}


def plan(config, manifest):
    if not isinstance(config, dict) or set(config) - {'seconds', 'owned_files'}:
        raise ValueError('observation configuration requires seconds and owned_files only')
    seconds = config.get('seconds', 30)
    paths = config.get('owned_files', ())
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 < seconds <= 3600:
        raise ValueError('observation seconds must be positive and at most 3600')
    if not isinstance(paths, tuple) or any(not isinstance(p, (str, Path)) for p in paths):
        raise ValueError('owned_files must be a tuple of paths')
    return {'version': VERSION, 'seconds': seconds, 'owned_files': [os.fspath(p) for p in paths],
            'budgets': dict(BUDGETS), 'manifest': copy.deepcopy(manifest),
            'sources': {Path(module.__file__).name: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
                        for module in (collect, macos_counters, ownership, cells, resource_cycles)},
            'observer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'mixed_cycle_sha256': hashlib.sha256(Path(__file__).with_name('mixed_cycle.py').read_bytes()).hexdigest(),
            'methods': {'interval': 'resource_cycles.idle_interval', 'allocation': 'resource_cells.allocation_snapshot',
                        'file_descriptors': 'proc_pidinfo PROC_PIDLISTFDS', 'ownership': 'ownership.open_files'}}


def fd_snapshot(manifest):
    started = time.monotonic()
    result = {'status': 'unknown', 'errors': [], 'processes': [], 'total': None,
              'method': 'proc_pidinfo PROC_PIDLISTFDS; kernel start before and after',
              'started_monotonic': started}
    try:
        required = manifest.get('required_processes', [])
        if not required or len({p['pid'] for p in required}) != len(required) or (manifest.get('engine') == 'ctrs' and not any(p.get('role') == 'vm' for p in required)):
            raise ValueError('incomplete required process manifest')
        if sys.platform != 'darwin' or os.uname().machine != 'arm64':
            raise RuntimeError('native FD sampling requires ARM64 macOS')
        lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
        lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
        lib.proc_pidinfo.restype = ctypes.c_int
        counters = Counters()
        for proc in required:
            pid = proc['pid']
            begin = time.monotonic()
            try:
                if counters.read(pid)['kernel_start_identity'] != proc['kernel_start_identity']:
                    raise ValueError('process start identity changed before FD sample')
                size = lib.proc_pidinfo(pid, 1, 0, None, 0)
                if size <= 0 or size > 8 * 65536:
                    raise ValueError('invalid or excessive FD buffer size')
                capacity = min(8 * 65536, size + 8 * 256)
                buf = ctypes.create_string_buffer(capacity)
                length = lib.proc_pidinfo(pid, 1, 0, buf, capacity)
                if length < 0 or length >= capacity or length % 8 or (length == 0 and size):
                    raise ValueError('incomplete FD list')
                if counters.read(pid)['kernel_start_identity'] != proc['kernel_start_identity']:
                    raise ValueError('process start identity changed after FD sample')
                result['processes'].append({'pid': pid, 'count': length // 8,
                    'started_monotonic': begin, 'ended_monotonic': time.monotonic()})
            except Exception as exc:
                result['errors'].append(f'pid {pid}: {exc!r}')
        if not result['errors'] and len(result['processes']) == len(required):
            result.update(status='ok', total=sum(p['count'] for p in result['processes']))
    except Exception as exc:
        result['errors'].append(repr(exc))
    result['ended_monotonic'] = time.monotonic()
    return result


def allocation(manifest, paths):
    snapshot = cells.allocation_snapshot(paths)
    if snapshot['status'] != 'ok':
        return snapshot
    try:
        required = manifest.get('required_processes', [])
        if not required or (manifest.get('engine') == 'ctrs' and not any(p.get('role') == 'vm' for p in required)):
            raise ValueError('incomplete required process manifest')
        counters = Counters()
        handles = set()
        for proc in required:
            pid = proc['pid']
            if counters.read(pid)['kernel_start_identity'] != proc['kernel_start_identity']:
                raise ValueError(f'process identity changed before open files: {pid}')
            for entry in ownership.open_files(pid):
                if entry.get('fd', '').isdigit() and entry.get('n') and entry.get('i'):
                    handles.add((entry['n'], entry['i']))
            if counters.read(pid)['kernel_start_identity'] != proc['kernel_start_identity']:
                raise ValueError(f'process identity changed after open files: {pid}')
        for item in snapshot['files']:
            if (item['path'], str(item['inode'])) not in handles:
                raise ValueError(f'file not held open by owned process: {item["path"]}')
        after = cells.allocation_snapshot(paths)
        if after['status'] != 'ok' or [(f['device'], f['inode']) for f in after['files']] != [(f['device'], f['inode']) for f in snapshot['files']]:
            raise ValueError('file identity changed during ownership check')
        snapshot = after
    except Exception as exc:
        snapshot.update(status='unknown', allocated_bytes=None)
        snapshot['errors'].append(repr(exc))
    return snapshot


def observe(plan_value, cycle, directory):
    manifest = plan_value['manifest']
    row = {'cycle': cycle, 'version': VERSION}
    try:
        row['interval'] = resource_cycles.idle_interval(manifest, plan_value['seconds'], directory / 'resource-interval.jsonl')
    except Exception as exc:
        row['interval'] = {'status': 'unknown', 'errors': [repr(exc)]}
    try:
        row['file_descriptors'] = fd_snapshot(manifest)
    except Exception as exc:
        row['file_descriptors'] = {'status': 'unknown', 'errors': [repr(exc)]}
    try:
        row['allocation'] = allocation(manifest, plan_value['owned_files'])
    except Exception as exc:
        row['allocation'] = {'status': 'unknown', 'errors': [repr(exc)]}
    return row


def summarize(plan_value, observations):
    budgets = plan_value['budgets']
    minimum = budgets['minimum_observation_seconds']
    def value(row, cell, key):
        interval = row.get('interval', {})
        if interval.get('status') != 'ok' or interval.get('elapsed_s', 0) < minimum:
            return None
        source = row.get(cell, {})
        return source.get(key) if source.get('status') == 'ok' else None
    result = {'version': VERSION, 'plan': plan_value, 'observations': observations,
              'minimum_coverage_met': len(observations) >= budgets['warmup_cycles'] + budgets['minimum_post_warmup_cycles'] and all(
                  r.get('interval', {}).get('status') == 'ok' and r['interval'].get('elapsed_s', 0) >= minimum for r in observations),
              'qualification_eligible': False,
              'exclusive_allocation': {'status': 'unknown', 'reason': 'shared APFS extents not measured'},
              'build_cache': {'status': 'unknown', 'reason': 'build cache is not isolated'}}
    file_ids = [tuple((f['device'], f['inode']) for f in r.get('allocation', {}).get('files', [])) for r in observations]
    files_stable = bool(file_ids) and bool(file_ids[0]) and all(ids == file_ids[0] for ids in file_ids)
    ordered = all(r.get('cycle') == i and r.get('version') == VERSION for i, r in enumerate(observations))
    if not ordered:
        result['minimum_coverage_met'] = False
    for name, cell, key, budget in (('physical_footprint', 'interval', 'steady_phys_footprint_bytes', budgets['physical_footprint_bytes']),
            ('file_descriptors', 'file_descriptors', 'total', budgets['file_descriptors']),
            ('active_disk_allocation', 'allocation', 'allocated_bytes', budgets['active_disk_allocation_bytes'])):
        values = [value(row, cell, key) for row in observations]
        if not ordered or (name == 'active_disk_allocation' and not files_stable):
            values = [None] * len(values)
        result[name] = cells.evaluate_cycles(values[0] if values else None, values[1:], warmup_cycles=0,
            minimum_cycles=budgets['minimum_post_warmup_cycles'], growth_budget=budget, return_tolerance=budget, reference_growth=0)
        valid = result[name]['status'] != 'unknown'
        result[name]['final_return_difference'] = values[-1] - values[0] if valid else None
        result[name]['final_return_status'] = ('pass' if values[-1] - values[0] <= budget else 'fail') if valid else 'unknown'
    return result
