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
        return {"trial_id": self.run_id, "metrics": {}, "correctness": {"ok": True, "checks": {}},
                "resources": {}, "validation_errors": [], "notes": []}


def fake_engine(name="orbstack"):
    engine = Mock()
    engine.name = name
    engine.socket = f"unix:///bench/{name}.sock"
    engine.builder_name = f"np-dc-{name}-verified"
    engine.sh.return_value = completed()
    engine.compose.return_value = completed()
    return engine


class CleanupOwnershipTests(unittest.TestCase):
    def test_project_orphans_require_matching_label_and_identity(self):
        for label, identity, allowed in (("owned", "abc", True), ("other", "abc", False), ("owned", "other", False)):
            with self.subTest(label=label, identity=identity):
                engine = fake_engine()
                engine.sh.side_effect = [completed(), completed("abc\n"), completed(json.dumps([
                    {"Id": identity, "Config": {"Labels": {"com.docker.compose.project": label}}}]))] + ([completed()] if allowed else [])
                if allowed:
                    runner.compose_down(engine, "owned")
                else:
                    with self.assertRaisesRegex(RuntimeError, "exact project ownership"):
                        runner.compose_down(engine, "owned")
                commands = [call.args[0] for call in engine.sh.call_args_list]
                self.assertIn("label=com.docker.compose.project=owned", commands[1])
                self.assertFalse(any(arg.startswith("name=") for cmd in commands for arg in cmd))
                self.assertEqual([cmd for cmd in commands if cmd[0] == "rm"], [["rm", "-f", "--", "abc"]] if allowed else [])


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
    def test_w3_reports_complete_commits_and_rejects_corrupt_persisted_payload(self):
        timings = "SET\nTiming is on.\n" + "".join(
            f"BEGIN\nINSERT 0 1\nUPDATE 1\nCOMMIT\nTime: {i}.125 ms\n"
            for i in range(1, runner.W3_TXS + 1))
        rows = {"rows": [[i, f"v{i}"] for i in range(runner.W3_TXS)],
                "meta": [["txs", runner.W3_TXS]], "fsync": "on"}
        with tempfile.TemporaryDirectory() as tmp:
            engine = fake_engine()
            pin = json.loads((runner.FIXTURES / "w8-v5/portfolio.json").read_text())["images"]["np-v5/postgres"]
            volume_owner = "test-run-000001"

            def execute(args, **kwargs):
                if args[:2] == ["image", "inspect"]:
                    self.assertEqual(args[-1], pin["manifest"])
                    return completed(json.dumps([{"Id": pin["manifest"], "Architecture": "arm64",
                                                  "RootFS": {"Layers": pin["diff_ids"]}}]))
                if args[:2] == ["volume", "inspect"]:
                    return completed(json.dumps([{"Name": args[-1], "Labels": {"dev.ctrs.campaign.run": volume_owner}}]))
                if args[0] == "inspect":
                    return completed(json.dumps([{"Config": {"Labels": {"dev.ctrs.campaign.run": "test-run-000001"}}}]))
                if args[0] == "run":
                    self.assertIn("--pull=never", args)
                    self.assertEqual(args[-1], pin["manifest"])
                if "-tAc" in args:
                    return completed("1\n")
                if "-tA" in args:
                    return completed(json.dumps(rows))
                if args[-1] == "/tmp/txmix.sql":
                    self.assertIn("ON_ERROR_STOP=1", args)
                    self.assertIn("LC_ALL=C", args)
                    return completed(timings)
                if "du" in args:
                    return completed("12 /var/lib/postgresql/data\n")
                return completed()

            engine.sh.side_effect = execute

            @contextlib.contextmanager
            def resource_phase(engine, record, name):
                yield
                record["resources"].setdefault("phases", {})[name] = {"operation_wall_seconds": 2}

            with patch.object(runner, "start_sampler", return_value=(None, None)), \
                    patch.object(runner, "resource_phase", resource_phase), \
                    patch.object(runner.time, "monotonic", side_effect=iter(range(1000))), \
                    patch.object(runner.time, "sleep"):
                rec = runner.trial_w3(FixtureContext(tmp), engine, "warm")
                rows["rows"][25][1] = "wrong payload"
                bad_rows = runner.trial_w3(FixtureContext(tmp), engine, "warm")
                timings = timings.replace("COMMIT", "ROLLBACK", 1)
                bad_tx = runner.trial_w3(FixtureContext(tmp), engine, "warm")
                volume_owner = "another-run"
                engine.sh.reset_mock()
                unowned = runner.trial_w3(FixtureContext(tmp), engine, "warm")
                self.assertFalse(unowned["correctness"]["ok"])
                self.assertIn("W3 database volume ownership mismatch", unowned["validation_errors"][0])
                self.assertFalse(any(call.args[0][0] in ("run", "rm") or call.args[0][:2] == ["volume", "rm"]
                                     for call in engine.sh.call_args_list))

            self.assertTrue(rec["correctness"]["ok"], rec)
            self.assertEqual(rec["metrics"]["transaction_p95_ms"], 285.125)
            self.assertEqual(rec["metrics"]["tx_tps"], 150)
            self.assertFalse(bad_rows["correctness"]["checks"]["verify_rows"])
            self.assertFalse(bad_tx["correctness"]["checks"]["txmix"])
            self.assertNotIn("transaction_p95_ms", bad_tx["metrics"])
            statements = (Path(tmp) / "orbstack/W3/txmix.sql").read_text().splitlines()
            self.assertEqual(statements[:2], ["SET synchronous_commit = on;", r"\timing on"])
            self.assertEqual(len(statements[2:]), runner.W3_TXS)
            self.assertTrue(all(line.count(r"\;") == 3 and line.endswith("COMMIT;") for line in statements[2:]))

    def test_w6_compiles_both_apps_and_records_paired_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = FixtureContext(tmp)
            engine = fake_engine()
            probe_hashes = {
                "/src/target/release/hyperfine": "fcfbf31a7d309a79dba362d75310ead3eafc35d984248a197f5cfbd2dce09c3f",
                "/src/libz.a": "6b6ba12f2f7ed1e8c7ebe08480e408394c8e66aebec862a10494fb2dc415914b",
            }
            solves = []
            emit_reuse = True

            def run_command(args, **kw):
                if args[:2] == ["buildx", "build"]:
                    context = Path(args[args.index("-f") + 1]).parent
                    instruction = (context / "Dockerfile").read_text().strip().splitlines()[-1]
                    cached = emit_reuse and "--no-cache" not in args
                    vertex = {"name": "[stage-0 5/5] " + instruction,
                              "digest": "sha256:" + "f" * 64,
                              "started": "2026-11-17T12:00:00Z", "completed": "2026-11-17T12:00:02Z"}
                    if cached:
                        vertex["cached"] = True
                    solves.append((context.name, args, (context / "stamp.txt").read_bytes()))
                    return subprocess.CompletedProcess(args, 0, "", json.dumps({"vertexes": [vertex]}))
                return completed(f"{probe_hashes[args[-1]]}  {args[-1]}\n" if args[0] == "run" else "")

            engine.sh.side_effect = run_command
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
            @contextlib.contextmanager
            def resource_phase(engine, record, name):
                yield
                record["resources"].setdefault("phases", {})[name] = {"operation_wall_seconds": 3.5}

            def start_sampler(*args):
                solves.append(("sampling", None, None))
                return None, None

            with patch.object(runner, "W6_DIR", fixture), \
                    patch.object(runner, "W6_ZLIB_SOURCE", zlib_pin), \
                    patch.object(runner, "W6_RUST_SOURCE", rust_pin), \
                    patch.object(runner, "resource_phase", resource_phase), \
                    patch.object(runner, "start_sampler", return_value=(None, None)) as sampler:
                rec = runner.trial_w6(ctx, engine, "warm")
                good_hash = probe_hashes["/src/target/release/hyperfine"]
                probe_hashes["/src/target/release/hyperfine"] = "a" * 64
                bad_artifact = runner.trial_w6(ctx, engine, "warm")
                probe_hashes["/src/target/release/hyperfine"] = good_hash
                sampler.side_effect = start_sampler
                warm_build = runner.trial_w6(ctx, engine, "warm", build_cache="warm")
                emit_reuse = False
                missed_cache = runner.trial_w6(ctx, engine, "warm", build_cache="warm")
            self.assertTrue(rec["correctness"]["ok"], rec)
            self.assertFalse(bad_artifact["correctness"]["ok"], bad_artifact)
            self.assertFalse(bad_artifact["correctness"]["checks"]["artifact_rust"])
            self.assertTrue(bad_artifact["correctness"]["checks"]["artifact_zlib"])
            builds = [call.args[0] for call in engine.sh.call_args_list
                      if call.args[0][:2] == ["buildx", "build"]]
            self.assertEqual(len(builds), 12)
            self.assertTrue(all("--progress=rawjson" in b for b in builds))
            self.assertTrue(all(b[b.index("--platform") + 1] == "linux/arm64" for b in builds))
            self.assertTrue(all("--no-cache" in b for b in builds[:4]))
            self.assertEqual([step[0] for step in solves[4:9]],
                             ["ctx-rust", "ctx-zlib", "sampling", "ctx-rust", "ctx-zlib"])
            for prime, timed in zip(solves[4:6], solves[7:9], strict=True):
                self.assertEqual([arg for arg in prime[1] if arg != "--no-cache"], timed[1])
                self.assertEqual(prime[2], timed[2])
            self.assertTrue(warm_build["correctness"]["ok"], warm_build)
            self.assertEqual(warm_build["metrics"]["cache_mode"], "primed-build-cache")
            self.assertEqual(warm_build["metrics"]["build_rust_s"], 3.5)
            self.assertNotIn("prime_rust", warm_build["resources"]["phases"])
            self.assertFalse(missed_cache["correctness"]["ok"], missed_cache)
            self.assertIn("did not prove cached=True", missed_cache["validation_errors"][0])
            base = Path(tmp) / "orbstack/W6"
            for name in ("ctx-rust", "ctx-zlib"):
                self.assertEqual((base / name / "stamp.txt").read_text(),
                                 ctx.workload_id + "\n")
            first = runner.workload_id("run", "W6", 1, 1)
            self.assertEqual(first, runner.workload_id("run", "W6", 1, 2))
            self.assertNotEqual(first, runner.workload_id("run", "W6", 2, 3))

    def test_w6_compile_receipt_rejects_ambiguous_missing_and_failed_steps(self):
        instruction = "RUN compile"
        vertex = {"name": "[stage-0 5/5] " + instruction, "digest": "sha256:" + "a" * 64,
                  "started": "2026-11-17T12:00:00Z", "completed": "2026-11-17T12:00:02Z"}
        for vertices in ([], [dict(vertex, error="test failed")], [dict(vertex, completed=None)],
                         [dict(vertex, cached=True)], [vertex, dict(vertex, digest="sha256:" + "b" * 64)]):
            with self.subTest(vertices=vertices), self.assertRaises(ValueError):
                runner._buildkit_vertex(json.dumps({"vertexes": vertices}), instruction, cached=False)

    def test_missing_w6_asset_fails_before_starting_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = fake_engine()
            with patch.object(runner, "ensure_pinned_source",
                              side_effect=RuntimeError("checksum-pinned fetch failed")):
                rec = runner.trial_w6(FixtureContext(tmp), engine, "warm")
            self.assertFalse(rec["correctness"]["ok"])
            self.assertIn("checksum-pinned", rec["validation_errors"][0])
            engine.ensure_up.assert_not_called()

    def test_w9_completion_metrics_require_all_exact_jobs(self):
        image = "example/marked@" + runner.ci_jobs.IMAGE_DIGEST
        with tempfile.TemporaryDirectory() as tmp:
            class Context(FixtureContext):
                def new_record(self, *args):
                    return super().new_record(*args) | {"trial_id": "w9-trial"}

            engine = fake_engine()
            engine.sh.side_effect = lambda args, **kwargs: completed(
                json.dumps([{"Architecture": "arm64", "RepoDigests": [image]}])
                if args[:2] == ["image", "inspect"] else "")
            jobs = [{"name": f"owned-{n}", "completion_seconds": n / 10} for n in range(1, 17)]

            @contextlib.contextmanager
            def resource_phase(engine, record, name):
                try:
                    yield
                finally:
                    record["resources"].setdefault("phases", {})[name] = {"operation_wall_seconds": 2}

            with patch.object(runner, "resource_phase", resource_phase), \
                    patch.object(runner, "start_sampler", return_value=(None, None)), \
                    patch.object(runner.ci_jobs, "run_condition", return_value=jobs) as condition:
                successful = runner.trial_w9(Context(tmp), engine, "warm", image)
                condition.side_effect = runner.ci_jobs.ConditionFailed([
                    jobs[0] | {"job": 0, "error": "bad output"}])
                failed = runner.trial_w9(Context(tmp), engine, "warm", image)
            self.assertTrue(successful["correctness"]["ok"], successful)
            self.assertEqual(successful["metrics"]["successful_jobs_per_minute_at_4"], 480)
            self.assertEqual(successful["metrics"]["job_completion_p95_ms_at_4"], 1600)
            self.assertFalse(failed["correctness"]["ok"])
            self.assertNotIn("job_completion_p95_ms_at_1", failed["metrics"])
            raw = Path(tmp) / "orbstack/W9/jobs-at-1.json"
            self.assertEqual(json.loads(raw.read_text())[0]["completion_seconds"], .1)

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
            loaded = {}
            notes = []
            corrupt_warm = False
            miscached = False
            lost_ownership = False

            def respond(args, **kw):
                if args[:2] == ["buildx", "build"]:
                    tag = args[args.index("-t") + 1]
                    owner = args[args.index("--label") + 1].split("=", 1)[1]
                    context = Path(args[args.index("-f") + 1]).parent
                    loaded[tag] = owner, (context / "stamp/note.txt").read_text()
                    notes.append(loaded[tag][1])
                    app = "hyperfine" if "hyperfine" in tag else "httpie"
                    compile_cached = not tag.endswith("-uncached")
                    if miscached and app == "hyperfine" and tag.endswith("-incr"):
                        compile_cached = False
                    progress = {"vertexes": [
                        {"name": instruction, "digest": "sha256:" + digit * 64, "cached": cached,
                         "started": "2026-11-17T12:00:00Z", "completed": "2026-11-17T12:00:02Z"}
                        for instruction, digit, cached in (
                            (apps[app]["compile_step"], "a", compile_cached),
                            (runner.W7_NOTE_STEP, "b", tag.endswith("-warm")))]}
                    result = completed()
                    result.stderr = json.dumps(progress)
                    return result
                if args[0] == "run":
                    tag = args[3]
                    self.assertIn("--pull=never", args)
                    _, note = loaded[tag]
                    if "--version" in args:
                        return completed("hyperfine 2.0.0\n" if "hyperfine" in tag else "3.2.4\n")
                    if corrupt_warm and "hyperfine" in tag and tag.endswith("-warm"):
                        note = "wrong incremental-0\n"
                    return completed(note)
                if args[:3] == ["image", "inspect", "--format"]:
                    if lost_ownership and "httpie" in args[-1] and args[-1].endswith("-incr"):
                        return completed("different-owner\n")
                    return completed(loaded[args[-1]][0] + "\n")
                if args[:2] == ["image", "rm"]:
                    del loaded[args[-1]]
                return completed()
            engine.sh.side_effect = respond
            apps = {"hyperfine": dict(runner.W7_APPS["hyperfine"],
                                      source=rust_pin),
                    "httpie": dict(runner.W7_APPS["httpie"],
                                   source=httpie_pin)}
            @contextlib.contextmanager
            def resource_phase(engine, record, name):
                yield
                record["resources"].setdefault("phases", {})[name] = {"operation_wall_seconds": .5}

            with patch.object(runner, "W7_DIR", fixture), \
                    patch.object(runner, "W7_APPS", apps), \
                    patch.object(runner, "resource_phase", resource_phase), \
                    patch.object(runner, "start_sampler",
                                 return_value=(None, None)):
                rec = runner.trial_w7(FixtureContext(tmp), engine, "warm")
                stamp = hashlib.sha256(FixtureContext(tmp).workload_id.encode()).hexdigest()
                self.assertEqual(notes, [f"incremental-{i}:{stamp}\n" for i in (0, 0, 1)] * 2)
                commands = [call.args[0] for call in engine.sh.call_args_list]
                self.assertEqual(loaded, {})
                miscached = True
                bad_cache = runner.trial_w7(FixtureContext(tmp), engine, "warm")
                self.assertFalse(bad_cache["correctness"]["ok"])
                self.assertIn("did not prove cached=True", bad_cache["validation_errors"][0])
                self.assertNotIn("hyperfine_incr_first_use_s", bad_cache["metrics"])
                miscached = False
                corrupt_warm = lost_ownership = True
                bad = runner.trial_w7(FixtureContext(tmp), engine, "warm")
            self.assertTrue(rec["correctness"]["ok"], rec)
            self.assertFalse(bad["correctness"]["ok"], bad)
            self.assertNotIn("hyperfine_warm_first_use_s", bad["metrics"])
            self.assertNotIn("hyperfine_incr_s", bad["metrics"])
            self.assertTrue(any("ownership" in error for error in bad["validation_errors"]))
            self.assertEqual(len(loaded), 1)
            self.assertIn("httpie", next(iter(loaded)))
            self.assertFalse(any("prune" in command for command in commands))
            builds = [cmd for cmd in commands if cmd[:2] == ["buildx", "build"]]
            # 3 builds per app: uncached + warm + incremental.
            self.assertEqual(len(builds), 6)
            self.assertEqual(sum("--no-cache" in b for b in builds), 2)
            for app in ("hyperfine", "httpie"):
                for state in ("uncached", "warm", "incr"):
                    self.assertIn(f"{app}_{state}_s", rec["metrics"])
                    self.assertEqual(rec["metrics"][f"{app}_{state}_first_use_s"], .5)
            builds_and_runs = [command for command in commands
                               if command[:2] == ["buildx", "build"] or command[0] == "run"]
            self.assertEqual(len(builds_and_runs), 18)
            for index in range(0, len(builds_and_runs), 3):
                build, version, note = builds_and_runs[index:index + 3]
                tag = build[build.index("-t") + 1]
                self.assertEqual((version[3], note[3]), (tag, tag))

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
    def test_w2_baseline_serializes_sampling_mode_and_requires_pins(self):
        engine = fake_engine()
        engine.system_df.return_value = None
        context = Mock(run_id="one-run", _seq=0, engines={"orbstack": engine}, resource_lane="matched")

        def trial(ctx, engine, state, sampling=runner.SamplingMode.PERIODIC, pinned_stack=False):
            self.assertIs(sampling, runner.SamplingMode.PERIODIC)
            self.assertTrue(pinned_stack)
            json.dumps(ctx.workload_params)
            return {"correctness": {"ok": True}, "resources": {}, "validation_errors": []}

        with patch.object(runner, "trial_w2", trial), \
                patch.object(runner, "safe_version", return_value="observed"), \
                patch.object(runner, "safe_engine_info", return_value=None):
            runner.run_one(context, "orbstack", "W2", "warm", pair_id=1)
        self.assertEqual(context.workload_params["sampling"], "periodic")
        self.assertTrue(context.workload_params["pinned_stack"])

    def test_record_captures_executed_defaults_and_post_trial_version(self):
        engine = fake_engine()
        context = Mock(run_id="one-run", _seq=0, engines={"orbstack": engine}, resource_lane="matched")

        def trial(ctx, engine, state, duration=300.0, window=30.0, seed=1):
            return {"correctness": {"ok": True}, "resources": {}, "validation_errors": []}

        with patch.object(runner, "trial_w11", trial), \
                patch.object(runner, "safe_version", return_value="observed-after-start"), \
                patch.object(runner, "safe_engine_info", return_value=None):
            rec = runner.run_one(context, "orbstack", "W11", "warm",
                                 pair_id=1, order_index=0, duration=10.0, seed=4)
        self.assertEqual(context.workload_params,
                         {"cold": False, "duration": 10.0, "window": 30.0, "seed": 4,
                          "resource_lane": "matched"})
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
    def test_guest_override_uses_selected_assets_even_with_matching_size_and_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            default = repo / "guest/out"
            override = repo / "override"
            work = repo / "work"
            default.mkdir(parents=True)
            override.mkdir()
            work.mkdir()
            for directory, kernel in ((default, b"old"), (override, b"new")):
                for name, data in (("Image", kernel), ("initramfs.cpio", b"initrd"),
                                   ("data.img", b"disk")):
                    path = directory / name
                    path.write_bytes(data)
                    os.utime(path, ns=(1700000000000000000, 1700000000000000000))
            with patch.object(runner, "REPO", repo), patch.object(runner, "WORK", work):
                with patch.dict(os.environ, {"CTRS_GUEST_DIR": "guest/out"}):
                    baseline = runner.guest_provenance()
                with patch.dict(os.environ, {"CTRS_GUEST_DIR": "override"}):
                    selected = runner.guest_provenance()
                self.assertEqual(baseline["guest_kernel_sha256"], runner.sha256_file(default / "Image"))
                self.assertEqual(selected["guest_kernel_sha256"], runner.sha256_file(override / "Image"))

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
                    patch.dict(os.environ, {"CTRS_GUEST_DIR": "guest/out"}), \
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
                   latencies, counts, stop, error_log, t_start, **kwargs):
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
