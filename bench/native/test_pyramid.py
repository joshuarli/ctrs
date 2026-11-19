import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pyramid


def names(items):
    return [w.name for w in items]


class Selection(unittest.TestCase):
    def setUp(self):
        self.items = pyramid.registry()

    def select(self, tier=None, name=(), area=(), skip=()):
        with contextlib.redirect_stdout(io.StringIO()):
            return pyramid.select(self.items, tier, list(name), list(area), list(skip))

    def test_tier_is_a_ceiling(self):
        self.assertEqual({w.tier for w in self.select("edit")}, {"edit"})
        self.assertEqual({w.tier for w in self.select("change")}, {"edit", "change"})
        self.assertEqual({w.tier for w in self.select("scenario")}, {"edit", "change", "scenario"})

    def test_a_full_ceiling_never_selects_full_workloads(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            chosen = pyramid.select(self.items, "full", [], [], [])
        self.assertNotIn("full", {w.tier for w in chosen})
        self.assertIn("holdout", out.getvalue())

    def test_full_workloads_run_only_by_name(self):
        self.assertEqual(names(self.select("full", name=["holdout"])), ["holdout"])
        self.assertEqual(names(self.select(name=["holdout"])), ["holdout"])

    def test_names_and_areas_are_distinct_selectors(self):
        self.assertEqual(names(self.select(name=["w14-fresh"])), ["w14-fresh"])
        by_area = self.select("change", area=["connections"])
        self.assertTrue(by_area and all(w.area == "connections" and w.tier == "change" for w in by_area))
        with self.assertRaises(SystemExit):
            self.select("change", area=["w14-fresh"])
        with self.assertRaises(SystemExit):
            self.select("change", name=["connections"])

    def test_a_named_workload_above_the_ceiling_is_an_error(self):
        with self.assertRaises(SystemExit):
            self.select("edit", name=["w14-fresh:cohort"])

    def test_unknown_and_empty_selections_are_errors(self):
        with self.assertRaises(SystemExit):
            self.select("change", name=["nope"])
        with self.assertRaises(SystemExit):
            self.select("change", skip=["nope"])
        with self.assertRaises(SystemExit):
            self.select("edit", area=["harness"], skip=["harness-tests", "manifest"])
        with self.assertRaises(SystemExit):
            self.select()

    def test_skip_removes_a_workload(self):
        self.assertEqual(names(self.select("edit", skip=["manifest"])), ["harness-tests"])


class Entrypoint(unittest.TestCase):
    def main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = pyramid.main(list(argv))
        return code, out.getvalue()

    def test_unmet_requirement_stops_the_run_before_anything_starts(self):
        def check(key):
            return ("fail", "OrbStack socket missing; start OrbStack") if key == "orbstack" else ("ok", "")
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(pyramid, "OUT", Path(tmp) / "runs"), \
                patch.object(pyramid, "check_requirement", side_effect=check), \
                patch.object(pyramid.subprocess, "run", side_effect=AssertionError("ran")):
            code, out = self.main("run", "--name", "w14-fresh")
            self.assertFalse((Path(tmp) / "runs").exists())
        self.assertEqual(code, 1)
        self.assertIn("fail  orbstack [w14-fresh]: OrbStack socket missing", out)
        self.assertIn("nothing ran", out)

    def test_manual_workloads_fail_preflight(self):
        with patch.object(pyramid, "check_requirement", return_value=("ok", "")):
            code, out = self.main("check", "--name", "w11-soak")
        self.assertEqual(code, 1)
        self.assertIn("durable-job.md", out)

    def test_dry_run_prints_the_plan_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(pyramid, "OUT", Path(tmp) / "runs"), \
                patch.object(pyramid, "check_requirement", return_value=("ok", "")), \
                patch.object(pyramid.subprocess, "run", side_effect=AssertionError("ran")):
            code, out = self.main("run", "--tier", "change", "--area", "connections", "--dry-run")
            self.assertEqual(os.listdir(tmp), [])
        self.assertEqual(code, 0)
        self.assertIn("--lifecycle-mode reconnect", out)
        self.assertIn("plan: 6 workloads", out)

    def test_run_reports_failures_and_a_missing_result(self):
        class Done:
            def __init__(self, code):
                self.returncode = code
        calls = iter([Done(0), Done(3)])
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(pyramid, "OUT", Path(tmp) / "runs"), \
                patch.object(pyramid, "check_requirement", return_value=("ok", "")), \
                patch.object(pyramid, "_git", return_value={"head": "0" * 40, "dirty": False}), \
                patch.object(pyramid.subprocess, "run", side_effect=lambda *a, **k: next(calls)):
            code, out = self.main("run", "--name", "manifest", "--name", "w14-fresh")
            summary = next((Path(tmp) / "runs").iterdir()) / "summary.md"
            text = summary.read_text()
        self.assertEqual(code, 1)
        self.assertIn("| manifest | edit | ok |", text)
        self.assertIn("| w14-fresh | change | failed (no results line in the log) |", text)


if __name__ == "__main__":
    unittest.main()
