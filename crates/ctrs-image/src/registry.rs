//! Pulls images from and pushes them to OCI and Docker registries, with
//! the credentials `docker login` stored (the CLI sends them along).

use std::collections::HashMap;
use std::fmt;
use std::io::{self, Read, Write};
use std::sync::Mutex;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use serde::Deserialize;

use crate::cancel::Cancel;
use crate::tags::{next_link, version_order};
use crate::reference::Reference;
use crate::store::{Image, Layer, RunConfig, Store, sha256_digest};
use crate::transport::{Body, Request, Transport, with_query};

const ACCEPT: &str = "application/vnd.oci.image.index.v1+json, \
    application/vnd.docker.distribution.manifest.list.v2+json, \
    application/vnd.oci.image.manifest.v1+json, \
    application/vnd.docker.distribution.manifest.v2+json";

/// Layers downloaded at once. Registries and CDNs serve a few streams well;
/// more mostly adds contention.
const PARALLEL_LAYERS: usize = 4;

#[derive(Debug)]
pub enum Error {
    Http(String),
    Status { url: String, status: u16, body: String },
    NoPlatform { wanted: String, available: Vec<String> },
    Manifest(String),
    /// No such image or tag, in the words `docker pull` uses.
    NotFound(String),
    Io(io::Error),
    /// Stopped by its [`Cancel`]; nothing was recorded.
    Cancelled,
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Http(e) => write!(f, "network error: {e}"),
            Error::Status { url, status, body } => {
                write!(f, "{url} returned HTTP {status}")?;
                if !body.is_empty() {
                    write!(f, ": {}", body.chars().take(200).collect::<String>())?;
                }
                Ok(())
            }
            Error::NoPlatform { wanted, available } => {
                write!(f, "no {wanted} image; available: {}", available.join(", "))
            }
            Error::Manifest(e) => write!(f, "unexpected manifest: {e}"),
            Error::NotFound(e) => write!(f, "{e}"),
            Error::Io(e) => write!(f, "{e}"),
            Error::Cancelled => write!(f, "pull cancelled"),
        }
    }
}

impl std::error::Error for Error {}

impl From<io::Error> for Error {
    fn from(e: io::Error) -> Self {
        Error::Io(e)
    }
}

/// The platform to pull, e.g. `linux/arm64`. Normalized at the boundary:
/// aliases map to one canonical architecture name, `linux/arm64/v8` is the
/// baseline `linux/arm64`, and anything else unsupported or malformed is
/// refused, never silently rewritten.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Platform {
    pub os: String,
    pub architecture: String,
}

impl Platform {
    /// `linux/amd64`, `linux/arm64/v8`, `amd64`, `aarch64`, `x86_64`,
    /// `intel`: the CLI's `--platform`. `arm64/v8` is baseline `arm64`;
    /// an unknown variant, an extra component, a non-Linux OS, or an
    /// unsupported architecture is refused, never dropped.
    pub fn parse(s: &str) -> Option<Platform> {
        let s = s.trim().to_lowercase();
        let mut parts = s.split('/');
        let first = parts.next()?;
        let (os, arch) = match (parts.next(), parts.next()) {
            (None, _) => {
                let normalized = match first {
                    "arm64" | "aarch64" => "arm64",
                    "amd64" | "x86_64" | "x86-64" | "intel" => "amd64",
                    "386" | "i386" | "i686" => "386",
                    _ => return None,
                };
                ("linux", normalized)
            }
            (Some(arch), variant) => {
                // A third component or a trailing '/' is refused here.
                let normalized = match (arch, variant) {
                    // v8 is the arm64 baseline instruction set; nothing else
                    // exists for arm64 in the registries ctrs reads.
                    ("arm64" | "aarch64", Some("v8")) | ("arm64" | "aarch64", None) => "arm64",
                    ("amd64" | "x86_64" | "x86-64" | "intel", None) => "amd64",
                    ("386" | "i386" | "i686", None) => "386",
                    _ => return None,
                };
                (first, normalized)
            }
        };
        (os == "linux" && !arch.is_empty()).then(|| Platform { os: os.to_owned(), architecture: arch.to_owned() })
    }

    /// Linux on this machine's CPU architecture, which is what the guest runs.
    pub fn host_linux() -> Platform {
        let architecture = match std::env::consts::ARCH {
            "aarch64" => "arm64",
            "x86_64" => "amd64",
            other => other,
        };
        Platform { os: "linux".into(), architecture: architecture.into() }
    }
}

/// One canonical name per architecture, where ctrs knows the aliases;
/// other nonempty names pass through verbatim (foreign records from
/// registries and archives load unchanged).
pub(crate) fn normalize_arch(s: &str) -> Option<String> {
    let s = s.trim().to_lowercase();
    if s.is_empty() || !s.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-') {
        return None;
    }
    Some(match s.as_str() {
        "x86_64" | "x86-64" | "intel" => "amd64".into(),
        "aarch64" => "arm64".into(),
        "i386" | "i686" => "386".into(),
        other => other.into(),
    })
}

impl fmt::Display for Platform {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}/{}", self.os, self.architecture)
    }
}

#[derive(Debug, Clone)]
pub enum PushProgress {
    Exists { digest: String },
    Uploading { digest: String, size: u64 },
    Pushed { digest: String },
}

const OCI_MANIFEST: &str = "application/vnd.oci.image.manifest.v1+json";

/// Docker layer media types, spelled the OCI way for an OCI manifest.
fn oci_layer_type(media_type: &str) -> &str {
    match media_type {
        "application/vnd.docker.image.rootfs.diff.tar.gzip" => "application/vnd.oci.image.layer.v1.tar+gzip",
        "application/vnd.docker.image.rootfs.diff.tar" => "application/vnd.oci.image.layer.v1.tar",
        other => other,
    }
}

/// The response if it is a success, else its status and body as an error.
fn ok(resp: crate::transport::Response, url: &str) -> Result<crate::transport::Response, Error> {
    let status = resp.status;
    if (200..300).contains(&status) {
        return Ok(resp);
    }
    let body = resp.text(64 << 10).unwrap_or_default();
    Err(Error::Status { url: url.to_owned(), status, body })
}

#[derive(Debug, Clone)]
pub enum Progress {
    Resolved { layers: usize, bytes: u64, cached: usize },
    /// Each layer, once the manifest is read and before any downloads.
    Layer { digest: String, size: u64, cached: bool },
    /// Bytes of a layer so far, every half MB or so.
    Downloading { digest: String, got: u64, size: u64 },
    LayerDone { digest: String, bytes: u64, cached: bool },
}

/// What `docker login` saved, as the CLI sends it in `X-Registry-Auth`
/// (base64url JSON) and in `POST /auth`.
#[derive(Debug, Clone, Default, Deserialize)]
pub struct Credentials {
    #[serde(default)]
    pub username: String,
    #[serde(default)]
    pub password: String,
    /// `base64(user:password)`, which some clients send instead.
    #[serde(default)]
    pub auth: String,
    #[serde(default, rename = "serveraddress")]
    pub server_address: String,
    /// An OAuth refresh token from an earlier login.
    #[serde(default, rename = "identitytoken")]
    pub identity_token: String,
    /// A bearer token to use as is.
    #[serde(default, rename = "registrytoken")]
    pub registry_token: String,
}

impl Credentials {
    /// Decodes an `X-Registry-Auth` header. Empty or unreadable means none.
    pub fn from_header(header: &str) -> Option<Credentials> {
        let json = crate::b64::decode(header.trim())?;
        let mut c: Credentials = serde_json::from_slice(&json).ok()?;
        if c.username.is_empty() && !c.auth.is_empty() {
            let pair = crate::b64::decode(&c.auth).and_then(|b| String::from_utf8(b).ok()).unwrap_or_default();
            if let Some((u, p)) = pair.split_once(':') {
                c.username = u.to_owned();
                c.password = p.to_owned();
            }
        }
        (!c.username.is_empty() || !c.identity_token.is_empty() || !c.registry_token.is_empty()).then_some(c)
    }

    fn basic(&self) -> Option<String> {
        (!self.username.is_empty()).then(|| format!("Basic {}", crate::b64::encode(format!("{}:{}", self.username, self.password).as_bytes())))
    }
}

/// A client is cheap: the connection pool, the tokens and what each
/// registry's auth challenge said are shared by the whole process (below),
/// so the next pull skips the handshakes and token round trips this one made.
#[derive(Debug)]
pub struct Client {
    transport: Transport,
    credentials: Option<Credentials>,
}

impl Default for Client {
    fn default() -> Self {
        Self::new()
    }
}

/// Where the program decides the proxy: `None` leaves the transport's
/// default handling, `Some(None)` is no proxy, `Some(Some((url, skip)))` a
/// proxy and the hosts that bypass it. The registry transport applies no
/// proxy settings; a program that sets a source is told so once.
pub type ProxySource = fn() -> Option<Option<(String, Vec<String>)>>;
static PROXY_SOURCE: std::sync::OnceLock<ProxySource> = std::sync::OnceLock::new();

/// Called once by the daemon, so every client follows its proxy settings.
pub fn set_proxy_source(f: ProxySource) {
    let _ = PROXY_SOURCE.set(f);
}

/// The authority part of an absolute http(s) URL, without userinfo.
fn host_of(url: &str) -> Option<String> {
    let after = url.split_once("://")?.1;
    let authority = after.split(['/', '?', '#']).next()?;
    let authority = authority.rsplit('@').next()?;
    let host = if let Some(rest) = authority.strip_prefix('[') {
        // Keep the brackets: is_local expects `[::1]` for IPv6.
        format!("[{}]", rest.split(']').next()?)
    } else {
        authority.split(':').next()?.to_owned()
    };
    (!host.is_empty()).then_some(host)
}

fn realm_is_secure(realm: &str, registry: &str) -> bool {
    if realm.get(..8).is_some_and(|s| s.eq_ignore_ascii_case("https://")) {
        return true;
    }
    realm.get(..7).is_some_and(|s| s.eq_ignore_ascii_case("http://"))
        && crate::reference::is_local(registry)
        && host_of(realm).is_some_and(|h| crate::reference::is_local(&h))
}

/// The process's one transport, shared so a pull's connections are made
/// once each. The h12tiny backend keeps no pool (every request pays
/// TCP+TLS), so there is nothing to rebuild when the proxy settings
/// change: they are not applied at all, and a program that sets a
/// proxy source is warned about that once.
fn shared_transport() -> Transport {
    static T: std::sync::OnceLock<Transport> = std::sync::OnceLock::new();
    if PROXY_SOURCE.get().is_some() {
        static WARNED: std::sync::Once = std::sync::Once::new();
        WARNED.call_once(|| eprintln!("ctrs: the registry transport has no proxy support; ignoring the proxy settings"));
    }
    T.get_or_init(Transport::shared_h12tiny).clone()
}

/// Bearer tokens (and Basic answers) by registry, repository, actions and
/// who asked, with when each stops being used. A registry says how long a
/// token lasts (`expires_in`, 60 s if it doesn't; Docker Hub gives 300 s).
static TOKENS: std::sync::LazyLock<Mutex<HashMap<String, (String, Instant)>>> = std::sync::LazyLock::new(Default::default);

/// Each registry's last bearer challenge without its scope, so a pull from
/// a registry seen before asks for its token straight away instead of
/// first sending a request only to be told where the token server is.
static CHALLENGES: std::sync::LazyLock<Mutex<HashMap<String, String>>> = std::sync::LazyLock::new(Default::default);

/// What Docker Hub answers every anonymous request with, so even the first
/// pull from it can fetch the token while it connects to the registry. If
/// Hub ever changes it, the registry's own challenge takes over.
const DOCKER_HUB_CHALLENGE: &str = r#"Bearer realm="https://auth.docker.io/token",service="registry.docker.io""#;

/// Manifests fetched by digest, which never change: re-pulling an image
/// (after `rmi`, or the same image under another tag) skips that round trip.
/// Kept per repository and per who asked (`manifest_key`), so a manifest
/// read with one repository's access, or with credentials, is not handed
/// out for another repository or to an anonymous pull.
static MANIFESTS: std::sync::LazyLock<Mutex<ManifestCache>> = std::sync::LazyLock::new(Default::default);

#[derive(Default)]
struct ManifestCache {
    by_digest: HashMap<String, (Vec<u8>, String)>,
    bytes: usize,
}

impl ManifestCache {
    /// Real manifests are a few KB; this holds hundreds.
    const MAX_BYTES: usize = 4 << 20;

    fn get(&self, key: &str) -> Option<(Vec<u8>, String)> {
        self.by_digest.get(key).cloned()
    }

    /// Keeps `bytes` under `key` if they are what `digest` names.
    fn put(&mut self, key: &str, digest: &str, bytes: &[u8], media_type: &str) {
        if bytes.len() > Self::MAX_BYTES || sha256_digest(bytes) != digest {
            return;
        }
        if self.bytes + bytes.len() > Self::MAX_BYTES {
            self.by_digest.clear();
            self.bytes = 0;
        }
        if self.by_digest.insert(key.to_owned(), (bytes.to_vec(), media_type.to_owned())).is_none() {
            self.bytes += bytes.len();
        }
    }
}

/// The longest a token is used, whatever the registry says: its
/// `expires_in` is untrusted, and `u64::MAX` seconds overflowed the
/// deadline (a panic, so the daemon went down).
const MAX_TOKEN_TTL: Duration = Duration::from_secs(3600);

/// How long to use a token the registry says lasts `ttl`: a little less,
/// so one is not sent just as it runs out, and never over an hour.
fn token_lifetime(ttl: Duration) -> Duration {
    let ttl = ttl.min(MAX_TOKEN_TTL);
    ttl - ttl / 10
}

/// A bearer challenge reduced to its realm and service: the scope it named
/// was for the repository that request was about.
fn without_scope(challenge: &str) -> Option<String> {
    if !challenge.get(..7).is_some_and(|s| s.eq_ignore_ascii_case("bearer ")) {
        return None;
    }
    let p = parse_challenge(&challenge[7..]);
    let realm = p.get("realm")?;
    Some(match p.get("service") {
        Some(service) => format!(r#"Bearer realm="{realm}",service="{service}""#),
        None => format!(r#"Bearer realm="{realm}""#),
    })
}

/// Tries a blob download gets in a row without receiving anything.
const BLOB_TRIES: u32 = 5;

/// A failure worth trying again: the network (a reset, a stall, a refused
/// or timed-out connect) or the registry being briefly unwell, not an
/// answer that will be the same next time.
fn transient(e: &Error) -> bool {
    match e {
        Error::Http(_) => true,
        Error::Status { status, .. } => *status >= 500 || *status == 408 || *status == 429,
        Error::Io(e) => {
            matches!(
                e.kind(),
                io::ErrorKind::TimedOut
                    | io::ErrorKind::WouldBlock
                    | io::ErrorKind::ConnectionReset
                    | io::ErrorKind::ConnectionAborted
                    | io::ErrorKind::BrokenPipe
                    | io::ErrorKind::UnexpectedEof
            )
        }
        _ => false,
    }
}

/// A pooled connection the server closed just as it was reused: the request
/// never got an answer and is safe to send again on a new connection.
fn stale(e: &Error) -> bool {
    const CLOSED: [io::ErrorKind; 4] = [io::ErrorKind::ConnectionReset, io::ErrorKind::ConnectionAborted, io::ErrorKind::BrokenPipe, io::ErrorKind::UnexpectedEof];
    match e {
        Error::Io(e) => CLOSED.contains(&e.kind()),
        // The backend connects fresh each time, so only a failure before any
        // bytes were sent is worth one automatic retry.
        Error::Http(msg) => msg.starts_with("h12tiny Connect:") || msg.starts_with("h12tiny Timeout:"),
        _ => false,
    }
}

impl Client {
    pub fn new() -> Client {
        Client { transport: shared_transport(), credentials: None }
    }

    /// Who the tokens are for: a fingerprint of the credentials, so one
    /// user's token is never sent for another, or for an anonymous pull.
    fn who(&self) -> String {
        match &self.credentials {
            None => "-".into(),
            Some(c) => sha256_digest(format!("{}\0{}\0{}\0{}", c.username, c.password, c.identity_token, c.registry_token).as_bytes()),
        }
    }

    fn token_key(&self, r: &Reference, actions: &str) -> String {
        format!("{}/{} {actions} {}", r.registry, r.repository, self.who())
    }

    fn manifest_key(&self, r: &Reference, reference: &str) -> String {
        format!("{}/{}@{reference} {}", r.registry, r.repository, self.who())
    }

    fn cached_token(key: &str) -> Option<String> {
        let mut tokens = TOKENS.lock().unwrap_or_else(|e| e.into_inner());
        match tokens.get(key) {
            Some((header, until)) if Instant::now() < *until => Some(header.clone()),
            Some(_) => {
                tokens.remove(key);
                None
            }
            None => None,
        }
    }

    fn remember_token(key: String, header: String, ttl: Duration) {
        let mut tokens = TOKENS.lock().unwrap_or_else(|e| e.into_inner());
        let now = Instant::now();
        tokens.retain(|_, (_, until)| now < *until);
        let Some(until) = now.checked_add(token_lifetime(ttl)) else { return };
        tokens.insert(key, (header, until));
    }

    /// Before a pull's first request: when there is no token for it yet but
    /// the registry's challenge is known, gets the token while a connection
    /// to the registry opens, rather than connecting, being refused and
    /// only then asking for a token. Saves a round trip and overlaps the
    /// handshakes. A failed token is left to the usual path, which reports
    /// it; a registry that cannot be reached at all is reported at once,
    /// rather than waiting out the connect timeout a second time.
    fn warm_up(&self, r: &Reference, actions: &str) -> Result<(), Error> {
        let key = self.token_key(r, actions);
        if self.credentials.as_ref().is_some_and(|c| !c.registry_token.is_empty()) || Self::cached_token(&key).is_some() {
            return Ok(());
        }
        let known = CHALLENGES.lock().unwrap_or_else(|e| e.into_inner()).get(&r.registry).cloned();
        let Some(challenge) = known.or_else(|| (r.registry == "docker.io").then(|| DOCKER_HUB_CHALLENGE.to_owned())) else { return Ok(()) };
        // The token pre-fetch is all that pays off when connections cannot
        // be reused: a challenge already known lets the first request skip
        // the 401 round trip.
        if let Ok((header, ttl)) = self.answer(&challenge, &format!("repository:{}:{actions}", r.repository), &r.registry) {
            Self::remember_token(key, header, ttl);
        }
        Ok(())
    }

    /// The same client, authenticating as `credentials`.
    pub fn with_credentials(mut self, credentials: Option<Credentials>) -> Client {
        self.credentials = credentials;
        self
    }

    /// Pulls `reference` for `platform` into `store` and records it in the
    /// image index. Layers already in the store are not downloaded again.
    pub fn pull(
        &self,
        store: &Store,
        reference: &Reference,
        platform: &Platform,
        progress: &(dyn Fn(Progress) + Sync),
    ) -> Result<Image, Error> {
        self.pull_with(store, reference, platform, progress, &Cancel::new())
    }

    /// [`Client::pull`] that `cancel` can stop from another thread: it then
    /// ends with [`Error::Cancelled`], its downloads stopped and no image
    /// recorded. Layers it finished stay in the store, for the next pull.
    pub fn pull_with(
        &self,
        store: &Store,
        reference: &Reference,
        platform: &Platform,
        progress: &(dyn Fn(Progress) + Sync),
        cancel: &Cancel,
    ) -> Result<Image, Error> {
        let _on = cancel.enter();
        let stopped = |e: Error| if cancel.is_cancelled() { Error::Cancelled } else { e };
        self.warm_up(reference, "pull").map_err(stopped)?;
        let (bytes, media_type) = self.manifest(reference, &reference.reference).map_err(|e| not_found(stopped(e), reference))?;
        // A pull by digest must get exactly that content, whether it is a
        // single manifest or a multi-arch index. Without this, a registry
        // could answer a pinned digest with any index naming any children.
        if reference.is_digest() && sha256_digest(&bytes) != reference.reference {
            return Err(Error::Manifest("manifest failed digest check".into()));
        }
        let manifest: Manifest = serde_json::from_slice(&bytes).map_err(|e| Error::Manifest(e.to_string()))?;

        // An index lists one manifest per platform; pick ours and fetch it.
        let index_digest = manifest.manifests.is_some().then(|| sha256_digest(&bytes));
        let (manifest, digest) = if let Some(entries) = manifest.manifests {
            let wanted = entries.iter().find(|m| {
                m.platform.as_ref().is_some_and(|p| p.os == platform.os && p.architecture == platform.architecture)
            });
            let Some(entry) = wanted else {
                return Err(Error::NoPlatform {
                    wanted: platform.to_string(),
                    available: entries
                        .iter()
                        .filter_map(|m| m.platform.as_ref())
                        .filter(|p| p.os != "unknown")
                        .map(|p| format!("{}/{}", p.os, p.architecture))
                        .collect(),
                });
            };
            let (bytes, _) = self.manifest(reference, &entry.digest).map_err(stopped)?;
            if sha256_digest(&bytes) != entry.digest {
                return Err(Error::Manifest(format!("manifest {} failed digest check", entry.digest)));
            }
            let m: Manifest = serde_json::from_slice(&bytes).map_err(|e| Error::Manifest(e.to_string()))?;
            (m, entry.digest.clone())
        } else {
            if reference.is_digest() && sha256_digest(&bytes) != reference.reference {
                return Err(Error::Manifest("manifest failed digest check".into()));
            }
            (manifest, sha256_digest(&bytes))
        };
        let (Some(config), Some(layers)) = (manifest.config, manifest.layers) else {
            return Err(Error::Manifest(format!("{media_type} has no config or layers")));
        };

        let layers: Vec<Layer> = layers
            .into_iter()
            .map(|l| Layer { digest: l.digest, size: l.size, media_type: l.media_type })
            .collect();
        let cached = layers.iter().filter(|l| store.has_blob(&l.digest, l.size)).count();
        progress(Progress::Resolved { layers: layers.len(), bytes: layers.iter().map(|l| l.size).sum(), cached });
        for l in &layers {
            progress(Progress::Layer { digest: l.digest.clone(), size: l.size, cached: store.has_blob(&l.digest, l.size) });
        }

        // Download missing layers in parallel, with a fixed number of workers
        // pulling from a shared queue, the largest first: the pull takes as
        // long as its slowest stream, so the big layer must not start last.
        let mut queue = layers.iter().collect::<Vec<_>>();
        queue.sort_by_key(|l| l.size);
        let queue = Mutex::new(queue);
        let first_error: Mutex<Option<Error>> = Mutex::new(None);
        std::thread::scope(|s| {
            // The config, alongside the layers rather than before them: it is
            // small, and fetching it first cost a round trip to the registry
            // and one to its CDN before any layer started. The config is
            // verified the moment it lands: os and architecture are required
            // and must name the selected platform — a mismatch fails the
            // pull before any layer completes the update.
            s.spawn(|| {
                let _on = cancel.enter();
                let done = (|| -> Result<(), Error> {
                    if !store.has_blob(&config.digest, config.size) {
                        // Bounded: the manifest declares the size, and a config is small.
                        let result = self.download_with(store, reference, &config.digest, crate::store::MAX_CONFIG, &|_| {}, cancel)?;
                        if result != config.size {
                            return Err(Error::Manifest(format!("config {} is {result} bytes, the manifest says {}", config.digest, config.size)));
                        }
                    }
                    let bytes = store.read_config(&config.digest)?;
                    let cfg: ImageConfig = serde_json::from_slice(&bytes).map_err(|e| Error::Manifest(format!("image config is not JSON: {e}")))?;
                    verify_config_against(&cfg, platform)
                })();
                if let Err(e) = done {
                    first_error.lock().unwrap_or_else(|e| e.into_inner()).get_or_insert(e);
                }
            });
            for _ in 0..PARALLEL_LAYERS.min(layers.len()) {
                s.spawn(|| {
                    let _on = cancel.enter();
                    loop {
                        let Some(layer) = queue.lock().unwrap_or_else(|e| e.into_inner()).pop() else { return };
                        if cancel.is_cancelled() || first_error.lock().unwrap_or_else(|e| e.into_inner()).is_some() {
                            return;
                        }
                        let cached = store.has_blob(&layer.digest, layer.size);
                        let result = if cached {
                            Ok(layer.size)
                        } else {
                            let on_bytes = |got| progress(Progress::Downloading { digest: layer.digest.clone(), got, size: layer.size });
                            self.download_with(store, reference, &layer.digest, u64::MAX, &on_bytes, cancel)
                        };
                        match result {
                            Ok(bytes) => progress(Progress::LayerDone { digest: layer.digest.clone(), bytes, cached }),
                            Err(e) => {
                                first_error.lock().unwrap_or_else(|e| e.into_inner()).get_or_insert(e);
                                return;
                            }
                        }
                    }
                });
            }
        });
        // Cancelled: whatever a stopped download said, that's why.
        if cancel.is_cancelled() {
            return Err(Error::Cancelled);
        }
        if let Some(e) = first_error.into_inner().unwrap_or_else(|e| e.into_inner()) {
            return Err(e);
        }
        // The record was verified when the config landed; re-read it for
        // the image metadata (created, run command).
        let cfg_bytes = store.read_config(&config.digest)?;
        let cfg: ImageConfig = serde_json::from_slice(&cfg_bytes).map_err(|e| Error::Manifest(e.to_string()))?;

        let run = cfg.config.unwrap_or_default();
        let image = Image {
            name: reference.short(),
            digest,
            index_digest,
            config_digest: config.digest,
            size: layers.iter().map(|l| l.size).sum(),
            layers,
            platform: platform.to_string(),
            created: cfg.created.unwrap_or_default(),
            pulled_at: SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0),
            config: RunConfig {
                env: run.env.unwrap_or_default(),
                entrypoint: run.entrypoint.unwrap_or_default(),
                cmd: run.cmd.unwrap_or_default(),
                working_dir: run.working_dir.unwrap_or_default(),
                user: run.user.unwrap_or_default(),
            },
        };
        // The last moment a cancel can stop it: after this it is pulled.
        if cancel.is_cancelled() {
            return Err(Error::Cancelled);
        }
        store.put_image(image.clone())?;
        Ok(image)
    }

    fn manifest(&self, r: &Reference, reference: &str) -> Result<(Vec<u8>, String), Error> {
        let by_digest = reference.starts_with("sha256:");
        let key = self.manifest_key(r, reference);
        if by_digest && let Some(hit) = MANIFESTS.lock().unwrap_or_else(|e| e.into_inner()).get(&key) {
            return Ok(hit);
        }
        let url = format!("{}/v2/{}/manifests/{reference}", r.api_base(), r.repository);
        let resp = self.get(r, &url, Some(ACCEPT))?;
        let media_type = resp.header("content-type").unwrap_or_default().to_owned();
        let bytes = resp.bytes(4 << 20)?;
        if by_digest {
            MANIFESTS.lock().unwrap_or_else(|e| e.into_inner()).put(&key, reference, &bytes, &media_type);
        }
        Ok((bytes, media_type))
    }

    /// Streams one blob into the store, verifying its digest. Returns its size.
    #[cfg(test)]
    fn download(&self, store: &Store, r: &Reference, digest: &str, on_bytes: &dyn Fn(u64)) -> Result<u64, Error> {
        self.download_with(store, r, digest, u64::MAX, on_bytes, &Cancel::new())
    }

    /// Downloads a blob, telling `on_bytes` how much has arrived every
    /// half MB, so a pull can show a progress bar. A connection that drops
    /// or stalls is resumed from where it got to
    /// (a `Range` request; from the start if the server ignores it), as
    /// Docker retries a layer, up to [`BLOB_TRIES`] times in a row without
    /// progress. Refuses bodies over `max` bytes, and stops (removing what
    /// it wrote) once `cancel` is.
    fn download_with(&self, store: &Store, r: &Reference, digest: &str, max: u64, on_bytes: &dyn Fn(u64), cancel: &Cancel) -> Result<u64, Error> {
        let url = format!("{}/v2/{}/blobs/{digest}", r.api_base(), r.repository);
        let mut out = store.blob_writer(digest)?;
        let mut buf = vec![0u8; 256 * 1024];
        let (mut got, mut told) = (0u64, 0u64);
        let mut failed = 0;
        loop {
            let before = got;
            let result = (|| -> Result<(), Error> {
                if cancel.is_cancelled() {
                    return Err(Error::Cancelled);
                }
                let resp = self.get_from(r, &url, got)?;
                if got > 0 && resp.status != 206 {
                    // The whole blob again: start over.
                    out = store.blob_writer(digest)?;
                    (got, told) = (0, 0);
                }
                let remaining = max.saturating_sub(got);
                let mut body = resp.into_reader().take(remaining.saturating_add(1));
                loop {
                    let n = body.read(&mut buf)?;
                    // A shut-down connection reads as an early end.
                    if cancel.is_cancelled() {
                        return Err(Error::Cancelled);
                    }
                    if n == 0 {
                        return Ok(());
                    }
                    out.write_all(&buf[..n])?;
                    got += n as u64;
                    if got > max {
                        return Err(Error::Io(io::Error::new(io::ErrorKind::InvalidData, "body exceeds limit")));
                    }
                    if got - told >= 512 * 1024 {
                        on_bytes(got);
                        told = got;
                    }
                }
            })();
            match result {
                Ok(()) => return Ok(out.finish()?),
                Err(_) if cancel.is_cancelled() => return Err(Error::Cancelled),
                Err(e) if transient(&e) => {
                    failed = if got > before { 1 } else { failed + 1 };
                    if failed >= BLOB_TRIES {
                        return Err(e);
                    }
                    cancel.sleep(Duration::from_millis(500 << (failed - 1).min(4)));
                }
                Err(e) => return Err(e),
            }
        }
    }

    /// GET a blob from byte `from` on (all of it from 0).
    fn get_from(&self, r: &Reference, url: &str, from: u64) -> Result<crate::transport::Response, Error> {
        if from == 0 {
            return self.get(r, url, None);
        }
        let resp = self.authed(r, "pull", |auth| {
            let mut req = Request::get(url.to_owned()).header("Range", format!("bytes={from}-"));
            if let Some(a) = auth {
                req = req.header("Authorization", a);
            }
            self.transport.send(req)
        })?;
        ok(resp, url)
    }

    /// GET with registry auth.
    fn get(&self, r: &Reference, url: &str, accept: Option<&str>) -> Result<crate::transport::Response, Error> {
        let resp = self.authed(r, "pull", |auth| {
            let send = || {
                let mut req = Request::get(url.to_owned());
                if let Some(a) = accept {
                    req = req.header("Accept", a);
                }
                if let Some(a) = auth {
                    req = req.header("Authorization", a);
                }
                self.transport.send(req)
            };
            match send() {
                Err(e) if stale(&e) => send(),
                r => r,
            }
        })?;
        ok(resp, url)
    }

    /// Makes a request with registry auth: on a 401 it answers the challenge
    /// (a bearer token for `actions` from the realm, or Basic credentials),
    /// caches the result per repository, and tries once more.
    fn authed(
        &self,
        r: &Reference,
        actions: &str,
        call: impl Fn(Option<&str>) -> Result<crate::transport::Response, Error>,
    ) -> Result<crate::transport::Response, Error> {
        let key = self.token_key(r, actions);
        let mut resp = None;
        for attempt in 0..2 {
            let header = Self::cached_token(&key).or_else(|| {
                self.credentials.as_ref().filter(|c| !c.registry_token.is_empty()).map(|c| format!("Bearer {}", c.registry_token))
            });
            let rsp = call(header.as_deref())?;
            if rsp.status == 401 && attempt == 0 {
                let challenge = rsp.header("www-authenticate").unwrap_or_default().to_owned();
                rsp.discard();
                let (answer, ttl) = self.answer(&challenge, &format!("repository:{}:{actions}", r.repository), &r.registry).map_err(|e| match e {
                    Error::Status { url, status, body } if url.is_empty() => Error::Status { url: r.api_base(), status, body },
                    e => e,
                })?;
                if let Some(c) = without_scope(&challenge) {
                    CHALLENGES.lock().unwrap_or_else(|e| e.into_inner()).insert(r.registry.clone(), c);
                }
                Self::remember_token(key.clone(), answer, ttl);
                continue;
            }
            resp = Some(rsp);
            break;
        }
        resp.ok_or_else(|| Error::Status { url: r.api_base(), status: 401, body: "unauthorized after token refresh".into() })
    }

    /// The `Authorization` header that answers a `WWW-Authenticate` challenge
    /// from `registry`, and how long it lasts.
    fn answer(&self, challenge: &str, default_scope: &str, registry: &str) -> Result<(String, Duration), Error> {
        if challenge.get(..5).is_some_and(|s| s.eq_ignore_ascii_case("basic")) {
            let basic = self.credentials.as_ref().and_then(Credentials::basic).ok_or_else(|| Error::Status {
                url: String::new(),
                status: 401,
                body: "unauthorized: authentication required (docker login)".into(),
            })?;
            return Ok((basic, Duration::from_secs(300)));
        }
        let params = parse_challenge(challenge);
        let scope = params.get("scope").cloned().unwrap_or_else(|| default_scope.to_owned());
        let (token, ttl) = self.token(&params, Some(&scope), registry)?;
        Ok((format!("Bearer {token}"), ttl))
    }

    /// A bearer token from the challenge's realm, as the logged-in user if
    /// any, and how long it lasts.
    fn token(&self, params: &HashMap<String, String>, scope: Option<&str>, registry: &str) -> Result<(String, Duration), Error> {
        let realm = params.get("realm").ok_or_else(|| Error::Http("registry sent no token realm".into()))?;
        let service = params.get("service").map(String::as_str).unwrap_or_default();
        // The registry names the realm, so a registry (or whoever answers for
        // it) could send the credentials anywhere, in the clear: only an https
        // realm gets them, or a loopback realm for a loopback registry.
        let secure = realm_is_secure(realm, registry);
        if !secure && self.credentials.is_some() {
            static WARNED: std::sync::Once = std::sync::Once::new();
            WARNED.call_once(|| eprintln!("ctrs: not sending {registry}'s credentials to its token realm {realm}: not https"));
        }
        let creds = self.credentials.as_ref().filter(|_| secure);
        let resp = if let Some(c) = creds.filter(|c| !c.identity_token.is_empty()) {
            // An identity token is an OAuth refresh token.
            let mut form = vec![("grant_type".to_owned(), "refresh_token".to_owned()), ("refresh_token".to_owned(), c.identity_token.clone()), ("service".to_owned(), service.to_owned()), ("client_id".to_owned(), "ctrs".to_owned())];
            if let Some(s) = scope {
                form.push(("scope".to_owned(), s.to_owned()));
            }
            self.transport.send(Request { method: "POST", url: realm.clone(), headers: Vec::new(), body: Body::Form(form) })?
        } else {
            let query: Vec<(&str, &str)> = scope.into_iter().map(|s| ("scope", s)).chain((!service.is_empty()).then_some(("service", service))).chain(creds.map(|c| ("account", c.username.as_str()))).collect();
            let url = with_query(realm, &query);
            let mut req = Request::get(url);
            if let Some(c) = creds
                && let Some(b) = c.basic()
            {
                req = req.header("Authorization", b);
            }
            self.transport.send(req)?
        };
        let status = resp.status;
        if status == 401 || status == 403 {
            return Err(Error::Status { url: realm.clone(), status, body: "unauthorized: incorrect username or password".into() });
        }
        if status != 200 {
            return Err(Error::Status { url: realm.clone(), status, body: String::new() });
        }
        let t: Token = serde_json::from_slice(&resp.bytes(16 << 20)?).map_err(|e| Error::Http(e.to_string()))?;
        // The distribution spec: 60 seconds when the server does not say.
        let ttl = Duration::from_secs(t.expires_in.filter(|&s| s > 0).unwrap_or(60));
        Ok((t.token.or(t.access_token).ok_or_else(|| Error::Http("token response had no token".into()))?, ttl))
    }

    /// `docker search`, against Docker Hub's search API.
    pub fn search(&self, term: &str, limit: u32) -> Result<Vec<serde_json::Value>, Error> {
        let url = with_query("https://index.docker.io/v1/search", &[("q", term), ("n", &limit.to_string())]);
        let resp = self.transport.send(Request::get(url))?;
        let status = resp.status;
        if status != 200 {
            return Err(Error::Status { url: "https://index.docker.io/v1/search".to_owned(), status, body: String::new() });
        }
        let body: serde_json::Value = serde_json::from_slice(&resp.bytes(4 << 20)?).map_err(|e| Error::Http(e.to_string()))?;
        Ok(body["results"].as_array().cloned().unwrap_or_default())
    }

    /// A Docker Hub repository's tags, most recently pushed first:
    /// `postgres` gives `latest`, `17-alpine`, `17`… Hub's own API, since
    /// the registry's tag list is unordered and has no dates.
    pub fn hub_tags(&self, repo: &str, limit: u32) -> Result<Vec<String>, Error> {
        let repo = if repo.contains('/') { repo.to_owned() } else { format!("library/{repo}") };
        let base_url = format!("https://hub.docker.com/v2/repositories/{repo}/tags");
        let url = with_query(&base_url, &[("page_size", &limit.to_string()), ("ordering", "last_updated")]);
        let resp = self.transport.send(Request::get(url))?;
        let status = resp.status;
        if status != 200 {
            return Err(Error::Status { url: base_url, status, body: String::new() });
        }
        let body: serde_json::Value = serde_json::from_slice(&resp.bytes(4 << 20)?).map_err(|e| Error::Http(e.to_string()))?;
        Ok(body["results"].as_array().into_iter().flatten().filter_map(|t| t["name"].as_str().map(str::to_owned)).collect())
    }

    /// A repository's tags from the registry itself (`/v2/<repo>/tags/list`),
    /// for registries other than Docker Hub: GitHub's, ECR's. The list has
    /// no dates, so they are put newest version first by their names, and
    /// the signature and attestation tags (`sha256-….sig`) are left out.
    pub fn tags(&self, r: &Reference, limit: usize) -> Result<Vec<String>, Error> {
        // The list comes a page at a time, in name order: all of it is read
        // (up to `TAG_PAGES` pages) before the newest can be picked out.
        const TAG_PAGES: usize = 20;
        let base = r.api_base();
        let mut url = format!("{base}/v2/{}/tags/list?n=1000", r.repository);
        let mut tags: Vec<String> = Vec::new();
        for _ in 0..TAG_PAGES {
            let resp = self.get(r, &url, None)?;
            let next = resp.header("link").and_then(next_link).map(str::to_owned);
            let body: serde_json::Value = serde_json::from_slice(&resp.bytes(4 << 20)?).map_err(|e| Error::Http(e.to_string()))?;
            tags.extend(body["tags"].as_array().into_iter().flatten().filter_map(|t| t.as_str()).filter(|t| !t.starts_with("sha256-")).map(str::to_owned));
            // Only a next page on the same registry is followed.
            match next {
                Some(n) if n.starts_with("/v2/") => url = format!("{base}{n}"),
                _ => break,
            }
        }
        tags.sort_by(|a, b| version_order(b, a));
        tags.truncate(limit);
        Ok(tags)
    }

    /// `docker login`: checks the credentials against the registry at
    /// `server` (`https://index.docker.io/v1/`, `ghcr.io`, `localhost:5000`).
    pub fn login(&self, server: &str) -> Result<(), Error> {
        let host = server.trim_start_matches("https://").trim_start_matches("http://").split('/').next().unwrap_or_default();
        let host = if host.is_empty() || host == "index.docker.io" || host == "docker.io" { "registry-1.docker.io" } else { host };
        let base = format!("{}://{host}", if crate::reference::is_local(host) { "http" } else { "https" });
        let url = format!("{base}/v2/");
        let resp = self.transport.send(Request::get(url.clone()))?;
        match resp.status {
            200 => Ok(()),
            401 => {
                let challenge = resp.header("www-authenticate").unwrap_or_default().to_owned();
                if challenge.get(..5).is_some_and(|s| s.eq_ignore_ascii_case("basic")) {
                    let (auth, _) = self.answer(&challenge, "", host)?;
                    let again = self.transport.send(Request::get(url.clone()).header("Authorization", auth))?;
                    return match again.status {
                        200 => Ok(()),
                        s => Err(Error::Status { url, status: s, body: "unauthorized: incorrect username or password".into() }),
                    };
                }
                // A token for no particular repository proves the password.
                self.token(&parse_challenge(&challenge), None, host).map(|_| ())
            }
            s => Err(Error::Status { url, status: s, body: String::new() }),
        }
    }

    /// Uploads `image` as `target` (`docker push`): blobs the registry
    /// lacks, then a manifest. Returns the manifest's digest and size.
    pub fn push(&self, store: &Store, image: &Image, target: &Reference, progress: &dyn Fn(PushProgress)) -> Result<(String, u64), Error> {
        let base = target.api_base();
        let repo = &target.repository;
        let config_size = std::fs::metadata(store.blob_path(&image.config_digest)?)?.len();
        let blobs: Vec<(String, u64)> =
            image.layers.iter().map(|l| (l.digest.clone(), l.size)).chain(std::iter::once((image.config_digest.clone(), config_size))).collect();
        for (digest, size) in &blobs {
            let url = format!("{base}/v2/{repo}/blobs/{digest}");
            let head = self.authed(target, "pull,push", |auth| {
                let mut req = Request { method: "HEAD", url: url.clone(), headers: Vec::new(), body: Body::Empty };
                if let Some(a) = auth {
                    req = req.header("Authorization", a);
                }
                self.transport.send(req)
            })?;
            if head.status == 200 {
                progress(PushProgress::Exists { digest: digest.clone() });
                continue;
            }
            progress(PushProgress::Uploading { digest: digest.clone(), size: *size });
            // Start an upload session, then send the blob in one PUT.
            let start_url = format!("{base}/v2/{repo}/blobs/uploads/");
            let started = self.authed(target, "pull,push", |auth| {
                let mut req = Request { method: "POST", url: start_url.clone(), headers: Vec::new(), body: Body::Empty };
                if let Some(a) = auth {
                    req = req.header("Authorization", a);
                }
                self.transport.send(req)
            })?;
            let started = ok(started, &start_url)?;
            let location = started.header("location").unwrap_or_default().to_owned();
            let location = if location.starts_with('/') { format!("{base}{location}") } else { location };
            let put_url = format!("{location}{}digest={digest}", if location.contains('?') { '&' } else { '?' });
            let path = store.blob_path(digest)?;
            let put = self.authed(target, "pull,push", |auth| {
                let mut req = Request { method: "PUT", url: put_url.clone(), headers: vec![("Content-Length".to_owned(), size.to_string())], body: Body::File { path: path.clone(), content_type: Some("application/octet-stream") } };
                if let Some(a) = auth {
                    req = req.header("Authorization", a);
                }
                self.transport.send(req)
            })?;
            ok(put, &put_url)?;
            progress(PushProgress::Pushed { digest: digest.clone() });
        }
        let manifest = serde_json::json!({
            "schemaVersion": 2,
            "mediaType": OCI_MANIFEST,
            "config": {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": image.config_digest, "size": config_size},
            "layers": image.layers.iter().map(|l| serde_json::json!({"mediaType": oci_layer_type(&l.media_type), "digest": l.digest, "size": l.size})).collect::<Vec<_>>(),
        });
        let bytes = serde_json::to_vec(&manifest).map_err(|e| Error::Manifest(e.to_string()))?;
        let url = format!("{base}/v2/{repo}/manifests/{}", target.reference);
        let put = self.authed(target, "pull,push", |auth| {
            let mut req = Request { method: "PUT", url: url.clone(), headers: vec![("Content-Type".to_owned(), OCI_MANIFEST.to_owned())], body: Body::Bytes(bytes.clone()) };
            if let Some(a) = auth {
                req = req.header("Authorization", a);
            }
            self.transport.send(req)
        })?;
        ok(put, &url)?;
        Ok((sha256_digest(&bytes), bytes.len() as u64))
    }
}

/// Parses `Bearer realm="…",service="…",scope="…"`.
fn parse_challenge(header: &str) -> HashMap<String, String> {
    let rest = header.strip_prefix("Bearer ").unwrap_or(header);
    let mut out = HashMap::new();
    let mut s = rest;
    while let Some(eq) = s.find('=') {
        let key = s[..eq].trim().trim_start_matches(',').trim().to_ascii_lowercase();
        let after = &s[eq + 1..];
        let (value, next) = if let Some(quoted) = after.strip_prefix('"') {
            match quoted.find('"') {
                Some(end) => (&quoted[..end], &quoted[end + 1..]),
                None => (quoted, ""),
            }
        } else {
            match after.find(',') {
                Some(end) => (&after[..end], &after[end..]),
                None => (after, ""),
            }
        };
        out.insert(key, value.to_owned());
        s = next;
    }
    out
}

#[derive(Deserialize)]
struct Token {
    token: Option<String>,
    access_token: Option<String>,
    expires_in: Option<u64>,
}

/// Either an index (has `manifests`) or an image manifest (has `config` and `layers`).
#[derive(Deserialize)]
struct Manifest {
    manifests: Option<Vec<IndexEntry>>,
    config: Option<Descriptor>,
    layers: Option<Vec<Descriptor>>,
}

#[derive(Deserialize)]
struct IndexEntry {
    digest: String,
    platform: Option<PlatformJson>,
}

#[derive(Deserialize)]
struct PlatformJson {
    os: String,
    architecture: String,
}

#[derive(Deserialize)]
struct Descriptor {
    #[serde(rename = "mediaType", default)]
    media_type: String,
    digest: String,
    size: u64,
}

/// The config must name the platform the manifest selected (or the host,
/// for the fallback entry): os and architecture are required; a mismatch
/// or an absence fails the pull before any record is published.
fn verify_config_against(cfg: &ImageConfig, platform: &Platform) -> Result<(), Error> {
    match (cfg.os.as_deref(), cfg.architecture.as_deref()) {
        (Some(os), Some(architecture)) if os == platform.os && architecture == platform.architecture => Ok(()),
        (Some(os), Some(architecture)) => Err(Error::Manifest(format!("image config is {os}/{architecture}, the manifest selection is {platform}"))),
        _ => Err(Error::Manifest("image config is missing os or architecture".into())),
    }
}

#[derive(Deserialize)]
struct ImageConfig {
    created: Option<String>,
    config: Option<ContainerConfig>,
    os: Option<String>,
    architecture: Option<String>,
}

#[derive(Deserialize, Default)]
struct ContainerConfig {
    #[serde(rename = "Env")]
    env: Option<Vec<String>>,
    #[serde(rename = "Entrypoint")]
    entrypoint: Option<Vec<String>>,
    #[serde(rename = "Cmd")]
    cmd: Option<Vec<String>>,
    #[serde(rename = "WorkingDir")]
    working_dir: Option<String>,
    #[serde(rename = "User")]
    user: Option<String>,
}

/// A registry answers a name that doesn't exist with 401 (Docker Hub hides
/// private repositories that way) and a missing tag with 404. Say it as
/// `docker pull` does, not as the raw registry reply; a wrong password stays as it is.
fn not_found(e: Error, r: &Reference) -> Error {
    match e {
        Error::Status { status: 401 | 403, ref body, .. } if !body.contains("incorrect username or password") => {
            let short = r.short();
            let repo = short.rsplit_once(if r.is_digest() { '@' } else { ':' }).map_or(short.as_str(), |(n, _)| n);
            Error::NotFound(format!("pull access denied for {repo}, repository does not exist or may require 'docker login'"))
        }
        Error::Status { status: 404, .. } => Error::NotFound(format!("manifest for {} not found: manifest unknown", r.short())),
        e => e,
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn platform_aliases_normalize() {
        for (given, want) in [
            ("linux/amd64", Platform { os: "linux".into(), architecture: "amd64".into() }),
            ("linux/x86_64", Platform { os: "linux".into(), architecture: "amd64".into() }),
            ("linux/x86-64", Platform { os: "linux".into(), architecture: "amd64".into() }),
            ("linux/intel", Platform { os: "linux".into(), architecture: "amd64".into() }),
            ("linux/aarch64", Platform { os: "linux".into(), architecture: "arm64".into() }),
            ("linux/arm64", Platform { os: "linux".into(), architecture: "arm64".into() }),
            ("linux/arm64/v8", Platform { os: "linux".into(), architecture: "arm64".into() }),
            ("linux/aarch64/v8", Platform { os: "linux".into(), architecture: "arm64".into() }),
            ("linux/386", Platform { os: "linux".into(), architecture: "386".into() }),
            ("linux/i386", Platform { os: "linux".into(), architecture: "386".into() }),
            ("linux/i686", Platform { os: "linux".into(), architecture: "386".into() }),
            ("amd64", Platform { os: "linux".into(), architecture: "amd64".into() }),
            ("arm64", Platform { os: "linux".into(), architecture: "arm64".into() }),
            ("X86_64", Platform { os: "linux".into(), architecture: "amd64".into() }),
            ("LINUX/Arm64/V8", Platform { os: "linux".into(), architecture: "arm64".into() }),
            (" linux/arm64 ", Platform { os: "linux".into(), architecture: "arm64".into() }),
        ] {
            assert_eq!(Platform::parse(given), Some(want), "{given}");
        }
    }

    #[test]
    fn platform_refusals() {
        for given in [
            "",
            " ",
            "linux/",
            "linux//arm64",
            "/arm64",
            "linux/arm/v7",
            "linux/arm64/v9",
            "linux/arm64/",
            "linux/amd64/v4",
            "linux/amd64/x86-64",
            "linux/arm64/extra/v8",
            "windows/amd64",
            "darwin/arm64",
            "bsd/amd64",
            "banana",
            "linux/banana",
            "arch64",
        ] {
            assert_eq!(Platform::parse(given), None, "{given}");
        }
    }

    #[test]
    fn architecture_aliases_normalize_or_pass_foreign() {
        assert_eq!(normalize_arch("x86_64").as_deref(), Some("amd64"));
        assert_eq!(normalize_arch("x86-64").as_deref(), Some("amd64"));
        assert_eq!(normalize_arch("aarch64").as_deref(), Some("arm64"));
        assert_eq!(normalize_arch("ARM64").as_deref(), Some("arm64"));
        assert_eq!(normalize_arch("ppc64le").as_deref(), Some("ppc64le"));
        assert_eq!(normalize_arch("s390x").as_deref(), Some("s390x"));
        assert_eq!(normalize_arch("riscv64").as_deref(), Some("riscv64"));
        assert_eq!(normalize_arch(""), None);
        assert_eq!(normalize_arch("   "), None);
        assert_eq!(normalize_arch("arm_64!!!"), None);
    }

    fn tmp_root(tag: &str) -> std::path::PathBuf {
        static SEQ: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
        let seq = SEQ.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        std::env::temp_dir().join(format!("ctrs-{tag}-{}-{seq}", std::process::id()))
    }

    #[test]
    fn a_missing_image_reads_as_docker_says_it() {
        let r = Reference::parse("gall").unwrap();
        let denied = Error::Status { url: "https://registry-1.docker.io/v2/library/gall/manifests/latest".into(), status: 401, body: r#"{"errors":[{"code":"UNAUTHORIZED"}]}"#.into() };
        assert_eq!(not_found(denied, &r).to_string(), "pull access denied for gall, repository does not exist or may require 'docker login'");
        let tag = Reference::parse("alpine:nope").unwrap();
        assert_eq!(not_found(Error::Status { url: String::new(), status: 404, body: String::new() }, &tag).to_string(), "manifest for alpine:nope not found: manifest unknown");
        let wrong = Error::Status { url: String::new(), status: 401, body: "unauthorized: incorrect username or password".into() };
        assert!(matches!(not_found(wrong, &r), Error::Status { status: 401, .. }));
        assert!(matches!(not_found(Error::Status { url: String::new(), status: 500, body: String::new() }, &r), Error::Status { status: 500, .. }));
    }

    #[test]
    fn parses_docker_hub_challenge() {
        let p = parse_challenge(
            r#"Bearer realm="https://auth.docker.io/token",service="registry.docker.io",scope="repository:library/alpine:pull""#,
        );
        assert_eq!(p["realm"], "https://auth.docker.io/token");
        assert_eq!(p["service"], "registry.docker.io");
        assert_eq!(p["scope"], "repository:library/alpine:pull");
    }

    #[test]
    fn a_remembered_challenge_drops_the_scope() {
        let hub = r#"Bearer realm="https://auth.docker.io/token",service="registry.docker.io",scope="repository:library/alpine:pull""#;
        assert_eq!(without_scope(hub).as_deref(), Some(DOCKER_HUB_CHALLENGE));
        assert_eq!(without_scope(r#"bearer realm="https://ghcr.io/token""#).as_deref(), Some(r#"Bearer realm="https://ghcr.io/token""#));
        assert_eq!(without_scope(r#"Basic realm="registry""#), None);
        assert_eq!(without_scope(r#"Bearer service="x""#), None);
    }

    #[test]
    fn tokens_are_used_a_little_less_long_than_they_last() {
        assert_eq!(token_lifetime(Duration::from_secs(300)), Duration::from_secs(270));
        assert_eq!(token_lifetime(Duration::from_secs(60)), Duration::from_secs(54));
        // A hostile expires_in is clamped, and remembering it cannot panic.
        assert_eq!(token_lifetime(Duration::from_secs(u64::MAX)), Duration::from_secs(3240));
        assert_eq!(token_lifetime(Duration::MAX), Duration::from_secs(3240));
        Client::remember_token("sec-test".into(), "Bearer x".into(), Duration::from_secs(u64::MAX));
        assert!(TOKENS.lock().unwrap().get("sec-test").is_some_and(|(_, until)| *until <= Instant::now() + MAX_TOKEN_TTL));
        let t: Token = serde_json::from_str(r#"{"token":"a","expires_in":300,"issued_at":"2026-10-30T06:00:00Z"}"#).unwrap();
        assert_eq!(t.expires_in, Some(300));
    }

    #[test]
    fn tokens_are_kept_apart_by_who_asked() {
        let r = Reference::parse("alpine").unwrap();
        let anon = Client { transport: shared_transport(), credentials: None };
        let alice = Client { transport: shared_transport(), credentials: Some(Credentials { username: "alice".into(), password: "a".into(), ..Default::default() }) };
        let other = Client { transport: shared_transport(), credentials: Some(Credentials { username: "alice".into(), password: "b".into(), ..Default::default() }) };
        let keys = [anon.token_key(&r, "pull"), alice.token_key(&r, "pull"), other.token_key(&r, "pull"), alice.token_key(&r, "pull,push")];
        for (i, a) in keys.iter().enumerate() {
            for b in &keys[i + 1..] {
                assert_ne!(a, b);
            }
        }
        assert!(!alice.token_key(&r, "pull").contains("alice"), "the key holds a fingerprint, not the name");
        assert_eq!(anon.token_key(&r, "pull"), Client::new().token_key(&r, "pull"));
        // Cached manifests too: one fetched with credentials is not an
        // anonymous pull's, nor another account's.
        let d = "sha256:0000000000000000000000000000000000000000000000000000000000000000";
        assert_ne!(anon.manifest_key(&r, d), alice.manifest_key(&r, d));
        assert_ne!(alice.manifest_key(&r, d), other.manifest_key(&r, d));
        assert_eq!(anon.manifest_key(&r, d), Client::new().manifest_key(&r, d));
        assert_ne!(anon.manifest_key(&r, d), anon.manifest_key(&Reference::parse("busybox").unwrap(), d));
    }

    #[test]
    fn token_cache_expires() {
        let key = "test.invalid/expiring pull -".to_owned();
        Client::remember_token(key.clone(), "Bearer a".into(), Duration::from_secs(60));
        assert_eq!(Client::cached_token(&key).as_deref(), Some("Bearer a"));
        Client::remember_token(key.clone(), "Bearer b".into(), Duration::ZERO);
        assert_eq!(Client::cached_token(&key), None);
    }

    #[test]
    fn manifest_cache_keeps_only_what_the_digest_names() {
        let mut c = ManifestCache::default();
        let body = br#"{"schemaVersion":2}"#;
        let digest = sha256_digest(body);
        let key = format!("docker.io/library/alpine@{digest}");
        c.put(&key, &digest, b"something else", OCI_MANIFEST);
        assert!(c.get(&key).is_none());
        c.put(&key, &digest, body, OCI_MANIFEST);
        assert_eq!(c.get(&key), Some((body.to_vec(), OCI_MANIFEST.to_owned())));
        assert!(c.get(&format!("docker.io/library/other@{digest}")).is_none());
        c.put(&key, &digest, body, OCI_MANIFEST);
        assert_eq!(c.bytes, body.len());
        // Over the limit, it starts again rather than growing.
        let big = vec![b' '; ManifestCache::MAX_BYTES - 4];
        let big_digest = sha256_digest(&big);
        c.put(&big_digest, &big_digest, &big, OCI_MANIFEST);
        assert!(c.get(&key).is_none());
        assert_eq!(c.bytes, big.len());
    }

    #[test]
    fn credentials_only_use_https_or_a_loopback_realm() {
        assert!(realm_is_secure("https://auth.example.com/token", "registry.example.com"));
        assert!(realm_is_secure("http://127.0.0.1:5000/token", "localhost:5000"));
        assert!(realm_is_secure("http://[::1]:5000/token", "localhost:5000"));
        for (realm, registry) in [
            ("http://auth.example.com/token", "registry.example.com"),
            ("http://auth.example.com/token", "localhost:5000"),
            ("http://127.evil.com/token", "127.evil.com"),
            ("http://192.168.1.10/token", "localhost:5000"),
        ] {
            assert!(!realm_is_secure(realm, registry), "{realm} for {registry}");
        }
    }

    /// A registry on loopback serving one blob: `answer` gets each request's
    /// `Range` start (0 without one) and the connection, and writes the reply.
    fn blob_server(answer: impl Fn(u64, &mut std::net::TcpStream) + Send + Sync + 'static) -> (String, std::thread::JoinHandle<Vec<u64>>) {
        let answer = std::sync::Arc::new(answer);
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let host = listener.local_addr().unwrap().to_string();
        let served = std::thread::spawn(move || {
            let mut seen = Vec::new();
            listener.set_nonblocking(true).unwrap();
            let end = Instant::now() + Duration::from_secs(20);
            while Instant::now() < end {
                let Ok((mut c, _)) = listener.accept() else {
                    std::thread::sleep(Duration::from_millis(10));
                    continue;
                };
                c.set_nonblocking(false).unwrap();
                let mut head = Vec::new();
                let mut b = [0u8; 1];
                while !head.ends_with(b"\r\n\r\n") && c.read(&mut b).unwrap_or(0) == 1 {
                    head.push(b[0]);
                }
                let head = String::from_utf8_lossy(&head).to_lowercase();
                if head.starts_with("quit") || head.is_empty() {
                    break;
                }
                let from = head.lines().find_map(|l| l.strip_prefix("range: bytes=")).and_then(|r| r.trim_end_matches('-').parse().ok()).unwrap_or(0);
                seen.push(from);
                // Each on its own, so a stalled answer does not hold up the next.
                let answer = answer.clone();
                std::thread::spawn(move || answer(from, &mut c));
            }
            seen
        });
        (host, served)
    }

    fn quit(host: &str) {
        let _ = std::net::TcpStream::connect(host).and_then(|mut c| c.write_all(b"QUIT\r\n\r\n"));
    }

    fn test_client() -> Client {
        Client { transport: Transport::test_h12tiny(Duration::from_millis(300)), credentials: None }
    }

    fn blob() -> (Vec<u8>, String) {
        let data: Vec<u8> = (0..200_000u32).map(|i| (i * 7 % 251) as u8).collect();
        let digest = sha256_digest(&data);
        (data, digest)
    }

    fn stalled_resume_case(client: Client) {
        let (data, digest) = blob();
        let half = data.len() / 2;
        let body = data.clone();
        let (host, served) = blob_server(move |from, c| {
            if from == 0 {
                // Half the blob, then silence with the connection open.
                let _ = write!(c, "HTTP/1.1 200 OK\r\nContent-Length: {}\r\n\r\n", body.len());
                let _ = c.write_all(&body[..half]);
                std::thread::sleep(Duration::from_secs(2));
            } else {
                let rest = &body[from as usize..];
                let _ = write!(c, "HTTP/1.1 206 Partial Content\r\nContent-Length: {}\r\nContent-Range: bytes {from}-{}/{}\r\n\r\n", rest.len(), body.len() - 1, body.len());
                let _ = c.write_all(rest);
            }
        });
        let root = tmp_root("stall");
        let store = Store::open(&root).unwrap();
        let r = Reference::parse(&format!("{host}/test/blob:1")).unwrap();
        let started = Instant::now();
        let got = client.download(&store, &r, &digest, &|_| {}).unwrap();
        assert_eq!(got, data.len() as u64);
        assert!(store.has_blob(&digest, data.len() as u64));
        assert!(started.elapsed() < Duration::from_secs(2), "{:?}", started.elapsed());
        quit(&host);
        assert_eq!(served.join().unwrap(), [0, half as u64]);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn a_stalled_blob_resumes_where_it_stopped() {
        stalled_resume_case(test_client());
    }

    fn no_range_case(client: Client) {
        let (data, digest) = blob();
        let body = data.clone();
        let tries = std::sync::Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let (host, served) = blob_server(move |_, c| {
            let _ = write!(c, "HTTP/1.1 200 OK\r\nContent-Length: {}\r\n\r\n", body.len());
            // The first connection drops a third of the way in.
            if tries.fetch_add(1, std::sync::atomic::Ordering::SeqCst) == 0 {
                let _ = c.write_all(&body[..body.len() / 3]);
                let _ = c.shutdown(std::net::Shutdown::Both);
            } else {
                let _ = c.write_all(&body);
            }
        });
        let root = tmp_root("norange");
        let store = Store::open(&root).unwrap();
        let r = Reference::parse(&format!("{host}/test/blob:1")).unwrap();
        assert_eq!(client.download(&store, &r, &digest, &|_| {}).unwrap(), data.len() as u64);
        assert!(store.has_blob(&digest, data.len() as u64));
        quit(&host);
        let seen = served.join().unwrap();
        assert_eq!(seen.len(), 2);
        assert_eq!(seen[0], 0);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn a_server_without_ranges_sends_the_blob_again() {
        no_range_case(test_client());
    }

    fn never_arrives_case(client: Client) {
        let (_, digest) = blob();
        let (host, served) = blob_server(|_, c| {
            let _ = write!(c, "HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\n");
            std::thread::sleep(Duration::from_millis(400));
        });
        let root = tmp_root("dead");
        let store = Store::open(&root).unwrap();
        let r = Reference::parse(&format!("{host}/test/blob:1")).unwrap();
        assert!(client.download(&store, &r, &digest, &|_| {}).is_err());
        quit(&host);
        assert_eq!(served.join().unwrap().len(), BLOB_TRIES as usize);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn a_blob_that_never_arrives_gives_up() {
        never_arrives_case(test_client());
    }

    #[test]
    fn a_cancelled_download_closes_a_stalled_body_and_removes_the_partial_blob() {
        let client = Client::new();
        let data = vec![0x5a; 1024 * 1024];
        let digest = sha256_digest(&data);
        let body = data.clone();
        let (closed_tx, closed_rx) = std::sync::mpsc::sync_channel(1);
        let (host, served) = blob_server(move |_, c| {
            write!(c, "HTTP/1.1 200 OK\r\nContent-Length: {}\r\n\r\n", body.len()).unwrap();
            c.write_all(&body[..body.len() / 2]).unwrap();
            c.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
            closed_tx.send(c.read(&mut [0])).unwrap();
        });
        let root = tmp_root("cancel");
        let store = Store::open(&root).unwrap();
        let r = Reference::parse(&format!("{host}/test/blob:1")).unwrap();
        let cancel = Cancel::new();
        let result = {
            let _on = cancel.enter();
            client.download_with(&store, &r, &digest, u64::MAX, &|_| cancel.cancel(), &cancel)
        };
        let peer_closed = closed_rx.recv_timeout(Duration::from_secs(1));
        quit(&host);
        let requests = served.join().unwrap();
        let has_blob = store.has_blob(&digest, data.len() as u64);
        let partial_files = std::fs::read_dir(root.join("tmp")).unwrap().count();
        std::fs::remove_dir_all(&root).unwrap();
        assert!(matches!(result, Err(Error::Cancelled)), "{result:?}");
        assert!(matches!(peer_closed, Ok(Ok(0))), "{peer_closed:?}");
        assert!(!has_blob);
        assert_eq!(partial_files, 0);
        assert_eq!(requests, [0]);
    }

    #[test]
    fn the_next_page_of_tags_comes_from_the_link_header() {
        assert_eq!(next_link(r#"</v2/o/r/tags/list?last=1.9&n=1000>; rel="next""#), Some("/v2/o/r/tags/list?last=1.9&n=1000"));
        assert_eq!(next_link(r#"<https://elsewhere.example/x>; rel="prev""#), None);
    }

    #[test]
    fn registry_tags_are_newest_version_first() {
        let mut tags = ["1.9", "1.10", "1.2-rc1", "latest", "1.2", "1.2.1", "main"].map(String::from).to_vec();
        tags.sort_by(|a, b| version_order(b, a));
        assert_eq!(tags, ["1.10", "1.9", "1.2.1", "1.2", "1.2-rc1", "main", "latest"]);
    }

    #[test]
    fn transient_failures_are_the_network_and_5xx() {
        assert!(transient(&Error::Http("h12tiny Timeout: recv body".to_string())));
        assert!(transient(&Error::Io(io::ErrorKind::ConnectionReset.into())));
        assert!(transient(&Error::Status { url: String::new(), status: 503, body: String::new() }));
        assert!(!transient(&Error::Status { url: String::new(), status: 404, body: String::new() }));
        assert!(!transient(&Error::Io(io::Error::new(io::ErrorKind::InvalidData, "digest mismatch"))));
    }

    // --- Pull, against a loopback registry --------------------------------

    /// A registry on loopback serving fixed routes by path; entries are
    /// (path, content-type, body). Unknown paths answer 404 like a registry.
    fn registry_stub(routes: Vec<(String, &'static str, Vec<u8>)>) -> (String, std::thread::JoinHandle<()>) {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let host = listener.local_addr().unwrap().to_string();
        let routes: std::sync::Arc<Vec<(String, &'static str, Vec<u8>)>> = std::sync::Arc::new(routes);
        let server = std::thread::spawn(move || {
            listener.set_nonblocking(true).unwrap();
            let end = Instant::now() + Duration::from_secs(20);
            while Instant::now() < end {
                let Ok((mut c, _)) = listener.accept() else {
                    std::thread::sleep(Duration::from_millis(10));
                    continue;
                };
                c.set_nonblocking(false).unwrap();
                let mut head = Vec::new();
                let mut b = [0u8; 1];
                while !head.ends_with(b"\r\n\r\n") && c.read(&mut b).unwrap_or(0) == 1 {
                    head.push(b[0]);
                }
                let head = String::from_utf8_lossy(&head).to_lowercase();
                if head.starts_with("quit") || head.is_empty() {
                    break;
                }
                let path = head.lines().next().and_then(|l| l.split_whitespace().nth(1)).unwrap_or("").to_owned();
                let found = routes.iter().find(|(p, _, _)| *p == path);
                match found {
                    Some((_, content_type, body)) => {
                        let head = format!("HTTP/1.1 200 OK\r\nContent-Type: {content_type}\r\nContent-Length: {}\r\n\r\n", body.len());
                        let _ = c.write_all(head.as_bytes());
                        let _ = c.write_all(body);
                    }
                    None => {
                        let body = b"{\"errors\":[{\"code\":\"MANIFEST_UNKNOWN\"}]}";
                        let head = format!("HTTP/1.1 404 Not Found\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n", body.len());
                        let _ = c.write_all(head.as_bytes());
                        let _ = c.write_all(body);
                    }
                }
            }
        });
        (host, server)
    }

    fn digest_of(body: &[u8]) -> String {
        sha256_digest(body)
    }

    fn pull_case(platform: &str, routes: Vec<(String, &'static str, Vec<u8>)>, expect_err: Option<&str>) {
        let root = tmp_root("pull-case");
        let store = Store::open(&root).unwrap();
        let (host, server) = registry_stub(routes);
        let client = test_client();
        let reference = Reference::parse(&format!("{host}/test/repo:latest")).unwrap();
        let result = client.pull(&store, &reference, &Platform::parse(platform).unwrap(), &|_| {});
        match (result, expect_err) {
            (Ok(_), None) => assert!(store.find(&format!("{host}/test/repo:latest")).unwrap().is_some(), "record published"),
            (Err(e), Some(want)) => {
                let text = e.to_string();
                assert!(text.contains(want), "want {want:?} in {text:?}");
                assert!(store.find(&format!("{host}/test/repo:latest")).unwrap().is_none(), "no record on failure");
            }
            (Ok(_), Some(want)) => panic!("expected failure containing {want:?}, got Ok"),
            (Err(e), None) => panic!("expected success, got {e}"),
        }
        quit(&host);
        let _ = server.join();
        let _ = std::fs::remove_dir_all(&root);
    }

    fn image_routes(config_os: &str, config_arch: Option<&str>, arch_entry: Option<&str>) -> Vec<(String, &'static str, Vec<u8>)> {
        let layer = b"layer-bytes".to_vec();
        let layer_digest = digest_of(&layer);
        let cfg = match config_arch {
            Some(arch) => serde_json::to_vec(&json!({"os": config_os, "architecture": arch, "created": "2026-01-01T00:00:00Z", "config": {"Cmd": ["/bin/true"]}})).unwrap(),
            None => serde_json::to_vec(&json!({"os": config_os, "created": "2026-01-01T00:00:00Z", "config": {"Cmd": ["/bin/true"]}})).unwrap(),
        };
        let cfg_digest = digest_of(&cfg);
        let manifest = json!({
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "config": {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": cfg_digest, "size": cfg.len()},
            "layers": [{"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip", "digest": layer_digest, "size": layer.len()}],
        });
        let manifest_bytes = serde_json::to_vec(&manifest).unwrap();
        let manifest_digest = digest_of(&manifest_bytes);
        let mut routes = vec![
            ("/v2/test/repo/manifests/latest".to_owned(), "application/vnd.docker.distribution.manifest.list.v2+json", vec![]),
            (format!("/v2/test/repo/manifests/{manifest_digest}"), "application/vnd.oci.image.manifest.v1+json", manifest_bytes),
            (format!("/v2/test/repo/blobs/{cfg_digest}"), "application/vnd.oci.image.config.v1+json", cfg),
            (format!("/v2/test/repo/blobs/{layer_digest}"), "application/vnd.oci.image.layer.v1.tar+gzip", layer),
        ];
        // The index names the requested entry for both platforms, pointing
        // at the same manifest — the config decides.
        let entries = match arch_entry {
            Some(arch) => serde_json::json!([
                {"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": manifest_digest, "size": 0, "platform": {"os": config_os, "architecture": arch}}
            ]),
            None => serde_json::json!([
                {"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": manifest_digest, "size": 0, "platform": {"os": config_os, "architecture": "amd64"}},
                {"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": manifest_digest, "size": 0, "platform": {"os": config_os, "architecture": "arm64"}}
            ]),
        };
        let index = json!({"schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json", "manifests": entries});
        routes[0].2 = serde_json::to_vec(&index).unwrap();
        routes
    }

    #[test]
    fn pull_fails_when_config_disagrees_with_the_selection() {
        // The index's amd64 entry points at a manifest whose config says arm64.
        pull_case("linux/amd64", image_routes("linux", Some("arm64"), Some("amd64")), Some("image config is linux/arm64"));
        // No record: the previous tag record is untouched.
    }

    #[test]
    fn pull_fails_when_config_arch_is_missing() {
        pull_case("linux/arm64", image_routes("linux", None, Some("arm64")), Some("missing os or architecture"));
    }

    #[test]
    fn pull_fails_when_config_os_is_missing() {
        let layer = b"layer-bytes".to_vec();
        let layer_digest = digest_of(&layer);
        let cfg = serde_json::to_vec(&json!({"architecture": "arm64", "created": "2026-01-01T00:00:00Z", "config": {"Cmd": ["/bin/true"]}})).unwrap();
        let cfg_digest = digest_of(&cfg);
        let manifest = serde_json::to_vec(&json!({
            "schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "config": {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": cfg_digest, "size": cfg.len()},
            "layers": [{"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip", "digest": layer_digest, "size": layer.len()}],
        })).unwrap();
        let manifest_digest = digest_of(&manifest);
        let routes = vec![
            ("/v2/test/repo/manifests/latest".to_owned(), "application/vnd.docker.distribution.manifest.list.v2+json", serde_json::to_vec(&json!({"schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json", "manifests": [{"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": manifest_digest, "size": 0, "platform": {"os": "linux", "architecture": "arm64"}}]})).unwrap()),
            (format!("/v2/test/repo/manifests/{manifest_digest}"), "application/vnd.oci.image.manifest.v1+json", manifest),
            (format!("/v2/test/repo/blobs/{cfg_digest}"), "application/vnd.oci.image.config.v1+json", cfg),
            (format!("/v2/test/repo/blobs/{layer_digest}"), "application/vnd.oci.image.layer.v1.tar+gzip", layer),
        ];
        pull_case("linux/arm64", routes, Some("missing os or architecture"));
    }

    #[test]
    fn a_single_manifest_pull_fails_when_its_config_is_not_the_requested_platform() {
        let layer = b"layer-bytes".to_vec();
        let layer_digest = digest_of(&layer);
        let cfg = serde_json::to_vec(&json!({"os": "linux", "architecture": "amd64", "created": "2026-01-01T00:00:00Z", "config": {"Cmd": ["/bin/true"]}})).unwrap();
        let cfg_digest = digest_of(&cfg);
        let manifest = serde_json::to_vec(&json!({
            "schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "config": {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": cfg_digest, "size": cfg.len()},
            "layers": [{"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip", "digest": layer_digest, "size": layer.len()}],
        })).unwrap();
        let routes = vec![
            ("/v2/test/repo/manifests/latest".to_owned(), "application/vnd.oci.image.manifest.v1+json", manifest),
            (format!("/v2/test/repo/blobs/{cfg_digest}"), "application/vnd.oci.image.config.v1+json", cfg),
            (format!("/v2/test/repo/blobs/{layer_digest}"), "application/vnd.oci.image.layer.v1.tar+gzip", layer),
        ];
        pull_case("linux/arm64", routes, Some("image config is linux/amd64"));
    }

    #[test]
    fn a_pull_by_digest_fails_when_its_config_is_not_the_requested_platform() {
        let layer = b"layer-bytes".to_vec();
        let layer_digest = digest_of(&layer);
        let cfg = serde_json::to_vec(&json!({"os": "linux", "architecture": "amd64", "created": "2026-01-01T00:00:00Z", "config": {"Cmd": ["/bin/true"]}})).unwrap();
        let cfg_digest = digest_of(&cfg);
        let manifest = serde_json::to_vec(&json!({
            "schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
            "config": {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": cfg_digest, "size": cfg.len()},
            "layers": [{"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip", "digest": layer_digest, "size": layer.len()}],
        })).unwrap();
        let manifest_digest = digest_of(&manifest);
        let routes = vec![
            (format!("/v2/test/repo/manifests/{manifest_digest}"), "application/vnd.oci.image.manifest.v1+json", manifest.clone()),
            (format!("/v2/test/repo/blobs/{cfg_digest}"), "application/vnd.oci.image.config.v1+json", cfg),
            (format!("/v2/test/repo/blobs/{layer_digest}"), "application/vnd.oci.image.layer.v1.tar+gzip", layer),
        ];
        let root = tmp_root("pull-digest");
        let store = Store::open(&root).unwrap();
        let (host, server) = registry_stub(routes);
        let client = test_client();
        let reference = Reference::parse(&format!("{host}/test/repo@{manifest_digest}")).unwrap();
        let result = client.pull(&store, &reference, &Platform::parse("linux/arm64").unwrap(), &|_| {});
        let err = result.expect_err("digest pull must fail on disagreement");
        assert!(err.to_string().contains("image config is linux/amd64"), "{err}");
        assert!(store.find(&reference.short()).unwrap().is_none(), "no record on failure");
        quit(&host);
        let _ = server.join();
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn pull_accepts_a_matching_config_and_records_the_platform() {
        pull_case("linux/arm64", image_routes("linux", Some("arm64"), None), None);
    }
}
