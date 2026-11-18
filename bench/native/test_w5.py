import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

FIXTURE = Path(__file__).parent / 'fixtures/w5-v2'
EDIT = FIXTURE / 'edit.mjs'
VERIFY = (FIXTURE / 'verify.mjs').resolve().as_uri()
CONTRACT = json.loads((FIXTURE / 'workload.json').read_text())
BEFORE = CONTRACT['edit']['original']
AFTER = CONTRACT['edit']['edited']


class W5Tests(unittest.TestCase):
    def test_edit_is_exact_reversible_and_rejects_unexpected_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'src').mkdir()
            source = root / 'src/Renderer.ts'
            source.write_text('prefix\n' + BEFORE + '\nsuffix\n')
            def run(state):
                return subprocess.run(['node', str(EDIT), str(root), state], capture_output=True, text=True)
            self.assertEqual(run('edited').returncode, 0)
            self.assertEqual(source.read_text(), 'prefix\n' + AFTER + '\nsuffix\n')
            self.assertNotEqual(run('edited').returncode, 0)
            self.assertEqual(source.read_text(), 'prefix\n' + AFTER + '\nsuffix\n')
            self.assertEqual(run('original').returncode, 0)
            self.assertEqual(source.read_text(), 'prefix\n' + BEFORE + '\nsuffix\n')
            source.write_text(BEFORE + BEFORE)
            self.assertNotEqual(run('edited').returncode, 0)
            self.assertEqual(source.read_text(), BEFORE + BEFORE)

    def test_cli_result_requires_exact_output_and_success(self):
        script = f'''import {{ verify, original, edited }} from {VERIFY!r};
for (const [output, expected] of [[original, 'original'], [edited, 'edited']]) {{
  if (verify({{status: 0, stdout: output, stderr: ''}}) !== expected) process.exit(1);
}}
for (const result of [
  {{status: 1, stdout: original, stderr: ''}},
  {{status: 0, stdout: original + 'extra', stderr: ''}},
  {{status: 0, stdout: edited, stderr: 'error'}},
  {{status: null, stdout: null, stderr: null}},
]) {{
  let rejected = false;
  try {{ verify(result); }} catch {{ rejected = true; }}
  if (!rejected) process.exit(2);
}}
'''
        result = subprocess.run(['node', '--input-type=module', '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_prepare_rejects_unpinned_archive_before_creating_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'bad.tar.gz'
            archive.write_bytes(b'not the pinned archive')
            target = root / 'source'
            result = subprocess.run(['python3', str(FIXTURE / 'prepare.py'), str(archive), str(target)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('source archive SHA256 mismatch', result.stderr)
            self.assertFalse(target.exists())


class WatchContractTests(unittest.TestCase):
    def test_shared_preparation_builds_one_image_and_imports_it_on_the_other_engine(self):
        from unittest.mock import Mock, patch
        import watch_loop
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.tar.gz'
            image = Path(directory) / 'image.tar'
            builder = Mock()
            importer = Mock()
            builder.sh.side_effect = lambda *args, **kwargs: image.write_bytes(b'exported')
            with patch.object(watch_loop, 'prepare_image') as prepare:
                watch_loop.prepare_shared_image(builder, source, image)
                watch_loop.prepare_shared_image(importer, source, image)
            prepare.assert_called_once_with(builder, source, image.parent)
            builder.sh.assert_called_once_with(['image', 'save', '--output', str(image), watch_loop.IMAGE],
                                               timeout=180)
            importer.sh.assert_called_once_with(['image', 'load', '--input', str(image)], timeout=180)

    def test_mounted_probe_reads_current_bytes_and_rejects_symlinks(self):
        script = (FIXTURE / 'mounted-inputs.mjs').read_text()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mounted, app = root / 'source', root / 'app'
            mounted.mkdir()
            (app / 'bin').mkdir(parents=True)
            (mounted / 'Renderer.ts').write_bytes(b'mounted source')
            (app / 'bin' / 'marked.js').write_bytes(b'cli')
            (app / 'package.json').write_bytes(b'package')
            (app / 'package-lock.json').write_bytes(b'lock')

            def probe():
                return subprocess.run(['node', '--input-type=module', '-e', script, str(mounted), str(app)],
                                      capture_output=True, text=True)

            result = probe()
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt['mounted_files'], {'Renderer.ts': hashlib.sha256(b'mounted source').hexdigest()})
            self.assertEqual(receipt['app_files']['package-lock.json'], hashlib.sha256(b'lock').hexdigest())
            (mounted / 'link').symlink_to(app / 'package-lock.json')
            result = probe()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('W5 nonregular input', result.stderr)

    def test_mounted_verification_rejects_wrong_image_mount_and_bytes(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        import watch_loop
        source = {'source_sha256': 'archive', 'files': {'a.ts': 'source', 'package-lock.json': 'lock'}}
        with tempfile.TemporaryDirectory() as directory:
            for mode, field in (('bind', 'Source'), ('volume', 'Name')):
                for fault in (None, 'image', 'mount', 'extra', 'lock'):
                    with self.subTest(mode=mode, fault=fault):
                        state = {'Pid': 2, 'Running': True}
                        mount = {'Destination': '/src', 'Type': mode, field: 'owned', 'RW': True}
                        inspect = {'Image': 'immutable', 'Mounts': [mount], 'State': state}
                        observed = {'mounted_files': dict(source['files']), 'app_files': {'package-lock.json': 'lock'}}
                        match fault:
                            case 'image':
                                inspect['Image'] = 'different'
                            case 'mount':
                                mount[field] = 'different'
                            case 'extra':
                                observed['mounted_files']['extra.ts'] = 'extra'
                            case 'lock':
                                observed['app_files']['package-lock.json'] = 'wrong'
                        engine = Mock()
                        engine.sh.side_effect = [SimpleNamespace(stdout=json.dumps(value))
                                                for value in ([inspect], observed)]
                        args = (engine, 'watcher', mode, 'owned', 'immutable', source, Path(directory))
                        if fault is None:
                            self.assertEqual(watch_loop.verify_mounted_inputs(*args), state)
                        else:
                            with self.assertRaises(ValueError):
                                watch_loop.verify_mounted_inputs(*args)

    def test_host_edit_matches_volume_editor_and_rejects_symlink(self):
        import watch_loop
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / CONTRACT['edit']['path']
            target.parent.mkdir()
            initial = 'prefix\n' + BEFORE + '\nsuffix\n'
            target.write_text(initial)
            watch_loop.edit_source(root, 'edited', CONTRACT)
            self.assertEqual(target.read_text(), 'prefix\n' + AFTER + '\nsuffix\n')
            watch_loop.edit_source(root, 'original', CONTRACT)
            self.assertEqual(target.read_text(), initial)
            external = root / 'external'
            target.rename(external)
            target.symlink_to(external)
            with self.assertRaises(ValueError):
                watch_loop.edit_source(root, 'edited', CONTRACT)
            self.assertEqual(external.read_text(), initial)

    def test_event_requires_expected_state_and_exact_cli_bytes(self):
        import watch_loop
        valid = {'event': 'tested', 'state': 'edited', 'output': CONTRACT['test']['edited']}
        watch_loop.validate_event(valid, 'edited', CONTRACT)
        with self.assertRaises(ValueError):
            watch_loop.validate_event(valid, 'original', CONTRACT)
        with self.assertRaises(ValueError):
            watch_loop.validate_event({**valid, 'output': valid['output'] + '\n'}, 'edited', CONTRACT)

    def test_cleanup_failure_does_not_skip_other_owned_cleanup(self):
        from contextlib import nullcontext
        from types import SimpleNamespace
        import watch_loop
        class Engine:
            name = 'ctrs'
            calls = []
            def sh(self, args, **kwargs):
                self.calls.append(args)
                if args[:2] == ['volume', 'create']:
                    raise RuntimeError('setup interrupted')
                if args[0] == 'inspect':
                    return SimpleNamespace(returncode=0, stdout=json.dumps([{'Config': {'Labels': {'dev.ctrs.campaign.run': 'unrelated'}}}]))
                if args[:2] == ['volume', 'inspect']:
                    return SimpleNamespace(returncode=0, stdout=json.dumps([{'Labels': {'dev.ctrs.campaign.run': 'owned'}}]))
                return SimpleNamespace(returncode=0, stdout='')
        engine = Engine()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'setup interrupted'):
                watch_loop.run_mode(engine, Path(directory), 'volume', 'owned', Path('unused'), 1,
                                    lambda _: nullcontext(), docker_cli='unused', image_id='immutable',
                                    source_receipt={})
            cleanup = json.loads((Path(directory) / 'cleanup.json').read_text())
            self.assertIn('ownership mismatch', cleanup['errors'][0])
        self.assertTrue(any(args[:2] == ['volume', 'rm'] for args in engine.calls))
        self.assertFalse(any(args[0] == 'rm' for args in engine.calls))


if __name__ == '__main__':
    unittest.main()
