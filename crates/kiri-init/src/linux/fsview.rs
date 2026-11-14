//! Path resolution inside running containers' filesystems: every path is
//! resolved with openat2(RESOLVE_IN_ROOT), so the container's root is `/`
//! even for symlinks inside it, and nothing outside the container is
//! reachable from `docker cp`.

use std::ffi::CString;
use std::io;
use std::os::fd::{FromRawFd, OwnedFd, RawFd};

use super::sys;

const RESOLVE_NO_MAGICLINKS: u64 = 0x02;
const RESOLVE_IN_ROOT: u64 = 0x10;

#[repr(C)]
struct OpenHow {
    flags: u64,
    mode: u64,
    resolve: u64,
}

/// Opens `path` under `root`, every symlink resolved inside `root`.
pub(super) fn open_in(root: RawFd, path: &str, flags: i32) -> io::Result<OwnedFd> {
    let rel = path.trim_start_matches('/');
    let c = CString::new(if rel.is_empty() { "." } else { rel }).map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "path contains a NUL byte"))?;
    let how = OpenHow { flags: (flags | libc::O_CLOEXEC) as u64, mode: 0, resolve: RESOLVE_IN_ROOT | RESOLVE_NO_MAGICLINKS };
    // SAFETY: openat2 with a valid dirfd, path and open_how of the stated size.
    let fd = unsafe { libc::syscall(libc::SYS_openat2, root, c.as_ptr(), &how as *const OpenHow, std::mem::size_of::<OpenHow>()) };
    sys::check(fd, "open")?;
    // SAFETY: openat2 returned a fresh descriptor.
    Ok(unsafe { OwnedFd::from_raw_fd(fd as RawFd) })
}
