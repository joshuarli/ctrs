//! Mac-side changes under bind mounts, from the host's FSEvents stream, are
//! raised as inotify events through the guest kernel's `/proc/ctrs/fsnotify`.
//! A forked writer does the writes, since each one walks a virtiofs path:
//! the agent stays single-threaded (musl's set*id in raw-clone'd container
//! children fails when the parent has other threads) and its loop never
//! waits on the share. A full pipe drops events, as a full inotify queue does.

use std::io::{self, BufRead, Write};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::fs::OpenOptionsExt;

const PROC_FILE: &str = "/proc/ctrs/fsnotify";

pub struct Fsnotify {
    pipe: Option<OwnedFd>,
}

pub fn start() -> Fsnotify {
    let mut fds = [0; 2];
    // SAFETY: `fds` has room for the two descriptors pipe2 writes.
    if unsafe { libc::pipe2(fds.as_mut_ptr(), libc::O_CLOEXEC) } != 0 {
        eprintln!("ctrs-init: no fsnotify pipe: {}", io::Error::last_os_error());
        return Fsnotify { pipe: None };
    }
    // SAFETY: pipe2 succeeded, so both descriptors are fresh and ours.
    let (read, write) = unsafe { (OwnedFd::from_raw_fd(fds[0]), OwnedFd::from_raw_fd(fds[1])) };
    // SAFETY: the agent is single-threaded here, so the child may run Rust code.
    match unsafe { libc::fork() } {
        0 => {
            drop(write);
            // SAFETY: plain prctl; the writer must not outlive the agent.
            unsafe { libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) };
            write_events(read);
            // SAFETY: leaving the forked child without running the agent's destructors.
            unsafe { libc::_exit(0) }
        }
        pid if pid < 0 => {
            eprintln!("ctrs-init: no fsnotify writer: {}", io::Error::last_os_error());
            Fsnotify { pipe: None }
        }
        _ => {
            drop(read);
            // SAFETY: making a descriptor we own non-blocking.
            unsafe { libc::fcntl(write.as_raw_fd(), libc::F_SETFL, libc::O_NONBLOCK) };
            Fsnotify { pipe: Some(write) }
        }
    }
}

fn write_events(read: OwnedFd) {
    let proc_file = match std::fs::OpenOptions::new().write(true).custom_flags(libc::O_CLOEXEC).open(PROC_FILE) {
        Ok(f) => Some(f),
        Err(e) => {
            eprintln!("ctrs-init: cannot open {PROC_FILE}: {e}");
            None
        }
    };
    let mut lines = io::BufReader::new(std::fs::File::from(read));
    let mut line = Vec::new();
    let mut logged = false;
    loop {
        line.clear();
        match lines.read_until(b'\n', &mut line) {
            Ok(0) | Err(_) => return,
            Ok(_) => {}
        }
        let Some(mut f) = proc_file.as_ref() else { continue };
        match f.write(&line) {
            Ok(_) => {}
            Err(e) if e.raw_os_error() == Some(libc::ENOENT) => {}
            Err(e) if !logged => {
                eprintln!("ctrs-init: {PROC_FILE} write failed: {e}");
                logged = true;
            }
            Err(_) => {}
        }
    }
}

impl Fsnotify {
    pub fn send(&self, events: ctrs_proto::FsEvents<'_>) {
        let Some(pipe) = &self.pipe else { return };
        let mut line = Vec::with_capacity(256);
        for event in events.iter() {
            line.clear();
            line.extend_from_slice(&[event.kind as u8, b' ']);
            line.extend_from_slice(b"/mnt/mac");
            line.extend_from_slice(event.path.as_bytes());
            line.push(b'\n');
            if line.len() > libc::PIPE_BUF {
                continue;
            }
            // SAFETY: writing a buffer we own; a line under PIPE_BUF is written whole or not at all.
            if unsafe { libc::write(pipe.as_raw_fd(), line.as_ptr().cast(), line.len()) } < 0 {
                return;
            }
        }
    }
}
