//! Port forwarding, guest side: the host opens a vsock stream per client
//! connection, sends `ip[4] port[2]`, and the agent relays bytes between it
//! and a TCP connection to that address. Non-blocking, from the agent's poll
//! loop, with bounded buffers in each direction.

use std::io;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd, RawFd};

use super::sys;

/// vsock port the agent accepts forwarded connections on.
pub const PORT: u32 = 1025;
/// Forwarded UDP: the same header, then datagrams framed as `u16 len | bytes`
/// both ways on one stream per client address.
pub const UDP_PORT: u32 = 1029;
/// Forwarded TCP as on `PORT`, but what the container sends comes back
/// framed as `u32 len | bytes`, and an empty frame is its end. The Mac
/// side learns the end from that frame, not from the stream's half-close:
/// Virtualization.framework drops a guest's vsock half-close that follows
/// data too closely (a few in a thousand under concurrent connections), and
/// the client then waits for an end that never comes.
pub const FRAMED_PORT: u32 = 1030;
/// Largest UDP payload.
const MAX_DATAGRAM: usize = 65_507;
const BUF: usize = 64 * 1024;

pub fn listen() -> io::Result<OwnedFd> {
    listen_vsock(PORT)
}

/// A non-blocking listener on `port` (vsock, or a unix socket on a Linux host).
pub fn listen_vsock(port: u32) -> io::Result<OwnedFd> {
    super::transport::listen(port)
}

/// Bytes a direction may hold in its kernel pipe.
const SPLICE_CAP: usize = 1 << 20;
/// A direction moves to splice after copying this much: short connections
/// never pay for a pipe or its descriptors.
const SPLICE_AFTER: usize = 256 * 1024;

/// One direction of a relay.
struct Pipe {
    /// Bytes to write before anything in `kernel`: a frame's length, or
    /// what the copy fallback read.
    buf: Vec<u8>,
    /// The reading side reached EOF; once `buf` drains, shut the writer.
    eof: bool,
    shut: bool,
    /// Bytes move from socket to socket through a kernel pipe, never
    /// through `buf`, once the direction has copied `SPLICE_AFTER`.
    kernel: Option<KernelPipe>,
    /// Bytes copied through `buf` so far.
    copied: usize,
    /// splice or a pipe was refused; copy through `buf` for good.
    copy_only: bool,
}

struct KernelPipe {
    read: OwnedFd,
    write: OwnedFd,
    held: usize,
}

impl Pipe {
    fn new() -> Pipe {
        Pipe { buf: Vec::new(), eof: false, shut: false, kernel: None, copied: 0, copy_only: false }
    }

    /// A direction that never splices: the Mac's bytes arriving over the NAT
    /// network, measured slower spliced than copied into the container.
    fn copied_only() -> Pipe {
        Pipe { copy_only: true, ..Pipe::new() }
    }

    fn held(&self) -> usize {
        self.kernel.as_ref().map_or(0, |k| k.held)
    }

    /// Room to read more: the copy buffer, or the kernel pipe (one frame
    /// at a time when framed, so a length always precedes its bytes).
    fn wants_input(&self, framed: bool) -> bool {
        !self.eof && match &self.kernel {
            None => self.buf.len() < BUF,
            Some(k) if framed => self.buf.is_empty() && k.held == 0,
            Some(k) => self.buf.is_empty() && k.held < SPLICE_CAP,
        }
    }

    fn has_output(&self) -> bool {
        !self.buf.is_empty() || self.held() > 0
    }
}

fn kernel_pipe() -> Option<KernelPipe> {
    let mut fds = [0; 2];
    // SAFETY: pipe2 fills two fresh descriptors that we own at once.
    if unsafe { libc::pipe2(fds.as_mut_ptr(), libc::O_NONBLOCK | libc::O_CLOEXEC) } != 0 {
        return None;
    }
    // SAFETY: both descriptors are fresh and owned by nothing else.
    let (read, write) = unsafe { (OwnedFd::from_raw_fd(fds[0]), OwnedFd::from_raw_fd(fds[1])) };
    // SAFETY: F_SETPIPE_SZ on a pipe we own; a smaller limit keeps the default size.
    unsafe { libc::fcntl(write.as_raw_fd(), libc::F_SETPIPE_SZ, SPLICE_CAP as libc::c_int) };
    Some(KernelPipe { read, write, held: 0 })
}

fn splice(from: RawFd, to: RawFd, len: usize) -> io::Result<usize> {
    // SAFETY: splice between descriptors we own, with no offsets.
    let n = unsafe { libc::splice(from, std::ptr::null_mut(), to, std::ptr::null_mut(), len, libc::SPLICE_F_NONBLOCK | libc::SPLICE_F_MOVE) };
    if n < 0 { Err(io::Error::last_os_error()) } else { Ok(n as usize) }
}

pub struct Relay {
    host: OwnedFd,
    target: Option<OwnedFd>,
    connected: bool,
    header: Vec<u8>,
    /// host → container, container → host.
    up: Pipe,
    down: Pipe,
    pub dead: bool,
    udp: bool,
    /// The container's bytes go to the host in frames (`FRAMED_PORT`).
    framed: bool,
    /// The backend connect failed; a refusal marker still owes the host.
    refusing: bool,
    /// A connection the agent opened to the Mac's NAT relay ahead of time,
    /// for a published-port client the Mac has yet to accept. Only the
    /// container's bytes go over it; the client's come over vsock.
    leg: bool,
    leg_id: u16,
    /// Where a leg's client bytes come from: the vsock stream the Mac
    /// opened for it.
    up_src: Option<OwnedFd>,
    /// A vsock stream that carries the client bytes for leg `attach`.
    attach: Option<u16>,
}

pub fn listen_udp() -> io::Result<OwnedFd> {
    listen_vsock(UDP_PORT)
}

/// A forwarded UDP client: datagrams to and from `ip:port` in a container.
pub fn accept_udp(listener: &OwnedFd) -> Option<Relay> {
    accept(listener).map(|r| Relay { udp: true, ..r })
}

pub fn listen_framed() -> io::Result<OwnedFd> {
    listen_vsock(FRAMED_PORT)
}

/// A forwarded TCP client whose replies go back framed.
pub fn accept_framed(listener: &OwnedFd) -> Option<Relay> {
    accept(listener).map(|r| Relay { framed: true, ..r })
}

pub fn accept(listener: &OwnedFd) -> Option<Relay> {
    // SAFETY: accept4 on a listening socket we own; the fd is owned immediately.
    let fd = unsafe { libc::accept4(listener.as_raw_fd(), std::ptr::null_mut(), std::ptr::null_mut(), libc::SOCK_NONBLOCK | libc::SOCK_CLOEXEC) };
    if fd < 0 {
        return None;
    }
    // SAFETY: `fd` is a fresh descriptor that nothing else owns.
    let host = unsafe { OwnedFd::from_raw_fd(fd) };
    Some(Relay { host, target: None, connected: false, header: Vec::with_capacity(6), up: Pipe::new(), down: Pipe::new(), dead: false, udp: false, framed: false, refusing: false, leg: false, leg_id: 0, up_src: None, attach: None })
}

fn read_into(fd: RawFd, buf: &mut Vec<u8>, max: usize) -> io::Result<usize> {
    let start = buf.len();
    let room = max - start;
    if room == 0 {
        return Ok(1); // not EOF; just full
    }
    buf.resize(start + room, 0);
    // SAFETY: reading into the spare part of a buffer we own.
    let n = unsafe { libc::read(fd, buf[start..].as_mut_ptr().cast(), room) };
    if n < 0 {
        buf.truncate(start);
        return Err(io::Error::last_os_error());
    }
    buf.truncate(start + n as usize);
    Ok(n as usize)
}

/// `read_into` as one frame for the host: `u32 len | bytes`. EOF adds the
/// empty frame that ends the stream.
fn read_frame_into(fd: RawFd, buf: &mut Vec<u8>, max: usize) -> io::Result<usize> {
    let start = buf.len();
    if max <= start + 4 {
        return Ok(1); // not EOF; just full
    }
    buf.resize(max, 0);
    // SAFETY: reading into the spare part of a buffer we own, after the frame's length.
    let n = unsafe { libc::read(fd, buf[start + 4..].as_mut_ptr().cast(), max - start - 4) };
    if n < 0 {
        buf.truncate(start);
        return Err(io::Error::last_os_error());
    }
    buf[start..start + 4].copy_from_slice(&(n as u32).to_be_bytes());
    buf.truncate(start + 4 + n as usize);
    Ok(n as usize)
}

fn write_from(fd: RawFd, buf: &mut Vec<u8>) -> io::Result<()> {
    if buf.is_empty() {
        return Ok(());
    }
    // SAFETY: writing from a buffer we own.
    let n = unsafe { libc::write(fd, buf.as_ptr().cast(), buf.len()) };
    if n < 0 {
        return Err(io::Error::last_os_error());
    }
    buf.drain(..n as usize);
    Ok(())
}

fn would_block(e: &io::Error) -> bool {
    matches!(e.raw_os_error(), Some(libc::EAGAIN) | Some(libc::EINPROGRESS))
}

impl Relay {
    /// (fd, events) pairs to poll for this relay.
    pub fn interest(&self, out: &mut Vec<libc::pollfd>) {
        let reading_up = self.up.wants_input(false);
        // A leg's host side carries only its header up; the client's bytes
        // come from `up_src`.
        // Nothing is read from the host while the container's connect is
        // pending: a client's early bytes would wake poll at once, again and
        // again, until a dropped SYN is sent again a second later.
        let host_in = if self.leg { self.target.is_none() && !self.refusing } else { self.target.is_none() || (self.connected && reading_up) };
        let host_ev = (if host_in { libc::POLLIN } else { 0 })
            | (if self.down.has_output() { libc::POLLOUT } else { 0 })
            | if self.refusing { libc::POLLOUT } else { 0 };
        out.push(libc::pollfd { fd: self.host.as_raw_fd(), events: host_ev, revents: 0 });
        if let Some(u) = &self.up_src {
            out.push(libc::pollfd { fd: u.as_raw_fd(), events: if self.connected && reading_up { libc::POLLIN } else { 0 }, revents: 0 });
        }
        if let (Some(t), true) = (&self.target, self.udp) {
            out.push(libc::pollfd { fd: t.as_raw_fd(), events: libc::POLLIN, revents: 0 });
            return;
        }
        if let Some(t) = &self.target {
            let ev = if !self.connected {
                libc::POLLOUT
            } else {
                (if self.down.wants_input(self.framed) { libc::POLLIN } else { 0 })
                    | if self.up.has_output() { libc::POLLOUT } else { 0 }
            };
            out.push(libc::pollfd { fd: t.as_raw_fd(), events: ev, revents: 0 });
        }
    }

    /// A NAT leg the Mac has not yet handed a client.
    pub fn idle_leg(&self) -> bool {
        self.leg && self.target.is_none() && self.up_src.is_none() && !self.refusing && !self.dead
    }

    pub fn is_leg(&self) -> bool {
        self.leg
    }

    pub fn leg_id(&self) -> u16 {
        self.leg_id
    }

    /// The client stream of a leg, once its header named the leg; this
    /// relay is done with it.
    pub fn take_attach(&mut self) -> Option<(u16, OwnedFd)> {
        let id = self.attach.take()?;
        self.dead = true;
        Some((id, self.host.try_clone().ok()?))
    }

    /// Gives leg `id` its client stream; false if this is not that leg.
    pub fn attach_up(&mut self, id: u16, src: &mut Option<OwnedFd>) -> bool {
        if !self.leg || self.leg_id != id || self.up_src.is_some() || self.dead {
            return false;
        }
        self.up_src = src.take();
        true
    }

    pub fn lost_leg(&self) -> bool {
        self.leg && self.dead && self.target.is_none() && !self.refusing
    }

    pub fn owns(&self, fd: RawFd) -> bool {
        self.host.as_raw_fd() == fd || self.target.as_ref().is_some_and(|t| t.as_raw_fd() == fd) || self.up_src.as_ref().is_some_and(|u| u.as_raw_fd() == fd)
    }

    /// Makes progress after poll; marks the relay dead when it is finished.
    pub fn step(&mut self) {
        if let Err(e) = self.try_step()
            && !would_block(&e)
        {
            self.dead = true;
        }
        if self.up.shut && self.down.shut {
            self.dead = true;
        }
    }

    fn try_step(&mut self) -> io::Result<()> {
        if self.refusing {
            // A `u32::MAX` frame length is the refusal marker: it precedes
            // the stream's end so the host can stop relaying retries to a
            // backend that is not listening.
            let marker = u32::MAX.to_be_bytes();
            // SAFETY: writing to a socket we own.
            let n = unsafe { libc::write(self.host.as_raw_fd(), marker.as_ptr().cast(), marker.len()) };
            if n == marker.len() as isize {
                self.dead = true;
            } else if n >= 0 || would_block(&io::Error::last_os_error()) {
                // Partial or busy: try again next poll.
            } else {
                self.dead = true;
            }
            return Ok(());
        }
        if self.target.is_none() {
            // The header: where to connect.
            let need = 6 - self.header.len();
            let mut b = [0u8; 6];
            // SAFETY: reading into a local buffer.
            let n = unsafe { libc::read(self.host.as_raw_fd(), b.as_mut_ptr().cast(), need) };
            if n == 0 {
                self.dead = true;
                return Ok(());
            }
            if n < 0 {
                return Err(io::Error::last_os_error());
            }
            self.header.extend_from_slice(&b[..n as usize]);
            if self.header.len() < 6 {
                return Ok(());
            }
            let ip: [u8; 4] = self.header[..4].try_into().expect("4");
            let port = u16::from_be_bytes([self.header[4], self.header[5]]);
            if ip == [0; 4] && !self.udp && !self.framed && !self.leg {
                self.attach = Some(port);
                return Ok(());
            }
            if self.udp {
                self.target = Some(connect_udp(ip, port)?);
                self.connected = true;
            } else {
                match connect(ip, port) {
                    Ok(t) => self.target = Some(t),
                    Err(e) => {
                        if self.framed {
                            self.refusing = true;
                        } else {
                            return Err(e);
                        }
                    }
                }
            }
            return Ok(());
        }
        if self.udp {
            let target = self.target.as_ref().expect("checked").as_raw_fd();
            return udp_step(self.host.as_raw_fd(), target, &mut self.up, &mut self.down);
        }
        let target = self.target.as_ref().expect("checked").as_raw_fd();
        if !self.connected {
            let mut err: libc::c_int = 0;
            let mut len = std::mem::size_of::<libc::c_int>() as u32;
            // SAFETY: reading SO_ERROR into a local int.
            unsafe { libc::getsockopt(target, libc::SOL_SOCKET, libc::SO_ERROR, (&mut err as *mut libc::c_int).cast(), &mut len) };
            if err == libc::EINPROGRESS || err == libc::EALREADY {
                return Ok(());
            }
            if err != 0 {
                // Refused: the client sees its connection close. On the
                // framed port the marker lets the host drop retries early.
                if self.framed {
                    self.refusing = true;
                } else {
                    self.dead = true;
                }
                return Ok(());
            }
            // Writable without error means connected; one quick probe tells
            // a still-pending connect apart.
            // SAFETY: plain getpeername into a local buffer.
            let mut sa: libc::sockaddr_in = unsafe { std::mem::zeroed() };
            let mut sl = std::mem::size_of::<libc::sockaddr_in>() as u32;
            if unsafe { libc::getpeername(target, (&mut sa as *mut libc::sockaddr_in).cast(), &mut sl) } != 0 {
                return Ok(());
            }
            self.connected = true;
        }
        let host = self.host.as_raw_fd();
        match (&self.up_src, self.leg) {
            (Some(src), _) => pump(src.as_raw_fd(), target, &mut self.up, false)?,
            (None, false) => pump(host, target, &mut self.up, false)?,
            (None, true) => {}
        }
        pump(target, host, &mut self.down, self.framed)?;
        Ok(())
    }
}

/// Moves bytes from `from` to `to` through `pipe`, passing EOF on as a
/// half-close once everything read has been written.
fn pump(from: RawFd, to: RawFd, pipe: &mut Pipe, framed: bool) -> io::Result<()> {
    if pipe.kernel.is_none() && !pipe.copy_only && pipe.copied >= SPLICE_AFTER && pipe.buf.is_empty() {
        pipe.kernel = kernel_pipe();
        pipe.copy_only = pipe.kernel.is_none();
    }
    if pipe.kernel.is_none() {
        return pump_copy(from, to, pipe, framed);
    }
    match pump_splice(from, to, pipe, framed) {
        Err(e) if e.raw_os_error() == Some(libc::EINVAL) && pipe.held() == 0 && pipe.buf.is_empty() => {
            pipe.kernel = None;
            pipe.copy_only = true;
            pump_copy(from, to, pipe, framed)
        }
        r => r,
    }
}

/// `pump` without copying through user space: the socket's bytes go into
/// a kernel pipe and out of it. A frame's length is written before its
/// bytes, and a frame is one splice's worth.
fn pump_splice(from: RawFd, to: RawFd, pipe: &mut Pipe, framed: bool) -> io::Result<()> {
    flush_splice(to, pipe)?;
    if pipe.wants_input(framed) {
        let k = pipe.kernel.as_mut().expect("splice pipe");
        match splice(from, k.write.as_raw_fd(), SPLICE_CAP - k.held) {
            Ok(0) => {
                pipe.eof = true;
                if framed {
                    pipe.buf.extend_from_slice(&0u32.to_be_bytes());
                }
            }
            Ok(n) => {
                k.held += n;
                if framed {
                    pipe.buf.extend_from_slice(&(n as u32).to_be_bytes());
                }
            }
            Err(e) if would_block(&e) => {}
            Err(e) => return Err(e),
        }
        flush_splice(to, pipe)?;
    }
    if pipe.eof && !pipe.has_output() && !pipe.shut {
        // SAFETY: half-closing a socket we own.
        unsafe { libc::shutdown(to, libc::SHUT_WR) };
        pipe.shut = true;
    }
    Ok(())
}

fn flush_splice(to: RawFd, pipe: &mut Pipe) -> io::Result<()> {
    match write_from(to, &mut pipe.buf) {
        Ok(()) => {}
        Err(e) if would_block(&e) => return Ok(()),
        Err(e) => return Err(e),
    }
    if !pipe.buf.is_empty() {
        return Ok(());
    }
    let k = pipe.kernel.as_mut().expect("splice pipe");
    while k.held > 0 {
        match splice(k.read.as_raw_fd(), to, k.held) {
            Ok(0) => break,
            Ok(n) => k.held -= n,
            Err(e) if would_block(&e) => break,
            Err(e) => return Err(e),
        }
    }
    Ok(())
}

fn pump_copy(from: RawFd, to: RawFd, pipe: &mut Pipe, framed: bool) -> io::Result<()> {
    if !pipe.eof && pipe.buf.len() < BUF {
        let read = if framed { read_frame_into(from, &mut pipe.buf, BUF) } else { read_into(from, &mut pipe.buf, BUF) };
        match read {
            Ok(0) => pipe.eof = true,
            Ok(_) => {}
            Err(e) if would_block(&e) => {}
            Err(e) => return Err(e),
        }
    }
    let before = pipe.buf.len();
    match write_from(to, &mut pipe.buf) {
        Ok(()) => {}
        Err(e) if would_block(&e) => {}
        Err(e) => return Err(e),
    }
    pipe.copied += before - pipe.buf.len();
    if pipe.eof && pipe.buf.is_empty() && !pipe.shut {
        // SAFETY: half-closing a socket we own.
        unsafe { libc::shutdown(to, libc::SHUT_WR) };
        pipe.shut = true;
    }
    Ok(())
}

/// Frames from the host become datagrams; datagrams become frames. A full
/// socket buffer drops datagrams, as UDP may.
fn udp_step(host: RawFd, target: RawFd, up: &mut Pipe, down: &mut Pipe) -> io::Result<()> {
    if !up.eof && up.buf.len() < BUF {
        match read_into(host, &mut up.buf, BUF) {
            Ok(0) => up.eof = true,
            Ok(_) => {}
            Err(e) if would_block(&e) => {}
            Err(e) => return Err(e),
        }
    }
    while up.buf.len() >= 2 {
        let len = u16::from_be_bytes([up.buf[0], up.buf[1]]) as usize;
        if up.buf.len() < 2 + len {
            break;
        }
        // SAFETY: sending from a buffer we own on a connected socket.
        unsafe { libc::send(target, up.buf[2..].as_ptr().cast(), len, libc::MSG_DONTWAIT) };
        up.buf.drain(..2 + len);
    }
    if up.eof {
        // The host ended the session (idle, or the client went away).
        up.shut = true;
        down.shut = true;
        return Ok(());
    }
    let mut d = [0u8; MAX_DATAGRAM];
    while down.buf.len() + 2 + MAX_DATAGRAM <= BUF * 2 {
        // SAFETY: receiving into a local buffer.
        let n = unsafe { libc::recv(target, d.as_mut_ptr().cast(), d.len(), libc::MSG_DONTWAIT) };
        if n < 0 {
            break; // EAGAIN, or ECONNREFUSED from an ICMP: nothing to pass on
        }
        down.buf.extend_from_slice(&(n as u16).to_be_bytes());
        down.buf.extend_from_slice(&d[..n as usize]);
    }
    match write_from(host, &mut down.buf) {
        Ok(()) => Ok(()),
        Err(e) if would_block(&e) => Ok(()),
        Err(e) => Err(e),
    }
}

fn connect_udp(ip: [u8; 4], port: u16) -> io::Result<OwnedFd> {
    // SAFETY: plain socket setup; the fd is owned immediately.
    unsafe {
        let fd = sys::check(libc::socket(libc::AF_INET, libc::SOCK_DGRAM | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK, 0) as _, "socket")?;
        let sock = OwnedFd::from_raw_fd(fd as RawFd);
        let mut a: libc::sockaddr_in = std::mem::zeroed();
        a.sin_family = libc::AF_INET as libc::sa_family_t;
        a.sin_port = port.to_be();
        a.sin_addr.s_addr = u32::from_ne_bytes(ip);
        sys::check(libc::connect(sock.as_raw_fd(), (&a as *const libc::sockaddr_in).cast(), std::mem::size_of::<libc::sockaddr_in>() as u32) as _, "connect")?;
        Ok(sock)
    }
}

fn connect(ip: [u8; 4], port: u16) -> io::Result<OwnedFd> {
    // SAFETY: plain non-blocking connect; the fd is owned immediately.
    unsafe {
        let fd = sys::check(libc::socket(libc::AF_INET, libc::SOCK_STREAM | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK, 0) as _, "socket")?;
        let sock = OwnedFd::from_raw_fd(fd as RawFd);
        let one: libc::c_int = 1;
        libc::setsockopt(sock.as_raw_fd(), libc::IPPROTO_TCP, libc::TCP_NODELAY, (&one as *const libc::c_int).cast(), 4);
        let mut a: libc::sockaddr_in = std::mem::zeroed();
        a.sin_family = libc::AF_INET as libc::sa_family_t;
        a.sin_port = port.to_be();
        a.sin_addr.s_addr = u32::from_ne_bytes(ip);
        let r = libc::connect(sock.as_raw_fd(), (&a as *const libc::sockaddr_in).cast(), std::mem::size_of::<libc::sockaddr_in>() as u32);
        if r != 0 {
            let e = io::Error::last_os_error();
            if e.raw_os_error() != Some(libc::EINPROGRESS) {
                return Err(e);
            }
        }
        Ok(sock)
    }
}

/// The reverse direction, for `host.docker.internal`: TCP connections a
/// container makes to the reserved host address are redirected here.
pub fn listen_host_bound(port: u16) -> io::Result<OwnedFd> {
    // SAFETY: plain socket setup; the fd is owned immediately.
    unsafe {
        let fd = sys::check(libc::socket(libc::AF_INET, libc::SOCK_STREAM | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK, 0) as _, "socket")?;
        let sock = OwnedFd::from_raw_fd(fd as RawFd);
        let one: libc::c_int = 1;
        libc::setsockopt(sock.as_raw_fd(), libc::SOL_SOCKET, libc::SO_REUSEADDR, (&one as *const libc::c_int).cast(), 4);
        let mut a: libc::sockaddr_in = std::mem::zeroed();
        a.sin_family = libc::AF_INET as libc::sa_family_t;
        a.sin_port = port.to_be();
        sys::check(libc::bind(sock.as_raw_fd(), (&a as *const libc::sockaddr_in).cast(), std::mem::size_of::<libc::sockaddr_in>() as u32) as _, "bind")?;
        sys::check(libc::listen(sock.as_raw_fd(), 128) as _, "listen")?;
        Ok(sock)
    }
}

/// The host side listens on this vsock port for host-bound connections
/// whose container bytes arrive framed, as on `FRAMED_PORT`: after bulk
/// data Virtualization.framework drops the guest's vsock half-close, and
/// the Mac service would wait for an end that never comes.
pub const HOST_FRAMED_VSOCK_PORT: u32 = 1032;

/// Accepts one redirected connection, finds the port the container meant,
/// dials the Mac and returns a relay between the two. Only connections that
/// were redirected from `host_addr` are relayed: one made to the listener
/// directly (from the LAN, on a Linux host) would reach the host's loopback.
/// Where the Mac accepts host-bound connections on the VM's NAT network
/// (`Msg::HostRelay`). The path carries guest-to-Mac bytes faster than
/// vsock; a connection that cannot reach it uses vsock instead.
#[derive(Clone, Copy)]
pub struct NatRelay {
    pub addr: [u8; 4],
    pub port: u16,
    pub token: [u8; 16],
}

/// How long a NAT relay connect may hold up the agent loop before the
/// connection falls back to vsock.
const NAT_CONNECT_MS: libc::c_int = 100;
const MIRROR_VSOCK_CONNECT: std::time::Duration = std::time::Duration::from_millis(100);

/// What a connection to the Mac's NAT relay is for, the byte after the token.
const NAT_HOST_BOUND: u8 = 0;
const NAT_PUBLISHED_LEG: u8 = 1;

/// A connected TCP socket to the Mac's NAT relay with the token and
/// `header` already written, or None to fall back to vsock.
fn dial_nat(nat: &NatRelay, kind: u8, target: [u8; 6]) -> Option<OwnedFd> {
    let sock = connect(nat.addr, nat.port).ok()?;
    let mut pfd = libc::pollfd { fd: sock.as_raw_fd(), events: libc::POLLOUT, revents: 0 };
    // SAFETY: one valid pollfd.
    if unsafe { libc::poll(&mut pfd, 1, NAT_CONNECT_MS) } != 1 {
        return None;
    }
    let mut err: libc::c_int = 0;
    let mut len = std::mem::size_of::<libc::c_int>() as libc::socklen_t;
    // SAFETY: SO_ERROR fills an int of the stated size.
    if unsafe { libc::getsockopt(sock.as_raw_fd(), libc::SOL_SOCKET, libc::SO_ERROR, (&mut err as *mut libc::c_int).cast(), &mut len) } != 0 || err != 0 {
        return None;
    }
    let mut header = [0u8; 23];
    header[..16].copy_from_slice(&nat.token);
    header[16] = kind;
    header[17..].copy_from_slice(&target);
    // SAFETY: a 23-byte write to a just-connected stream; the socket buffer is empty.
    if unsafe { libc::write(sock.as_raw_fd(), header.as_ptr().cast(), header.len()) } != header.len() as isize {
        return None;
    }
    Some(sock)
}

/// A published-port leg: the Mac hands it the next client connection by
/// opening a vsock stream to `PORT` with the header `0.0.0.0` and the leg's
/// id, then sending the container's `ip[4] port[2]` on the leg. The
/// container's bytes go back on the leg, framed as on `FRAMED_PORT`: TCP
/// over the NAT network carries them several times faster than vsock does
/// from the guest to the Mac, while vsock carries the Mac's bytes to the
/// guest faster than the NAT network.
pub fn dial_leg(nat: &NatRelay, id: u16) -> Option<Relay> {
    let [hi, lo] = id.to_be_bytes();
    let host = dial_nat(nat, NAT_PUBLISHED_LEG, [hi, lo, 0, 0, 0, 0])?;
    Some(Relay { host, target: None, connected: false, header: Vec::with_capacity(6), up: Pipe::new(), down: Pipe::new(), dead: false, udp: false, framed: true, refusing: false, leg: true, leg_id: id, up_src: None, attach: None })
}

pub fn accept_host_bound(listener: &OwnedFd, host_addr: [u8; 4], nat: Option<&NatRelay>, build_mirror_port: Option<std::num::NonZeroU16>) -> Option<Relay> {
    // SAFETY: accept4 on a listening socket we own; the fd is owned immediately.
    let fd = unsafe { libc::accept4(listener.as_raw_fd(), std::ptr::null_mut(), std::ptr::null_mut(), libc::SOCK_NONBLOCK | libc::SOCK_CLOEXEC) };
    if fd < 0 {
        return None;
    }
    // SAFETY: `fd` is a fresh descriptor that nothing else owns.
    let client = unsafe { OwnedFd::from_raw_fd(fd) };
    // SAFETY: SO_ORIGINAL_DST fills a sockaddr_in with the pre-redirect destination.
    let port = unsafe {
        let mut dst: libc::sockaddr_in = std::mem::zeroed();
        let mut len = std::mem::size_of::<libc::sockaddr_in>() as u32;
        const SO_ORIGINAL_DST: libc::c_int = 80;
        if libc::getsockopt(client.as_raw_fd(), libc::SOL_IP, SO_ORIGINAL_DST, (&mut dst as *mut libc::sockaddr_in).cast(), &mut len) != 0 {
            return Some(Relay::dead_one(client));
        }
        if dst.sin_addr.s_addr != u32::from_ne_bytes(host_addr) {
            return Some(Relay::dead_one(client));
        }
        u16::from_be(dst.sin_port)
    };
    let mut target = [127, 0, 0, 1, 0, 0];
    target[4..].copy_from_slice(&port.to_be_bytes());
    let vsock = build_mirror_port.is_some_and(|mirror| mirror.get() == port)
        .then(|| super::transport::dial_within(HOST_FRAMED_VSOCK_PORT, MIRROR_VSOCK_CONNECT));
    if !matches!(vsock, Some(Ok(_)))
        && let Some(host) = nat.and_then(|nat| dial_nat(nat, NAT_HOST_BOUND, target)) {
        return Some(Relay { host, target: Some(client), connected: true, header: Vec::new(), up: Pipe::copied_only(), down: Pipe::new(), dead: false, udp: false, framed: false, refusing: false, leg: false, leg_id: 0, up_src: None, attach: None });
    }
    let Ok(host) = vsock.unwrap_or_else(|| dial_host(HOST_FRAMED_VSOCK_PORT)) else { return Some(Relay::dead_one(client)) };
    // The Mac connects to its own loopback: services bound to 127.0.0.1 work.
    let mut header = [127, 0, 0, 1, 0, 0];
    header[4..].copy_from_slice(&port.to_be_bytes());
    // SAFETY: a 6-byte write to a just-connected stream; the socket buffer is empty.
    if unsafe { libc::write(host.as_raw_fd(), header.as_ptr().cast(), 6) } != 6 {
        return Some(Relay::dead_one(client));
    }
    if sys::set_nonblocking(host.as_raw_fd()).is_err() {
        return Some(Relay::dead_one(client));
    }
    Some(Relay {
        host,
        target: Some(client),
        connected: true,
        header: Vec::new(),
        up: Pipe::new(),
        down: Pipe::new(),
        dead: false,
        udp: false,
        framed: true,
        refusing: false,
        leg: false,
        leg_id: 0,
        up_src: None,
        attach: None,
    })
}

fn dial_host(port: u32) -> io::Result<OwnedFd> {
    super::transport::dial(port)
}

impl Relay {
    /// A relay that only exists to close `fd` on the next sweep.
    fn dead_one(fd: OwnedFd) -> Relay {
        Relay { host: fd, target: None, connected: false, header: Vec::new(), up: Pipe::new(), down: Pipe::new(), dead: true, udp: false, framed: false, refusing: false, leg: false, leg_id: 0, up_src: None, attach: None }
    }
}

/// SSH agent forwarding: containers that mount this socket reach the Mac's
/// SSH agent. Each connection is relayed over vsock; keys never leave the Mac.
pub const SSH_AGENT_SOCK: &str = "/run/host-services/ssh-auth.sock";
pub const SSH_VSOCK_PORT: u32 = 1027;

pub fn listen_ssh_agent() -> io::Result<OwnedFd> {
    std::fs::create_dir_all("/run/host-services")?;
    let _ = std::fs::remove_file(SSH_AGENT_SOCK);
    // SAFETY: plain unix socket setup; the fd is owned immediately.
    unsafe {
        // The socket below is 0777 for any user in a container. On a Linux
        // host this directory is the host's own, so only root, which
        // bind-mounts the socket into containers, may reach it by path.
        let dir = std::ffi::CString::new("/run/host-services").expect("no NUL");
        sys::check(libc::chmod(dir.as_ptr(), 0o700) as _, "chmod /run/host-services")?;
        let fd = sys::check(libc::socket(libc::AF_UNIX, libc::SOCK_STREAM | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK, 0) as _, "socket")?;
        let sock = OwnedFd::from_raw_fd(fd as RawFd);
        let mut a: libc::sockaddr_un = std::mem::zeroed();
        a.sun_family = libc::AF_UNIX as libc::sa_family_t;
        for (d, s) in a.sun_path.iter_mut().zip(SSH_AGENT_SOCK.bytes()) {
            *d = s as libc::c_char;
        }
        sys::check(libc::bind(sock.as_raw_fd(), (&a as *const libc::sockaddr_un).cast(), std::mem::size_of::<libc::sockaddr_un>() as u32) as _, "bind")?;
        // Any user in a container may use it, as with Docker Desktop.
        let path = std::ffi::CString::new(SSH_AGENT_SOCK).expect("no NUL");
        libc::chmod(path.as_ptr(), 0o777);
        sys::check(libc::listen(sock.as_raw_fd(), 64) as _, "listen")?;
        Ok(sock)
    }
}

pub fn accept_ssh_agent(listener: &OwnedFd) -> Option<Relay> {
    // SAFETY: accept4 on a listening socket we own; the fd is owned immediately.
    let fd = unsafe { libc::accept4(listener.as_raw_fd(), std::ptr::null_mut(), std::ptr::null_mut(), libc::SOCK_NONBLOCK | libc::SOCK_CLOEXEC) };
    if fd < 0 {
        return None;
    }
    // SAFETY: fresh descriptor.
    let client = unsafe { OwnedFd::from_raw_fd(fd) };
    let Ok(host) = dial_host(SSH_VSOCK_PORT) else { return Some(Relay::dead_one(client)) };
    if sys::set_nonblocking(host.as_raw_fd()).is_err() {
        return Some(Relay::dead_one(client));
    }
    Some(Relay { host, target: Some(client), connected: true, header: Vec::new(), up: Pipe::new(), down: Pipe::new(), dead: false, udp: false, framed: false, refusing: false, leg: false, leg_id: 0, up_src: None, attach: None })
}

/// The engine's own API, for containers that mount the docker socket
/// (Testcontainers' Ryuk, CI runners): crates/ctrs/src/daemon/binds.rs
/// mounts this socket for `/var/run/docker.sock`, and each connection is
/// relayed over vsock to the daemon on the Mac. In the VM only: on a Linux
/// host containers mount the daemon's socket itself.
pub const ENGINE_SOCK: &str = "/run/host-services/docker.sock";
pub const ENGINE_VSOCK_PORT: u32 = 1036;

pub fn listen_engine() -> io::Result<OwnedFd> {
    std::fs::create_dir_all("/run/host-services")?;
    let _ = std::fs::remove_file(ENGINE_SOCK);
    // SAFETY: plain unix socket setup; the fd is owned immediately.
    unsafe {
        let fd = sys::check(libc::socket(libc::AF_UNIX, libc::SOCK_STREAM | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK, 0) as _, "socket")?;
        let sock = OwnedFd::from_raw_fd(fd as RawFd);
        let mut a: libc::sockaddr_un = std::mem::zeroed();
        a.sun_family = libc::AF_UNIX as libc::sa_family_t;
        for (d, s) in a.sun_path.iter_mut().zip(ENGINE_SOCK.bytes()) {
            *d = s as libc::c_char;
        }
        sys::check(libc::bind(sock.as_raw_fd(), (&a as *const libc::sockaddr_un).cast(), std::mem::size_of::<libc::sockaddr_un>() as u32) as _, "bind")?;
        // root in a container that was given it, as Docker's root:docker 0660.
        let path = std::ffi::CString::new(ENGINE_SOCK).expect("no NUL");
        libc::chmod(path.as_ptr(), 0o660);
        sys::check(libc::listen(sock.as_raw_fd(), 64) as _, "listen")?;
        Ok(sock)
    }
}

pub fn accept_engine(listener: &OwnedFd) -> Option<Relay> {
    // SAFETY: accept4 on a listening socket we own; the fd is owned immediately.
    let fd = unsafe { libc::accept4(listener.as_raw_fd(), std::ptr::null_mut(), std::ptr::null_mut(), libc::SOCK_NONBLOCK | libc::SOCK_CLOEXEC) };
    if fd < 0 {
        return None;
    }
    // SAFETY: fresh descriptor.
    let client = unsafe { OwnedFd::from_raw_fd(fd) };
    let Ok(host) = dial_host(ENGINE_VSOCK_PORT) else { return Some(Relay::dead_one(client)) };
    if sys::set_nonblocking(host.as_raw_fd()).is_err() {
        return Some(Relay::dead_one(client));
    }
    Some(Relay { host, target: Some(client), connected: true, header: Vec::new(), up: Pipe::new(), down: Pipe::new(), dead: false, udp: false, framed: false, refusing: false, leg: false, leg_id: 0, up_src: None, attach: None })
}

#[cfg(test)]
mod tests {
    use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};

    #[test]
    fn framed_reads_carry_their_length_and_end_with_an_empty_frame() {
        let mut fds = [0; 2];
        // SAFETY: `fds` has room for the two descriptors pipe writes.
        assert_eq!(unsafe { libc::pipe(fds.as_mut_ptr()) }, 0);
        // SAFETY: pipe succeeded, so both are fresh and ours.
        let (r, w) = unsafe { (OwnedFd::from_raw_fd(fds[0]), OwnedFd::from_raw_fd(fds[1])) };
        // SAFETY: writing a local buffer to a pipe we own.
        assert_eq!(unsafe { libc::write(w.as_raw_fd(), b"abc".as_ptr().cast(), 3) }, 3);
        drop(w);
        let mut buf = Vec::new();
        assert_eq!(super::read_frame_into(r.as_raw_fd(), &mut buf, super::BUF).unwrap(), 3);
        assert_eq!(super::read_frame_into(r.as_raw_fd(), &mut buf, super::BUF).unwrap(), 0);
        assert_eq!(buf, [0, 0, 0, 3, b'a', b'b', b'c', 0, 0, 0, 0]);
        // No room for a frame: not read, and not taken for EOF.
        let full = buf.len() + 4;
        assert_eq!(super::read_frame_into(r.as_raw_fd(), &mut buf, full).unwrap(), 1);
    }

    fn pair() -> (OwnedFd, OwnedFd) {
        let mut fds = [0; 2];
        // SAFETY: `fds` has room for the two descriptors socketpair writes.
        assert_eq!(unsafe { libc::socketpair(libc::AF_UNIX, libc::SOCK_STREAM | libc::SOCK_NONBLOCK, 0, fds.as_mut_ptr()) }, 0);
        // SAFETY: socketpair succeeded, so both are fresh and ours.
        unsafe { (OwnedFd::from_raw_fd(fds[0]), OwnedFd::from_raw_fd(fds[1])) }
    }

    /// Pumps `len` patterned bytes from one socket pair to another and
    /// returns what came out, and whether the direction moved to splice.
    fn relay_bytes(len: usize, framed: bool) -> (Vec<u8>, Vec<u8>, bool) {
        use std::io::{Read, Write};
        let (src_far, src) = pair();
        let (dst, dst_far) = pair();
        let sent: Vec<u8> = (0..len).map(|i| (i * 31 % 251) as u8).collect();
        let input = sent.clone();
        let writer = std::thread::spawn(move || {
            // SAFETY: the thread owns this end; blocking writes are what it wants.
            unsafe { libc::fcntl(src_far.as_raw_fd(), libc::F_SETFL, 0) };
            let mut f = std::fs::File::from(src_far);
            f.write_all(&input).unwrap();
        });
        let reader = std::thread::spawn(move || {
            // SAFETY: as above.
            unsafe { libc::fcntl(dst_far.as_raw_fd(), libc::F_SETFL, 0) };
            let mut out = Vec::new();
            std::fs::File::from(dst_far).read_to_end(&mut out).unwrap();
            out
        });
        let mut pipe = super::Pipe::new();
        let mut spliced = false;
        while !pipe.shut {
            let mut fds = [
                libc::pollfd { fd: src.as_raw_fd(), events: if pipe.wants_input(framed) { libc::POLLIN } else { 0 }, revents: 0 },
                libc::pollfd { fd: dst.as_raw_fd(), events: if pipe.has_output() { libc::POLLOUT } else { 0 }, revents: 0 },
            ];
            // SAFETY: a valid pollfd array.
            unsafe { libc::poll(fds.as_mut_ptr(), 2, 1000) };
            super::pump(src.as_raw_fd(), dst.as_raw_fd(), &mut pipe, framed).unwrap();
            spliced |= pipe.kernel.is_some();
        }
        writer.join().unwrap();
        drop(dst);
        (sent, reader.join().unwrap(), spliced)
    }

    #[test]
    fn bulk_bytes_move_through_splice_unchanged() {
        let (sent, got, spliced) = relay_bytes(5 << 20, false);
        assert!(spliced);
        assert!(got == sent, "{} bytes out of {}", got.len(), sent.len());
    }

    #[test]
    fn spliced_frames_carry_their_length_and_end_with_an_empty_frame() {
        let (sent, got, spliced) = relay_bytes(5 << 20, true);
        assert!(spliced);
        let mut payload = Vec::new();
        let mut rest = &got[..];
        loop {
            let len = u32::from_be_bytes(rest[..4].try_into().unwrap()) as usize;
            rest = &rest[4..];
            if len == 0 {
                break;
            }
            payload.extend_from_slice(&rest[..len]);
            rest = &rest[len..];
        }
        assert!(rest.is_empty(), "{} bytes after the end frame", rest.len());
        assert!(payload == sent, "{} payload bytes out of {}", payload.len(), sent.len());
    }

    #[test]
    fn a_short_connection_never_opens_a_pipe() {
        let (sent, got, spliced) = relay_bytes(64 * 1024, false);
        assert!(!spliced);
        assert!(got == sent);
    }

    #[test]
    fn a_pending_connect_leaves_poll_asleep_while_the_client_has_sent() {
        let mut host = [0; 2];
        // SAFETY: `host` has room for the two descriptors socketpair writes.
        assert_eq!(unsafe { libc::socketpair(libc::AF_UNIX, libc::SOCK_STREAM | libc::SOCK_NONBLOCK, 0, host.as_mut_ptr()) }, 0);
        // SAFETY: socketpair succeeded, so both are fresh and ours.
        let (near, far) = unsafe { (OwnedFd::from_raw_fd(host[0]), OwnedFd::from_raw_fd(host[1])) };
        // SAFETY: writing a local buffer to a socket we own.
        assert_eq!(unsafe { libc::write(far.as_raw_fd(), b"GET".as_ptr().cast(), 3) }, 3);
        // A connect the container has not answered: a socket that never becomes writable here.
        let mut target = [0; 2];
        // SAFETY: as above.
        assert_eq!(unsafe { libc::pipe2(target.as_mut_ptr(), libc::O_NONBLOCK) }, 0);
        // SAFETY: pipe2 succeeded; the read end is never writable.
        let (pending, _w) = unsafe { (OwnedFd::from_raw_fd(target[0]), OwnedFd::from_raw_fd(target[1])) };
        let mut relay = super::Relay { target: Some(pending), connected: false, header: vec![0; 6], ..super::Relay::dead_one(near) };
        relay.dead = false;
        let mut fds = Vec::new();
        relay.interest(&mut fds);
        // SAFETY: `fds` is a valid pollfd array of the given length.
        assert_eq!(unsafe { libc::poll(fds.as_mut_ptr(), fds.len() as libc::nfds_t, 0) }, 0, "{:?}", fds.iter().map(|p| p.events).collect::<Vec<_>>());
        relay.connected = true;
        fds.clear();
        relay.interest(&mut fds);
        assert_ne!(fds[0].events & libc::POLLIN, 0);
    }
}
