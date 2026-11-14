//! The BuildKit builder Kiri provisions for `docker build`: a docker-container
//! builder on Kiri's engine, made on first use and reused after. Plain
//! `docker build` goes through it through `docker buildx` (see buildwith.rs).

use std::io;
use std::process::Command;

/// Kiri's BuildKit builder, a docker-container one on Kiri's context.
pub const BUILDER: &str = "kiri-build";

/// Makes the builder if it is not there (called at startup, cheap when it is).
pub fn ensure_builder() {
    let _ = builder();
}

pub fn builder() -> io::Result<bool> {
    let Some(docker) = crate::client::docker_cli() else { return Ok(false) };
    // buildx talks to the daemon, and can wait on it for good: give the
    // daemon (just started) a few seconds, else skip.
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(5);
    while !crate::client::alive() {
        if std::time::Instant::now() > deadline {
            return Err(io::Error::other("the Kiri daemon isn't answering yet"));
        }
        std::thread::sleep(std::time::Duration::from_millis(200));
    }
    let quiet = || std::process::Stdio::null();
    if !Command::new(&docker).args(["buildx", "version"]).stdout(quiet()).stderr(quiet()).status()?.success() {
        println!("docker build: no buildx plugin here, so docker builds with Kiri's classic builder API (the same BuildKit, run by the daemon)");
        return Ok(false);
    }
    let inspect = Command::new(&docker).args(["buildx", "inspect", BUILDER]).stderr(quiet()).output()?;
    let mut exists = inspect.status.success();
    // Without default-load a docker-container builder keeps what it builds
    // to itself: `docker build -t x .` builds and `docker run x` finds
    // nothing. One made without it is made again; --keep-state keeps its
    // cache volume, which the daemon's builder container reuses.
    if exists && !String::from_utf8_lossy(&inspect.stdout).contains("default-load") {
        exists = !Command::new(&docker).args(["buildx", "rm", "--keep-state", BUILDER]).stdout(quiet()).stderr(quiet()).status()?.success();
    }
    if !exists {
        // buildx create takes Kiri's context's name; without that context
        // (Linux makes it only in the optional "docker uses Kiri" step) buildx
        // reads the name as a host and fails on tcp://kiri:2375.
        ensure_context(&docker)?;
        let made = Command::new(&docker)
            .args(["buildx", "create", "--name", BUILDER, "--driver", "docker-container", "--driver-opt", "default-load=true", "kiri"])
            .stdout(quiet())
            .output()?;
        if !made.status.success() {
            return Err(io::Error::other(failure("docker buildx create failed", &made.stderr)));
        }
    }
    // Which builder plain `docker build` uses, Docker's or Kiri's, as
    // chosen (crate::buildwith): it needs this builder to exist.
    if let Err(e) = crate::buildwith::apply() {
        println!("docker build: could not set which builder it uses ({e})");
    }
    Ok(true)
}

#[cfg(unix)]
fn ensure_context(docker: impl AsRef<std::ffi::OsStr>) -> io::Result<()> {
    let docker = docker.as_ref();
    let quiet = || std::process::Stdio::null();
    if Command::new(docker).args(["context", "inspect", "kiri"]).stdout(quiet()).stderr(quiet()).status()?.success() {
        return Ok(());
    }
    let host = format!("host=unix://{}", crate::client::socket()?.display());
    let out = Command::new(docker).args(["context", "create", "kiri", "--description", "Kiri", "--docker", &host]).stdout(quiet()).output()?;
    if out.status.success() { Ok(()) } else { Err(io::Error::other(failure("docker context create failed", &out.stderr))) }
}

/// What failed, with the tool's own last error line when it gave one.
fn failure(what: &str, stderr: &[u8]) -> String {
    let err = String::from_utf8_lossy(stderr);
    match err.lines().map(str::trim).filter(|l| !l.is_empty()).last() {
        Some(line) => format!("{what}: {}", line.trim_start_matches("ERROR: ")),
        None => what.to_owned(),
    }
}


#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_failure_carries_the_tools_last_error_line() {
        assert_eq!(failure("docker buildx create failed", b""), "docker buildx create failed");
        assert_eq!(
            failure("docker buildx create failed", b"Warning: x\nERROR: failed to initialize builder kiri-build (kiri-build0): permission denied\n\n"),
            "docker buildx create failed: failed to initialize builder kiri-build (kiri-build0): permission denied"
        );
    }
}
