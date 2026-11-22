"""Attribute guest CPU during W13 transfers by mode and by process.

Runs one normal W13 trial per engine. A privileged reader in the guest's
host PID namespace snapshots /proc/stat and every thread's utime/stime just
before and after each measured transfer, outside the host resource phase.
Snapshot cost lands in the guest deltas and is reported as the reader's own
row. Timings from these trials are diagnostic only.
"""
import argparse
import collections
import contextlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runner

SNAPSHOT = r"""
import json, os
def stat_line():
    with open('/proc/stat') as f:
        head = f.readline().split()
    return dict(zip(('user', 'nice', 'system', 'idle', 'iowait', 'irq', 'softirq', 'steal'), map(int, head[1:9])))
threads = {}
for pid in os.listdir('/proc'):
    if not pid.isdigit():
        continue
    try:
        for tid in os.listdir(f'/proc/{pid}/task'):
            with open(f'/proc/{pid}/task/{tid}/stat') as f:
                text = f.read()
            comm = text[text.index('(') + 1:text.rindex(')')]
            fields = text[text.rindex(')') + 2:].split()
            threads[tid] = [comm, int(fields[11]), int(fields[12])]
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        continue
print(json.dumps({'stat': stat_line(), 'threads': threads, 'hz': os.sysconf('SC_CLK_TCK')}))
"""


def snapshot(engine, reader):
    cp = engine.sh(["exec", reader, "python", "-c", SNAPSHOT], timeout=60)
    return json.loads(cp.stdout)


def delta(before, after):
    hz = after["hz"]
    modes = {key: (after["stat"][key] - before["stat"][key]) / hz for key in after["stat"]}
    by_comm = collections.Counter()
    for tid, (comm, user, system) in after["threads"].items():
        old = before["threads"].get(tid)
        if old is None or old[0] != comm:
            old = [comm, 0, 0]
        by_comm[(comm, "user")] += (user - old[1]) / hz
        by_comm[(comm, "system")] += (system - old[2]) / hz
    return modes, by_comm


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engines", default="ctrs,orbstack")
    parser.add_argument("--transfer-path", default="published-port",
                        choices=("published-port", "container-to-container", "container-to-mac"))
    parser.add_argument("--direction", default="upload", choices=("upload", "download"))
    parser.add_argument("--streams", type=int, default=1, choices=(1, 4))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--resource-lane", choices=runner.RESOURCE_LANES, default="installed-default")
    args = parser.parse_args()
    runner.DOCKER = runner.find_docker()
    ctx = runner.RunContext(f"w13cpu-{time.strftime('%Y%m%dT%H%M%S')}")
    ctx.resource_lane = args.resource_lane
    original_phase = runner.resource_phase
    current = {}

    @contextlib.contextmanager
    def traced_phase(engine, rec, name):
        if not name.startswith("transfer_"):
            with original_phase(engine, rec, name):
                yield
            return
        before = snapshot(engine, current["reader"])
        with original_phase(engine, rec, name):
            yield
        after = snapshot(engine, current["reader"])
        current["windows"].append((before, after))

    failed = False
    runner.resource_phase = traced_phase
    try:
        for index, name in enumerate(args.engines.split(",")):
            engine = ctx.engines.get(name) or runner.Engine(name, ctx.run_id, resource_lane=ctx.resource_lane)
            ctx.engines[name] = engine
            engine.ensure_up()
            if name == "ctrs" and engine.proc is None:
                raise RuntimeError("refusing to adopt a running ctrs daemon")
            image = next(line.split()[1] for line in engine.sh(["images", "--format", "{{.Repository}} {{.ID}}"]).stdout.splitlines()
                         if line.split() and line.split()[0].endswith("np-v6/api"))
            reader = f"w13cpu-{ctx.run_id[-6:]}-{name}"
            engine.sh(["run", "-d", "--pull", "never", "--privileged", "--pid", "host", "--network", "none",
                       "--name", reader, "--label", "dev.ctrs.campaign.run=" + ctx.run_id,
                       "--entrypoint", "python", image, "-c", "import time; time.sleep(86400)"], timeout=60)
            current.update(reader=reader, windows=[])
            try:
                rec = runner.run_one(ctx, name, "W13", "warm", pair_id=1, order_index=index, keep_warm=True,
                                     slot=name, path=args.transfer_path, direction=args.direction,
                                     streams=args.streams, size_bytes=1 << 30, repeats=args.repeats)
            finally:
                label = engine.sh(["inspect", reader, "--format", '{{index .Config.Labels "dev.ctrs.campaign.run"}}'], check=False)
                if label.stdout.strip() == ctx.run_id:
                    engine.sh(["rm", "-f", reader], check=False)
            modes, comms = collections.Counter(), collections.Counter()
            for before, after in current["windows"]:
                m, c = delta(before, after)
                modes.update(m)
                comms.update(c)
            gib = sum(a["verified_bytes"] for a in rec["metrics"]["attempts"]) / 1024 ** 3
            per_gib = lambda value: round(value / gib, 3) if gib else None
            out = {"engine": name, "ok": rec["correctness"]["ok"], "errors": rec["validation_errors"],
                   "guest_cpus": (rec["resources"].get("engine") or {}).get("ncpu"),
                   "goodput_bytes_per_second": rec["metrics"].get("goodput_bytes_per_second"),
                   "verified_gib": gib, "windows": len(current["windows"]),
                   "guest_cpu_seconds_per_gib_by_mode": {k: per_gib(v) for k, v in modes.items() if k != "idle"},
                   "guest_cpu_seconds_per_gib_by_thread": {f"{comm}/{mode}": per_gib(v) for (comm, mode), v in comms.most_common(14)}}
            failed |= not rec["correctness"]["ok"] or len(current["windows"]) != args.repeats
            (ctx.results_dir / f"{name}-guest-cpu.json").write_text(json.dumps(out, indent=2) + "\n")
            print(json.dumps(out, indent=2), flush=True)
    finally:
        runner.resource_phase = original_phase
        for engine in ctx.engines.values():
            engine.stop()
    print(f"results: {ctx.results_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
