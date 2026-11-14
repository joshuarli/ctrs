//! Build tasks for Kiri. Run with `cargo xtask <task>`.
//!
//!   guest    build kiri-init for the guest and pack guest/out/initramfs.cpio
//!   kernel   build the guest kernel into guest/out/Image (needs a Docker engine)
//!   disk     make the empty data disk template guest/out/data.img (needs a Docker engine)
//!   host     build the `kiri` binary and sign it with the virtualization entitlement
//!   app      host + target/Kiri.app: the guest, the icon and a bundled docker CLI,
//!            Compose and buildx
//!   app-dev  app + target/dev/Kiri Dev.app: the same app as a second Kiri, with
//!            its own engine, containers and settings (crates/kiri/src/flavor.rs)
//!            and a DEV band on its icon; never notarized. `app-dev builds`
//!            makes Kiri Builds.app instead: one more, for one feature
//!   release  app + target/Kiri-<version>-arm64.tar.gz and its update feed
//!            (latest-mac-arm64.json)
//!   linux    `kiri` and `kiri-init` for a Linux host, in target/linux/release
//!            (built in a Linux container: needs a Docker engine, Kiri works)
//!   all      guest + host
//!
//! `--arch x86_64` (or `intel`) makes guest, kernel, host, app, app-lite,
//! dmg, release and pack build Kiri for Intel Macs instead: an x86-64 guest
//! in guest/out/x86_64, the host binary for x86_64-apple-darwin, and
//! target/intel/Kiri.app with Intel builds of the docker CLI, Compose and
//! buildx; its DMG, tarball and feed carry `-x86_64` in their names
//! (latest-mac-x86_64.json), as Apple silicon's carry `-arm64`.

use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, ExitCode};

/// Which Mac a build is for. Kiri ships one app per architecture rather
/// than a universal one: the bundled docker CLI, Compose and buildx are most
/// of the download, and a universal app would carry both builds of each.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum Arch {
    Arm64,
    X86_64,
}

impl Arch {
    /// `--arch x86_64` (`amd64`, `intel`) anywhere after the task; arm64 otherwise.
    fn from_args() -> Arch {
        let args = std::env::args().skip(2).collect::<Vec<_>>();
        let intel = args.windows(2).any(|w| w[0] == "--arch" && matches!(w[1].as_str(), "x86_64" | "amd64" | "intel"));
        if intel { Arch::X86_64 } else { Arch::Arm64 }
    }

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

    /// The kernel file in guest/out and in the app (crates/kiri/src/guest.rs).
    fn kernel(self) -> &'static str {
        match self {
            Arch::Arm64 => "Image",
            Arch::X86_64 => "bzImage",
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
        if self.native() { root.join("target/release/kiri") } else { root.join("target").join(self.host_target()).join("release/kiri") }
    }

    fn native(self) -> bool {
        (self == Arch::X86_64) == cfg!(target_arch = "x86_64")
    }

    /// In release file names: every one says which Mac it's for.
    fn suffix(self) -> &'static str {
        match self {
            Arch::Arm64 => "-arm64",
            Arch::X86_64 => "-x86_64",
        }
    }

    /// The app's folder under target/.
    fn app_dir(self, lite: bool) -> &'static str {
        match (self, lite) {
            (Arch::Arm64, false) => "target/Kiri.app",
            (Arch::Arm64, true) => "target/lite/Kiri.app",
            (Arch::X86_64, false) => "target/intel/Kiri.app",
            (Arch::X86_64, true) => "target/intel/lite/Kiri.app",
        }
    }

    fn cli(self) -> cli_pins::MacArch {
        match self {
            Arch::Arm64 => cli_pins::MacArch::Arm64,
            Arch::X86_64 => cli_pins::MacArch::X86_64,
        }
    }
}

fn main() -> ExitCode {
    let task = std::env::args().nth(1).unwrap_or_default();
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap().to_path_buf();
    let arch = Arch::from_args();
    let result = match task.as_str() {
        "guest" => guest(&root, arch),
        "kernel" => kernel(&root, arch),
        "disk" => disk(&root),
        "host" => host(&root, arch),
        "linux" => linux(&root),
        "app" => app(&root, arch, false).map(drop),
        "app-lite" => app(&root, arch, true).map(drop),
        // `app-dev builds`: Kiri Builds.app, a Kiri Dev of its own for one feature.
        "app-dev" => match std::env::args().nth(2) {
            Some(f) if f.is_empty() || !f.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit()) || f == "dev" => {
                eprintln!("a feature name is lower-case letters and digits, not `dev`");
                return ExitCode::FAILURE;
            }
            feature => app(&root, Arch::Arm64, false).and_then(|a| app_dev(&root, &a, feature.as_deref())),
        },
        // The disk image of the app already built, signed but not notarized (to look at it).
        "dmg" => dmg(&root, &root.join(arch.app_dir(false)), arch, false).map(|d| println!("{}", d.display())),
        "release" => app(&root, arch, false).and_then(|a| release(&root, &a, arch)),
        // Signs the app already built (on a Mac without the identity).
        "sign" => sign_app(&root, &root.join(arch.app_dir(false)), arch, false),
        // Packs the app already built, without rebuilding it.
        "pack" => release(&root, &root.join(arch.app_dir(false)), arch),
        "all" => guest(&root, arch).and_then(|()| host(&root, arch)),
        _ => {
            eprintln!("usage: cargo xtask <guest|kernel|disk|host|linux|app|app-lite|app-dev|release|sign|pack|all> [--arch arm64]");
            return ExitCode::FAILURE;
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
    // kiri-init is pure Rust: rust-lld links it against Rust's own musl, as
    // .cargo/config.toml does for arm64. Set here, not there, so the Linux
    // engine build (which links C) keeps its own linker.
    run(Command::new(env!("CARGO"))
        .current_dir(root)
        .env("CARGO_TARGET_X86_64_UNKNOWN_LINUX_MUSL_LINKER", "rust-lld")
        .args(["build", "--release", "-p", "kiri-init", "--target", target]))?;
    let init = fs::read(root.join("target").join(target).join("release/kiri-init"))?;

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

/// The arm64 kernel builds in the cached tree in the `kiri-kbuild` volume;
/// the x86-64 one in its own, `kiri-kbuild-x86_64`, since both build in the
/// source tree. On Apple Silicon the x86-64 kernel is cross-compiled.
fn kernel(root: &Path, arch: Arch) -> io::Result<()> {
    let src = root.join("guest/kernel");
    let out = arch.guest_out(root)?;
    let (karch, cache) = match arch {
        Arch::Arm64 => ("KARCH=arm64", "kiri-kbuild:/build"),
        Arch::X86_64 => ("KARCH=x86_64", "kiri-kbuild-x86_64:/build"),
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
        "debian:trixie",
        "sh",
        "/src/build.sh",
    ]))
}

/// A sparse 64 GiB ext4 image with lazily initialised inode tables: it uses a
/// few MB on the Mac until data is written. Each install copies it (an APFS
/// clone, so instant) into its data directory on first boot.
/// The same ext4 image serves both architectures.
fn disk(root: &Path) -> io::Result<()> {
    let out = Arch::Arm64.guest_out(root)?;
    run(Command::new("docker").args([
        "run",
        "--rm",
        "-v",
        &format!("{}:/out", out.display()),
        "debian:trixie",
        "sh",
        "-c",
        "set -e; apt-get update -qq >/dev/null && apt-get install -y -qq e2fsprogs >/dev/null; \
         rm -f /out/data.img; truncate -s 64G /out/data.img; \
         mkfs.ext4 -q -F -m 0 -L kiri-data -E lazy_itable_init=1,lazy_journal_init=1 /out/data.img",
    ]))?;
    let meta = fs::metadata(out.join("data.img"))?;
    println!("{} ({} GiB sparse)", out.join("data.img").display(), meta.len() >> 30);
    Ok(())
}

fn host(root: &Path, arch: Arch) -> io::Result<()> {
    let mut build = Command::new(env!("CARGO"));
    build.current_dir(root).args(["build", "--release", "-p", "kiri"]);
    if !arch.native() {
        build.args(["--target", arch.host_target()]);
    }
    run(&mut build)?;
    let bin = arch.host_bin(root);
    if cfg!(target_os = "macos") {
        // Virtualization.framework refuses to start a VM without this entitlement.
        run(Command::new("codesign").args(["--force", "--sign", "-", "--entitlements"])
            .arg(root.join("crates/kiri/kiri.entitlements"))
            .arg(&bin))?;
    }
    println!("{} ({} KiB)", bin.display(), fs::metadata(&bin)?.len() / 1024);
    Ok(())
}

/// The Linux host build: native, in a Rust container, so C dependencies
/// (ring) find a compiler. The cargo registry is cached in a volume.
/// `--arch amd64` builds x86-64 binaries (on Apple silicon the container
/// runs under Rosetta).
fn linux(root: &Path) -> io::Result<()> {
    let amd64 = std::env::args().skip(2).collect::<Vec<_>>().windows(2).any(|w| w[0] == "--arch" && (w[1] == "amd64" || w[1] == "x86_64"));
    linux_build(root, amd64)
}

fn linux_build(root: &Path, amd64: bool) -> io::Result<()> {
    let (platform, out, cache) = if amd64 { ("linux/amd64", "linux-x86_64", "kiri-cargo-amd64") } else { ("linux/arm64", "linux", "kiri-cargo") };
    run(Command::new("docker").args(["run", "--rm", "--platform", platform, "-v"]).arg(format!("{}:/src", root.display())).args([
        "-v",
        &format!("{cache}:/usr/local/cargo/registry"),
        "-w",
        "/src",
        "-e",
        &format!("CARGO_TARGET_DIR=/src/target/{out}"),
        // The repo's cross-linking setting is for the guest build from macOS.
        "-e",
        "CARGO_TARGET_AARCH64_UNKNOWN_LINUX_MUSL_LINKER=cc",
        "rust:1-alpine",
        "sh",
        "-c",
        "apk add -q musl-dev && cargo build --release -p kiri -p kiri-init",
    ]))?;
    for b in ["kiri", "kiri-init"] {
        let p = root.join("target").join(out).join("release").join(b);
        println!("{} ({} KiB)", p.display(), fs::metadata(&p)?.len() / 1024);
    }
    Ok(())
}

/// The docker CLI tools bundled into Kiri.app, pinned.
/// SHA-256s from the releases (GitHub's asset digests; the docker tarball
/// as download.docker.com served it), checked before anything is bundled.
#[path = "../../crates/kiri/src/cli_pins.rs"]
mod cli_pins;


/// Downloads `url` into the cache once; returns the cached path.
fn fetch(cache: &Path, name: &str, url: &str) -> io::Result<PathBuf> {
    let path = cache.join(name);
    if !path.is_file() {
        fs::create_dir_all(cache)?;
        let tmp = cache.join(format!("{name}.part"));
        run(Command::new("curl").args(["-fsSL", "--retry", "3", "-o"]).arg(&tmp).arg(url))?;
        fs::rename(&tmp, &path)?;
    }
    Ok(path)
}

fn sha256(path: &Path) -> io::Result<String> {
    if cfg!(windows) {
        // certutil prints a header line, the hash, then a footer.
        let out = Command::new("certutil").args(["-hashfile"]).arg(path).arg("SHA256").output()?;
        let text = String::from_utf8_lossy(&out.stdout).into_owned();
        return Ok(text.lines().nth(1).unwrap_or_default().replace(' ', "").to_ascii_lowercase());
    }
    let out = Command::new("shasum").args(["-a", "256"]).arg(path).output()?;
    Ok(String::from_utf8_lossy(&out.stdout).split_whitespace().next().unwrap_or_default().to_owned())
}

/// Checks a download against its pinned SHA-256; a mismatch deletes it.
fn verify(file: &Path, want: &str) -> io::Result<()> {
    let got = sha256(file)?;
    if got != want {
        let _ = fs::remove_file(file);
        return Err(io::Error::other(format!("{}: SHA-256 {got}, expected {want}", file.display())));
    }
    Ok(())
}

/// target/Kiri.app, signed with the virtualization entitlement. `lite`:
/// target/lite/Kiri.app, without the docker CLI, Compose and buildx, which
/// Kiri Lite downloads on first launch (src/tools.rs).
fn app(root: &Path, arch: Arch, lite: bool) -> io::Result<PathBuf> {
    host(root, arch)?;
    let version = env!("CARGO_PKG_VERSION");
    // Info.plist's versions are numbers only: a test build's 0.1.8-dev.42 is 0.1.8 there.
    let plain = version.split('-').next().unwrap_or(version);
    let app = root.join(arch.app_dir(lite));
    let _ = fs::remove_dir_all(&app);
    let contents = app.join("Contents");
    let (macos, res) = (contents.join("MacOS"), contents.join("Resources"));
    for d in [&macos, &res.join("guest")] {
        fs::create_dir_all(d)?;
    }
    if !lite {
        fs::create_dir_all(res.join("bin/cli-plugins"))?;
    }
    fs::copy(arch.host_bin(root), macos.join("kiri"))?;
    // In Resources, not loose in Contents: codesign refuses a file there
    // ("code object is not signed at all ... In subcomponent: Contents/LICENSE").
    fs::copy(root.join("LICENSE"), res.join("LICENSE"))?;
    fs::copy(root.join("NOTICE"), res.join("NOTICE"))?;
    fs::copy(root.join("guest/kernel/SOURCE_OFFER.md"), res.join("KERNEL_SOURCE_OFFER.md"))?;
    let out = arch.guest_out(root)?;
    for f in [arch.kernel(), "initramfs.cpio"] {
        fs::copy(out.join(f), res.join("guest").join(f))?;
    }
    // The disk template is 64 GiB sparse. Packed as a sparse tarball it is a
    // few hundred KB, and zips, notarization and downloads never see the
    // 64 GiB; Kiri unpacks it on first boot.
    run(Command::new("tar").args(["-cSzf"]).arg(res.join("guest/data.img.tgz")).arg("-C").arg(Arch::Arm64.guest_out(root)?).arg("data.img"))?;

    if !lite {
        // Intel downloads in their own folder: the docker tarball has the
        // same name for both architectures.
        let cache = root.join(if arch == Arch::X86_64 { "target/cli-cache/x86_64" } else { "target/cli-cache" });
        let mac = arch.cli();
        let [(docker_v, docker_sum), (compose_v, compose_sum), (buildx_v, buildx_sum)] = mac.tools();
        let tgz = fetch(&cache, &format!("docker-{docker_v}.tgz"), &mac.docker_url(docker_v))?;
        verify(&tgz, docker_sum)?;
        run(Command::new("tar").args(["-xzf"]).arg(&tgz).arg("-C").arg(&cache).arg("docker/docker"))?;
        fs::copy(cache.join("docker/docker"), res.join("bin/docker"))?;
        let compose = fetch(&cache, &format!("docker-compose-darwin-{}-{compose_v}", mac.compose_arch()), &mac.compose_url(compose_v))?;
        verify(&compose, compose_sum)?;
        fs::copy(&compose, res.join("bin/cli-plugins/docker-compose"))?;
        let buildx = fetch(&cache, &mac.buildx_name(buildx_v), &mac.buildx_url(buildx_v))?;
        verify(&buildx, buildx_sum)?;
        fs::copy(&buildx, res.join("bin/cli-plugins/docker-buildx"))?;
        for f in ["bin/docker", "bin/cli-plugins/docker-compose", "bin/cli-plugins/docker-buildx"] {
            run(Command::new("chmod").arg("755").arg(res.join(f)))?;
        }
    }

    // The icon, from the brand PNGs.
    let iconset = root.join("target/Kiri.iconset");
    let _ = fs::remove_dir_all(&iconset);
    fs::create_dir_all(&iconset)?;
    let png = root.join("brand/icon/png");
    for (size, scale) in [(16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2), (256, 1), (256, 2), (512, 1), (512, 2)] {
        let px = size * scale;
        let name = if scale == 1 { format!("icon_{size}x{size}.png") } else { format!("icon_{size}x{size}@2x.png") };
        fs::copy(png.join(format!("kiri-app-icon-{px}.png")), iconset.join(name))?;
    }
    run(Command::new("iconutil").args(["-c", "icns", "-o"]).arg(res.join("Kiri.icns")).arg(&iconset))?;
    fs::remove_dir_all(&iconset)?;

    fs::write(
        contents.join("Info.plist"),
        format!(
            r#"<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Kiri</string>
  <key>CFBundleDisplayName</key><string>Kiri</string>
  <key>CFBundleIdentifier</key><string>dev.kiri.app</string>
  <key>CFBundleExecutable</key><string>kiri</string>
  <key>CFBundleIconFile</key><string>Kiri</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>{plain}</string>
  <key>CFBundleVersion</key><string>{plain}</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.developer-tools</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSLocalNetworkUsageDescription</key><string>Kiri lets containers reach devices and services on your network, and serves the ports they publish.</string>
  <key>NSDesktopFolderUsageDescription</key><string>Kiri shares this folder with containers you mount it into.</string>
  <key>NSDocumentsFolderUsageDescription</key><string>Kiri shares this folder with containers you mount it into.</string>
  <key>NSDownloadsFolderUsageDescription</key><string>Kiri saves files you download from containers here, and shares the folder with containers you mount it into.</string>
  <key>NSRemovableVolumesUsageDescription</key><string>Kiri shares this drive with containers you mount it into.</string>
  <key>NSNetworkVolumesUsageDescription</key><string>Kiri shares this network drive with containers you mount it into.</string>
</dict>
</plist>
"#
        ),
    )?;
    sign_app(root, &app, arch, lite)?;
    let size = Command::new("du").args(["-sh"]).arg(&app).output()?;
    println!("{} ({})", app.display(), String::from_utf8_lossy(&size.stdout).split_whitespace().next().unwrap_or("?"));
    Ok(app)
}

/// target/dev/Kiri Dev.app, from the app just built: its own name and
/// bundle identifier, which make the binary Kiri Dev, and the icon with a
/// DEV band. Signed again without the hardened runtime or a timestamp: it
/// is never notarized, and the timestamp asks Apple's server on every build.
/// With a feature, `builds`: target/dev/Kiri Builds.app, `dev.kiri.app.builds`,
/// a BUILDS band, and its own engine beside Kiri's and Kiri Dev's.
fn app_dev(root: &Path, built: &Path, feature: Option<&str>) -> io::Result<()> {
    let (name, id, band, state) = match feature {
        None => ("Kiri Dev".to_owned(), "dev.kiri.app.dev".to_owned(), "DEV".to_owned(), "kiri-dev".to_owned()),
        Some(f) => (format!("Kiri {}{}", f[..1].to_ascii_uppercase(), &f[1..]), format!("dev.kiri.app.{f}"), f.to_ascii_uppercase(), format!("kiri-{f}")),
    };
    let dir = root.join("target/dev");
    let app = dir.join(format!("{name}.app"));
    let _ = fs::remove_dir_all(&app);
    fs::create_dir_all(&dir)?;
    run(Command::new("ditto").arg(built).arg(&app))?;
    let contents = app.join("Contents");
    let plist = fs::read_to_string(contents.join("Info.plist"))?
        .replace("<key>CFBundleName</key><string>Kiri</string>", &format!("<key>CFBundleName</key><string>{name}</string>"))
        .replace("<key>CFBundleDisplayName</key><string>Kiri</string>", &format!("<key>CFBundleDisplayName</key><string>{name}</string>"))
        .replace("<string>dev.kiri.app</string>", &format!("<string>{id}</string>"));
    fs::write(contents.join("Info.plist"), plist)?;

    let png = root.join("target/kiri-dev-icon.png");
    run(Command::new("swift").arg(root.join("xtask/dev-icon.swift")).arg(root.join("brand/icon/png/kiri-app-icon-1024.png")).arg(&png).arg(&band))?;
    let iconset = root.join("target/KiriDev.iconset");
    let _ = fs::remove_dir_all(&iconset);
    fs::create_dir_all(&iconset)?;
    for (size, scale) in [(16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2), (256, 1), (256, 2), (512, 1), (512, 2)] {
        let name = if scale == 1 { format!("icon_{size}x{size}.png") } else { format!("icon_{size}x{size}@2x.png") };
        let px = (size * scale).to_string();
        run(Command::new("sips").args(["-z", &px, &px]).arg(&png).arg("--out").arg(iconset.join(name)).stdout(std::process::Stdio::null()))?;
    }
    run(Command::new("iconutil").args(["-c", "icns", "-o"]).arg(contents.join("Resources/Kiri.icns")).arg(&iconset))?;
    fs::remove_dir_all(&iconset)?;

    let identity = signing_identity();
    let entitlements = root.join("crates/kiri/kiri.entitlements");
    for target in [contents.join("MacOS/kiri"), app.clone()] {
        run(Command::new("codesign").args(["--force", "--sign", &identity, "--entitlements"]).arg(&entitlements).arg(target))?;
    }
    run(Command::new("codesign").args(["--verify", "--deep", "--strict"]).arg(&app))?;
    println!("{}: its own engine (~/.{state}, docker context {state}); open it from there or copy it to /Applications", app.display());
    Ok(())
}

/// `KIRI_SIGN_IDENTITY`, else the keychain's Developer ID Application
/// identity, else ad hoc ("-"), which runs only on this Mac.
fn signing_identity() -> String {
    if let Ok(id) = std::env::var("KIRI_SIGN_IDENTITY") {
        return id;
    }
    let out = Command::new("security").args(["find-identity", "-v", "-p", "codesigning"]).output().map(|o| String::from_utf8_lossy(&o.stdout).into_owned()).unwrap_or_default();
    out.lines()
        .find_map(|l| l.split('"').nth(1).filter(|n| n.starts_with("Developer ID Application:")).map(str::to_owned))
        .unwrap_or_else(|| "-".to_owned())
}

/// codesign with the hardened runtime and a secure timestamp, which
/// notarization requires; ad hoc signatures get neither.
fn sign(identity: &str, entitlements: Option<&Path>) -> Command {
    let mut c = Command::new("codesign");
    c.args(["--force", "--sign", identity]);
    if identity != "-" {
        c.args(["--options", "runtime", "--timestamp"]);
    }
    if let Some(e) = entitlements {
        c.arg("--entitlements").arg(e);
    }
    c
}

/// target/Kiri-<version>-arm64.dmg (-x86_64 for Intel): the app and an Applications shortcut, signed,
/// then notarized by Apple in one submission, with the ticket stapled to the
/// DMG and the app so Gatekeeper opens both offline. `KIRI_NOTARY_PROFILE`
/// names credentials stored with `xcrun notarytool store-credentials`;
/// unset or empty (as CI sets it when not notarizing) skips this.
/// The drag-to-install disk image: a fixed
/// Finder window with Kiri on the left, Applications on the right and an
/// arrow between them (scripts/dmg-background.swift draws it,
/// scripts/dmg-settings.py places the icons). dmgbuild writes the window's
/// .DS_Store directly, with no Finder or AppleScript; it is installed,
/// pinned, in a throwaway virtualenv under target/. Signed, not notarized.
/// Signs an app `app` built (here, or on a Mac without the Developer ID
/// identity, such as the Intel CI Mac), and notarizes it if
/// KIRI_NOTARY_PROFILE names a profile.
fn sign_app(root: &Path, app: &Path, arch: Arch, lite: bool) -> io::Result<()> {
    let (macos, res) = (app.join("Contents/MacOS"), app.join("Contents/Resources"));
    // Inside out: the helper binaries first, then the app with the
    // entitlement Virtualization.framework requires.
    let identity = signing_identity();
    if !lite {
        for f in ["bin/docker", "bin/cli-plugins/docker-compose", "bin/cli-plugins/docker-buildx"] {
            run(sign(&identity, None).arg(res.join(f)))?;
        }
    }
    run(sign(&identity, Some(&root.join("crates/kiri/kiri.entitlements"))).arg(macos.join("kiri")))?;
    run(sign(&identity, Some(&root.join("crates/kiri/kiri.entitlements"))).arg(app))?;
    run(Command::new("codesign").args(["--verify", "--deep", "--strict"]).arg(app))?;
    println!("signed: {}", if identity == "-" { "ad hoc (no Developer ID identity found)" } else { identity.as_str() });
    if let Some(profile) = std::env::var("KIRI_NOTARY_PROFILE").ok().filter(|p| !p.is_empty()) {
        notarize(root, app, &profile, arch, lite)?;
    }
    Ok(())
}

fn dmg(root: &Path, app: &Path, arch: Arch, lite: bool) -> io::Result<PathBuf> {
    const DMGBUILD: &str = "1.6.7";
    let version = env!("CARGO_PKG_VERSION");
    let venv = root.join(format!("target/dmgbuild-venv-{DMGBUILD}"));
    let dmgbuild = venv.join("bin/dmgbuild");
    if !Command::new(&dmgbuild).arg("--help").stdout(std::process::Stdio::null()).stderr(std::process::Stdio::null()).status().is_ok_and(|s| s.success()) {
        let _ = fs::remove_dir_all(&venv);
        run(Command::new("python3").args(["-m", "venv"]).arg(&venv))?;
        run(Command::new(venv.join("bin/pip")).args(["install", "--quiet", "--disable-pip-version-check", &format!("dmgbuild=={DMGBUILD}")]))?;
    }
    let bg = root.join("target/dmg-background");
    fs::create_dir_all(&bg)?;
    run(Command::new("swift").arg(root.join("scripts/dmg-background.swift")).arg(bg.join("background")))?;
    let dmg = root.join(format!("target/Kiri-{}{version}{}.dmg", if lite { "Lite-" } else { "" }, arch.suffix()));
    let _ = fs::remove_file(&dmg);
    run(Command::new(&dmgbuild)
        .arg("-s")
        .arg(root.join("scripts/dmg-settings.py"))
        .arg("-D")
        .arg(format!("app={}", app.display()))
        .arg("-D")
        .arg(format!("background={}", bg.join("background.png").display()))
        .arg(match (lite, arch) {
            (false, Arch::Arm64) => "Kiri",
            (true, Arch::Arm64) => "Kiri Lite",
            (false, Arch::X86_64) => "Kiri for Intel",
            (true, Arch::X86_64) => "Kiri Lite for Intel",
        })
        .arg(&dmg))?;
    run(sign(&signing_identity(), None).arg(&dmg))?;
    Ok(dmg)
}

fn notarize(root: &Path, app: &Path, profile: &str, arch: Arch, lite: bool) -> io::Result<()> {
    let dmg = dmg(root, app, arch, lite)?;
    run(Command::new("xcrun").args(["notarytool", "submit"]).arg(&dmg).args(["--keychain-profile", profile, "--wait"]))?;
    run(Command::new("xcrun").args(["stapler", "staple"]).arg(&dmg))?;
    run(Command::new("xcrun").args(["stapler", "staple"]).arg(app))?;
    println!("notarized and stapled: {}", dmg.display());
    Ok(())
}

/// A string's JSON form, without the quotes.
fn json_escape(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            '"' => out += "\\\"",
            '\\' => out += "\\\\",
            '\n' => out += "\\n",
            '\r' => out += "\\r",
            '\t' => out += "\\t",
            c if (c as u32) < 0x20 => out += &format!("\\u{:04x}", c as u32),
            c => out.push(c),
        }
    }
    out
}

/// What's new, for a feed (Mac's and Windows'): KIRI_RELEASE_NOTES names a
/// Markdown file ("## New", "- a line") shown in the window's What's new;
/// KIRI_RELEASE_NOTES_URL a runkiri.com page. Empty when neither is set.
fn feed_notes() -> io::Result<String> {
    let mut extra = String::new();
    if let Ok(path) = std::env::var("KIRI_RELEASE_NOTES") {
        extra += &format!(",\"notes\":\"{}\"", json_escape(&fs::read_to_string(&path)?));
    }
    if let Ok(url) = std::env::var("KIRI_RELEASE_NOTES_URL") {
        extra += &format!(",\"notes_url\":\"{}\"", json_escape(&url));
    }
    Ok(extra)
}

/// target/Kiri-<version>-arm64.tar.gz (sparse-aware, so the disk template
/// stays small) and target/latest-mac-arm64.json, the feed that Mac's app
/// reads (crates/kiri/src/update.rs); for Intel, -x86_64 in both.
fn release(root: &Path, app: &Path, arch: Arch) -> io::Result<()> {
    let version = env!("CARGO_PKG_VERSION");
    let suffix = arch.suffix();
    let tarball = root.join(format!("target/Kiri-{version}{suffix}.tar.gz"));
    run(Command::new("tar").args(["-cSzf"]).arg(&tarball).arg("-C").arg(app.parent().unwrap_or(root)).arg("Kiri.app"))?;
    let sum = sha256(&tarball)?;
    let base = std::env::var("KIRI_RELEASE_BASE").unwrap_or_else(|_| "https://download.runkiri.com".to_owned());
    let extra = feed_notes()?;
    let feed = format!("{{\"version\":\"{version}\",\"url\":\"{base}/Kiri-{version}{suffix}.tar.gz\",\"sha256\":\"{sum}\"{extra}}}\n");
    let feed_path = root.join(format!("target/latest-mac{suffix}.json"));
    fs::write(&feed_path, &feed)?;
    println!("{} ({} KiB)\n{}", tarball.display(), fs::metadata(&tarball)?.len() / 1024, feed_path.display());
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
