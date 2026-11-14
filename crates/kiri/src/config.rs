//! The engine's typed configuration.
//!
//! `vm.json` (the VM's CPUs and memory, written by the
//! `PUT /kiri/resources` API) and the `KIRI_*` environment that overrides
//! it are read here and nowhere else. Network mode and policy have no
//! configuration surface and are deliberately absent.
//!
//! The on-disk format is unchanged from what the settings writer produced:
//! `vm.json` keeps its two optional keys; unknown keys are ignored on load
//! and dropped on save (the JSON writer always rewrote exactly those two).

use std::io;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};

/// `~/.kiri/vm.json`: `{"cpus": N, "memory_mib": N}`. Both optional;
/// missing means "the default". Unknown fields are ignored on load and
/// dropped on save, exactly as the JSON writer did.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct Resources {
    pub cpus: Option<u64>,
    pub memory_mib: Option<u64>,
}

impl Resources {
    /// `~/.kiri/vm.json` (`KIRI_STATE_DIR` moves the diag state dir).
    pub fn path() -> Option<PathBuf> {
        super::diag::state_dir().map(|d| d.join("vm.json"))
    }

    /// Reads the file; missing or corrupt means defaults (as before).
    pub fn load() -> Resources {
        Resources::path()
            .and_then(|p| std::fs::read(p).ok())
            .and_then(|b| serde_json::from_slice(&b).ok())
            .unwrap_or_default()
    }

    /// Writes the file atomically (tmp + rename), readable only by the user.
    pub fn save(&self) -> io::Result<()> {
        let Some(path) = Resources::path() else {
            return Err(io::Error::other("HOME is not set"));
        };
        let tmp = path.with_extension("json.tmp");
        std::fs::write(&tmp, serde_json::to_vec(self).map_err(io::Error::other)?)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&tmp, std::fs::Permissions::from_mode(0o600))?;
        }
        std::fs::rename(&tmp, &path)
    }
}

/// `~/.kiri/run/docker.sock`, beside OrbStack's `~/.orbstack/run/docker.sock`;
/// `KIRI_SOCKET` overrides it.
pub fn socket() -> io::Result<PathBuf> {
    if let Some(s) = std::env::var_os("KIRI_SOCKET") {
        return Ok(PathBuf::from(s));
    }
    let home = std::env::var_os("HOME").map(PathBuf::from).ok_or_else(|| io::Error::other("HOME is not set"))?;
    Ok(home.join(".kiri").join("run/docker.sock"))
}

/// The lifecycle pidfile for one socket: `<socket>.pid`, not a fixed name
/// beside it. Distinct endpoints in one directory own distinct pidfiles,
/// so one engine can never claim another's lifecycle metadata.
pub fn pidfile(socket: &std::path::Path) -> PathBuf {
    let mut name = socket.as_os_str().to_owned();
    name.push(".pid");
    PathBuf::from(name)
}

/// Where the kernel, initramfs and data-disk template live: `KIRI_GUEST_DIR`
/// overrides; else `guest/out` (or `guest/out/x86_64`) relative to the
/// binary, following links from PATH to the real file.
#[cfg(target_os = "macos")]
pub fn guest_dir() -> PathBuf {
    if let Some(d) = std::env::var_os("KIRI_GUEST_DIR") {
        return PathBuf::from(d);
    }
    let exe = std::env::current_exe().ok().map(|e| e.canonicalize().unwrap_or(e));
    let built = if cfg!(target_arch = "x86_64") { "guest/out/x86_64" } else { "guest/out" };
    exe.as_ref()
        .and_then(|e| e.ancestors().find(|d| d.join("Cargo.lock").is_file() && d.join("guest").is_dir()))
        .map(|r| r.join(built))
        .unwrap_or_else(|| PathBuf::from(built))
}

#[cfg(all(test, target_os = "macos"))]
mod tests {
    use super::*;

    #[test]
    fn vm_json_round_trip() {
        let r = Resources { cpus: Some(4), memory_mib: Some(4096) };
        let json = serde_json::to_string(&r).unwrap();
        assert_eq!(json, r#"{"cpus":4,"memory_mib":4096}"#);
        let back: Resources = serde_json::from_str(&json).unwrap();
        assert_eq!(back, r);
        // Empty file semantics: an empty object means defaults.
        let empty: Resources = serde_json::from_str("{}").unwrap();
        assert_eq!(empty, Resources::default());
        // Unknown keys are ignored, like the JSON reader did.
        let extra: Resources = serde_json::from_str(r#"{"cpus":2,"mystery":true}"#).unwrap();
        assert_eq!(extra.cpus, Some(2));
    }

    #[test]
    fn missing_file_is_defaults() {
        let back: Resources = serde_json::from_slice(b"").unwrap_or_default();
        assert_eq!(back, Resources::default());
    }
}
