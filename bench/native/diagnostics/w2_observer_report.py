"""Check the W2 leaf profiler's effect on API CPU and workload wall time."""

import argparse
import json
import math
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reporting import FOREIGN_CORES, bootstrap_ci

ENGINES = ("ctrs", "orbstack")
MODES = ("off", "on")
METRICS = {"application_cpu": "application_cpu_relative", "workload_wall": "workload_wall_relative"}
BLOCKS = 10
OUTSIDE_CPU_ADMISSION = "outside-engine-workload-cpu-v1"


def read_object(path):
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def measurements(directory, mode, plan):
    row = read_object(directory / "result.json")
    if (row.get("mode") != mode or row.get("correctness") is not True or row.get("errors") != []
            or row.get("cleanup_errors") != [] or row.get("successful_operations") != plan["operations"]
            or row.get("effective_client_location") != plan["requested_client_location"]
            or any(row.get(key) != plan[key] for key in (
                "fixture_version", "profile_kind", "profile_identity", "client_image_sha256",
                "client_source_sha256", "concurrency", "seed"))):
        raise ValueError(f"{directory} has invalid workload or cleanup evidence")
    outside_cpu_admission = plan.get("host_admission") == OUTSIDE_CPU_ADMISSION
    expected_gate_status = (0, 75) if outside_cpu_admission else (0,)
    for boundary in ("before", "after"):
        if read_object(directory / f"{boundary}-gate.json").get("exit") not in expected_gate_status:
            raise ValueError(f"{directory} failed its {boundary} host gate")
    if outside_cpu_admission:
        host_cpu = row.get("host_cpu") or {}
        outside = host_cpu.get("foreign_cpu_cores")
        if host_cpu.get("errors") != [] or not number(outside) or outside > FOREIGN_CORES:
            raise ValueError(f"{directory} lacks a valid outside-engine CPU receipt within {FOREIGN_CORES} cores")
    if mode == "on":
        profile = row.get("cpu_profile") or {}
        if profile.get("status") != "ok" or profile.get("raw_event_coverage_checked") is not True:
            raise ValueError(f"{directory} has invalid sample coverage")
    cpu = row["application_cpu"]
    seconds, bound = cpu["cpu_seconds"], cpu["counter_quantization_bound_cpu_seconds"]
    wall = row["workload_wall_seconds"]
    if (cpu.get("status") != "ok" or cpu.get("errors") != []
            or not all(number(value) for value in (seconds, bound, wall))
            or not 0 < bound < seconds or wall <= 0):
        raise ValueError(f"{directory} has invalid CPU or wall-time counters")
    counts = row["reads_ok"], row["writes_ok"]
    if any(type(count) is not int or count < 0 for count in counts) or sum(counts) != plan["operations"]:
        raise ValueError(f"{directory} has invalid operation counts")
    return counts, {"application_cpu": (seconds, bound), "workload_wall": (wall, 0)}


def block_ratios(directory, index, expected_plan):
    plan = read_object(directory / "plan.json")
    engines, modes = plan.pop("engine_order"), plan.pop("mode_order")
    odd = index % 2 == 1
    expected_engines = ENGINES if odd else ENGINES[::-1]
    expected_modes = MODES if odd else MODES[::-1]
    if tuple(engines) != expected_engines or tuple(modes) != expected_modes:
        raise ValueError("engine and mode orders must alternate from the declared opening block")
    if (plan.get("profile_kind") != "cpu-leaf" or plan.get("operations") != 50000
            or plan.get("requested_client_location") != "guest" or plan.get("concurrency") != 8
            or plan.get("host_admission") not in (None, OUTSIDE_CPU_ADMISSION)
            or any(plan["observer_confirmation_budget"][key] != .05 for key in METRICS.values())):
        raise ValueError("expected the declared 50k guest leaf workload and 5% budgets")
    if expected_plan is not None and plan != expected_plan:
        raise ValueError("plan inputs differ from the opening block")
    observations = {}
    workloads = set()
    for engine in ENGINES:
        work_off, off = measurements(directory / engine / "off", "off", plan)
        work_on, on = measurements(directory / engine / "on", "on", plan)
        workloads.update((work_off, work_on))
        observations[engine] = {}
        for metric, (value, bound) in on.items():
            base, base_bound = off[metric]
            observations[engine][metric] = (value / base, (value - bound) / (base + base_bound),
                                           (value + bound) / (base - base_bound))
    if len(workloads) != 1:
        raise ValueError("verified read/write counts differ across legs")
    return plan, observations


def assess(directories):
    accepted = []
    rejected = []
    first_plan = None
    seen = set()
    for index, directory in enumerate(directories, start=1):
        try:
            resolved = directory.resolve()
            if resolved in seen:
                raise ValueError("duplicate block directory")
            seen.add(resolved)
            plan, observations = block_ratios(directory, index, first_plan)
            if first_plan is None:
                first_plan = plan
        except (OSError, ValueError, KeyError, TypeError) as exc:
            rejected.append({"block": index, "directory": str(directory), "reason": str(exc)})
        else:
            accepted.append(observations)

    metrics = {}
    complete = len(accepted) == BLOCKS and not rejected
    for engine in ENGINES:
        metrics[engine] = {}
        for metric in METRICS:
            samples = [block[engine][metric] for block in accepted]
            if not samples:
                continue
            ratios, lows, highs = zip(*samples, strict=True)
            entry = {"median_on_off_ratio": statistics.median(ratios), "status": "incomplete"}
            if len(samples) > 1:
                low, high = bootstrap_ci(lows)[0], bootstrap_ci(highs)[1]
                entry["ci95_with_quantization"] = [low, high]
                if complete:
                    entry["status"] = "inconclusive"
                    if low >= .95 and high <= 1.05:
                        entry["status"] = "within-budget"
                    if low > 1.05 or high < .95:
                        entry["status"] = "outside-budget"
            metrics[engine][metric] = entry
    return {"expected_blocks": BLOCKS, "accepted_blocks": len(accepted), "rejected_blocks": rejected,
            "metrics": metrics, "host_process_review_required": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     epilog="Example: w2_observer_report.py results/BLOCK1 results/BLOCK2")
    parser.add_argument("blocks", metavar="BLOCK", type=Path, nargs="*",
                        help="receipt directories in attempted order, starting at block 1")
    args = parser.parse_args()
    if not args.blocks:
        parser.print_help()
        return 0
    if len(args.blocks) > BLOCKS:
        parser.error(f"expected at most {BLOCKS} attempted blocks")
    report = assess(args.blocks)
    print(json.dumps(report, indent=2))
    return int(report["accepted_blocks"] != BLOCKS or any(
        result["status"] != "within-budget"
        for metrics in report["metrics"].values() for result in metrics.values()))


if __name__ == "__main__":
    raise SystemExit(main())
