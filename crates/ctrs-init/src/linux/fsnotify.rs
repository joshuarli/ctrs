//! Mac-side changes under bind mounts, from the host's FSEvents stream, are
//! raised as inotify events through the guest kernel's `/proc/ctrs/fsnotify`.
//! A forked writer does the writes, since each one walks a virtiofs path:
//! the agent stays single-threaded (musl's set*id in raw-clone'd container
//! children fails when the parent has other threads) and its loop never
//! waits on the share. Lines a full pipe refuses wait in a bounded queue
//! that the agent loop retries; past the bound they collapse into one
//! rescan of the share, so a loss is never silent.

use std::cell::{Cell, RefCell};
use std::collections::VecDeque;
use std::io::{self, BufRead, Write};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::fs::OpenOptionsExt;

const PROC_FILE: &str = "/proc/ctrs/fsnotify";
const RESCAN_SHARE: &[u8] = b"s /mnt/mac\n";
const MAX_PENDING: usize = 8192;
const PIPE_BYTES: libc::c_int = 1 << 20;

pub struct Fsnotify {
    pipe: Option<OwnedFd>,
    queue: RefCell<Queue>,
    lost: Cell<u64>,
}

/// Lines waiting for room in the pipe, and whether some were dropped.
#[derive(Default)]
struct Queue {
    lines: VecDeque<Vec<u8>>,
    rescan: bool,
}

impl Queue {
    fn push(&mut self, line: Vec<u8>) -> bool {
        if self.rescan {
            return false;
        }
        if line.len() > libc::PIPE_BUF || self.lines.len() >= MAX_PENDING {
            self.lines.clear();
            self.rescan = true;
            return false;
        }
        self.lines.push_back(line);
        true
    }

    /// Writes what fits; `write` answers like write(2) on a non-blocking
    /// pipe. Returns false when the pipe is gone.
    fn flush(&mut self, mut write: impl FnMut(&[u8]) -> io::Result<()>) -> bool {
        if self.rescan {
            match write(RESCAN_SHARE) {
                Ok(()) => self.rescan = false,
                Err(e) if e.kind() == io::ErrorKind::WouldBlock => return true,
                Err(_) => return false,
            }
        }
        while let Some(line) = self.lines.front() {
            match write(line) {
                Ok(()) => {
                    self.lines.pop_front();
                }
                Err(e) if e.kind() == io::ErrorKind::WouldBlock => return true,
                Err(_) => return false,
            }
        }
        true
    }

    fn waiting(&self) -> bool {
        self.rescan || !self.lines.is_empty()
    }
}

pub fn start() -> Fsnotify {
    let mut fds = [0; 2];
    // SAFETY: `fds` has room for the two descriptors pipe2 writes.
    if unsafe { libc::pipe2(fds.as_mut_ptr(), libc::O_CLOEXEC) } != 0 {
        eprintln!("ctrs-init: no fsnotify pipe: {}", io::Error::last_os_error());
        return Fsnotify { pipe: None, queue: RefCell::default(), lost: Cell::new(0) };
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
            Fsnotify { pipe: None, queue: RefCell::default(), lost: Cell::new(0) }
        }
        _ => {
            drop(read);
            // SAFETY: making a descriptor we own non-blocking.
            unsafe { libc::fcntl(write.as_raw_fd(), libc::F_SETFL, libc::O_NONBLOCK) };
            // SAFETY: plain fcntl on our pipe; a smaller pipe only queues sooner.
            unsafe { libc::fcntl(write.as_raw_fd(), libc::F_SETPIPE_SZ, PIPE_BYTES) };
            Fsnotify { pipe: Some(write), queue: RefCell::default(), lost: Cell::new(0) }
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
        if self.pipe.is_none() {
            return;
        }
        let mut queue = self.queue.borrow_mut();
        for event in events.iter() {
            let mut line = Vec::with_capacity(event.path.len() + 12);
            line.extend_from_slice(&[event.kind as u8, b' ']);
            line.extend_from_slice(b"/mnt/mac");
            line.extend_from_slice(event.path.as_bytes());
            line.push(b'\n');
            if !queue.push(line) {
                self.lost.set(self.lost.get() + 1);
            }
        }
        drop(queue);
        self.flush();
    }

    /// Writes queued lines the pipe has room for; the agent loop calls it
    /// every turn, and sooner while `waiting`.
    pub fn flush(&self) {
        let Some(pipe) = &self.pipe else { return };
        let mut queue = self.queue.borrow_mut();
        if !queue.waiting() {
            return;
        }
        let lost = self.lost.replace(0);
        if lost > 0 {
            eprintln!("ctrs-init: {lost} host change events did not fit; the share is rescanned");
        }
        let alive = queue.flush(|line| {
            // SAFETY: writing a buffer we own; a line under PIPE_BUF is written whole or not at all.
            if unsafe { libc::write(pipe.as_raw_fd(), line.as_ptr().cast(), line.len()) } < 0 { Err(io::Error::last_os_error()) } else { Ok(()) }
        });
        if !alive {
            *queue = Queue::default();
        }
    }

    pub fn waiting(&self) -> bool {
        self.queue.borrow().waiting()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn line(n: usize) -> Vec<u8> {
        format!("m /mnt/mac/f{n}\n").into_bytes()
    }

    #[test]
    fn a_full_pipe_keeps_lines_in_order() {
        let mut q = Queue::default();
        for n in 0..3 {
            assert!(q.push(line(n)));
        }
        let mut written = Vec::new();
        let mut room = 2;
        assert!(q.flush(|l| if room == 0 { Err(io::ErrorKind::WouldBlock.into()) } else { room -= 1; written.push(l.to_vec()); Ok(()) }));
        assert!(q.waiting());
        assert!(q.flush(|l| { written.push(l.to_vec()); Ok(()) }));
        assert_eq!(written, vec![line(0), line(1), line(2)]);
        assert!(!q.waiting());
    }

    #[test]
    fn overflow_collapses_into_one_rescan_before_later_lines() {
        let mut q = Queue::default();
        for n in 0..MAX_PENDING {
            assert!(q.push(line(n)));
        }
        assert!(!q.push(line(MAX_PENDING)));
        assert!(!q.push(line(0)));
        let mut written = Vec::new();
        assert!(q.flush(|l| { written.push(l.to_vec()); Ok(()) }));
        assert_eq!(written, vec![RESCAN_SHARE.to_vec()]);
        assert!(q.push(line(1)));
        assert!(q.flush(|l| { written.push(l.to_vec()); Ok(()) }));
        assert_eq!(written.last(), Some(&line(1)));
    }

    #[test]
    fn an_oversized_line_is_a_rescan_and_a_dead_pipe_reports() {
        let mut q = Queue::default();
        assert!(!q.push(vec![b'x'; libc::PIPE_BUF + 1]));
        assert!(!q.flush(|_| Err(io::ErrorKind::BrokenPipe.into())));
    }
}
