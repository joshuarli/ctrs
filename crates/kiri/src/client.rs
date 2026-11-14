//! `kiri` subcommands talk to `kiri daemon` the way the docker CLI does: HTTP
//! over the daemon's unix socket. One short connection per request, and one
//! long-lived one for `/events`.

use std::io::{self, BufRead, BufReader, Read, Write};
use std::os::unix::net::UnixStream;
use std::path::PathBuf;
use std::time::Duration;

use serde_json::Value;

pub fn socket() -> io::Result<PathBuf> {
    if let Some(s) = std::env::var_os("KIRI_SOCKET") {
        return Ok(PathBuf::from(s));
    }
    // Linux: a `kiri.service`-style system unit's socket, when present.
    #[cfg(target_os = "linux")]
    if std::path::Path::new(SERVICE_SOCKET).exists() {
        return Ok(PathBuf::from(SERVICE_SOCKET));
    }
    let home = std::env::var_os("HOME").map(PathBuf::from).ok_or_else(|| io::Error::other("HOME is not set"))?;
    Ok(home.join(".kiri").join("run/docker.sock"))
}

/// Where the Linux service's engine listens, for members of the `kiri` group.
#[cfg(target_os = "linux")]
pub const SERVICE_SOCKET: &str = "/run/kiri/docker.sock";

/// An answer: status and body.
pub struct Response {
    pub status: u16,
    pub body: Vec<u8>,
}

impl Response {
    pub fn json(&self) -> Value {
        serde_json::from_slice(&self.body).unwrap_or(Value::Null)
    }

    /// The daemon's `{"message": …}` on failure, or the body as text.
    pub fn error(&self) -> String {
        self.json()["message"].as_str().map(str::to_owned).unwrap_or_else(|| String::from_utf8_lossy(&self.body).into_owned())
    }

    pub fn ok(&self) -> bool {
        (200..300).contains(&self.status)
    }
}

fn connect(timeout: Option<Duration>) -> io::Result<UnixStream> {
    let s = UnixStream::connect(socket()?)?;
    s.set_read_timeout(timeout)?;
    Ok(s)
}

fn head(r: &mut impl BufRead) -> io::Result<(u16, Option<usize>, bool)> {
    let mut line = String::new();
    r.read_line(&mut line)?;
    let status = line.split_whitespace().nth(1).and_then(|s| s.parse().ok()).ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "bad status line"))?;
    let (mut len, mut chunked) = (None, false);
    loop {
        line.clear();
        if r.read_line(&mut line)? == 0 {
            break;
        }
        let l = line.trim_end();
        if l.is_empty() {
            break;
        }
        if let Some((k, v)) = l.split_once(':') {
            match k.to_ascii_lowercase().as_str() {
                "content-length" => len = v.trim().parse().ok(),
                "transfer-encoding" => chunked = v.trim().eq_ignore_ascii_case("chunked"),
                _ => {}
            }
        }
    }
    Ok((status, len, chunked))
}

/// Reads one chunk of a chunked body; `None` at the end.
fn chunk(r: &mut impl BufRead) -> io::Result<Option<Vec<u8>>> {
    let mut line = String::new();
    if r.read_line(&mut line)? == 0 {
        return Ok(None);
    }
    let n = usize::from_str_radix(line.trim().split(';').next().unwrap_or(""), 16).map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "bad chunk"))?;
    if n == 0 {
        return Ok(None);
    }
    let mut buf = vec![0; n + 2];
    r.read_exact(&mut buf)?;
    buf.truncate(n);
    Ok(Some(buf))
}

/// One request; the whole body is read, chunked or not.
pub fn request(method: &str, path: &str, body: Option<&Value>) -> io::Result<Response> {
    send(method, path, body, "")
}

/// A GET the window makes on its own (status, lists): it doesn't count as
/// use, so it never keeps an idle VM awake.
pub fn get_background(path: &str) -> io::Result<Value> {
    let r = send("GET", path, None, "X-Kiri-Background: 1\r\n")?;
    if !r.ok() {
        return Err(io::Error::other(r.error()));
    }
    Ok(r.json())
}

fn send(method: &str, path: &str, body: Option<&Value>, extra: &str) -> io::Result<Response> {
    let mut s = connect(Some(Duration::from_secs(120)))?;
    let payload = body.map(Value::to_string).unwrap_or_default();
    // The window's action this is part of, for the engine's log lines.
    let op = crate::diag::op_header();
    write!(
        s,
        "{method} {path} HTTP/1.1\r\nHost: kiri\r\nConnection: close\r\n{extra}{op}Content-Type: application/json\r\nContent-Length: {}\r\n\r\n{payload}",
        payload.len()
    )?;
    let mut r = BufReader::new(s);
    let (status, len, chunked) = head(&mut r)?;
    let mut body = Vec::new();
    // These never have a body, and the daemon keeps the connection open.
    if status == 204 || status == 304 {
        return Ok(Response { status, body });
    }
    if chunked {
        while let Some(c) = chunk(&mut r)? {
            body.extend_from_slice(&c);
        }
    } else if let Some(n) = len {
        body.resize(n, 0);
        r.read_exact(&mut body)?;
    } else {
        r.read_to_end(&mut body)?;
    }
    Ok(Response { status, body })
}

pub fn alive() -> bool {
    send("GET", "/_ping", None, "X-Kiri-Background: 1\r\n").is_ok_and(|r| r.ok())
}

/// A POST whose answer is JSON lines arriving over time (a pull's
/// progress): `on_line` sees each as it comes. Returns the HTTP status.
/// `auth` is a registry sign-in for a pull (`X-Registry-Auth`, base64url).
/// `opened` gets the connection once it is made, so another thread can
/// shut it down to stop the request (Cancel on a pull).
pub fn docker_cli() -> Option<PathBuf> {
    let on_path = std::env::var_os("PATH").and_then(|p| std::env::split_paths(&p).map(|d| d.join("docker")).find(|d| d.is_file()));
    on_path.or_else(|| {
        let exe = std::env::current_exe().ok()?.canonicalize().ok()?;
        Some(exe.parent()?.join("docker")).filter(|d| d.is_file())
    })
}
