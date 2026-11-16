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
                                    lambda _: nullcontext(), docker_cli='unused')
            cleanup = json.loads((Path(directory) / 'cleanup.json').read_text())
            self.assertIn('ownership mismatch', cleanup['errors'][0])
        self.assertTrue(any(args[:2] == ['volume', 'rm'] for args in engine.calls))
        self.assertFalse(any(args[0] == 'rm' for args in engine.calls))


if __name__ == '__main__':
    unittest.main()
