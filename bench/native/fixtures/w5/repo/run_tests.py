"""W5 edit-test probe: import every module and hash the edited marker,
printing npw5-ok <nmodules> <marker-hash>."""
import hashlib
import importlib
import pathlib
import sys

root = pathlib.Path("/repo")
mods = sorted(p.stem for p in root.glob("m*.py"))
for name in mods:
    importlib.import_module(name)
marker = (root / "edited.txt").read_text().strip()
h = hashlib.sha256(marker.encode()).hexdigest()[:12]
print(f"npw5-ok {len(mods)} {h} {marker}")
