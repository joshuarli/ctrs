from pathlib import Path
import subprocess
import tempfile
import unittest

FIXTURE = Path(__file__).parent / 'fixtures/w5-v2'
EDIT = FIXTURE / 'edit.mjs'
VERIFY = (FIXTURE / 'verify.mjs').resolve().as_uri()
BEFORE = 'return `<h${depth}>${this.parser.parseInline(tokens)}</h${depth}>\\n`;'
AFTER = 'return `<h${depth} class="w5">${this.parser.parseInline(tokens)}</h${depth}>\\n`;'


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


if __name__ == '__main__':
    unittest.main()
