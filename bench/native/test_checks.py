"""Contract tests for the bounded component check command."""

import contextlib
import io
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

import runner


class ComponentCheckTests(unittest.TestCase):
    def completed(self, returncode=0, stdout="", stderr="Ran 3 tests in 0.01s\n\nOK\n"):
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    def test_component_runs_exact_nonempty_native_selection_without_full_path(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            return self.completed()

        with mock.patch.object(sys, "argv", ["runner.py", "check", "w2"]), \
             mock.patch.object(runner, "cmd_baseline",
                               side_effect=AssertionError("Full path reached")), \
             mock.patch("sys.stdout", new_callable=io.StringIO):
            with mock.patch.object(runner.subprocess, "run", side_effect=fake_run):
                self.assertEqual(runner.main(), 0)

        self.assertEqual(len(calls), 1)
        command, kwargs = calls[0]
        self.assertTrue(command[4:])
        self.assertEqual(command, [sys.executable, "-m", "unittest", "-v",
                                   "test_w2", "test_mixed_cycle", "test_safety"])
        self.assertEqual(kwargs["cwd"], runner.BENCH)
        self.assertEqual(kwargs["timeout"], runner.CHECK_TIMEOUT_SECONDS)
        self.assertFalse(kwargs["check"])

    def test_missing_and_full_component_are_rejected_without_running_tests(self):
        for argv in (["runner.py", "check"], ["runner.py", "check", "full"]):
            stderr = io.StringIO()
            with self.subTest(argv=argv), \
                 mock.patch.object(sys, "argv", argv), \
                 mock.patch.object(runner.subprocess, "run",
                                   side_effect=AssertionError("tests unexpectedly ran")), \
                 contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    runner.main()
            self.assertEqual(raised.exception.code, 2)
            self.assertIn("usage:", stderr.getvalue())

    def test_nonzero_test_exit_cannot_pass(self):
        result = self.completed(returncode=1,
                                stderr="Ran 1 test in 0.01s\n\nFAILED (failures=1)\n")
        self.assertEqual(runner.run_component_check("w2", run=lambda *a, **k: result), 1)

    def test_import_or_discovery_error_cannot_pass(self):
        result = self.completed(returncode=1,
                                stderr="ImportError: Failed to import test module\n")
        self.assertEqual(runner.run_component_check("w2", run=lambda *a, **k: result), 1)

    def test_required_skip_cannot_pass(self):
        result = self.completed(stderr="Ran 2 tests in 0.01s\n\nOK (skipped=1)\n")
        self.assertEqual(runner.run_component_check("w2", run=lambda *a, **k: result), 1)

    def test_zero_match_cannot_pass(self):
        result = self.completed(stderr="Ran 0 tests in 0.00s\n\nOK\n")
        self.assertEqual(runner.run_component_check("w2", run=lambda *a, **k: result), 1)

    def test_timeout_cannot_pass(self):
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

        self.assertEqual(runner.run_component_check("w2", timeout=1, run=timeout), 1)


if __name__ == "__main__":
    unittest.main()
