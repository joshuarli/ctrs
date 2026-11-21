import json
import os
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import linux_cgroups as cg
import linux_lane as lane
import runner
import pyramid
import reporting


class Cgroups(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=runner.REPO / '.work/tmp')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.proc = self.root / 'proc'
        self.proc.mkdir()
        self.identity = {'engine': 'dockerd', 'cgroup_roots': list(cg.SERVICES)}
        for name in cg.SERVICES:
            self.group(name)
        self.process(599, 1, cg.SERVICES[0])

    def process(self, pid, parent, group, command=b'dockerd\0'):
        directory = self.proc / str(pid)
        directory.mkdir(exist_ok=True)
        (directory / 'stat').write_text(f'{pid} (test) ' + ' '.join(['S', str(parent), *['0'] * 17, '123']))
        (directory / 'cgroup').write_text('0::/' + group + '\n')
        (directory / 'cmdline').write_bytes(command)

    def sample(self, identity=None):
        return cg.sample(identity or self.identity, self.root, self.proc)

    def group(self, name, usage=1000000, peak=True):
        directory = self.root / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'cpu.stat').write_text(f'usage_usec {usage}\nuser_usec 0\n')
        (directory / 'memory.current').write_text('4096\n')
        (directory / 'memory.stat').write_text('anon 1024\nfile 2048\nkernel 1024\n')
        if peak:
            (directory / 'memory.peak').write_text('8192\n')
        return directory

    def test_services_and_dynamic_scopes_do_not_double_count_descendants(self):
        first = self.sample()
        scope = 'system.slice/docker-' + 'a' * 64 + '.scope'
        self.group(scope)
        self.group(scope + '/nested', usage=90000000)
        self.process(600, 599, scope)
        second = self.sample()
        self.assertEqual(len(first['groups']), 2)
        self.assertEqual(len(second['groups']), 3)
        self.assertEqual(cg.cpu_delta(first, second)['cpu_seconds'], 1)
        summary = cg.summarize([first, second])
        self.assertEqual(summary['cpu_seconds_est'], 1)
        self.assertEqual(summary['peak_memory_current_bytes'], 12288)
        self.assertEqual(summary['peak_anon_kernel_bytes'], 6144)
        self.assertEqual(summary['peak_memory_file_bytes'], 6144)

    def test_optional_peak(self):
        directory = self.root / cg.SERVICES[0]
        (directory / 'memory.peak').unlink()
        sample = self.sample()
        self.assertEqual(sample['errors'], [])
        self.assertIsNone(sample['groups'][cg.SERVICES[0]]['memory_peak_bytes'])

    def test_missing_required_counter_invalidates_measurement(self):
        (self.root / cg.SERVICES[0] / 'cpu.stat').unlink()
        sample = self.sample()
        self.assertTrue(sample['errors'])
        self.assertIsNone(cg.summarize([sample, sample])['cpu_seconds_est'])

    def test_overlap_and_nested_roots_refused(self):
        for update in ({'excluded_cgroups': ['system.slice']},
                       {'cgroup_roots': ['system.slice', cg.SERVICES[0]]}):
            sample = self.sample({**self.identity, **update})
            self.assertTrue(sample['errors'])

    def test_symlink_refused(self):
        link = self.root / 'system.slice/alias.service'
        link.symlink_to(self.root / cg.SERVICES[0], target_is_directory=True)
        sample = self.sample({'engine': 'ctrs', 'cgroup_roots': ['system.slice/alias.service']})
        self.assertTrue(sample['errors'])

    def test_reset_and_empty_boundaries_do_not_score_zero(self):
        before = self.sample()
        self.group(cg.SERVICES[0], usage=0)
        after = self.sample()
        self.assertIsNone(cg.cpu_delta(before, after)['cpu_seconds'])
        self.assertIsNone(cg.cpu_delta({'errors': [], 'groups': {}}, after)['cpu_seconds'])

    def test_proc_stat_excludes_guest_ticks_and_iowait(self):
        stat = self.root / 'stat'
        stat.write_text('cpu 10 0 10 40 40 0 0 0 999 999\ncpu0 0\n')
        ticks = cg.host_cpu_ticks(stat)
        self.assertEqual(cg.busy_cores([0] * 8, ticks, 8), 1.6)
        self.assertIsNone(cg.busy_cores(ticks, ticks, 8))

    def test_socket_activation_follows_listener_inode_not_systemd_peer(self):
        proc = self.root / 'proc'
        (proc / 'net').mkdir(parents=True)
        (proc / 'net/unix').write_text('header\n0: 2 0 00010000 0001 01 42 /owned/docker.sock\n')
        daemon = proc / '88'
        (daemon / 'fd').mkdir(parents=True)
        (daemon / 'fd/3').symlink_to('socket:[42]')
        (daemon / 'cgroup').write_text('0::/system.slice/docker.service\n')
        (self.root / cg.SERVICES[0] / 'cgroup.procs').write_text('88\n')
        self.assertEqual(cg.socket_holder(Path('/owned/docker.sock'), self.root, proc), 88)
        (daemon / 'fd/3').unlink()
        with self.assertRaisesRegex(ValueError, 'unique'):
            cg.socket_holder(Path('/owned/docker.sock'), self.root, proc)

    def test_buildkit_and_other_transients_rediscovered_by_ancestry(self):
        before = self.sample()
        for pid, group in [(600, 'system.slice/system.slice:docker:build123'),
                           (601, 'other.slice/transient-job')]:
            self.group(group)
            self.process(pid, 599, group)
        after = self.sample()
        self.assertTrue(after['ownership_verified'])
        self.assertEqual(len(after['transient_ownership']), 2)
        self.assertEqual(cg.cpu_delta(before, after)['cpu_seconds'], 2)

    def test_transients_cannot_be_claimed_by_name_alone(self):
        group = 'other.slice/transient-job'
        self.group(group)
        self.process(600, 1, group, b'unrelated\0')
        self.identity['verified_transients'] = {group: -1}
        sample = self.sample()
        self.assertFalse(sample['ownership_verified'])
        self.assertIsNone(cg.summarize([sample, sample])['cpu_seconds_est'])

    def test_empty_scope_creation_requires_owned_docker_api_confirmation(self):
        group = 'system.slice/docker-' + 'a' * 64 + '.scope'
        self.group(group)
        self.identity['endpoint'] = '/owned/docker.sock'
        with patch.object(cg, 'docker_container_ids', return_value={'a' * 64}):
            sample = self.sample()
        self.assertTrue(sample['ownership_verified'])
        self.assertIn(group, sample['transient_ownership'])
        self.identity.pop('verified_transients')
        with patch.object(cg, 'docker_container_ids', return_value=set()):
            self.assertFalse(self.sample()['ownership_verified'])

    def test_new_cgroup_members_missing_from_proc_listing_are_verified_directly(self):
        group = 'other.slice/forked'
        self.group(group)
        self.identity['verified_transients'] = {group: -1}
        (self.root / group / 'cgroup.procs').write_text('600\n')
        listing = Path.iterdir

        def snapshot(path):
            return (entry for entry in listing(path) if path != self.proc or entry.name != '600')

        for parent, expected in [(1, False), (599, True)]:
            self.process(600, parent, group, b'new-process\0')
            with patch.object(Path, 'iterdir', snapshot):
                self.assertEqual(self.sample()['ownership_verified'], expected)

    def test_structural_buildkit_ownership_needs_no_live_process_or_metadata(self):
        before = self.sample()
        group = 'system.slice/system.slice:docker:retired-worker'
        self.group(group, usage=5000000)
        after = self.sample()
        self.assertTrue(after['ownership_verified'], after['errors'])
        self.assertIn('structural', after['transient_ownership'][group]['method'])
        shutil.rmtree(self.root / group)
        retired = self.sample()
        summary = cg.summarize([before, after, retired])
        self.assertEqual(summary['cpu_seconds_est'], 5)
        self.assertEqual(summary['peak_memory_current_bytes'], 12288)
        self.assertEqual(summary['peak_anon_kernel_bytes'], 6144)

    def test_structural_buildkit_rule_counts_unrelated_processes_by_design(self):
        group = 'system.slice/system.slice:docker:claimed-name'
        self.group(group)
        self.process(600, 1, group, b'unrelated\0')
        self.assertTrue(self.sample()['ownership_verified'])

    def test_structural_rule_only_matches_direct_system_slice_children(self):
        for group in ('system.slice/system.slice:docker:', 'other.slice/system.slice:docker:worker',
                      'system.slice/parent/system.slice:docker:worker',
                      'system.slice/system.slice:docker:worker/child'):
            with self.subTest(group=group):
                self.assertFalse(cg.buildkit_group(group))
        self.assertTrue(cg.buildkit_group('system.slice/system.slice:docker:worker'))

    def test_ctrs_cannot_own_buildkit_groups_or_their_ancestors_or_descendants(self):
        group = 'system.slice/system.slice:docker:worker'
        self.group(group)
        self.group(group + '/child')
        for name in ('', '.', 'system.slice', group, group + '/child'):
            with self.subTest(name=name):
                result = self.sample({'engine': 'ctrs', 'cgroup_roots': [name]})
                self.assertFalse(result['ownership_verified'])
                self.assertIn('structurally owned Docker BuildKit', str(result['errors']))
        unit = 'system.slice/ctrs-bench.service'
        self.group(unit)
        result = self.sample({'engine': 'ctrs', 'cgroup_roots': [unit]})
        self.assertTrue(result['ownership_verified'])

    def test_moby_shim_descendants_outside_service_are_owned(self):
        self.process(600, 1, cg.SERVICES[1], b'/usr/bin/containerd-shim-runc-v2\0-namespace\0moby\0')
        group = 'custom.slice/docker-task'
        self.process(601, 600, group, b'workload\0')
        self.group(group)
        self.assertIn(group, self.sample()['groups'])

    def test_missing_memory_stat_never_scores_a_small_footprint(self):
        (self.root / cg.SERVICES[0] / 'memory.stat').write_text('anon 1024\nfile 2048\n')
        record = self.sample()
        result = cg.summarize([record, record])
        self.assertFalse(result['ownership_verified'])
        self.assertIsNone(result['peak_anon_kernel_bytes'])

    def test_footprint_analog_uses_coincident_anon_plus_kernel(self):
        first = self.sample()
        directory = self.root / cg.SERVICES[0]
        (directory / 'memory.stat').write_text('anon 0\nfile 2048\nkernel 2048\n')
        second = self.sample()
        self.assertEqual(cg.summarize([first, second])['peak_anon_kernel_bytes'], 4096)

    def test_phase_cpu_includes_a_worker_created_and_retired_between_boundaries(self):
        before = self.sample()
        group = 'system.slice/system.slice:docker:worker'
        self.group(group, usage=5000000)
        self.process(600, 599, group)
        during = self.sample()
        trace = self.root / 'trace.jsonl'
        trace.write_text(json.dumps(during) + '\n')
        shutil.rmtree(self.root / group)
        shutil.rmtree(self.proc / '600')
        after = self.sample()
        result = cg.phase_delta(before, after, trace)
        self.assertEqual(result['cpu_seconds'], 5)
        self.assertEqual(result['periodic_samples'], 1)


class Engines(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'NP_BENCH_LANE': 'linux-amd64', 'CTRS_SOCKET': '/owned/ctrs.sock'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_engine_selection_and_no_lifecycle(self):
        for name, endpoint in [('ctrs', '/owned/ctrs.sock'), ('dockerd', '/var/run/docker.sock')]:
            engine = runner.Engine(name, 'offline')
            self.assertEqual(engine.socket, 'unix://' + endpoint)
            with patch.object(engine, 'sh') as command, patch.object(runner.subprocess, 'Popen') as spawn:
                engine.ensure_up()
                command.assert_called_once_with(['version'], timeout=30)
                spawn.assert_not_called()
                with self.assertRaisesRegex(ValueError, 'externally managed'):
                    engine.stop()

    def test_fresh_configuration_and_missing_socket_refused(self):
        for name in ('ctrs', 'dockerd'):
            with self.assertRaisesRegex(ValueError, 'fresh_dir'):
                runner.Engine(name, 'offline', fresh_dir=Path('/fresh'))
        with patch.dict(os.environ, {'CTRS_SOCKET': ''}):
            with self.assertRaisesRegex(ValueError, 'CTRS_SOCKET'):
                runner.Engine('ctrs', 'offline')
        with self.assertRaisesRegex(ValueError, 'Linux lane'):
            runner.Engine('orbstack', 'offline')

    def test_workloads_and_cold_refusals(self):
        for case in lane.CASES:
            lane.require_case('dockerd', case)
        for engine, case, cold in [('orbstack', 'W2', False), ('ctrs', 'W8', False), ('dockerd', 'W6', True)]:
            with self.assertRaises(ValueError):
                lane.require_case(engine, case, cold)

    def test_lock_missing_and_wrong_architecture_refused(self):
        with tempfile.TemporaryDirectory(dir=runner.REPO / '.work/tmp') as tmp:
            lock = Path(tmp) / 'lock.json'
            with patch.object(lane, 'LOCK', lock):
                with self.assertRaisesRegex(ValueError, 'missing'):
                    lane.read_lock()
                lock.write_text(json.dumps({'fixture_version': lane.VERSION, 'platform': 'linux/arm64'}))
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    lane.read_lock()

    def test_frozen_archive_hash_error_does_not_touch_engines(self):
        with patch.object(lane, 'read_lock', return_value={'archive_sha256': 'frozen'}), \
                patch.object(runner, 'sha256_file', return_value='wrong'), \
                patch.object(runner, 'Engine') as factory:
            with self.assertRaisesRegex(ValueError, 'archive hash mismatch'):
                lane.prepare(factory, Path('/unused'), runner, Path('/archive'))
            factory.assert_not_called()

    def test_pyramid_has_only_supported_native_cells(self):
        items = pyramid.registry('linux-amd64')
        self.assertEqual(len(items), 4)
        self.assertTrue(all('dockerd' in item.argv and 'linux-amd64' in item.argv for item in items))

    def test_image_architecture_and_layers_are_checked(self):
        pin = {'ids': {'dockerd': 'immutable'}, 'diff_ids': ['expected']}
        engine = Mock(name='engine')
        engine.name = 'dockerd'
        engine.sh.return_value.stdout = json.dumps([{'Architecture': 'arm64', 'RootFS': {'Layers': ['expected']}}])
        with patch.object(lane, 'read_lock', return_value={'images': {'api': pin}}):
            with self.assertRaisesRegex(ValueError, 'differs'):
                lane.image(engine, 'api')

    def test_build_base_tags_must_still_match_the_untimed_freeze(self):
        engine = Mock()
        lock = {'images': {'rust': {'reference': 'rust:pinned'}}}
        with patch.object(lane, 'read_lock', return_value=lock), \
                patch.object(lane, 'image', return_value=('sha256:frozen', {'verified': True})):
            engine.sh.return_value.stdout = json.dumps([{'Id': 'sha256:frozen'}])
            self.assertEqual(lane.build_images(engine, ('rust',)), {'rust': {'verified': True}})
            engine.sh.return_value.stdout = json.dumps([{'Id': 'sha256:changed'}])
            with self.assertRaisesRegex(ValueError, 'tag changed'):
                lane.build_images(engine, ('rust',))


class LinuxReporting(unittest.TestCase):
    def test_footprint_analog_and_secondary_current_are_reported_for_dockerd(self):
        records = [{'run_id': 'run', 'host_id': 'host', 'arch': 'x86_64', 'git_sha': 'sha',
                    'case': 'W6', 'state': 'warm', 'lane': 'linux-amd64', 'engine': engine,
                    'pair_id': 1, 'order_index': order, 'workload_id': 'work',
                    'workload_params': {'lane': 'linux-amd64'},
                    'correctness': {'ok': True, 'checks': {'hash': True}},
                    'metrics': {'build_rust_s': 1, 'build_zlib_s': 1},
                    'resources': {'ownership_verified': True, 'resource_errors': [],
                                  'footprint_field': 'anon+kernel', 'peak_anon_kernel_bytes': 2048,
                                  'peak_memory_current_bytes': 8192}}
                   for order, engine in enumerate(('ctrs', 'dockerd'))]
        result = reporting.analyze(records)
        self.assertEqual(result['input_issues'], [])
        cohort = result['cohorts'][0]
        self.assertEqual(cohort['valid_pairs'], 1)
        metrics = {metric['metric']: metric for metric in cohort['metrics']}
        for metric in ('peak_anon_kernel_bytes', 'peak_memory_current_bytes'):
            self.assertEqual(metrics[metric]['ratio_median'], 1)
        self.assertNotIn('peak_phys_footprint_bytes', metrics)
        records[1]['resources']['ownership_verified'] = False
        self.assertIsNone(reporting._metric(records[1], 'peak_anon_kernel_bytes')[0])

    def test_linux_lane_never_pools_with_legacy_macos_identity(self):
        record = {'workload_params': {}}
        legacy = reporting.cohort_identity(record)
        linux = reporting.cohort_identity({**record, 'lane': 'linux-amd64'})
        self.assertNotIn('lane', legacy)
        self.assertNotEqual(legacy, linux)


if __name__ == '__main__':
    unittest.main()
