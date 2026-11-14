//! Bind sources as clients send them. Tools that drive the engine mount its
//! socket into containers (Testcontainers' Ryuk, CI runners); that source is
//! made into a path this daemon can mount.

use std::path::Path;

use super::engine::Error;

/// One `-v` spec (HostConfig.Binds) as source, target and options.
pub fn split(spec: &str) -> Result<(String, String, String), Error> {
    let bad = || Error::BadRequest(format!("invalid volume specification: {spec}"));
    let Some(i) = spec.find(':') else { return Err(bad()) };
    let (src, rest) = (&spec[..i], &spec[i + 1..]);
    let (dst, opts) = match rest.split(':').collect::<Vec<_>>().as_slice() {
        [d] => (*d, ""),
        [d, o] => (*d, *o),
        _ => return Err(bad()),
    };
    Ok((src.to_owned(), dst.to_owned(), opts.to_owned()))
}

/// Single slashes, none at the end.
fn clean(p: &str) -> String {
    let mut out = String::with_capacity(p.len());
    for c in p.chars() {
        if c == '/' && out.ends_with('/') {
            continue;
        }
        out.push(c);
    }
    if out.len() > 1 && out.ends_with('/') {
        out.pop();
    }
    out
}

/// Where a container that mounts the engine's socket is given one in the
/// VM: the agent relays it to the daemon (crates/kiri-init/src/linux/relay.rs).
#[cfg(target_os = "macos")]
const VM_ENGINE_SOCK: &str = "/run/host-services/docker.sock";

/// The paths clients mean as "the engine" when they mount it into a
/// container: Docker's own, and on the Mac the socket the client was given
/// (`DOCKER_HOST=unix://~/.kiri/run/docker.sock`, which Testcontainers
/// mounts into Ryuk).
const ENGINE_SOCKS: &[&str] = &["/var/run/docker.sock", "/run/docker.sock", "/private/var/run/docker.sock"];

/// What to mount for a bind of `src`, when it is the engine's socket. On a
/// Mac the VM's relay to this daemon, as Docker Desktop and OrbStack give
/// the VM's engine. On a Linux host a socket at that path is
/// mounted as it is, as Docker does (Docker's own, or the package's link to
/// Kiri); a missing `/var/run/docker.sock` is Kiri's, rather than a new
/// empty directory.
pub fn engine_socket(src: &str) -> Option<String> {
    let own = super::socket_path().ok()?;
    let own = own.to_string_lossy();
    engine_socket_for(src, &own, |p| Path::new(p).exists())
}

fn engine_socket_for(src: &str, own: &str, exists: impl Fn(&str) -> bool) -> Option<String> {
    let src = clean(src);
    #[cfg(target_os = "macos")]
    {
        let _ = exists;
        (ENGINE_SOCKS.contains(&src.as_str()) || src == own).then(|| VM_ENGINE_SOCK.to_owned())
    }
    #[cfg(not(target_os = "macos"))]
    {
        (ENGINE_SOCKS.contains(&src.as_str()) && !exists(&src)).then(|| own.to_owned())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ok(spec: &str) -> (String, String, String) {
        split(spec).unwrap_or_else(|e| panic!("{spec}: {e:?}"))
    }

    fn t(s: &str, d: &str, o: &str) -> (String, String, String) {
        (s.into(), d.into(), o.into())
    }

    #[test]
    fn splits_on_every_colon() {
        assert_eq!(ok("/src:/app:ro"), t("/src", "/app", "ro"));
        assert_eq!(ok("/src:/app"), t("/src", "/app", ""));
        assert_eq!(ok("data:/var/lib/data"), t("data", "/var/lib/data", ""));
        assert_eq!(ok("data:/var/lib/data:ro,nocopy"), t("data", "/var/lib/data", "ro,nocopy"));
    }

    #[test]
    fn bad_specs_are_refused() {
        for spec in ["nocolon", "a:b:c:d"] {
            assert!(split(spec).is_err(), "{spec} should be refused");
        }
    }

    #[test]
    fn engine_socket_aliases() {
        let none = |_: &str| false;
        let all = |_: &str| true;
        #[cfg(target_os = "macos")]
        {
            let own = "/Users/me/.kiri/run/docker.sock";
            for s in ["/var/run/docker.sock", "/private/var/run/docker.sock", "/run/docker.sock", own, "/Users/me/.kiri/run//docker.sock"] {
                assert_eq!(engine_socket_for(s, own, all).as_deref(), Some(VM_ENGINE_SOCK), "{s}");
            }
            assert_eq!(engine_socket_for("/Users/me/.orbstack/run/docker.sock", own, none), None);
        }
        #[cfg(not(target_os = "macos"))]
        {
            let own = "/run/kiri/docker.sock";
            assert_eq!(engine_socket_for("/var/run/docker.sock", own, none).as_deref(), Some(own));
            assert_eq!(engine_socket_for("/run/docker.sock", own, none).as_deref(), Some(own));
            // Docker's socket, or the package's link to Kiri's: mounted as it is.
            assert_eq!(engine_socket_for("/var/run/docker.sock", own, all), None);
            assert_eq!(engine_socket_for(own, own, all), None);
        }
        assert_eq!(engine_socket_for("/srv/app.sock", "/x/docker.sock", none), None);
    }
}
