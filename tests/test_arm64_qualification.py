import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = (ROOT / "tests/arm64-build.sh").read_text()


def shell_function(name):
    return name + "() {" + RUNNER.split(name + "() {", 1)[1].split("\n}\n", 1)[0] + "\n}\n"


def run_shell(function, body, *args):
    return subprocess.run(
        ["bash", "-uc", 'ok() { echo "ok $*"; }; miss() { echo "MISS $*"; };\n'
         + shell_function(function) + body, "test", *map(str, args)],
        capture_output=True, text=True, check=False,
    )


class OciInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / ".work/tmp")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "blobs/sha256").mkdir(parents=True)

    def blob(self, value):
        data = json.dumps(value).encode()
        digest = hashlib.sha256(data).hexdigest()
        (self.root / "blobs/sha256" / digest).write_bytes(data)
        return "sha256:" + digest

    def index(self, nested=False, config_arch="arm64"):
        manifests = []
        for arch in ("amd64", "arm64"):
            config = self.blob({"os": "linux", "architecture": arch if arch == "amd64" else config_arch})
            manifest = self.blob({"config": {"digest": config}})
            manifests.append({"digest": manifest, "platform": {"os": "linux", "architecture": arch}})
        index = {"manifests": manifests}
        if nested:
            index = {"manifests": [{"mediaType": "application/vnd.oci.image.index.v1+json", "digest": self.blob(index)}]}
        (self.root / "index.json").write_text(json.dumps(index))

    def inspect(self, body='inspect_oci_export "$1"'):
        return run_shell("inspect_oci_export", body, self.root)

    def test_flat_and_nested_platforms_and_configs(self):
        for nested in (False, True):
            with self.subTest(nested=nested):
                self.index(nested=nested)
                result = self.inspect()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("OCI index carries linux/amd64 and linux/arm64 entries", result.stdout)
                self.assertIn("OCI amd64 manifest config is linux/amd64", result.stdout)
                self.assertIn("OCI arm64 manifest config is linux/arm64", result.stdout)

    def test_empty_index_is_an_explicit_failure(self):
        (self.root / "index.json").write_text('{"manifests": []}')
        result = self.inspect()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no platform entries or readable nested index", result.stdout)

    def test_malformed_json_is_an_explicit_failure(self):
        (self.root / "index.json").write_text("{")
        result = self.inspect()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("OCI index parsing failed", result.stdout)

    def test_missing_blob_is_an_explicit_failure(self):
        self.index()
        for blob in (self.root / "blobs/sha256").iterdir():
            blob.unlink()
        result = self.inspect()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("OCI amd64 config lookup failed", result.stdout)
        self.assertNotIn("manifest config is /", result.stdout)

    def test_wrong_architecture_is_not_accepted(self):
        self.index(config_arch="amd64")
        result = self.inspect()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MISS OCI arm64 manifest config is linux/amd64", result.stdout)

    def test_missing_parser_is_an_explicit_failure(self):
        result = self.inspect('PATH=/nonexistent; inspect_oci_export "$1"')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("OCI inspection requires jaq on PATH", result.stdout)


class BuilderReadinessTests(unittest.TestCase):
    def test_ready_builder_succeeds(self):
        result = run_shell("wait_builder_ready", 'isoc() { echo workers; }; wait_builder_ready managed 0')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("MISS", result.stdout)

    def test_starting_builder_is_probed_until_ready(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".work/tmp") as temp:
            result = run_shell("wait_builder_ready", '''
marker=$1/marker
isoc() {
  if [ ! -f "$marker" ]; then
    touch "$marker"
    echo socket-not-ready >&2
    return 1
  fi
  echo workers
}
wait_builder_ready managed 5
''', temp)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("MISS", result.stdout)

    def test_timeout_reports_error_state_and_logs(self):
        result = run_shell("wait_builder_ready", '''
isoc() {
  case "$*" in
    *exec*) echo socket-not-ready >&2; return 1 ;;
    *inspect*) echo container-state ;;
    *logs*) echo container-logs ;;
  esac
}
wait_builder_ready managed 0
''')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MISS builder did not answer after docker restart within 0s; last probe: socket-not-ready", result.stdout)
        self.assertIn("container-state", result.stdout)
        self.assertIn("container-logs", result.stdout)

    def test_empty_probe_error_is_explicit(self):
        result = run_shell("wait_builder_ready", 'isoc() { return 1; }; wait_builder_ready managed 0')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("last probe: no output", result.stdout)


class CompatibilityGuardTests(unittest.TestCase):
    def test_prior_case_failure_does_not_block_compatibility(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".work/tmp") as temp:
            binary = Path(temp) / "ctrs"
            binary.touch()
            binary.chmod(0o755)
            for failures in (0, 1):
                result = run_shell("case_compatibility", '''
ROOT=$1
BIN=$2
FAIL=$3
REQUIRE_NO_BINFMT=0
source() { echo reached-harness; exit 0; }
case_compatibility
''', ROOT, temp, failures)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("reached-harness", result.stdout)

    def test_missing_fixtures_still_block_compatibility(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".work/tmp") as temp:
            result = run_shell("case_compatibility", '''
ROOT=$1
FAIL=1
miss() { FAIL=$((FAIL + 1)); echo "MISS $*"; }
source() { echo reached-harness; exit 0; }
case_compatibility
''', temp)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("MISS fixture", result.stdout)
        self.assertNotIn("reached-harness", result.stdout)


if __name__ == "__main__":
    unittest.main()
