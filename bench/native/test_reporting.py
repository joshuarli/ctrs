"""Adversarial reporting checks; standard library, no Docker or macOS needed."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import reporting


def pair(pair_id=1, ratio=0.8, run_id="run-a", case="W1", metric="wall_seconds"):
    records = []
    for order, engine in enumerate(("ctrs", "orbstack")):
        records.append({
            "schema": 1, "trial_id": f"{run_id}-{pair_id}-{engine}",
            "run_id": run_id, "pair_id": pair_id, "order_index": order,
            "host_id": "mac-a", "arch": "arm64", "git_sha": "commit-a",
            "case": case, "state": "warm", "engine": engine,
            "engine_server_version": "ctrs-v1" if engine == "ctrs" else "orb-v1",
            "workload_params": {"duration": 20, "seed": pair_id},
            "workload_id": f"{run_id}-{pair_id}",
            "provenance": {"runner_sha256": "runner-a", "assets_sha256": "assets-a"},
            "evidence_status": "pilot",
            "metrics": {metric: ratio if engine == "ctrs" else 1.0},
            "resources": {"engine": {"ncpu": 8, "mem_total_bytes": 8 << 30}},
            "correctness": {"ok": True, "checks": {"output_exact": True}},
            "validation_errors": [],
        })
    return records


def noise_pair(pair_id=1, ratio=1.0, run_id="noise-a", case="W1",
               metric="wall_seconds", engine="ctrs"):
    records = []
    for order, (slot, value) in enumerate((("a", ratio), ("b", 1.0))):
        records.append({
            "schema": 1, "trial_id": f"{run_id}-{pair_id}-{slot}",
            "run_id": run_id, "pair_id": pair_id, "order_index": order,
            "slot": slot, "design": "noise-control",
            "host_id": "mac-a", "arch": "arm64", "git_sha": "commit-a",
            "case": case, "state": "warm", "engine": engine,
            "engine_server_version": "ctrs-v1",
            "workload_params": {"duration": 20, "seed": pair_id},
            "workload_id": f"{run_id}-{pair_id}",
            "provenance": {"runner_sha256": "runner-a", "assets_sha256": "assets-a"},
            "evidence_status": "pilot",
            "metrics": {metric: value},
            "resources": {"engine": {"ncpu": 8, "mem_total_bytes": 8 << 30}},
            "correctness": {"ok": True, "checks": {"output_exact": True}},
            "validation_errors": [],
        })
    return records


def metric_result(report, metric="wall_seconds", cohort=0):
    return next(m for m in report["cohorts"][cohort]["metrics"] if m["metric"] == metric)


class ReportingTests(unittest.TestCase):
    def test_legacy_w8_without_parameters_is_historical_and_does_not_crash(self):
        records = pair(case='W8', metric='pull_wall_seconds')
        for record in records:
            record.pop('workload_params')
        report = reporting.analyze(records)
        self.assertIn('workload_params', report['cohorts'][0]['metadata_gaps'])
        self.assertTrue(all(m['assessment'] == 'historical-only' for m in report['cohorts'][0]['metrics']))

    def test_partial_provenance_and_empty_parameters_expose_missing_metadata(self):
        records = pair()
        for record in records:
            record["workload_params"] = {}
            record["provenance"] = {"ctrs_binary_sha256": None,
                                    "runner_sha256": "a" * 64}
        report = reporting.analyze(records)
        gaps = report["cohorts"][0]["metadata_gaps"]
        self.assertIn("workload_params", gaps)
        self.assertIn("provenance.ctrs_binary_sha256", gaps)
        self.assertIn("provenance.assets_sha256", gaps)
        self.assertNotIn("provenance.runner_sha256", gaps)
        self.assertFalse(report["promotion_eligible"])

    def test_run_ids_never_pool_or_cross_pair(self):
        records = pair(run_id="run-a", ratio=0.5) + pair(run_id="run-b", ratio=2.0)
        report = reporting.analyze(records)
        self.assertEqual(len(report["cohorts"]), 2)
        self.assertEqual([metric_result(report, cohort=i)["ratio_median"] for i in range(2)], [0.5, 2.0])
        halves = [records[0], records[3]]
        self.assertTrue(all(c["valid_pairs"] == 0 for c in reporting.analyze(halves)["cohorts"]))

    def test_revision_host_params_driver_and_assets_split_cohorts(self):
        for field in ("git_sha", "host_id", "state", "workload_params", "provenance", "metrics"):
            with self.subTest(field=field):
                records = pair()
                if field == "workload_params":
                    records[1][field]["duration"] = 40
                elif field == "provenance":
                    records[1][field]["assets_sha256"] = "assets-b"
                elif field == "metrics":
                    records[1][field]["builder_driver"] = "dc"
                else:
                    records[1][field] += "-different"
                report = reporting.analyze(records)
                self.assertEqual(len(report["cohorts"]), 2)
                self.assertTrue(all(c["valid_pairs"] == 0 for c in report["cohorts"]))

    def test_seed_varies_between_pairs_but_matches_within_pair(self):
        records = [r for n in range(1, 11) for r in pair(n)]
        report = reporting.analyze(records)
        self.assertEqual(len(report["cohorts"]), 1)
        self.assertEqual(metric_result(report)["valid_pairs"], 10)
        self.assertEqual(metric_result(report)["assessment"], "strict-win")
        records[1]["workload_params"]["seed"] = 99
        report = reporting.analyze(records)
        self.assertEqual(metric_result(report)["valid_pairs"], 9)
        self.assertEqual(metric_result(report)["assessment"], "invalid")
        self.assertIn("seeds", report["cohorts"][0]["rejections"][0]["reason"])

    def test_duplicate_engine_record_is_rejected_not_overwritten(self):
        records = pair()
        records.append(copy.deepcopy(records[0]))
        report = reporting.analyze(records)
        self.assertEqual(report["cohorts"][0]["valid_pairs"], 0)
        self.assertIn("duplicate", report["cohorts"][0]["rejections"][0]["reason"])

    def test_failed_trial_and_explicit_failed_check_cannot_be_speed_wins(self):
        for failure in ("aggregate", "check", "validation"):
            records = [r for n in range(1, 12) for r in pair(n)]
            if failure == "aggregate":
                records[0]["correctness"]["ok"] = False
            elif failure == "check":
                records[0]["correctness"]["checks"]["output_exact"] = {"ok": False}
            else:
                records[0]["validation_errors"] = ["missing load summary"]
            report = reporting.analyze(records)
            self.assertEqual(metric_result(report)["valid_pairs"], 10)
            self.assertEqual(metric_result(report)["assessment"], "failed")
            self.assertEqual(report["cohorts"][0]["engines"]["ctrs"]["failed"], 1)

    def test_missing_resources_remain_unmeasured(self):
        report = reporting.analyze(pair())
        result = metric_result(report, "peak_total_rss_kb")
        self.assertIsNone(result["ratio_median"])
        self.assertEqual(result["assessment"], "unmeasured")
        self.assertEqual(result["missing_pairs"], [1])

    def test_nonfinite_and_zero_metrics_are_not_ratios(self):
        for bad in (None, 0, float("nan"), float("inf"), "0.1", True):
            records = pair()
            records[0]["metrics"]["wall_seconds"] = bad
            result = metric_result(reporting.analyze(records))
            self.assertIsNone(result["ratio_median"])
            self.assertEqual(result["assessment"], "unmeasured")

    def test_median_bootstrap_does_not_estimate_mean(self):
        # A mean bootstrap would react heavily to the final outlier. Nine of
        # ten paired ratios remain exactly one, so the median CI remains one.
        low, high = reporting.bootstrap_ci([1.0] * 9 + [100.0])
        self.assertEqual((low, high), (1.0, 1.0))

    def test_thresholds_and_minimum_replication(self):
        self.assertEqual(reporting.classify(9, 0.5, 0.6), "pilot")
        self.assertEqual(reporting.classify(10, 0.9, 0.95), "strict-win")
        self.assertEqual(reporting.classify(10, 0.95, 0.977), "non-inferior")
        self.assertEqual(reporting.classify(10, 0.93, 1.03), "non-inferior")
        self.assertEqual(reporting.classify(10, 1.031, 1.05), "loss")
        self.assertEqual(reporting.classify(10, 0.457, 1.237), "inconclusive")

    def test_version_drift_and_budget_mismatch_reject_pairs(self):
        records = pair(1) + pair(2)
        records[3]["engine_server_version"] = "orb-v2"
        self.assertEqual(reporting.analyze(records)["cohorts"][0]["valid_pairs"], 0)
        records = pair()
        records[1]["resources"]["engine"]["ncpu"] = 16
        self.assertEqual(reporting.analyze(records)["cohorts"][0]["valid_pairs"], 0)

    def test_holdout_and_soak_counts_never_score(self):
        records = pair(case="W11", metric="requests") + pair(case="HOLDOUT", metric="ops_per_s")
        report = reporting.analyze(records)
        self.assertEqual(report["holdout_excluded"], 2)
        self.assertEqual(report["cohorts"][0]["metrics"], [])

    def test_recovery_does_not_score_attempt_throughput(self):
        records = pair(case="W10", metric="recovery_s")
        for record in records:
            record["metrics"]["load_rps"] = 100000
        metrics = reporting.analyze(records)["cohorts"][0]["metrics"]
        self.assertNotIn("load_rps", [m["metric"] for m in metrics])

    def test_empty_cache_history_not_equated_with_uncached_build(self):
        records = pair(case="W7", metric="build_empty_s")
        report = reporting.analyze(records)
        self.assertEqual(metric_result(report, "build_empty_s")["assessment"], "historical-only")
        self.assertEqual(metric_result(report, "httpie_uncached_s")["assessment"], "unmeasured")

    def test_truncated_json_is_visible_and_fails_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trials.jsonl"
            path.write_text(json.dumps(pair()[0]) + '\n{"partial":\n')
            records, issues = reporting.load_records([path])
        report = reporting.analyze(records, issues)
        self.assertEqual(len(issues), 1)
        self.assertTrue(reporting.invalid_report(report))
        self.assertIn("invalid JSON", reporting.render_markdown(report))

    def test_noise_records_never_enter_cross_engine_scoring(self):
        records = [r for n in range(1, 4) for r in noise_pair(n)]
        report = reporting.analyze(records)
        self.assertEqual(report["noise_excluded"], 6)
        self.assertEqual(report["cohorts"], [])
        self.assertIn("Noise-control records excluded",
                      reporting.render_markdown(report))

    def test_noise_report_pairs_slots_and_stays_descriptive(self):
        records = [r for n in range(1, 11) for r in noise_pair(n, ratio=1.04)]
        report = reporting.analyze_noise(records)
        self.assertEqual(len(report["cohorts"]), 1)
        cohort = report["cohorts"][0]
        self.assertEqual(cohort["valid_pairs"], 10)
        self.assertFalse(report["promotion_eligible"])
        self.assertEqual(report["evidence_status"], "pilot")
        result = metric_result(report)
        self.assertAlmostEqual(result["ratio_median"], 1.04)
        self.assertIn("noise", reporting.render_noise_markdown(report).lower())
        # Cross-engine scoring skips the same records entirely.
        self.assertEqual(reporting.analyze(records)["cohorts"], [])

    def test_noise_pair_requires_both_slots_and_one_engine(self):
        records = noise_pair()
        records[1]["slot"] = "a"
        cohort = reporting.analyze_noise(records)["cohorts"][0]
        self.assertEqual(cohort["valid_pairs"], 0)
        self.assertIn("duplicate", cohort["rejections"][0]["reason"])
        records = noise_pair()
        records[1]["engine"] = "orbstack"
        cohort = reporting.analyze_noise(records)["cohorts"][0]
        self.assertEqual(cohort["valid_pairs"], 0)
        self.assertIn("different engines", cohort["rejections"][0]["reason"])

    def test_noise_record_without_slot_is_input_issue(self):
        records = noise_pair()
        del records[0]["slot"]
        report = reporting.analyze_noise(records)
        self.assertTrue(report["input_issues"])
        self.assertTrue(reporting.invalid_noise_report(report))

    def test_even_large_winning_cohort_remains_unqualified_pilot(self):
        report = reporting.analyze([r for n in range(1, 11) for r in pair(n)])
        self.assertFalse(report["promotion_eligible"])
        self.assertEqual(report["evidence_status"], "pilot")
        self.assertFalse(metric_result(report)["promotion_eligible"])


if __name__ == "__main__":
    unittest.main()


class NormalizedW2Tests(unittest.TestCase):
    def test_efficiency_uses_raw_normalized_metric_and_omits_total_cpu(self):
        rows = pair(case="W2", metric="cpu_seconds_per_success", ratio=0.001)
        for row, cpu in zip(rows, (12, 10)):
            row["resources"]["phases"] = {"workload": {"cpu_seconds": cpu, "errors": []}}
            row["metrics"].update(requests_ok=100, reads_ok=70, writes_ok=30, errors=0)
        rows[0]["resources"]["cpu_seconds_est"] = .1
        rows[1]["resources"]["cpu_seconds_est"] = 100
        report = reporting.analyze(rows)
        metrics = {m["metric"]: m for m in report["cohorts"][0]["metrics"]}
        self.assertEqual(metrics["cpu_seconds_per_success"]["ratio_median"], 1.2)
        self.assertNotIn("cpu_seconds_est", metrics)

        for mutate in (
            lambda r: r["resources"].pop("phases"),
            lambda r: r["resources"]["phases"]["workload"].update(errors=["missing VM"]),
            lambda r: r["metrics"].update(requests_ok=99),
            lambda r: r["metrics"].update(errors=1),
            lambda r: r["metrics"].update(requests_ok=101, reads_ok=71),
        ):
            bad = copy.deepcopy(rows)
            mutate(bad[0])
            result = metric_result(reporting.analyze(bad), "cpu_seconds_per_success")
            self.assertIsNone(result["ratio_median"])
            self.assertTrue(result["missing_reasons"])

    def test_resource_coverage_and_noise_reporting(self):
        rows = [r for n in range(1, 11) for r in pair(n)]
        for row in rows:
            row["resources"].update(peak_phys_footprint_bytes=100, cpu_seconds_est=10,
                                    peak_total_rss_kb=20, ownership_verified=True,
                                    resource_errors=[], footprint_field="phys_footprint",
                                    cpu_counters_complete=True)
        rows[0]["resources"].update(peak_phys_footprint_bytes=.01, ownership_verified=False,
                                    resource_errors=["missing VM"])
        rows[2]["resources"]["footprint_field"] = "category_table"
        rows[4]["resources"]["cpu_counters_complete"] = False
        report = reporting.analyze(rows)
        for name in ("peak_phys_footprint_bytes", "cpu_seconds_est"):
            result = metric_result(report, name)
            self.assertIsNone(result["ratio_median"])
            self.assertTrue(result["missing_reasons"])
            self.assertIn(name, reporting.render_markdown(report))
        self.assertEqual(metric_result(report)["valid_pairs"], 10)
        self.assertEqual(metric_result(report, "peak_total_rss_kb")["valid_pairs"], 10)
        good = reporting.analyze(rows[6:])
        self.assertEqual(metric_result(good, "peak_phys_footprint_bytes")["ratio_median"], 1)
        self.assertEqual(metric_result(good, "cpu_seconds_est")["ratio_median"], 1)
        for updates, name, reason in (
            ({"ownership_verified": False, "resource_errors": ["missing VM"]}, "peak_phys_footprint_bytes", "missing VM"),
            ({"footprint_field": "category_table"}, "peak_phys_footprint_bytes", "footprint field"),
            ({"cpu_counters_complete": False}, "cpu_seconds_est", "CPU counters"),
        ):
            bad = copy.deepcopy(rows[6:8])
            bad[0]["resources"].update(updates)
            result = metric_result(reporting.analyze(bad), name)
            self.assertIsNone(result["ratio_median"])
            self.assertIn(reason, result["missing_reasons"][0]["reason"])
        legacy = pair()
        for row in legacy:
            row["resources"].update(peak_phys_footprint_bytes=100, cpu_seconds_est=10)
        for name in ("peak_phys_footprint_bytes", "cpu_seconds_est"):
            result = metric_result(reporting.analyze(legacy), name)
            self.assertEqual(result["assessment"], "unmeasured")
            self.assertIsNone(result["ratio_median"])
        noise = noise_pair()
        for row in noise:
            row["resources"].update(rows[0]["resources"])
        result = metric_result(reporting.analyze_noise(noise), "peak_phys_footprint_bytes")
        self.assertIsNone(result["ratio_median"])
        self.assertIn("missing VM", reporting.render_noise_markdown(reporting.analyze_noise(noise)))


class InvalidMeasurementTests(unittest.TestCase):
    def test_contaminated_pair_retains_correctness_but_has_no_ratios(self):
        rows = pair(case="W2", metric="cpu_seconds_per_success")
        rows[0].update(measurement_valid=False, measurement_invalidation="host busy")
        cohort = reporting.analyze(rows)["cohorts"][0]
        self.assertEqual(cohort["valid_pairs"], 0)
        self.assertEqual(cohort["engines"]["ctrs"]["correct"], 1)
        self.assertIn("host busy", cohort["rejections"][0]["reason"])
        self.assertTrue(all(m["ratio_median"] is None for m in cohort["metrics"]))
