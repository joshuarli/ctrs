//! A running ctrs guest: the VM plus the agent connection, with boot timings.

// Parts of this serve only the Mac (the window, boot timings).
#![cfg_attr(not(target_os = "macos"), allow(dead_code))]

use std::fs::File;
use std::io::{self, Read, Write};
use std::os::fd::AsFd;
#[cfg(target_os = "macos")]
use std::os::fd::AsRawFd;
use std::path::PathBuf;
use std::time::Duration;

use ctrs_proto::{HEADER, Hello, Msg};
use ctrs_vmm::{Config, Event, Vm};

#[cfg(target_os = "macos")]
#[path = "../../../guest/disk_capacity.rs"]
mod disk_capacity;
#[cfg(target_os = "macos")]
#[path = "../../../guest/ext4.rs"]
mod ext4;

#[derive(Debug, Default)]
pub struct BootOptions {
    /// Send the guest console to stdout.
    pub console: bool,
    /// Keep the guest console in a file, replacing the previous boot's file
    /// (the pre-capture content moves to `<path>.prev`). Used by the daemon
    /// so a crashed guest's oops trace survives the VM.
    pub console_file: Option<PathBuf>,
    /// Attach the persistent data disk (layers and containers). Without it
    /// the guest keeps them in memory, which is fine for a quick boot test.
    pub data_disk: bool,
    /// The VM's memory ceiling; 1 GiB if not set. The daemon sets a larger
    /// one and keeps the guest inside it with the balloon.
    pub memory_mib: Option<u64>,
    /// The VM's CPUs; 2 if not set.
    pub cpus: Option<usize>,
}

#[derive(Debug)]
pub struct Guest {
    vm: Vm,
    conn: File,
    /// Reused for every frame, so steady-state traffic does not allocate.
    frame: Vec<u8>,
    out: Vec<u8>,
    pub hello: Hello,
}

impl Guest {
    pub fn boot(opts: &BootOptions) -> io::Result<Guest> {
        // The Intel build opened on Apple Silicon runs under Rosetta, where
        // Virtualization.framework cannot boot its x86-64 guest.
        #[cfg(all(target_os = "macos", target_arch = "x86_64"))]
        if translated() {
            return Err(io::Error::other("this is ctrs for Intel Macs, and this Mac has Apple silicon: get the aarch64-apple-darwin build instead"));
        }
        if !Vm::is_supported() {
            return Err(io::Error::other(if cfg!(target_os = "linux") {
                "on Linux, ctrs runs containers on this machine's kernel and needs root: sudo ctrs daemon"
            } else {
                "this Mac does not support virtualization"
            }));
        }
        #[cfg(target_os = "linux")]
        let cfg = Config {
            cpus: 0,
            memory_mib: 0,
            kernel: PathBuf::new(),
            initrd: agent_binary(),
            cmdline: String::new(),
            console: console_fd(opts)?,
            agent_port: ctrs_proto::HOST_PORT,
            disk: None,
            share: None,
            rosetta_tag: None,
            nat_mac: None,
        };
        #[cfg(target_os = "macos")]
        let cfg = Self::vm_config(opts)?;
        Self::start(cfg)
    }

    /// The VM: kernel, initramfs, data disk, NAT, the Mac's files, Rosetta.
    #[cfg(target_os = "macos")]
    fn vm_config(opts: &BootOptions) -> io::Result<Config> {
        let dir = crate::config::guest_dir();
        // swiotlb=noforce: the VM's virtio devices address all of memory, so
        // the kernel's 64 MB bounce buffer would sit there unused.
        let mut cmdline = String::from("console=hvc0 rdinit=/init panic=-1 rcupdate.rcu_expedited=1 swiotlb=noforce");
        if !opts.console && opts.console_file.is_none() {
            cmdline.push_str(" quiet loglevel=0");
        }
        let cfg = Config {
            cpus: opts.cpus.unwrap_or(2),
            memory_mib: opts.memory_mib.unwrap_or(1024),
            kernel: dir.join(KERNEL),
            initrd: dir.join("initramfs.cpio"),
            cmdline,
            console: console_fd(opts)?,
            agent_port: ctrs_proto::HOST_PORT,
            disk: if opts.data_disk { Some(data_disk(&dir)?) } else { None },
            nat_mac: if opts.data_disk { Some(mac_address()?) } else { None },
            // The Mac's filesystem, for bind mounts: /mnt/mac in the guest.
            share: opts.data_disk.then(|| (PathBuf::from("/"), "ctrs-mac".to_owned())),
            rosetta_tag: opts.data_disk.then(|| "rosetta".to_owned()),
        };
        if !cfg.kernel.is_file() {
            return Err(missing_kernel(&cfg.kernel, std::env::current_exe().ok().as_deref()));
        }
        Ok(cfg)
    }

    fn start(cfg: Config) -> io::Result<Guest> {
        let vm = Vm::start(cfg)?;
        let conn = match vm.next_event(Duration::from_secs(10)) {
            Some(Event::GuestConnected(fd)) => File::from(fd),
            Some(Event::Stopped(why)) => {
                return Err(io::Error::other(format!("guest stopped before connecting: {why:?}")));
            }
            None => return Err(io::Error::new(io::ErrorKind::TimedOut, "guest did not connect within 10 s")),
        };
        let mut guest = Guest {
            vm,
            conn,
            frame: Vec::with_capacity(256),
            out: Vec::with_capacity(64),
            hello: Hello { protocol: 0, init_start_ns: 0, ready_ns: 0, mem_total_kib: 0, mem_available_kib: 0 },
        };
        guest.hello = match guest.read()? {
            Msg::Hello(h) => h,
            other => return Err(io::Error::other(format!("expected Hello, got {other:?}"))),
        };
        // The agent comes from the same install, so another version means the
        // files changed under a running ctrs: stop rather than misread it.
        if guest.hello.protocol != ctrs_proto::PROTOCOL {
            return Err(io::Error::other(format!(
                "the VM agent speaks protocol {}, this ctrs speaks {}: quit ctrs and open it again",
                guest.hello.protocol,
                ctrs_proto::PROTOCOL
            )));
        }
        // The guest has no real-time clock source of its own.
        let now = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default();
        guest.send(Msg::SetTime(now.as_nanos() as u64))?;
        Ok(guest)
    }

    /// Hands over the VM and the agent connection, for callers that drive the
    /// connection from several threads (the daemon).
    pub fn into_parts(self) -> (Vm, File) {
        (self.vm, self.conn)
    }

    fn send(&mut self, msg: Msg<'_>) -> io::Result<()> {
        self.out.clear();
        msg.encode(&mut self.out);
        self.conn.write_all(&self.out)
    }

    fn read(&mut self) -> io::Result<Msg<'_>> {
        self.frame.resize(4, 0);
        self.conn.read_exact(&mut self.frame[..4])?;
        let len = ctrs_proto::frame_len(self.frame[..4].try_into().unwrap())
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, format!("{e:?}")))?;
        self.frame.resize(len.max(HEADER), 0);
        self.conn.read_exact(&mut self.frame[4..])?;
        ctrs_proto::decode(&self.frame).map_err(|e| io::Error::new(io::ErrorKind::InvalidData, format!("{e:?}")))
    }
}

/// stdout for a debugging session, or the capture file rotated to `.prev`.
fn console_fd(opts: &BootOptions) -> io::Result<Option<std::os::fd::OwnedFd>> {
    if opts.console {
        return Ok(Some(io::stdout().as_fd().try_clone_to_owned()?));
    }
    opts.console_file.as_deref().map(open_console_capture).transpose()
}

/// The capture file for one boot, with the last generation kept as `.prev`.
fn open_console_capture(path: &std::path::Path) -> io::Result<std::os::fd::OwnedFd> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    if path.exists() {
        let mut prev = path.as_os_str().to_os_string();
        prev.push(".prev");
        std::fs::rename(path, PathBuf::from(prev))?;
    }
    Ok(std::fs::OpenOptions::new().create(true).append(true).open(path)?.into())
}

/// The agent on a Linux host: `CTRS_AGENT`, else `ctrs-init` beside `ctrs`.
#[cfg(target_os = "linux")]
fn agent_binary() -> PathBuf {
    if let Some(p) = std::env::var_os("CTRS_AGENT") {
        return PathBuf::from(p);
    }
    std::env::current_exe().ok().and_then(|e| e.parent().map(|d| d.join("ctrs-init"))).unwrap_or_else(|| PathBuf::from("ctrs-init"))
}

#[cfg(target_os = "macos")]
/// The guest's data disk, copied from the empty template on first use. On
/// APFS the copy is a clone: instant, and it takes no space until written.
fn data_disk(guest_dir: &std::path::Path) -> io::Result<PathBuf> {
    let vm = ctrs_image::Store::default_root()?.join("vm");
    std::fs::create_dir_all(&vm)?;
    let disk = vm.join("data.img");
    if !disk.exists() {
        // In a checkout the Intel guest (guest/out/x86_64) shares the one
        // template in guest/out.
        let template = Some(guest_dir.join("data.img")).filter(|t| t.is_file()).unwrap_or_else(|| guest_dir.join("../data.img"));
        let tmp = vm.join("data.img.tmp");
        if template.is_file() {
            std::fs::copy(&template, &tmp)
                .map_err(|e| io::Error::new(e.kind(), format!("copy data disk template {}: {e}", template.display())))?;
        } else {
            // The distribution may pack the 1 TiB template as a sparse tarball;
            // tar recreates its holes, so it stays small on disk.
            let packed = guest_dir.join("data.img.tgz");
            let unpack = vm.join("unpack");
            let _ = std::fs::remove_dir_all(&unpack);
            std::fs::create_dir_all(&unpack)?;
            let ok = std::process::Command::new("/usr/bin/tar").args(["-xzf"]).arg(&packed).arg("-C").arg(&unpack).status()?.success();
            if !ok {
                return Err(io::Error::other(format!("could not unpack the data disk template {}", packed.display())));
            }
            std::fs::rename(unpack.join("data.img"), &tmp)?;
            let _ = std::fs::remove_dir_all(&unpack);
        }
        std::fs::rename(tmp, &disk)?;
    }
    expand_data_disk(&disk, disk_capacity::MINIMUM_BYTES)
        .map_err(|e| io::Error::new(e.kind(), format!("validate or expand data disk {}: {e}", disk.display())))?;
    Ok(disk)
}

#[cfg(target_os = "macos")]
fn expand_data_disk(path: &std::path::Path, minimum_bytes: u64) -> io::Result<()> {
    use std::os::unix::fs::OpenOptionsExt;
    let mut file = std::fs::OpenOptions::new().read(true).write(true).custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK).open(path)?;
    let metadata = file.metadata()?;
    if !metadata.is_file() || metadata.len() % 512 != 0 || minimum_bytes % 512 != 0 {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "data disk must be a sector-aligned regular file"));
    }
    let geometry = ext4::geometry(&mut file)?;
    if geometry.filesystem_bytes > metadata.len() {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "data disk is shorter than its ext4 filesystem"));
    }
    let target = metadata.len().max(minimum_bytes);
    let grow_filesystem = geometry.filesystem_bytes < target / geometry.block_bytes * geometry.block_bytes;
    if grow_filesystem {
        let mut space = std::mem::MaybeUninit::<libc::statvfs>::uninit();
        // SAFETY: space is writable; fstatvfs initializes it on success for this valid descriptor.
        if unsafe { libc::fstatvfs(file.as_raw_fd(), space.as_mut_ptr()) } != 0 {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: fstatvfs returned success.
        let space = unsafe { space.assume_init() };
        let available = (space.f_bavail as u64).checked_mul(space.f_frsize)
            .filter(|_| space.f_frsize > 0)
            .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "host free space is unavailable"))?;
        if available < 1 << 30 {
            return Err(io::Error::new(io::ErrorKind::StorageFull, "at least 1 GiB of free host space is required before expanding the data filesystem"));
        }
    }
    if target > metadata.len() {
        file.set_len(target)?;
    }
    if grow_filesystem {
        // The larger backing length must survive power loss before guest resize can commit a larger filesystem.
        // SAFETY: file owns a valid descriptor; F_FULLFSYNC takes no third argument.
        if unsafe { libc::fcntl(file.as_raw_fd(), libc::F_FULLFSYNC) } < 0 {
            return Err(io::Error::last_os_error());
        }
    }
    Ok(())
}

#[cfg(target_os = "macos")]
/// The VM's MAC address: made once (locally administered, unicast) and kept
/// beside the data disk, so the DHCP lease stays the same across boots.
fn mac_address() -> io::Result<String> {
    let path = ctrs_image::Store::default_root()?.join("vm/mac");
    if let Ok(s) = std::fs::read_to_string(&path) {
        let s = s.trim().to_owned();
        if s.len() == 17 {
            return Ok(s);
        }
    }
    let mut b = [0u8; 6];
    std::fs::File::open("/dev/urandom")?.read_exact(&mut b)?;
    b[0] = (b[0] | 0x02) & !0x01;
    let mac = b.iter().map(|x| format!("{x:02x}")).collect::<Vec<_>>().join(":");
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    std::fs::write(&path, &mac)?;
    Ok(mac)
}

/// The guest kernel: an arm64 `Image` for Apple Silicon, an
/// x86-64 `bzImage` for Intel (the build for the other architecture lives
/// under `guest/out/x86_64`).
#[cfg(target_arch = "x86_64")]
pub const KERNEL: &str = "bzImage";
#[cfg(not(target_arch = "x86_64"))]
pub const KERNEL: &str = "Image";

/// Whether this process runs under Rosetta (`sysctl.proc_translated`).
#[cfg(all(target_os = "macos", target_arch = "x86_64"))]
fn translated() -> bool {
    let mut on: libc::c_int = 0;
    let mut len = std::mem::size_of::<libc::c_int>();
    // SAFETY: sysctlbyname writes an int into `on`; on a Mac without
    // Rosetta the name does not exist and `on` stays 0.
    unsafe { libc::sysctlbyname(c"sysctl.proc_translated".as_ptr(), (&mut on as *mut libc::c_int).cast(), &mut len, std::ptr::null_mut(), 0) };
    on == 1
}

/// The error for a guest kernel that isn't there. Usually the engine ran
/// from a checkout whose `guest/out/` was cleaned: say that, not a bare path.
#[cfg(target_os = "macos")]
fn missing_kernel(kernel: &std::path::Path, exe: Option<&std::path::Path>) -> io::Error {
    let msg = match exe {
        Some(exe) if !exe.exists() => format!("{} was deleted or moved while it ran: rebuild it with `cargo xtask host`", "the ctrs binary"),
        // The whole path, so it shows where ctrs looked.
        _ => format!("the guest kernel {} is missing: rebuild it with `cargo xtask kernel`", std::path::absolute(kernel).unwrap_or_else(|_| kernel.to_owned()).display()),
    };
    io::Error::new(io::ErrorKind::NotFound, msg)
}


#[cfg(all(test, target_os = "macos"))]
mod disk_expansion_tests {
    use super::*;
    use std::io::Cursor;
    use std::os::unix::fs::MetadataExt;

    struct Scratch(PathBuf);
    impl Scratch {
        fn new() -> Self {
            static NEXT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
            let path = std::env::temp_dir().join(format!("ctrs-disk-grow-{}-{}", std::process::id(), NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)));
            std::fs::create_dir(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for Scratch {
        fn drop(&mut self) { let _ = std::fs::remove_dir_all(&self.0); }
    }
    fn disk(path: &std::path::Path, declared_bytes: u64) -> Vec<u8> {
        let mut bytes = vec![0u8; 16 * 1024];
        bytes[1024 + 0x38..1024 + 0x3a].copy_from_slice(&0xef53u16.to_le_bytes());
        bytes[1024 + 4..1024 + 8].copy_from_slice(&((declared_bytes / 4096) as u32).to_le_bytes());
        bytes[1024 + 0x18..1024 + 0x1c].copy_from_slice(&2u32.to_le_bytes());
        bytes[4096..4104].copy_from_slice(b"userdata");
        std::fs::write(path, &bytes).unwrap();
        bytes
    }
    #[test]
    fn disk_growth_preserves_bytes_inode_and_larger_capacity() {
        let scratch = Scratch::new();
        let path = scratch.0.join("data.img");
        let before = disk(&path, 16 * 1024);
        let inode = std::fs::metadata(&path).unwrap().ino();
        expand_data_disk(&path, 32 * 1024).unwrap();
        let grown = std::fs::read(&path).unwrap();
        assert_eq!(&grown[..before.len()], before);
        assert!(grown[before.len()..].iter().all(|b| *b == 0));
        assert_eq!(grown.len(), 32 * 1024);
        assert_eq!(std::fs::metadata(&path).unwrap().ino(), inode);
        assert_eq!(ext4::geometry(&mut Cursor::new(grown)).unwrap().filesystem_bytes, 16 * 1024);
        expand_data_disk(&path, 8 * 1024).unwrap();
        assert_eq!(std::fs::metadata(&path).unwrap().len(), 32 * 1024);
    }
    #[test]
    fn unknown_or_truncated_media_is_not_extended() {
        let scratch = Scratch::new();
        let path = scratch.0.join("data.img");
        for declared in [32 * 1024, 0] {
            let mut before = disk(&path, declared);
            if declared == 0 { before[1024 + 0x38] = 0; std::fs::write(&path, &before).unwrap(); }
            assert!(expand_data_disk(&path, 64 * 1024).is_err());
            assert_eq!(std::fs::read(&path).unwrap(), before);
        }
        assert!(expand_data_disk(std::path::Path::new("/dev/null"), 64 * 1024).is_err());
    }
    #[test]
    fn disk_growth_does_not_follow_a_symlink() {
        let scratch = Scratch::new();
        let path = scratch.0.join("data.img");
        let before = disk(&path, 16 * 1024);
        let link = scratch.0.join("link");
        std::os::unix::fs::symlink(&path, &link).unwrap();
        assert!(expand_data_disk(&link, 32 * 1024).is_err());
        assert_eq!(std::fs::read(&path).unwrap(), before);
    }
}
