import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import runner
import storage_v4 as storage


class FakeEngine:
    name = "ctrs"

    def __init__(self, directory, bad_setting=False, bad_owner=False):
        self.bad_owner = bad_owner
        self.directory = directory
        self.bad_setting = bad_setting
        self.calls = []
        self.volume = None
        self.container = None
        self.phase = None

    def ensure_up(self):
        pass

    def sh(self, args, **kwargs):
        self.calls.append(args)
        out = ""
        if args[:2] == ["image", "inspect"]:
            out = "[]"
        elif args[:2] == ["volume", "create"]:
            self.volume = args[-1]
        elif args[:2] == ["volume", "inspect"]:
            out = json.dumps([{"Name": self.volume, "Labels": {"dev.ctrs.campaign.run": "other" if self.bad_owner else "run1"}}])
        elif args[0] == "run":
            self.container = args[args.index("--name") + 1]
        elif args[0] == "inspect":
            out = json.dumps([{"Config": {"Labels": {"dev.ctrs.campaign.run": "run1"}}}])
        elif args[0] == "cp":
            (self.directory / f"{self.phase}.123").write_text("0 1 1000 0 100\n0 2 3000 0 101\n")
        elif "pgbench" in args and "-i" not in args:
            self.phase = "ro" if "-S" in args else "rw"
            out = "tps = 12.5 (without initial connection time)\n"
        elif "du" in args:
            out = "12 /var/lib/postgresql/data\n"
        elif "psql" in args:
            query = args[-1]
            if query == "SELECT 1":
                out = "1\n"
            elif query.startswith("SHOW "):
                out = "off\n" if self.bad_setting else "on\n"
            elif "json_build_object" in query:
                out = json.dumps({"accounts": 100000, "account_balance": 5, "history_delta": 5, "history": 2})
            elif "pg_database_size" in query:
                out = "200|100\n"
        return SimpleNamespace(returncode=0, stdout=out, stderr="")


class FakeContext:
    run_id = "run1"

    def __init__(self, directory):
        self.directory = directory
        self.workload_params = {"resource_lane": "matched"}

    def trial_dir(self, *args):
        return self.directory

    def new_record(self, *args):
        return {"trial_id": "trial1", "metrics": {}, "correctness": {"checks": {}, "ok": False},
                "resources": {}, "validation_errors": [], "workload_params": dict(self.workload_params)}


class StorageTests(unittest.TestCase):
    def test_linux_pin_preserves_receipts_and_durability_rejection(self):
        with patch.object(runner.linux_lane, "enabled", return_value=True), \
             patch.object(runner.linux_lane, "image", return_value=("native-image", {"image_diff_ids": ["native-layer"]})) as image:
            rec, engine, _ = self.run_trial()
            self.assertTrue(rec["correctness"]["ok"], rec["validation_errors"])
            self.assertEqual(rec["paired_inputs"], {"postgres_diff_ids": ["native-layer"],
                "portfolio_sha256": runner.sha256_file(runner.linux_lane.LOCK)})
            self.assertFalse(any(call[:2] == ["image", "inspect"] for call in engine.calls))
            self.test_metrics_receipts_and_owned_cleanup()
            self.test_durability_failure_still_cleans_owned_resources()
            self.test_volume_ownership_mismatch_never_removes_volume()
        self.assertEqual(image.call_count, 4)
        self.assertTrue(all(call.args[1] == "db" for call in image.call_args_list))

    def test_latency_receipts_and_nearest_rank(self):
        log = "".join(f"0 {i} {i * 1000} 0 1\n" for i in range(1, 101))
        self.assertEqual(storage.latency_metrics([log], 100, "rw"),
                         {"rw_p50_ms": 50, "rw_p95_ms": 95, "rw_p99_ms": 99})
        for bad in ("0 1 skipped 0 1", "0 1 nan 0 1", "bad", ""):
            with self.assertRaises(ValueError):
                storage.latency_metrics([bad], 1, "rw")

    def test_exact_verification(self):
        data = {"accounts": 200000, "account_balance": -9, "history_delta": -9, "history": 16}
        self.assertTrue(storage.verify_data(data, 2, 4, 4))
        for key in data:
            altered = dict(data)
            altered[key] += 1
            self.assertFalse(storage.verify_data(altered, 2, 4, 4))

    def run_trial(self, bad_setting=False, bad_owner=False):
        params = {"scale": 1, "shared_buffers": "128MB", "clients": 1, "threads": 1,
                  "transactions_per_client": 2, "random_seed": 42}
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name)
        engine = FakeEngine(path, bad_setting, bad_owner)
        ctx = FakeContext(path)
        with patch.object(runner, "load_cases", return_value={"case": [{"id": "W3-v4", "params": params}]}), \
             patch.object(storage, "baseline_image_reference", return_value=("digest", "image")), \
             patch.object(storage, "require_baseline_images", return_value={"db": "pinned"}), \
             patch.object(runner, "start_sampler", return_value=(None, None)), \
             patch.object(storage.time, "sleep"), \
             patch.object(storage.time, "monotonic", side_effect=range(1000)):
            record = storage.trial_w3_v4(ctx, engine, "warm")
        return record, engine, path

    def test_metrics_receipts_and_owned_cleanup(self):
        rec, engine, path = self.run_trial()
        self.assertTrue(rec["correctness"]["ok"], rec["validation_errors"])
        self.assertEqual(rec["metrics"]["rw_tps"], 12.5)
        self.assertEqual(rec["metrics"]["rw_p99_ms"], 3)
        self.assertEqual(rec["metrics"]["ro_p99_ms"], 3)
        self.assertEqual(rec["metrics"]["pgdata_allocated_bytes"], 12288)
        self.assertEqual(rec["metrics"]["db_size_bytes"], 200)
        self.assertEqual(rec["workload_params"]["scale"], 1)
        self.assertTrue((path / "rw.123").is_file())
        self.assertTrue((path / "durability_after-fsync.stdout").is_file())
        creates = [a for a in engine.calls if a[:2] == ["volume", "create"] or a[0] == "run"]
        self.assertEqual(len(creates), 2)
        self.assertTrue(all("dev.ctrs.campaign.run=run1" in a for a in creates))
        self.assertTrue(any(a[:2] == ["volume", "rm"] for a in engine.calls))
        self.assertTrue(any(a[:2] == ["rm", "-f"] for a in engine.calls))
        runs = [a for a in engine.calls if "pgbench" in a and "-i" not in a]
        self.assertEqual(["-n" in a for a in runs], [False, True])

    def test_durability_failure_still_cleans_owned_resources(self):
        rec, engine, path = self.run_trial(True)
        self.assertFalse(rec["correctness"]["ok"])
        self.assertFalse(rec["correctness"]["checks"]["durability_before"])
        self.assertTrue((path / "durability_before-fsync.stdout").is_file())
        self.assertTrue(any(a[:2] == ["volume", "rm"] for a in engine.calls))
        self.assertFalse(any("pgbench" in a for a in engine.calls))

    def test_volume_ownership_mismatch_never_removes_volume(self):
        rec, engine, _ = self.run_trial(bad_owner=True)
        self.assertFalse(rec["correctness"]["ok"])
        self.assertTrue(any("ownership mismatch" in error for error in rec["validation_errors"]))
        self.assertFalse(any(a[:2] == ["volume", "rm"] for a in engine.calls))

    def test_bad_throughput_rejected(self):
        for output in ("", "tps = 0", "tps = 1\ntps = 2"):
            with self.assertRaises(ValueError):
                storage.throughput(output)


if __name__ == "__main__":
    unittest.main()
