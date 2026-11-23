//! Build tasks for ctrs. Run with `cargo xtask <task>`.
//!
//!   guest    build ctrs-init for the guest and pack guest/out/initramfs.cpio
//!   kernel   build the guest kernel into guest/out/Image (needs a Docker engine)
//!   disk     make the empty data disk template guest/out/data.img (needs a Docker engine)
//!   host     build the `ctrs` binary and sign it with the virtualization entitlement
//!   linux    `ctrs` and `ctrs-init` for a Linux host, in target/linux/release
//!            (built in a Linux container: needs a Docker engine, ctrs works)
//!   all      guest + host
//!
//! `--arch x86_64` (or `intel`) makes guest, kernel, host and linux do the
//! Intel platform instead: an x86-64 guest in guest/out/x86_64, or an
//! x86-64 Linux binary in target/linux/.

use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

#[path = "../../guest/disk_capacity.rs"]
mod disk_capacity;

/// Which platform a build is for; `--arch` selects it. One flag, one value;
/// aliases map to one canonical value; unknown or conflicting flags are
/// refused before anything runs.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Arch {
    Arm64,
    X86_64,
}

/// `x86_64` (`amd64`, `x86-64`, `intel`) selects Intel; `arm64` (`aarch64`)
/// selects ARM. macOS keeps its intentional ARM default; Linux follows the
/// host.
fn default_arch() -> Arch {
    if cfg!(target_os = "macos") {
        Arch::Arm64
    } else if cfg!(target_arch = "x86_64") {
        Arch::X86_64
    } else {
        Arch::Arm64
    }
}

fn parse_arch(value: &str) -> Option<Arch> {
    match value {
        "arm64" | "aarch64" => Some(Arch::Arm64),
        "amd64" | "x86_64" | "x86-64" | "intel" => Some(Arch::X86_64),
        _ => None,
    }
}

/// Parses `--arch` from the argument slice (everything after the task).
/// One flag, one value; unknown flags and conflicting `--arch`s are errors.
fn parse(args: &[String], default: Arch) -> Result<Arch, String> {
    let mut arch: Option<Arch> = None;
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--arch" => {
                let value = args.get(i + 1).ok_or("--arch needs a value (arm64, aarch64, amd64, x86_64, x86-64, intel)")?;
                let parsed = parse_arch(value).ok_or_else(|| format!("--arch {value} is not supported (want arm64, aarch64, amd64, x86_64, x86-64 or intel)"))?;
                if arch.is_some() {
                    return Err("--arch given more than once".into());
                }
                arch = Some(parsed);
                i += 2;
            }
            other => return Err(format!("unknown argument {other:?} (known flag: --arch)")),
        }
    }
    Ok(arch.unwrap_or(default))
}

impl Arch {
    fn guest_target(self) -> &'static str {
        match self {
            Arch::Arm64 => "aarch64-unknown-linux-musl",
            Arch::X86_64 => "x86_64-unknown-linux-musl",
        }
    }

    fn host_target(self) -> &'static str {
        match self {
            Arch::Arm64 => "aarch64-apple-darwin",
            Arch::X86_64 => "x86_64-apple-darwin",
        }
    }

    /// Where the Linux binaries land: target/linux/release for arm64,
    /// target/linux-x86_64/release for amd64.
    fn linux_out(self) -> &'static str {
        match self {
            Arch::Arm64 => "linux",
            Arch::X86_64 => "linux-x86_64",
        }
    }

    /// The cargo cache for the Linux build (separate per architecture).
    fn linux_cache(self) -> &'static str {
        match self {
            Arch::Arm64 => "ctrs-cargo-aarch64-musl",
            Arch::X86_64 => "ctrs-cargo-amd64",
        }
    }

    /// guest/out for Apple Silicon, guest/out/x86_64 for Intel.
    fn guest_out(self, root: &Path) -> io::Result<PathBuf> {
        let out = match self {
            Arch::Arm64 => root.join("guest/out"),
            Arch::X86_64 => root.join("guest/out/x86_64"),
        };
        fs::create_dir_all(&out)?;
        Ok(out)
    }

    /// Where the host binary lands: target/release when it is this Mac's own
    /// architecture (so `cargo run` and the Apple Silicon build stay as they
    /// were), target/<triple>/release when cross-built.
    fn host_bin(self, root: &Path) -> PathBuf {
        if self.native() { root.join("target/release/ctrs") } else { root.join("target").join(self.host_target()).join("release/ctrs") }
    }

    fn native(self) -> bool {
        (self == Arch::X86_64) == cfg!(target_arch = "x86_64")
    }
}

fn main() -> ExitCode {
    let task = std::env::args().nth(1).unwrap_or_default();
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().to_path_buf();
    let args: Vec<String> = std::env::args().skip(2).collect();
    let arch = match parse(&args, default_arch()) {
        Ok(arch) => arch,
        Err(e) => {
            eprintln!("xtask {task}: {e}");
            return ExitCode::from(2);
        }
    };
    let result = match task.as_str() {
        "guest" => guest(&root, arch),
        "kernel" => kernel(&root, arch),
        "disk" => disk(&root),
        "host" => host(&root, arch),
        "linux" => linux(&root, arch),
        "all" => guest(&root, arch).and_then(|()| host(&root, arch)),
        _ => {
            eprintln!("usage: cargo xtask <guest|kernel|disk|host|linux|all> [--arch arm64|aarch64|amd64|x86_64|x86-64|intel]");
            return ExitCode::from(2);
        }
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("xtask {task}: {e}");
            ExitCode::FAILURE
        }
    }
}

fn run(cmd: &mut Command) -> io::Result<()> {
    let status = cmd.status()?;
    if !status.success() {
        return Err(io::Error::other(format!("{cmd:?} failed: {status}")));
    }
    Ok(())
}

fn guest(root: &Path, arch: Arch) -> io::Result<()> {
    let target = arch.guest_target();
    // ctrs-init is pure Rust: rust-lld links it against Rust's own musl, as
    // .cargo/config.toml does for arm64. Set here, not there, so the Linux
    // engine build (which links C) keeps its own linker.
    run(Command::new(env!("CARGO"))
        .current_dir(root)
        .env("CARGO_TARGET_X86_64_UNKNOWN_LINUX_MUSL_LINKER", "rust-lld")
        .args(["build", "--release", "-p", "ctrs-init", "--target", target]))?;
    let init = fs::read(root.join("target").join(target).join("release/ctrs-init"))?;

    // Uncompressed on purpose: it is small, and the kernel skips decompression.
    let mut cpio = Cpio::default();
    for dir in ["dev", "proc", "sys", "run", "tmp", "etc"] {
        cpio.dir(dir);
    }
    // The kernel opens /dev/console for PID 1 before any filesystem is mounted.
    cpio.char_dev("dev/console", 0o600, 5, 1);
    cpio.file("init", 0o755, &init);
    let path = arch.guest_out(root)?.join("initramfs.cpio");
    fs::write(&path, cpio.finish())?;
    println!("{} ({} KiB)", path.display(), fs::metadata(&path)?.len() / 1024);
    Ok(())
}

/// The arm64 kernel builds in the cached tree in the `ctrs-kbuild` volume;
/// the x86-64 one in its own, `ctrs-kbuild-x86_64`, since both build in the
/// source tree. On Apple Silicon the x86-64 kernel is cross-compiled.
fn kernel(root: &Path, arch: Arch) -> io::Result<()> {
    let src = root.join("guest/kernel");
    let out = arch.guest_out(root)?;
    let (karch, cache) = match arch {
        Arch::Arm64 => ("KARCH=arm64", "ctrs-kbuild:/build"),
        Arch::X86_64 => ("KARCH=x86_64", "ctrs-kbuild-x86_64:/build"),
    };
    run(Command::new("docker").args([
        "run",
        "--rm",
        "-e",
        "DEBIAN_FRONTEND=noninteractive",
        "-e",
        karch,
        "-v",
        cache,
        "-v",
        &format!("{}:/src:ro", src.display()),
        "-v",
        &format!("{}:/out", out.display()),
        // Pinned by index digest (verified 2026-11-15); the mutable tag is not a release input.
        "debian:trixie@sha256:9c6e381421d0f48d1b8133e573f33c185ee16cbf505eda9c4a8a4791b25ea8a6",
        "sh",
        "/src/build.sh",
    ]))
}

/// A sparse 1 TiB ext4 image with lazily initialised inode tables: it uses a
/// few MB on the Mac until data is written. Each install copies it (an APFS
/// clone, so instant) into its data directory on first boot.
/// The same ext4 image serves both architectures.
fn disk(root: &Path) -> io::Result<()> {
    let out = Arch::Arm64.guest_out(root)?;
    let script = format!(
        "set -e; apt-get update -qq >/dev/null && apt-get install -y -qq e2fsprogs >/dev/null; \
         rm -f /out/data.img; truncate -s {} /out/data.img; \
         mkfs.ext4 -q -F -m 0 -L ctrs-data -E lazy_itable_init=1,lazy_journal_init=1 /out/data.img", disk_capacity::MINIMUM_BYTES);
    run(Command::new("docker").args([
        "run",
        "--rm",
        "-v",
        &format!("{}:/out", out.display()),
        "debian:trixie@sha256:9c6e381421d0f48d1b8133e573f33c185ee16cbf505eda9c4a8a4791b25ea8a6",
        "sh",
        "-c",
        &script,
    ]))?;
    let meta = fs::metadata(out.join("data.img"))?;
    println!("{} ({} GiB sparse)", out.join("data.img").display(), meta.len() >> 30);
    Ok(())
}

fn host(root: &Path, arch: Arch) -> io::Result<()> {
    let mut build = Command::new(env!("CARGO"));
    build.current_dir(root).args(["build", "--release", "-p", "ctrs"]);
    if !arch.native() {
        build.args(["--target", arch.host_target()]);
    }
    run(&mut build)?;
    let bin = arch.host_bin(root);
    if cfg!(target_os = "macos") {
        // Virtualization.framework refuses to start a VM without this entitlement.
        run(Command::new("codesign").args(["--force", "--sign", "-", "--entitlements"])
            .arg(root.join("crates/ctrs/ctrs.entitlements"))
            .arg(&bin))?;
    }
    println!("{} ({} KiB)", bin.display(), fs::metadata(&bin)?.len() / 1024);
    Ok(())
}

/// The Linux host build, native, in a container: amd64 runs the rust image
/// natively (x86_64 under it compiles straight for x86_64); arm64 runs a
/// pinned cross toolchain on the *build* platform — the compiler and build
/// scripts run natively there, targeting aarch64 musl, never a target
/// emulator for compilation. The cargo registry is cached per architecture.
fn linux(root: &Path, arch: Arch) -> io::Result<()> {
    linux_build(root, arch)
}

fn linux_build(root: &Path, arch: Arch) -> io::Result<()> {
    let out = arch.linux_out();
    let cache = arch.linux_cache();
    /// The platform the Linux builds run on: the host's own architecture.
    /// The arm64 cross path runs the matching variant of the pinned
    /// toolchain, natively, wherever it runs.
    #[cfg(target_arch = "aarch64")]
    const BUILDPLATFORM: &str = "linux/arm64";
    #[cfg(not(target_arch = "aarch64"))]
    const BUILDPLATFORM: &str = "linux/amd64";

    match arch {
        Arch::Arm64 => {
            // Pinned: messense/rust-musl-cross (rustc 1.96.1, gcc 12.4.0,
            // aarch64 musl 1.2.x), built from the Debian toolchain by that
            // project. Build-only; never redistributed.
            run(Command::new("docker")
                .args(["run", "--rm", "--platform", BUILDPLATFORM, "-v"])
                .arg(format!("{}:/src", root.display()))
                .args([
                    "-v",
                    &format!("{cache}:/root/.cargo/registry"),
                    "-w",
                    "/src",
                    "-e",
                    &format!("CARGO_TARGET_DIR=/src/target/{out}"),
                    // messense ships aarch64-unknown-linux-musl-gcc; the repo's
                    // guest config wants rust-lld, which cannot drive crt paths
                    // for the full release build.
                    "-e",
                    "CARGO_TARGET_AARCH64_UNKNOWN_LINUX_MUSL_LINKER=aarch64-unknown-linux-musl-gcc",
                    // The user's global config injects a mold -B path; override it.
                    "-e",
                    "CARGO_ENCODED_RUSTFLAGS=",
                    // The repo's rust-toolchain.toml requests nightly-2026-11-09,
                    // which this image does not ship and whose musl std rustup has
                    // not been installed for; the image's stable carries the target.
                    "-e",
                    "RUSTUP_TOOLCHAIN=stable",
                    "messense/rust-musl-cross:aarch64-musl@sha256:02e790506c5f15a533bc05b3af8719b16a8a2314480f6f0fdc0166432035d9b4",
                    "sh",
                    "-c",
                    // The container runs as root and owns target/linux; the copy
                    // keeps the published layout at target/linux/release.
                    "set -e; cargo build --release --target aarch64-unknown-linux-musl -p ctrs -p ctrs-init \
                        && mkdir -p /src/target/linux/release \
                        && cp /src/target/linux/aarch64-unknown-linux-musl/release/ctrs /src/target/linux/aarch64-unknown-linux-musl/release/ctrs-init /src/target/linux/release/",
                ]))?;
        }
        Arch::X86_64 => {
            run(Command::new("docker")
                .args(["run", "--rm", "--platform", "linux/amd64", "-v"])
                .arg(format!("{}:/src", root.display()))
                .args([
                    "-v",
                    &format!("{cache}:/usr/local/cargo/registry"),
                    "-w",
                    "/src",
                    "-e",
                    &format!("CARGO_TARGET_DIR=/src/target/{out}"),
                    // The repo's cross-linking setting is for the guest build from macOS.
                    "-e",
                    "CARGO_TARGET_AARCH64_UNKNOWN_LINUX_MUSL_LINKER=cc",
                    // The user's global config injects a mold -B path; override it.
                    "-e",
                    "CARGO_ENCODED_RUSTFLAGS=",
                    "rust:1.100.0-alpine@sha256:de1e0058543a81ed7b046629167db587c67a94bdf37cce14eb27f0ec83baaffb",
                    "sh",
                    "-c",
                    "apk add -q musl-dev && cargo build --release -p ctrs -p ctrs-init",
                ]))?;
        }
    }
    for b in ["ctrs", "ctrs-init"] {
        let p = root.join("target").join(out).join("release").join(b);
        println!("{} ({} KiB)", p.display(), fs::metadata(&p)?.len() / 1024);
    }
    Ok(())
}



/// Minimal writer for the "newc" cpio format the kernel unpacks as initramfs.
#[derive(Default)]
struct Cpio {
    buf: Vec<u8>,
    ino: u32,
}

impl Cpio {
    fn dir(&mut self, name: &str) {
        self.entry(name, 0o040_755, 2, (0, 0), &[]);
    }

    fn char_dev(&mut self, name: &str, perm: u32, major: u32, minor: u32) {
        self.entry(name, 0o020_000 | perm, 1, (major, minor), &[]);
    }

    fn file(&mut self, name: &str, perm: u32, data: &[u8]) {
        self.entry(name, 0o100_000 | perm, 1, (0, 0), data);
    }

    fn entry(&mut self, name: &str, mode: u32, nlink: u32, rdev: (u32, u32), data: &[u8]) {
        self.ino += 1;
        let fields = [
            self.ino,
            mode,
            0, // uid
            0, // gid
            nlink,
            0, // mtime: fixed, so builds are reproducible
            data.len() as u32,
            0, // devmajor
            0, // devminor
            rdev.0,
            rdev.1,
            name.len() as u32 + 1,
            0, // check
        ];
        self.buf.extend_from_slice(b"070701");
        for f in fields {
            write!(self.buf, "{f:08x}").unwrap();
        }
        self.buf.extend_from_slice(name.as_bytes());
        self.buf.push(0);
        self.pad();
        self.buf.extend_from_slice(data);
        self.pad();
    }

    fn pad(&mut self) {
        while !self.buf.len().is_multiple_of(4) {
            self.buf.push(0);
        }
    }

    fn finish(mut self) -> Vec<u8> {
        self.ino = 0;
        self.entry("TRAILER!!!", 0, 1, (0, 0), &[]);
        self.buf
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(v: &[&str]) -> Vec<String> {
        v.iter().map(|s| s.to_string()).collect()
    }

    /// Options whose guest experiments were rejected or kept private
    /// (docs/decisions.md); enabling one needs a new recorded decision.
    #[test]
    fn guest_kernel_leaves_out_unpromoted_options() {
        let config = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../guest/kernel/ctrs.config")).unwrap();
        for option in ["CONFIG_SCHED_MC", "CONFIG_ARM64_USE_LSE_ATOMICS", "CONFIG_UPROBE_EVENTS", "CONFIG_PREEMPT", "CONFIG_HZ_1000"] {
            assert!(!config.lines().any(|l| l.trim() == format!("{option}=y")), "{option} is enabled");
        }
        assert!(config.lines().any(|l| l.trim() == "CONFIG_PREEMPT_VOLUNTARY=y"));
    }

    #[test]
    fn arch_aliases() {
        for (given, want) in [
            ("arm64", Arch::Arm64),
            ("aarch64", Arch::Arm64),
            ("amd64", Arch::X86_64),
            ("x86_64", Arch::X86_64),
            ("x86-64", Arch::X86_64),
            ("intel", Arch::X86_64),
        ] {
            assert_eq!(parse(&args(&["--arch", given]), Arch::Arm64), Ok(want), "{given}");
        }
    }

    #[test]
    fn arch_defaults_follow_the_host() {
        assert_eq!(parse(&args(&[]), Arch::X86_64), Ok(Arch::X86_64));
        assert_eq!(parse(&args(&[]), Arch::Arm64), Ok(Arch::Arm64));
        assert_eq!(parse(&args(&["--arch", "arm64"]), Arch::X86_64), Ok(Arch::Arm64));
    }

    #[test]
    fn arch_refusals() {
        for given in ["--arch", "--arch banana", "--arch arm64 --arch amd64", "--arch arm64 --arch arm64", "--bogus", "-a arm64", "--arch arm64 --bogus"] {
            let parts: Vec<&str> = given.split_whitespace().collect();
            assert!(parse(&args(&parts), Arch::Arm64).is_err(), "{given}");
        }
    }

    #[test]
    fn arch_error_names_the_flag_and_values() {
        let e = parse(&args(&["--arch", "banana"]), Arch::Arm64).unwrap_err();
        assert!(e.contains("banana"));
        assert!(e.contains("arm64"));
        assert!(e.contains("x86_64"));
        let e = parse(&args(&["--arch"]), Arch::Arm64).unwrap_err();
        assert!(e.contains("--arch"));
    }

    #[test]
    fn triples_and_paths_are_target_specific() {
        assert_eq!(Arch::Arm64.guest_target(), "aarch64-unknown-linux-musl");
        assert_eq!(Arch::X86_64.guest_target(), "x86_64-unknown-linux-musl");
        assert_eq!(Arch::Arm64.linux_out(), "linux");
        assert_eq!(Arch::X86_64.linux_out(), "linux-x86_64");
        assert_eq!(Arch::Arm64.linux_cache(), "ctrs-cargo-aarch64-musl");
        assert_eq!(Arch::X86_64.linux_cache(), "ctrs-cargo-amd64");
    }
}
