"""Adversarial reporting checks; standard library, no Docker or macOS needed."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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
    def test_pinned_w2_requires_matching_input_receipts(self):
        records = pair(case="W2")
        for record in records:
            record["workload_params"]["pinned_stack"] = True
            record["paired_inputs"] = {"portfolio_sha256": "same", "seed_sha256": "same"}
        self.assertEqual(reporting.analyze(records)["cohorts"][0]["valid_pairs"], 1)
        for receipt in ({"portfolio_sha256": "different", "seed_sha256": "same"}, {}):
            records[1]["paired_inputs"] = receipt
            result = reporting.analyze(records)["cohorts"][0]
            self.assertEqual(result["valid_pairs"], 0)
            self.assertEqual(result["rejections"][0]["reason"], "paired inputs differ or are missing")

    def test_w5_receipts_require_equal_observed_inputs_for_pairing(self):
        records = pair(case='W5', metric='bind_edit_to_result_median_s')
        for record in records:
            record['workload_params']['fixture_version'] = reporting.W5_RECEIPT_VERSION
            record['paired_inputs'] = {'layers': ['same'], 'tools': {'esbuild': 'same'},
                                       'source_sha256': 'same', 'dependency_lock_sha256': 'same'}
        self.assertEqual(reporting.analyze(records)['cohorts'][0]['valid_pairs'], 1)
        records[1]['paired_inputs']['layers'] = ['changed']
        result = reporting.analyze(records)['cohorts'][0]
        self.assertEqual(result['valid_pairs'], 0)
        self.assertEqual(result['rejections'][0]['reason'], 'paired inputs differ or are missing')

    def test_w9_throughput_and_completion_latency_use_opposite_ratio_directions(self):
        duration = "job_completion_p95_ms_at_4"
        rate = "successful_jobs_per_minute_at_4"
        records = pair(case="W9", metric=duration, ratio=.5)
        records[0]["metrics"][rate] = 120
        records[1]["metrics"][rate] = 60
        report = reporting.analyze(records)
        self.assertEqual(metric_result(report, duration)["ratio_median"], .5)
        self.assertEqual(metric_result(report, rate)["ratio_median"], .5)

    def test_w3_v4_rate_and_latency_directions(self):
        records = pair(case="W3-v4", metric="rw_p99_ms", ratio=.5)
        for metric in ("rw_tps", "ro_tps"):
            records[0]["metrics"][metric] = 120
            records[1]["metrics"][metric] = 60
        report = reporting.analyze(records)
        for metric in ("rw_p99_ms", "rw_tps", "ro_tps"):
            self.assertEqual(metric_result(report, metric)["ratio_median"], .5)

    def test_overlap_metric_directions_and_paired_inputs(self):
        records = pair(case="W13-overlap", metric="w2_latency_p99_ms", ratio=.5)
        for record in records:
            record["paired_inputs"] = {"seed": "same"}
        for metric in ("w2_rps", "transfer_goodput_bytes_per_second"):
            records[0]["metrics"][metric] = 2
            records[1]["metrics"][metric] = 1
        report = reporting.analyze(records)
        for metric in ("w2_latency_p99_ms", "w2_rps", "transfer_goodput_bytes_per_second"):
            self.assertEqual(metric_result(report, metric)["ratio_median"], .5)
        records[1]["paired_inputs"] = {"seed": "different"}
        self.assertEqual(reporting.analyze(records)["cohorts"][0]["valid_pairs"], 0)

    def test_w13_tool_limited_side_caps_the_claim(self):
        records = [r for i in range(1, 11) for r in pair(pair_id=i, case="W13", metric="goodput_bytes_per_second", ratio=2)]
        for record in records:
            record["metrics"]["tool_limited"] = record["engine"] == "orbstack"
        self.assertEqual(metric_result(reporting.analyze([dict(r, metrics={**r["metrics"], "tool_limited": False}) for r in records]),
                                       "goodput_bytes_per_second")["assessment"], "strict-win")
        report = reporting.analyze(records)
        result = metric_result(report, "goodput_bytes_per_second")
        self.assertEqual(result["tool_limited_trials"], {"ctrs": 0, "orbstack": 10})
        self.assertEqual(result["assessment"], "tool-limited")

    def test_pairs_measured_on_a_contended_host_are_rejected(self):
        records = [r for i in range(1, 4) for r in pair(pair_id=i, case="W13", metric="goodput_bytes_per_second", ratio=2)]
        for record in records:
            record["host_load"] = {"cpus": 10, "start": [3.0, 3, 3], "end": [4.0, 4, 4]}
        records[3]["host_load"]["end"] = [36.6, 23, 17]
        cohort = reporting.analyze(records)["cohorts"][0]
        self.assertEqual(cohort["valid_pairs"], 2)
        self.assertEqual([r["pair_id"] for r in cohort["rejections"]], [2])
        self.assertIn("host contended", cohort["rejections"][0]["reason"])

    def test_outside_cpu_decides_admission_where_it_was_measured(self):
        records = [r for i in range(1, 4) for r in pair(pair_id=i, case="W13", metric="goodput_bytes_per_second", ratio=2)]
        for record in records:
            record["host_load"] = {"cpus": 10, "start": [3.0, 3, 3], "end": [12.0, 4, 4]}
            record.setdefault("resources", {})["phases"] = {
                "setup": {"foreign_cpu_cores": 0.4, "operation_wall_seconds": 1.0},
                "measured": {"foreign_cpu_cores": 0.8, "operation_wall_seconds": 9.0}}
        records[3]["resources"]["phases"]["measured"]["foreign_cpu_cores"] = 3.5
        cohort = reporting.analyze(records)["cohorts"][0]
        self.assertEqual([r["pair_id"] for r in cohort["rejections"]], [2])
        self.assertIn("3.2 cores busy outside the engine", cohort["rejections"][0]["reason"])

    def test_a_phase_without_outside_cpu_falls_back_to_load(self):
        record = {"engine": "ctrs", "host_load": {"cpus": 10, "start": [11.0], "end": [3.0]},
                  "resources": {"phases": {"setup": {"foreign_cpu_cores": 0.1, "operation_wall_seconds": 1},
                                           "run": {"foreign_cpu_cores": None, "operation_wall_seconds": 5}}}}
        self.assertIn("1-minute load 11.0", reporting.host_contended(record))

    def test_a_trial_too_short_for_outside_cpu_falls_back_to_load(self):
        record = {"engine": "ctrs", "host_load": {"cpus": 10, "start": [3.0], "end": [3.0]},
                  "resources": {"phases": {"run": {"foreign_cpu_cores": 6.1, "operation_wall_seconds": 0.08}}}}
        self.assertIsNone(reporting.host_contended(record))

    def test_anchor_separates_a_ctrs_regression_from_orbstack_drift(self):
        def run(run_id, ctrs_ratio):
            records = [r for i in range(1, 11) for r in pair(pair_id=i, run_id=run_id, case="W13",
                       metric="goodput_bytes_per_second", ratio=ctrs_ratio)]
            for r in records:
                r["design"] = "paired"
                if run_id == "b":
                    r["workload_params"]["artifact_bytes"] = None
            return records
        anchor, candidate = run("a", 2.0), run("b", 1.0)
        rows = {(r["engine"], r["metric"]): r for r in reporting.analyze_anchor(anchor, candidate)}
        ctrs = rows[("ctrs", "goodput_bytes_per_second")]
        self.assertEqual((ctrs["anchor_n"], ctrs["candidate_n"]), (10, 10))
        self.assertAlmostEqual(ctrs["ratio"], 2.0)
        self.assertEqual(ctrs["verdict"], "regressed")
        self.assertEqual(rows[("orbstack", "goodput_bytes_per_second")]["verdict"], "no regression")

    def test_anchor_never_matches_different_common_portfolios(self):
        anchor = pair(run_id="old")
        candidate = pair(run_id="new")
        for record in anchor:
            record["inputs"] = {"portfolio_sha256": "a" * 64}
        for record in candidate:
            record["inputs"] = {"portfolio_sha256": "b" * 64}
        self.assertEqual(reporting.analyze_anchor(anchor, candidate), [])

    def test_w14_scores_only_the_metrics_its_mode_produces(self):
        records = [r for i in range(1, 3) for r in pair(pair_id=i, case="W14", metric="completion_seconds")]
        for r in records:
            r["workload_params"]["mode"] = "fresh"
        names = [m["metric"] for m in reporting.analyze(records)["cohorts"][0]["metrics"]]
        self.assertEqual(names[:4], ["completion_seconds", "latency_p50_ms", "latency_p95_ms", "latency_p99_ms"])
        self.assertNotIn("reconnect_p99_ms", names)
        self.assertNotIn("chunk_lateness_p99_ms", names)

    def test_anchor_never_compares_across_fixture_versions(self):
        def run(run_id, version):
            records = [r for i in range(1, 11) for r in pair(pair_id=i, run_id=run_id, case="W13",
                       metric="goodput_bytes_per_second")]
            for r in records:
                r["design"] = "paired"
                r["metrics"]["fixture_version"] = version
            return records
        self.assertEqual(reporting.analyze_anchor(run("a", "w13-v3"), run("b", "w13-v4")), [])

    def test_w13_reports_which_path_ctrs_connections_took(self):
        records = [r for i in range(1, 4) for r in pair(pair_id=i, case="W13", metric="goodput_bytes_per_second", ratio=2)]
        for record in records[:4]:
            if record["engine"] == "ctrs":
                record["metrics"]["transport"] = {"nat_leg": 3, "vsock": 0}
        result = metric_result(reporting.analyze(records), "goodput_bytes_per_second")
        self.assertEqual(result["ctrs_transport"], {"unrecorded_trials": 1, "nat_leg": 6, "vsock": 0})

    def test_w13_pairs_need_matching_verified_inputs_and_old_ones_are_flagged(self):
        records = pair(case="W14", metric="latency_p99_ms")
        report = reporting.analyze(records)
        self.assertIn("paired_inputs (historical: image chosen by repository name, not verified)",
                      report["cohorts"][0]["metadata_gaps"])
        for record in records:
            record["paired_inputs"] = {"api_config": "sha256:a"}
        records[1]["paired_inputs"] = {"api_config": "sha256:b"}
        self.assertEqual(reporting.analyze(records)["cohorts"][0]["valid_pairs"], 0)

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
            record["provenance"] = {"runner_sha256": "a" * 64,
                                    "build_outputs": {"ctrs_binary_sha256": None,
                                                      "guest_kernel_sha256": "b" * 64}}
        report = reporting.analyze(records)
        gaps = report["cohorts"][0]["metadata_gaps"]
        self.assertIn("workload_params", gaps)
        self.assertIn("provenance.build_outputs.ctrs_binary_sha256", gaps)
        self.assertIn("provenance.build_outputs.guest_initramfs_sha256", gaps)
        self.assertIn("provenance.assets_sha256", gaps)
        self.assertNotIn("provenance.runner_sha256", gaps)
        self.assertNotIn("provenance.build_outputs.guest_kernel_sha256", gaps)
        self.assertFalse(report["promotion_eligible"])

    def test_engine_table_shows_each_engines_guest_vcpus(self):
        records = pair()
        for record, cpus in zip(records, (9, 2)):
            record.setdefault("resources", {})["engine"] = {"ncpu": cpus, "mem_total_bytes": 1 << 33}
        report = reporting.analyze(records)
        engines = report["cohorts"][0]["engines"]
        self.assertEqual(sorted(info["guest_cpus"] for info in engines.values()), [["2"], ["9"]])
        self.assertEqual(report["cohorts"][0]["valid_pairs"], 0)

    def test_installed_default_lane_pairs_unequal_budgets_in_its_own_cohort(self):
        matched = pair()
        default = pair()
        for record, cpus in zip(default, (2, 9)):
            record["workload_params"]["resource_lane"] = "installed-default"
            record.setdefault("resources", {})["engine"] = {"ncpu": cpus, "mem_total_bytes": cpus << 30}
        cohorts = reporting.analyze(matched + default)["cohorts"]
        self.assertEqual(len(cohorts), 2)
        self.assertEqual(sorted(c["valid_pairs"] for c in cohorts), [1, 1])

    def test_runner_build_outputs_close_binary_and_guest_provenance(self):
        records = pair()
        build = {key: c * 64 for key, c in (("ctrs_binary_sha256", "1"),
                                            ("guest_kernel_sha256", "2"),
                                            ("guest_initramfs_sha256", "3"),
                                            ("guest_data_sha256", "4"))}
        for record in records:
            record["provenance"] = {**{key: "f" * 64 for key in (
                "cases_sha256", "assets_sha256", "fixture_sha256", "runner_sha256")},
                "build_outputs": dict(build)}
        gaps = reporting.analyze(records)["cohorts"][0]["metadata_gaps"]
        self.assertFalse([gap for gap in gaps if gap.startswith("provenance")])

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

    def test_nat_carried_cpu_win_is_incomplete_but_a_loss_stands(self):
        for ratio, expected in ((0.7, "incomplete"), (1.3, "loss")):
            records = [r for n in range(1, 11) for r in pair(n, ratio=ratio, metric="cpu_seconds_est")]
            for record in records:
                record["metrics"] = {}
                record["resources"].update(ownership_verified=True, resource_errors=[], cpu_counters_complete=True,
                                           cpu_seconds_est=ratio if record["engine"] == "ctrs" else 1.0)
                if record["engine"] == "ctrs":
                    record["cpu_accounting"] = {"complete": False, "nat_connections": 3}
            report = reporting.analyze(records)
            result = metric_result(report, "cpu_seconds_est")
            self.assertEqual(result["assessment"], expected)
            self.assertEqual(result["cpu_accounting_incomplete_trials"], 10)
            self.assertIn("NAT", reporting.render_markdown(report))

    def candidate_records(self, slot_a_value, slot_b_value, pairs=10):
        records = []
        for n in range(1, pairs + 1):
            for record in noise_pair(n):
                record["design"] = "candidate"
                record["workload_params"]["resource_lane"] = "installed-default"
                record["metrics"]["wall_seconds"] = slot_a_value if record["slot"] == "a" else slot_b_value
                if record["slot"] == "b":
                    record["config_overrides"] = {"CTRS_CPUS": "9"}
                    record["resources"] = {"engine": {"ncpu": 9, "mem_total_bytes": 8 << 30}}
                records.append(record)
        return records

    def test_candidate_ratio_is_candidate_over_current(self):
        report = reporting.analyze_noise(self.candidate_records(1.0, 0.8), design="candidate")
        self.assertEqual(report["input_issues"], [])
        cohort = report["cohorts"][0]
        self.assertEqual(cohort["valid_pairs"], 10)
        self.assertEqual(cohort["config_overrides"], {"CTRS_CPUS": "9"})
        self.assertAlmostEqual(metric_result(report)["ratio_median"], 0.8)
        self.assertIn("CTRS_CPUS", reporting.render_noise_markdown(report))
        self.assertEqual(reporting.analyze_noise(self.candidate_records(1.0, 0.8))["cohorts"], [])

    def test_cpu_candidate_requires_observed_vcpu_change_at_fixed_memory(self):
        for slot, budgets in [
            ("a", {"ncpu": 9, "mem_total_bytes": 8 << 30}),
            ("b", {"ncpu": 8, "mem_total_bytes": 8 << 30}),
            ("b", {"ncpu": 9, "mem_total_bytes": 16 << 30}),
            ("b", {"ncpu": 9}),
        ]:
            with self.subTest(slot=slot, budgets=budgets):
                records = self.candidate_records(1.0, 0.8)
                next(r for r in records if r["slot"] == slot)["resources"]["engine"] = budgets
                report = reporting.analyze_noise(records, design="candidate")
                cohort = report["cohorts"][0]
                self.assertEqual(cohort["valid_pairs"], 9)
                self.assertIn("CPU candidate did not apply", cohort["rejections"][0]["reason"])
                self.assertEqual(metric_result(report)["assessment"], "invalid")

    def test_candidate_without_overrides_is_an_input_issue(self):
        records = self.candidate_records(1.0, 1.0)
        for record in records:
            record.pop("config_overrides", None)
        report = reporting.analyze_noise(records, design="candidate")
        self.assertIn("config_overrides", report["input_issues"][0])

    def test_memory_candidate_scores_only_the_requested_ceiling_at_fixed_cpus(self):
        records = self.candidate_records(1.0, 0.8)
        for record in records:
            candidate = record["slot"] == "b"
            budget = record["resources"]["engine"]
            budget["ncpu"] = 9
            budget["vm_memory_ceiling_bytes"] = (6144 if candidate else 8192) << 20
            if candidate:
                record["config_overrides"] = {"CTRS_MEMORY_MIB": "6144"}
        report = reporting.analyze_noise(records, design="candidate")
        self.assertEqual(report["cohorts"][0]["valid_pairs"], 10)
        budget = records[1]["resources"]["engine"]
        for changes in ({"vm_memory_ceiling_bytes": 8192 << 20}, {"ncpu": 8},
                        {"vm_memory_ceiling_bytes": None}, {"vm_memory_ceiling_bytes": (6144 << 20) + 1}):
            with self.subTest(changes=changes), patch.dict(budget, changes):
                cohort = reporting.analyze_noise(records, design="candidate")["cohorts"][0]
                self.assertEqual(cohort["valid_pairs"], 9)
                self.assertIn("memory candidate did not apply", cohort["rejections"][0]["reason"])

    def test_partial_cpu_counter_cannot_decide_same_engine_candidate(self):
        records = self.candidate_records(1.0, 0.8)
        for record in records:
            candidate = record["slot"] == "b"
            record["resources"].update(ownership_verified=True, resource_errors=[], cpu_counters_complete=True,
                                       cpu_seconds_est=1.2 if candidate else 1.0)
            record["cpu_accounting"] = {"complete": candidate}
        report = reporting.analyze_noise(records, design="candidate")
        metric = metric_result(report, "cpu_seconds_est")
        self.assertEqual(metric["assessment"], "incomplete")
        self.assertEqual(metric["cpu_accounting_incomplete_trials"], 10)
        self.assertIn("10 slot trials have incomplete CPU accounting.", reporting.render_noise_markdown(report))

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
