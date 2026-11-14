//! The HTTP transport seam for the registry client (CTRS-16 pilot).
//!
//! Everything above this module is transport-agnostic: the bearer-auth
//! dance, the token and manifest caches, digest verification, multiarch
//! selection, blob resume over `Range`. Two backends:
//!
//! - `ureq` (always compiled): the incumbent — Happy Eyeballs via
//!   [`crate::connect`], a process-wide connection pool, redirects followed
//!   by ureq itself (`RedirectAuthHeaders::Never`: no auth across hops).
//! - `h12tiny` (feature `h12tiny`): h12tiny-client-sync 0.9.0 with explicit
//!   Graviola + platform trust roots (fails closed if the trust store is
//!   unreadable). No pool (every request pays TCP+TLS), no proxy, no
//!   automatic redirects — this module resolves them, at most five hops,
//!   dropping `Authorization` on every hop. Measured for CTRS-16;
//!   experimental, not for production.
//!
//! Response bodies are consumed either wholesale with a limit
//! (`bytes`/`text`) or streamed (`into_reader`, for blobs).

use std::io::{self, Read};
use std::path::PathBuf;
#[cfg(feature = "h12tiny")]
use std::sync::Arc;
#[cfg(any(test, feature = "h12tiny"))]
use std::time::Duration;

/// How long one blocking body read may wait, before a stalled download
/// is resumed from where it got to.
#[cfg(feature = "h12tiny")]
const STALL: Duration = Duration::from_secs(60);

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
pub(crate) enum Transport {
    #[cfg(any(test, not(feature = "h12tiny")))]
    Ureq(ureq::Agent),
    #[cfg(feature = "h12tiny")]
    H12Tiny(Arc<H12TinyClient>),
}

#[cfg(feature = "h12tiny")]
pub(crate) struct H12TinyClient {
    client: h12tiny_client_sync::Client,
    /// How long one blocking body read may wait; blob downloads resume from
    /// where they stopped after a stall.
    stall: Duration,
}

impl std::fmt::Debug for Transport {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            #[cfg(any(test, not(feature = "h12tiny")))]
            Transport::Ureq(_) => f.write_str("Transport::Ureq"),
            #[cfg(feature = "h12tiny")]
            Transport::H12Tiny(_) => f.write_str("Transport::H12Tiny"),
        }
    }
}

impl Transport {
    /// Which backend this is, for tests and evidence.
    #[cfg(test)]
    pub fn name(&self) -> &'static str {
        match self {
            #[cfg(any(test, not(feature = "h12tiny")))]
            Transport::Ureq(_) => "ureq",
            #[cfg(feature = "h12tiny")]
            Transport::H12Tiny(_) => "h12tiny",
        }
    }

    /// Whether warming the pool ahead of a pull is worth doing (ureq: two
    /// `/v2/` connections pay off once reused; h12tiny: connections do not
    /// survive their body, so only the token pre-fetch matters).
    pub fn warms_pool(&self) -> bool {
        #[cfg(feature = "h12tiny")]
        {
            false
        }
        #[cfg(not(feature = "h12tiny"))]
        {
            true
        }
    }

    pub fn send(&self, req: Request) -> Result<Response, Error> {
        match self {
            #[cfg(any(test, not(feature = "h12tiny")))]
            Transport::Ureq(agent) => ureq_send(agent, req),
            #[cfg(feature = "h12tiny")]
            Transport::H12Tiny(h12) => h12tiny_send(h12, req),
        }
    }

    /// The test client: Happy Eyeballs with a short budget, against a
    /// loopback registry.
    #[cfg(test)]
    pub fn test_ureq(stall: Duration) -> Transport {
        let cfg = ureq::Agent::config_builder().http_status_as_error(false).build();
        let agent = ureq::Agent::with_parts(cfg, crate::connect::connector_with(stall), ureq::unversioned::resolver::DefaultResolver::default());
        Transport::Ureq(agent)
    }

    #[cfg(all(test, feature = "h12tiny"))]
    pub fn test_h12tiny(stall: Duration) -> Transport {
        let tls = h12tiny_client_sync::ClientTlsConfigBuilder::new().build().expect("system trust store loads");
        let client = h12tiny_client_sync::Client::builder().connect_timeout(stall).expect("connect timeout").tls_config(tls).build();
        Transport::H12Tiny(Arc::new(H12TinyClient { client, stall }))
    }

    /// The shared h12tiny transport; the trust store is read once. A store
    /// that cannot be read fails every HTTPS request, never silently
    /// widened to embedded roots.
    #[cfg(feature = "h12tiny")]
    pub fn shared_h12tiny() -> Transport {
        static T: std::sync::OnceLock<Transport> = std::sync::OnceLock::new();
        T.get_or_init(|| {
            let stall = STALL;
            match h12tiny_client_sync::ClientTlsConfigBuilder::new().build() {
                Ok(tls) => {
                    let client = h12tiny_client_sync::Client::builder().connect_timeout(Duration::from_secs(15)).expect("connect timeout").tls_config(tls).build();
                    Transport::H12Tiny(Arc::new(H12TinyClient { client, stall }))
                }
                Err(e) => {
                    eprintln!("kiri: h12tiny trust store unavailable ({e}); HTTPS registry requests will fail");
                    let client = h12tiny_client_sync::Client::builder().connect_timeout(Duration::from_secs(15)).expect("connect timeout").build();
                    Transport::H12Tiny(Arc::new(H12TinyClient { client, stall }))
                }
            }
        })
        .clone()
    }
}

#[cfg(any(test, not(feature = "h12tiny")))]
fn collect_ureq_headers(resp: &ureq::http::Response<ureq::Body>) -> Vec<(String, String)> {
    resp.headers().iter().map(|(k, v)| (k.as_str().to_owned(), v.to_str().unwrap_or_default().to_owned())).collect()
}

/// Ureq transport errors travel inside `Error::Io` so `transient` and
/// `stale` can downcast them (with the timeout and connection-reset kinds
/// intact), exactly as they did before the seam.
#[cfg(any(test, not(feature = "h12tiny")))]
fn map_ureq(e: ureq::Error) -> Error {
    Error::Io(io::Error::other(e))
}

#[cfg(any(test, not(feature = "h12tiny")))]
fn finish_ureq(resp: ureq::http::Response<ureq::Body>) -> Result<Response, Error> {
    let status = resp.status().as_u16();
    let headers = collect_ureq_headers(&resp);
    let reader = resp.into_parts().1.into_reader();
    Ok(Response { status, headers, body: Some(Box::new(reader)) })
}

#[cfg(any(test, not(feature = "h12tiny")))]
fn ureq_send(agent: &ureq::Agent, req: Request) -> Result<Response, Error> {
    let with_headers = |mut r: ureq::RequestBuilder<ureq::typestate::WithoutBody>| -> ureq::RequestBuilder<ureq::typestate::WithoutBody> {
        for (k, v) in &req.headers {
            r = r.header(k, v);
        }
        r
    };
    match (req.method, req.body) {
        ("GET", Body::Empty) => finish_ureq(with_headers(agent.get(&req.url)).call().map_err(map_ureq)?),
        ("HEAD", Body::Empty) => finish_ureq(with_headers(agent.head(&req.url)).call().map_err(map_ureq)?),
        ("POST", Body::Empty) => {
            let with_headers = |mut r: ureq::RequestBuilder<ureq::typestate::WithBody>| -> ureq::RequestBuilder<ureq::typestate::WithBody> {
                for (k, v) in &req.headers {
                    r = r.header(k, v);
                }
                r
            };
            finish_ureq(with_headers(agent.post(&req.url)).send_empty().map_err(map_ureq)?)
        }
        ("POST", Body::Form(form)) => {
            let with_headers = |mut r: ureq::RequestBuilder<ureq::typestate::WithBody>| -> ureq::RequestBuilder<ureq::typestate::WithBody> {
                for (k, v) in &req.headers {
                    r = r.header(k, v);
                }
                r
            };
            let encoded: Vec<(&str, &str)> = form.iter().map(|(k, v)| (k.as_str(), v.as_str())).collect();
            finish_ureq(with_headers(agent.post(&req.url)).send_form(encoded).map_err(map_ureq)?)
        }
        ("POST" | "PUT", Body::Bytes(bytes)) => {
            let with_headers = |mut r: ureq::RequestBuilder<ureq::typestate::WithBody>| -> ureq::RequestBuilder<ureq::typestate::WithBody> {
                for (k, v) in &req.headers {
                    r = r.header(k, v);
                }
                r
            };
            let r = with_headers(if req.method == "POST" { agent.post(&req.url) } else { agent.put(&req.url) });
            finish_ureq(r.send(&bytes[..]).map_err(map_ureq)?)
        }
        ("PUT", Body::File { path, content_type }) => {
            let mut f = std::fs::File::open(&path).map_err(Error::Io)?;
            let with_headers = |mut r: ureq::RequestBuilder<ureq::typestate::WithBody>| -> ureq::RequestBuilder<ureq::typestate::WithBody> {
                for (k, v) in &req.headers {
                    r = r.header(k, v);
                }
                r
            };
            let mut r = with_headers(agent.put(&req.url));
            if let Some(ct) = content_type
                && !req.headers.iter().any(|(k, _)| k.eq_ignore_ascii_case("content-type"))
            {
                r = r.header("Content-Type", ct);
            }
            finish_ureq(r.send(ureq::SendBody::from_reader(&mut f)).map_err(map_ureq)?)
        }
        (method, _) => Err(Error::Http(format!("unsupported request {method} in the transport"))),
    }
}

#[cfg(feature = "h12tiny")]
const H12_MAX_REDIRECTS: usize = 5;

#[cfg(feature = "h12tiny")]
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

#[cfg(feature = "h12tiny")]
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
        let mut it = response.into_body();
        let _ = it.set_read_timeout(Some(h12.stall));
        let reader: Box<dyn Read + Send> = Box::new(it);

        if matches!(status, 301 | 302 | 303 | 307 | 308)
            && let Some(location) = response_headers.iter().find(|(k, _)| k.eq_ignore_ascii_case("location")).map(|(_, v)| v.clone())
        {
            let new_url = resolve_redirect(&url, &location)?;
            // Never forward credentials across a redirect hop (ureq's
            // `RedirectAuthHeaders::Never`); the auth header names the
            // previous origin, so drop it on every hop.
            headers.retain(|(k, _)| !k.eq_ignore_ascii_case(AUTHORIZATION.as_str()));
            if matches!(status, 301 | 302 | 303) && method != "HEAD" {
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

        return Ok(Response { status, headers: response_headers, body: Some(reader) });
    }
    Err(Error::Http(format!("too many redirects (more than {H12_MAX_REDIRECTS})")))
}

#[cfg(feature = "h12tiny")]
impl From<h12tiny_client_sync::Error> for Error {
    fn from(e: h12tiny_client_sync::Error) -> Self {
        Error::Http(format!("h12tiny {:?}: {e}", e.kind()))
    }
}
