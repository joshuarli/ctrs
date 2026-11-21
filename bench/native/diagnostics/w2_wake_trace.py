"""Trace W2 wakeup placement and IPI senders in one bounded guest window.

Runs one normal pinned W2 trial per engine. A fixed delay after the workload
phase starts, the trial's privileged counter reader enables ipi and sched
tracepoints through tracefs for a fixed window, then restores the guest's
tracing state. Ring-buffer overruns invalidate the window. Timings from a
traced trial are diagnostic only; the observer perturbs the workload.
"""
import argparse
import collections
import contextlib
import json
import re
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runner

EVENTS = ("ipi/ipi_send_cpu", "ipi/ipi_send_cpumask", "sched/sched_waking",
          "sched/sched_wakeup", "sched/sched_switch", "sched/sched_wake_idle_without_ipi")
TRACE_BUFFER_KB = 32768
LINE = re.compile(r"^\s*(?P<comm>.+?)-(?P<pid>\d+)\s+\[(?P<cpu>\d+)\]\s+\S+\s+"
                  r"(?P<ts>\d+\.\d+):\s+(?P<event>\w+):\s+(?P<body>.*)$")
FIELD = re.compile(r"(\w+)=(\S+)")

TRACE_SCRIPT = r"""set -eu
T=/sys/kernel/tracing
[ -d "$T/events" ] || mount -t tracefs nodev "$T"
cd "$T"
[ "$(cat current_tracer)" = nop ] || { echo "tracer already in use" >&2; exit 3; }
[ -z "$(cat set_event)" ] || { echo "events already enabled" >&2; exit 3; }
original=$(cat buffer_size_kb | cut -d' ' -f1)
was_on=$(cat tracing_on)
restore() { echo 0 > tracing_on; for e in EVENTS; do echo 0 > "events/$e/enable"; done; echo > trace; echo "$original" > buffer_size_kb; echo "$was_on" > tracing_on; }
trap restore EXIT
echo 0 > tracing_on
echo > trace
echo BUFFER > buffer_size_kb
for e in EVENTS; do echo 1 > "events/$e/enable"; done
echo 1 > tracing_on
sleep WINDOW
echo 0 > tracing_on
cat per_cpu/cpu*/stats | grep -E '^(overrun|dropped events):' | awk '{s+=$NF} END {print "LOST", s+0}'
cat trace
"""


def trace_script(window: float) -> str:
    return (TRACE_SCRIPT.replace("EVENTS", " ".join(EVENTS))
            .replace("BUFFER", str(TRACE_BUFFER_KB)).replace("WINDOW", f"{window:g}"))


def _callsite(value: str) -> str:
    return value.split("+", 1)[0]


def analyze(text: str) -> dict:
    lost = None
    running: dict[int, int] = {}
    wakes = collections.Counter()
    wake_targets = collections.Counter()
    ipis = collections.Counter()
    ipi_senders = collections.Counter()
    events = collections.Counter()
    first = last = None
    for line in text.splitlines():
        if line.startswith("LOST "):
            lost = int(line.split()[1])
            continue
        match = LINE.match(line)
        if match is None:
            continue
        cpu = int(match["cpu"])
        ts = float(match["ts"])
        first = ts if first is None else first
        last = ts
        event = match["event"]
        events[event] += 1
        fields = dict(FIELD.findall(match["body"]))
        if event == "sched_switch":
            running[cpu] = int(fields["next_pid"])
        elif event == "sched_waking":
            target = int(fields["target_cpu"])
            if target == cpu:
                kind = "same-cpu"
            elif target not in running:
                kind = "remote-unknown"
            else:
                kind = "remote-idle" if running[target] == 0 else "remote-busy"
            wakes[kind] += 1
            wake_targets[fields["comm"]] += 1
        elif event in ("ipi_send_cpu", "ipi_send_cpumask"):
            ipis[_callsite(fields["callsite"])] += 1
            ipi_senders[match["comm"]] += 1
    if lost is None:
        raise ValueError("trace has no overrun/dropped-event receipt")
    seconds = (last - first) if first is not None and last is not None else 0.0
    return {"lost_events": lost, "valid": lost == 0 and seconds > 0,
            "window_seconds": seconds, "events": dict(events),
            "wakes": dict(wakes), "wake_targets": dict(wake_targets.most_common(8)),
            "ipi_callsites": dict(ipis.most_common(12)),
            "ipi_sender_comms": dict(ipi_senders.most_common(8))}


def per_success(summary: dict, rps: float) -> dict:
    operations = rps * summary["window_seconds"]
    if operations <= 0:
        return {}
    scale = lambda counts: {key: round(value / operations, 3) for key, value in counts.items()}
    return {"operations_estimate": round(operations), "events": scale(summary["events"]),
            "wakes": scale(summary["wakes"]), "ipi_callsites": scale(summary["ipi_callsites"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engines", default="ctrs,orbstack")
    parser.add_argument("--operations", type=int, default=50000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--delay", type=float, default=6.0, help="seconds after workload start")
    parser.add_argument("--window", type=float, default=2.0)
    parser.add_argument("--resource-lane", choices=runner.RESOURCE_LANES, default="matched")
    parser.add_argument("--client-location", choices=("host", "guest"), default="host")
    args = parser.parse_args()
    engines = args.engines.split(",")
    if set(engines) - {"ctrs", "orbstack", "dockerd"} or len(set(engines)) != len(engines):
        parser.error("engines must be distinct ctrs/orbstack names")
    if not 0 < args.window <= 5:
        parser.error("window must be within (0, 5] seconds")
    runner.DOCKER = runner.find_docker()
    ctx = runner.RunContext(f"wake-{time.strftime('%Y%m%dT%H%M%S')}")
    ctx.resource_lane = args.resource_lane
    original_phase = runner.resource_phase
    traces: dict[str, dict] = {}

    @contextlib.contextmanager
    def traced_phase(engine, rec, name):
        with original_phase(engine, rec, name):
            if name != "workload":
                yield
                return
            reader = runner.project_name(ctx.run_id, engine.name, "W2") + "-counters"

            def capture():
                time.sleep(args.delay)
                cp = engine.sh(["exec", reader, "sh", "-c", trace_script(args.window)],
                               timeout=120, check=False)
                traces[engine.name] = {"returncode": cp.returncode, "stdout": cp.stdout,
                                       "stderr": cp.stderr[-2000:]}

            worker = threading.Thread(target=capture, daemon=True)
            worker.start()
            try:
                yield
            finally:
                worker.join(timeout=args.delay + args.window + 120)

    failed = False
    runner.resource_phase = traced_phase
    try:
        for index, name in enumerate(engines):
            rec = runner.run_one(ctx, name, "W2", "warm", pair_id=1, order_index=index,
                                 keep_warm=True, slot=name, concurrency=8, duration=20.0,
                                 write_ratio=0.3, seed=args.seed, operations=args.operations,
                                 client_location=args.client_location)
            trace = traces.get(name)
            out = {"engine": name, "trial_correct": rec["correctness"]["ok"],
                   "validation_errors": rec.get("validation_errors"),
                   "rps": rec["metrics"].get("rps"), "guest_cpus": (rec["resources"].get("engine") or {}).get("ncpu")}
            if trace is None or trace["returncode"] != 0:
                out["trace_error"] = trace["stderr"] if trace else "trace never ran"
                failed = True
            else:
                (ctx.results_dir / f"{name}-trace.txt").write_text(trace["stdout"])
                out["trace"] = analyze(trace["stdout"])
                out["per_success"] = per_success(out["trace"], out["rps"] or 0)
                failed |= not out["trace"]["valid"]
            failed |= not out["trial_correct"]
            (ctx.results_dir / f"{name}-wake.json").write_text(json.dumps(out, indent=2) + "\n")
            print(json.dumps(out, indent=2), flush=True)
    finally:
        runner.resource_phase = original_phase
        for engine in ctx.engines.values():
            engine.stop()
    print(f"results: {ctx.results_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
