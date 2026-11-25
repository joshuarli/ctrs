import os
import pathlib
import subprocess
import tempfile
import unittest


class ConformanceRunnerTest(unittest.TestCase):
    def test_unknown_selector_fails(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        result = subprocess.run(
            ["bash", "conformance/run.sh", "__no_such_fixture__"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("0 fixtures", result.stdout)

    def test_isolation_requires_containers_to_run(self):
        root = pathlib.Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temp:
            work = pathlib.Path(temp)
            tools = {
                "perl": '#!/bin/sh\nshift 2\nexec "$@"\n',
                "docker": """#!/bin/sh
case "$1" in
    pull) exit 0 ;;
    run)
        if [ "$ISOLATION_TEST_STATUS" -ne 0 ]; then
            echo 'stub container launch failed' >&2
        fi
        if [ "$ISOLATION_TEST_LEAK" = 'yes' ] && [ "$3" = '--privileged' ]; then
            echo 'CTRS_SOCKET=/unexpected.sock'
        fi
        exit "$ISOLATION_TEST_STATUS" ;;
    *) exit 99 ;;
esac
""",
                "python3": """#!/bin/sh
[ "$1" = '-c' ] || exit 99
case "$3" in
    "$CTRS_SOCKET") echo 600 ;;
    "$CTRS_DATA_DIR") echo 700 ;;
    *) echo 755 ;;
esac
""",
            }
            for name, source in tools.items():
                tool = work / name
                tool.write_text(source)
                tool.chmod(0o700)
            data = work / "data"
            data.mkdir()
            env = os.environ | {
                "PATH": str(work) + os.pathsep + os.environ["PATH"],
                "CTRS_SOCKET": str(work / "docker.sock"),
                "CTRS_DATA_DIR": str(data),
            }
            cases = ((0, "no", 0, "5 pass, 0 fail", None),
                     (125, "no", 1, "2 pass, 3 fail", "docker run exited 125"),
                     (0, "yes", 1, "4 pass, 1 fail", "CTRS_SOCKET=/unexpected.sock"))
            for launch_status, leak, exit_code, summary, detail in cases:
                with self.subTest(launch_status=launch_status, leak=leak):
                    result = subprocess.run(
                        ["bash", "conformance/isolation.sh"],
                        cwd=root,
                        env=env | {"ISOLATION_TEST_STATUS": str(launch_status), "ISOLATION_TEST_LEAK": leak},
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, exit_code, result.stdout)
                    self.assertIn(f"isolation: {summary}", result.stdout)
                    if detail:
                        self.assertIn(detail, result.stdout)
