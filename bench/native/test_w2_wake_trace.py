import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "diagnostics"))
import w2_wake_trace

TRACE = """LOST 0
# tracer: nop
          python-40      [001] d..2.   100.000000: sched_switch: prev_comm=swapper/1 prev_pid=0 prev_prio=120 prev_state=R ==> next_comm=python next_pid=40 next_prio=120
          <idle>-0       [002] d..2.   100.000100: sched_switch: prev_comm=python prev_pid=41 prev_prio=120 prev_state=S ==> next_comm=swapper/2 next_pid=0 next_prio=120
          python-40      [001] d..3.   100.000200: sched_waking: comm=python pid=41 prio=120 target_cpu=002
          python-40      [001] d..3.   100.000210: ipi_send_cpu: cpu=2 callsite=ttwu_queue_wakelist+0x8c/0xd0 callback=0x0
          python-40      [001] d..3.   100.000300: sched_waking: comm=postgres pid=50 prio=120 target_cpu=001
          python-40      [001] d..3.   100.000400: sched_waking: comm=redis pid=60 prio=120 target_cpu=003
          python-40      [001] d..3.   100.000500: sched_wake_idle_without_ipi: cpu=2
          <idle>-0       [002] d.h2.   100.001000: sched_wakeup: comm=python pid=41 prio=120 target_cpu=002
"""


class WakeTraceTests(unittest.TestCase):
    def test_classifies_wake_targets_and_ipi_callsites(self):
        summary = w2_wake_trace.analyze(TRACE)
        self.assertTrue(summary["valid"])
        self.assertEqual(summary["wakes"], {"remote-idle": 1, "same-cpu": 1, "remote-unknown": 1})
        self.assertEqual(summary["ipi_callsites"], {"ttwu_queue_wakelist": 1})
        self.assertEqual(summary["ipi_sender_comms"], {"python": 1})
        self.assertEqual(summary["events"]["sched_wake_idle_without_ipi"], 1)
        self.assertAlmostEqual(summary["window_seconds"], 0.001)
        scaled = w2_wake_trace.per_success(summary, rps=2000)
        self.assertEqual(scaled["operations_estimate"], 2)
        self.assertEqual(scaled["wakes"]["remote-idle"], 0.5)

    def test_overrun_or_missing_receipt_never_counts_as_complete(self):
        self.assertFalse(w2_wake_trace.analyze(TRACE.replace("LOST 0", "LOST 7"))["valid"])
        with self.assertRaises(ValueError):
            w2_wake_trace.analyze(TRACE.replace("LOST 0\n", ""))

    def test_script_uses_and_removes_only_its_instance(self):
        for missing in (None, "event", "cpu loss counter"):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "tracefs"
                (root / "instances").mkdir(parents=True)
                (root / "events").mkdir()
                global_trace = root / "trace"
                global_trace.write_text("another reader's trace\n")
                template = Path(tmp) / "template"
                (template / "per_cpu/cpu0").mkdir(parents=True)
                (template / "per_cpu/cpu0/stats").write_text("overrun: 0\ndropped events: 0\n")
                if missing == "cpu loss counter":
                    (template / "per_cpu/cpu1").mkdir()
                    (template / "per_cpu/cpu1/stats").write_text("overrun: 0\n")
                (template / "trace").write_text(TRACE[7:])
                events = w2_wake_trace.EVENTS[:-1] if missing == "event" else w2_wake_trace.EVENTS
                for event in events:
                    enable = template / "events" / event / "enable"
                    enable.parent.mkdir(parents=True)
                    enable.write_text("0\n")
                audit = Path(tmp) / "removed"
                script = w2_wake_trace.trace_script(2.0).replace(
                    "T=/sys/kernel/tracing", 'T="$TRACE_ROOT"')
                shell = """mkdir() { cp -R "$TRACE_TEMPLATE" "$1"; }
rmdir() { mv "$1" "$TRACE_AUDIT"; }
sleep() { [ "$1" = 2 ]; }
"""
                result = subprocess.run(
                    ["sh", "-c", shell + script], capture_output=True, text=True,
                    env=dict(os.environ, TRACE_ROOT=str(root), TRACE_TEMPLATE=str(template),
                             TRACE_AUDIT=str(audit)),
                )
                self.assertEqual(result.returncode == 0, missing is None, result.stderr)
                self.assertEqual(list((root / "instances").iterdir()), [])
                self.assertEqual(global_trace.read_text(), "another reader's trace\n")
                self.assertEqual((audit / "trace_clock").read_text(), "mono\n")
                self.assertEqual((audit / "tracing_on").read_text(), "0\n")
                if missing is None:
                    self.assertTrue(w2_wake_trace.analyze(result.stdout)["valid"])
                else:
                    self.assertNotIn("LOST", result.stdout)


if __name__ == "__main__":
    unittest.main()
