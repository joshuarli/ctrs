import pathlib
import subprocess
import unittest


class ConformanceRunnerTest(unittest.TestCase):
    def test_unknown_selector_fails(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        result = subprocess.run(
            ["bash", "conformance/run.sh", "__no_such_fixture__"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("0 fixtures", result.stdout)
