"""Prepare an offline Cargo source archive from the pinned Hyperfine release."""
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import tomllib


VENDOR_ARCHIVE = '.work/tmp/w7-hyperfine-vendor.tar.gz'
VENDOR_SHA256 = '46ac26bd0205449fff0f866be91cb730bd27ae05d4708964f5f2afc79c129e7e'
CARGO_LOCK_SHA256 = '190e5ac0a53fb5ceb73136b275f21ac9591fddfadcdc28dd0bb4a67dd84b3d83'


def normalize(entry):
    if not (entry.isfile() or entry.isdir()):
        raise ValueError(f'unexpected Cargo vendor entry: {entry.name}')
    entry.uid = entry.gid = entry.mtime = 0
    entry.uname = entry.gname = ''
    entry.mode = 0o755 if entry.isdir() or entry.mode & 0o111 else 0o644
    return entry


def prepare(source, destination):
    import runner

    if runner.sha256_file(source) != runner.W6_RUST_SOURCE['sha256']:
        raise ValueError('Hyperfine source archive does not match the pin')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='w7-vendor-', dir=destination.parent) as temporary:
        scratch = Path(temporary)
        with tarfile.open(source, 'r:gz') as extracted:
            extracted.extractall(scratch, filter='data')
        project = scratch / 'hyperfine-2.0.0'
        lock = project / 'Cargo.lock'
        if runner.sha256_file(lock) != CARGO_LOCK_SHA256:
            raise ValueError('Hyperfine Cargo.lock does not match the pin')
        packages = tomllib.loads(lock.read_text())['package']
        registry = {f"{p['name']}-{p['version']}": p['checksum'] for p in packages
                    if p.get('source') == 'registry+https://github.com/rust-lang/crates.io-index'}
        if len(registry) != len(packages) - 1:
            raise ValueError('expected one local Hyperfine package and a crates.io lock')

        manifest = project / 'Cargo.toml'
        # Cargo would otherwise associate the scratch checkout with the parent workspace.
        with manifest.open('a') as stream:
            stream.write('\n[workspace]\n')
        config = project / '.cargo/config.toml'
        config.parent.mkdir()
        env = {**os.environ, 'CARGO_HOME': str(scratch / 'cargo-home')}
        with config.open('wb') as stream:
            subprocess.run(['cargo', 'vendor', '--locked', '--versioned-dirs', 'vendor'],
                           cwd=project, env=env, stdout=stream, check=True)
        if runner.sha256_file(lock) != CARGO_LOCK_SHA256:
            raise ValueError('Cargo vendor changed the Hyperfine lock')
        vendor = project / 'vendor'
        if {path.name for path in vendor.iterdir()} != registry.keys():
            raise ValueError('vendored crates differ from the Hyperfine lock')
        for name, checksum in registry.items():
            metadata = json.loads((vendor / name / '.cargo-checksum.json').read_text())
            if metadata['package'] != checksum:
                raise ValueError(f'Cargo registry checksum mismatch for {name}')

        cargo_home = {**env, 'CARGO_HOME': str(scratch / 'offline-cargo-home')}
        resolved = subprocess.run(['cargo', 'metadata', '--frozen', '--format-version', '1',
                                   '--filter-platform', 'aarch64-unknown-linux-gnu'],
                                  cwd=project, env=cargo_home, capture_output=True, text=True, check=True)
        packages = json.loads(resolved.stdout)['packages']
        if any(not Path(package['manifest_path']).is_relative_to(vendor)
               for package in packages if package['source']):
            raise ValueError('offline resolution used a registry package outside the vendor tree')
        output = scratch / destination.name
        with output.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w|') as archive:
                archive.add(config, '.cargo/config.toml', filter=normalize)
                archive.add(vendor, 'vendor', filter=normalize)
        digest = runner.sha256_file(output)
        if digest != VENDOR_SHA256:
            raise ValueError(f'Hyperfine vendor archive does not match the pin: {digest}')
        output.replace(destination)
    return {'path': str(destination), 'cargo_lock_sha256': CARGO_LOCK_SHA256,
            'sha256': digest, 'registry_crates': len(registry)}


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    import runner

    if runner.linux_lane.enabled():
        sys.exit('run without the Linux amd64 campaign lane enabled')
    source = runner.ensure_pinned_source(runner.W6_RUST_SOURCE, runner.W7_DIR)
    print(json.dumps(prepare(source, runner.REPO / VENDOR_ARCHIVE), indent=2))
