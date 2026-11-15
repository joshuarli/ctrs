//! The agent's event loop: one poll over the host connection, a signalfd for
//! child exits, and every process's output (and pending input) descriptors.
//! Single-threaded, which is also what lets clone3 copy the process safely.

use std::collections::{HashMap, VecDeque};
use std::fs::File;
use std::io::{self, Read, Write};
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};
use std::path::Path;

use ctrs_proto::{Exited, LayerStored, MAX_OUTPUT_CHUNK, Msg, Stats, Stream};

use super::container::{self, NetCtx, Paths, Process};
use super::net::{self, Bridges, Dhcp};
use super::{layers, meminfo, sys};

/// Input held for a process that is not reading yet. The host sends at most
/// `INPUT_WINDOW` bytes beyond what `InputConsumed` acknowledged, so a
/// correct host never gets here; a broken one has the process's stdin closed
/// rather than the agent holding unbounded memory.
const MAX_PENDING_INPUT: usize = 2 * ctrs_proto::INPUT_WINDOW;

struct Proc {
    run: Process,
    received_ns: u64,
    cloned_ns: u64,
    /// Set once reaped: (exit code, when).
    exited: Option<(i32, u64)>,
    input: VecDeque<u8>,
    close_stdin_when_drained: bool,
    /// When a running TTY process last had its terminal hung up: no one
    /// held the pty open, as while systemd reopens /dev/console. Kept, and
    /// looked at again shortly, rather than taken for the end of output.
    tty_hup: Option<std::time::Instant>,
    /// This exec's dedicated output connection to the host, when it
    /// dialed back at start. Its `Output` and `Exited` frames bypass the
    /// multiplexed control connection, which is the bulk-stream ceiling.
    bulk: Option<BulkConn>,
}

/// A per-exec vsock connection carrying this process's `Output` and
/// `Exited` frames. Writes are nonblocking with a bounded pending buffer;
/// POLLOUT drains it. `closing` means the exit report is already queued,
/// so the process stays until the last byte is on the wire.
struct BulkConn {
    fd: OwnedFd,
    pending: Vec<u8>,
    pos: usize,
    closing: bool,
}

/// Output queued for a bulk connection beyond this stops the process's
/// pipes being read, the same backpressure the control connection gets
/// from a full socket buffer.
const BULK_HIGH: usize = 8 << 20;

impl BulkConn {
    fn drained(&self) -> bool {
        self.pos == self.pending.len()
    }
}

/// Sends what it can of `pending` without blocking.
fn bulk_flush(b: &mut BulkConn) -> io::Result<()> {
    while b.pos < b.pending.len() {
        // SAFETY: `send` on a descriptor and buffer we own.
        let n = unsafe {
            libc::send(
                b.fd.as_raw_fd(),
                b.pending[b.pos..].as_ptr().cast(),
                b.pending.len() - b.pos,
                libc::MSG_DONTWAIT,
            )
        };
        if n > 0 {
            b.pos += n as usize;
        } else if n == 0 {
            break;
        } else {
            let e = io::Error::last_os_error();
            if e.raw_os_error() == Some(libc::EAGAIN) {
                break;
            }
            return Err(e);
        }
    }
    if b.drained() {
        b.pending.clear();
        b.pos = 0;
    }
    Ok(())
}

/// Dials the host's exec port and introduces this process. The first
/// frame is `u32 BE len | id`, then `Output`/`Exited` frames follow in
/// order. `None` on any failure: the process simply keeps reporting on
/// the control connection.
fn bulk_connect(id: &str) -> Option<BulkConn> {
    let fd = super::transport::dial_within(ctrs_proto::EXEC_PORT, std::time::Duration::from_millis(500)).ok()?;
    let mut hs = Vec::with_capacity(4 + id.len());
    hs.extend_from_slice(&(id.len() as u32).to_be_bytes());
    hs.extend_from_slice(id.as_bytes());
    // The fresh connection is still blocking; the handshake is tiny and
    // the host reads it at once. Nonblocking starts with the data path.
    let mut file = File::from(fd.try_clone().ok()?);
    file.write_all(&hs).ok()?;
    sys::set_nonblocking(fd.as_raw_fd()).ok()?;
    Some(BulkConn { fd, pending: Vec::new(), pos: 0, closing: false })
}

/// How long a hung-up terminal waits before it's polled again.
const TTY_HUP_WAIT: std::time::Duration = std::time::Duration::from_millis(100);

/// One reply slot in `outbox`, in the order the host sent the requests.
/// `AwaitJob` is a `LayerBegin` whose `LayerStored`/`Error` the install
/// worker still owes; everything behind it waits so replies stay FIFO.
enum OutItem {
    Ready(Vec<u8>),
    AwaitJob { seq: u64 },
}

/// Writes the ready prefix of `outbox` to the host connection. An
/// `AwaitJob` at the front is ready once the worker's done for its seq is
/// the next completed install (installs finish in request order).
fn drain_outbox(
    conn: &mut File,
    out: &mut Vec<u8>,
    outbox: &mut VecDeque<OutItem>,
    done_jobs: &mut VecDeque<layers::InstallDone>,
) -> io::Result<()> {
    loop {
        match outbox.front() {
            Some(OutItem::Ready(_)) => {}
            Some(OutItem::AwaitJob { seq }) => match done_jobs.front() {
                Some(d) if d.seq == *seq => {}
                _ => break,
            },
            None => break,
        }
        match outbox.pop_front().expect("front checked above") {
            OutItem::Ready(bytes) => conn.write_all(&bytes)?,
            OutItem::AwaitJob { .. } => {
                let done = done_jobs.pop_front().expect("matched above");
                out.clear();
                match &done.result {
                    Ok(unpacked) => Msg::LayerStored(LayerStored {
                        unpacked_bytes: *unpacked,
                        elapsed_ns: done.started.elapsed().as_nanos() as u64,
                    })
                    .encode(out),
                    Err(e) => Msg::Error(&format!("unpack {}: {e}", done.digest)).encode(out),
                }
                conn.write_all(out)?;
            }
        }
    }
    Ok(())
}

/// The one install child allowed at a time: its job, the read end of its
/// result pipe and whatever record bytes have arrived so far.
struct InstallWait {
    job: layers::InstallJob,
    read: OwnedFd,
    pid: libc::pid_t,
    buf: Vec<u8>,
}

/// Forks the child that unpacks and installs `job`'s staged blob. The child
/// keeps only its result pipe, like the `docker cp` children, so it cannot
/// hold the agent's connection or a container's pipes open.
fn start_install(root: &Path, job: &layers::InstallJob) -> io::Result<(OwnedFd, libc::pid_t)> {
    let mut fds = [0; 2];
    sys::check(unsafe { libc::pipe2(fds.as_mut_ptr(), libc::O_CLOEXEC | libc::O_NONBLOCK) } as _, "pipe")?;
    // SAFETY: pipe2 just opened both; each side is owned immediately.
    let (read, write) = unsafe { (OwnedFd::from_raw_fd(fds[0]), OwnedFd::from_raw_fd(fds[1])) };
    let result_fd = write.as_raw_fd();
    // SAFETY: the agent is single-threaded, so the child is a consistent
    // copy. It touches only the layer store, writes one record, exits.
    let pid = unsafe { libc::fork() };
    if pid == 0 {
        install_child(root, job, result_fd);
    }
    if pid < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok((read, pid))
}

/// Runs in the forked install child and never returns: every descriptor but
/// stdio and the result pipe is closed, the staged blob is installed, one
/// result record (`tag | u64 len | payload`) is written, then _exit.
fn install_child(root: &Path, job: &layers::InstallJob, result_fd: RawFd) -> ! {
    // SAFETY: closing descriptor ranges in this child only.
    unsafe {
        if result_fd > 3 {
            libc::syscall(libc::SYS_close_range, 3, (result_fd - 1) as libc::c_uint, 0);
        }
        libc::syscall(libc::SYS_close_range, (result_fd + 1) as libc::c_uint, libc::c_uint::MAX, 0);
    }
    let mut rec = Vec::with_capacity(24);
    match layers::finish_job(root, job) {
        Ok(unpacked) => {
            rec.push(b'O');
            rec.extend_from_slice(&8u64.to_le_bytes());
            rec.extend_from_slice(&unpacked.to_le_bytes());
        }
        Err(e) => {
            let msg = e.to_string();
            rec.push(b'E');
            rec.extend_from_slice(&(msg.len() as u64).to_le_bytes());
            rec.extend_from_slice(msg.as_bytes());
        }
    }
    // SAFETY: writing a record we built to a descriptor we own.
    unsafe { libc::write(result_fd, rec.as_ptr().cast(), rec.len()) };
    // SAFETY: leaving the child without running the parent's destructors.
    unsafe { libc::_exit(0) }
}

/// Starts forked installs while none runs and jobs wait. A fork or pipe
/// failure fails only that job: installs are an optimization of ordering,
/// not a reason to wedge every later reply.
fn pump_installs(
    root: &Path,
    queue: &mut VecDeque<layers::InstallJob>,
    wait: &mut Option<InstallWait>,
    done: &mut VecDeque<layers::InstallDone>,
) {
    while wait.is_none() {
        let Some(job) = queue.pop_front() else { return };
        match start_install(root, &job) {
            Ok((read, pid)) => *wait = Some(InstallWait { job, read, pid, buf: Vec::new() }),
            Err(e) => done.push_back(layers::InstallDone {
                seq: job.seq,
                digest: job.digest,
                started: job.started,
                result: Err(e),
            }),
        }
    }
}

/// Takes one complete result record off `buf`, if one has arrived.
fn take_install_record(buf: &mut Vec<u8>) -> Option<io::Result<u64>> {
    if buf.len() < 9 {
        return None;
    }
    let tag = buf[0];
    let len = u64::from_le_bytes(buf[1..9].try_into().expect("9 checked")) as usize;
    if buf.len() < 9 + len {
        return None;
    }
    let payload = &buf[9..9 + len];
    let result = match tag {
        b'O' if len == 8 => Ok(u64::from_le_bytes(payload.try_into().expect("len checked"))),
        b'E' => Err(io::Error::new(io::ErrorKind::InvalidData, String::from_utf8_lossy(payload).into_owned())),
        _ => Err(io::Error::new(io::ErrorKind::InvalidData, "bad install record")),
    };
    buf.drain(..9 + len);
    Some(result)
}

pub fn serve(mut conn: File, paths: &Paths) -> io::Result<()> {
    let sigfd = child_signals()?;
    // In the VM a DHCP lease gives the uplink and DNS; on a Linux host the
    // host has them already.
    let host_process = super::transport::is_host_process();
    // The published ports the kernel forwards, by container (on a Linux
    // host; in the VM, TCP ones reached over the NAT network).
    let mut published: Vec<(String, super::netlink::Dnat)> = Vec::new();
    let host_dns = if host_process { super::transport::host_dns() } else { Vec::new() };
    let mut dhcp: Option<Dhcp> = if host_process {
        if let Err(e) = net::host_uplink() {
            eprintln!("ctrs-init: no uplink: {e}");
        }
        None
    } else {
        match net::uplink() {
            Ok(d) => d,
            Err(e) => {
                eprintln!("ctrs-init: no uplink: {e}");
                None
            }
        }
    };
    // On a Linux host, SIGTERM or SIGINT stops the agent as Shutdown does.
    let term = if host_process { Some(term_signals()?) } else { None };
    let mut bridges = Bridges::default();
    // In the VM, lookups the gateway's resolver fails go through the host.
    let mut dns = super::dns::Dns::default();
    dns.relay = !host_process;
    let forward = super::relay::listen()?;
    // host.docker.internal's relay to the Mac (VM only). A Linux host maps
    // that name to the bridge gateway and redirects nothing here, so the
    // listener would only be a port open to the LAN and a clash with any
    // host service on it.
    let host_bound = if host_process { None } else { Some(super::relay::listen_host_bound(net::HOST_RELAY_PORT)?) };
    let framed = super::relay::listen_framed()?;
    let ssh_agent = super::relay::listen_ssh_agent()?;
    // The engine's API for containers that mount the docker socket (VM only).
    let engine_api = if host_process {
        None
    } else {
        super::relay::listen_engine().inspect_err(|e| eprintln!("ctrs-init: no engine socket for containers: {e}")).ok()
    };
    let copies = super::copy::listen()?;
    let udp = super::relay::listen_udp()?;
    let pressure = memory_pressure_trigger();
    let mut last_pressure = std::time::Instant::now() - std::time::Duration::from_secs(1);
    // `docker system df`: measured on a thread, which wakes the loop through
    // this pipe; the loop sends the `Usage` lines (it is the only writer).
    let (usage_wake, usage_ring) = usage_pipe()?;
    let usage_ring = std::sync::Arc::new(usage_ring);
    let (usage_tx, usage_rx) = std::sync::mpsc::channel::<Vec<String>>();
    let mut measuring = false;
    // Bulk layer installs run in forked children so decompression,
    // extraction and the filesystem flush never stall the event loop. A
    // child, not a thread: clone3 copies this process for container setup
    // and needs it single-threaded. Installs stay serialized, so the
    // layer store sees the same one-at-a-time order as before. Replies
    // still reach the host in request order through `outbox`.
    let mut install_seq = 0u64;
    let mut install_queue: VecDeque<layers::InstallJob> = VecDeque::new();
    let mut install_wait: Option<InstallWait> = None;
    let mut outbox: VecDeque<OutItem> = VecDeque::new();
    let mut done_jobs: VecDeque<layers::InstallDone> = VecDeque::new();
    let mut relays: Vec<super::relay::Relay> = Vec::new();
    let mut procs: HashMap<libc::pid_t, Proc> = HashMap::new();
    let mut fds: Vec<libc::pollfd> = Vec::with_capacity(16);
    let mut frame = Vec::with_capacity(4096);
    let mut out = Vec::with_capacity(4096);
    let mut chunk = vec![0u8; MAX_OUTPUT_CHUNK];

    loop {
        fds.clear();
        fds.push(libc::pollfd { fd: conn.as_raw_fd(), events: libc::POLLIN, revents: 0 });
        fds.push(libc::pollfd { fd: sigfd.as_raw_fd(), events: libc::POLLIN, revents: 0 });
        // Always present (fd -1 is ignored by poll), so process fds start at 3.
        fds.push(libc::pollfd { fd: dhcp.as_ref().map_or(-1, Dhcp::fd), events: libc::POLLIN, revents: 0 });
        for fd in dns.fds() {
            fds.push(libc::pollfd { fd, events: libc::POLLIN, revents: 0 });
        }
        fds.push(libc::pollfd { fd: forward.as_raw_fd(), events: libc::POLLIN, revents: 0 });
        fds.push(libc::pollfd { fd: framed.as_raw_fd(), events: libc::POLLIN, revents: 0 });
        fds.push(libc::pollfd { fd: host_bound.as_ref().map_or(-1, |l| l.as_raw_fd()), events: libc::POLLIN, revents: 0 });
        fds.push(libc::pollfd { fd: ssh_agent.as_raw_fd(), events: libc::POLLIN, revents: 0 });
        fds.push(libc::pollfd { fd: engine_api.as_ref().map_or(-1, |l| l.as_raw_fd()), events: libc::POLLIN, revents: 0 });
        fds.push(libc::pollfd { fd: copies.as_raw_fd(), events: libc::POLLIN, revents: 0 });
        fds.push(libc::pollfd { fd: udp.as_raw_fd(), events: libc::POLLIN, revents: 0 });
        fds.push(libc::pollfd { fd: pressure.as_ref().map_or(-1, |f| f.as_raw_fd()), events: libc::POLLPRI, revents: 0 });
        fds.push(libc::pollfd { fd: term.as_ref().map_or(-1, |f| f.as_raw_fd()), events: libc::POLLIN, revents: 0 });
        fds.push(libc::pollfd { fd: usage_wake.as_raw_fd(), events: libc::POLLIN, revents: 0 });
        fds.push(libc::pollfd { fd: install_wait.as_ref().map_or(-1, |w| w.read.as_raw_fd()), events: libc::POLLIN, revents: 0 });
        for r in &relays {
            r.interest(&mut fds);
        }
        let mut hung = false;
        for p in procs.values() {
            // A hung-up pty polls as ready all the time; skip it a moment.
            if p.tty_hup.is_some_and(|t| t.elapsed() < TTY_HUP_WAIT) {
                hung = true;
                continue;
            }
            // A backed-up bulk connection stops this process's pipes being
            // read until it drains, like a full control-connection buffer.
            let bulk_full = p.bulk.as_ref().is_some_and(|b| b.pending.len() - b.pos > BULK_HIGH);
            for fd in [&p.run.stdout, &p.run.stderr].into_iter().flatten() {
                fds.push(libc::pollfd { fd: fd.as_raw_fd(), events: if bulk_full { 0 } else { libc::POLLIN }, revents: 0 });
            }
            if let (Some(fd), false) = (&p.run.stdin, p.input.is_empty()) {
                fds.push(libc::pollfd { fd: fd.as_raw_fd(), events: libc::POLLOUT, revents: 0 });
            }
            if let Some(b) = &p.bulk
                && b.pos < b.pending.len()
            {
                fds.push(libc::pollfd { fd: b.fd.as_raw_fd(), events: libc::POLLOUT, revents: 0 });
            }
        }
        // SAFETY: `fds` is a valid array of pollfd of the given length.
        let mut timeout = dhcp.as_ref().map_or(-1, Dhcp::timeout_ms);
        if hung {
            let wait = TTY_HUP_WAIT.as_millis() as i32;
            timeout = if timeout < 0 { wait } else { timeout.min(wait) };
        }
        let wait = dns.timeout_ms();
        if wait >= 0 {
            timeout = if timeout < 0 { wait } else { timeout.min(wait) };
        }
        // SAFETY: `fds` is a valid array of pollfd of the given length.
        let n = unsafe { libc::poll(fds.as_mut_ptr(), fds.len() as libc::nfds_t, timeout) };
        if n < 0 {
            let e = io::Error::last_os_error();
            if e.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            return Err(e);
        }

        if let Some(d) = dhcp.as_mut() {
            if fds[2].revents != 0 {
                match d.on_readable() {
                    Ok(true) => {
                        if let Some(l) = &d.lease {
                            eprintln!("ctrs-init: {} is {}/{} via {}", net::UPLINK, net::ip_str(l.ip), l.prefix, net::ip_str(l.gateway));
                        }
                    }
                    Ok(false) => {}
                    Err(e) => eprintln!("ctrs-init: dhcp: {e}"),
                }
            }
            if let Err(e) = d.on_timer() {
                eprintln!("ctrs-init: dhcp: {e}");
            }
        }

        dns.on_timer();

        // Output and input first, so a process's last words go out before its exit.
        for pfd in &fds[3..] {
            if pfd.revents == 0 {
                continue;
            }
            if term.as_ref().is_some_and(|t| t.as_raw_fd() == pfd.fd) {
                stop_containers(&mut procs);
                return Ok(());
            }
            if pfd.fd == usage_wake.as_raw_fd() {
                let mut sink = [0u8; 16];
                // SAFETY: reading into a buffer we own from a descriptor we own.
                while unsafe { libc::read(usage_wake.as_raw_fd(), sink.as_mut_ptr().cast(), sink.len()) } > 0 {}
                while let Ok(lines) = usage_rx.try_recv() {
                    measuring = false;
                    out.clear();
                    ctrs_proto::encode_usage(&mut out, &lines);
                    conn.write_all(&out)?;
                }
                continue;
            }
            if install_wait.as_ref().is_some_and(|w| w.read.as_raw_fd() == pfd.fd) {
                let mut eof = false;
                {
                    let w = install_wait.as_mut().expect("checked above");
                    let mut tmp = [0u8; 512];
                    loop {
                        // SAFETY: reading into a stack buffer from a descriptor we own.
                        let n = unsafe { libc::read(w.read.as_raw_fd(), tmp.as_mut_ptr().cast(), tmp.len()) };
                        if n > 0 {
                            w.buf.extend_from_slice(&tmp[..n as usize]);
                        } else if n == 0 {
                            eof = true;
                            break;
                        } else if io::Error::last_os_error().raw_os_error() == Some(libc::EAGAIN) {
                            break;
                        } else {
                            eof = true;
                            break;
                        }
                    }
                }
                // A record means the child finished its install; EOF or an
                // error first means it died mid-install. Either way the job
                // is over and the next one may start.
                let record = take_install_record(&mut install_wait.as_mut().expect("still waiting").buf);
                if record.is_some() || eof {
                    let w = install_wait.take().expect("waited on it");
                    let result = match record {
                        Some(r) => r,
                        None => Err(io::Error::new(io::ErrorKind::UnexpectedEof, "install child exited without a result")),
                    };
                    // SAFETY: plain waitpid on the child we forked; it has
                    // written its record or died, and reap() may already
                    // have collected it, which is fine.
                    let mut status = 0;
                    unsafe { libc::waitpid(w.pid, &mut status, 0) };
                    done_jobs.push_back(layers::InstallDone {
                        seq: w.job.seq,
                        digest: w.job.digest,
                        started: w.job.started,
                        result,
                    });
                    pump_installs(&paths.layers, &mut install_queue, &mut install_wait, &mut done_jobs);
                    drain_outbox(&mut conn, &mut out, &mut outbox, &mut done_jobs)?;
                }
                continue;
            }
            if pfd.fd == forward.as_raw_fd() {
                while let Some(r) = super::relay::accept(&forward) {
                    relays.push(r);
                }
                continue;
            }
            if pfd.fd == framed.as_raw_fd() {
                while let Some(r) = super::relay::accept_framed(&framed) {
                    relays.push(r);
                }
                continue;
            }
            if pressure.as_ref().is_some_and(|f| f.as_raw_fd() == pfd.fd) {
                // At most ten a second: the host reacts to the first one.
                if last_pressure.elapsed() >= std::time::Duration::from_millis(100) {
                    last_pressure = std::time::Instant::now();
                    out.clear();
                    Msg::MemoryPressure.encode(&mut out);
                    conn.write_all(&out)?;
                }
                continue;
            }
            if pfd.fd == udp.as_raw_fd() {
                while let Some(r) = super::relay::accept_udp(&udp) {
                    relays.push(r);
                }
                continue;
            }
            if pfd.fd == copies.as_raw_fd() {
                let running: Vec<(&str, libc::pid_t)> =
                    procs.iter().filter(|(_, p)| p.run.container.is_none() && p.exited.is_none()).map(|(pid, p)| (p.run.id.as_str(), *pid)).collect();
                super::copy::accept(&copies, &running, paths);
                continue;
            }
            if pfd.fd == ssh_agent.as_raw_fd() {
                while let Some(r) = super::relay::accept_ssh_agent(&ssh_agent) {
                    relays.push(r);
                }
                continue;
            }
            if let Some(l) = engine_api.as_ref().filter(|l| l.as_raw_fd() == pfd.fd) {
                while let Some(r) = super::relay::accept_engine(l) {
                    relays.push(r);
                }
                continue;
            }
            if let Some(l) = host_bound.as_ref().filter(|l| l.as_raw_fd() == pfd.fd) {
                while let Some(r) = super::relay::accept_host_bound(l, super::net::HOST_ADDR) {
                    relays.push(r);
                }
                continue;
            }
            if let Some(r) = relays.iter_mut().find(|r| r.owns(pfd.fd)) {
                r.step();
                continue;
            }
            if dns.owns(pfd.fd) {
                let upstream = dhcp.as_ref().and_then(|d| d.lease.as_ref()).map_or(&host_dns[..], |l| &l.dns);
                dns.on_readable(pfd.fd, upstream);
                continue;
            }
            // A bulk connection's POLLOUT: drain its pending output. A dead
            // connection drops the process back to the control connection
            // for whatever has not been written yet.
            if let Some(pid) = procs.iter().find_map(|(pid, p)| {
                p.bulk.as_ref().filter(|b| b.fd.as_raw_fd() == pfd.fd).map(|_| *pid)
            }) {
                let p = procs.get_mut(&pid).expect("found above");
                let failed = p.bulk.as_mut().is_some_and(|b| bulk_flush(b).is_err());
                if failed {
                    p.bulk = None;
                }
                continue;
            }
            // Only process stdin is polled for writing beyond this point.
            if pfd.events & libc::POLLOUT != 0 {
                flush_input(&mut procs, pfd.fd, &mut conn, &mut out)?;
                continue;
            }
            let Some((pid, stream)) = owner(&procs, pfd.fd) else { continue };
            let p = procs.get_mut(&pid).expect("owner found it");
            let slot = if stream == Stream::Stdout { &mut p.run.stdout } else { &mut p.run.stderr };
            let fd = slot.as_ref().expect("polled fd is open").as_raw_fd();
            // Drain while data is ready: one poll wakeup then pays for
            // many chunks instead of one read per cycle, which matters
            // when several processes stream at once. Reads are
            // nonblocking (as TTY masters already are), so EAGAIN ends
            // the drain; `got` keeps the last read's verdict.
            let mut got = 0;
            for _ in 0..8 {
                // SAFETY: reading into a buffer we own from a descriptor we own.
                got = unsafe { libc::read(fd, chunk.as_mut_ptr().cast(), chunk.len()) };
                if got <= 0 {
                    break;
                }
                p.tty_hup = None;
                out.clear();
                Msg::Output { id: &p.run.id, stream, data: &chunk[..got as usize] }.encode(&mut out);
                if let Some(b) = p.bulk.as_mut() {
                    b.pending.extend_from_slice(&out);
                    if bulk_flush(b).is_err() {
                        p.bulk = None;
                    }
                } else {
                    conn.write_all(&out)?;
                }
            }
            if got == 0 || (got < 0 && io::Error::last_os_error().raw_os_error() != Some(libc::EAGAIN)) {
                if got < 0 && p.run.tty && p.exited.is_none() && io::Error::last_os_error().raw_os_error() == Some(libc::EIO) {
                    // Nobody holds the terminal right now, but the process lives
                    // and may open it again (systemd does): keep it.
                    p.tty_hup = Some(std::time::Instant::now());
                } else {
                    // EOF, or EIO from a pty whose other side has closed.
                    *slot = None;
                    if p.run.tty {
                        p.run.stdin = None;
                    }
                }
            }
        }

        relays.retain(|r| !r.dead);

        if fds[1].revents != 0 {
            drain_signals(&sigfd);
            reap(&mut procs);
        }

        // Report processes that have exited and whose output is fully read,
        // then tear containers down after the host already has its answer.
        // A process on a bulk connection gets its exit report queued there
        // first, so it stays until the last frame is written; the report
        // then arrives after its output, as it does on the control conn.
        let mut done: Vec<(libc::pid_t, bool)> = Vec::new();
        for (pid, p) in procs.iter_mut() {
            if p.exited.is_none() || p.run.stdout.is_some() || p.run.stderr.is_some() {
                continue;
            }
            let Some(b) = p.bulk.as_mut() else {
                done.push((*pid, false));
                continue;
            };
            if !b.closing {
                let (code, reaped_ns) = p.exited.expect("checked above");
                out.clear();
                Msg::Exited(Exited {
                    id: &p.run.id,
                    code,
                    setup_ns: p.cloned_ns - p.received_ns,
                    run_ns: reaped_ns - p.cloned_ns,
                    oom_killed: container::oom_killed(&p.run),
                })
                .encode(&mut out);
                b.pending.extend_from_slice(&out);
                b.closing = true;
                if bulk_flush(b).is_err() {
                    p.bulk = None;
                    done.push((*pid, false));
                    continue;
                }
            }
            if b.drained() {
                p.bulk = None;
                done.push((*pid, true));
            }
        }
        for (pid, via_bulk) in done {
            let p = procs.remove(&pid).expect("listed above");
            if !via_bulk {
                let (code, reaped_ns) = p.exited.expect("filtered on exited");
                out.clear();
                let oom_killed = container::oom_killed(&p.run);
                Msg::Exited(Exited { id: &p.run.id, code, setup_ns: p.cloned_ns - p.received_ns, run_ns: reaped_ns - p.cloned_ns, oom_killed })
                    .encode(&mut out);
                conn.write_all(&out)?;
            }
            for (bridge, ip) in &p.run.dns_entries {
                dns.unregister(bridge, *ip);
            }
            dns.drop_container(pid);
            // A container still running in its network namespace keeps that
            // alive (its execs went with its PID namespace and count as 0).
            let shared = p.run.netns != 0 && procs.values().any(|o| o.exited.is_none() && o.run.netns == p.run.netns);
            container::teardown(&p.run, shared);
        }

        if fds[0].revents != 0 {
            if !read_frame(&mut conn, &mut frame)? {
                // The host went away: on a Linux host, the daemon died. Its
                // containers do not outlive it (there is no live restore).
                if host_process {
                    stop_containers(&mut procs);
                }
                return Ok(());
            }
            let received_ns = sys::boottime_ns();
            out.clear();
            match ctrs_proto::decode(&frame) {
                Ok(Msg::Ping(v)) => Msg::Pong(v).encode(&mut out),
                Ok(Msg::Shutdown) => {
                    if host_process {
                        // The daemon has stopped them Docker's way already;
                        // what is left is killed and torn down.
                        stop_containers(&mut procs);
                    } else {
                        for p in procs.values() {
                            // SAFETY: signalling a child we started.
                            unsafe { libc::kill(p.run.pid, libc::SIGKILL) };
                        }
                    }
                    return Ok(());
                }
                Ok(Msg::StatsRequest) => {
                    let (mem_total_kib, mem_available_kib) = meminfo();
                    let agent_rss_kib = self_rss_kib();
                    let (mem_stall, oom_kills) = super::cgroup::memory_trouble();
                    Msg::Stats(Stats { uptime_ns: sys::boottime_ns(), mem_total_kib, mem_available_kib, agent_rss_kib, mem_used_kib: held_kib(paths, agent_rss_kib), mem_stall, oom_kills })
                        .encode(&mut out)
                }
                Ok(Msg::LayerQuery(digest)) => Msg::LayerStatus(layers::present(&paths.layers, digest)).encode(&mut out),
                // The blob follows the frame on the same stream; it is staged
                // here (stream order demands it) but unpacked and flushed on
                // the install worker, so a large layer cannot stall output,
                // exits, execs or relays. Its Stored/Error reply keeps its
                // place in the outbox.
                Ok(Msg::LayerBegin(begin)) => {
                    let seq = install_seq;
                    install_seq += 1;
                    match layers::stage_blob(&mut conn, &begin, &paths.layers, seq) {
                        Ok(blob) => {
                            install_queue.push_back(layers::InstallJob {
                                seq,
                                digest: begin.digest.to_owned(),
                                media_type: begin.media_type.to_owned(),
                                size: begin.size,
                                blob,
                                started: std::time::Instant::now(),
                            });
                            outbox.push_back(OutItem::AwaitJob { seq });
                            pump_installs(&paths.layers, &mut install_queue, &mut install_wait, &mut done_jobs);
                            drain_outbox(&mut conn, &mut out, &mut outbox, &mut done_jobs)?;
                            continue;
                        }
                        Err(e) => Msg::Error(&format!("unpack {}: {e}", begin.digest)).encode(&mut out),
                    }
                }
                Ok(Msg::Run(spec)) => {
                    // A container that wants the network must not start before the
                    // VM has it: right after boot the DHCP lease can be a few
                    // hundred milliseconds away.
                    let prepared = {
                        if spec.flags & (ctrs_proto::run_flags::NET_NONE | ctrs_proto::run_flags::NET_HOST) == 0 {
                            wait_for_lease(&mut dhcp, std::time::Duration::from_secs(3));
                        }
                        let join_pid = ctrs_proto::net_opts::values(spec.net.opts, ctrs_proto::net_opts::NETNS).next().and_then(|t| running_pid(&procs, t));
                        container::spawn(
                            &spec,
                            paths,
                            NetCtx { bridges: &mut bridges, dns: &mut dns, upstream_dns: dhcp.as_ref().and_then(|d| d.lease.as_ref()).map_or(&host_dns[..], |l| &l.dns), join_pid },
                        )
                    };
                    match prepared {
                        Ok(run) => {
                            let cloned_ns = sys::boottime_ns();
                            Msg::Started { id: &run.id, pid: run.pid as u32 }.encode(&mut out);
                            procs.insert(run.pid, new_proc(run, received_ns, cloned_ns));
                        }
                        Err(e) => Msg::Error(&format!("run {}: {e}", spec.id)).encode(&mut out),
                    }
                }
                Ok(Msg::Exec(spec)) => {
                    let target = procs.values().find(|p| p.run.container.is_none() && p.run.id == spec.container_id);
                    match target.map(|p| p.run.pid) {
                        None => Msg::Error(&format!("container {} is not running", spec.container_id)).encode(&mut out),
                        Some(pid) => match container::exec(&spec, pid, paths) {
                            Ok(run) => {
                                let cloned_ns = sys::boottime_ns();
                                Msg::Started { id: &run.id, pid: run.pid as u32 }.encode(&mut out);
                                let pid = run.pid;
                                let mut p = new_proc(run, received_ns, cloned_ns);
                                p.bulk = bulk_connect(&p.run.id);
                                procs.insert(pid, p);
                            }
                            Err(e) => Msg::Error(&format!("exec in {}: {e}", spec.container_id)).encode(&mut out),
                        },
                    }
                }
                Ok(Msg::Input { id, data }) => {
                    let mut target = None;
                    if let Some(p) = procs.values_mut().find(|p| p.run.id == id)
                        && let Some(fd) = p.run.stdin.as_ref().map(|f| f.as_raw_fd())
                    {
                        if p.input.len() + data.len() > MAX_PENDING_INPUT {
                            p.input.clear();
                            p.run.stdin = None;
                        } else {
                            p.input.extend(data);
                            target = Some(fd);
                        }
                    }
                    if let Some(fd) = target {
                        flush_input(&mut procs, fd, &mut conn, &mut out)?;
                    }
                    continue;
                }
                Ok(Msg::CloseStdin { id }) => {
                    if let Some(p) = procs.values_mut().find(|p| p.run.id == id) {
                        // A terminal has no separate end of input; keep it open.
                        if !p.run.tty {
                            if p.input.is_empty() {
                                p.run.stdin = None;
                            } else {
                                p.close_stdin_when_drained = true;
                            }
                        }
                    }
                    continue;
                }
                Ok(Msg::Resize { id, rows, cols }) => {
                    if let Some(fd) = procs.values().find(|p| p.run.id == id && p.run.tty).and_then(|p| p.run.stdout.as_ref()) {
                        sys::resize_pty(fd.as_raw_fd(), rows, cols);
                    }
                    continue;
                }
                Ok(Msg::Kill { id, signal }) => {
                    if let Some(p) = procs.values().find(|p| p.run.id == id) {
                        // SAFETY: signalling a child we started and have not reaped.
                        unsafe { libc::kill(p.run.pid, signal as libc::c_int) };
                    }
                    continue; // no reply: the exit, if any, is reported as Exited
                }
                Ok(Msg::Remove { id }) => {
                    if !procs.values().any(|p| p.run.id == id) {
                        container::remove(paths, id);
                    }
                    continue;
                }
                Ok(Msg::Publish(p)) => {
                    // In the VM: from the Mac over the NAT network, TCP only.
                    let gateway = dhcp.as_ref().and_then(|d| d.lease.as_ref()).map(|l| l.gateway);
                    if !host_process && (p.udp || gateway.is_none()) {
                        Msg::Error("published ports are relayed on this platform").encode(&mut out);
                    } else {
                        let d = super::netlink::Dnat { udp: p.udp, host_ip: p.host_ip, host_port: p.host_port, to_ip: p.to_ip, to_port: p.to_port };
                        published.push((p.id.to_owned(), d));
                        let all = published.iter().map(|(_, d)| *d).collect::<Vec<_>>();
                        match if host_process { net::publish(&all) } else { net::publish_vm(&all, gateway.expect("checked")) } {
                            Ok(()) => Msg::Ack.encode(&mut out),
                            Err(e) => {
                                published.pop();
                                Msg::Error(&format!("publish {}:{}: {e}", p.host_port, p.to_port)).encode(&mut out)
                            }
                        }
                    }
                }
                Ok(Msg::Unpublish { id }) => {
                    let before = published.len();
                    published.retain(|(i, _)| i != id);
                    if published.len() != before {
                        let all = published.iter().map(|(_, d)| *d).collect::<Vec<_>>();
                        let gateway = dhcp.as_ref().and_then(|d| d.lease.as_ref()).map_or([0; 4], |l| l.gateway);
                        if let Err(e) = if host_process { net::publish(&all) } else { net::publish_vm(&all, gateway) } {
                            eprintln!("ctrs-init: unpublish {id}: {e}");
                        }
                    }
                    continue;
                }
                Ok(Msg::UsageQuery) => {
                    // No reply here: replies go in order, and this can take
                    // seconds. The lines follow as a `Usage` message.
                    if !measuring {
                        measuring = true;
                        let (layers, containers, tx, ring) = (paths.layers.clone(), paths.containers.clone(), usage_tx.clone(), usage_ring.clone());
                        let _ = std::thread::Builder::new().name("usage".into()).spawn(move || {
                            let _ = tx.send(super::usage::measure(&layers, &containers, Path::new(container::VOLUMES)));
                            // SAFETY: writing one byte from a buffer we own to a descriptor we own.
                            unsafe { libc::write(ring.as_raw_fd(), [1u8].as_ptr().cast(), 1) };
                        });
                    }
                    continue;
                }
                Ok(Msg::RemoveVolume { name }) => {
                    container::remove_volume(name);
                    continue;
                }
                Ok(Msg::RemoveBridge { bridge }) => {
                    // Only ctrs's own bridges, never another interface.
                    if bridge.starts_with("ctrs") && bridge != "ctrs0" {
                        dns.forget_bridge(bridge);
                        bridges.remove(bridge);
                    }
                    continue;
                }
                Ok(Msg::Retain(keep)) => {
                    let running: Vec<&str> = procs.values().map(|p| p.run.id.as_str()).collect();
                    container::retain(paths, keep, &running);
                    continue;
                }
                Ok(Msg::RetainLayers(keep)) => {
                    layers::retain(&paths.layers, keep.iter());
                    continue;
                }
                Ok(Msg::SetTime(ns)) => {
                    // A host process shares the host's clock; only the VM needs
                    // telling. The host sends it again every minute and after
                    // the Mac wakes: stepped only when off by more than a
                    // quarter second, so the clock is not nudged back and forth.
                    if !host_process && clock_off(ns) {
                        let ts = libc::timespec { tv_sec: (ns / 1_000_000_000) as _, tv_nsec: (ns % 1_000_000_000) as _ };
                        // SAFETY: `ts` is a valid timespec.
                        unsafe { libc::clock_settime(libc::CLOCK_REALTIME, &ts) };
                    }
                    continue;
                }
                Ok(Msg::Update { id, limits }) => match running_pid(&procs, id) {
                    Some(_) => match super::cgroup::apply_limits(&paths.cgroup.join(id), &limits) {
                        Ok(()) => Msg::Ack.encode(&mut out),
                        Err(e) => Msg::Error(&format!("update: {e}")).encode(&mut out),
                    },
                    None => Msg::Error(&format!("container {id} is not running")).encode(&mut out),
                },
                Ok(Msg::Freeze { id, frozen }) => match running_pid(&procs, id) {
                    Some(_) => match super::cgroup::freeze(&paths.cgroup.join(id), frozen) {
                        Ok(()) => Msg::Ack.encode(&mut out),
                        Err(e) => Msg::Error(&format!("freeze: {e}")).encode(&mut out),
                    },
                    None => Msg::Error(&format!("container {id} is not running")).encode(&mut out),
                },
                Ok(Msg::StatsQuery { id }) => match running_pid(&procs, id) {
                    Some(pid) => match super::cgroup::stats(&paths.cgroup.join(id), pid) {
                        Ok(s) => Msg::ContainerStats(s).encode(&mut out),
                        Err(e) => Msg::Error(&format!("stats: {e}")).encode(&mut out),
                    },
                    None => Msg::Error(&format!("container {id} is not running")).encode(&mut out),
                },
                Ok(Msg::TopQuery { id }) => match running_pid(&procs, id) {
                    Some(_) => {
                        let lines = super::cgroup::top(&paths.cgroup.join(id));
                        ctrs_proto::encode_top(&mut out, &lines);
                    }
                    None => Msg::Error(&format!("container {id} is not running")).encode(&mut out),
                },
                Ok(Msg::ListenQuery { id }) => match running_pid(&procs, id) {
                    Some(pid) => ctrs_proto::encode_listening(&mut out, &net::listening(pid)),
                    None => Msg::Error(&format!("container {id} is not running")).encode(&mut out),
                },
                Ok(Msg::NetAttach { id, ifname, net: n }) => match running_pid(&procs, id) {
                    Some(pid) => {
                        let num: u32 = ifname.strip_prefix("eth").and_then(|v| v.parse().ok()).unwrap_or(1);
                        let host_if = extra_veth(id, num);
                        // A previous run's veth can outlive its namespace for a moment;
                        // the name is this container's own, so it can go.
                        let _ = net::detach(&host_if);
                        let mac = ctrs_proto::net_opts::values(n.opts, ctrs_proto::net_opts::MAC).next().and_then(net::parse_mac);
                        let v6 = net::Ip6::from_opts(n.opts);
                        let plug = net::Plug::from_opts(n.opts);
                        let attached = net::attach(&mut bridges, n.bridge, &host_if, pid, num, n.ip, n.prefix, n.gateway, mac, v6, plug)
                            .and_then(|()| if plug.no_ipv4 { Ok(()) } else { dns.serve(n.bridge, n.gateway) })
                            .and_then(|()| std::fs::File::open(format!("/proc/{pid}/ns/net")).and_then(|ns| dns.serve_in(&ns, pid, n.ip, n.bridge)));
                        match attached {
                            Ok(()) => {
                                if !plug.no_ipv4 {
                                    dns.register(n.bridge, n.dns_names.iter(), n.ip);
                                }
                                if let Some(v) = v6 {
                                    dns.register6(n.bridge, n.dns_names.iter(), n.ip, v.ip);
                                }
                                if let Some(p) = procs.get_mut(&pid) {
                                    p.run.dns_entries.push((n.bridge.to_owned(), n.ip));
                                    p.run.veths.push(host_if.clone());
                                }
                                Msg::Ack.encode(&mut out)
                            }
                            Err(e) => Msg::Error(&format!("connect: {e}")).encode(&mut out),
                        }
                    }
                    None => Msg::Error(&format!("container {id} is not running")).encode(&mut out),
                },
                Ok(Msg::UplinkQuery) => match super::netlink::default_v4_route().and_then(|(index, gateway)| super::netlink::primary_v4_addr(index).map(|ip| (ip, gateway))) {
                    // The live answer: survives a vmnet re-lease without a
                    // VM restart. The boot-time lease is the fallback for a
                    // route that is not there yet (before DHCP finishes).
                    Ok((ip, gateway)) => Msg::Uplink { ip, gateway }.encode(&mut out),
                    Err(_) => match dhcp.as_ref().and_then(|d| d.lease.as_ref()) {
                        Some(l) => Msg::Uplink { ip: l.ip, gateway: l.gateway }.encode(&mut out),
                        None => Msg::Error("no uplink lease").encode(&mut out),
                    },
                },
                Ok(Msg::Route { dst, prefix, via, add }) => match net::route(dst, prefix, via, add) {
                    Ok(()) => Msg::Ack.encode(&mut out),
                    Err(e) => Msg::Error(&format!("route: {e}")).encode(&mut out),
                },
                Ok(Msg::NetDetach { id, ifname, bridge, ip }) => match running_pid(&procs, id) {
                    Some(pid) => {
                        let num: u32 = ifname.strip_prefix("eth").and_then(|v| v.parse().ok()).unwrap_or(1);
                        dns.unregister(bridge, ip);
                        dns.leave(pid, bridge);
                        let host_if = extra_veth(id, num);
                        if let Some(p) = procs.get_mut(&pid) {
                            p.run.dns_entries.retain(|(b, a)| !(b == bridge && *a == ip));
                            p.run.veths.retain(|v| *v != host_if);
                        }
                        match net::detach(&host_if) {
                            Ok(()) => Msg::Ack.encode(&mut out),
                            Err(e) => Msg::Error(&format!("disconnect: {e}")).encode(&mut out),
                        }
                    }
                    None => Msg::Error(&format!("container {id} is not running")).encode(&mut out),
                },
                Ok(other) => Msg::Error(&format!("unexpected {other:?}")).encode(&mut out),
                Err(e) => Msg::Error(&format!("bad frame: {e:?}")).encode(&mut out),
            }
            // `out` holds this frame's reply. With installs outstanding it
            // queues behind them so the host's FIFO reply matching holds;
            // the drain then writes whatever the front allows.
            if outbox.is_empty() {
                conn.write_all(&out)?;
            } else {
                outbox.push_back(OutItem::Ready(out.clone()));
            }
            drain_outbox(&mut conn, &mut out, &mut outbox, &mut done_jobs)?;
        }
    }
}

/// A PSI trigger: readable (POLLPRI) when tasks stall on memory for 50 ms
/// within any 500 ms window. None if the kernel has no PSI.
/// Runs the DHCP client alone until it has a lease or `max` passes.
fn wait_for_lease(dhcp: &mut Option<Dhcp>, max: std::time::Duration) {
    let Some(d) = dhcp.as_mut() else { return };
    let deadline = std::time::Instant::now() + max;
    while d.lease.is_none() {
        let left = deadline.saturating_duration_since(std::time::Instant::now());
        if left.is_zero() {
            eprintln!("ctrs-init: no DHCP lease yet; starting the container without waiting longer");
            return;
        }
        let mut pfd = libc::pollfd { fd: d.fd(), events: libc::POLLIN, revents: 0 };
        let wait = (d.timeout_ms().max(0) as u128).min(left.as_millis()) as libc::c_int;
        // SAFETY: one valid pollfd.
        unsafe { libc::poll(&mut pfd, 1, wait.max(1)) };
        if pfd.revents != 0 {
            let _ = d.on_readable();
        }
        let _ = d.on_timer();
    }
}

fn memory_pressure_trigger() -> Option<std::fs::File> {
    let mut f = std::fs::OpenOptions::new().read(true).write(true).open("/proc/pressure/memory").ok()?;
    f.write_all(b"some 50000 500000\0").ok()?;
    Some(f)
}

/// A running container's init (not an exec).
fn running_pid(procs: &HashMap<libc::pid_t, Proc>, id: &str) -> Option<libc::pid_t> {
    procs.iter().find(|(_, p)| p.run.container.is_none() && p.run.id == id && p.exited.is_none()).map(|(pid, _)| *pid)
}

/// The host side of a container's `eth{n}` for n > 0: 15 characters at most.
fn extra_veth(id: &str, n: u32) -> String {
    format!("kx{}{n}", &id[..id.len().min(9)])
}


fn new_proc(run: Process, received_ns: u64, cloned_ns: u64) -> Proc {
    Proc { run, received_ns, cloned_ns, exited: None, input: VecDeque::new(), close_stdin_when_drained: false, tty_hup: None, bulk: None }
}

/// Writes as much pending input as the process will take without blocking,
/// and tells the host how much, so it can send that much more.
fn flush_input(procs: &mut HashMap<libc::pid_t, Proc>, fd: RawFd, conn: &mut File, out: &mut Vec<u8>) -> io::Result<()> {
    let Some(p) = procs.values_mut().find(|p| p.run.stdin.as_ref().is_some_and(|f| f.as_raw_fd() == fd)) else { return Ok(()) };
    let mut consumed = 0usize;
    while !p.input.is_empty() {
        let (front, _) = p.input.as_slices();
        // SAFETY: writing from a buffer we own to a non-blocking descriptor we own.
        let n = unsafe { libc::write(fd, front.as_ptr().cast(), front.len()) };
        if n > 0 {
            p.input.drain(..n as usize);
            consumed += n as usize;
        } else {
            if io::Error::last_os_error().raw_os_error() != Some(libc::EAGAIN) {
                // The reader is gone.
                p.input.clear();
                p.run.stdin = None;
            }
            break;
        }
    }
    if p.input.is_empty() && p.close_stdin_when_drained {
        p.run.stdin = None;
    }
    if consumed > 0 {
        out.clear();
        Msg::InputConsumed { id: &p.run.id, bytes: consumed as u32 }.encode(out);
        conn.write_all(out)?;
    }
    Ok(())
}

/// This process's resident memory, from /proc/self/statm (in pages).
/// What ctrs's Linux holds, in KiB. In the VM, where this process is init,
/// it is the root cgroup: the whole guest. On a Linux host it is the
/// containers' cgroup and this process; the daemon adds itself.
fn held_kib(paths: &Paths, agent_rss_kib: u64) -> u64 {
    if std::process::id() == 1 {
        return super::cgroup::held(std::path::Path::new("/sys/fs/cgroup")).unwrap_or(0) >> 10;
    }
    match super::cgroup::held(&paths.cgroup) {
        Some(b) => (b >> 10) + agent_rss_kib,
        None => 0,
    }
}

fn self_rss_kib() -> u64 {
    let mut buf = [0u8; 128];
    let n = std::fs::File::open("/proc/self/statm").and_then(|mut f| f.read(&mut buf)).unwrap_or(0);
    let pages: u64 = std::str::from_utf8(&buf[..n]).ok().and_then(|s| s.split_whitespace().nth(1)?.parse().ok()).unwrap_or(0);
    // SAFETY: sysconf takes no pointers.
    pages * unsafe { libc::sysconf(libc::_SC_PAGESIZE) } as u64 / 1024
}

/// Whether the guest's clock is more than a quarter second from `ns`
/// (Unix nanoseconds, the host's time).
fn clock_off(ns: u64) -> bool {
    let now = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0, |d| d.as_nanos() as u64);
    off_by_more(now, ns, 250_000_000)
}

fn off_by_more(a: u64, b: u64, limit: u64) -> bool {
    a.abs_diff(b) > limit
}

/// Reads one frame into `buf`. Returns false on a clean end of stream.
fn read_frame(conn: &mut File, buf: &mut Vec<u8>) -> io::Result<bool> {
    buf.resize(4, 0);
    if let Err(e) = conn.read_exact(&mut buf[..4]) {
        return if e.kind() == io::ErrorKind::UnexpectedEof { Ok(false) } else { Err(e) };
    }
    let len = ctrs_proto::frame_len(buf[..4].try_into().expect("4 bytes"))
        .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, format!("{e:?}")))?;
    buf.resize(len, 0);
    conn.read_exact(&mut buf[4..])?;
    Ok(true)
}

fn owner(procs: &HashMap<libc::pid_t, Proc>, fd: RawFd) -> Option<(libc::pid_t, Stream)> {
    procs.iter().find_map(|(pid, p)| {
        if p.run.stdout.as_ref().is_some_and(|f| f.as_raw_fd() == fd) {
            Some((*pid, Stream::Stdout))
        } else if p.run.stderr.as_ref().is_some_and(|f| f.as_raw_fd() == fd) {
            Some((*pid, Stream::Stderr))
        } else {
            None
        }
    })
}

/// Blocks SIGCHLD and returns a signalfd that becomes readable when a child exits.
fn child_signals() -> io::Result<OwnedFd> {
    // SAFETY: sigset manipulation on a local set, then plain syscalls.
    unsafe {
        let mut set: libc::sigset_t = std::mem::zeroed();
        libc::sigemptyset(&mut set);
        libc::sigaddset(&mut set, libc::SIGCHLD);
        sys::check(libc::sigprocmask(libc::SIG_BLOCK, &set, std::ptr::null_mut()) as _, "sigprocmask")?;
        let fd = sys::check(libc::signalfd(-1, &set, libc::SFD_CLOEXEC | libc::SFD_NONBLOCK) as _, "signalfd")?;
        Ok(OwnedFd::from_raw_fd(fd as RawFd))
    }
}

/// Linux host: every process still running is killed and reaped (a few
/// seconds at most), and each container torn down: mounts, cgroup, and the
/// writable layer of a `--rm` one. Veths go with their network namespaces.
fn stop_containers(procs: &mut HashMap<libc::pid_t, Proc>) {
    for p in procs.values().filter(|p| p.exited.is_none()) {
        // SAFETY: signalling a child we started and have not reaped.
        unsafe { libc::kill(p.run.pid, libc::SIGKILL) };
    }
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(5);
    loop {
        reap(procs);
        if procs.values().all(|p| p.exited.is_some()) || std::time::Instant::now() >= deadline {
            break;
        }
        std::thread::sleep(std::time::Duration::from_millis(10));
    }
    for p in procs.values() {
        container::teardown(&p.run, false);
    }
    procs.clear();
}

/// The read end of a pipe written to on SIGTERM and SIGINT. A handler, not
/// a blocked signal read from a signalfd: a blocked mask would be inherited
/// by every container process, and a caught signal is reset by exec.
fn term_signals() -> io::Result<OwnedFd> {
    let mut fds = [0; 2];
    // SAFETY: plain pipe2 and sigaction; the handler only calls write(2),
    // which is async-signal-safe, on a descriptor that is never closed.
    unsafe {
        sys::check(libc::pipe2(fds.as_mut_ptr(), libc::O_CLOEXEC | libc::O_NONBLOCK) as _, "pipe")?;
        TERM_PIPE.store(fds[1], std::sync::atomic::Ordering::SeqCst);
        AGENT_PID.store(libc::getpid(), std::sync::atomic::Ordering::SeqCst);
        let mut sa: libc::sigaction = std::mem::zeroed();
        sa.sa_sigaction = on_term as *const () as usize;
        sa.sa_flags = libc::SA_RESTART;
        libc::sigemptyset(&mut sa.sa_mask);
        for sig in [libc::SIGTERM, libc::SIGINT] {
            sys::check(libc::sigaction(sig, &sa, std::ptr::null_mut()) as _, "sigaction")?;
        }
        Ok(OwnedFd::from_raw_fd(fds[0]))
    }
}

static TERM_PIPE: std::sync::atomic::AtomicI32 = std::sync::atomic::AtomicI32::new(-1);
static AGENT_PID: std::sync::atomic::AtomicI32 = std::sync::atomic::AtomicI32::new(0);

extern "C" fn on_term(_: libc::c_int) {
    // A container's process, between its clone and its exec, still has
    // this handler (and the pipe): a signal meant for it must not stop the
    // agent.
    // SAFETY: getpid and write(2) are async-signal-safe.
    unsafe {
        if libc::getpid() == AGENT_PID.load(std::sync::atomic::Ordering::SeqCst) {
            libc::write(TERM_PIPE.load(std::sync::atomic::Ordering::SeqCst), b"t".as_ptr().cast(), 1);
        }
    }
}

fn drain_signals(fd: &OwnedFd) {
    let mut info = [0u8; 128 * 8];
    // SAFETY: reading into a local buffer from a non-blocking signalfd.
    while unsafe { libc::read(fd.as_raw_fd(), info.as_mut_ptr().cast(), info.len()) } > 0 {}
}

fn reap(procs: &mut HashMap<libc::pid_t, Proc>) {
    loop {
        let mut status = 0;
        // SAFETY: plain waitpid on any child.
        let pid = unsafe { libc::waitpid(-1, &mut status, libc::WNOHANG) };
        if pid <= 0 {
            return;
        }
        let code = if libc::WIFEXITED(status) {
            libc::WEXITSTATUS(status)
        } else if libc::WIFSIGNALED(status) {
            128 + libc::WTERMSIG(status)
        } else {
            continue;
        };
        if let Some(p) = procs.get_mut(&pid) {
            p.exited = Some((code, sys::boottime_ns()));
            // Nobody will read input any more.
            p.input.clear();
            p.run.stdin = None;
        }
    }
}

/// A non-blocking pipe: (read end the loop polls, write end the thread rings).
fn usage_pipe() -> io::Result<(OwnedFd, OwnedFd)> {
    let mut fds = [0; 2];
    // SAFETY: `fds` has room for the two descriptors pipe2 writes.
    sys::check(unsafe { libc::pipe2(fds.as_mut_ptr(), libc::O_CLOEXEC | libc::O_NONBLOCK) } as _, "pipe")?;
    // SAFETY: pipe2 just opened both; nothing else owns them.
    Ok(unsafe { (OwnedFd::from_raw_fd(fds[0]), OwnedFd::from_raw_fd(fds[1])) })
}

#[cfg(test)]
mod clock_tests {
    use super::off_by_more;

    #[test]
    fn steps_only_when_the_clock_is_off() {
        let now = 1_792_800_000_000_000_000;
        assert!(!off_by_more(now, now, 250_000_000));
        assert!(!off_by_more(now, now + 200_000_000, 250_000_000));
        assert!(!off_by_more(now + 200_000_000, now, 250_000_000));
        // An hour behind, after the Mac slept.
        assert!(off_by_more(now - 3_600_000_000_000, now, 250_000_000));
        assert!(off_by_more(now + 300_000_000, now, 250_000_000));
    }
}

