//! ctrs's images as a registry, for its BuildKit: `FROM myapp:dev` (an
//! image built or loaded here, never pushed) works as it does with Docker.
//!
//! A read-only registry API on 127.0.0.1, which containers reach at
//! host.docker.internal. buildkitd.toml names it as a mirror of every
//! registry ctrs has images from; a mirror that answers 404 is skipped, so
//! anything not here comes from the registry itself. Paths carry a secret
//! (`/v2/<token>/<registry>/<repo>/…`), so other local users can't read
//! images through it. Manifests are made from the store's records (layers,
//! config), the same bytes for the same image every time.

use std::collections::HashMap;
use std::io::{self, BufRead, BufReader, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::{Arc, Mutex, OnceLock, Weak};
use std::time::Duration;

use serde_json::{Value, json};

use ctrs_image::{Image, Reference};

use super::engine::Engine;

/// Tried first, so a builder started by buildx after a daemon restart still
/// finds the mirror its config names.
const PORT: u16 = 47_391;

static LISTENING: OnceLock<Option<u16>> = OnceLock::new();

/// Push state, all keyed off the secret path token's builds: manifest
/// digest → manifest bytes (so a pushed index can resolve its children),
/// image name → the manifest digest it was recorded from, repo → the
/// image names pushes produced, `repo:ref` → the manifest digest an
/// index's tag selected, and upload uuid → its temp file.
static PUSH_MANIFESTS: OnceLock<Mutex<HashMap<String, Vec<u8>>>> = OnceLock::new();
static PUSH_IMAGE_MANIFEST: OnceLock<Mutex<HashMap<String, String>>> = OnceLock::new();
static PUSH_IMAGES: OnceLock<Mutex<HashMap<String, Vec<String>>>> = OnceLock::new();
static PUSH_INDEX_PICK: OnceLock<Mutex<HashMap<String, String>>> = OnceLock::new();
static PUSH_REFS: OnceLock<Mutex<HashMap<String, String>>> = OnceLock::new();
static PUSH_UPLOADS: OnceLock<Mutex<HashMap<String, PathBuf>>> = OnceLock::new();

fn manifests() -> &'static Mutex<HashMap<String, Vec<u8>>> {
    PUSH_MANIFESTS.get_or_init(|| Mutex::new(HashMap::new()))
}
fn image_manifests() -> &'static Mutex<HashMap<String, String>> {
    PUSH_IMAGE_MANIFEST.get_or_init(|| Mutex::new(HashMap::new()))
}
fn push_images() -> &'static Mutex<HashMap<String, Vec<String>>> {
    PUSH_IMAGES.get_or_init(|| Mutex::new(HashMap::new()))
}
fn index_picks() -> &'static Mutex<HashMap<String, String>> {
    PUSH_INDEX_PICK.get_or_init(|| Mutex::new(HashMap::new()))
}
fn refs() -> &'static Mutex<HashMap<String, String>> {
    PUSH_REFS.get_or_init(|| Mutex::new(HashMap::new()))
}
fn uploads() -> &'static Mutex<HashMap<String, PathBuf>> {
    PUSH_UPLOADS.get_or_init(|| Mutex::new(HashMap::new()))
}

/// The mirror's secret path segment, kept in the state directory so it
/// survives restarts (the builder's config keeps naming it).
fn token() -> String {
    static TOKEN: OnceLock<String> = OnceLock::new();
    TOKEN
        .get_or_init(|| {
            let path = super::state_dir().ok().map(|d| d.join("build-mirror-token"));
            if let Some(t) = path.as_ref().and_then(|p| std::fs::read_to_string(p).ok()).map(|t| t.trim().to_owned()).filter(|t| t.len() == 32) {
                return t;
            }
            let t = super::engine::random_hex(16);
            if let Some(p) = path {
                let _ = save_token(&p, &t);
            }
            t
        })
        .clone()
}

/// Writes the token readable by its owner only from the moment the file
/// exists: written and then chmod-ed, it was the umask's 0644 in between,
/// and other local users could read it there.
fn save_token(path: &std::path::Path, token: &str) -> io::Result<()> {
    use std::os::unix::fs::OpenOptionsExt;
    // One already there (not a valid token) is replaced, mode and all.
    let _ = std::fs::remove_file(path);
    std::fs::OpenOptions::new().write(true).create_new(true).mode(0o600).open(path)?.write_all(token.as_bytes())
}

/// Starts the server (at the daemon's start: a listening socket costs
/// nothing while no build asks).
pub fn start(engine: &Arc<Engine>) {
    LISTENING.get_or_init(|| {
        let wanted = PORT;
        let listener = TcpListener::bind(("127.0.0.1", wanted)).or_else(|_| TcpListener::bind(("127.0.0.1", 0))).ok()?;
        let port = listener.local_addr().ok()?.port();
        let me = Arc::downgrade(engine);
        // On a Linux host the builder reaches the mirror at the default
        // bridge's gateway (mirror_host): containers have no way to the
        // host's loopback there, so it listens on that address too.
        #[cfg(target_os = "linux")]
        if let Some(gateway) = bridge_gateway(&engine.lock_net()) {
            match bind_freely(gateway, port) {
                Ok(l) => {
                    let me = me.clone();
                    let _ = std::thread::Builder::new().name("ctrs-build-mirror".into()).spawn(move || serve(l, me));
                }
                Err(e) => crate::diag::warn!("image mirror not on the bridge; builds pull from registries", error = e),
            }
        }
        std::thread::Builder::new().name("ctrs-build-mirror".into()).spawn(move || serve(listener, me)).ok()?;
        crate::diag::info!("image mirror for builds", port = port);
        Some(port)
    });
    // Upload temp files cannot outlive the process that owned them.
    sweep_uploads(engine, None);
}

/// Removes `tmp/upload.*` files: all of them at start (the upload table
/// is in-memory, so none can still be live), or only ones older than
/// `max_age` that no upload owns, on the next upload request.
fn sweep_uploads(engine: &Engine, max_age: Option<Duration>) {
    let live = uploads().lock().unwrap_or_else(|e| e.into_inner());
    let now = std::time::SystemTime::now();
    let Ok(rd) = std::fs::read_dir(engine.store.root().join("tmp")) else { return };
    for e in rd.flatten() {
        let is_upload = e.file_name().to_str().is_some_and(|n| n.starts_with("upload."));
        if !is_upload || live.values().any(|p| *p == e.path()) {
            continue;
        }
        if let Some(max) = max_age {
            let fresh = e
                .metadata()
                .and_then(|m| m.modified())
                .ok()
                .and_then(|t| now.duration_since(t).ok())
                .is_some_and(|d| d <= max);
            if fresh {
                continue;
            }
        }
        let _ = std::fs::remove_file(e.path());
    }
}

/// buildkitd.toml lines: this mirror for every registry ctrs has images
/// from (Docker Hub always), over plain HTTP.
#[cfg(target_os = "linux")]
fn mirror_host(networks: &super::network::Networks) -> String {
    bridge_gateway(networks).map_or_else(|| super::ports::HOST_ADDR.into(), super::network::ip_str)
}

/// The default bridge's gateway, which containers reach the host at.
#[cfg(target_os = "linux")]
fn bridge_gateway(networks: &super::network::Networks) -> Option<[u8; 4]> {
    networks.find("bridge").map(|n| n.gateway).filter(|g| *g != [0; 4])
}

/// A listener on `ip:port` before the address exists: the bridge (and
/// its gateway address) is made with the first container (IP_FREEBIND).
#[cfg(target_os = "linux")]
fn bind_freely(ip: [u8; 4], port: u16) -> io::Result<TcpListener> {
    use std::os::fd::{FromRawFd, OwnedFd};
    // SAFETY: plain socket creation; owned at once.
    let fd = unsafe { libc::socket(libc::AF_INET, libc::SOCK_STREAM | libc::SOCK_CLOEXEC, 0) };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: `fd` is fresh and ours.
    let sock = unsafe { OwnedFd::from_raw_fd(fd) };
    let one: libc::c_int = 1;
    for opt in [(libc::SOL_SOCKET, libc::SO_REUSEADDR), (libc::IPPROTO_IP, libc::IP_FREEBIND)] {
        // SAFETY: setsockopt with an int of the stated size on a socket we own.
        if unsafe { libc::setsockopt(fd, opt.0, opt.1, (&one as *const libc::c_int).cast(), std::mem::size_of::<libc::c_int>() as libc::socklen_t) } != 0 {
            return Err(io::Error::last_os_error());
        }
    }
    // SAFETY: sockaddr_in is plain data; all-zero is valid, then filled in.
    let mut sin: libc::sockaddr_in = unsafe { std::mem::zeroed() };
    sin.sin_family = libc::AF_INET as libc::sa_family_t;
    sin.sin_port = port.to_be();
    sin.sin_addr.s_addr = u32::from_ne_bytes(ip);
    // SAFETY: bind and listen on our socket with a sockaddr_in of its size.
    unsafe {
        if libc::bind(fd, (&sin as *const libc::sockaddr_in).cast(), std::mem::size_of::<libc::sockaddr_in>() as libc::socklen_t) != 0 || libc::listen(fd, 128) != 0 {
            return Err(io::Error::last_os_error());
        }
    }
    Ok(TcpListener::from(sock))
}

#[cfg(not(target_os = "linux"))]
fn mirror_host(_networks: &super::network::Networks) -> String {
    super::ports::HOST_ADDR.into()
}

/// The port the mirror listens on, once started.
pub fn port() -> Option<u16> {
    LISTENING.get().copied().flatten()
}

/// A unique build repo for one `docker build`: pushes land under
/// `/v2/<token>/push/<repo>/…` and are retagged when the build ends.
/// `None` when the mirror isn't listening (the caller falls back to
/// streaming the image archive).
pub fn push_repo() -> Option<String> {
    port().map(|_| format!("b{}", super::engine::random_hex(4)))
}

/// The full image reference buildkit pushes to for `repo`: the token
/// leads the repo path so requests land under `/v2/<token>/push/…`.
pub fn push_ref(engine: &Engine, repo: &str) -> Option<String> {
    Some(format!("{}:{}/{}/push/{}", host_addr(engine), port()?, token(), repo))
}

/// Forgets everything pushes to `repo` recorded; returns the image
/// names that were selected (to tag) and the ones that were not (to
/// remove).
pub fn take_pushed(repo: &str) -> (Vec<String>, Vec<String>) {
    let names = push_images().lock().unwrap_or_else(|e| e.into_inner()).remove(repo).unwrap_or_default();
    let pick = index_picks().lock().unwrap_or_else(|e| e.into_inner()).remove(&format!("{repo}:latest"));
    let mut manifests = image_manifests().lock().unwrap_or_else(|e| e.into_inner());
    let (keep, drop): (Vec<String>, Vec<String>) = names.into_iter().partition(|n| pick.is_none() || manifests.get(n) == pick.as_ref());
    for n in &drop {
        manifests.remove(n);
    }
    (keep, drop)
}

/// Where a build reaches this computer: the address `--add-host
/// x:host-gateway` gets, the one the mirror is reached at. On a Linux host
/// (and Windows' engine in WSL2) that's the default bridge's gateway, as
/// for `docker run`; 198.19.248.254 only leads anywhere in the Mac's VM.
pub fn host_addr(engine: &Engine) -> String {
    mirror_host(&engine.lock_net())
}

pub fn config(engine: &Engine) -> String {
    let Some(port) = LISTENING.get().copied().flatten() else { return String::new() };
    let host = format!("{}:{port}", mirror_host(&engine.lock_net()));
    let mut registries = vec!["docker.io".to_owned()];
    for i in engine.store.images().unwrap_or_default() {
        if let Ok(r) = Reference::parse(&i.name)
            && !registries.contains(&r.registry)
            && !ctrs_image::reference::is_local(&r.registry)
        {
            registries.push(r.registry);
        }
    }
    let token = token();
    let mut out = String::new();
    for r in registries {
        out.push_str(&format!("[registry.\"{r}\"]\n  mirrors = [\"{host}/{token}/{r}\"]\n"));
    }
    out.push_str(&format!("[registry.\"{host}\"]\n  http = true\n"));
    out
}

fn serve(listener: TcpListener, engine: Weak<Engine>) {
    for conn in listener.incoming() {
        let Ok(conn) = conn else { continue };
        let Some(engine) = engine.upgrade() else { return };
        let _ = std::thread::Builder::new().name("ctrs-build-mirror".into()).spawn(move || {
            let _ = conn.set_read_timeout(Some(Duration::from_secs(30)));
            let _ = answer(conn, &engine);
        });
    }
}

/// One request, then the connection closes.
fn answer(conn: TcpStream, engine: &Engine) -> io::Result<()> {
    // Bodies (blob uploads) are unbounded, so the reader is not capped;
// the header block is bounded by count instead.
    let mut r = BufReader::with_capacity(64 << 10, &conn);
    let mut line = String::new();
    r.read_line(&mut line)?;
    let mut parts = line.split_whitespace();
    let (method, target) = (parts.next().unwrap_or_default().to_owned(), parts.next().unwrap_or_default().to_owned());
    let mut headers = Vec::new();
    loop {
        let mut h = String::new();
        if r.read_line(&mut h)? == 0 || h.trim().is_empty() {
            break;
        }
        if headers.len() > 100 {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "too many headers"));
        }
        if let Some((k, v)) = h.split_once(':') {
            headers.push((k.trim().to_ascii_lowercase(), v.trim().to_owned()));
        }
    }
    let header = |name: &str| headers.iter().find(|(k, _)| k == name).map(|(_, v)| v.as_str());
    let mut w = &conn;
    let head = |w: &mut &TcpStream, status: &str, extra: &str, len: u64| write!(w, "HTTP/1.1 {status}\r\nConnection: close\r\nContent-Length: {len}\r\n{extra}\r\n");
    // `/v2/<token>/push/<repo>/…`: a build's image push. Blobs are
    // content-addressed, so a HEAD that finds one ends its upload.
    if let Some(push) = parse_push(target.split('?').next().unwrap_or_default(), &token()) {
        let query = target.split_once('?').map(|(_, q)| q).unwrap_or_default();
        return push_answer(&mut r, engine, &method, push, query, header("content-length").and_then(|v| v.parse().ok()), header("transfer-encoding").is_some_and(|v| v.contains("chunked")), &mut w);
    }
    if method != "GET" && method != "HEAD" {
        return head(&mut w, "405 Method Not Allowed", "", 0);
    }
    match lookup(engine, target.split('?').next().unwrap_or_default(), &token()) {
        Some(Found::Manifest(bytes, digest)) => {
            head(&mut w, "200 OK", &format!("Content-Type: application/vnd.oci.image.manifest.v1+json\r\nDocker-Content-Digest: {digest}\r\n"), bytes.len() as u64)?;
            if method == "GET" {
                w.write_all(&bytes)?;
            }
        }
        Some(Found::Blob(path, digest)) => {
            let mut f = std::fs::File::open(&path)?;
            let len = f.metadata()?.len();
            head(&mut w, "200 OK", &format!("Content-Type: application/octet-stream\r\nDocker-Content-Digest: {digest}\r\n"), len)?;
            if method == "GET" {
                io::copy(&mut f, &mut w)?;
            }
        }
        None => head(&mut w, "404 Not Found", "", 0)?,
    }
    w.flush()
}

/// A push path: `/v2/<token>/push/<repo>/blobs/<digest>`,
/// `…/blobs/uploads[/<uuid>]`, or `…/manifests/<ref>`.
#[derive(Debug, PartialEq, Eq)]
enum Push {
    Blob(String, String),
    UploadNew(String),
    Upload(String, String),
    Manifest(String, String),
}

fn parse_push(path: &str, token: &str) -> Option<Push> {
    let rest = path.strip_prefix("/v2/")?.strip_prefix(token)?.strip_prefix("/push/")?;
    if let Some(repo) = rest.strip_suffix("/blobs/uploads/").or_else(|| rest.strip_suffix("/blobs/uploads")) {
        return Some(Push::UploadNew(repo.to_owned()));
    }
    if let Some((repo, uuid)) = rest.split_once("/blobs/uploads/")
        && !uuid.is_empty()
        && !uuid.contains('/')
    {
        return Some(Push::Upload(repo.to_owned(), uuid.to_owned()));
    }
    if let Some((repo, digest)) = rest.rsplit_once("/blobs/")
        && !repo.is_empty()
        && !digest.is_empty()
        && !digest.contains('/')
    {
        return Some(Push::Blob(repo.to_owned(), digest.to_owned()));
    }
    if let Some((repo, reference)) = rest.rsplit_once("/manifests/")
        && !repo.is_empty()
        && !reference.is_empty()
        && !reference.contains('/')
    {
        return Some(Push::Manifest(repo.to_owned(), reference.to_owned()));
    }
    None
}

const MAX_MANIFEST: u64 = 8 << 20;

/// The body as a reader of exactly its bytes (content-length or
/// chunked), for `r` positioned just past the headers.
enum Body<'a, 'b> {
    Len { r: &'a mut BufReader<&'b TcpStream>, left: u64 },
    Chunked { r: &'a mut BufReader<&'b TcpStream>, line: String, left: u64 },
    Empty,
}

impl Read for Body<'_, '_> {
    fn read(&mut self, buf: &mut [u8]) -> io::Result<usize> {
        match self {
            Body::Len { r, left } => {
                if *left == 0 {
                    return Ok(0);
                }
                let want = (*left).min(buf.len() as u64) as usize;
                let n = r.read(&mut buf[..want])?;
                *left -= n as u64;
                Ok(n)
            }
            Body::Chunked { r, line, left } => {
                if *left == 0 {
                    // Next chunk header.
                    line.clear();
                    if r.read_line(line)? == 0 {
                        return Ok(0);
                    }
                    let size = usize::from_str_radix(line.trim().split(';').next().unwrap_or(""), 16).map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "bad chunk size"))? as u64;
                    if size == 0 {
                        // Trailer headers, then the empty line.
                        loop {
                            line.clear();
                            if r.read_line(line)? == 0 || line.trim().is_empty() {
                                return Ok(0);
                            }
                        }
                    }
                    *left = size;
                }
                let want = (*left).min(buf.len() as u64) as usize;
                let n = r.read(&mut buf[..want])?;
                *left -= n as u64;
                if *left == 0 {
                    // The CRLF after each chunk's data.
                    let mut crlf = [0u8; 2];
                    r.read_exact(&mut crlf)?;
                }
                Ok(n)
            }
            Body::Empty => Ok(0),
        }
    }
}

fn body<'a, 'b>(r: &'a mut BufReader<&'b TcpStream>, len: Option<u64>, chunked: bool) -> Body<'a, 'b> {
    if chunked {
        Body::Chunked { r, line: String::new(), left: 0 }
    } else if let Some(n) = len.filter(|n| *n > 0) {
        Body::Len { r, left: n }
    } else {
        Body::Empty
    }
}

fn query_param(query: &str, key: &str) -> Option<String> {
    query.split('&').find_map(|p| {
        let (k, v) = p.split_once('=')?;
        if k != key {
            return None;
        }
        // `sha256:` arrives as `sha256%3A`; blob digests need the colon back.
        let bytes = v.as_bytes();
        let mut out = Vec::with_capacity(bytes.len());
        let mut i = 0;
        while i < bytes.len() {
            if bytes[i] == b'%' && i + 2 < bytes.len() {
                if let Ok(b) = u8::from_str_radix(&v[i + 1..i + 3], 16) {
                    out.push(b);
                    i += 3;
                    continue;
                }
            }
            out.push(bytes[i]);
            i += 1;
        }
        String::from_utf8(out).ok()
    })
}

/// `/v2/<token>/push/…` requests: the OCI distribution push protocol,
/// writing blobs into the store under their digest and recording
/// manifests as images the build's caller retags.
fn push_answer(r: &mut BufReader<&TcpStream>, engine: &Engine, method: &str, push: Push, query: &str, len: Option<u64>, chunked: bool, w: &mut &TcpStream) -> io::Result<()> {
    let head = |w: &mut &TcpStream, status: &str, extra: &str, len: u64| write!(w, "HTTP/1.1 {status}\r\nConnection: close\r\nContent-Length: {len}\r\n{extra}\r\n");
    match push {
        Push::Blob(_repo, digest) => {
            if method == "HEAD" || method == "GET" {
                // Content-addressed: presence is the whole answer, whoever
                // pushed it first. Only size is unknown, so any file counts.
                let exists = engine.store.blob_path(&digest).is_ok_and(|p| p.is_file());
                if exists {
                    let size = engine.store.blob_path(&digest).ok().and_then(|p| std::fs::metadata(p).ok()).map(|m| m.len()).unwrap_or(0);
                    head(w, "200 OK", &format!("Content-Type: application/octet-stream\r\nDocker-Content-Digest: {digest}\r\n"), size)?;
                    if method == "GET" {
                        if let Ok(path) = engine.store.blob_path(&digest) {
                            io::copy(&mut std::fs::File::open(path)?, w)?;
                        }
                    }
                } else {
                    head(w, "404 Not Found", "", 0)?;
                }
            } else {
                head(w, "405 Method Not Allowed", "", 0)?;
            }
        }
        Push::UploadNew(repo) => {
            if method != "POST" {
                return head(w, "405 Method Not Allowed", "", 0);
            }
            // Monolithic POST (?digest= with the blob as the body) or a
            // mount request (?mount=, which we never satisfy: 202 starts
            // a normal upload either way).
            if let Some(digest) = query_param(query, "digest") {
                let mut ingest = engine.store.blob_writer(&digest)?;
                io::copy(&mut body(r, len, chunked), &mut ingest)?;
                let written = ingest.finish()?;
                head(w, "201 Created", &format!("Location: /v2/x/blobs/{digest}\r\nDocker-Content-Digest: {digest}\r\n"), 0)?;
                let _ = written;
                let _ = repo;
                return w.flush();
            }
            // A dropped connection leaks its upload file; ten idle minutes
            // is far past any live PATCH, so sweep those before adding one.
            sweep_uploads(engine, Some(Duration::from_secs(600)));
            let uuid = super::engine::random_hex(8);
            let path = engine.store.root().join("tmp").join(format!("upload.{uuid}"));
            std::fs::File::create(&path)?;
            uploads().lock().unwrap_or_else(|e| e.into_inner()).insert(uuid.clone(), path);
            let loc = format!("/v2/{}/push/{repo}/blobs/uploads/{uuid}", token());
            head(w, "202 Accepted", &format!("Location: {loc}\r\nDocker-Upload-UUID: {uuid}\r\nRange: 0-0\r\n"), 0)?;
        }
        Push::Upload(repo, uuid) => {
            let path = uploads().lock().unwrap_or_else(|e| e.into_inner()).get(&uuid).cloned();
            let Some(path) = path else {
                return head(w, "404 Not Found", "", 0);
            };
            match method {
                "PATCH" => {
                    let mut f = std::fs::OpenOptions::new().create(true).append(true).open(&path)?;
                    io::copy(&mut body(r, len, chunked), &mut f)?;
                    let size = f.metadata()?.len();
                    head(w, "202 Accepted", &format!("Location: /v2/{}/push/{repo}/blobs/uploads/{uuid}\r\nDocker-Upload-UUID: {uuid}\r\nRange: 0-{size}\r\n", token()), 0)?;
                }
                "PUT" => {
                    let Some(digest) = query_param(query, "digest") else {
                        return head(w, "400 Bad Request", "", 0);
                    };
                    {
                        let mut f = std::fs::OpenOptions::new().create(true).append(true).open(&path)?;
                        io::copy(&mut body(r, len, chunked), &mut f)?;
                    }
                    let mut ingest = engine.store.blob_writer(&digest)?;
                    io::copy(&mut std::fs::File::open(&path)?, &mut ingest)?;
                    ingest.finish()?;
                    uploads().lock().unwrap_or_else(|e| e.into_inner()).remove(&uuid);
                    let _ = std::fs::remove_file(&path);
                    head(w, "201 Created", &format!("Location: /v2/x/blobs/{digest}\r\nDocker-Content-Digest: {digest}\r\n"), 0)?;
                }
                _ => return head(w, "405 Method Not Allowed", "", 0),
            }
        }
        Push::Manifest(repo, reference) => match method {
            "GET" | "HEAD" => {
                // Serve what this build pushed: ref → manifest digest →
                // bytes. Anything else is not there.
                let digest = manifests_ref(&repo, &reference);
                let bytes = digest.and_then(|d| manifests().lock().unwrap_or_else(|e| e.into_inner()).get(&d).cloned());
                match bytes {
                    Some(b) => {
                        let d = ctrs_image::store::sha256_digest(&b);
                        head(w, "200 OK", &format!("Content-Type: application/vnd.oci.image.manifest.v1+json\r\nDocker-Content-Digest: {d}\r\n"), b.len() as u64)?;
                        if method == "GET" {
                            w.write_all(&b)?;
                        }
                    }
                    None => head(w, "404 Not Found", "", 0)?,
                }
            }
            "PUT" => {
                let mut bytes = Vec::new();
                body(r, len, chunked).take(MAX_MANIFEST).read_to_end(&mut bytes)?;
                record_manifest(engine, &repo, &reference, &bytes)?;
                let digest = ctrs_image::store::sha256_digest(&bytes);
                manifests_ref_insert(&repo, &reference, &digest);
                head(w, "201 Created", &format!("Docker-Content-Digest: {digest}\r\n"), 0)?;
            }
            _ => return head(w, "405 Method Not Allowed", "", 0),
        },
    }
    w.flush()
}

/// `repo:ref` → the digest of the manifest last PUT under it.
fn manifests_ref(repo: &str, reference: &str) -> Option<String> {
    if reference.starts_with("sha256:") {
        return Some(reference.to_owned());
    }
    refs().lock().unwrap_or_else(|e| e.into_inner()).get(&format!("{repo}:{reference}")).cloned()
}

fn manifests_ref_insert(repo: &str, reference: &str, digest: &str) {
    refs().lock().unwrap_or_else(|e| e.into_inner()).insert(format!("{repo}:{reference}"), digest.to_owned());
}

/// A pushed manifest: an image index resolves to its selected platform
/// manifest; an image manifest becomes an image record named after the
/// push repo and ref (the build retags it when it ends).
fn record_manifest(engine: &Engine, repo: &str, reference: &str, bytes: &[u8]) -> io::Result<()> {
    let v: Value = serde_json::from_slice(bytes).map_err(|e| io::Error::new(io::ErrorKind::InvalidData, format!("manifest: {e}")))?;
    let digest = ctrs_image::store::sha256_digest(bytes);
    manifests().lock().unwrap_or_else(|e| e.into_inner()).insert(digest.clone(), bytes.to_vec());
    if let Some(entries) = v["manifests"].as_array() {
        // An index (or manifest list): pick the entry for this host's
        // platform, skipping attestation manifests, and remember the
        // choice for `repo:ref`.
        let host = ctrs_image::Platform::host_linux();
        let pick = entries
            .iter()
            .filter(|m| m["annotations"]["vnd.docker.reference.type"].as_str() != Some("attestation-manifest"))
            .find(|m| {
                let p = &m["platform"];
                p["os"].as_str() == Some(host.os.as_str()) && p["architecture"].as_str() == Some(host.architecture.as_str())
            })
            .or_else(|| entries.iter().find(|m| m["annotations"]["vnd.docker.reference.type"].as_str() != Some("attestation-manifest")));
        if let Some(d) = pick.and_then(|m| m["digest"].as_str()) {
            index_picks().lock().unwrap_or_else(|e| e.into_inner()).insert(format!("{repo}:{reference}"), d.to_owned());
        }
        return Ok(());
    }
    // An image manifest: config + layers, already pushed as blobs.
    let config_digest = v["config"]["digest"].as_str().unwrap_or_default().to_owned();
    let config_bytes = engine.store.read_config(&config_digest)?;
    let config: Value = serde_json::from_slice(&config_bytes).map_err(|e| io::Error::new(io::ErrorKind::InvalidData, format!("image config: {e}")))?;
    let mut layers = Vec::new();
    for l in v["layers"].as_array().into_iter().flatten() {
        layers.push(ctrs_image::Layer {
            digest: l["digest"].as_str().unwrap_or_default().to_owned(),
            size: l["size"].as_u64().unwrap_or(0),
            media_type: l["mediaType"].as_str().unwrap_or_default().to_owned(),
        });
    }
    // Attestation manifests carry no layers; they are not images.
    if layers.is_empty() {
        return Ok(());
    }
    // A registry refuses a manifest whose blobs it does not have
    // (BLOB_UNKNOWN); recording one anyway would leave an image whose
    // layers can never deploy.
    for l in &layers {
        if !engine.store.has_blob(&l.digest, l.size) {
            return Err(io::Error::new(io::ErrorKind::InvalidData, format!("manifest references missing blob {}", l.digest)));
        }
    }
    // Digest refs name the image `m<hex>`; tag refs keep the tag.
    let name = if reference.starts_with("sha256:") {
        format!("{repo}:m{}", digest.get(7..23).unwrap_or(&digest))
    } else {
        format!("{repo}:{reference}")
    };
    let image = ctrs_image::archive::from_config(name.clone(), &config_digest, &config, layers)?;
    engine.store.put_image(image)?;
    image_manifests().lock().unwrap_or_else(|e| e.into_inner()).insert(name.clone(), digest);
    push_images().lock().unwrap_or_else(|e| e.into_inner()).entry(repo.to_owned()).or_default().push(name);
    Ok(())
}

#[derive(Debug)]
enum Found {
    Manifest(Vec<u8>, String),
    Blob(std::path::PathBuf, String),
}

/// An image's manifest as ctrs serves it, and its digest.
fn manifest(store: &ctrs_image::Store, i: &Image) -> Option<(Vec<u8>, String)> {
    let config_size = std::fs::metadata(store.blob_path(&i.config_digest).ok()?).ok()?.len();
    let m = json!({
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": i.config_digest, "size": config_size},
        "layers": i.layers.iter().map(|l| json!({"mediaType": l.media_type, "digest": l.digest, "size": l.size})).collect::<Vec<Value>>(),
    });
    let bytes = serde_json::to_vec(&m).ok()?;
    let digest = ctrs_image::store::sha256_digest(&bytes);
    Some((bytes, digest))
}

/// `/v2/<token>/<registry>/<repo…>/manifests/<tag|digest>` or `…/blobs/<digest>`.
fn parse(path: &str, token: &str) -> Option<(String, String, bool, String)> {
    let rest = path.strip_prefix("/v2/")?.strip_prefix(token)?.strip_prefix('/')?;
    let (registry, rest) = rest.split_once('/')?;
    let (repo, kind, reference) = if let Some((repo, r)) = rest.rsplit_once("/manifests/") {
        (repo, true, r)
    } else {
        let (repo, r) = rest.rsplit_once("/blobs/")?;
        (repo, false, r)
    };
    (!repo.is_empty() && !reference.is_empty() && !reference.contains('/')).then(|| (registry.to_owned(), repo.to_owned(), kind, reference.to_owned()))
}

fn lookup(engine: &Engine, path: &str, token: &str) -> Option<Found> {
    let (registry, repo, is_manifest, reference) = parse(path, token)?;
    let images = engine.store.images().ok()?;
    let in_repo = |i: &&Image| Reference::parse(&i.name).is_ok_and(|n| n.registry == registry && n.repository == repo);
    if is_manifest {
        if reference.starts_with("sha256:") {
            return images.iter().filter(in_repo).find_map(|i| manifest(&engine.store, i).filter(|(_, d)| *d == reference)).map(|(b, d)| Found::Manifest(b, d));
        }
        let wanted = Reference::parse(&format!("{registry}/{repo}:{reference}")).ok()?.short();
        let i = images.iter().find(|i| i.name == wanted)?;
        let (b, d) = manifest(&engine.store, i)?;
        return Some(Found::Manifest(b, d));
    }
    // Only blobs of that repository's images.
    let owned = images.iter().filter(in_repo).any(|i| i.config_digest == reference || i.layers.iter().any(|l| l.digest == reference));
    let path = engine.store.blob_path(&reference).ok()?;
    (owned && path.is_file()).then_some(Found::Blob(path, reference))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_mirror_paths() {
        assert_eq!(parse("/v2/tok/docker.io/library/myapp/manifests/dev", "tok"), Some(("docker.io".into(), "library/myapp".into(), true, "dev".into())));
        assert_eq!(parse("/v2/tok/ghcr.io/o/r/blobs/sha256:ab", "tok"), Some(("ghcr.io".into(), "o/r".into(), false, "sha256:ab".into())));
        assert_eq!(parse("/v2/wrong/docker.io/library/a/manifests/x", "tok"), None);
        assert_eq!(parse("/v2/tok/docker.io/manifests/x", "tok"), None);
        assert_eq!(parse("/v2/", "tok"), None);
    }

    #[test]
    fn parses_push_paths() {
        assert_eq!(parse_push("/v2/tok/push/b1/blobs/uploads", "tok"), Some(Push::UploadNew("b1".into())));
        assert_eq!(parse_push("/v2/tok/push/b1/blobs/uploads/", "tok"), Some(Push::UploadNew("b1".into())));
        assert_eq!(parse_push("/v2/tok/push/b1/blobs/uploads/abc", "tok"), Some(Push::Upload("b1".into(), "abc".into())));
        assert_eq!(parse_push("/v2/tok/push/b1/blobs/sha256:ff", "tok"), Some(Push::Blob("b1".into(), "sha256:ff".into())));
        assert_eq!(parse_push("/v2/tok/push/b1/manifests/latest", "tok"), Some(Push::Manifest("b1".into(), "latest".into())));
        assert_eq!(parse_push("/v2/tok/push/b1/manifests/sha256:aa", "tok"), Some(Push::Manifest("b1".into(), "sha256:aa".into())));
        assert_eq!(parse_push("/v2/wrong/push/b1/manifests/x", "tok"), None);
        assert_eq!(parse_push("/v2/tok/docker.io/library/a/manifests/x", "tok"), None);
    }

    #[test]
    fn query_params_are_percent_decoded() {
        assert_eq!(query_param("digest=sha256%3Aab%2Fcd&mount=x", "digest").as_deref(), Some("sha256:ab/cd"));
        assert_eq!(query_param("mount=sha256%3Aaa", "digest"), None);
        assert_eq!(query_param("digest=plain", "digest").as_deref(), Some("plain"));
    }

    #[test]
    fn mirror_host_matches_the_host_network() {
        let dir = std::env::temp_dir().join(format!("ctrs-mirror-host-{}", std::process::id()));
        let networks = super::super::network::Networks::load(&dir).unwrap();
        #[cfg(target_os = "linux")]
        assert_eq!(mirror_host(&networks), super::super::network::ip_str(networks.find("bridge").unwrap().gateway));
        #[cfg(not(target_os = "linux"))]
        assert_eq!(mirror_host(&networks), super::super::ports::HOST_ADDR);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn token_file_is_private_from_the_start() {
        use std::os::unix::fs::PermissionsExt;
        let p = std::env::temp_dir().join(format!("ctrs-mirror-token-{}", std::process::id()));
        // A leftover readable by everyone is replaced, not reused with its mode.
        std::fs::write(&p, "old").unwrap();
        std::fs::set_permissions(&p, std::fs::Permissions::from_mode(0o644)).unwrap();
        save_token(&p, "0123456789abcdef0123456789abcdef").unwrap();
        assert_eq!(std::fs::metadata(&p).unwrap().permissions().mode() & 0o777, 0o600);
        assert_eq!(std::fs::read_to_string(&p).unwrap(), "0123456789abcdef0123456789abcdef");
        let _ = std::fs::remove_file(&p);
    }
}
