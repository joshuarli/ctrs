#!/bin/bash
# CTRS-21 seccomp differential fixture. Builds the probe for the engine
# under test (default KIRI_SOCKET), runs the syscall battery under every
# security mode, and asserts the matrix matches the documented filter
# (Kiri's deny-list + per-capability relaxation; vsock and io_uring stay
# denied for everyone). Exits non-zero on any mismatch.
set -u
cd "$(dirname "$0")/../.."
SOCK=${KIRI_SOCKET:?set KIRI_SOCKET to the engine socket}
export DOCKER_HOST="unix://$SOCK"
unset DOCKER_CONTEXT
TAG=ctrs21/seccomp-probe
LOG=$(mktemp)
echo "building the probe image..."
if ! DOCKER_HOST="$DOCKER_HOST" docker build --load -q -t "$TAG" conformance/seccomp > "$LOG" 2>&1; then
  cat "$LOG"; echo "seccomp fixture: build failed"; rm -f "$LOG"; exit 2
fi

python3 - "$SOCK" > "$LOG" <<'PY'
import json, re, socket, sys

sock = sys.argv[1]

def api(method, path, body=None, timeout=30):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(sock)
    payload = json.dumps(body).encode() if body is not None else b""
    headers = f"{method} {path} HTTP/1.1\r\nHost: x\r\nConnection: close\r\n"
    if body is not None:
        headers += f"Content-Type: application/json\r\nContent-Length: {len(payload)}\r\n"
    headers += "\r\n"
    s.sendall(headers.encode() + payload)
    s.shutdown(socket.SHUT_WR)
    data = b""
    head_end = -1
    while True:
        try:
            chunk = s.recv(65536)
        except socket.timeout:
            break
        if not chunk:
            break
        data += chunk
        if head_end < 0:
            head_end = data.find(b"\r\n\r\n")
        if head_end >= 0:
            head_now = data[:head_end]
            declared = None
            for line in head_now.split(b"\r\n")[1:]:
                k, _, v = line.partition(b":")
                if k and k.strip().lower() == b"content-length":
                    declared = int(v.strip())
            if declared is not None and len(data) - (head_end + 4) >= declared:
                break
            # chunked: stop once the terminal chunk has arrived
            if b"0\r\n\r\n" in data[head_end:]:
                break
    s.close()
    head, _, body_bytes = data.partition(b"\r\n\r\n")
    status = int(head.split(b"\r\n", 1)[0].decode().split(" ")[1])
    headers = {}
    for line in head.split(b"\r\n")[1:]:
        k, _, v = line.partition(b":")
        if k:
            headers[k.decode().lower()] = v.decode().strip()
    if headers.get("transfer-encoding", "").lower() == "chunked":
        out = b""
        rest = body_bytes
        while True:
            line, _, rest = rest.partition(b"\r\n")
            n = int(line.split(b";", 1)[0], 16)
            if n == 0:
                break
            out += rest[:n]
            rest = rest[n + 2:]
        body_bytes = out
    return status, body_bytes

def probe(args):
    body = {"Image": "ctrs21/seccomp-probe", "Entrypoint": ["/seccomp-probe"], "Hostname": "seccomp-probe"}
    body["HostConfig"] = {"AutoRemove": True}
    if args.startswith("--cap-add"):
        body["HostConfig"]["CapAdd"] = args.split()[1:]
    elif args.startswith("--privileged"):
        body["HostConfig"]["Privileged"] = True
    elif args.startswith("--security-opt"):
        body["HostConfig"]["SecurityOpt"] = args.split()[1:]
    body["HostConfig"].pop("AutoRemove", None)
    status, resp = api("POST", "/containers/create", body)
    cid = json.loads(resp)["Id"]
    api("POST", f"/containers/{cid}/start")
    for _ in range(60):
        status, inspect = api("GET", f"/containers/{cid}/json")
        state = json.loads(inspect)["State"]
        if state["Status"] in ("exited", "dead"):
            break
    status, logs = api("GET", f"/containers/{cid}/logs?stdout=true")

    def demux(body):
        out = []
        i = 0
        while i + 8 <= len(body):
            size = int.from_bytes(body[i + 4:i + 8], "big")
            out.append(body[i + 8:i + 8 + size])
            i += 8 + size
        return b"".join(out)

    text = demux(logs).decode(errors="replace")
    out = {}
    for line in text.splitlines():
        k, sep, v = line.partition("=")
        if sep and k:
            out[k.strip()] = v.strip()
    api("DELETE", f"/containers/{cid}?force=true")
    return out

MODES = [
    ("default", ""),
    ("no-new-privileges", "--security-opt no-new-privileges"),
    ("seccomp=unconfined", "--security-opt seccomp=unconfined"),
    ("privileged", "--privileged"),
    ("SYS_ADMIN", "--cap-add SYS_ADMIN"),
    ("SYS_BOOT", "--cap-add SYS_BOOT"),
    ("SYS_TIME", "--cap-add SYS_TIME"),
    ("SYS_NICE", "--cap-add SYS_NICE"),
    ("SYS_MODULE", "--cap-add SYS_MODULE"),
    ("SYS_PACCT", "--cap-add SYS_PACCT"),
    ("BPF", "--cap-add BPF"),
    ("PERFMON", "--cap-add PERFMON"),
]

results = {name: probe(args) for name, args in MODES}

def errno(mode, key):
    v = results[mode].get(key, "missing")
    if v == "ok":
        return 0
    m = re.match(r"errno:(\d+)", v)
    return int(m.group(1)) if m else -99

EPERMS = {1, 38, 97}  # EPERM, ENOSYS, EAFNOSUPPORT — the filter's answers
FAILURES = []

def expect(mode, key, allowed, why=""):
    e = errno(mode, key)
    if e not in allowed:
        FAILURES.append(f"{mode:22} {key:22} -> {results[mode].get(key)} (want {why or sorted(allowed)})")

for mode in ("default", "no-new-privileges", "SYS_ADMIN", "SYS_BOOT", "SYS_TIME", "SYS_NICE", "SYS_MODULE", "SYS_PACCT", "BPF", "PERFMON"):
    for key in ["socket_vsock", "io_uring_setup", "io_uring_enter", "io_uring_register"]:
        expect(mode, key, {97} if key == "socket_vsock" else {1}, "vsock+io_uring denied for everyone")
    for key in ["keyctl", "add_key", "request_key", "userfaultfd"]:
        expect(mode, key, {1}, "always denied")

# Without CAP_SYS_ADMIN, mount stays denied by the filter. seccomp=unconfined
# and --privileged install only the host boundary (vsock + io_uring), so
# inside the user namespace mount is allowed, like Docker without a filter.
for mode in ("default", "no-new-privileges", "SYS_BOOT", "SYS_TIME", "SYS_NICE", "SYS_MODULE", "SYS_PACCT", "BPF", "PERFMON"):
    expect(mode, "mount", {1}, "without CAP_SYS_ADMIN mount is denied")
for mode in ("seccomp=unconfined", "privileged"):
    if errno(mode, "mount") == 1:
        FAILURES.append(f"{mode} mount -> errno:1 (only the boundary is installed; mount is not filtered)")
for mode in ("default", "no-new-privileges", "SYS_ADMIN", "SYS_BOOT", "SYS_TIME", "SYS_MODULE", "SYS_PACCT"):
    expect(mode, "bpf", {1}, "without CAP_BPF bpf is denied")
    expect(mode, "perf_event_open", {1}, "without CAP_PERFMON perf_event_open is denied")

expect("default", "clone3", {38})
if errno("SYS_ADMIN", "clone3") == 38:
    FAILURES.append("SYS_ADMIN clone3 -> ENOSYS (the filter must not hide clone3 from CAP_SYS_ADMIN)")
expect("no-new-privileges", "clone3", {38})

relax = {
    "SYS_ADMIN": ["mount", "umount2", "pivot_root", "swapon", "swapoff", "quotactl", "unshare_user", "name_to_handle_at", "open_by_handle_at"],
    "SYS_BOOT": ["kexec_load", "kexec_file_load", "reboot"],
    "SYS_TIME": ["clock_settime", "clock_adjtime", "settimeofday"],
    "SYS_NICE": ["mbind", "set_mempolicy", "migrate_pages", "move_pages"],
    "SYS_MODULE": ["init_module", "finit_module", "delete_module"],
    "SYS_PACCT": ["acct"],
    "BPF": ["bpf"],
    "PERFMON": ["perf_event_open"],
}
for mode, keys in relax.items():
    for key in keys:
        if errno(mode, key) == 1:
            FAILURES.append(f"{mode} should relax {key}, got errno:1")

for name, _ in MODES:
    print(f"{name}:".ljust(24) + " ".join(f"{k.split('=')[0]}={v}" for k, v in list(results[name].items())[:6]) + " ...")
print()
if FAILURES:
    print(f"seccomp fixture: {len(FAILURES)} FAILURE(S)")
    for f in FAILURES:
        print(f"  FAIL {f}")
    sys.exit(1)
print("seccomp fixture: all modes match the documented filter (vsock+io_uring denied for everyone; capabilities relax only their own rules)")
PY
rc=$?
cat "$LOG"
rm -f "$LOG"
exit $rc
