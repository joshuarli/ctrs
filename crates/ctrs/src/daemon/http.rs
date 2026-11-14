//! Just enough HTTP/1.1 for Docker clients: keep-alive, Content-Length and
//! chunked bodies, streamed (chunked) responses and connection upgrades for
//! `attach`. Docker clients keep a few connections open, so the server runs
//! one thread per connection and never parses more than it needs.

use std::io::{self, BufRead, BufReader, Read, Write};
use std::os::unix::net::UnixStream;

/// API version this daemon speaks. The Docker CLI negotiates down to it.
pub const API_VERSION: &str = "1.47";

/// Largest request body read into memory (container create, etc.). Archives
/// and image loads are streamed with [`Body`] instead, at any size.
pub(crate) const MAX_BODY: usize = 8 << 20;
/// The request line and headers together may not exceed this: an endless
/// header line must not grow memory without bound.
const MAX_HEAD: u64 = 64 << 10;
/// One chunk-size line (hex, plus an optional `;extension`).
const MAX_CHUNK_LINE: u64 = 64;
/// One trailer field line and the number of trailer fields per body.
const MAX_TRAILER_LINE: u64 = 8 << 10;
const MAX_TRAILER_FIELDS: usize = 32;

/// Request body framing, parsed exactly once from the head and carried on
/// the request. The buffered and streamed readers both consume this value;
/// nothing downstream reinterprets the header lines.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Framing {
    /// No body.
    Empty,
    /// `Content-Length: n`.
    ContentLength(u64),
    /// `Transfer-Encoding: chunked`; the only coding ctrs reads.
    Chunked,
}

#[derive(Debug)]
pub struct Request {
    pub method: String,
    /// Path without the `/v1.xx` prefix or the query string.
    pub path: String,
    query: Vec<(String, String)>,
    headers: Vec<(String, String)>,
    pub body: Vec<u8>,
    pub(crate) framing: Framing,
}

impl Request {
    pub fn query(&self, key: &str) -> Option<&str> {
        self.query.iter().find(|(k, _)| k == key).map(|(_, v)| v.as_str())
    }

    /// Every value of a repeated key (`names=a&names=b`).
    pub fn queries<'a>(&'a self, key: &'a str) -> impl Iterator<Item = &'a str> + 'a {
        self.query.iter().filter(move |(k, _)| k == key).map(|(_, v)| v.as_str())
    }

    /// Docker sends booleans as `1`/`true`/`0`/`false`.
    pub fn flag(&self, key: &str) -> bool {
        matches!(self.query(key), Some("1" | "true" | "True"))
    }

    pub fn header(&self, key: &str) -> Option<&str> {
        self.headers.iter().find(|(k, _)| k.eq_ignore_ascii_case(key)).map(|(_, v)| v.as_str())
    }

    /// Replaces the headers after construction (the pilot fills them).
    #[cfg(feature = "h12tiny")]
    pub(crate) fn with_headers(mut self, headers: Vec<(String, String)>) -> io::Result<Request> {
        self.framing = parse_framing(&headers)?;
        self.headers = headers;
        Ok(self)
    }

    /// A request the daemon makes of itself (the managed builder's
    /// container create), so it goes through the same code as a client's.
    pub fn internal(method: &str, path: &str, query: &[(&str, &str)], body: Vec<u8>) -> Request {
        let query = query.iter().map(|(k, v)| ((*k).to_owned(), (*v).to_owned())).collect();
        Request { method: method.to_owned(), path: path.to_owned(), query, headers: Vec::new(), body, framing: Framing::Empty }
    }
}

/// Reads a line of at most `max` bytes. A line that hits the cap without a
/// newline is too large and is an error.
fn read_capped_line(r: &mut dyn DynBufRead, max: u64) -> io::Result<String> {
    let mut line = String::new();
    let n = (&mut *r).take(max + 1).read_line(&mut line)?;
    if n == 0 {
        return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "unexpected end of body"));
    }
    if n as u64 > max {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "line too large"));
    }
    Ok(line)
}

/// One chunk-size line: hex with an optional `;extension`. Bounded.
fn read_chunk_size(r: &mut dyn DynBufRead) -> io::Result<u64> {
    let line = read_capped_line(r, MAX_CHUNK_LINE)?;
    let size = line.trim().split(';').next().unwrap_or("");
    u64::from_str_radix(size, 16).map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "bad chunk size"))
}

/// The CRLF terminating one chunk's data.
fn read_chunk_crlf(r: &mut dyn DynBufRead) -> io::Result<()> {
    let mut crlf = [0u8; 2];
    r.read_exact(&mut crlf)?;
    if &crlf != b"\r\n" {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "missing CRLF after chunk"));
    }
    Ok(())
}

/// The trailer section after the zero-size chunk: field lines, then the
/// final empty line. Bounded in line length and field count.
fn consume_trailers(r: &mut dyn DynBufRead) -> io::Result<()> {
    let mut line = String::new();
    for _ in 0..MAX_TRAILER_FIELDS {
        line.clear();
        let n = (&mut *r).take(MAX_TRAILER_LINE).read_line(&mut line)?;
        if n == 0 || line.trim().is_empty() {
            return Ok(());
        }
    }
    Err(io::Error::new(io::ErrorKind::InvalidData, "too many trailer fields"))
}

/// HTTP/1.1: a request with `Expect: 100-continue` waits for the interim
/// status line before the client sends the body; answer it before the
/// body is read, in both the buffered and the streamed path.
fn expects_continue(headers: &[(String, String)]) -> bool {
    headers.iter().any(|(k, v)| k.eq_ignore_ascii_case("expect") && v.trim().eq_ignore_ascii_case("100-continue"))
}

/// Contradictory or invalid framing is rejected before dispatch: both
/// framings at once, mismatched repeated Content-Length, a non-numeric
/// value, or a Transfer-Encoding ctrs cannot read. Identical repeated
/// Content-Length values are accepted. `chunked` must be the only coding:
/// a list of chunked codings (`chunked, chunked`) is rejected.
fn parse_framing(headers: &[(String, String)]) -> io::Result<Framing> {
    let bad = || io::Error::new(io::ErrorKind::InvalidData, "invalid or contradictory framing");
    let mut codings: Vec<&str> = Vec::new();
    let mut lengths: Vec<&str> = Vec::new();
    for (k, v) in headers {
        if k.eq_ignore_ascii_case("transfer-encoding") {
            codings.extend(v.split(',').map(str::trim));
        } else if k.eq_ignore_ascii_case("content-length") {
            lengths.push(v.trim());
        }
    }
    if !codings.is_empty() {
        if codings.len() != 1 || !codings[0].eq_ignore_ascii_case("chunked") {
            return Err(bad());
        }
        if !lengths.is_empty() {
            return Err(bad());
        }
        return Ok(Framing::Chunked);
    }
    if let Some(first) = lengths.first() {
        if lengths.iter().any(|l| l != first) {
            return Err(bad());
        }
        let n: u64 = first.parse().map_err(|_| bad())?;
        return Ok(Framing::ContentLength(n));
    }
    Ok(Framing::Empty)
}

/// The request body reader: usually `BufReader<UnixStream>`, but the
/// chunked decoder is unit-tested through in-memory readers, which is what
/// this indirection is for; the h12tiny pilot (CTRS-15) is another caller.
/// Any so the attach/stdin path can recover the socket when there is one.
pub trait DynBufRead: BufRead + std::any::Any {
    fn as_any_mut(&mut self) -> &mut dyn std::any::Any;
}
impl<T: BufRead + std::any::Any> DynBufRead for T {
    fn as_any_mut(&mut self) -> &mut dyn std::any::Any {
        self
    }
}

/// Reads the next request on a connection. `Ok(None)` is a clean close.
/// When `stream(method, path)` is true the body stays unread: the handler
/// reads it through [`Body`].
///
/// The head is the only phase with a read deadline: a peer that connects
/// and sends nothing must not hold the thread forever. The body and any
/// upgraded stream keep no deadline, so legitimate long-running or idle
/// streams (exec, attach) are never cut.
pub fn read_request(r: &mut BufReader<UnixStream>, w: &mut UnixStream, stream: impl Fn(&str, &str) -> bool) -> io::Result<Option<Request>> {
    r.get_ref().set_read_timeout(Some(std::time::Duration::from_secs(10)))?;
    // The request line and headers are read through a cap, so a client
    // cannot exhaust memory with an endless line. The body is read after.
    let (method, path, query, headers) = {
        let mut head = (&mut *r).take(MAX_HEAD);
        let mut line = String::new();
        if head.read_line(&mut line)? == 0 {
            return Ok(None);
        }
        let mut parts = line.split_whitespace();
        let (Some(method), Some(target)) = (parts.next(), parts.next()) else {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "bad request line"));
        };
        let method = method.to_owned();
        let (raw_path, raw_query) = target.split_once('?').unwrap_or((target, ""));
        let path = strip_version(raw_path).to_owned();
        let query: Vec<(String, String)> = raw_query
            .split('&')
            .filter(|kv| !kv.is_empty())
            .map(|kv| {
                let (k, v) = kv.split_once('=').unwrap_or((kv, ""));
                (percent_decode(k), percent_decode(v))
            })
            .collect();
        let mut headers = Vec::new();
        loop {
            line.clear();
            if head.read_line(&mut line)? == 0 {
                return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "headers too large or cut short"));
            }
            let l = line.trim_end();
            if l.is_empty() {
                break;
            }
            if let Some((k, v)) = l.split_once(':') {
                headers.push((k.trim().to_owned(), v.trim().to_owned()));
            }
        }
        (method, path, query, headers)
    };
    r.get_ref().set_read_timeout(None)?;
    let framing = parse_framing(&headers)?;
    if expects_continue(&headers) {
        w.write_all(b"HTTP/1.1 100 Continue\r\n\r\n")?;
        w.flush()?;
    }
    let streamed = stream(&method, &path);
    let mut req = Request { method, path, query, headers, body: Vec::new(), framing };
    if streamed {
        return Ok(Some(req));
    }
    if req.framing == Framing::Chunked {
        loop {
            // A chunk-size line is short hex (plus an optional ;extension).
            let n = read_chunk_size(r)? as usize;
            if n == 0 {
                consume_trailers(r)?;
                break;
            }
            if req.body.len().checked_add(n).is_none_or(|t| t > MAX_BODY) {
                return Err(io::Error::new(io::ErrorKind::InvalidData, "request body too large"));
            }
            let start = req.body.len();
            req.body.resize(start + n, 0);
            r.read_exact(&mut req.body[start..])?;
            read_chunk_crlf(r)?;
        }
    } else if let Framing::ContentLength(len) = req.framing {
        if len > MAX_BODY as u64 {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "request body too large"));
        }
        let len = len as usize;
        req.body.resize(len, 0);
        r.read_exact(&mut req.body)?;
    }
    Ok(Some(req))
}

/// A streamed request body: Content-Length or chunked, read as it arrives.
pub struct Body<'a> {
    r: &'a mut dyn DynBufRead,
    chunked: bool,
    /// Bytes left in the body (or in the current chunk).
    left: u64,
    done: bool,
}

impl<'a> Body<'a> {
    pub fn new(req: &Request, r: &'a mut dyn DynBufRead) -> Body<'a> {
        match req.framing {
            Framing::Chunked => Body { r, chunked: true, left: 0, done: false },
            Framing::ContentLength(n) => Body { r, chunked: false, left: n, done: n == 0 },
            Framing::Empty => Body { r, chunked: false, left: 0, done: true },
        }
    }
}

impl Read for Body<'_> {
    fn read(&mut self, buf: &mut [u8]) -> io::Result<usize> {
        if self.done || buf.is_empty() {
            return Ok(0);
        }
        if self.chunked && self.left == 0 {
            self.left = read_chunk_size(self.r)?;
            if self.left == 0 {
                consume_trailers(self.r)?;
                self.done = true;
                return Ok(0);
            }
        }
        let want = buf.len().min(self.left.min(usize::MAX as u64) as usize);
        let n = self.r.read(&mut buf[..want])?;
        if n == 0 {
            return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "request body cut short"));
        }
        self.left -= n as u64;
        if self.left == 0 {
            if self.chunked {
                read_chunk_crlf(self.r)?;
            } else {
                self.done = true;
            }
        }
        Ok(n)
    }
}

/// `/v1.47/containers/json` → `/containers/json`.
pub(crate) fn strip_version(path: &str) -> &str {
    if let Some(rest) = path.strip_prefix("/v")
        && let Some(i) = rest.find('/')
            && rest[..i].bytes().all(|b| b.is_ascii_digit() || b == b'.') {
                return &rest[i..];
            }
    path
}

pub(crate) fn percent_decode(s: &str) -> String {
    let b = s.as_bytes();
    let hex = |c: u8| (c as char).to_digit(16).map(|d| d as u8);
    let mut out = Vec::with_capacity(b.len());
    let mut i = 0;
    while i < b.len() {
        match b[i] {
            b'+' => out.push(b' '),
            b'%' if i + 2 < b.len() && hex(b[i + 1]).is_some() && hex(b[i + 2]).is_some() => {
                out.push(hex(b[i + 1]).unwrap_or(0) << 4 | hex(b[i + 2]).unwrap_or(0));
                i += 2;
            }
            c => out.push(c),
        }
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn reason(status: u16) -> &'static str {
    match status {
        101 => "UPGRADED",
        200 => "OK",
        201 => "Created",
        204 => "No Content",
        304 => "Not Modified",
        400 => "Bad Request",
        404 => "Not Found",
        409 => "Conflict",
        500 => "Internal Server Error",
        501 => "Not Implemented",
        _ => "",
    }
}

thread_local! {
    /// The request this connection thread is answering, for the log.
    static SERVING: std::cell::RefCell<(String, String)> = const { std::cell::RefCell::new((String::new(), String::new())) };
}

/// Notes the request being answered: a failure status written for it is
/// logged with its method and path (never its query or body).
pub fn serving(method: &str, path: &str) {
    SERVING.with(|s| *s.borrow_mut() = (method.to_owned(), path.to_owned()));
}

/// Engine API failures in the log: 5xx as errors, 4xx as warnings, except
/// 404s, which clients use to ask (does this image exist yet?).
fn note_failure(status: u16) {
    SERVING.with(|s| {
        let (method, path) = &*s.borrow();
        match status {
            404 => crate::diag::debug!("request failed", method = method, path = path, status = status),
            400..=499 => crate::diag::warn!("request failed", method = method, path = path, status = status),
            _ => crate::diag::error!("request failed", method = method, path = path, status = status),
        }
    });
}

fn head(w: &mut impl Write, status: u16, extra: &str) -> io::Result<()> {
    if status >= 400 {
        note_failure(status);
    }
    write!(
        w,
        "HTTP/1.1 {status} {}\r\nApi-Version: {API_VERSION}\r\nDocker-Experimental: false\r\nOstype: linux\r\nServer: ctrs/{} (linux)\r\n{extra}\r\n",
        reason(status),
        env!("CARGO_PKG_VERSION")
    )
}

pub fn respond(w: &mut impl Write, status: u16, content_type: &str, body: &[u8]) -> io::Result<()> {
    let extra = if status == 204 || status == 304 {
        String::new()
    } else {
        format!("Content-Type: {content_type}\r\nContent-Length: {}\r\n", body.len())
    };
    head(w, status, &extra)?;
    w.write_all(body)?;
    w.flush()
}

/// `respond` plus extra header lines, each ending in CRLF.
pub fn respond_with(w: &mut impl Write, status: u16, content_type: &str, extra: &str, body: &[u8]) -> io::Result<()> {
    head(w, status, &format!("Content-Type: {content_type}\r\nContent-Length: {}\r\n{extra}", body.len()))?;
    w.write_all(body)?;
    w.flush()
}

pub fn json(w: &mut impl Write, status: u16, body: &str) -> io::Result<()> {
    respond(w, status, "application/json", body.as_bytes())
}

pub fn no_content(w: &mut impl Write) -> io::Result<()> {
    respond(w, 204, "", b"")
}

/// Docker's error shape: `{"message": "..."}`.
pub fn error(w: &mut impl Write, status: u16, message: &str) -> io::Result<()> {
    json(w, status, &serde_json::json!({ "message": message }).to_string())
}

/// Starts a streamed response; follow with [`chunk`] calls and [`end`].
pub fn begin_stream(w: &mut impl Write, status: u16, content_type: &str) -> io::Result<()> {
    begin_stream_with(w, status, content_type, "")
}

/// `begin_stream` plus extra header lines, each ending in CRLF.
pub fn begin_stream_with(w: &mut impl Write, status: u16, content_type: &str, extra: &str) -> io::Result<()> {
    head(w, status, &format!("Content-Type: {content_type}\r\nTransfer-Encoding: chunked\r\n{extra}"))?;
    w.flush()
}

/// Headers only, for HEAD: `extra` lines end in CRLF.
pub fn head_only(w: &mut impl Write, status: u16, extra: &str) -> io::Result<()> {
    head(w, status, &format!("Content-Length: 0\r\n{extra}"))?;
    w.flush()
}

pub fn chunk(w: &mut impl Write, data: &[u8]) -> io::Result<()> {
    if data.is_empty() {
        return Ok(());
    }
    write!(w, "{:x}\r\n", data.len())?;
    w.write_all(data)?;
    w.write_all(b"\r\n")?;
    w.flush()
}

pub fn end(w: &mut impl Write) -> io::Result<()> {
    w.write_all(b"0\r\n\r\n")?;
    w.flush()
}

/// Switches the connection to Docker's raw stream for `attach`. After this
/// the connection carries multiplexed output frames until it closes.
pub fn upgrade(w: &mut impl Write) -> io::Result<()> {
    head(w, 101, "Content-Type: application/vnd.docker.raw-stream\r\nConnection: Upgrade\r\nUpgrade: tcp\r\n")?;
    w.flush()
}

/// Docker's multiplexed stream framing: `[stream, 0, 0, 0, len u32 BE] data`.
pub fn mux_frame(w: &mut impl Write, stream: u8, data: &[u8]) -> io::Result<()> {
    let mut header = [0u8; 8];
    header[0] = stream;
    header[4..].copy_from_slice(&(data.len() as u32).to_be_bytes());
    w.write_all(&header)?;
    w.write_all(data)?;
    w.flush()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strips_api_version() {
        assert_eq!(strip_version("/v1.47/containers/json"), "/containers/json");
        assert_eq!(strip_version("/_ping"), "/_ping");
        assert_eq!(strip_version("/volumes"), "/volumes");
    }

    #[test]
    fn decodes_query_values() {
        assert_eq!(percent_decode("docker.io%2Flibrary%2Falpine"), "docker.io/library/alpine");
        assert_eq!(percent_decode("a+b"), "a b");
        assert_eq!(percent_decode("100%"), "100%");
        assert_eq!(percent_decode("%7B%22a%22%3A1%7D"), "{\"a\":1}");
    }
}

#[cfg(test)]
mod framing_tests {
    use super::{Framing, parse_framing};

    fn h(pairs: &[(&str, &str)]) -> Vec<(String, String)> {
        pairs.iter().map(|(k, v)| ((*k).to_owned(), (*v).to_owned())).collect()
    }

    #[test]
    fn repeated_chunked_is_rejected() {
        assert!(parse_framing(&h(&[("Transfer-Encoding", "chunked, chunked")])).is_err());
        assert!(parse_framing(&h(&[("Transfer-Encoding", "chunked"), ("Transfer-Encoding", "chunked")])).is_err());
        assert!(parse_framing(&h(&[("Transfer-Encoding", "Chunked")])).is_ok());
    }

    #[test]
    fn any_non_chunked_coding_is_rejected() {
        assert!(parse_framing(&h(&[("Transfer-Encoding", "gzip, chunked")])).is_err());
        assert!(parse_framing(&h(&[("Transfer-Encoding", "gzip")])).is_err());
        assert!(parse_framing(&h(&[("Transfer-Encoding", "")])).is_err());
        assert!(parse_framing(&h(&[("Transfer-Encoding", "chunked,")])).is_err());
    }

    #[test]
    fn te_and_cl_together_are_rejected() {
        assert!(parse_framing(&h(&[("Transfer-Encoding", "chunked"), ("Content-Length", "4")])).is_err());
    }

    #[test]
    fn identical_repeated_cl_is_accepted() {
        assert_eq!(parse_framing(&h(&[("Content-Length", "4"), ("Content-Length", "4")])).unwrap(), Framing::ContentLength(4));
        assert_eq!(parse_framing(&h(&[("Content-Length", " 4 "), ("Content-Length", "4")])).unwrap(), Framing::ContentLength(4));
    }

    #[test]
    fn mismatched_or_nonnumeric_cl_is_rejected() {
        assert!(parse_framing(&h(&[("Content-Length", "4"), ("Content-Length", "5")])).is_err());
        assert!(parse_framing(&h(&[("Content-Length", "four")])).is_err());
        assert!(parse_framing(&h(&[("Content-Length", "")])).is_err());
        // u64 range is all this path needs; the reader caps the buffered size.
        assert_eq!(parse_framing(&h(&[("Content-Length", "18446744073709551615")])).unwrap(), Framing::ContentLength(u64::MAX));
    }

    #[test]
    fn no_framing_headers_is_empty() {
        assert_eq!(parse_framing(&h(&[])).unwrap(), Framing::Empty);
        assert_eq!(parse_framing(&h(&[("Host", "x")])).unwrap(), Framing::Empty);
    }

    #[test]
    fn chunked_roundtrip_is_recognized_identically() {
        assert_eq!(parse_framing(&h(&[("transfer-encoding", "chunked")])).unwrap(), Framing::Chunked);
    }
}

#[cfg(test)]
mod body_tests {
    use super::*;
    use std::io::Cursor;

    fn req_with(framing: Framing) -> Request {
        Request { method: "POST".into(), path: "/x".into(), query: Vec::new(), headers: Vec::new(), body: Vec::new(), framing }
    }

    fn body_of(bytes: &[u8], framing: Framing) -> io::Result<Vec<u8>> {
        let mut cur = Cursor::new(bytes.to_vec());
        let req = req_with(framing);
        let mut b = Body::new(&req, &mut cur);
        let mut out = Vec::new();
        b.read_to_end(&mut out)?;
        Ok(out)
    }

    #[test]
    fn chunked_body_with_trailers_decodes() {
        let bytes = b"5\r\nhello\r\n6\r\n world\r\n0\r\nX-Trailer: v\r\n\r\n";
        assert_eq!(body_of(bytes, Framing::Chunked).unwrap(), b"hello world");
    }

    #[test]
    fn chunk_extensions_are_ignored() {
        let bytes = b"3;ext=1\r\nabc\r\n0\r\n\r\n";
        assert_eq!(body_of(bytes, Framing::Chunked).unwrap(), b"abc");
    }

    #[test]
    fn a_cut_short_chunk_is_an_error() {
        assert!(body_of(b"5\r\nhel", Framing::Chunked).is_err());
    }

    #[test]
    fn content_length_reads_exactly_that_many_bytes() {
        assert_eq!(body_of(b"hello world", Framing::ContentLength(5)).unwrap(), b"hello");
        assert!(body_of(b"hi", Framing::ContentLength(5)).is_err());
    }

    #[test]
    fn empty_framing_reads_nothing() {
        assert_eq!(body_of(b"", Framing::Empty).unwrap(), b"");
    }
}
