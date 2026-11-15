//! The docker driver's BuildKit endpoints (docs/buildkit-driver.md).
//!
//! `docker buildx build` picks its `docker` driver when the engine
//! answers the `/grpc` hijack with h2c to BuildKit's gRPC, plus a
//! hijacked `/session` carrying the build's session (context, secrets,
//! auth) as a byte splice through BuildKit's `Control.Session` RPC.
//!
//! `/grpc` terminates HTTP/2 on both hops: buildx on one side, the
//! managed builder's buildkitd (`--addr tcp://0.0.0.0:1234`) on the
//! other. HPACK header blocks are relayed verbatim — each connection's
//! dynamic table sees the same block sequence, so indexed references
//! stay valid. The one mutation is the default `--load` export: a
//! `SolveRequest` whose only exporter is `type=docker`/`type=image`
//! without `push` is rewritten to push the image to the local mirror,
//! which ingests it straight into ctrs's store; retagging happens when
//! the solve's trailers arrive. Every other exporter form (push, tar,
//! local, multi-entry, attestations) passes through untouched.
//!
//! `/session` is a byte-level proxy: buildkitd's session manager is an
//! HTTP hijack endpoint keyed on the `X-Docker-Expose-Session-*`
//! headers, so the client's request head is forwarded verbatim and the
//! h2 bytes are spliced raw in both directions.
//!
//! Flow control: both hops advertise a 1 GiB stream window and a
//! 1 GiB connection window up front, so no WINDOW_UPDATE traffic is
//! generated for realistic build control messages; sends still wait on
//! the peer's advertised windows.

use std::collections::{HashMap, HashSet};
use std::io::{self, BufReader, Read, Write};
use std::net::Shutdown;
use std::os::unix::net::UnixStream;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex};

use super::engine::Engine;
use super::http::{self, DynBufRead};

/// buildkitd's TCP listener inside the managed builder container.
pub const BUILDKIT_TCP_PORT: u16 = 1234;

const H2_PREFACE: &[u8] = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n";
const H2_MAX_FRAME: usize = 1 << 22;
/// Advertised per-stream and per-conn receive windows (1 GiB).
const BIG_WINDOW: u32 = 1 << 30;
/// Outgoing frames are chunked to the spec minimum max-frame size,
/// which every peer must accept.
const OUT_FRAME: usize = 16 * 1024;

const F_DATA: u8 = 0;
const F_HEADERS: u8 = 1;
const F_RST: u8 = 3;
const F_SETTINGS: u8 = 4;
const F_PING: u8 = 6;
const F_GOAWAY: u8 = 7;
const F_WINDOW_UPDATE: u8 = 8;
const F_CONTINUATION: u8 = 9;

const FL_END_STREAM: u8 = 0x1;
const FL_ACK: u8 = 0x1;
const FL_END_HEADERS: u8 = 0x4;
const FL_PADDED: u8 = 0x8;
const FL_PRIORITY: u8 = 0x20;

const S_INITIAL_WINDOW_SIZE: u16 = 4;

fn io_err(msg: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, msg.into())
}

fn sid_of(h: &[u8; 9]) -> u32 {
    u32::from_be_bytes([h[5], h[6], h[7], h[8]]) & 0x7fff_ffff
}

fn frame_header(len: usize, ftype: u8, flags: u8, sid: u32) -> [u8; 9] {
    let l = len as u32;
    [
        (l >> 16) as u8,
        (l >> 8) as u8,
        l as u8,
        ftype,
        flags,
        ((sid >> 24) & 0x7f) as u8,
        (sid >> 16) as u8,
        (sid >> 8) as u8,
        sid as u8,
    ]
}

/// The upgrade handshake plus the builder dial, shared by both
/// endpoints. The 101 goes out only once buildkitd is reachable, so a
/// dead builder fails the dial as an HTTP error rather than a hung h2
/// connection.
pub fn serve(engine: &Arc<Engine>, req: &http::Request, path: &str, w: &mut UnixStream, r: &mut dyn DynBufRead) -> io::Result<()> {
    crate::diag::info!("build endpoint", path = path);
    // Anything the peer sent behind the request head is already in the
    // BufReader; hand it to the h2 side first.
    let concrete = r
        .as_any_mut()
        .downcast_mut::<BufReader<UnixStream>>()
        .ok_or_else(|| io_err("build endpoints need the socket"))?;
    let early = concrete.buffer().to_vec();
    let sock = concrete.get_ref().try_clone()?;
    let backend = match dial_builder(engine) {
        Ok(b) => b,
        Err(e) => {
            crate::diag::warn!("build endpoint dial failed", path = path, error = format!("{e}"));
            let _ = http::respond_with(w, 500, "text/plain; charset=utf-8", "", format!("ctrs: {e}\n").as_bytes());
            return Ok(());
        }
    };
    w.write_all(b"HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: h2c\r\n\r\n")?;
    w.flush()?;
    match path {
        "/grpc" => grpc(engine, early, sock, backend),
        _ => session(req, early, sock, backend),
    }
}

/// The builder's buildkitd TCP port, reached through the guest relay
/// at the builder container's bridge address.
fn dial_builder(engine: &Arc<Engine>) -> io::Result<UnixStream> {
    let id = super::builder::ensure_for_driver(engine).map_err(|e| io_err(format!("ensure: {e:?}")))?;
    let ip = engine
        .with(&id, |c| c.ip)
        .map_err(|e| io_err(format!("lookup: {e:?}")))?
        .ok_or_else(|| io_err("the builder has no address"))?;
    let vm = engine.vm()?;
    let conn = super::ports::open_relay(&vm, ip, BUILDKIT_TCP_PORT).map_err(|e| io_err(format!("relay {ip:?}:{BUILDKIT_TCP_PORT}: {e}")))?;
    Ok(UnixStream::from(conn.fd.try_clone()?))
}

// --- framing ---------------------------------------------------------------

struct Frame {
    ftype: u8,
    flags: u8,
    sid: u32,
    payload: Vec<u8>,
}

/// An h2 frame source: `early` bytes already read past the HTTP head,
/// then the socket.
struct FrameReader<R: Read> {
    s: R,
    pending: Vec<u8>,
}

impl<R: Read> FrameReader<R> {
    fn new(s: R, early: Vec<u8>) -> Self {
        FrameReader { s, pending: early }
    }

    fn fill(&mut self, n: usize) -> io::Result<bool> {
        while self.pending.len() < n {
            let mut tmp = [0u8; 16384];
            match self.s.read(&mut tmp) {
                Ok(0) => return Ok(false),
                Ok(m) => self.pending.extend_from_slice(&tmp[..m]),
                Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
                Err(e) => return Err(e),
            }
        }
        Ok(true)
    }

    fn take(&mut self, n: usize) -> io::Result<Vec<u8>> {
        if !self.fill(n)? {
            return Err(io_err("eof mid-frame"));
        }
        Ok(self.pending.drain(..n).collect())
    }

    /// Consumes the client connection preface when present (h2c
    /// upgrade may skip it and start with SETTINGS).
    fn preface(&mut self) -> io::Result<()> {
        if !self.fill(9)? {
            return Err(io_err("eof before the connection preface"));
        }
        if &self.pending[..9] == b"PRI * HTT" {
            let got = self.take(24)?;
            if got != H2_PREFACE {
                return Err(io_err("bad client preface"));
            }
        }
        Ok(())
    }

    fn frame(&mut self) -> io::Result<Option<Frame>> {
        match self.fill(9) {
            Ok(true) => {}
            Ok(false) => {
                return if self.pending.is_empty() {
                    Ok(None)
                } else {
                    Err(io_err("partial frame header"))
                };
            }
            Err(e) => return Err(e),
        }
        let h: [u8; 9] = self.pending[..9].try_into().expect("9 bytes");
        let len = ((h[0] as usize) << 16) | ((h[1] as usize) << 8) | h[2] as usize;
        if len > H2_MAX_FRAME {
            return Err(io_err("http2 frame too large"));
        }
        let mut all = self.take(9 + len)?;
        let payload = all.split_off(9);
        Ok(Some(Frame { ftype: h[3], flags: h[4], sid: sid_of(&h), payload }))
    }
}

// --- flow control ----------------------------------------------------------

/// Send-window accounting for one direction of one hop, fed by the
/// peer's SETTINGS and WINDOW_UPDATE frames.
struct Win {
    m: Mutex<(u64, u64, HashMap<u32, u64>)>, // conn, default stream, per-stream
    cv: Condvar,
}

impl Win {
    fn new() -> Self {
        Win { m: Mutex::new((65535, 65535, HashMap::new())), cv: Condvar::new() }
    }

    /// The peer's SETTINGS_INITIAL_WINDOW_SIZE sizes new streams.
    fn settings(&self, initial: u32) {
        let mut w = self.m.lock().unwrap_or_else(|e| e.into_inner());
        w.1 = initial as u64;
        w.2.clear();
        self.cv.notify_all();
    }

    fn update(&self, sid: u32, inc: u32) {
        let mut w = self.m.lock().unwrap_or_else(|e| e.into_inner());
        if sid == 0 {
            w.0 = w.0.saturating_add(inc as u64);
        } else {
            let cur = w.2.get(&sid).copied().unwrap_or(w.1);
            w.2.insert(sid, cur.saturating_add(inc as u64));
        }
        self.cv.notify_all();
    }

    fn wait(&self, sid: u32, len: usize) {
        let need = len as u64;
        let mut w = self.m.lock().unwrap_or_else(|e| e.into_inner());
        loop {
            let dflt = w.1;
            let sw = *w.2.entry(sid).or_insert(dflt);
            if w.0 >= need && sw >= need {
                return;
            }
            w = self.cv.wait(w).unwrap_or_else(|e| e.into_inner());
        }
    }

    fn take(&self, sid: u32, len: usize) {
        let mut w = self.m.lock().unwrap_or_else(|e| e.into_inner());
        if w.0 < len as u64 || w.2.get(&sid).copied().unwrap_or(w.1) < len as u64 {
            crate::diag::warn!(
                "flow window overdraw",
                sid = sid,
                len = len,
                conn = w.0,
                stream = w.2.get(&sid).copied().unwrap_or(w.1),
                default = w.1
            );
        }
        w.0 = w.0.saturating_sub(len as u64);
        let d = w.1;
        if let Some(s) = w.2.get_mut(&sid) {
            *s = s.saturating_sub(len as u64);
        } else {
            w.2.insert(sid, d.saturating_sub(len as u64));
        }
    }

    fn close(&self, sid: u32) {
        self.m.lock().unwrap_or_else(|e| e.into_inner()).2.remove(&sid);
    }
}

/// One side of an h2 hop: the socket (as a File, writable through a
/// shared ref) plus the write lock both relay directions share.
struct Endpoint {
    f: std::fs::File,
    lock: Mutex<()>,
}

impl Endpoint {
    fn new(s: UnixStream) -> Self {
        Endpoint { f: std::fs::File::from(std::os::fd::OwnedFd::from(s)), lock: Mutex::new(()) }
    }

    fn frame(&self, ftype: u8, flags: u8, sid: u32, payload: &[u8]) -> io::Result<()> {
        let _g = self.lock.lock().unwrap_or_else(|e| e.into_inner());
        let mut f = &self.f;
        f.write_all(&frame_header(payload.len(), ftype, flags, sid))?;
        f.write_all(payload)?;
        f.flush()
    }

    fn raw(&self, bytes: &[u8]) -> io::Result<()> {
        let _g = self.lock.lock().unwrap_or_else(|e| e.into_inner());
        let mut f = &self.f;
        f.write_all(bytes)?;
        f.flush()
    }

    fn shutdown(&self) {
        // SAFETY: f is a valid socket fd for the life of self.
        unsafe { libc::shutdown(std::os::fd::AsRawFd::as_raw_fd(&self.f), libc::SHUT_RDWR) };
    }
}

fn settings_frame(initial_window: u32) -> Vec<u8> {
    // One setting: INITIAL_WINDOW_SIZE.
    let mut p = Vec::with_capacity(6);
    p.extend_from_slice(&S_INITIAL_WINDOW_SIZE.to_be_bytes());
    p.extend_from_slice(&initial_window.to_be_bytes());
    let mut f = frame_header(p.len(), F_SETTINGS, 0, 0).to_vec();
    f.extend_from_slice(&p);
    f
}

fn ack_frame(ftype: u8) -> Vec<u8> {
    frame_header(0, ftype, FL_ACK, 0).to_vec()
}

fn window_update_frame(sid: u32, inc: u32) -> Vec<u8> {
    let p = (inc & 0x7fff_ffff).to_be_bytes();
    let mut f = frame_header(4, F_WINDOW_UPDATE, 0, sid).to_vec();
    f.extend_from_slice(&p);
    f
}

// --- payload normalization ---------------------------------------------------

/// Strips PADDED and PRIORITY from a HEADERS/DATA payload, returning
/// the bare bytes and the flags that survive. Priority's dependency
/// stream id would not exist on the other hop.
fn strip_flags(payload: &[u8], flags: u8) -> (Vec<u8>, u8) {
    let mut keep = flags & !(FL_PADDED | FL_PRIORITY);
    let mut start = 0;
    let mut end = payload.len();
    if flags & FL_PADDED != 0 {
        if payload.is_empty() {
            return (Vec::new(), keep);
        }
        let pad = payload[0] as usize;
        end = end.saturating_sub(pad);
        start += 1;
        if flags & FL_PRIORITY != 0 {
            start += 4;
        }
    } else if flags & FL_PRIORITY != 0 {
        start += 4;
    }
    if flags & FL_PADDED != 0 || flags & FL_PRIORITY != 0 {
        keep &= !(FL_PADDED | FL_PRIORITY);
    }
    if start >= end || end > payload.len() {
        return (Vec::new(), keep);
    }
    (payload[start..end].to_vec(), keep)
}

// --- emit helpers ------------------------------------------------------------

/// Writes `block` as HEADERS/CONTINUATION frames of ≤ OUT_FRAME on
/// `ep`/`sid`, preserving END_STREAM and END_HEADERS placement.
fn send_head(ep: &Endpoint, win: &Win, sid: u32, first: u8, block: &[u8], end_stream: bool, end_headers: bool) -> io::Result<()> {
    let mut off = 0;
    let mut first_frame = true;
    loop {
        let n = (block.len() - off).min(OUT_FRAME);
        let last = off + n == block.len();
        let ftype = if first_frame { first } else { F_CONTINUATION };
        let mut flags = 0;
        if last && end_headers {
            flags |= FL_END_HEADERS;
        }
        if first_frame && end_stream {
            flags |= FL_END_STREAM;
        }
        win.wait(sid, n);
        ep.frame(ftype, flags, sid, &block[off..off + n])?;
        win.take(sid, n);
        off += n;
        first_frame = false;
        if last {
            break;
        }
    }
    Ok(())
}

/// Writes `payload` as DATA frames of ≤ OUT_FRAME on `ep`/`sid`,
/// waiting on `win`; END_STREAM rides the last frame.
fn send_data(ep: &Endpoint, win: &Win, sid: u32, payload: &[u8], end: bool) -> io::Result<()> {
    let mut off = 0;
    loop {
        let n = (payload.len() - off).min(OUT_FRAME);
        let last = off + n == payload.len();
        if n == 0 && !end {
            break;
        }
        let flags = if last && end { FL_END_STREAM } else { 0 };
        win.wait(sid, n);
        ep.frame(F_DATA, flags, sid, &payload[off..off + n])?;
        win.take(sid, n);
        off += n;
        if last {
            break;
        }
    }
    Ok(())
}

// --- sid maps -----------------------------------------------------------------

#[derive(Default)]
struct Sids {
    /// client stream id → builder stream id.
    c2b: HashMap<u32, u32>,
    /// builder stream id → client stream id.
    b2c: HashMap<u32, u32>,
    /// next odd builder stream id we assign (we are the h2 client).
    next_b: u32,
    /// client streams we've already ended (for cleanup only).
    dead_c: HashSet<u32>,
}

impl Sids {
    fn new() -> Self {
        Sids { next_b: 1, ..Default::default() }
    }

    fn open_b(&mut self, c: u32) -> u32 {
        if let Some(&b) = self.c2b.get(&c) {
            return b;
        }
        let b = self.next_b;
        self.next_b += 2;
        self.c2b.insert(c, b);
        self.b2c.insert(b, c);
        b
    }

    fn c_of(&self, b: u32) -> Option<u32> {
        self.b2c.get(&b).copied()
    }

    fn close(&mut self, c: u32, b: u32) {
        self.c2b.remove(&c);
        self.b2c.remove(&b);
        self.dead_c.insert(c);
    }
}

// --- SolveRequest rewrite -----------------------------------------------------

/// Exporter attr keys a default `--load` may carry that survive the
/// rewrite to a mirror push. Anything else fails closed to the plain
/// proxy path.
const CARRY_ATTRS: &[&str] = &["oci-mediatypes", "compression", "compression-level", "force-compression", "rewrite-timestamp"];

fn varint(msg: &[u8], i: &mut usize) -> Option<u64> {
    let mut v = 0u64;
    let mut shift = 0u32;
    loop {
        let b = *msg.get(*i)?;
        *i += 1;
        v |= ((b & 0x7f) as u64) << shift;
        if b & 0x80 == 0 {
            return Some(v);
        }
        shift += 7;
        if shift > 63 {
            return None;
        }
    }
}

fn put_varint(out: &mut Vec<u8>, mut v: u64) {
    loop {
        let b = (v & 0x7f) as u8;
        v >>= 7;
        if v == 0 {
            out.push(b);
            return;
        }
        out.push(b | 0x80);
    }
}

fn put_key(out: &mut Vec<u8>, field: u32, wire: u8) {
    put_varint(out, ((field as u64) << 3) | wire as u64);
}

fn put_bytes(out: &mut Vec<u8>, field: u32, bytes: &[u8]) {
    put_key(out, field, 2);
    put_varint(out, bytes.len() as u64);
    out.extend_from_slice(bytes);
}

/// A field's absolute span within the message: `start..end` covers
/// key + length + content; `content` covers just the value bytes.
struct Field {
    field: u32,
    wire: u8,
    start: usize,
    end: usize,
    content: (usize, usize),
}

fn parse_fields(msg: &[u8]) -> Option<Vec<Field>> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < msg.len() {
        let start = i;
        let key = varint(msg, &mut i)?;
        let field = (key >> 3) as u32;
        let wire = (key & 7) as u8;
        let content_start;
        match wire {
            0 => {
                content_start = i;
                varint(msg, &mut i)?;
            }
            1 => {
                content_start = i;
                i = i.checked_add(8)?;
            }
            2 => {
                let l = varint(msg, &mut i)? as usize;
                content_start = i;
                i = i.checked_add(l)?;
            }
            5 => {
                content_start = i;
                i = i.checked_add(4)?;
            }
            _ => return None,
        }
        if i > msg.len() {
            return None;
        }
        out.push(Field { field, wire, start, end: i, content: (content_start, i) });
    }
    Some(out)
}

/// A string map entry message: {1: key, 2: value}.
fn parse_map_entry(msg: &[u8]) -> Option<(String, String)> {
    let fields = parse_fields(msg)?;
    let mut k = None;
    let mut v = None;
    for f in fields {
        if f.wire != 2 {
            return None;
        }
        let s = std::str::from_utf8(&msg[f.content.0..f.content.1]).ok()?;
        match f.field {
            1 => k = Some(s.to_owned()),
            2 => v = Some(s.to_owned()),
            _ => {}
        }
    }
    Some((k?, v?))
}

/// The `Exporter` message: Type=1, Attrs=2 (repeated map entries).
fn parse_exporter(msg: &[u8]) -> Option<(String, Vec<(String, String)>)> {
    let fields = parse_fields(msg)?;
    let mut ty = None;
    let mut attrs = Vec::new();
    for f in fields {
        if f.wire != 2 {
            return None;
        }
        let bytes = &msg[f.content.0..f.content.1];
        match f.field {
            1 => ty = Some(std::str::from_utf8(bytes).ok()?.to_owned()),
            2 => attrs.push(parse_map_entry(bytes)?),
            _ => return None,
        }
    }
    Some((ty?, attrs))
}

/// Rewrites a SolveRequest's default docker/image export into a push
/// to the image mirror. Returns the new message plus the mirror repo
/// and the tags to restore; `None` passes the request through.
fn rewrite_solve(msg: &[u8], engine: &Arc<Engine>) -> Option<(Vec<u8>, String, Vec<String>)> {
    let fields = parse_fields(msg)?;
    crate::diag::debug!(
        "solve request fields",
        fields = format!("{:?}", fields.iter().map(|f| (f.field, f.wire)).collect::<Vec<_>>())
    );
    // Deprecated exporter fields (3, 4) are ignored by buildkitd when
    // `Exporters` (13) is set — which buildx always does — so they are
    // not a reason to skip the rewrite.
    let exporters: Vec<&Field> = fields.iter().filter(|f| f.field == 13 && f.wire == 2).collect();
    if exporters.len() != 1 {
        crate::diag::debug!("solve rewrite skipped", reason = format!("exporters={}", exporters.len()));
        return None;
    }
    let e = exporters[0];
    let Some((etype, attrs)) = parse_exporter(&msg[e.content.0..e.content.1]) else {
        crate::diag::debug!("solve rewrite skipped", reason = "exporter parse failed");
        return None;
    };
    crate::diag::debug!("solve exporter", etype = etype.clone(), attrs = format!("{attrs:?}"));
    // The docker driver rewrites `image` exports to `moby` (buildx
    // build/opt.go); dockerd's builtin exporter name means the same
    // "load into the image store" intent our mirror+retag provides.
    if etype != "docker" && etype != "image" && etype != "moby" {
        return None;
    }
    if etype == "moby" {
        crate::diag::debug!("moby exporter attrs", attrs = format!("{attrs:?}"));
    }
    let get = |k: &str| attrs.iter().find(|(a, _)| a == k).map(|(_, v)| v.as_str());
    if get("push") == Some("true") {
        crate::diag::debug!("solve rewrite skipped", reason = "push=true");
        return None;
    }
    let Some(name) = get("name").filter(|n| !n.is_empty()) else {
        crate::diag::debug!("solve rewrite skipped", reason = "no name attr");
        return None;
    };
    // Fail closed on anything we don't recognize: attestations,
    // platform pins, store selection, unknown knobs.
    for (k, _) in &attrs {
        if k.starts_with("annotation") || !(k == "name" || k == "push" || CARRY_ATTRS.contains(&k.as_str())) {
            crate::diag::debug!("solve rewrite skipped", reason = format!("attr {k}"));
            return None;
        }
    }
    let tags: Vec<String> = name.split(',').map(str::trim).filter(|t| !t.is_empty()).map(str::to_owned).collect();
    if tags.is_empty() {
        return None;
    }
    let repo = super::mirror::push_repo()?;
    let push_ref = super::mirror::push_ref(engine, &repo)?;

    // New Exporter: type=image, name=<push ref>, push=true, plus the
    // harmless carry-over attrs.
    let mut em = Vec::new();
    put_bytes(&mut em, 1, b"image");
    let mut am = Vec::new();
    let put_attr = |k: &str, v: &str, am: &mut Vec<u8>| {
        let mut e = Vec::new();
        put_bytes(&mut e, 1, k.as_bytes());
        put_bytes(&mut e, 2, v.as_bytes());
        put_bytes(am, 2, &e);
    };
    put_attr("name", &push_ref, &mut am);
    put_attr("push", "true", &mut am);
    for k in CARRY_ATTRS {
        if let Some(v) = get(k) {
            put_attr(k, v, &mut am);
        }
    }
    em.extend_from_slice(&am);

    // The exporter field's index within `fields`.
    let ei = fields.iter().position(|f| std::ptr::eq(f, e))?;
    Some((rebuild_solve(msg, &fields, ei, &em)?, repo, tags))
}

/// Rebuilds the message replacing field `ei`'s content with `em`,
/// preserving every other byte.
fn rebuild_solve(msg: &[u8], fields: &[Field], ei: usize, em: &[u8]) -> Option<Vec<u8>> {
    let mut out = Vec::with_capacity(msg.len() + em.len() + 8);
    for (i, f) in fields.iter().enumerate() {
        if i == ei {
            put_key(&mut out, 13, 2);
            put_varint(&mut out, em.len() as u64);
            out.extend_from_slice(em);
        } else {
            out.extend_from_slice(&msg[f.start..f.end]);
        }
    }
    Some(out)
}

// --- /grpc -------------------------------------------------------------------

/// A rewritten solve waiting for its trailers: builder stream id →
/// (mirror repo, tags, engine).
type Pending = Arc<Mutex<HashMap<u32, (String, Vec<String>, Arc<Engine>)>>>;

fn grpc(engine: &Arc<Engine>, early: Vec<u8>, sock: UnixStream, backend: UnixStream) -> io::Result<()> {
    let cli_rd_sock = sock.try_clone()?;
    let be_rd_sock = backend.try_clone()?;
    let cli_ep = Arc::new(Endpoint::new(sock));
    let be_ep = Arc::new(Endpoint::new(backend));

    // Server connection preface on the client hop: SETTINGS with a
    // big stream window, then a conn-level WINDOW_UPDATE.
    cli_ep.raw(&settings_frame(BIG_WINDOW))?;
    cli_ep.raw(&window_update_frame(0, BIG_WINDOW))?;
    // Client connection preface on the builder hop.
    be_ep.raw(H2_PREFACE)?;
    be_ep.raw(&settings_frame(BIG_WINDOW))?;
    be_ep.raw(&window_update_frame(0, BIG_WINDOW))?;

    let cli_send = Arc::new(Win::new());
    let be_send = Arc::new(Win::new());
    let sids = Arc::new(Mutex::new(Sids::new()));
    let pending: Pending = Arc::new(Mutex::new(HashMap::new()));
    let dead = Arc::new(AtomicBool::new(false));

    // client → builder
    let t1 = {
        let be_ep = be_ep.clone();
        let cli_ep = cli_ep.clone();
        let be_send = be_send.clone();
        let cli_send = cli_send.clone();
        let sids = sids.clone();
        let pending = pending.clone();
        let dead = dead.clone();
        let engine = engine.clone();
        std::thread::Builder::new()
            .name("ctrs-h2c-req".into())
            .spawn(move || relay_c2b(FrameReader::new(cli_rd_sock, early), be_ep, cli_ep, be_send, cli_send, sids, pending, engine, dead))
    }?;

    // builder → client (runs on this thread)
    let r = relay_b2c(FrameReader::new(be_rd_sock, Vec::new()), cli_ep.clone(), be_ep.clone(), cli_send, be_send, sids, pending.clone(), engine.clone(), dead.clone());
    let _ = t1.join();
    // Anything still pending never saw trailers: drop its mirror
    // records so a retry starts clean.
    let leftovers: Vec<(u32, (String, Vec<String>, Arc<Engine>))> = pending.lock().unwrap_or_else(|e| e.into_inner()).drain().collect();
    for (_, (repo, _, e)) in leftovers {
        super::builder::discard_pushed(&e, &repo);
    }
    r
}

/// Reads client-conn frames, forwards stream data to buildkitd.
/// `cli_send` is fed by the client's SETTINGS/WINDOW_UPDATE (my send
/// window toward the client); `be_send` is consumed for writes toward
/// buildkitd and fed by the other thread.
#[allow(clippy::too_many_arguments)]
fn relay_c2b<R: Read>(
    rd: FrameReader<R>,
    be_ep: Arc<Endpoint>,
    cli_ep: Arc<Endpoint>,
    be_send: Arc<Win>,
    cli_send: Arc<Win>,
    sids: Arc<Mutex<Sids>>,
    pending: Pending,
    engine: Arc<Engine>,
    dead: Arc<AtomicBool>,
) -> io::Result<()> {
    relay_c2b_run(rd, be_ep.clone(), cli_ep, be_send, cli_send, sids, pending, engine, dead)
}

#[allow(clippy::too_many_arguments)]
fn relay_c2b_run<R: Read>(
    mut rd: FrameReader<R>,
    be_ep: Arc<Endpoint>,
    cli_ep: Arc<Endpoint>,
    be_send: Arc<Win>,
    cli_send: Arc<Win>,
    sids: Arc<Mutex<Sids>>,
    pending: Pending,
    engine: Arc<Engine>,
    dead: Arc<AtomicBool>,
) -> io::Result<()> {
    let r = (|| -> io::Result<()> {
    rd.preface()?;
    // Per-stream bytes awaiting their first complete grpc message.
    let mut cbuf: HashMap<u32, (Vec<u8>, bool)> = HashMap::new();
    // Client stream ids whose first gRPC message was already relayed;
    // only that message is eligible for the Solve rewrite.
    let mut seen_first: std::collections::HashSet<u32> = std::collections::HashSet::new();
    loop {
        if dead.load(Ordering::Relaxed) {
            return Ok(());
        }
        let Some(f) = rd.frame()? else { break Ok(()) };
        match f.ftype {
            F_SETTINGS if f.flags & FL_ACK == 0 => {
                let mut i = 0;
                let mut initial = None;
                while i + 6 <= f.payload.len() {
                    let id = u16::from_be_bytes([f.payload[i], f.payload[i + 1]]);
                    let v = u32::from_be_bytes([f.payload[i + 2], f.payload[i + 3], f.payload[i + 4], f.payload[i + 5]]);
                    if id == S_INITIAL_WINDOW_SIZE {
                        initial = Some(v);
                    }
                    i += 6;
                }
                if let Some(v) = initial {
                    cli_send.settings(v);
                }
                cli_ep.raw(&ack_frame(F_SETTINGS))?;
            }
            F_WINDOW_UPDATE => {
                if f.payload.len() >= 4 {
                    let inc = u32::from_be_bytes([f.payload[0], f.payload[1], f.payload[2], f.payload[3]]) & 0x7fff_ffff;
                    cli_send.update(f.sid, inc);
                }
            }
            F_PING if f.flags & FL_ACK == 0 => {
                let mut p = [0u8; 8];
                p.copy_from_slice(&f.payload[..f.payload.len().min(8)]);
                cli_ep.frame(F_PING, FL_ACK, 0, &p)?;
            }
            F_GOAWAY => {
                crate::diag::warn!("builder sent GOAWAY on grpc relay", payload = format!("{:?}", &f.payload[..f.payload.len().min(8)]));
                break Ok(());
            }
            F_HEADERS | F_CONTINUATION if f.sid != 0 => {
                let (block, _) = strip_flags(&f.payload, f.flags);
                let end_stream = f.ftype == F_HEADERS && f.flags & FL_END_STREAM != 0;
                let end_headers = f.flags & FL_END_HEADERS != 0;
                let b = {
                    let mut s = sids.lock().unwrap_or_else(|e| e.into_inner());
                    s.open_b(f.sid)
                };
                send_head(&be_ep, &be_send, b, f.ftype, &block, end_stream, end_headers)?;
            }
            F_DATA if f.sid != 0 => {
                let (data, _) = strip_flags(&f.payload, f.flags);
                let end = f.flags & FL_END_STREAM != 0;
                let b = {
                    let mut s = sids.lock().unwrap_or_else(|e| e.into_inner());
                    s.open_b(f.sid)
                };
                if seen_first.contains(&f.sid) {
                    send_data(&be_ep, &be_send, b, &data, end)?;
                    continue;
                }
                // Every stream's first bytes are one gRPC message; buffer
                // until it completes so a SolveRequest can be inspected.
                // Later messages on the same stream pass through below.
                let (mut buf, mut ended) = cbuf.remove(&f.sid).unwrap_or_default();
                buf.extend_from_slice(&data);
                ended |= end;
                if buf.len() >= 5 {
                    let mlen = u32::from_be_bytes([buf[1], buf[2], buf[3], buf[4]]) as usize;
                    if buf.len() >= 5 + mlen || ended {
                        let take = (5 + mlen).min(buf.len());
                        let msg = &buf[..take];
                        let rest = &buf[take..];
                        let mut emit: Vec<u8> = Vec::new();
                        let mut rewrote = None;
                        if msg.len() >= 5 && msg[0] == 0 {
                            if let Some((new_msg, repo, tags)) = rewrite_solve(&msg[5..msg.len().min(5 + mlen)], &engine) {
                                emit.push(0);
                                emit.extend_from_slice(&(new_msg.len() as u32).to_be_bytes());
                                emit.extend_from_slice(&new_msg);
                                rewrote = Some((repo, tags));
                            }
                        }
                        if rewrote.is_none() {
                            emit.extend_from_slice(msg);
                        }
                        emit.extend_from_slice(rest);
                        if let Some((repo, tags)) = rewrote {
                            pending.lock().unwrap_or_else(|e| e.into_inner()).insert(b, (repo, tags, engine.clone()));
                        }
                        seen_first.insert(f.sid);
                        send_data(&be_ep, &be_send, b, &emit, ended)?;
                        continue;
                    }
                }
                cbuf.insert(f.sid, (buf, ended));
            }
            F_RST if f.sid != 0 => {
                let (b, c) = {
                    let mut s = sids.lock().unwrap_or_else(|e| e.into_inner());
                    let b = s.open_b(f.sid);
                    (b, f.sid)
                };
                cbuf.remove(&c);
                if let Some((repo, _, e)) = pending.lock().unwrap_or_else(|e| e.into_inner()).remove(&b) {
                    super::builder::discard_pushed(&e, &repo);
                }
                {
                    let mut s = sids.lock().unwrap_or_else(|e| e.into_inner());
                    s.close(c, b);
                }
                be_send.close(b);
                if f.payload.len() >= 4 {
                    let code = u32::from_be_bytes([f.payload[0], f.payload[1], f.payload[2], f.payload[3]]);
                    crate::diag::warn!("builder reset grpc stream", sid = b, code = code);
                }
                be_ep.frame(F_RST, 0, b, &f.payload)?;
            }
            _ => {}
        }
    }
    })();
    be_ep.shutdown();
    r
}

/// Reads builder-conn frames, forwards stream data to the client.
#[allow(clippy::too_many_arguments)]
fn relay_b2c<R: Read>(
    rd: FrameReader<R>,
    cli_ep: Arc<Endpoint>,
    be_ep: Arc<Endpoint>,
    cli_send: Arc<Win>,
    be_send: Arc<Win>,
    sids: Arc<Mutex<Sids>>,
    pending: Pending,
    _engine: Arc<Engine>,
    _dead: Arc<AtomicBool>,
) -> io::Result<()> {
    relay_b2c_run(rd, cli_ep.clone(), be_ep, cli_send, be_send, sids, pending, _engine, _dead)
}

#[allow(clippy::too_many_arguments)]
fn relay_b2c_run<R: Read>(
    mut rd: FrameReader<R>,
    cli_ep: Arc<Endpoint>,
    be_ep: Arc<Endpoint>,
    cli_send: Arc<Win>,
    be_send: Arc<Win>,
    sids: Arc<Mutex<Sids>>,
    pending: Pending,
    _engine: Arc<Engine>,
    _dead: Arc<AtomicBool>,
) -> io::Result<()> {
    let r = (|| -> io::Result<()> {
    loop {
        let Some(f) = rd.frame()? else { break Ok(()) };
        match f.ftype {
            F_SETTINGS if f.flags & FL_ACK == 0 => {
                let mut i = 0;
                let mut initial = None;
                while i + 6 <= f.payload.len() {
                    let id = u16::from_be_bytes([f.payload[i], f.payload[i + 1]]);
                    let v = u32::from_be_bytes([f.payload[i + 2], f.payload[i + 3], f.payload[i + 4], f.payload[i + 5]]);
                    if id == S_INITIAL_WINDOW_SIZE {
                        initial = Some(v);
                    }
                    i += 6;
                }
                if let Some(v) = initial {
                    be_send.settings(v);
                }
                be_ep.raw(&ack_frame(F_SETTINGS))?;
            }
            F_WINDOW_UPDATE => {
                if f.payload.len() >= 4 {
                    let inc = u32::from_be_bytes([f.payload[0], f.payload[1], f.payload[2], f.payload[3]]) & 0x7fff_ffff;
                    be_send.update(f.sid, inc);
                }
            }
            F_PING if f.flags & FL_ACK == 0 => {
                let mut p = [0u8; 8];
                p.copy_from_slice(&f.payload[..f.payload.len().min(8)]);
                be_ep.frame(F_PING, FL_ACK, 0, &p)?;
            }
            F_GOAWAY => {
                crate::diag::warn!("client sent GOAWAY on grpc relay");
                break Ok(());
            }
            F_HEADERS | F_CONTINUATION if f.sid != 0 => {
                let end_stream = f.ftype == F_HEADERS && f.flags & FL_END_STREAM != 0;
                // Trailers for a rewritten solve: retag now.
                if f.ftype == F_HEADERS && end_stream
                    && let Some((repo, tags, e)) = pending.lock().unwrap_or_else(|x| x.into_inner()).remove(&f.sid)
                {
                    if let Err(err) = super::builder::retag_pushed_names(&e, &tags, &repo) {
                        crate::diag::warn!("builder retag failed", error = err);
                    }
                }
                let c = {
                    let s = sids.lock().unwrap_or_else(|e| e.into_inner());
                    match s.c_of(f.sid) {
                        Some(c) => c,
                        None => continue,
                    }
                };
                let (block, _) = strip_flags(&f.payload, f.flags);
                let end_headers = f.flags & FL_END_HEADERS != 0;
                send_head(&cli_ep, &cli_send, c, f.ftype, &block, end_stream, end_headers)?;
                if end_stream {
                    let mut s = sids.lock().unwrap_or_else(|e| e.into_inner());
                    s.close(c, f.sid);
                    cli_send.close(c);
                }
            }
            F_DATA if f.sid != 0 => {
                let c = {
                    let s = sids.lock().unwrap_or_else(|e| e.into_inner());
                    match s.c_of(f.sid) {
                        Some(c) => c,
                        None => continue,
                    }
                };
                let (data, _) = strip_flags(&f.payload, f.flags);
                let end = f.flags & FL_END_STREAM != 0;
                send_data(&cli_ep, &cli_send, c, &data, end)?;
                if end {
                    let mut s = sids.lock().unwrap_or_else(|e| e.into_inner());
                    s.close(c, f.sid);
                    cli_send.close(c);
                }
            }
            F_RST if f.sid != 0 => {
                let b = f.sid;
                if f.payload.len() >= 4 {
                    let code = u32::from_be_bytes([f.payload[0], f.payload[1], f.payload[2], f.payload[3]]);
                    crate::diag::warn!("builder reset grpc stream (b2c)", sid = b, code = code);
                }
                let c = {
                    let s = sids.lock().unwrap_or_else(|e| e.into_inner());
                    s.c_of(b)
                };
                if let Some(c) = c {
                    if let Some((repo, _, e)) = pending.lock().unwrap_or_else(|x| x.into_inner()).remove(&b) {
                        super::builder::discard_pushed(&e, &repo);
                    }
                    let mut s = sids.lock().unwrap_or_else(|e| e.into_inner());
                    s.close(c, b);
                    cli_send.close(c);
                    cli_ep.frame(F_RST, 0, c, &f.payload)?;
                }
                be_send.close(b);
            }
            _ => {}
        }
    }
    })();
    cli_ep.shutdown();
    r
}

// --- /session -----------------------------------------------------------------

/// HPACK "literal header field without indexing — new name".
fn hpack_lit(out: &mut Vec<u8>, name: &str, value: &str) {
    out.push(0x00);
    hpack_str(out, name);
    hpack_str(out, value);
}

fn hpack_str(out: &mut Vec<u8>, s: &str) {
    let b = s.as_bytes();
    if b.len() < 127 {
        out.push(b.len() as u8);
        out.extend_from_slice(b);
    } else {
        out.push(127);
        let mut n = b.len();
        while n >= 128 {
            out.push((n & 0x7f) as u8 | 0x80);
            n >>= 7;
        }
        out.push(n as u8);
        out.extend_from_slice(b);
    }
}

/// The `Control.Session` request headers, HPACK-encoded. The session
/// id/shared-key/methods ride the client's `X-Docker-Expose-Session-*`
/// headers, forwarded as gRPC metadata (lowercase, as h2 requires).
fn session_headers(req: &http::Request) -> Vec<u8> {
    let mut h = Vec::new();
    h.push(0x83); // :method POST (static index 3)
    h.push(0x86); // :scheme http (static index 6)
    hpack_lit(&mut h, ":path", "/moby.buildkit.v1.Control/Session");
    hpack_lit(&mut h, ":authority", "buildkit");
    hpack_lit(&mut h, "content-type", "application/grpc");
    hpack_lit(&mut h, "te", "trailers");
    hpack_lit(&mut h, "user-agent", "ctrs");
    for (k, v) in req.headers() {
        if k.to_ascii_lowercase().starts_with("x-docker-expose-session-") {
            hpack_lit(&mut h, &k.to_ascii_lowercase(), v);
        }
    }
    h
}

/// varint-encodes a protobuf `BytesMessage{data}` field.
fn bytes_message(data: &[u8]) -> Vec<u8> {
    let mut m = Vec::with_capacity(data.len() + 8);
    m.push(0x0a); // field 1, wire 2
    put_varint(&mut m, data.len() as u64);
    m.extend_from_slice(data);
    m
}

/// grpc frame: compression flag + big-endian length + message.
fn grpc_frame(msg: &[u8]) -> Vec<u8> {
    let mut g = Vec::with_capacity(msg.len() + 5);
    g.push(0);
    g.extend_from_slice(&(msg.len() as u32).to_be_bytes());
    g.extend_from_slice(msg);
    g
}

/// `/session`: splice the client's session bytes through a
/// `Control.Session` bidi stream on a fresh buildkitd connection.
fn session(req: &http::Request, early: Vec<u8>, sock: UnixStream, mut be: UnixStream) -> io::Result<()> {
    let cli_rd_sock = sock.try_clone()?;
    let mut cli_wr_sock = sock.try_clone()?;
    let be_ep = Arc::new(Endpoint::new(be.try_clone()?));
    let be_send = Arc::new(Win::new());
    let dead = Arc::new(AtomicBool::new(false));

    // h2 client handshake toward buildkitd.
    be.write_all(H2_PREFACE)?;
    be.write_all(&settings_frame(BIG_WINDOW))?;
    be.write_all(&window_update_frame(0, BIG_WINDOW))?;

    let mut be_rd = FrameReader::new(be.try_clone()?, Vec::new());
    // Read until the server's SETTINGS, ACKing and learning its
    // initial window; connection frames may interleave.
    loop {
        let Some(f) = be_rd.frame()? else { return Err(io_err("builder closed during handshake")) };
        match f.ftype {
            F_SETTINGS if f.flags & FL_ACK == 0 => {
                let mut i = 0;
                let mut initial = None;
                while i + 6 <= f.payload.len() {
                    let id = u16::from_be_bytes([f.payload[i], f.payload[i + 1]]);
                    let v = u32::from_be_bytes([f.payload[i + 2], f.payload[i + 3], f.payload[i + 4], f.payload[i + 5]]);
                    if id == S_INITIAL_WINDOW_SIZE {
                        initial = Some(v);
                    }
                    i += 6;
                }
                if let Some(v) = initial {
                    be_send.settings(v);
                }
                be_ep.raw(&ack_frame(F_SETTINGS))?;
                break;
            }
            F_SETTINGS => {}
            F_WINDOW_UPDATE if f.payload.len() >= 4 => {
                let inc = u32::from_be_bytes([f.payload[0], f.payload[1], f.payload[2], f.payload[3]]) & 0x7fff_ffff;
                be_send.update(f.sid, inc);
            }
            F_PING if f.flags & FL_ACK == 0 => {
                let mut p = [0u8; 8];
                p.copy_from_slice(&f.payload[..f.payload.len().min(8)]);
                be_ep.frame(F_PING, FL_ACK, 0, &p)?;
            }
            F_GOAWAY => return Err(io_err("builder sent GOAWAY")),
            _ => {}
        }
    }

    // Open the Control.Session stream (client-initiated stream 1).
    be_ep.frame(F_HEADERS, FL_END_HEADERS, 1, &session_headers(req))?;

    // Sender: client bytes → BytesMessage → grpc DATA on stream 1.
    let send_ep = be_ep.clone();
    let send_win = be_send.clone();
    let send_dead = dead.clone();
    let sender = std::thread::Builder::new()
        .name("ctrs-h2c-sess-tx".into())
        .spawn(move || -> io::Result<()> {
            let mut rd = FrameReader::new(cli_rd_sock, early);
            let mut buf = vec![0u8; 32 * 1024];
            loop {
                if send_dead.load(Ordering::Relaxed) {
                    return Ok(());
                }
                // FrameReader's fill would parse h2; the session leg is
                // a raw byte stream — read the socket directly after
                // draining `early`.
                let n = {
                    // Drain early first.
                    if !rd.pending.is_empty() {
                        let n = rd.pending.len().min(buf.len());
                        buf[..n].copy_from_slice(&rd.pending[..n]);
                        rd.pending.drain(..n);
                        n
                    } else {
                        match rd.s.read(&mut buf) {
                            Ok(0) => 0,
                            Ok(n) => n,
                            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
                            Err(e) => return Err(e),
                        }
                    }
                };
                if n == 0 {
                    // Client half-closed: end our side of the stream.
                    send_win.wait(1, 0);
                    send_ep.frame(F_DATA, FL_END_STREAM, 1, &[])?;
                    return Ok(());
                }
                let msg = grpc_frame(&bytes_message(&buf[..n]));
                let mut off = 0;
                while off < msg.len() {
                    let n2 = (msg.len() - off).min(OUT_FRAME);
                    send_win.wait(1, n2);
                    crate::diag::debug!("session DATA", len = n2, off = off, msg_len = msg.len());
                    send_ep.frame(F_DATA, 0, 1, &msg[off..off + n2])?;
                    send_win.take(1, n2);
                    off += n2;
                }
            }
        })?;

    // Receiver (this thread): builder DATA → grpc messages → session
    // bytes to the client; conn frames handled inline.
    let mut gbuf: Vec<u8> = Vec::new();
    let result = loop {
        let f = match be_rd.frame() {
            Ok(Some(f)) => f,
            Ok(None) => break Err(io_err("builder closed the session")),
            Err(e) => break Err(e),
        };
        crate::diag::debug!("session rx frame", ty = f.ftype, flags = f.flags, sid = f.sid, len = f.payload.len());
        match f.ftype {
            F_SETTINGS if f.flags & FL_ACK == 0 => {
                let mut i = 0;
                let mut initial = None;
                while i + 6 <= f.payload.len() {
                    let id = u16::from_be_bytes([f.payload[i], f.payload[i + 1]]);
                    let v = u32::from_be_bytes([f.payload[i + 2], f.payload[i + 3], f.payload[i + 4], f.payload[i + 5]]);
                    if id == S_INITIAL_WINDOW_SIZE {
                        initial = Some(v);
                    }
                    i += 6;
                }
                if let Some(v) = initial {
                    be_send.settings(v);
                }
                be_ep.raw(&ack_frame(F_SETTINGS))?;
            }
            F_WINDOW_UPDATE if f.payload.len() >= 4 => {
                let inc = u32::from_be_bytes([f.payload[0], f.payload[1], f.payload[2], f.payload[3]]) & 0x7fff_ffff;
                crate::diag::debug!("session WINDOW_UPDATE", sid = f.sid, inc = inc);
                be_send.update(f.sid, inc);
            }
            F_PING if f.flags & FL_ACK == 0 => {
                let mut p = [0u8; 8];
                p.copy_from_slice(&f.payload[..f.payload.len().min(8)]);
                be_ep.frame(F_PING, FL_ACK, 0, &p)?;
            }
            F_DATA if f.sid == 1 => {
                // Reassemble grpc messages; extract BytesMessage.data.
                gbuf.extend_from_slice(&f.payload);
                while gbuf.len() >= 5 {
                    let mlen = u32::from_be_bytes([gbuf[1], gbuf[2], gbuf[3], gbuf[4]]) as usize;
                    if gbuf.len() < 5 + mlen {
                        break;
                    }
                    let msg = gbuf[5..5 + mlen].to_vec();
                    gbuf.drain(..5 + mlen);
                    // BytesMessage: field 1, wire 2.
                    if msg.len() >= 2 && msg[0] == 0x0a {
                        let mut j = 1;
                        if let Some(l) = (|| {
                            let mut v = 0u64;
                            let mut sh = 0u32;
                            loop {
                                let b = *msg.get(j)?;
                                j += 1;
                                v |= ((b & 0x7f) as u64) << sh;
                                if b & 0x80 == 0 {
                                    return Some(v as usize);
                                }
                                sh += 7;
                            }
                        })() {
                            if j + l <= msg.len() {
                                let _ = cli_wr_sock.write_all(&msg[j..j + l]);
                                let _ = cli_wr_sock.flush();
                            }
                        }
                    }
                }
                if f.flags & FL_END_STREAM != 0 {
                    break Ok(());
                }
            }
            F_HEADERS if f.sid == 1 && f.flags & FL_END_STREAM != 0 => break Ok(()),
            F_RST if f.sid == 1 => {
                let code = if f.payload.len() >= 4 {
                    u32::from_be_bytes([f.payload[0], f.payload[1], f.payload[2], f.payload[3]])
                } else {
                    u32::MAX
                };
                break Err(io_err(&format!("builder reset the session (code {code})")));
            }
            F_GOAWAY => break Err(io_err("builder sent GOAWAY")),
            _ => {}
        }
    };
    dead.store(true, Ordering::Relaxed);
    be_ep.shutdown();
    let _ = sender.join();
    let _ = be.shutdown(Shutdown::Both);
    result
}
