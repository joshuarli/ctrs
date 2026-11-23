import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
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
    def test_macos_phase_preserves_raw_host_tick_boundaries(self):
        engine = SimpleNamespace(measurement_identity={})
        record = {"resources": {}}
        ticks_before = [10, 20, 30, 0]
        ticks_after = [20, 30, 50, 0]
        with (
            patch.object(runner.linux_lane, "enabled", return_value=False),
            patch("macos_counters.host_cpu_ticks", side_effect=[ticks_before, ticks_after]),
            patch.object(runner.time, "monotonic", side_effect=[1, 2, 3, 4, 5, 6]),
            patch.object(runner.os, "cpu_count", return_value=10),
            patch.object(runner, "harness_cpu_seconds", side_effect=[0, 1]),
            patch.object(runner.collect, "cpu_boundary"),
            patch.object(runner.collect, "cpu_delta", return_value={"cpu_seconds": 2}),
            runner.resource_phase(engine, record, "work"),
        ):
            pass

        phase = record["resources"]["phases"]["work"]
        self.assertEqual(phase["host_cpu_tick_samples"], {
            "before": {"ticks": ticks_before, "started_monotonic": 1, "ended_monotonic": 2},
            "after": {"ticks": ticks_after, "started_monotonic": 5, "ended_monotonic": 6},
        })
        self.assertEqual((phase["operation_started_monotonic"], phase["operation_ended_monotonic"]), (3, 4))
        self.assertEqual(phase["host_busy_cores"], 5)
        self.assertEqual(phase["foreign_cpu_cores"], 2)

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


class CpuAccounting(unittest.TestCase):
    def test_nat_connections_make_cpu_incomplete_and_scalars_are_ignored(self):
        before = {"published": {"nat_leg": 2, "vsock": 5}, "host_bound": {"nat": 0}, "active": 3}
        after = {"published": {"nat_leg": 4, "vsock": 9}, "host_bound": {"nat": 1}, "active": 1}
        self.assertEqual(runner.cpu_accounting(before, after)["nat_connections"], 3)
        self.assertFalse(runner.cpu_accounting(before, after)["complete"])
        self.assertTrue(runner.cpu_accounting(after, after)["complete"])
        self.assertIsNone(runner.cpu_accounting(before, None)["complete"])

    def test_opt_in_vmnet_marks_published_port_cpu_incomplete(self):
        before = {"published": {"nat_leg": 2, "vmnet": 3, "vsock": 5}}
        after = {"published": {"nat_leg": 2, "vmnet": 5, "vsock": 6}}
        accounting = runner.cpu_accounting(before, after)
        self.assertFalse(accounting["complete"])
        self.assertEqual(accounting["nat_connections"], 2)
