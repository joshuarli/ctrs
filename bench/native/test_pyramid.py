import contextlib
import io
import json
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

    def test_warm_w2_cohorts_cover_every_declared_load_cell(self):
        qualified = json.loads((pyramid.HERE / "qualification-cells.json").read_text())
        expected = {cell["load"] for cell in qualified.values()
                    if cell["workload"] == "W2" and cell["state"] == "warm"}
        actual = []
        for workload in self.select("scenario", area=["api"]):
            if workload.tier != "scenario" or "--case" not in workload.argv:
                continue
            argv = workload.argv

            def value(flag):
                return argv[argv.index(flag) + 1]

            if value("--case") != "W2" or workload.design != "paired":
                continue
            location = {"host": "published-port", "guest": "container-to-container"}[value("--client-location")]
            if "--request-rate" in argv:
                self.assertEqual((value("--operations"), value("--request-rate"), value("--concurrency")),
                                 ("10000", "500", "4"))
                actual.append(f"{location}-fixed-offered-rate")
            elif "--operations" in argv:
                self.assertEqual(value("--operations"), "50000")
                actual.append(f"{location}-fixed-work-c{value('--concurrency')}")
            else:
                self.assertEqual(value("--duration"), "20")
                actual.append(f"{location}-saturation-c{value('--concurrency')}")
            self.assertEqual(value("--pairs"), "10")
        self.assertCountEqual(actual, expected)

    def test_w10_targets_keep_shared_engine_interruptions_out_of_cohorts(self):
        by_name = {w.name: w for w in self.items}
        for name, target, guard in (
            ("w10-db-recovery:cohort", "db", "pinned-portfolio"),
            ("w10-queue-recovery:cohort", "queue", "w4-image"),
        ):
            entry = by_name[name]
            self.assertIn("baseline", entry.argv)
            self.assertEqual(entry.argv[entry.argv.index("--interrupt-service") + 1], target)
            self.assertIn(guard, entry.requires)
        owned = by_name["w10-engine-recovery"]
        self.assertNotIn(owned, self.select("scenario"))
        self.assertIn(owned, self.select(name=[owned.name]))
        self.assertIn("run", owned.argv)
        self.assertEqual(owned.argv[owned.argv.index("--engine") + 1], "ctrs")
        self.assertIn("w8-layout", owned.requires)
        self.assertFalse(owned.report)

    def test_w13_cohorts_cover_each_supported_path_direction_and_stream_count(self):
        actual = []
        for entry in self.select("scenario", area=["transfer"]):
            argv = entry.argv
            if entry.tier != "scenario" or argv[argv.index("--case") + 1] != "W13":
                continue
            path = argv[argv.index("--transfer-path") + 1]
            direction = argv[argv.index("--direction") + 1]
            streams = argv[argv.index("--streams") + 1] if "--streams" in argv else "1"
            self.assertEqual(argv[argv.index("--pairs") + 1], "10")
            actual.append((path, direction, streams))
        self.assertCountEqual(actual, [
            (path, direction, streams)
            for path in ("published-port", "container-to-mac", "container-to-container")
            for direction in ("upload", "download")
            for streams in ("1", "4")
        ])

    def test_w8_load_cohort_preserves_the_paired_inputs(self):
        idle, under_load, installed, installed_under_load, *retained = self.select("scenario", area=["pull"])
        self.assertEqual(idle.name, "w8-pull:cohort")
        self.assertEqual(under_load.name, "w8-pull-under-load:cohort")
        self.assertEqual(under_load.argv, (*idle.argv, "--under-load"))
        self.assertEqual(under_load.requires, idle.requires)
        self.assertEqual(installed.name, "w8-pull-installed-default:cohort")
        self.assertEqual(installed.argv, (*idle.argv, "--resource-lane", "installed-default"))
        self.assertEqual(installed_under_load.argv, (*installed.argv, "--under-load"))
        self.assertEqual(len(retained), 4)
        for original, alternative in zip((idle, under_load, installed, installed_under_load), retained, strict=True):
            self.assertEqual(alternative.name, original.name.replace(":cohort", "-retained:cohort"))
            base, switches = original.argv[:original.argv.index("--pairs") + 2], original.argv[original.argv.index("--pairs") + 2:]
            self.assertEqual(alternative.argv, (*base, "--content", "retained", *switches))
            self.assertEqual(alternative.requires, original.requires)


class Entrypoint(unittest.TestCase):
    def main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = pyramid.main(list(argv))
        return code, out.getvalue()

    def test_old_python_fails_before_runtime_preflight(self):
        error = io.StringIO()
        with patch.object(pyramid.sys, "version_info", (3, 9)), \
                patch.object(pyramid, "preflight", side_effect=AssertionError("ran")), \
                contextlib.redirect_stderr(error), self.assertRaises(SystemExit):
            self.main("check", "--name", "w13-overlap:cpus9")
        self.assertIn("native benchmarks require Python 3.11+", error.getvalue())

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
                patch.object(pyramid, "WORK", Path(tmp)), \
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
