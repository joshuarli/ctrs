//! `kiri daemon`: owns the VM and serves the Docker Engine API on a Unix
//! socket. The docker CLI (context `kiri`), the kiri CLI and the window are
//! all clients of it.

#[cfg(target_os = "linux")]
pub mod access;
mod api;
mod binds;
mod builder;
pub mod dns;
pub mod proxy;
mod engine;
#[cfg(feature = "h12tiny")]
mod h12tiny;
mod filters;
mod health;
mod hostetc;
mod hostopts;
mod mirror;
mod http;
mod logfile;
mod names;
mod network;
mod ops;
pub(crate) mod ports;
mod pulls;
pub mod time;
mod vmcpu;
mod vmlink;
mod volumes;

use std::io;
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::{UnixListener, UnixStream};
use std::os::unix::io::{AsRawFd, OwnedFd};
use std::path::{Path, PathBuf};
use std::time::Instant;

use crate::diag;


/// The data root, created and validated before the lock is taken. A
/// daemon meeting a data root it must not trust stops rather than writes
/// into it: the root itself is 0700 and owner-only, a planted symlink or a
/// root owned by someone else fails closed. Intermediate directories above
/// the root are created with the user's umask; the root itself never is.
fn prepare_root(root: &Path) -> io::Result<()> {
    use std::os::unix::fs::{DirBuilderExt, MetadataExt, PermissionsExt};
    // SAFETY: geteuid cannot fail.
    let euid = unsafe { libc::geteuid() };
    let created = match std::fs::symlink_metadata(root) {
        Ok(meta) => {
            if meta.file_type().is_symlink() {
                return Err(io::Error::other(format!("the data root {} is a symlink; refusing to use it", root.display())));
            }
            if !meta.is_dir() {
                return Err(io::Error::other(format!("the data root {} is not a directory", root.display())));
            }
            if meta.uid() != euid {
                return Err(io::Error::other(format!("the data root {} is owned by uid {}; refusing to use it", root.display(), meta.uid())));
            }
            false
        }
        Err(e) if e.kind() == io::ErrorKind::NotFound => {
            // The root itself is ours from the start: private.
            std::fs::DirBuilder::new().mode(0o700).recursive(true).create(root)?;
            true
        }
        Err(e) => return Err(e),
    };
    let meta = std::fs::metadata(root)?;
    if created || meta.permissions().mode() & 0o077 != 0 {
        // Ours and too open, or freshly created under a loose umask.
        std::fs::set_permissions(root, std::fs::Permissions::from_mode(0o700))?;
    }
    Ok(())
}

/// One engine per data root: an `flock(2)` on `<root>/.lock`, held for the
/// daemon's life. Without it two engines on the same root interleave blob
/// and image writes and both silently corrupt the store.
fn root_lock(root: &Path) -> io::Result<OwnedFd> {
    use std::os::unix::fs::OpenOptionsExt;
    let file = std::fs::OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(false)
        .custom_flags(libc::O_NOFOLLOW)
        .mode(0o600)
        .open(root.join(".lock"))?;
    // SAFETY: flock on a descriptor this function owns; the lock dies with it.
    let ret = unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) };
    if ret != 0 {
        return Err(io::Error::new(io::ErrorKind::AddrInUse, format!("the data root {} is in use by another engine", root.display())));
    }
    Ok(OwnedFd::from(file))
}

/// `~/.kiri`: the daemon's state. Always under HOME: `KIRI_SOCKET` may point the
/// socket anywhere, but it must not move private state into a directory another user can prepare.
pub fn state_dir() -> io::Result<PathBuf> {
    let home = std::env::var_os("HOME").map(PathBuf::from).ok_or_else(|| io::Error::other("HOME is not set"))?;
    Ok(home.join(".kiri"))
}

/// `~/.kiri/run/docker.sock`, beside OrbStack's `~/.orbstack/run/docker.sock`.
pub fn socket_path() -> io::Result<PathBuf> {
    if let Some(s) = std::env::var_os("KIRI_SOCKET") {
        return Ok(PathBuf::from(s));
    }
    let home = std::env::var_os("HOME").map(PathBuf::from).ok_or_else(|| io::Error::other("HOME is not set"))?;
    Ok(home.join(".kiri").join("run/docker.sock"))
}

/// Raises the soft open-file limit to the hard one, as Go does for dockerd.
/// launchd starts the daemon with 256, and each relayed connection holds
/// four or five descriptors: a LAN client opening ~60 connections to a
/// published port ran it out, and the daemon fell over with its VM.
fn raise_open_files() {
    // SAFETY: rlimit is plain data; get/setrlimit read and write it.
    unsafe {
        let mut lim: libc::rlimit = std::mem::zeroed();
        if libc::getrlimit(libc::RLIMIT_NOFILE, &mut lim) != 0 {
            return;
        }
        // macOS refuses more than OPEN_MAX for the soft limit.
        let want = if cfg!(target_os = "macos") { lim.rlim_max.min(10240) } else { lim.rlim_max };
        if lim.rlim_cur < want {
            lim.rlim_cur = want;
            libc::setrlimit(libc::RLIMIT_NOFILE, &lim);
        }
    }
}

pub fn run(_args: &[String]) -> io::Result<()> {
    let t0 = Instant::now();
    raise_open_files();
    // SIGINT/SIGTERM shut down cleanly: power the guest off, remove the socket.
    // Blocked before anything else starts a thread, so every thread inherits
    // it and one thread waits for them. A thread started before this (the
    // socket group's watcher, on a Linux host) took the signal instead, and
    // the daemon died without a shutdown: the agent was killed with its
    // bridges and nftables table still in place.
    // The VM-crash test hook exists only when the daemon is started with
    // KIRI_TEST_VM_CRASH=1; production engines never handle the signal.
    let vm_crash_hook = std::env::var_os("KIRI_TEST_VM_CRASH").is_some();
    // SAFETY: plain signal-mask calls on a local set.
    let set = unsafe {
        let mut set: libc::sigset_t = std::mem::zeroed();
        libc::sigemptyset(&mut set);
        libc::sigaddset(&mut set, libc::SIGINT);
        libc::sigaddset(&mut set, libc::SIGTERM);
        if vm_crash_hook {
            libc::sigaddset(&mut set, libc::SIGUSR2);
        }
        libc::pthread_sigmask(libc::SIG_BLOCK, &set, std::ptr::null_mut());
        set
    };
    let socket = socket_path()?;
    if UnixStream::connect(&socket).is_ok() {
        // Not an error: launchd (KeepAlive on failure) must not retry it.
        diag::info!("engine already running", socket = socket.display());
        return Ok(());
    }
    if let Some(dir) = socket.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let _ = std::fs::remove_file(&socket); // stale, from a daemon that died
    let listener = UnixListener::bind(&socket)?;
    std::fs::set_permissions(&socket, std::fs::Permissions::from_mode(0o600))?;
    // On a Linux host the daemon runs as root; `KIRI_SOCKET_GROUP=kiri`
    // lets that group's users in, as the docker group does for dockerd.
    let access_group = std::env::var_os("KIRI_SOCKET_GROUP");
    if let Some(group) = &access_group {
        socket_group(&socket, group)?;
    }
    // Each member by name too, so one just added needn't sign in again; and
    // connections are checked against the group when made and while open, so
    // a member removed is let go at once, whatever the list still says.
    #[cfg(target_os = "linux")]
    let gate = match &access_group {
        Some(group) => {
            let gate = access::Gate::new(&socket, group)?;
            match gate.grant() {
                Ok(n) => diag::info!("socket access list written", members = n),
                Err(e) => diag::warn!("socket access list not written: new members sign in again first", error = e),
            }
            gate.clone().watch()?;
            Some(gate)
        }
        None => None,
    };

    let root = kiri_image::Store::default_root()?;
    prepare_root(&root)?;
    let _root_lock = root_lock(&root)?;
    let store = kiri_image::Store::open(root)?;
    let engine = engine::Engine::boot(store).inspect_err(|e| diag::error!("engine did not start", error = e))?;
    diag::info!("engine ready", version = env!("CARGO_PKG_VERSION"), ms = t0.elapsed().as_millis(), socket = format!("unix://{}", socket.display()));
    // The pidfile is the fallback handle for `kiri engine stop` when the
    // socket is wedged; it exists only once the engine is actually up.
    {
        use std::os::unix::fs::PermissionsExt;
        let pidfile = crate::config::pidfile(&socket);
        let now = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
        if let Err(e) = std::fs::write(&pidfile, format!("{} {now}\n", std::process::id())).and_then(|()| std::fs::set_permissions(&pidfile, std::fs::Permissions::from_mode(0o600))) {
            diag::warn!("pidfile not written", error = e);
        }
    }
    kiri_image::set_proxy_source(proxy::for_registry);
    // The managed BuildKit stops itself when builds have been idle a while.
    builder::watch(engine.clone());
    let on_signal = engine.clone();
    let sock = socket.clone();
    std::thread::Builder::new().name("kiri-signals".into()).spawn(move || loop {
        let mut sig = 0;
        // SAFETY: waits on the blocked set; writes the signal number to `sig`.
        unsafe { libc::sigwait(&set, &mut sig) };
        if sig == libc::SIGUSR2 {
            diag::warn!("test hook: crashing the VM");
            on_signal.crash_vm_for_test();
            continue;
        }
        diag::info!("engine shutting down", signal = sig);
        let _ = std::fs::remove_file(&sock);
        let _ = std::fs::remove_file(crate::config::pidfile(&sock));
        on_signal.shutdown();
        // Give the guest a moment to power off before the VM is released.
        std::thread::sleep(std::time::Duration::from_millis(50));
        std::process::exit(0);
    })?;

    for conn in listener.incoming() {
        let Ok(conn) = conn else { continue };
        let engine = engine.clone();
        #[cfg(target_os = "linux")]
        let gate = gate.clone();
        let spawned = std::thread::Builder::new().name("kiri-api".into()).spawn(move || {
            // Checked here, not in the accept loop: a slow user lookup holds up
            // this connection only.
            #[cfg(target_os = "linux")]
            let _seat = match &gate {
                Some(gate) => match gate.admit(&conn) {
                    Some(seat) => Some(seat),
                    None => return,
                },
                None => None,
            };
            #[cfg(feature = "h12tiny")]
            {
                if h12tiny::wants_incumbent(&conn) {
                    let _ = api::serve(conn, engine);
                } else {
                    let _ = h12tiny::serve_conn(conn, engine);
                }
                return;
            }
            #[cfg(not(feature = "h12tiny"))]
            let _ = api::serve(conn, engine);
        });
        if let Err(e) = spawned {
            diag::error!("cannot start a connection thread", error = e);
        }
    }
    Ok(())
}

/// Gives `group` read-write access to the socket.
fn socket_group(socket: &std::path::Path, group: &std::ffi::OsStr) -> io::Result<()> {
    let name = std::ffi::CString::new(std::os::unix::ffi::OsStrExt::as_bytes(group)).map_err(|_| io::Error::from(io::ErrorKind::InvalidInput))?;
    // SAFETY: getgrnam with a valid C string; the result is read at once.
    let gid = unsafe {
        let g = libc::getgrnam(name.as_ptr());
        if g.is_null() {
            return Err(io::Error::new(io::ErrorKind::NotFound, format!("no group {}", group.to_string_lossy())));
        }
        (*g).gr_gid
    };
    std::os::unix::fs::chown(socket, None, Some(gid))?;
    std::fs::set_permissions(socket, std::fs::Permissions::from_mode(0o660))
}

#[cfg(test)]
mod tests {
    use super::{prepare_root, root_lock};
    use std::os::unix::fs::PermissionsExt;

    fn scratch(name: &str) -> std::path::PathBuf {
        let dir = std::env::temp_dir().join(format!("ctrs-root-test-{}-{name}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn creates_a_missing_root_private_and_lockable() {
        let parent = scratch("fresh");
        let root = parent.join("data");
        assert!(!root.exists());
        prepare_root(&root).unwrap();
        let mode = std::fs::metadata(&root).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode, 0o700);
        let lock = root_lock(&root).unwrap();
        drop(lock);
        let _ = std::fs::remove_dir_all(&parent);
    }

    #[test]
    fn the_second_lock_is_refused() {
        let parent = scratch("held");
        let root = parent.join("data");
        prepare_root(&root).unwrap();
        let first = root_lock(&root).unwrap();
        let err = root_lock(&root).unwrap_err();
        assert_eq!(err.kind(), std::io::ErrorKind::AddrInUse);
        drop(first);
        root_lock(&root).unwrap();
        let _ = std::fs::remove_dir_all(&parent);
    }

    #[test]
    fn refuses_a_planted_symlink() {
        let parent = scratch("link");
        let elsewhere = scratch("link-elsewhere");
        let root = parent.join("data");
        std::os::unix::fs::symlink(&elsewhere, &root).unwrap();
        let err = prepare_root(&root).unwrap_err();
        assert!(err.to_string().contains("symlink"));
        let _ = std::fs::remove_dir_all(&parent);
        let _ = std::fs::remove_dir_all(&elsewhere);
    }

    #[test]
    fn refuses_a_root_that_is_a_file() {
        let parent = scratch("file");
        let root = parent.join("data");
        std::fs::write(&root, b"not a directory").unwrap();
        let err = prepare_root(&root).unwrap_err();
        assert!(err.to_string().contains("not a directory"));
        let _ = std::fs::remove_dir_all(&parent);
    }

    #[test]
    fn tightens_an_open_root_and_keeps_the_lock_private() {
        use std::os::unix::fs::PermissionsExt;
        let parent = scratch("loose");
        let root = parent.join("data");
        std::fs::create_dir_all(&root).unwrap();
        std::fs::set_permissions(&root, std::fs::Permissions::from_mode(0o755)).unwrap();
        prepare_root(&root).unwrap();
        let mode = std::fs::metadata(&root).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode, 0o700);
        let _ = root_lock(&root).unwrap();
        let mode = std::fs::metadata(root.join(".lock")).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode, 0o600);
        let _ = std::fs::remove_dir_all(&parent);
    }
}
