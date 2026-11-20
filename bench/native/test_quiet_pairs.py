import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import runner


class QuietPairs(unittest.TestCase):
    def wait(self, loads, timeout=100, hold=False):
        now = [0.0]
        sleeps = []
        loads = iter(loads)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hold"
            if hold:
                path.write_text("")
            with patch.object(runner, "HOLD", path):
                def sleep(seconds):
                    sleeps.append(seconds)
                    now[0] += seconds
                    if hold and len(sleeps) == 2:
                        path.unlink()
                runner.wait_for_quiet_host(4.0, timeout, clock=lambda: now[0], sleep=sleep,
                                           loadavg=lambda: (next(loads), 0, 0))
        return sleeps

    def test_a_quiet_host_starts_the_pair_at_once(self):
        self.assertEqual(self.wait([1.0]), [])

    def test_a_busy_host_holds_the_pair_until_load_falls(self):
        self.assertEqual(len(self.wait([12.0, 6.0, 3.9])), 2)

    def test_a_hold_file_holds_the_pair(self):
        self.assertEqual(len(self.wait([1.0, 1.0, 1.0], hold=True)), 2)

    def test_a_host_that_never_quiets_fails_the_run(self):
        with self.assertRaisesRegex(RuntimeError, "not quiet"):
            self.wait([9.0] * 20, timeout=60)


if __name__ == "__main__":
    unittest.main()
