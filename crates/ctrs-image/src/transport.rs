//! The HTTP transport for the registry client.
//!
//! Everything above this module is transport-agnostic: the bearer-auth
//! dance, the token and manifest caches, digest verification, multiarch
//! selection, blob resume over `Range`. The backend is h12tiny-client-sync
//! 0.9.0 with explicit Graviola + platform trust roots (fails closed if the
//! trust store is unreadable). No pool (every request pays TCP+TLS), no
//! proxy, no automatic redirects — this module resolves them, at most five
//! hops, dropping `Authorization` on every hop. The owner picked this
//! transport for stack coherence over measured pull speed (see
//! docs/evidence/registry.md; the previous incumbent, ureq with a Happy
//! Eyeballs connector and a process-wide pool, was deleted with it).
//!
//! Response bodies are consumed either wholesale with a limit
//! (`bytes`/`text`) or streamed (`into_reader`, for blobs).

use std::io::{self, Read};
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

/// How long one blocking body read may wait, before a stalled download
/// is resumed from where it got to.
const STALL: Duration = Duration::from_secs(60);

use crate::cancel::{Cancel, RegisteredBody};
use crate::registry::Error;

pub(crate) enum Body {
    Empty,
    /// `application/x-www-form-urlencoded`; the content type is implied.
    Form(Vec<(String, String)>),
    Bytes(Vec<u8>),
    /// Streamed from disk; reopened on each redirect hop. The length is
    /// read from the opened file.
    File { path: PathBuf, content_type: Option<&'static str> },
}

pub(crate) struct Request {
    pub method: &'static str,
    pub url: String,
    pub headers: Vec<(String, String)>,
    pub body: Body,
}

impl Request {
    pub fn get(url: String) -> Request {
        Request { method: "GET", url, headers: Vec::new(), body: Body::Empty }
    }
    pub fn header(mut self, name: &str, value: impl Into<String>) -> Request {
        self.headers.push((name.to_owned(), value.into()));
        self
    }
}

/// A response's head, with its body still attached.
pub(crate) struct Response {
    pub status: u16,
    headers: Vec<(String, String)>,
    body: Option<Box<dyn Read + Send>>,
}

struct ResponseReader {
    body: h12tiny_client_sync::ResponseBody,
    _registered: Option<RegisteredBody>,
}

impl Read for ResponseReader {
    fn read(&mut self, output: &mut [u8]) -> io::Result<usize> {
        self.body.read(output)
    }
}

impl Response {
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers.iter().find(|(k, _)| k.eq_ignore_ascii_case(name)).map(|(_, v)| v.as_str())
    }

    /// The whole body, bounded at `limit` bytes.
    pub fn bytes(self, limit: u64) -> io::Result<Vec<u8>> {
        let mut body = self.into_reader().take(limit + 1);
        let mut buf = Vec::new();
        body.read_to_end(&mut buf)?;
        if buf.len() as u64 > limit {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "body exceeds limit"));
        }
        Ok(buf)
    }

    pub fn text(self, limit: u64) -> io::Result<String> {
        let bytes = self.bytes(limit)?;
        String::from_utf8(bytes).map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "body is not utf-8"))
    }

    pub fn into_reader(mut self) -> Box<dyn Read + Send> {
        self.body.take().expect("body read once")
    }

    /// Reads (at most 64 KiB of) the body and discards it, so the connection
    /// can be reused; h12tiny drops the body instead, which closes it.
    pub fn discard(self) {
        let _ = self.into_reader().take(64 << 10).read_to_end(&mut Vec::new());
    }
}

/// `application/x-www-form-urlencoded` values and query parameters.
pub(crate) fn uri_encode(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for byte in s.bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => out.push(byte as char),
            _ => out.push_str(&format!("%{byte:02X}")),
        }
    }
    out
}

/// Appends a query string, or replaces what is there only when `params`
/// is empty and the caller wants one.
pub(crate) fn with_query(url: &str, params: &[(&str, &str)]) -> String {
    if params.is_empty() {
        return url.to_owned();
    }
    let (base, existing) = url.split_once('?').unwrap_or((url, ""));
    let mut pairs: Vec<String> = Vec::new();
    if !existing.is_empty() {
        pairs.push(existing.to_owned());
    }
    for (k, v) in params {
        pairs.push(format!("{}={}", uri_encode(k), uri_encode(v)));
    }
    format!("{base}?{}", pairs.join("&"))
}

#[derive(Clone)]
pub(crate) struct Transport(Arc<H12TinyClient>);

pub(crate) struct H12TinyClient {
    client: h12tiny_client_sync::Client,
    /// How long one blocking body read may wait; blob downloads resume from
    /// where they stopped after a stall.
    stall: Duration,
}

impl std::fmt::Debug for Transport {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("Transport(h12tiny)")
    }
}

impl Transport {
    pub fn send(&self, req: Request) -> Result<Response, Error> {
        h12tiny_send(&self.0, req)
    }

    #[cfg(test)]
    pub fn test_h12tiny(stall: Duration) -> Transport {
        let tls = h12tiny_client_sync::ClientTlsConfigBuilder::new().build().expect("system trust store loads");
        let client = h12tiny_client_sync::Client::builder().connect_timeout(stall).expect("connect timeout").tls_config(tls).build();
        Transport(Arc::new(H12TinyClient { client, stall }))
    }

    /// The shared transport; the trust store is read once. A store that
    /// cannot be read fails every HTTPS request, never silently widened to
    /// embedded roots.
    pub fn shared_h12tiny() -> Transport {
        static T: std::sync::OnceLock<Transport> = std::sync::OnceLock::new();
        T.get_or_init(|| {
            let stall = STALL;
            match h12tiny_client_sync::ClientTlsConfigBuilder::new().build() {
                Ok(tls) => {
                    let client = h12tiny_client_sync::Client::builder().connect_timeout(Duration::from_secs(15)).expect("connect timeout").tls_config(tls).build();
                    Transport(Arc::new(H12TinyClient { client, stall }))
                }
                Err(e) => {
                    eprintln!("ctrs: h12tiny trust store unavailable ({e}); HTTPS registry requests will fail");
                    let client = h12tiny_client_sync::Client::builder().connect_timeout(Duration::from_secs(15)).expect("connect timeout").build();
                    Transport(Arc::new(H12TinyClient { client, stall }))
                }
            }
        })
        .clone()
    }
}

const H12_MAX_REDIRECTS: usize = 5;

fn resolve_redirect(base: &str, location: &str) -> Result<String, Error> {
    let location = location.trim();
    if location.starts_with("http://") || location.starts_with("https://") {
        return Ok(location.to_owned());
    }
    let (scheme, rest) = base.split_once("://").ok_or_else(|| Error::Http("redirect base is not absolute".into()))?;
    let authority = rest.split('/').next().ok_or_else(|| Error::Http("redirect base has no authority".into()))?;
    if let Some(abs) = location.strip_prefix('/') {
        return Ok(format!("{scheme}://{authority}/{abs}"));
    }
    let path = &rest[authority.len()..];
    let dir = match path.rfind('/') {
        Some(i) => &path[..=i],
        None => "/",
    };
    Ok(format!("{scheme}://{authority}{dir}{location}"))
}

fn h12tiny_send(h12: &H12TinyClient, req: Request) -> Result<Response, Error> {
    use http::header::{AUTHORIZATION, CONTENT_LENGTH, CONTENT_TYPE, TRANSFER_ENCODING};
    let mut method = req.method;
    let mut url = req.url;
    let mut headers = req.headers;
    let mut body = req.body;

    for _ in 0..=H12_MAX_REDIRECTS {
        let hmethod = http::Method::from_bytes(method.as_bytes()).map_err(|_| Error::Http(format!("unsupported method {method}")))?;
        let mut builder = http::Request::builder().method(hmethod).uri(&url);
        for (k, v) in &headers {
            let name = http::HeaderName::from_bytes(k.as_bytes()).map_err(|e| Error::Http(format!("header name {k}: {e}")))?;
            let value = http::HeaderValue::from_str(v).map_err(|e| Error::Http(format!("header {k}: {e}")))?;
            builder = builder.header(name, value);
        }

        let buffered = |builder: http::request::Builder, bytes: Vec<u8>| -> Result<http::Response<h12tiny_client_sync::ResponseBody>, Error> {
            let request = builder.body(bytes).map_err(|e| Error::Http(e.to_string()))?;
            h12.client.request(request).map_err(Error::from)
        };

        let response = match &mut body {
            Body::Empty => buffered(builder, Vec::new())?,
            Body::Form(form) => {
                let mut encoded = String::new();
                for (i, (k, v)) in form.iter().enumerate() {
                    if i > 0 {
                        encoded.push('&');
                    }
                    encoded.push_str(&uri_encode(k));
                    encoded.push('=');
                    encoded.push_str(&uri_encode(v));
                }
                if !headers.iter().any(|(k, _)| k.eq_ignore_ascii_case("content-type")) {
                    builder = builder.header(http::header::CONTENT_TYPE, "application/x-www-form-urlencoded");
                }
                buffered(builder, encoded.into_bytes())?
            }
            Body::Bytes(bytes) => buffered(builder, bytes.clone())?,
            Body::File { path, content_type } => {
                let f = std::fs::File::open(path).map_err(Error::Io)?;
                let len = f.metadata().map_err(Error::Io)?.len();
                if let Some(ct) = content_type
                    && !headers.iter().any(|(k, _)| k.eq_ignore_ascii_case("content-type"))
                {
                    builder = builder.header(CONTENT_TYPE, *ct);
                }
                let request = builder.body(f).map_err(|e| Error::Http(e.to_string()))?;
                h12.client.request_streaming(request, len, None).map_err(Error::from)?
            }
        };

        let status = response.status().as_u16();
        let response_headers: Vec<(String, String)> = response.headers().iter().map(|(k, v)| (k.as_str().to_owned(), v.to_str().unwrap_or_default().to_owned())).collect();
        if matches!(status, 301 | 302 | 303 | 307 | 308)
            && let Some(location) = response_headers.iter().find(|(k, _)| k.eq_ignore_ascii_case("location")).map(|(_, v)| v.clone())
        {
            let new_url = resolve_redirect(&url, &location)?;
            // Never forward credentials across a redirect hop; the auth
            // header names the previous origin, so drop it on every hop.
            headers.retain(|(k, _)| !k.eq_ignore_ascii_case(AUTHORIZATION.as_str()));
            if matches!(status, 301..=303) && method != "HEAD" {
                method = "GET";
                body = Body::Empty;
                headers.retain(|(k, _)| {
                    let l = k.to_ascii_lowercase();
                    l != CONTENT_LENGTH.as_str() && l != TRANSFER_ENCODING.as_str() && l != CONTENT_TYPE.as_str()
                });
            }
            url = new_url;
            continue;
        }

        let mut body = response.into_body();
        let _ = body.set_read_timeout(Some(h12.stall));
        let registered = if body.is_complete() { None } else { Cancel::register_body(&body)? };
        let reader = Box::new(ResponseReader { body, _registered: registered });
        return Ok(Response { status, headers: response_headers, body: Some(reader) });
    }
    Err(Error::Http(format!("too many redirects (more than {H12_MAX_REDIRECTS})")))
}

impl From<h12tiny_client_sync::Error> for Error {
    fn from(e: h12tiny_client_sync::Error) -> Self {
        Error::Http(format!("h12tiny {:?}: {e}", e.kind()))
    }
}
