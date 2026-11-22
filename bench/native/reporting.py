"""Offline descriptive reporting; pairing/statistics alone never qualify a win.

All reports remain pilot evidence until asset, workload, binary-provenance and
host-isolation qualification. This module has no Docker/runtime dependency.
"""
from __future__ import annotations

import json
import math
import random
import re
import statistics
import resource_cells
from pathlib import Path

import ci_jobs
from watch_loop import RECEIPT_VERSION as W5_RECEIPT_VERSION

MIN_PAIRS = 10
W8_PAIRED_FIXTURE = 'w8-paired-v1'
W9_CONCURRENCIES = ci_jobs.SPEC['concurrency']
W9_THROUGHPUT = "successful_jobs_per_minute_at_"
JOB_RESOURCE_FIELDS = (("cpu_seconds_per_job", "cpu_seconds"),
                       ("peak_phys_footprint_bytes", "peak_phys_footprint_bytes"))
W4_RESOURCE_METRICS = {
    f"workers_{count}_{metric}": (count, field)
    for count in (1, 4, 16)
    for metric, field in JOB_RESOURCE_FIELDS
}
W9_RESOURCE_METRICS = {
    f"jobs_at_{count}_{metric}": (count, field)
    for count in W9_CONCURRENCIES
    for metric, field in JOB_RESOURCE_FIELDS
}
W5_MODE_RESOURCES = ("cpu_seconds_per_edit", "peak_phys_footprint_bytes")
W5_RESOURCE_METRICS = tuple(f"{mode}_{metric}" for mode in ("bind", "volume")
                            for metric in W5_MODE_RESOURCES)
CASE_METRICS = {
    "W1": ["wall_seconds", "time_to_health_s", "time_to_roundtrip_s", "db_restart_to_verified_s"],
    "W2": ["rps", "p50_ms", "p95_ms", "p99_ms", "cpu_seconds_per_success"],
    "W3": ["tx_tps", "transaction_p95_ms", "up_s", "migrate_s", "txmix_s", "checkpoint_s",
           "restart_s", "pgdata_allocated_bytes", "engine_cpu_per_success"],
    "W3-v4": ["init_s", "rw_tps", "rw_p50_ms", "rw_p95_ms", "rw_p99_ms", "ro_tps", "ro_p99_ms", "checkpoint_s", "restart_s", "pgdata_allocated_bytes", "db_size_bytes"],
    "W4": [metric for count in (1, 4, 16) for metric in
           (f"workers_{count}_s", f"queue_p95_ms_at_{count}", f"queue_p99_ms_at_{count}")] + list(W4_RESOURCE_METRICS),
    "W5": ["bind_edit_to_result_median_s", "volume_edit_to_result_median_s"],
    "W6": ["build_rust_s", "build_zlib_s"],
    "W7": [f"{app}_{state}{suffix}_s" for app in ("hyperfine", "httpie")
           for state in ("uncached", "warm", "incr") for suffix in ("", "_first_use")],
    "W8": ["pull_wall_seconds", "load_rps", "load_p95_ms", "load_p99_ms"],
    "W9": [metric for concurrency in W9_CONCURRENCIES
           for metric in (f"fixed16_at_{concurrency}_s", f"{W9_THROUGHPUT}{concurrency}",
                          f"job_completion_p95_ms_at_{concurrency}")] + list(W9_RESOURCE_METRICS),
    # Legacy load_rps counts failed attempts during downtime, not useful work.
    "W10": ["recovery_s", "recovered_p99_ms", "engine_cpu_per_success"],
    # Soak windows/requests/churn counts are reliability observations.
    "W11": [],
    "W12": ["workflow_seconds", "install_seconds", "build_seconds", "typecheck_seconds",
            "test_discovery_seconds", "warm_rebuild_seconds", "multi_file_change_seconds",
            "branch_switch_seconds"],
    # Watch latency is observed through host exec polling; missed/stale counts are reported, not scored.
    "W12-watch": ["edit_to_result_p50_s", "edit_to_result_p95_s"],
    "W13-overlap": ["w2_latency_p50_ms", "w2_latency_p99_ms", "w2_rps", "transfer_goodput_bytes_per_second", "overlap_fraction"],
    "W13": ["goodput_bytes_per_second", "completion_seconds", "cpu_seconds_per_verified_gib"],
    "W14": ["latency_p50_ms", "latency_p95_ms", "latency_p99_ms", "completion_seconds", "chunk_lateness_p99_ms", "cleanup_latency_ms", "post_cancel_latency_ms", "reconnect_p99_ms", "successes"],
}
HIGHER_BETTER = {"w2_rps", "transfer_goodput_bytes_per_second", "overlap_fraction", "rps", "tx_tps", "rw_tps", "ro_tps", "load_rps", "goodput_bytes_per_second", "successes"} | {f"{W9_THROUGHPUT}{c}" for c in W9_CONCURRENCIES}
TRANSFER_TIMING = ("goodput_bytes_per_second", "completion_seconds")
FAVORABLE = ("strict-win", "non-inferior")
RESOURCE_METRICS = ["peak_total_rss_kb", "peak_phys_footprint_bytes",
                    "cpu_seconds_est"]
LINUX_RESOURCE_METRICS = ["peak_anon_kernel_bytes", "peak_memory_current_bytes",
                          "peak_memory_anon_bytes", "peak_memory_file_bytes",
                          "peak_memory_kernel_bytes", "cpu_seconds_est"]
IDENTITY_FIELDS = ("run_id", "host_id", "arch", "git_sha", "case", "state")


def resource_metrics(record):
    return LINUX_RESOURCE_METRICS if record.get('lane') == 'linux-amd64' else RESOURCE_METRICS


W14_MODE_METRICS = {
    "fresh": ["completion_seconds", "latency_p50_ms", "latency_p95_ms", "latency_p99_ms"],
    "persistent": ["completion_seconds", "latency_p50_ms", "latency_p95_ms", "latency_p99_ms"],
    "streaming": ["chunk_lateness_p99_ms"],
    "cancel": ["post_cancel_latency_ms", "chunk_lateness_p99_ms"],
    "idle-resume": ["latency_p50_ms", "latency_p95_ms", "latency_p99_ms"],
    "reconnect": ["reconnect_p99_ms"],
}


def case_metrics(case: str, params) -> list[str]:
    """The metrics a cohort produces. W14 modes each measure a different
    lifecycle; listing every mode's metrics showed most as unmeasured."""
    mode = params.get("mode") if isinstance(params, dict) else None
    if case == "W14" and mode in W14_MODE_METRICS:
        return [*W14_MODE_METRICS[mode], "cleanup_latency_ms", "successes"]
    if case == "W5" and isinstance(params, dict) and params.get("fixture_version") == W5_RECEIPT_VERSION:
        return [*CASE_METRICS["W5"], "bind_setup_s", "volume_setup_s", *W5_RESOURCE_METRICS]
    return CASE_METRICS.get(case, [])


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def workload_params(record: dict):
    return record.get("workload_params", record.get("parameters", record.get("params")))


def cohort_identity(record: dict) -> dict:
    identity = {key: record.get(key) for key in IDENTITY_FIELDS}
    if 'lane' in record:
        identity['lane'] = record['lane']
    params = workload_params(record)
    # Seed varies between repetitions, but must match within a pair below.
    identity["workload_params"] = ({k: v for k, v in params.items() if k != "seed"}
                                   if isinstance(params, dict) else params)
    identity["builder_driver"] = record.get("metrics", {}).get(
        "builder_driver", params.get("driver", "default")
        if isinstance(params, dict) else "default")
    identity["provenance"] = record.get("provenance")
    identity["evidence_status"] = record.get("evidence_status")
    return identity


def bootstrap_ci(values: list[float], iters: int = 2000,
                 seed: int = 7) -> tuple[float, float]:
    """Percentile bootstrap of the SAME paired median shown in the report."""
    if len(values) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(values)
    samples = sorted(statistics.median(
        values[rng.randrange(n)] for _ in range(n)) for _ in range(iters))

    def percentile(q: float) -> float:
        position = (len(samples) - 1) * q
        low, high = math.floor(position), math.ceil(position)
        return samples[low] + (samples[high] - samples[low]) * (position - low)

    return percentile(0.025), percentile(0.975)


def classify(n: int, low: float, high: float) -> str:
    """Statistical assessment only; never a promotion decision."""
    if n == 0:
        return "unmeasured"
    if n < MIN_PAIRS:
        return "pilot"
    if not (math.isfinite(low) and math.isfinite(high)):
        return "inconclusive"
    if high <= 0.95:
        return "strict-win"
    if low > 1.03:
        return "loss"
    if high <= 1.03:
        return "non-inferior"
    return "inconclusive"


def _correct(record: dict) -> bool:
    correctness = record.get("correctness", {})
    if correctness.get("ok") is not True or record.get("validation_errors"):
        return False
    checks = correctness.get("checks", {})
    if not isinstance(checks, dict) or not checks:
        return False
    return all(value is not False and not (
        isinstance(value, dict) and value.get("ok") is False
    ) for value in checks.values())


def _number(value: object) -> bool:
    return (isinstance(value, (float, int)) and not isinstance(value, bool)
            and math.isfinite(value))


def _recovery_cpu_per_success(record: dict):
    metrics = record.get("metrics", {})
    target = metrics.get("interrupt_service")
    if target in ("api", "db"):
        count, names = metrics.get("requests_ok"), ("recovery_workload",)
    elif target == "queue":
        count, names = metrics.get("jobs"), ("workers_backlog", "workers_recovered")
    else:
        return None, "W10 target has no continuous resource phase"
    if type(count) is not int or count <= 0:
        return None, "missing verified W10 success count"
    phases = record.get("resources", {}).get("phases")
    cpu = []
    for name in names:
        phase = phases.get(name) if isinstance(phases, dict) else None
        if not isinstance(phase, dict) or phase.get("errors") != []:
            return None, f"missing or invalid W10 CPU phase {name}"
        value = phase.get("cpu_seconds")
        if not _number(value) or value <= 0:
            return None, f"invalid W10 CPU seconds for {name}"
        cpu.append(value)
    return sum(cpu) / count, None


def _job_resource(record: dict, concurrency: int, field: str):
    metrics = record.get("metrics", {})
    count = metrics.get(f"jobs_at_{concurrency}")
    checks = record.get("correctness", {}).get("checks", {})
    if record["case"] == "W4":
        phase_name = check = f"workers_{concurrency}"
        expected = metrics.get("jobs")
    else:
        phase_name, check = f"jobs_at_{concurrency}", f"exact_jobs_at_{concurrency}"
        expected = ci_jobs.SPEC["fixed_jobs"]
    if checks.get(check) is not True or type(count) is not int or count <= 0 or count != expected:
        return None, f"missing verified {record['case']} jobs at concurrency {concurrency}"
    resources = record.get("resources", {})
    phase = resources.get("phase_receipts", {}).get(phase_name, {})
    value = phase.get(field)
    if phase.get("status") != "ok" or phase.get("errors") != [] or not _number(value) or value <= 0:
        return None, f"missing or invalid {record['case']} resource receipt at concurrency {concurrency}"
    return (value / count if field == "cpu_seconds" else value), None


def _watch_resource(record: dict, mode: str, metric: str):
    params = workload_params(record) or {}
    count = params.get("iters")
    edits = record.get("metrics", {}).get(f"{mode}_edits_s")
    checks = record.get("correctness", {}).get("checks", {})
    if (checks.get(f"{mode}_persistent_exact_results") is not True
            or type(count) is not int or count <= 0 or not isinstance(edits, list)
            or len(edits) != count or any(not _number(value) or value <= 0 for value in edits)):
        return None, f"missing verified W5 {mode} edits"
    names = [f"edit-{i}" for i in range(count)]
    if metric == "peak_phys_footprint_bytes":
        names.extend(("setup", "verify-inputs", "cleanup"))
    receipts = record.get("resources", {}).get("phase_receipts", {})
    field = "cpu_seconds" if metric == "cpu_seconds_per_edit" else metric
    values = []
    for name in names:
        phase = receipts.get(f"{mode}-{name}", {})
        value = phase.get(field)
        if phase.get("status") != "ok" or phase.get("errors") != [] or not _number(value) or value < 0:
            return None, f"missing or invalid W5 {mode}-{name} receipt"
        values.append(value)
    value = sum(values) / count if metric == "cpu_seconds_per_edit" else max(values)
    return (value, None) if value > 0 else (None, f"invalid W5 {mode} {field}")


def _metric(record: dict, name: str):
    resources = record.get("resources", {})
    if name == "db_restart_to_verified_s" and record.get("case") == "W1":
        value = record.get("metrics", {}).get(name)
        return (value, None) if _number(value) and value > 0 else (None, "missing verified W1 restart time")
    if name == "engine_cpu_per_success" and record.get("case") == "W10":
        return _recovery_cpu_per_success(record)
    if name == "engine_cpu_per_success" and record.get("case") == "W3":
        count = record.get("metrics", {}).get("verified_transactions")
        checks = record.get("correctness", {}).get("checks", {})
        if (type(count) is not int or count <= 0 or checks.get("verify_rows") is not True
                or checks.get("txmix") is not True):
            return None, "missing verified W3 transaction count"
        phase = (resources.get("phases") or {}).get("transactions", {})
        cpu = phase.get("cpu_seconds")
        if phase.get("errors") != [] or not _number(cpu) or cpu <= 0:
            return None, "missing or invalid W3 transaction CPU phase"
        return cpu / count, None
    if name in W4_RESOURCE_METRICS and record.get("case") == "W4":
        return _job_resource(record, *W4_RESOURCE_METRICS[name])
    if name in W9_RESOURCE_METRICS and record.get("case") == "W9":
        return _job_resource(record, *W9_RESOURCE_METRICS[name])
    if name in W5_RESOURCE_METRICS and record.get("case") == "W5":
        mode, _, metric = name.partition("_")
        return _watch_resource(record, mode, metric)
    if name in ("peak_phys_footprint_bytes", "cpu_seconds_est", *LINUX_RESOURCE_METRICS):
        if resources.get("ownership_verified") is not True:
            return None, "ownership not verified: " + str(resources.get("resource_errors", "missing resource errors"))
        if resources.get("resource_errors") != []:
            return None, "resource errors or missing error metadata: " + str(resources.get("resource_errors"))
        if name == "peak_phys_footprint_bytes" and resources.get("footprint_field") != "phys_footprint":
            return None, "footprint field is not phys_footprint"
        if name == 'peak_anon_kernel_bytes' and resources.get('footprint_field') != 'anon+kernel':
            return None, 'footprint field is not anon+kernel'
        if name == "cpu_seconds_est" and resources.get("cpu_counters_complete") is not True:
            return None, "CPU counters incomplete or missing completeness metadata"
    if name == "cpu_seconds_per_success" and record.get("case") == "W2":
        phases = resources.get("phases")
        phase = phases.get("workload") if isinstance(phases, dict) else None
        if not isinstance(phase, dict) or phase.get("errors") != []:
            return None, "workload CPU boundary errors or missing phase: " + str(phase.get("errors") if isinstance(phase, dict) else None)
        cpu = phase.get("cpu_seconds")
        if not _number(cpu) or cpu <= 0:
            return None, "invalid workload CPU seconds"
        metrics = record.get("metrics", {})
        counts = [metrics.get(key) for key in ("requests_ok", "reads_ok", "writes_ok", "errors")]
        if any(type(value) is not int or value < 0 for value in counts):
            return None, "missing or invalid W2 success/failure counts"
        requests, reads, writes, errors = counts
        if not requests or reads + writes != requests or errors:
            return None, "W2 success counts disagree or failures occurred"
        return cpu / requests, None
    container = "resources" if name in RESOURCE_METRICS + LINUX_RESOURCE_METRICS else "metrics"
    value = record.get(container, {}).get(name)
    return (value, None) if _number(value) and value > 0 else (None, "missing or invalid numeric value")


def _resource_mismatch(a: dict, b: dict) -> bool:
    left = a.get("resources", {}).get("engine", {})
    right = b.get("resources", {}).get("engine", {})
    if not isinstance(left, dict) or not isinstance(right, dict):
        return True
    if left.get("ncpu") is not None and right.get("ncpu") is not None:
        if left["ncpu"] != right["ncpu"]:
            return True
    # Guest MemTotal includes reservations, unlike the configured VM budget.
    # Large discrepancies invalidate pairs; budget parity still needs preflight.
    x, y = left.get("mem_total_bytes"), right.get("mem_total_bytes")
    return bool(_number(x) and _number(y) and x > 0 and y > 0
                and max(x, y) / min(x, y) > resource_cells.ENGINE_MEMORY_RATIO_LIMIT)


def cpu_candidate_mismatch(current: dict, candidate: dict) -> bool:
    overrides = candidate.get("config_overrides")
    if not isinstance(overrides, dict) or "CTRS_CPUS" not in overrides:
        return False
    a = current.get("resources", {}).get("engine") or {}
    b = candidate.get("resources", {}).get("engine") or {}
    if not isinstance(a, dict) or not isinstance(b, dict):
        return True
    before, after = a.get("ncpu"), b.get("ncpu")
    x, y = a.get("mem_total_bytes"), b.get("mem_total_bytes")
    return not (type(before) is int and before > 0 and type(after) is int and after > 0
                and before != after and overrides["CTRS_CPUS"] == str(after)
                and _number(x) and _number(y) and x > 0 and y > 0
                and max(x, y) / min(x, y) <= resource_cells.ENGINE_MEMORY_RATIO_LIMIT)


def candidate_configuration_issue(current: dict, candidate: dict) -> str | None:
    if cpu_candidate_mismatch(current, candidate):
        return "CPU candidate did not apply a different vCPU count at fixed memory"
    overrides = candidate.get("config_overrides")
    if not isinstance(overrides, dict) or "CTRS_MEMORY_MIB" not in overrides:
        return None
    a = current.get("resources", {}).get("engine") or {}
    b = candidate.get("resources", {}).get("engine") or {}
    if isinstance(a, dict) and isinstance(b, dict):
        before, after = a.get("vm_memory_ceiling_bytes"), b.get("vm_memory_ceiling_bytes")
        cpus = a.get("ncpu")
        if (type(before) is int and type(after) is int and before > 0 and after > 0
                and before != after and after % (1 << 20) == 0
                and overrides["CTRS_MEMORY_MIB"] == str(after >> 20)
                and type(cpus) is int and cpus > 0
                and type(b.get("ncpu")) is int and b["ncpu"] == cpus):
            return None
    return "memory candidate did not apply the requested VM ceiling at fixed vCPU count"


def _fixed_rate_lateness(record: dict) -> dict | None:
    params = record.get("workload_params", {})
    metrics = record.get("metrics", {})
    rate = params.get("request_rate")
    concurrency = params.get("concurrency")
    operations = params.get("operations")
    budget = metrics.get("schedule_lag_budget_ms")
    slots = metrics.get("slots")
    if (metrics.get("fixture_version") != "w2-v3.2-fixed-rate"
            or not _number(rate) or rate <= 0 or rate != metrics.get("request_rate")
            or type(concurrency) is not int or concurrency < 1
            or type(operations) is not int or operations < 1
            or not _number(budget) or budget <= 0
            or not isinstance(slots, list) or len(slots) != operations):
        return None
    for index, slot in enumerate(slots):
        if (not isinstance(slot, dict) or type(slot.get("slot")) is not int or slot["slot"] != index
                or not _number(start := slot.get("start_lag_ms")) or start < 0
                or not _number(completion := slot.get("scheduled_latency_ms")) or completion < start):
            return None
    worker_interval_ms = 1000 * concurrency / rate
    late = [index for index, slot in enumerate(slots) if slot["start_lag_ms"] > budget]
    if type(metrics.get("late_requests")) is not int or len(late) != metrics["late_requests"]:
        return None
    blocked = sum(index >= concurrency
                  and slots[index - concurrency]["scheduled_latency_ms"] > worker_interval_ms + budget
                  for index in late)
    return {"late": len(late), "blocked": blocked, "other": len(late) - blocked}


def _analyze_cohort(identity: dict, records: list[dict],
                    sides: tuple[str, str] = ("ctrs", "orbstack"),
                    side_of=None,
                    same_engine_required: bool = False) -> dict:
    side_of = side_of or (lambda record: record.get("engine"))
    if identity.get('lane') == 'linux-amd64' and sides == ('ctrs', 'orbstack'):
        sides = ('ctrs', 'dockerd')
    params = identity.get('workload_params')
    paired_w8 = (identity['case'] == 'W8' and isinstance(params, dict)
                 and params.get('fixture_version') == W8_PAIRED_FIXTURE)
    paired_w5 = (identity['case'] == 'W5' and isinstance(params, dict)
                 and params.get('fixture_version') == W5_RECEIPT_VERSION)
    paired_w3 = identity['case'] == 'W3' and any('paired_inputs' in record for record in records)
    verified_transfer = identity['case'] in ('W13', 'W14') and any(r.get('paired_inputs') for r in records)
    pinned_stack = (identity['case'] in ('W1', 'W2') and isinstance(params, dict)
                    and params.get('pinned_stack') is True)
    require_paired_inputs = (paired_w3 or paired_w5 or paired_w8 or pinned_stack
                             or verified_transfer or identity['case'] == 'W13-overlap')
    result = {"identity": identity, "evidence_status": "pilot",
              "promotion_eligible": False, "engines": {}, "rejections": [],
              "metrics": [], "metadata_gaps": []}
    if identity['case'] in ('W13', 'W14') and not verified_transfer:
        result["metadata_gaps"].append("paired_inputs (historical: image chosen by repository name, not verified)")
    if identity["case"] == "W2" and isinstance(params, dict) and params.get("request_rate") is not None:
        result["fixed_rate_lateness"] = [
            {"pair_id": row.get("pair_id"), "engine": side_of(row), "counts": _fixed_rate_lateness(row)}
            for row in records
        ]
    for side in sides:
        rows = [r for r in records if side_of(r) == side]
        result["engines"][side] = {
            "trials": len(rows), "correct": sum(_correct(r) for r in rows),
            "failed": sum(not _correct(r) for r in rows),
            "versions": sorted({str(r.get("engine_server_version", "missing")) for r in rows}),
            "guest_cpus": sorted({str((r.get("resources", {}).get("engine") or {}).get("ncpu", "missing"))
                                  for r in rows}),
        }
    for key in ("workload_params", "provenance"):
        if not isinstance(identity.get(key), dict) or not identity[key]:
            result["metadata_gaps"].append(key)
    provenance = identity.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    build_outputs = provenance.get("build_outputs")
    build_outputs = build_outputs if isinstance(build_outputs, dict) else {}
    for scope, source, keys in (
            ("provenance", provenance, ("cases_sha256", "assets_sha256",
                                        "fixture_sha256", "runner_sha256")),
            ("provenance.build_outputs", build_outputs,
             ("ctrs_binary_sha256", "guest_kernel_sha256",
              "guest_initramfs_sha256", "guest_data_sha256"))):
        for key in keys:
            value = source.get(key)
            if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
                result["metadata_gaps"].append(f"{scope}.{key}")
    paired: dict[int, list[dict]] = {}
    for record in records:
        pair_id = record.get("pair_id")
        if not isinstance(pair_id, int) or isinstance(pair_id, bool) or pair_id < 1:
            result["rejections"].append({"pair_id": pair_id, "reason": "unpaired record"})
        else:
            paired.setdefault(pair_id, []).append(record)
    valid = []
    version_drift = any(len(info["versions"]) > 1 for info in result["engines"].values())
    for pair_id, rows in sorted(paired.items()):
        a = [r for r in rows if side_of(r) == sides[0]]
        b = [r for r in rows if side_of(r) == sides[1]]
        reason = None
        if len(a) > 1 or len(b) > 1:
            reason = "duplicate side records; no overwrite permitted"
        elif len(a) != 1 or len(b) != 1 or len(rows) != 2:
            reason = "incomplete or mismatched pair"
        elif same_engine_required and a[0].get("engine") != b[0].get("engine"):
            reason = "noise-control pair spans different engines"
        elif not (_correct(a[0]) and _correct(b[0])):
            reason = "failed correctness or validation"
        elif version_drift:
            reason = "engine version drift within run"
        elif same_engine_required and sides == ("b", "a") and (
                configuration_issue := candidate_configuration_issue(b[0], a[0])):
            reason = configuration_issue
        elif (not isinstance(params, dict) or params.get("resource_lane") != "installed-default") \
                and _resource_mismatch(a[0], b[0]):
            reason = "engine resource budgets differ"
        elif {a[0].get("order_index"), b[0].get("order_index")} != {0, 1}:
            reason = "missing or duplicated trial order"
        elif workload_params(a[0]) != workload_params(b[0]):
            reason = "executed parameters or seeds differ"
        elif require_paired_inputs and (not a[0].get("paired_inputs") or a[0].get("paired_inputs") != b[0].get("paired_inputs")):
            reason = "paired inputs differ or are missing"
        elif a[0].get("workload_id") != b[0].get("workload_id"):
            reason = "workload identities differ"
        if not reason:
            reason = next((contended for r in (*a, *b) if (contended := host_contended(r))), None)
        if not reason and any(r.get("measurement_valid") is False for r in (*a, *b)):
            reason = "measurement invalidated: " + "; ".join(
                r.get("measurement_invalidation", "unspecified") for r in (*a, *b)
                if r.get("measurement_valid") is False)
        if reason:
            result["rejections"].append({"pair_id": pair_id, "reason": reason})
        else:
            valid.append((pair_id, a[0], b[0]))
    result["valid_pairs"] = len(valid)
    result["attempted_pairs"] = len(paired)
    if identity["case"] == "W11":
        result["note"] = "Reliability observations only; no request/window/churn speed verdicts."
        return result
    metrics = [*case_metrics(identity["case"], params), *resource_metrics(identity)]
    if paired_w8:
        metrics = ["pull_to_health_s", "cpu_seconds_est", "peak_phys_footprint_bytes"]
        if identity["workload_params"].get("under_load"):
            metrics += ["under_pull_p95_ms", "under_pull_p99_ms"]
    if paired_w5:
        metrics = case_metrics("W5", params)
    if identity["case"] == "W2":
        metrics.remove("cpu_seconds_est")
    w2_saturation = (identity["case"] == "W2" and isinstance(params, dict)
                     and "operations" in params and params["operations"] is None
                     and params.get("request_rate") is None
                     and _number(params.get("duration")) and params["duration"] > 0)
    if identity["case"] == "W7" and any("build_empty_s" in r.get("metrics", {}) for r in records):
        metrics.append("build_empty_s")
    hard_failure = any(info["failed"] for info in result["engines"].values())
    for metric in metrics:
        ratios, missing, missing_reasons = [], [], []
        for pair_id, a, b in valid:
            left, left_reason = _metric(a, metric)
            right, right_reason = _metric(b, metric)
            if (identity["case"] == "W3" and metric == "engine_cpu_per_success"
                    and left is not None and right is not None
                    and a["metrics"]["verified_transactions"] != b["metrics"]["verified_transactions"]):
                left_reason = "W3 verified transaction counts differ within pair"
            if (metric == "cpu_seconds_per_success" and not w2_saturation
                    and left is not None and right is not None):
                keys = ("requests_ok", "reads_ok", "writes_ok")
                if any(a["metrics"][key] != b["metrics"][key] for key in keys):
                    left_reason = "W2 useful work counts differ within pair"
            if left_reason or right_reason:
                missing.append(pair_id)
                missing_reasons.append({"pair_id": pair_id, "reason": "; ".join(
                    f"{side}: {reason}" for side, reason in zip(sides, (left_reason, right_reason)) if reason)})
                continue
            ratios.append(right / left if metric in HIGHER_BETTER else left / right)
        low, high = bootstrap_ci(ratios)
        assessment = classify(len(ratios), low, high)
        if metric == "build_empty_s" or (identity["case"] == "W8" and not paired_w8):
            assessment = "historical-only"
        elif hard_failure:
            assessment = "failed"
        elif result["rejections"]:
            assessment = "invalid"
        elif missing:
            assessment = "unmeasured" if not ratios else "incomplete"
        limited = transport = None
        if identity["case"] == "W13" and metric in TRANSFER_TIMING:
            limited = {side: sum(bool(pair[i + 1]["metrics"].get("tool_limited")) for pair in valid)
                       for i, side in enumerate(sides)}
            if (assessment in FAVORABLE and limited[sides[1]]) or (assessment == "loss" and limited[sides[0]]):
                assessment = "tool-limited"
            if "ctrs" in sides:
                side = sides.index("ctrs") + 1
                recorded = [pair[side]["metrics"]["transport"] for pair in valid if "transport" in pair[side]["metrics"]]
                transport = {"unrecorded_trials": len(valid) - len(recorded)}
                for paths in recorded:
                    for name, n in paths.items():
                        transport[name] = transport.get(name, 0) + n
        incomplete_cpu = None
        if "cpu" in metric and "ctrs" in sides:
            side = sides.index("ctrs") + 1
            accounting = [(pair[side].get("cpu_accounting") or {}).get("complete") for pair in valid]
            incomplete_cpu = sum(value is not True for value in accounting) if paired_w8 else sum(
                value is False for value in accounting)
            if incomplete_cpu and assessment in FAVORABLE + ("inconclusive",):
                assessment = "incomplete"
        elif "cpu" in metric and same_engine_required:
            incomplete_cpu = sum((record.get("cpu_accounting") or {}).get("complete") is False
                                 for _, a, b in valid for record in (a, b))
            if incomplete_cpu and assessment in FAVORABLE + ("inconclusive", "loss"):
                assessment = "incomplete"
        complete_resource = not missing or metric not in (
            "peak_phys_footprint_bytes", "cpu_seconds_est", "cpu_seconds_per_success",
            "engine_cpu_per_success", *LINUX_RESOURCE_METRICS, *W4_RESOURCE_METRICS,
            *W5_RESOURCE_METRICS, *W9_RESOURCE_METRICS)
        result["metrics"].append({
            "metric": metric, "valid_pairs": len(ratios),
            "missing_pairs": missing, "missing_reasons": missing_reasons, "assessment": assessment,
            "ratio_median": statistics.median(ratios) if ratios and complete_resource else None,
            "ci95": [low, high] if len(ratios) >= 2 and complete_resource else None,
            "evidence_status": "pilot", "promotion_eligible": False,
            **({"tool_limited_trials": limited} if limited is not None else {}),
            **({"ctrs_transport": transport} if transport is not None else {}),
            **({"cpu_accounting_incomplete_trials": incomplete_cpu} if incomplete_cpu else {}),
        })
    return result


FOREIGN_CORES = 2.0
# Below this the host tick resolution (10 ms per core) dominates the estimate.
FOREIGN_MIN_WALL_S = 1.0


def foreign_cores(record: dict) -> float | None:
    """Wall-weighted mean cores busy outside the engine and harness over a
    trial's resource phases, or None when a phase lacks the measurement."""
    phases = ((record.get("resources") or {}).get("phases") or {}).values()
    measured = [(p.get("foreign_cpu_cores"), p.get("operation_wall_seconds")) for p in phases]
    if not measured or any(not _number(c) or not _number(w) or w <= 0 for c, w in measured):
        return None
    wall = sum(w for _, w in measured)
    if wall < FOREIGN_MIN_WALL_S:
        return None
    return sum(c * w for c, w in measured) / wall


def host_contended(record: dict) -> str | None:
    """Why a trial ran on a contended host. Records that measure CPU outside
    the engine and harness are judged on it, because the load average also
    counts the engine's own vCPU threads and would reject pairs for the
    engine's behavior. Older records fall back to the 1-minute load average,
    at start or end, above the CPU count."""
    foreign = foreign_cores(record)
    if foreign is not None:
        if foreign > FOREIGN_CORES:
            return (f"host contended: {record.get('engine')} trial had {foreign:.1f} cores busy "
                    f"outside the engine and harness > {FOREIGN_CORES}")
        return None
    load = record.get("host_load")
    if not load or not load.get("cpus"):
        return None
    worst = max(x[0] for x in (load.get("start"), load.get("end")) if x)
    if worst > load["cpus"]:
        return f"host contended: {record.get('engine')} trial 1-minute load {worst:.1f} > {load['cpus']} CPUs"
    return None


def analyze(records: list[dict], input_issues: list[str] | None = None) -> dict:
    groups: dict[str, tuple[dict, list[dict]]] = {}
    result = {"evidence_status": "pilot", "promotion_eligible": False,
              "input_issues": list(input_issues or []), "holdout_excluded": 0,
              "noise_excluded": 0, "cohorts": []}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            result["input_issues"].append(f"record {index}: expected an object")
            continue
        if record.get("case") == "HOLDOUT":
            result["holdout_excluded"] += 1
            continue
        if record.get("design") == "noise-control":
            # Same-engine slot repeats size measurement noise; they are
            # never cross-engine performance evidence.
            result["noise_excluded"] += 1
            continue
        invalid = [k for k in IDENTITY_FIELDS if not isinstance(record.get(k), str) or not record[k]]
        if invalid or record.get("case") not in CASE_METRICS:
            result["input_issues"].append(f"record {index}: invalid identity/case ({', '.join(invalid)})")
            continue
        if record.get("engine") not in (('ctrs', 'dockerd') if record.get('lane') == 'linux-amd64' else ('ctrs', 'orbstack')):
            result["input_issues"].append(f"record {index}: unknown engine")
            continue
        if any(not isinstance(record.get(key, {}), dict) for key in ("metrics", "resources", "correctness")):
            result["input_issues"].append(f"record {index}: malformed metric/resource/correctness object")
            continue
        identity = cohort_identity(record)
        key = _canonical(identity)
        groups.setdefault(key, (identity, []))[1].append(record)
    result["cohorts"] = [_analyze_cohort(identity, rows)
                         for _, (identity, rows) in sorted(groups.items())]
    return result


def analyze_noise(records: list[dict], input_issues: list[str] | None = None,
                  design: str = "noise-control") -> dict:
    """Same-engine A/B slot pairs.

    noise-control: slot "a" against slot "b" with identical configuration;
    ratios should center on 1 and size run-to-run noise. candidate: slot
    "b" runs a configuration candidate (`config_overrides`) against the
    current configuration in slot "a"; ratios are candidate/current. Neither
    is ever ctrs-vs-OrbStack evidence.
    """
    groups: dict[str, tuple[dict, list[dict]]] = {}
    result = {"evidence_status": "pilot", "promotion_eligible": False,
              "input_issues": list(input_issues or []), "skipped_records": 0,
              "cohorts": [],
              "design": design,
              "note": ("Same-engine noise control only; ratios near 1 indicate "
                       "measurement noise, never an OrbStack comparison.")
              if design == "noise-control" else
              "Candidate configuration (slot b) over current (slot a) on one engine; "
              "never an OrbStack comparison."}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            result["input_issues"].append(f"record {index}: expected an object")
            continue
        if record.get("design") != design:
            result["skipped_records"] += 1
            continue
        invalid = [k for k in IDENTITY_FIELDS
                   if not isinstance(record.get(k), str) or not record[k]]
        if invalid or record.get("case") not in CASE_METRICS:
            result["input_issues"].append(
                f"record {index}: invalid identity/case ({', '.join(invalid)})")
            continue
        if record.get("engine") not in (('ctrs', 'dockerd') if record.get('lane') == 'linux-amd64' else ('ctrs', 'orbstack')):
            result["input_issues"].append(f"record {index}: unknown engine")
            continue
        if record.get("slot") not in ("a", "b"):
            result["input_issues"].append(
                f"record {index}: noise-control record lacks slot a/b identity")
            continue
        if any(not isinstance(record.get(key, {}), dict)
               for key in ("metrics", "resources", "correctness")):
            result["input_issues"].append(
                f"record {index}: malformed metric/resource/correctness object")
            continue
        identity = cohort_identity(record)
        key = _canonical(identity)
        groups.setdefault(key, (identity, []))[1].append(record)
    for _, (identity, rows) in sorted(groups.items()):
        cohort = _analyze_cohort(identity, rows, sides=("a", "b") if design == "noise-control" else ("b", "a"),
                                 side_of=lambda record: record.get("slot"),
                                 same_engine_required=True)
        if design == "candidate":
            overrides = {_canonical(r.get("config_overrides") or {}) for r in rows if r.get("slot") == "b"}
            current = [r for r in rows if r.get("slot") == "a" and r.get("config_overrides")]
            if len(overrides) != 1 or overrides == {_canonical({})} or current:
                result["input_issues"].append(
                    f"{identity['run_id']}: candidate slot b needs one non-empty config_overrides and slot a none")
            cohort["config_overrides"] = next((r["config_overrides"] for r in rows
                                               if r.get("slot") == "b" and r.get("config_overrides")), None)
        result["cohorts"].append(cohort)
    return result


def load_records(files: list[Path]) -> tuple[list[dict], list[str]]:
    records, issues = [], []
    for path in files:
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                issues.append(f"{path}:{number}: invalid JSON ({exc.msg})")
    return records, issues


def render_markdown(report: dict) -> str:
    lines = ["# Native performance report — descriptive pilot evidence", "",
             "Pairing/statistics do not qualify assets, workload realism, binary provenance,",
             "host isolation or a promotion. Each run/configuration is separate; histories",
             "are never pooled. Ratios below 1 favor ctrs (throughput is inverted).",
             "CIs bootstrap the paired median. Fewer than 10 valid pairs cannot establish a win.", "",
             f"Holdout records excluded from scoring: {report['holdout_excluded']}.",
             f"Noise-control records excluded from scoring: {report.get('noise_excluded', 0)}."]
    if report["input_issues"]:
        lines += ["", "## Invalid input", ""]
        lines += [f"- {issue}" for issue in report["input_issues"]]
    for cohort in report["cohorts"]:
        ident = cohort["identity"]
        lines += ["", f"## {ident['case']} / {ident['state']} / {ident['run_id']}", "",
                  f"Host: `{ident['host_id']}` (`{ident['arch']}`); source: `{ident['git_sha']}`.",
                  f"Builder: `{ident['builder_driver']}`; parameters: `{_canonical(ident['workload_params'])}`.", "",
                  "| Engine | Trials | Correct | Failed | Server versions | Guest vCPUs |",
                  "| --- | ---: | ---: | ---: | --- | --- |"]
        for engine, info in cohort["engines"].items():
            lines.append(f"| {engine} | {info['trials']} | {info['correct']} | {info['failed']} | "
                         f"{', '.join(info['versions'])} | {', '.join(info['guest_cpus'])} |")
        if cohort["metadata_gaps"]:
            lines += ["", "Missing qualification metadata: " + ", ".join(cohort["metadata_gaps"]) + "."]
        if cohort["rejections"]:
            lines += ["", "Rejected observations (visible, never successes):", ""]
            lines += [f"- Pair {item['pair_id']}: {item['reason']}." for item in cohort["rejections"]]
        if cohort.get("fixed_rate_lateness"):
            lines += ["", "Fixed-rate lateness includes all trials. A slot was blocked when the same",
                      "worker's previous request was still in flight at the slot's lateness deadline.", "",
                      "| Pair | Engine | Late slots | Blocked | Other late slots |",
                      "| ---: | --- | ---: | ---: | ---: |"]
            for row in cohort["fixed_rate_lateness"]:
                counts = row["counts"]
                values = (f"{counts['late']} | {counts['blocked']} | {counts['other']}"
                          if counts is not None else "unavailable | unavailable | unavailable")
                lines.append(f"| {row['pair_id']} | {row['engine']} | {values} |")
        if cohort.get("note"):
            lines += ["", cohort["note"]]
        if cohort["metrics"]:
            lines += ["", "| Metric | Valid pairs | Missing pairs | Median ratio | 95% CI | Assessment (pilot only) |",
                      "| --- | ---: | ---: | ---: | --- | --- |"]
            for metric in cohort["metrics"]:
                median = metric["ratio_median"]
                ratio = f"{median:.4f}" if median is not None else "unmeasured"
                ci = metric["ci95"]
                interval = f"[{ci[0]:.4f}, {ci[1]:.4f}]" if ci else "unmeasured"
                lines.append(f"| {metric['metric']} | {metric['valid_pairs']} | {len(metric['missing_pairs'])} | {ratio} | {interval} | {metric['assessment']} |")
            lines.append("")
            for metric in cohort["metrics"]:
                lines += [f"- {metric['metric']}, pair {item['pair_id']}: {item['reason']}." for item in metric["missing_reasons"]]
                if "tool_limited_trials" in metric:
                    counts = ", ".join(f"{side} {n}" for side, n in metric["tool_limited_trials"].items())
                    lines.append(f"- {metric['metric']}: tool-limited trials {counts}.")
                if metric.get("cpu_accounting_incomplete_trials"):
                    lines.append(f"- {metric['metric']}: {metric['cpu_accounting_incomplete_trials']} ctrs trials "
                                 "carried connections over the Mac's NAT, whose host-kernel CPU is not charged "
                                 "to ctrs; a CPU win or tie is incomplete, a loss stands.")
                if "ctrs_transport" in metric:
                    paths = ", ".join(f"{name} {n}" for name, n in metric["ctrs_transport"].items())
                    lines.append(f"- {metric['metric']}: ctrs connections by path: {paths}.")
    return "\n".join(lines) + "\n"


def render_noise_markdown(report: dict) -> str:
    if report.get("design") == "candidate":
        lines = ["# Native candidate report — one engine, current vs candidate configuration", "",
                 "Ratios are candidate (slot b) / current (slot a); below 1 favors the",
                 "candidate. They cannot support any ctrs-vs-OrbStack claim.", ""]
    else:
        lines = ["# Native noise-control report — same-engine slot pairs", "",
                 "Slot a vs slot b on ONE engine sizes measurement noise. These",
                 "ratios are never engine performance evidence and cannot",
                 "support any ctrs-vs-OrbStack claim.", ""]
    if report["input_issues"]:
        lines += ["## Invalid input", ""]
        lines += [f"- {issue}" for issue in report["input_issues"]]
    for cohort in report["cohorts"]:
        ident = cohort["identity"]
        lines += ["", f"## {ident['case']} / {ident['state']} / {ident['run_id']}", "",
                  f"Host: `{ident['host_id']}` (`{ident['arch']}`); source: `{ident['git_sha']}`.",
                  f"Parameters: `{_canonical(ident['workload_params'])}`.",
                  *([f"Candidate: `{_canonical(cohort['config_overrides'])}`."] if cohort.get("config_overrides") else []), "",
                  "| Slot | Trials | Correct | Failed | Server versions |",
                  "| --- | ---: | ---: | ---: | --- |"]
        for side, info in cohort["engines"].items():
            lines.append(f"| {side} | {info['trials']} | {info['correct']} | "
                         f"{info['failed']} | {', '.join(info['versions'])} |")
        if cohort["rejections"]:
            lines += ["", "Rejected observations (visible, never successes):", ""]
            lines += [f"- Pair {item['pair_id']}: {item['reason']}."
                      for item in cohort["rejections"]]
        if cohort["metrics"]:
            label = "Assessment (candidate/current)" if report.get("design") == "candidate" else "Assessment (noise only)"
            lines += ["", f"| Metric | Valid pairs | Missing pairs | Median ratio | 95% CI | {label} |",
                      "| --- | ---: | ---: | ---: | --- | --- |"]
            for metric in cohort["metrics"]:
                median = metric["ratio_median"]
                ratio = f"{median:.4f}" if median is not None else "unmeasured"
                ci = metric["ci95"]
                interval = f"[{ci[0]:.4f}, {ci[1]:.4f}]" if ci else "unmeasured"
                lines.append(f"| {metric['metric']} | {metric['valid_pairs']} | "
                             f"{len(metric['missing_pairs'])} | {ratio} | {interval} | "
                             f"{metric['assessment']} |")
            lines.append("")
            for metric in cohort["metrics"]:
                lines += [f"- {metric['metric']}, pair {item['pair_id']}: {item['reason']}." for item in metric["missing_reasons"]]
                if missing_cpu := metric.get("cpu_accounting_incomplete_trials"):
                    lines.append(f"- {metric['metric']}: {missing_cpu} slot trials have incomplete CPU accounting.")
    return "\n".join(lines) + "\n"


def invalid_noise_report(report: dict) -> bool:
    return bool(report["input_issues"] or any(c["rejections"] for c in report["cohorts"]))


ANCHOR_VERDICTS = {"strict-win": "improved", "loss": "regressed", "non-inferior": "no regression",
                   "inconclusive": "inconclusive", "pilot": "pilot", "unmeasured": "unmeasured"}


def _anchor_key(record: dict) -> str:
    identity = cohort_identity(record)
    params = identity["workload_params"]
    if isinstance(params, dict):
        identity["workload_params"] = {k: v for k, v in params.items() if v is not None}
    identity["fixture_version"] = (record.get("metrics") or {}).get("fixture_version")
    key = {k: identity[k] for k in ("host_id", "arch", "case", "state",
                                   "workload_params", "builder_driver", "fixture_version")}
    for section, field in (("paired_inputs", "portfolio_sha256"), ("inputs", "portfolio_sha256"),
                           ("provenance", "w8_source_contract_sha256")):
        metadata = record.get(section)
        if isinstance(metadata, dict) and isinstance(digest := metadata.get(field), str):
            key["portfolio_sha256"] = digest
            break
    if 'lane' in identity:
        key['lane'] = identity['lane']
    return _canonical(key)


def _admitted(records: list[dict]) -> dict[str, list[dict]]:
    """Records of each engine from the pairs the paired analysis admits."""
    by_cohort: dict[str, list[dict]] = {}
    for record in records:
        if record.get("design") == "paired" and record.get("case") in CASE_METRICS:
            by_cohort.setdefault(_canonical(cohort_identity(record)), []).append(record)
    admitted: dict[str, list[dict]] = {}
    for rows in by_cohort.values():
        rejected = {r["pair_id"] for r in _analyze_cohort(cohort_identity(rows[0]), rows)["rejections"]}
        admitted.setdefault(_anchor_key(rows[0]), []).extend(
            r for r in rows if r.get("pair_id") not in rejected and _correct(r))
    return admitted


def _median_ratio_ci(anchor: list[float], candidate: list[float], iters: int = 2000,
                     seed: int = 7) -> tuple[float, float]:
    if len(anchor) < 2 or len(candidate) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    def resample(values):
        return statistics.median(values[rng.randrange(len(values))] for _ in values)
    samples = sorted(resample(candidate) / resample(anchor) for _ in range(iters))
    return samples[int(0.025 * (iters - 1))], samples[int(0.975 * (iters - 1))]


def analyze_anchor(anchor: list[dict], candidate: list[dict]) -> list[dict]:
    """Each engine's candidate run against its own anchor run of the same
    workload on the same host: ctrs build-to-build movement and OrbStack
    drift, which the ctrs/OrbStack ratio alone cannot separate."""
    before, after = _admitted(anchor), _admitted(candidate)
    rows = []
    for key in sorted(before.keys() & after.keys()):
        case = json.loads(key)["case"]
        wanted = case_metrics(case, json.loads(key)["workload_params"])
        for engine in (('ctrs', 'dockerd') if before[key][0].get('lane') == 'linux-amd64' else ('ctrs', 'orbstack')):
            a = [r for r in before[key] if r.get("engine") == engine]
            c = [r for r in after[key] if r.get("engine") == engine]
            for metric in wanted + [m for m in resource_metrics(before[key][0]) if m not in wanted]:
                va = [v for v in (_metric(r, metric)[0] for r in a) if v is not None]
                vc = [v for v in (_metric(r, metric)[0] for r in c) if v is not None]
                if metric in HIGHER_BETTER:
                    va, vc = [1 / v for v in va], [1 / v for v in vc]
                low, high = _median_ratio_ci(va, vc)
                rows.append({
                    "case": case, "engine": engine, "metric": metric,
                    "anchor_runs": sorted({r["run_id"] for r in a}),
                    "candidate_runs": sorted({r["run_id"] for r in c}),
                    "anchor_n": len(va), "candidate_n": len(vc),
                    "ratio": statistics.median(vc) / statistics.median(va) if va and vc else None,
                    "ci95": [low, high] if math.isfinite(low) else None,
                    "verdict": ANCHOR_VERDICTS[classify(min(len(va), len(vc)), low, high)]})
    return rows


def render_anchor_markdown(rows: list[dict]) -> str:
    if not rows:
        return "No workload appears in both the anchor and the candidate on the same host.\n"
    lines = ["# Candidate against anchor (same engine, same host)", "",
             "Ratio is candidate/anchor in time-like units (throughput inverted); below 1 is",
             "faster. Unpaired across runs; admitted pairs only. An OrbStack row that moved",
             "is host or OrbStack drift, not a ctrs change.", "",
             "| Case | Engine | Metric | n (anchor/candidate) | Ratio | 95% CI | Verdict |",
             "| --- | --- | --- | ---: | ---: | --- | --- |"]
    for r in rows:
        ratio = f"{r['ratio']:.3f}" if r["ratio"] is not None else "—"
        ci = f"[{r['ci95'][0]:.3f}, {r['ci95'][1]:.3f}]" if r["ci95"] else "—"
        lines.append(f"| {r['case']} | {r['engine']} | {r['metric']} | {r['anchor_n']}/{r['candidate_n']} | "
                     f"{ratio} | {ci} | {r['verdict']} |")
    return "\n".join(lines) + "\n"


def invalid_report(report: dict) -> bool:
    return bool(report["input_issues"] or any(c["rejections"] for c in report["cohorts"]))


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path,
                        default=Path(__file__).resolve().parents[2] / ".work/native-perf/results")
    parser.add_argument("--match", default="*")
    parser.add_argument("--noise", action="store_true",
                        help="report same-engine A/B slot noise control")
    parser.add_argument("--candidate", action="store_true",
                        help="report a same-engine configuration candidate (slot b) against current (slot a)")
    parser.add_argument("--anchor", help="run-id glob to compare --match against, engine by engine")
    args = parser.parse_args()
    if args.anchor:
        anchor, anchor_issues = load_records(sorted(args.results.glob(f"{args.anchor}/trials.jsonl")))
        candidate, candidate_issues = load_records(sorted(args.results.glob(f"{args.match}/trials.jsonl")))
        for issue in anchor_issues + candidate_issues:
            print(f"input issue: {issue}")
        rows = analyze_anchor(anchor, candidate)
        print(render_anchor_markdown(rows), end="")
        return int(not rows or any(r["verdict"] == "regressed" and r["engine"] == "ctrs" for r in rows))
    files = sorted(args.results.glob(f"{args.match}/trials.jsonl"))
    records, issues = load_records(files)
    if not records and not issues:
        print("no trial records found")
        return 1
    if args.noise or args.candidate:
        report = analyze_noise(records, issues, "candidate" if args.candidate else "noise-control")
        print(render_noise_markdown(report), end="")
        return int(invalid_noise_report(report))
    report = analyze(records, issues)
    print(render_markdown(report), end="")
    return int(invalid_report(report))


if __name__ == "__main__":
    raise SystemExit(main())
