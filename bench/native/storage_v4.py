import hashlib
import json
import math
import re
import time

import ci_jobs
from diagnostics.w8_under_pull import baseline_image_reference, require_baseline_images

VERSION = "w3-v4-pgbench"
DURABILITY = ("fsync", "synchronous_commit", "full_page_writes")
WAL_STATS = """
SELECT json_build_object('syncs', wal_sync, 'sync_ms', wal_sync_time, 'reset', stats_reset,
                         'method', current_setting('wal_sync_method'),
                         'timing', current_setting('track_wal_io_timing'))
FROM pg_stat_wal
"""


def latency_metrics(logs, expected, prefix):
    values = []
    for content in logs:
        for line in content.splitlines():
            fields = line.split()
            if len(fields) < 5 or not fields[0].isdigit() or not fields[1].isdigit():
                raise ValueError("invalid pgbench latency receipt")
            try:
                latency = float(fields[2])
            except ValueError as exc:
                raise ValueError("invalid pgbench latency") from exc
            if not math.isfinite(latency) or latency < 0:
                raise ValueError("invalid pgbench latency")
            values.append(latency / 1000)
    if len(values) != expected:
        raise ValueError(f"expected {expected} latency receipts, got {len(values)}")
    values.sort()
    return {f"{prefix}_p{p}_ms": values[math.ceil(p / 100 * len(values)) - 1]
            for p in (50, 95, 99)}


def throughput(output):
    matches = re.findall(r"^tps = ([0-9]+(?:\.[0-9]+)?)\b", output, re.MULTILINE)
    if len(matches) != 1 or float(matches[0]) <= 0:
        raise ValueError("invalid pgbench throughput")
    return float(matches[0])


def verify_data(data, scale, clients, transactions):
    return (data["accounts"] == 100000 * scale and
            data["account_balance"] == data["history_delta"] and
            data["history"] == clients * transactions)


def durability_ok(settings):
    return all(settings.get(name) == "on" for name in DURABILITY)


def wal_sync_delta(before, after):
    for snapshot in (before, after):
        if (snapshot['method'] != 'fdatasync' or snapshot['timing'] != 'on'
                or type(snapshot['syncs']) is not int or snapshot['syncs'] < 0
                or type(snapshot['sync_ms']) not in (int, float)
                or not math.isfinite(snapshot['sync_ms']) or snapshot['sync_ms'] < 0):
            raise ValueError('invalid WAL sync timing snapshot')
    syncs = after['syncs'] - before['syncs']
    elapsed = after['sync_ms'] - before['sync_ms']
    if before['reset'] != after['reset'] or syncs <= 0 or elapsed <= 0:
        raise ValueError('WAL sync timings did not advance on a consistent statistics interval')
    return {'rw_wal_syncs': syncs, 'rw_wal_sync_ms': elapsed, 'rw_mean_wal_sync_ms': elapsed / syncs}


def trial_w3_v4(ctx, engine, state):
    import runner
    params = next(c for c in runner.load_cases()["case"] if c["id"] == "W3-v4")["params"]
    scale, buffers = params["scale"], params["shared_buffers"]
    clients, threads, transactions, seed = (params[k] for k in ("clients", "threads", "transactions_per_client", "random_seed"))
    ctx.workload_params.update(params, fixture_version=VERSION, durability={k: "on" for k in DURABILITY})
    wal_timed = getattr(ctx, 'design', None) == 'storage-sync-diagnostic'
    wal_args = ['-c', 'track_wal_io_timing=on', '-c', 'wal_sync_method=fdatasync'] if wal_timed else []
    if wal_timed:
        ctx.workload_params.update(track_wal_io_timing='on', wal_sync_method='fdatasync')
    trial_dir = ctx.trial_dir(engine.name, "W3-v4", state)
    rec = ctx.new_record(engine, "W3-v4", state, trial_dir)
    checks = rec["correctness"]["checks"]
    rec["metrics"]["fixture_version"] = VERSION
    token = hashlib.sha256(rec["trial_id"].encode()).hexdigest()[:16]
    project = runner.project_name(token, engine.name, "W3-v4")
    name, volume = f"{project}-db", f"{project}-pgdata"
    owner_label = f"dev.ctrs.campaign.run={ctx.run_id}"
    created = attempted = False
    sampler = trace = None

    def run(args, phase, timeout=300):
        result = engine.sh(args, timeout=timeout, check=False)
        (trial_dir / f"{phase}.stdout").write_text(result.stdout)
        (trial_dir / f"{phase}.stderr").write_text(result.stderr)
        if result.returncode:
            raise RuntimeError(f"{phase} failed ({result.returncode}): {result.stderr[-300:]}")
        return result.stdout

    def sql(query, phase):
        return run(["exec", name, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "postgres", "-tA", "-c", query], phase)

    def ready(stable):
        start = time.monotonic()
        since = None
        while time.monotonic() - start < 90:
            cp = engine.sh(["exec", name, "psql", "-U", "postgres", "-d", "postgres", "-tAc", "SELECT 1"], timeout=15, check=False)
            if cp.returncode == 0 and cp.stdout.strip() == "1":
                if not stable:
                    return
                if since is None:
                    since = time.monotonic()
                elif time.monotonic() - since >= 1.2:
                    return
            else:
                since = None
            time.sleep(.15)
        raise RuntimeError("postgres did not become ready")

    def volume_owner():
        info, = json.loads(engine.sh(["volume", "inspect", volume], timeout=30).stdout)
        if info.get("Name") != volume or (info.get("Labels") or {}).get("dev.ctrs.campaign.run") != ctx.run_id:
            raise ValueError("database volume ownership mismatch")

    def show_settings(phase):
        settings = {key: sql(f"SHOW {key}", f"{phase}-{key}").strip() for key in DURABILITY}
        checks[phase] = durability_ok(settings)
        if not checks[phase]:
            raise ValueError(f"durability settings differ: {settings}")

    try:
        if any(type(x) is not int or x <= 0 for x in (scale, clients, threads, transactions, seed)) or threads > clients:
            raise ValueError("invalid pgbench parameters")
        engine.ensure_up()
        if runner.linux_lane.enabled():
            image, identity = runner.linux_lane.image(engine, 'db')
            rec["inputs"] = {**identity, "portfolio_sha256": runner.sha256_file(runner.linux_lane.LOCK)}
            rec["paired_inputs"] = {"postgres_diff_ids": identity["image_diff_ids"],
                                    "portfolio_sha256": rec["inputs"]["portfolio_sha256"]}
        else:
            pin_path = runner.FIXTURES / "w8-v6/portfolio.json"
            pin = json.loads(pin_path.read_text())["images"]["np-v6/postgres"]
            image = baseline_image_reference(engine.name, pin)[1]
            inspected = json.loads(engine.sh(["image", "inspect", image], timeout=30).stdout)
            rec["inputs"] = {"images": require_baseline_images(engine.name, {"db": pin}, inspected),
                             "portfolio_sha256": runner.sha256_file(pin_path)}
        engine.sh(["volume", "create", "--label", owner_label, volume], timeout=30)
        created = True
        volume_owner()
        attempted = True
        run(["run", "-d", "--pull=never", "--name", name, "--label", owner_label,
             "-e", f"POSTGRES_PASSWORD={runner.W3_PASSWORD}", "-v", f"{volume}:/var/lib/postgresql/data", image,
             "postgres", "-c", f"shared_buffers={buffers}", "-c", "fsync=on", "-c", "synchronous_commit=on",
             "-c", "full_page_writes=on", *wal_args], "start", 120)
        ready(True)
        checks["ready"] = True
        sampler, trace = runner.start_sampler(engine, trial_dir)
        show_settings("durability_before")
        start = time.monotonic()
        run(["exec", name, "pgbench", "-U", "postgres", "-i", "-s", str(scale), "postgres"], "init", 3600)
        rec["metrics"]["init_s"] = time.monotonic() - start
        run(["exec", "-u", "postgres", name, "mkdir", "/tmp/w3v4-logs"], "log-directory")
        for phase in ("rw", "ro"):
            args = ["exec", "-u", "postgres", name, "pgbench", "-U", "postgres", "-c", str(clients), "-j", str(threads), "-t", str(transactions), "--random-seed", str(seed), "-l", "--log-prefix", f"/tmp/w3v4-logs/{phase}"]
            if phase == "ro":
                args += ["-S", "-n"]
            trace_wal = wal_timed and phase == 'rw'
            if trace_wal:
                wal_before = json.loads(sql(WAL_STATS, 'rw-wal-before'))
            try:
                output = run([*args, "postgres"], phase, 3600)
                if trace_wal:
                    wal_after = json.loads(sql(WAL_STATS, 'rw-wal-after'))
                    rec['metrics'].update(wal_sync_delta(wal_before, wal_after))
                    checks['rw_wal_stats'] = True
            finally:
                run(["cp", f"{name}:/tmp/w3v4-logs/.", str(trial_dir)], f"{phase}-copy", 120)
            logs = sorted(trial_dir.glob(f"{phase}.*"))
            logs = [p for p in logs if re.fullmatch(rf"{phase}\.\d+(?:\.\d+)?", p.name)]
            rec["metrics"].update(latency_metrics([p.read_text() for p in logs], clients * transactions, phase))
            rec["metrics"][f"{phase}_tps"] = throughput(output)
            checks[phase] = True
        start = time.monotonic()
        sql("CHECKPOINT", "checkpoint")
        rec["metrics"]["checkpoint_s"] = time.monotonic() - start
        start = time.monotonic()
        run(["restart", name], "restart", 120)
        ready(False)
        rec["metrics"]["restart_s"] = time.monotonic() - start
        checks["restart"] = True
        show_settings("durability_after")
        data = json.loads(sql("SELECT json_build_object('accounts', (SELECT count(*) FROM pgbench_accounts), 'account_balance', (SELECT sum(abalance) FROM pgbench_accounts), 'history_delta', (SELECT sum(delta) FROM pgbench_history), 'history', (SELECT count(*) FROM pgbench_history))", "verification"))
        checks["verification"] = verify_data(data, scale, clients, transactions)
        if not checks["verification"]:
            raise ValueError(f"persisted data mismatch: {data}")
        size, cache = (int(v) for v in sql("SELECT pg_database_size(current_database()), pg_size_bytes(current_setting('shared_buffers'))", "db-size").strip().split("|"))
        rec["metrics"]["db_size_bytes"] = size
        checks["working_set_exceeds_buffers"] = size > cache
        if not checks["working_set_exceeds_buffers"]:
            raise ValueError("database size does not exceed shared_buffers")
        rec["metrics"]["pgdata_allocated_bytes"] = int(run(["exec", name, "du", "-sk", "/var/lib/postgresql/data"], "allocated-size", 120).split()[0]) * 1024
        rec["correctness"]["ok"] = True
    except Exception as exc:
        rec["correctness"]["ok"] = False
        rec["validation_errors"].append(f"W3-v4: {exc}")
    finally:
        try:
            if sampler is not None:
                runner.stop_sampler(sampler)
            rec["resources"].update(runner.summarize_trace(trace) if trace else {})
            if trace:
                rec["resources"]["trace"] = runner._trace_ref(trace)
        except Exception as exc:
            rec["correctness"]["ok"] = False
            rec["validation_errors"].append(f"W3-v4 resource receipt: {exc}")
        for action in (lambda: ci_jobs.cleanup(engine, name, ctx.run_id) if attempted else None,
                       lambda: (volume_owner(), engine.sh(["volume", "rm", volume], timeout=60)) if created else None):
            try:
                action()
            except Exception as exc:
                rec["correctness"]["ok"] = False
                rec["validation_errors"].append(f"W3-v4 cleanup: {exc}")
    return rec
