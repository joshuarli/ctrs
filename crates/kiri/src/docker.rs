//! `kiri ps`, `kiri run`, `kiri compose up`…: Docker's own commands, run
//! by the docker CLI against Kiri's daemon, over `DOCKER_HOST` (the URL of
//! the engine's Unix socket, set here — never a docker context).

use std::io;
#[cfg(unix)]
use std::os::unix::process::CommandExt;

#[cfg(unix)]
use crate::client;

/// The docker commands `kiri` answers. `import` is left out: `kiri import`
/// brings things over from OrbStack and Docker Desktop.
pub const COMMANDS: &[&str] = &[
    "attach", "build", "builder", "buildx", "commit", "compose", "container", "cp", "create", "diff", "events", "exec", "export", "history", "image", "images",
    "info", "inspect", "kill", "load", "login", "logout", "logs", "manifest", "network", "pause", "port", "ps", "pull", "push", "rename", "restart", "rm", "rmi",
    "run", "save", "search", "start", "stats", "stop", "system", "tag", "top", "unpause", "update", "version", "volume", "wait",
];

pub fn handles(command: &str) -> bool {
    COMMANDS.contains(&command)
}

/// Builds `docker <args>` with the engine's socket as `DOCKER_HOST` and any
/// docker context removed; used by [`run`] and by tests.
#[cfg(unix)]
fn docker_command(args: &[String], docker: &std::path::Path, socket: &std::path::Path) -> std::process::Command {
    let mut cmd = std::process::Command::new(docker);
    cmd.args(args).env("DOCKER_HOST", format!("unix://{}", socket.display())).env_remove("DOCKER_CONTEXT");
    // With DOCKER_HOST and no context, buildx would pick the endpoint's own
    // docker-driver builder, which needs BuildKit inside the engine: name
    // the engine's builder, if buildx knows it and the person hasn't picked one.
    if std::env::var_os("BUILDX_BUILDER").is_none() && buildx_knows(crate::builds::BUILDER) {
        cmd.env("BUILDX_BUILDER", crate::builds::BUILDER);
    }
    cmd
}

/// Replaces this process with `docker <args>`, so the terminal, signals and
/// the exit code are docker's own. Returns only if that fails.
#[cfg(unix)]
pub fn run(args: &[String]) -> io::Result<()> {
    let docker = client::docker_cli().ok_or_else(|| io::Error::other("no docker CLI found on PATH; install the Docker CLI, then retry"))?;
    let socket = client::socket()?;
    if !client::alive() {
        return Err(io::Error::other("the engine isn't running; start it with `kiri start` (or `kiri daemon`)"));
    }
    let mut cmd = docker_command(args, &docker, &socket);
    Err(cmd.exec())
}

/// buildx has a builder of this name: its instance file, in BUILDX_CONFIG,
/// else DOCKER_CONFIG/buildx, else ~/.docker/buildx.
#[cfg(unix)]
fn buildx_knows(name: &str) -> bool {
    let dir = std::env::var_os("BUILDX_CONFIG")
        .map(std::path::PathBuf::from)
        .or_else(|| std::env::var_os("DOCKER_CONFIG").map(|d| std::path::PathBuf::from(d).join("buildx")))
        .or_else(|| std::env::var_os("HOME").map(|h| std::path::PathBuf::from(h).join(".docker/buildx")));
    dir.is_some_and(|d| d.join("instances").join(name).is_file())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;
    use std::os::unix::fs::PermissionsExt;

    fn scratch_dir(tag: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("kiri-docker-delegation-{}-{}", std::process::id(), tag));
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn handles_the_docker_commands_and_not_import() {
        assert!(handles("run") && handles("ps") && handles("compose"));
        assert!(!handles("import") && !handles("share") && !handles(""));
    }

    #[test]
    fn delegates_argv_and_env_to_a_stub_docker() {
        let dir = scratch_dir("stub");
        let stub = dir.join("docker");
        // Records argv and the docker-relevant env; prints them for the parent.
        let script = "#!/bin/sh\nprintf 'argv:'; for a in \"$@\"; do printf ' %s' \"$a\"; done; echo; env | grep -E '^(DOCKER_HOST|DOCKER_CONTEXT|BUILDX_BUILDER)=' | sort\n";
        std::fs::write(&stub, script).unwrap();
        std::fs::set_permissions(&stub, std::fs::Permissions::from_mode(0o755)).unwrap();
        let out = docker_command(&["run".into(), "alpine".into(), "echo".into(), "hi".into()], &stub, std::path::Path::new("/tmp/ctrs-test.sock"))
            .output()
            .expect("the stub runs");
        let text = String::from_utf8_lossy(&out.stdout);
        assert_eq!(text.lines().next(), Some("argv: run alpine echo hi"));
        assert!(text.contains("DOCKER_HOST=unix:///tmp/ctrs-test.sock"));
        assert!(!text.contains("DOCKER_CONTEXT="), "a docker context must never reach the delegated CLI: {text}");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn env_remove_deletes_context_from_the_child_env() {
        let dir = scratch_dir("env");
        let cmd = docker_command(&["ps".into()], std::path::Path::new("/bin/true"), std::path::Path::new("/tmp/ctrs-test.sock"));
        let host = cmd.get_envs().find_map(|(k, v)| (k == "DOCKER_HOST").then(|| v.map(|v| v.to_os_string()))).flatten();
        assert_eq!(host.as_deref().and_then(|v| v.to_str()), Some("unix:///tmp/ctrs-test.sock"));
        let ctx = cmd.get_envs().find_map(|(k, v)| (k == "DOCKER_CONTEXT").then_some(v));
        assert!(matches!(ctx, Some(None)), "DOCKER_CONTEXT must be explicitly removed");
        let _ = std::fs::remove_dir_all(&dir);
    }
}
