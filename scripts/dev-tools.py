"""Install the development tools pinned in sources.lock.json.

Usage: sh bootstrap/buildlib-run -- scripts/dev-tools.py

bootstrap/buildlib-run (vendored from laputa-systems/buildlib) supplies the
pinned CPython 3.15 with laputa-buildlib importable. This script links that
interpreter and the pinned Node into $XDG_DATA_HOME/ctrs-dev/bin (default
~/.local/share/ctrs-dev/bin), verifying each download with buildlib.
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from buildlib.locks import fetch_input, load_sources

ROOT = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "ctrs-dev"
BIN = HOME / "bin"


def native_triple() -> str:
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(platform.machine().lower(), platform.machine().lower())
    system = platform.system()
    if system == "Darwin" and machine == "aarch64":
        return "aarch64-apple-darwin"
    if system == "Linux" and machine in ("x86_64", "aarch64"):
        return f"{machine}-unknown-linux-musl"
    sys.exit(f"dev-tools: no pinned tools for {system} {machine}")


def link(name: str, path: Path) -> None:
    BIN.mkdir(parents=True, exist_ok=True)
    dest = BIN / name
    if dest.is_symlink() or dest.exists():
        dest.unlink()
    dest.symlink_to(path)


def unpack(archive: Path, sha256: str, name: str) -> Path:
    """Unpack an archive into HOME/<name>; the stamp records the archive's digest."""
    target = HOME / name
    stamp = target / ".ctrs-dev-sha256"
    if stamp.is_file() and stamp.read_text() == sha256:
        return target
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    subprocess.run(["tar", "-xf", str(archive), "-C", str(target), "--strip-components=1"], check=True)
    stamp.write_text(sha256)
    return target


def runs(executable: Path) -> bool:
    return subprocess.run([str(executable), "--version"], capture_output=True, check=False).returncode == 0


def install_node(triple: str) -> str:
    lock = load_sources(ROOT / "sources.lock.json")
    pinned = next((item for item in lock.inputs if item.extra.get("tool") == "node" and item.target == triple), None)
    if pinned is not None:
        archive = fetch_input(pinned, HOME / "downloads" / pinned.url.rsplit("/", 1)[1])
        prefix = unpack(archive, pinned.sha256, f"{pinned.name}-{pinned.version}")
        if runs(prefix / "bin/node"):
            link("node", prefix / "bin/node")
            return f"node {pinned.version}: {prefix}"
        reason = f"pinned node {pinned.version} does not run here (it needs musl 1.2.5 or newer)"
    else:
        reason = f"no pinned node for {triple}"
    if (BIN / "node").is_symlink():
        (BIN / "node").unlink()
    system_node = shutil.which("node")
    if system_node is None:
        sys.exit(f"dev-tools: {reason}, and no node is on PATH; install the distribution's nodejs")
    return f"node: {reason}; using {system_node}"


def main() -> None:
    triple = native_triple()
    link("python3", Path(sys.executable))
    link("python", Path(sys.executable))
    print(f"python {platform.python_version()}: {sys.executable}")
    print(install_node(triple))
    print(f'export PATH="{BIN}:$PATH"')


if __name__ == "__main__":
    main()
