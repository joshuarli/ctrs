"""W8 preparation preserves the other engine and existing valid metadata."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import runner


class PortfolioTests(unittest.TestCase):
    def test_one_engine_update_preserves_other_exact_section(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'portfolio.json'
            original = {'ctrs': {'old': 'discard'}, 'orbstack': {'pinned': {'digest': 'sha256:keep'}}}
            path.write_text(json.dumps(original))
            with patch.object(runner, 'PORTFOLIO_FILE', path):
                runner.save_w8_portfolio({'ctrs': {'new': {'digest': 'sha256:new'}}})
            result = json.loads(path.read_text())
            self.assertEqual(result['orbstack'], original['orbstack'])
            self.assertEqual(result['ctrs'], {'new': {'digest': 'sha256:new'}})

    def test_invalid_existing_state_is_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'portfolio.json'
            path.write_text('{broken')
            with patch.object(runner, 'PORTFOLIO_FILE', path):
                with self.assertRaises(json.JSONDecodeError):
                    runner.save_w8_portfolio({'ctrs': {}})
            self.assertEqual(path.read_text(), '{broken')

    def test_failed_replace_preserves_both_sections_and_removes_scratch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'portfolio.json'
            path.write_text('{"ctrs":{},"orbstack":{"digest":"keep"}}')
            original = path.read_bytes()
            with patch.object(runner, 'PORTFOLIO_FILE', path), \
                    patch.object(runner.os, 'replace', side_effect=OSError('rename failed')):
                with self.assertRaises(OSError):
                    runner.save_w8_portfolio({'ctrs': {'new': True}})
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_symlink_does_not_modify_target(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'other.json'
            target.write_text('{}')
            path = Path(directory) / 'portfolio.json'
            path.symlink_to(target)
            with patch.object(runner, 'PORTFOLIO_FILE', path):
                with self.assertRaises(ValueError):
                    runner.save_w8_portfolio({'ctrs': {}})
            self.assertEqual(target.read_text(), '{}')
