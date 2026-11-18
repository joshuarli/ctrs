import sys
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

    def test_script_restores_original_tracing_state(self):
        script = w2_wake_trace.trace_script(2.0)
        self.assertIn('echo "$was_on" > tracing_on', script)
        self.assertIn("sleep 2\n", script)
        self.assertNotIn("EVENTS", script)


if __name__ == "__main__":
    unittest.main()
