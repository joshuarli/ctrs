import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import runner


class QuietPairs(unittest.TestCase):
    def wait(self, loads, timeout=100, hold=False, busy=None, holder=None):
        busy = iter(busy or [0.5] * 50)
        now = [0.0]
        sleeps = []
        loads = iter(loads)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hold"
            holds = Path(tmp) / "holds"
            if hold:
                path.write_text("")
            if holder:
                holds.mkdir()
                (holds / holder).write_text("")
            with patch.object(runner, "HOLD", path), patch.object(runner, "HOLDS", holds):
                def sleep(seconds):
                    sleeps.append(seconds)
                    now[0] += seconds
                    if len(sleeps) == 2:
                        path.unlink(missing_ok=True)
                        if holder:
                            (holds / holder).unlink()
                runner.wait_for_quiet_host(4.0, timeout, clock=lambda: now[0], sleep=sleep,
                                           loadavg=lambda: (next(loads), 0, 0), busy=lambda: next(busy))
        return sleeps

    def test_a_quiet_host_starts_the_pair_at_once(self):
        self.assertEqual(self.wait([1.0]), [])

    def test_a_busy_host_holds_the_pair_until_load_falls(self):
        self.assertEqual(len(self.wait([12.0, 6.0, 3.9])), 2)

    def test_a_hold_file_holds_the_pair(self):
        self.assertEqual(len(self.wait([1.0, 1.0, 1.0], hold=True)), 2)

    def test_any_named_holder_holds_the_pair(self):
        self.assertEqual(len(self.wait([1.0, 1.0, 1.0], holder="watcher-build")), 2)

    def test_busy_cores_hold_the_pair_even_at_low_load(self):
        self.assertEqual(len(self.wait([1.0, 1.0, 1.0], busy=[3.0, 2.5, 1.0])), 2)

    def test_a_host_that_never_quiets_fails_the_run(self):
        with self.assertRaisesRegex(RuntimeError, "not quiet"):
            self.wait([9.0] * 20, timeout=60)


class ForeignCpu(unittest.TestCase):
    def test_outside_cpu_excludes_the_engine_and_harness(self):
        with patch.object(runner.os, "cpu_count", return_value=10):
            got = runner.foreign_cpu([0, 0, 0, 0], [400, 100, 500, 0], 2.0, 7.0, engine_cpu=30.0, wall=10.0)
        self.assertAlmostEqual(got["host_busy_cores"], 5.0)
        self.assertAlmostEqual(got["foreign_cpu_cores"], 1.5)

    def test_an_unmeasured_engine_leaves_outside_cpu_unknown(self):
        got = runner.foreign_cpu([0, 0, 0, 0], [1, 0, 1, 0], 0.0, 0.0, engine_cpu=None, wall=1.0)
        self.assertIsNone(got["foreign_cpu_cores"])


if __name__ == "__main__":
    unittest.main()
