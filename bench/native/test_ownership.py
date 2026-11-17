"""Behavioral checks for engine process and loaded-artifact attribution."""
from pathlib import Path
import os
import tempfile
import time
import unittest
from unittest.mock import patch

import collect
import ownership
import runner


class OwnershipTests(unittest.TestCase):
    def test_fixture_process_cannot_hide_failed_engine_discovery(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(runner.ownership, 'discover', side_effect=ValueError('missing VM')), \
                patch.object(runner.subprocess, 'Popen') as spawn:
            engine = Mock(name='engine')
            engine.name = 'ctrs'
            engine.socket = 'unix:///engine/docker.sock'
            engine.dir = Path('/engine')
            with self.assertRaisesRegex(ValueError, 'without verified engine ownership'):
                runner.start_sampler(engine, Path(directory), fixture_processes=({'pid': 303},))
        spawn.assert_not_called()

    def test_current_coordinator_has_native_and_loaded_executable_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'python'
            binary.write_bytes(b'coordinator interpreter')
            os.utime(binary, (1, 1))
            proc = {'pid': 303, 'comm': str(binary), 'start_identity': 'Sun Nov 15 21:24:06 2026'}
            with patch.object(ownership.os, 'getpid', return_value=303), \
                    patch.object(ownership, 'process_table', return_value={303: proc}), \
                    patch.object(ownership, 'open_files', return_value=[{
                        'fd': 'txt', 'n': str(binary), 'i': str(binary.stat().st_ino)}]), \
                    patch.object(ownership, 'Counters') as counters:
                counters.return_value.read.return_value = {'kernel_start_identity': 123}
                result = ownership.current_coordinator()
            self.assertEqual(result['role'], 'fixture-coordinator')
            self.assertEqual(result['kernel_start_identity'], 123)
            self.assertEqual(result['executable']['size'], len(b'coordinator interpreter'))

    def test_missing_vm_and_reused_pid_are_rejected(self):
        required = {1: {'comm': '/ctrs', 'start_identity': 'a'},
                    2: {'comm': '/VM', 'start_identity': 'b'}}
        self.assertEqual(collect.validate_processes(required, [
            {'pid': 1, **required[1]}]), ['missing required process 2'])
        self.assertEqual(collect.validate_processes(required, [
            {'pid': 1, **required[1]},
            {'pid': 2, 'comm': '/VM', 'start_identity': 'replacement'}]),
            ['process identity changed: 2'])

    def test_category_name_does_not_establish_vm_ownership(self):
        table = {1: {'pid': 1, 'comm': '/ctrs', 'start_identity': 'a'},
                 2: {'pid': 2, 'comm': '/com.apple.VirtualMachine', 'start_identity': 'b'}}
        with patch.object(ownership, 'process_table', return_value=table), \
                patch.object(ownership, 'open_files', side_effect=lambda pid: [
                    {'fd': '5', 't': 'unix', 'n': '/engine/docker.sock'}] if pid == 1 else []):
            with self.assertRaisesRegex(ValueError, 'disk-owning VM'):
                ownership.discover('ctrs', '/engine/docker.sock', '/engine')

    def test_only_dedicated_disk_owner_is_selected(self):
        table = {1: {'pid': 1, 'comm': '/ctrs', 'start_identity': 'Sun Nov 15 21:24:06 2026'},
                 2: {'pid': 2, 'comm': '/VirtualMachine', 'start_identity': 'Sun Nov 15 21:24:06 2026'},
                 3: {'pid': 3, 'comm': '/VirtualMachine', 'start_identity': 'Sun Nov 15 21:24:06 2026'}}
        files = {1: [{'fd': 'txt', 'n': '/ctrs'}, {'fd': '5', 't': 'unix', 'n': '/engine/docker.sock'}],
                 2: [{'fd': 'txt', 'n': '/VirtualMachine'}, {'fd': '6', 'n': '/engine/data/vm/data.img'},
                     {'fd': '3', 'n': '/guest/Image'}, {'fd': '4', 'n': '/guest/initramfs.cpio'}],
                 3: [{'fd': '6', 'n': '/unrelated/data.img'}]}
        with patch.object(ownership, 'process_table', return_value=table), \
                patch.object(ownership, 'open_files', side_effect=files.__getitem__), \
                patch.object(ownership, 'artifact', return_value={'sha256': 'abc'}), \
                patch.object(ownership, 'Counters') as counters:
            counters.return_value.read.return_value = {'kernel_start_identity': 123}
            result = ownership.discover('ctrs', '/engine/docker.sock', '/engine')
        self.assertEqual([p['pid'] for p in result['required_processes']], [1, 2])

    def test_changed_open_artifact_cannot_use_current_path_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Image'
            path.write_bytes(b'kernel')
            os.utime(path, (1, 1))
            record = {'n': str(path), 'i': str(path.stat().st_ino)}
            self.assertEqual(ownership.artifact(record, time.time())['size'], 6)
            with self.assertRaisesRegex(ValueError, 'changed'):
                ownership.artifact({**record, 'i': '999'}, time.time())
            with self.assertRaisesRegex(ValueError, 'changed'):
                ownership.artifact(record, 0)
