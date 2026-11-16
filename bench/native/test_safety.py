"""Offline regression tests for benchmark isolation and honest outcomes.

No engine, VM, Docker installation, network service, or user data is used.
"""

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import runner


def completed(stdout="", code=0):
    return subprocess.CompletedProcess([], code, stdout, "")


class FixtureContext:
    def __init__(self, root):
        self.root = Path(root)
        self.run_id = "test-run-000001"
        self.workload_id = "test-run-000001:W6:pair-1"

    def trial_dir(self, engine, case, state):
        path = self.root / engine / case
        path.mkdir(parents=True, exist_ok=True)
        return path

    def new_record(self, *_):
        return {"metrics": {}, "correctness": {"ok": True, "checks": {}},
                "resources": {}, "validation_errors": [], "notes": []}


def fake_engine(name="orbstack"):
    engine = Mock()
    engine.name = name
    engine.socket = f"unix:///bench/{name}.sock"
    engine.builder_name = f"np-dc-{name}-verified"
    engine.sh.return_value = completed()
    engine.compose.return_value = completed()
    return engine


class ManifestTests(unittest.TestCase):
    def test_validation_needs_no_docker_or_path(self):
        env = {**os.environ, "PATH": ""}
        result = subprocess.run(
            [sys.executable, str(Path(runner.__file__)), "validate-manifest"],
            capture_output=True, text=True, env=env, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(result.stdout)
        self.assertIn("W6", manifest["cases"])
        self.assertEqual(len(manifest["cases_sha256"]), 64)

    def test_bad_contract_stops_before_engine_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "cases.toml"
            manifest.write_text("schema_version=1\nschema_version=2\n")
            with patch.object(runner, "CASES_FILE", manifest), \
                    patch.object(runner, "find_docker") as lookup, \
                    patch.object(sys, "argv", ["runner.py", "prepare"]), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as err:
                    runner.main()
                self.assertEqual(err.exception.code, 2)
                lookup.assert_not_called()

    def test_shared_orbstack_cold_comparison_rejected_offline(self):
        argv = ["runner.py", "baseline", "--case", "W7", "--a", "ctrs",
                "--b", "orbstack", "--cold"]
        with patch.object(sys, "argv", argv), \
                patch.object(runner, "find_docker") as lookup, \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as err:
                runner.main()
            self.assertEqual(err.exception.code, 2)
            lookup.assert_not_called()


class BuilderIsolationTests(unittest.TestCase):
    def test_engine_specific_builder_config_ignores_ambient_selection(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(runner, "WORK", Path(tmp)), \
                patch.object(runner, "DOCKER", "/usr/bin/docker"), \
                patch.dict(os.environ, {"BUILDX_BUILDER": "user-production"}):
            ctrs = runner.Engine("ctrs", "test")
            orb = runner.Engine("orbstack", "test")
            self.assertNotEqual(ctrs.builder_name, orb.builder_name)
            self.assertNotEqual(ctrs.buildx_config, orb.buildx_config)
            self.assertNotIn("BUILDX_BUILDER", ctrs.env())
            self.assertEqual(ctrs.env()["BUILDX_CONFIG"], str(ctrs.buildx_config))

    def test_existing_builder_with_wrong_endpoint_is_refused(self):
        engine = fake_engine()
        engine.sh.return_value = completed(
            "Name: np-test\nDriver: docker-container\nNodes:\nEndpoint: unix:///wrong\n")
        with self.assertRaisesRegex(RuntimeError, "different endpoint"):
            runner.ensure_dc_builder(engine)
        self.assertEqual(engine.sh.call_count, 1)

    def test_new_builder_gets_explicit_endpoint_and_is_verified(self):
        engine = fake_engine()
        engine.sh.side_effect = [completed(code=1), completed(), completed(
            "Name: np-test\nDriver: docker-container\nNodes:\n"
            f"Endpoint: {engine.socket}\n"
            f'Driver Options: image="{runner.DC_BUILDER_IMAGE}"\n')]
        runner.ensure_dc_builder(engine)
        create = engine.sh.call_args_list[1].args[0]
        self.assertEqual(create[-1], engine.socket)
        self.assertIn(engine.builder_name, create)
        self.assertNotIn("--use", create)

    def test_matching_endpoint_with_wrong_image_is_refused(self):
        engine = fake_engine()
        engine.sh.return_value = completed(
            "Name: np-test\nDriver: docker-container\nNodes:\n"
            f"Endpoint: {engine.socket}\nDriver Options: image=mutable:latest\n")
        with self.assertRaisesRegex(RuntimeError, "pinned BuildKit"):
            runner.ensure_dc_builder(engine)


class WorkloadSafetyTests(unittest.TestCase):
    def test_w6_compiles_both_apps_and_records_paired_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = FixtureContext(tmp)
            engine = fake_engine()
            engine.sh.side_effect = lambda args, **kw: completed(
                "a" * 64 + "  /src/out\n" if args[0] == "run" else "")
            fixture = Path(tmp) / "source"
            (fixture / "rust").mkdir(parents=True)
            shutil.copy(runner.W6_DIR / "Dockerfile", fixture / "Dockerfile")
            shutil.copy(runner.W6_DIR / "rust" / "Dockerfile",
                        fixture / "rust" / "Dockerfile")
            # Fake source archives are sufficient for this mocked build:
            # the test checks orchestration, never executes compilation.
            zlib_pin = dict(runner.W6_ZLIB_SOURCE)
            rust_pin = dict(runner.W6_RUST_SOURCE)
            zlib_pin["sha256"] = hashlib.sha256(b"zlib asset").hexdigest()
            rust_pin["sha256"] = hashlib.sha256(b"rust asset").hexdigest()
            (fixture / "zlib-1.3.1.tar.gz").write_bytes(b"zlib asset")
            (fixture / "hyperfine-2.0.0.tar.gz").write_bytes(b"rust asset")
            with patch.object(runner, "W6_DIR", fixture), \
                    patch.object(runner, "W6_ZLIB_SOURCE", zlib_pin), \
                    patch.object(runner, "W6_RUST_SOURCE", rust_pin):
                rec = runner.trial_w6(ctx, engine, "warm")
            self.assertTrue(rec["correctness"]["ok"], rec)
            builds = [call.args[0] for call in engine.sh.call_args_list
                      if call.args[0][:2] == ["buildx", "build"]]
            self.assertEqual(len(builds), 2)
            self.assertTrue(all("--no-cache" in b for b in builds))
            base = Path(tmp) / "orbstack/W6"
            for name in ("ctx-rust", "ctx-zlib"):
                self.assertEqual((base / name / "stamp.txt").read_text(),
                                 ctx.workload_id + "\n")
            first = runner.workload_id("run", "W6", 1, 1)
            self.assertEqual(first, runner.workload_id("run", "W6", 1, 2))
            self.assertNotEqual(first, runner.workload_id("run", "W6", 2, 3))

    def test_missing_w6_asset_fails_before_starting_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = fake_engine()
            with patch.object(runner, "ensure_pinned_source",
                              side_effect=RuntimeError("checksum-pinned fetch failed")):
                rec = runner.trial_w6(FixtureContext(tmp), engine, "warm")
            self.assertFalse(rec["correctness"]["ok"])
            self.assertIn("checksum-pinned", rec["validation_errors"][0])
            engine.ensure_up.assert_not_called()

    def test_w7_builds_two_real_apps_without_pruning(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "w7"
            for app in ("hyperfine", "httpie"):
                (fixture / app).mkdir(parents=True)
                shutil.copy(runner.W7_DIR / app / "Dockerfile",
                            fixture / app / "Dockerfile")
            rust = b"rust asset"
            httpie = b"httpie asset"
            rust_pin = dict(runner.W6_RUST_SOURCE)
            httpie_pin = dict(runner.W7_HTTPIE_SOURCE)
            rust_pin["sha256"] = hashlib.sha256(rust).hexdigest()
            httpie_pin["sha256"] = hashlib.sha256(httpie).hexdigest()
            (fixture / "hyperfine-2.0.0.tar.gz").write_bytes(rust)
            (fixture / "httpie-3.2.4.tar.gz").write_bytes(httpie)
            engine = fake_engine()

            def respond(args, **kw):
                if args[0] == "run":
                    if any("hyperfine" in a for a in args):
                        return completed(
                            "hyperfine 2.0.0\n" if "--version" in args
                            else "incremental-1\n")
                    if any("http" in a for a in args):
                        return completed(
                            "3.2.4\n" if "--version" in args
                            else "incremental-1\n")
                return completed()
            engine.sh.side_effect = respond
            apps = {"hyperfine": dict(runner.W7_APPS["hyperfine"],
                                      source=rust_pin),
                    "httpie": dict(runner.W7_APPS["httpie"],
                                   source=httpie_pin)}
            with patch.object(runner, "W7_DIR", fixture), \
                    patch.object(runner, "W7_APPS", apps), \
                    patch.object(runner, "start_sampler",
                                 return_value=(None, None)):
                rec = runner.trial_w7(FixtureContext(tmp), engine, "warm")
            self.assertTrue(rec["correctness"]["ok"], rec)
            commands = [call.args[0] for call in engine.sh.call_args_list]
            self.assertFalse(any("prune" in command for command in commands))
            builds = [cmd for cmd in commands if cmd[:2] == ["buildx", "build"]]
            # 3 builds per app: uncached + warm + incremental.
            self.assertEqual(len(builds), 6)
            self.assertEqual(sum("--no-cache" in b for b in builds), 2)
            for app in ("hyperfine", "httpie"):
                for state in ("uncached", "warm", "incr"):
                    self.assertIn(f"{app}_{state}_s", rec["metrics"])

    def test_w8_keeps_shared_content_and_labels_it_warm(self):
        with tempfile.TemporaryDirectory() as tmp:
            portfolio = Path(tmp) / "portfolio.json"
            portfolio.write_text(json.dumps({"orbstack": {"busybox": {
                "pull_ref": "127.0.0.1:5000/npw8/busybox@sha256:abc",
                "tag_ref": "127.0.0.1:5000/npw8/busybox:v1", "digest": "sha256:abc"}}}))
            engine = fake_engine()
            engine.sh.side_effect = lambda args, **kw: completed("sha256:abc npw8-ok")
            with patch.object(runner, "PORTFOLIO_FILE", portfolio), \
                    patch.object(runner, "ensure_registry", return_value=5000), \
                    patch.object(runner, "start_sampler", return_value=(None, None)), \
                    patch.object(runner, "compose_down"):
                rec = runner.trial_w8(FixtureContext(tmp), engine, "warm")
            self.assertTrue(rec["correctness"]["ok"], rec)
            commands = [call.args[0] for call in engine.sh.call_args_list]
            self.assertFalse(any("prune" in command for command in commands))
            engine.stop.assert_not_called()
            self.assertEqual(rec["metrics"]["cache_mode"],
                             "fixture-refs-removed-content-retained")

    def soak_result(self, summary, code=0):
        with tempfile.TemporaryDirectory() as tmp:
            clock = [0.0]
            engine = fake_engine()

            def load(args, **kwargs):
                if summary is not None:
                    Path(args[args.index("--out") + 1]).write_text(json.dumps(summary))
                clock[0] = 2.0
                return completed(code=code)

            with patch.object(runner.time, "monotonic", side_effect=lambda: clock[0]), \
                    patch.object(runner, "start_sampler", return_value=(None, None)), \
                    patch.object(runner, "wait_health", return_value=(0.0, {})), \
                    patch.object(runner, "compose_down"), \
                    patch.object(runner, "http_json", return_value=(200, {"items": 500})), \
                    patch.object(runner.subprocess, "run", side_effect=load):
                return runner.trial_w11(FixtureContext(tmp), engine, "warm", duration=1.0)

    def test_soak_rejects_even_one_percent_errors(self):
        rec = self.soak_result({"requests": 100, "errors": 1,
                                "reads_ok": 99, "writes_ok": 0})
        self.assertFalse(rec["correctness"]["ok"])
        self.assertFalse(rec["correctness"]["checks"]["errors_zero"])

    def test_soak_rejects_missing_summary_and_failed_driver(self):
        for summary, code in [(None, 0), ({"requests": 1, "errors": 0,
                                          "reads_ok": 1, "writes_ok": 0}, 1)]:
            with self.subTest(summary=summary, code=code):
                rec = self.soak_result(summary, code)
                self.assertFalse(rec["correctness"]["ok"])
                self.assertEqual(rec["metrics"]["invalid_load_windows"], 1)


class W6SourceTests(unittest.TestCase):
    @staticmethod
    def _pin(payload):
        return {"url": "https://example.invalid/src.tar.gz",
                "file": "src.tar.gz",
                "sha256": hashlib.sha256(payload).hexdigest()}

    @staticmethod
    def _resp(data):
        class Resp:
            def __enter__(self):
                return io.BytesIO(data)

            def __exit__(self, *args):
                return False
        return Resp()

    def test_verified_file_skips_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            payload = b"good archive"
            (dest / "src.tar.gz").write_bytes(payload)
            with patch.object(runner.urllib.request, "urlopen",
                              side_effect=AssertionError("network used")):
                self.assertEqual(
                    runner.ensure_pinned_source(self._pin(payload), dest),
                    dest / "src.tar.gz")

    def test_fetch_verifies_checksum_then_installs(self):
        payload = b"fetched archive"
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            with patch.object(runner.urllib.request, "urlopen",
                              return_value=self._resp(payload)) as fetch:
                target = runner.ensure_pinned_source(self._pin(payload), dest)
            self.assertEqual(target.read_bytes(), payload)
            self.assertFalse((dest / "src.tar.gz.part").exists())
            fetch.assert_called_once()

    def test_checksum_mismatch_never_installs_or_overwrites(self):
        payload = b"corrupt download"
        pin = self._pin(b"expected bytes")
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            original = b"pre-existing good archive"
            (dest / "src.tar.gz").write_bytes(original)
            with patch.object(runner.urllib.request, "urlopen",
                              return_value=self._resp(payload)):
                with self.assertRaisesRegex(RuntimeError, "checksum"):
                    runner.ensure_pinned_source(pin, dest)
            self.assertEqual((dest / "src.tar.gz").read_bytes(), original)
            self.assertFalse((dest / "src.tar.gz.part").exists())


class ExitStatusTests(unittest.TestCase):
    def test_record_captures_executed_defaults_and_post_trial_version(self):
        engine = fake_engine()
        context = Mock(run_id="one-run", _seq=0, engines={"orbstack": engine})

        def trial(ctx, engine, state, duration=300.0, window=30.0, seed=1):
            return {"correctness": {"ok": True}, "resources": {}, "validation_errors": []}

        with patch.object(runner, "trial_w11", trial), \
                patch.object(runner, "safe_version", return_value="observed-after-start"), \
                patch.object(runner, "safe_engine_info", return_value=None):
            rec = runner.run_one(context, "orbstack", "W11", "warm",
                                 pair_id=1, order_index=0, duration=10.0, seed=4)
        self.assertEqual(context.workload_params,
                         {"cold": False, "duration": 10.0, "window": 30.0, "seed": 4})
        self.assertEqual(rec["engine_server_version"], "observed-after-start")
        self.assertEqual(context.workload_id, "one-run:W11:pair-1")

    def test_baseline_returns_failure_and_pairs_seed(self):
        args = argparse.Namespace(a="ctrs", b="orbstack", seed=7, pairs=2,
                                  randomize=False, case="W2", state="warm", cold=False,
                                  concurrency=8, duration=20, write_ratio=0.3)
        context = Mock(engines={}, jsonl="trials.jsonl")
        calls = []

        def trial(ctx, engine, case, state, **kw):
            calls.append((engine, kw))
            return {"correctness": {"ok": len(calls) != 1}, "metrics": {}}

        with patch.object(runner, "RunContext", return_value=context), \
                patch.object(runner, "run_one", side_effect=trial), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.cmd_baseline(args), 1)
        self.assertEqual(calls[0][1]["seed"], calls[1][1]["seed"])
        self.assertEqual(calls[2][1]["seed"], calls[3][1]["seed"])
        self.assertNotEqual(calls[0][1]["seed"], calls[2][1]["seed"])

    def test_noop_assigns_distinct_slots_on_one_engine(self):
        args = argparse.Namespace(a="ctrs", b="ctrs", seed=3, pairs=2,
                                  randomize=False, case="W1", state="warm",
                                  cold=False, concurrency=8, duration=20,
                                  write_ratio=0.3, noise_control=True)
        context = Mock(engines={}, jsonl="trials.jsonl")
        calls = []

        def trial(ctx, engine, case, state, **kw):
            calls.append((engine, kw))
            return {"correctness": {"ok": True}, "metrics": {}}

        with patch.object(runner, "RunContext", return_value=context), \
                patch.object(runner, "run_one", side_effect=trial), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.cmd_baseline(args), 0)
        self.assertEqual(context.design, "noise-control")
        self.assertEqual([(c[0], c[1]["slot"]) for c in calls],
                         [("ctrs", "a"), ("ctrs", "b"),
                          ("ctrs", "b"), ("ctrs", "a")])

    def test_noop_command_marks_noise_control(self):
        args = argparse.Namespace(engine="ctrs", pairs=3, case=None,
                                  state=None, cold=False, seed=None,
                                  concurrency=8, duration=15.0,
                                  write_ratio=0.3)
        with patch.object(runner, "cmd_baseline", return_value=0) as baseline:
            self.assertEqual(runner.cmd_noop(args), 0)
        self.assertTrue(args.noise_control)
        self.assertEqual((args.a, args.b), ("ctrs", "ctrs"))
        baseline.assert_called_once_with(args)

    def test_holdout_failure_is_not_exit_zero(self):
        args = argparse.Namespace(engines="ctrs,orbstack", ops=240, repos=8,
                                  issues=5, clones=4, seed=1)
        rec = {"correctness": {"ok": False}, "metrics": {}, "validation_errors": ["failed"]}
        with patch.object(runner, "RunContext", return_value=Mock(engines={}, jsonl="trials")), \
                patch.object(runner, "run_one", return_value=rec), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.cmd_holdout(args), 1)


class GuestProvenanceTests(unittest.TestCase):
    def test_guest_hashes_cached_by_stat_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "guest" / "out"
            out.mkdir(parents=True)
            for name in ("Image", "initramfs.cpio", "data.img"):
                (out / name).write_bytes(name.encode())
            work = Path(tmp) / "work"
            work.mkdir()
            with patch.object(runner, "REPO", Path(tmp)), \
                    patch.object(runner, "WORK", work), \
                    patch.object(runner, "sha256_file",
                                 side_effect=lambda p: "ab" * 32) as digest, \
                    patch.object(runner, "sha256_sparse_file",
                                 side_effect=lambda p: "cd" * 32) as sparse:
                first = runner.guest_provenance()
                second = runner.guest_provenance()
            self.assertEqual(first, second)
            self.assertEqual(set(first), {"guest_kernel_sha256",
                                          "guest_initramfs_sha256",
                                          "guest_data_sha256"})
            self.assertEqual(digest.call_count, 2)
            self.assertEqual(sparse.call_count, 1)
            self.assertEqual(first["guest_data_sha256"], "cd" * 32)
            self.assertTrue((work / "guest-asset-hashes.json").is_file())


class LoadMetricTests(unittest.TestCase):
    def test_throughput_counts_successes_and_attempts_separately(self):
        spec = importlib.util.spec_from_file_location("native_load", runner.LOAD_PY)
        load = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(load)

        def worker(wid, base, duration, write_ratio, rng_seed,
                   latencies, counts, stop, error_log, t_start):
            counts.update(reads=3, writes=2, errors=5)
            latencies.extend([1.0] * 5)

        output = io.StringIO()
        with patch.object(load, "worker", worker), \
                patch.object(sys, "argv", ["load.py", "--url", "http://unused",
                                            "--concurrency", "1"]), \
                contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as err:
                load.main()
        self.assertEqual(err.exception.code, 1)
        summary = json.loads(output.getvalue())
        self.assertEqual(summary["requests"], 10)
        self.assertEqual(summary["requests_ok"], 5)
        self.assertAlmostEqual(summary["attempted_rps"], 2 * summary["rps"], delta=0.02)

    def test_failed_requests_do_not_enter_success_latency(self):
        spec = importlib.util.spec_from_file_location("native_load", runner.LOAD_PY)
        load = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(load)
        stop = threading.Event()
        conn = Mock()
        conn.request.side_effect = lambda *a, **kw: stop.set()
        conn.getresponse.return_value.status = 503
        counts = {"reads": 0, "writes": 0, "errors": 0}
        latencies = []
        with patch.object(load.http.client, "HTTPConnection", return_value=conn):
            load.worker(0, ("unused", 80), 1, 0, 1, latencies, counts,
                        stop, [], 0)
        self.assertEqual(counts["errors"], 1)
        self.assertEqual(latencies, [])


if __name__ == "__main__":
    unittest.main()
