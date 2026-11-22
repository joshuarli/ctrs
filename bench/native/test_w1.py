import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import runner


class W1Tests(unittest.TestCase):
    def execute(self, fault=None, *, cold=False):
        portfolio = json.loads((runner.FIXTURES / "w8-v6/portfolio.json").read_text())
        pins = {service: portfolio["images"]["np-v6/" + name] for service, name in
                (("api", "api"), ("db", "postgres"), ("cache", "redis"))}
        restarted = []
        commands = []
        persisted = {}
        project = None
        elapsed = 0.0

        def sh(args, **kwargs):
            nonlocal project, elapsed
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
                elapsed += 4
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
                elapsed += 2
            else:
                self.fail(f"unexpected command {args}")
            return SimpleNamespace(stdout=body)

        def write(url, obj):
            nonlocal elapsed
            elapsed += 0.5
            persisted[obj["key"]] = obj["value"]
            if fault == "HTTP rejection":
                return 503, b"database \xff unavailable"
            return (200, {"stored": "wrong"}) if fault == "wrong acknowledgment" else (200, {"stored": obj["key"]})

        def read(url, timeout):
            nonlocal elapsed
            elapsed += 0.25
            key = url.rsplit("/", 1)[-1]
            if key == "roundtrip":
                payload = "wrong" if fault == "wrong seed" else hashlib.md5(b"1").hexdigest()
                return 200, {"ok": True, "db_row": {"id": 1, "name": "item-1", "payload": payload},
                             "cache_token": "rt-1", "seed_rows": 500}
            response_key = "wrong" if fault == "wrong read key" else key
            return 200, {"key": response_key, "value": persisted[key], "cache_match": True}

        def wait_health(*args):
            nonlocal elapsed
            elapsed += 1
            return elapsed, {"ok": True}

        engine = SimpleNamespace(name="ctrs", sh=sh, external=False, proc=None)
        original_prepare = runner.prepare_pinned_stack

        def ensure_up():
            nonlocal elapsed
            if cold:
                commands.append(["start-daemon"])
                elapsed += 2
                engine.proc = SimpleNamespace(poll=lambda: None)

        def stop():
            nonlocal elapsed
            commands.append(["stop-daemon"])
            elapsed += 3
            engine.proc = None
            if fault == "socket remains":
                Path(engine.socket.removeprefix("unix://")).touch()

        def prepare(engine, override, *, layout=None):
            nonlocal elapsed
            if layout is not None:
                commands.append(["stage-pinned-stack"])
                elapsed += 50
            return original_prepare(engine, override)

        engine.ensure_up = ensure_up
        engine.stop = stop
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(runner, "RESULTS", Path(directory)), \
                patch.object(runner, "WORK", Path(directory)), \
                patch.object(runner, "prepare_pinned_stack", side_effect=prepare), \
                patch.object(runner, "start_sampler", return_value=(None, None)), \
                patch.object(runner.time, "monotonic", side_effect=lambda: elapsed), \
                patch.object(runner, "wait_health", side_effect=wait_health), \
                patch.object(runner, "http_json", side_effect=read), \
                patch.object(runner, "http_json_write", side_effect=write):
            (Path(directory) / "inputs/w8-portfolio-v6/layout").mkdir(parents=True)
            engine.socket = "unix://" + str(Path(directory) / "docker.sock")
            ctx = runner.RunContext("w1-test")
            ctx.workload_params["cold"] = cold
            record = runner.trial_w1(ctx, engine, "cold" if cold else "warm")
        return record, commands, restarted

    def test_requires_acknowledged_writes_and_exact_reads_across_owned_restart(self):
        record, commands, restarted = self.execute()
        self.assertTrue(record["correctness"]["ok"], record["validation_errors"])
        self.assertEqual(restarted, ["db-id"])
        self.assertEqual(record["metrics"]["db_restart_to_verified_s"], 4)
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
                if fault != "cleanup failed":
                    self.assertNotIn("db_restart_to_verified_s", record["metrics"])
                json.dumps(record)

    def test_cold_start_excludes_import_and_teardown_from_startup_measurement(self):
        record, commands, _ = self.execute(cold=True)
        self.assertTrue(record["correctness"]["ok"], record["validation_errors"])
        self.assertEqual(record["design"], "cold-start-diagnostic")
        self.assertEqual(record["metrics"]["cold_daemon_ready_s"], 2.)
        self.assertEqual(record["metrics"]["cold_roundtrip_s"], 3.25)
        self.assertTrue(record["correctness"]["checks"]["cold_pinned_images_preserved"])
        self.assertEqual([cmd[0] for cmd in commands if cmd[0] in ("start-daemon", "stop-daemon", "stage-pinned-stack")],
                         ["start-daemon", "stage-pinned-stack", "stop-daemon", "start-daemon"])

    def test_cold_start_refuses_to_reuse_a_live_preparation_socket(self):
        record, commands, _ = self.execute("socket remains", cold=True)
        self.assertFalse(record["correctness"]["ok"])
        self.assertIn("did not release", record["validation_errors"][0])
        self.assertEqual(commands.count(["start-daemon"]), 1)


if __name__ == "__main__":
    unittest.main()
