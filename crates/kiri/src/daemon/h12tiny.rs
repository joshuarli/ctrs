//! CTRS-15 pilot (behind the `h12tiny` feature, off by default): the Docker
//! API served by h12tiny's HTTP/1.1 driver instead of the hand-written
//! `http.rs` front end. Per accepted connection, not a global executor.
//!
//! Scope, deliberately narrow: streaming routes (archives, image
//! load/pull/push/save, logs, stats, events, wait, attach, exec) keep the
//! incumbent parser, detected from the first bytes with `recv(MSG_PEEK)`
//! without consuming them. Everything else goes through h12tiny: the body is
//! buffered (8 MiB cap, like the incumbent), the crate-internal request is
//! routed by the same `route()`, the raw bytes it writes are captured on a
//! `UnixStream::pair` and re-wrapped as one h12tiny response.

use std::io;
use std::io::{BufReader, Cursor, Read};
use std::os::fd::AsRawFd;
use std::os::unix::net::UnixStream;
use std::sync::Arc;

use super::engine::Engine;
use super::http;
use hyper::body::{Body as _, Incoming};

/// `true` when the request names a streaming route and must stay on the
/// incumbent parser. Fails toward the incumbent.
pub fn is_streaming(path: &str) -> bool {
    let p = path.split(['?', '#']).next().unwrap_or(path);
    if p == "/build" || p == "/images/load" || p == "/images/create" || p == "/images/get" {
        return true;
    }
    if p == "/events" || p.ends_with("/archive") || p.ends_with("/logs") || p.ends_with("/stats") || p.ends_with("/export") || p.ends_with("/wait") {
        return true;
    }
    if p.contains("/attach") {
        return true;
    }
    if p.starts_with("/images/") && (p.ends_with("/push") || p.ends_with("/get")) {
        return true;
    }
    if p.starts_with("/exec/") && p.ends_with("/start") {
        return true;
    }
    false
}

/// Sniffs the request's first line without consuming it; `false` (h12tiny)
/// when it cannot be determined — safe, h12tiny owns the connection then.
pub fn wants_incumbent(stream: &UnixStream) -> bool {
    let mut buf = [0u8; 512];
    let mut filled = 0usize;
    for _ in 0..200 {
        // SAFETY: `buf` is a valid writable buffer of buf.len() bytes; MSG_PEEK does not consume.
        let n = unsafe { libc::recv(stream.as_raw_fd(), buf.as_mut_ptr().cast(), buf.len() - filled, libc::MSG_PEEK | libc::MSG_DONTWAIT) };
        if n > 0 {
            filled = n as usize;
            if buf[..filled].contains(&b'\n') {
                break;
            }
            continue;
        }
        if n == 0 {
            return false;
        }
        let e = io::Error::last_os_error();
        if e.raw_os_error() == Some(libc::EWOULDBLOCK) {
            std::thread::sleep(std::time::Duration::from_micros(500));
            continue;
        }
        return false;
    }
    let first = buf[..filled].split(|&b| b == b'\n').next().unwrap_or_default();
    let mut parts = first.split(|&b| b == b' ');
    let (Some(_method), Some(path)) = (parts.next(), parts.next()) else { return false };
    let Ok(path) = std::str::from_utf8(path) else { return false };
    is_streaming(path)
}

/// A response body carrying bytes already buffered in memory; the error is
/// `Infallible` because the bytes exist before the response is built.
pub struct Full {
    bytes: Option<hyper::body::Bytes>,
}

impl hyper::body::Body for Full {
    type Data = hyper::body::Bytes;
    type Error = std::convert::Infallible;

    fn poll_frame(mut self: std::pin::Pin<&mut Self>, _cx: &mut std::task::Context<'_>) -> std::task::Poll<Option<Result<hyper::body::Frame<Self::Data>, Self::Error>>> {
        match self.bytes.take() {
            Some(b) => std::task::Poll::Ready(Some(Ok(hyper::body::Frame::data(b)))),
            None => std::task::Poll::Ready(None),
        }
    }

    fn is_end_stream(&self) -> bool {
        self.bytes.is_none()
    }
}

#[derive(Clone)]
struct Pilot {
    engine: Arc<Engine>,
}

impl hyper::service::Service<hyper::Request<Incoming>> for Pilot {
    type Response = hyper::Response<Full>;
    type Error = Box<dyn std::error::Error + Send + Sync>;
    type Future = std::pin::Pin<Box<dyn std::future::Future<Output = Result<Self::Response, Self::Error>> + Send>>;

    fn call(&self, req: hyper::Request<Incoming>) -> Self::Future {
        let engine = self.engine.clone();
        Box::pin(async move {
            let (parts, incoming) = req.into_parts();

            let mut incoming = incoming;
            let body = {
                let mut body = Vec::new();
                loop {
                    let frame = std::future::poll_fn(|cx| std::pin::Pin::new(&mut incoming).poll_frame(cx)).await;
                    match frame {
                        Some(Ok(frame)) => {
                            if let Ok(data) = frame.into_data() {
                                if body.len().checked_add(data.len()).is_none_or(|t| t > http::MAX_BODY) {
                                    return Err("request body too large".into());
                                }
                                body.extend_from_slice(&data);
                            }
                        }
                        Some(Err(e)) => return Err(e.to_string().into()),
                        None => break body,
                    }
                }
            };

            let method = parts.method.to_string();
            let target = parts.uri.path_and_query().map(|pq| pq.as_str()).unwrap_or("/").to_owned();
            let (path, query) = target.split_once('?').unwrap_or((target.as_str(), ""));
            let path = http::strip_version(path).to_owned();
            let query: Vec<(String, String)> = query
                .split('&')
                .filter(|kv| !kv.is_empty())
                .map(|kv| {
                    let (k, v) = kv.split_once('=').unwrap_or((kv, ""));
                    (http::percent_decode(k), http::percent_decode(v))
                })
                .collect();
            let qrefs: Vec<(&str, &str)> = query.iter().map(|(k, v)| (k.as_str(), v.as_str())).collect();
            let headers: Vec<(String, String)> = parts.headers.iter().map(|(k, v)| (k.as_str().to_owned(), v.to_str().unwrap_or("").to_owned())).collect();
            // The pilot only handles buffered bodies; route()'s reader is
            // never consulted for them.
            let internal = http::Request::internal(&method, &path, &qrefs, body).with_headers(headers);
            let body_for_r = internal.body.clone();
            let mut r = BufReader::new(Cursor::new(body_for_r));

            // route() is sync and blocking; this connection's reactor has
            // nothing else to drive, so blocking it matches the incumbent.
            let (mut client_side, mut route_side) = UnixStream::pair()?;
            let next = super::api::route(&internal, &engine, &mut route_side, &mut r).map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { format!("route: {e}").into() })?;
            drop(route_side); // EOF for the reader
            let mut out = Vec::new();
            Read::read_to_end(&mut client_side, &mut out).map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { e.to_string().into() })?;
            let head_end = out.windows(4).position(|w| w == b"\r\n\r\n").ok_or("route wrote no header terminator")?;
            if std::str::from_utf8(&out[..head_end]).unwrap_or("").to_ascii_lowercase().contains("transfer-encoding: chunked") {
                return Err("chunked response leaked into the pilot".into());
            }
            let head = out[..head_end].to_vec();
            let body_bytes = out[head_end + 4..].to_vec();
            let text = String::from_utf8_lossy(&head);
            let mut lines = text.split("\r\n");
            let status_line = lines.next().unwrap_or_default();
            let status: u16 = status_line.split_whitespace().nth(1).and_then(|s| s.parse().ok()).ok_or_else(|| format!("bad status line: {status_line:?}"))?;
            let mut builder = hyper::Response::builder().status(status);
            let mut closing = matches!(next, super::api::Next::Close);
            let mut has_connection = false;
            for line in lines {
                let Some((k, v)) = line.split_once(':') else { continue };
                let (k, v) = (k.trim(), v.trim());
                if k.eq_ignore_ascii_case("connection") {
                    has_connection = true;
                    closing = v.eq_ignore_ascii_case("close");
                }
                builder = builder.header(k, v);
            }
            if closing && !has_connection {
                builder = builder.header("connection", "close");
            }
            let body = Full { bytes: Some(hyper::body::Bytes::from(body_bytes)) };
            Ok(builder.body(body).map_err(|e| -> Box<dyn std::error::Error + Send + Sync> { e.to_string().into() })?)
        })
    }
}

/// Serves one accepted connection; the accept loop calls this instead of
/// `api::serve` when the first line is not a streaming route.
pub fn serve_conn(conn: UnixStream, engine: Arc<Engine>) -> io::Result<()> {
    conn.set_nonblocking(true)?;
    let io = h12tiny_core::io::FuturesIo::new(async_net::unix::UnixStream::try_from(conn)?);
    let service = Pilot { engine };
    let exec = h12tiny_core::runtime::BoxExecutor::new(h12tiny_core::runtime::FnExecutor::new(|f| {
        std::thread::spawn(move || {
            let _ = futures_lite::future::block_on(f);
        });
    }));
    let builder = h12tiny_server::conn::auto::Builder::new(exec).http1_only();
    let conn = builder.serve_connection(io, service);
    futures_lite::future::block_on(conn).map_err(|e| io::Error::other(e.to_string()))
}
