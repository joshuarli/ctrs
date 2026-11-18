import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import runner


class W1Tests(unittest.TestCase):
    def execute(self, fault=None):
        portfolio = json.loads((runner.FIXTURES / "w8-v5/portfolio.json").read_text())
        pins = {service: portfolio["images"]["np-v5/" + name] for service, name in
                (("api", "api"), ("db", "postgres"), ("cache", "redis"))}
        restarted = []
        commands = []
        persisted = {}
        project = None

        def sh(args, **kwargs):
            nonlocal project
            commands.append(args)
            body = ""
            if args[:2] == ["image", "inspect"]:
                images = [{"Id": pin["config"], "Architecture": "arm64",
                           "RootFS": {"Layers": pin["diff_ids"]}} for pin in pins.values()]
                if fault == "wrong image":
                    images[0]["RootFS"]["Layers"] = []
                body = json.dumps(images)
            elif args[0] == "compose":
                project = args[args.index("-p") + 1]
                if "ps" in args:
                    body = args[-1] + "-id"
                if "down" in args and fault == "cleanup failed":
                    raise RuntimeError("cannot remove project")
            elif args[0] == "inspect":
                service = args[-1].removesuffix("-id")
                labels = {"com.docker.compose.project": project, "com.docker.compose.service": service}
                if service == "db" and fault == "wrong owner":
                    labels["com.docker.compose.project"] = "other"
                body = json.dumps([{"Id": args[-1], "Image": pins[service]["config"],
                    "Config": {"Labels": labels},
                    "State": {"Running": True, "StartedAt": "after" if restarted and fault != "no restart" else "before"},
                    "Mounts": [{"Type": "volume", "Name": project + "_dbdata",
                                "Destination": "/var/lib/postgresql/data", "RW": True}]}])
            elif args[0] == "restart":
                restarted.append(args[-1])
            else:
                self.fail(f"unexpected command {args}")
            return SimpleNamespace(stdout=body)

        def write(url, obj):
            persisted[obj["key"]] = obj["value"]
            if fault == "HTTP rejection":
                return 503, b"database \xff unavailable"
            return (200, {"stored": "wrong"}) if fault == "wrong acknowledgment" else (200, {"stored": obj["key"]})

        def read(url, timeout):
            key = url.rsplit("/", 1)[-1]
            if key == "roundtrip":
                payload = "wrong" if fault == "wrong seed" else hashlib.md5(b"1").hexdigest()
                return 200, {"ok": True, "db_row": {"id": 1, "name": "item-1", "payload": payload},
                             "cache_token": "rt-1", "seed_rows": 500}
            response_key = "wrong" if fault == "wrong read key" else key
            return 200, {"key": response_key, "value": persisted[key], "cache_match": True}

        engine = SimpleNamespace(name="ctrs", ensure_up=lambda: None, sh=sh)
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(runner, "RESULTS", Path(directory)), \
                patch.object(runner, "start_sampler", return_value=(None, None)), \
                patch.object(runner, "wait_health", return_value=(1.0, {"ok": True})), \
                patch.object(runner, "http_json", side_effect=read), \
                patch.object(runner, "http_json_write", side_effect=write):
            record = runner.trial_w1(runner.RunContext("w1-test"), engine, "warm")
        return record, commands, restarted

    def test_requires_acknowledged_writes_and_exact_reads_across_owned_restart(self):
        record, commands, restarted = self.execute()
        self.assertTrue(record["correctness"]["ok"], record["validation_errors"])
        self.assertEqual(restarted, ["db-id"])
        self.assertEqual(len([command for command in commands if "down" in command]), 1)
        for name in ("write_before_restart", "persist_after_db_restart", "write_after_restart", "read_after_restart"):
            self.assertTrue(record["correctness"]["checks"][name])

    def test_rejects_false_recovery_evidence_and_retains_cleanup(self):
        for fault, reason, expected_restarts in (
            ("wrong image", "baseline image differs", []),
            ("wrong seed", "initial DB/cache roundtrip differs", []),
            ("wrong owner", "wrong identity for W1 db", []),
            ("wrong acknowledgment", "did not acknowledge the exact key", []),
            ("HTTP rejection", "did not acknowledge the exact key", []),
            ("no restart", "did not observe the owned database restart", ["db-id"]),
            ("wrong read key", "did not return the exact database and cache record", ["db-id"]),
            ("cleanup failed", "W1 cleanup", ["db-id"]),
        ):
            with self.subTest(fault=fault):
                record, commands, restarted = self.execute(fault)
                self.assertFalse(record["correctness"]["ok"])
                self.assertIn(reason, record["validation_errors"][0])
                self.assertEqual(restarted, expected_restarts)
                self.assertEqual(any("down" in command for command in commands), fault != "wrong image")
                json.dumps(record)


if __name__ == "__main__":
    unittest.main()
