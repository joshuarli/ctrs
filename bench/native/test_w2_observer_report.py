import json
from pathlib import Path
import tempfile
import unittest

from diagnostics import w2_observer_report as observer


def save(path, record):
    path.write_text(json.dumps(record))


class ObserverReportTests(unittest.TestCase):
    def setUp(self):
        storage = tempfile.TemporaryDirectory()
        self.addCleanup(storage.cleanup)
        self.blocks = [Path(storage.name) / str(index) for index in range(1, 11)]
        for index, block in enumerate(self.blocks, start=1):
            block.mkdir()
            plan = {"profile_kind": "cpu-leaf", "operations": 50000, "requested_client_location": "guest",
                    "concurrency": 8, "fixture_version": "leaf-v1", "profile_identity": "leaf-v1",
                    "client_image_sha256": "image", "client_source_sha256": "source", "seed": 7,
                    "fixed_cpu_clock_period_ns": observer.period_ns("cpu-leaf"),
                    "engine_order": observer.ENGINES[::1 if index % 2 else -1],
                    "mode_order": observer.MODES[::1 if index % 2 else -1],
                    "observer_confirmation_budget": {"application_cpu_relative": .05,
                                                     "workload_wall_relative": .05}}
            save(block / "plan.json", plan)
            for engine in observer.ENGINES:
                for mode in observer.MODES:
                    directory = block / engine / mode
                    directory.mkdir(parents=True)
                    row = {key: plan[key] for key in (
                        "profile_kind", "concurrency", "fixture_version", "profile_identity",
                        "client_image_sha256", "client_source_sha256", "seed")}
                    cpu = 100 if mode == "off" else 102
                    wall = 110 if engine == "orbstack" and mode == "on" else 100
                    row.update(mode=mode, correctness=True, errors=[], cleanup_errors=[],
                               successful_operations=50000, reads_ok=35000, writes_ok=15000,
                               effective_client_location="guest", workload_wall_seconds=wall,
                               application_cpu={"cpu_seconds": cpu, "status": "ok", "errors": [],
                                                "counter_quantization_bound_cpu_seconds": .25})
                    if mode == "on":
                        row["cpu_profile"] = {"status": "ok", "raw_event_coverage_checked": True,
                                              "fixed_cpu_clock_period_ns": plan["fixed_cpu_clock_period_ns"]}
                    save(directory / "result.json", row)
                    save(directory / "before-gate.json", {"exit": 0})
                    save(directory / "after-gate.json", {"exit": 0})

    def test_complete_budget_uses_pairing_and_quantization(self):
        report = observer.assess(self.blocks)
        self.assertEqual(report["accepted_blocks"], 10)
        self.assertTrue(report["host_process_review_required"])
        cpu = report["metrics"]["ctrs"]["application_cpu"]
        self.assertEqual(cpu["median_on_off_ratio"], 1.02)
        self.assertLess(cpu["ci95_with_quantization"][0], 1.02)
        self.assertGreater(cpu["ci95_with_quantization"][1], 1.02)
        self.assertEqual(cpu["status"], "within-budget")
        self.assertEqual(report["metrics"]["orbstack"]["workload_wall"]["status"], "outside-budget")

    def test_rejected_or_missing_blocks_cannot_establish_a_verdict(self):
        save(self.blocks[3] / "ctrs/on/after-gate.json", {"exit": 1})
        report = observer.assess(self.blocks[:-1])
        self.assertEqual(report["accepted_blocks"], 8)
        self.assertEqual(report["rejected_blocks"][0]["block"], 4)
        self.assertIn("failed its after host gate", report["rejected_blocks"][0]["reason"])
        self.assertEqual(report["metrics"]["ctrs"]["application_cpu"]["status"], "incomplete")

    def test_wrong_order_and_duplicate_block_are_rejected(self):
        report = observer.assess([self.blocks[1], self.blocks[1]])
        self.assertEqual(report["accepted_blocks"], 0)
        self.assertIn("orders must alternate", report["rejected_blocks"][0]["reason"])
        self.assertEqual(report["rejected_blocks"][1]["reason"], "duplicate block directory")

    def test_new_host_admission_requires_aligned_outside_cpu(self):
        block = self.blocks[0]
        gate = block / "ctrs/off/after-gate.json"
        save(gate, {"exit": 75})
        self.assertEqual(observer.assess([block])["accepted_blocks"], 0)

        file = block / "plan.json"
        plan = observer.read_object(file)
        plan["host_admission"] = observer.OUTSIDE_CPU_ADMISSION
        save(file, plan)
        self.assertEqual(observer.assess([block])["accepted_blocks"], 0)
        for engine in observer.ENGINES:
            for mode in observer.MODES:
                file = block / engine / mode / "result.json"
                row = observer.read_object(file)
                row["host_cpu"] = {"errors": [], "foreign_cpu_cores": .5}
                save(file, row)
        self.assertEqual(observer.assess([block])["accepted_blocks"], 1)

        row["host_cpu"]["foreign_cpu_cores"] = 2.01
        save(file, row)
        result = observer.assess([block])
        self.assertEqual(result["accepted_blocks"], 0)
        self.assertIn("outside-engine CPU receipt", result["rejected_blocks"][0]["reason"])
