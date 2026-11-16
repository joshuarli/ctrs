//! `ctrs engine start|stop|status|restart`: bring the engine up detached, or
//! stop it, without any window or service manager.
//!
//! `ctrs engine start` spawns `ctrs daemon` in its own process group with
//! stdio detached and waits for the socket to answer the API — not for a
//! pidfile to appear. `ctrs engine stop` asks the engine itself to shut down
//! (POST /ctrs/shutdown over the instance's own socket, the same teardown as
//! SIGTERM); the pidfile is only a fallback for a wedged socket, and it is
//! signalled only when the recorded process is verified against the OS
//! (alive, named like a daemon, started when the pidfile says it did).
//! A stale pidfile is reported stale, never signalled, and cleaned up by
//! `stop`. The pidfile is named for the socket (`<socket>.pid`), so engines
//! in one directory never share lifecycle metadata.
//!
//! Nothing here creates a docker context; the socket is the contract.

use std::io;
use std::os::unix::process::CommandExt;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

const USAGE: &str = "usage: ctrs engine start | ctrs engine stop | ctrs engine status [--json] | ctrs engine restart\n       (`ctrs start|stop|restart CONTAINER` drive containers, as docker does)";

fn socket() -> io::Result<PathBuf> {
    super::config::socket()
}

fn pidfile() -> Option<PathBuf> {
    socket().ok().map(|s| super::config::pidfile(&s))
}

/// `(pid, start-time-in-unix-seconds)` from the pidfile.
fn read_pid(path: &std::path::Path) -> Option<(u32, u64)> {
    let text = std::fs::read_to_string(path).ok()?;
    let mut parts = text.split_whitespace();
    let pid = parts.next()?.parse().ok()?;
    let started = parts.next().and_then(|v| v.parse().ok()).unwrap_or(0);
    Some((pid, started))
}

/// `kill(pid, 0)`: alive (or EPERM, which means alive and not ours — treat as alive).
fn alive(pid: u32) -> bool {
    let pid = pid as i32;
    // SAFETY: no target of the signal; only the existence check.
    let rc = unsafe { libc::kill(pid, 0) };
    rc == 0 || std::io::Error::last_os_error().raw_os_error() == Some(libc::EPERM)
}

/// This process's start time in unix seconds, from the OS. Used only to
/// recognise a recycled pid; fails closed when the OS will not say.
fn process_start_secs(pid: u32) -> Option<u64> {
    #[cfg(target_os = "linux")]
    {
        let stat = std::fs::read_to_string(format!("/proc/{pid}/stat")).ok()?;
        let after = stat.rsplit_once(") ")?.1;
        let field = |n: usize| after.split_whitespace().nth(n);
        let starttime: u64 = field(19)?.parse().ok()?;
        let btime = std::fs::read_to_string("/proc/stat")
            .ok()?
            .split_whitespace()
            .collect::<Vec<_>>()
            .windows(2)
            .find(|w| w[0] == "btime")?[1]
            .parse::<u64>()
            .ok()?;
        // clk_tck is 100 on Linux; do not assume more than the file says.
        Some(btime + starttime / 100)
    }
    #[cfg(target_os = "macos")]
    {
        let mut info: libc::proc_bsdinfo = unsafe { std::mem::zeroed() };
        let size = std::mem::size_of::<libc::proc_bsdinfo>() as i32;
        // SAFETY: info is a valid out buffer of `size` for this pid.
        let written = unsafe { libc::proc_pidinfo(pid as i32, libc::PROC_PIDTBSDINFO, 0, &mut info as *mut _ as *mut libc::c_void, size) };
        (written == (std::mem::size_of::<libc::proc_bsdinfo>() as i32)).then_some(info.pbi_start_tvsec as u64)
    }
    #[cfg(not(any(target_os = "linux", target_os = "macos")))]
    {
        let _ = pid;
        None
    }
}

/// The pidfile's contents name a live process started within two seconds of
/// the recorded start, or nothing may be signalled.
fn pidfile_identity(pid: u32, started: u64) -> bool {
    alive(pid) && process_start_secs(pid).is_some_and(|s| s.abs_diff(started) <= 2)
}

/// What the socket answers, when it answers at all: the engine's pid.
fn socket_pid() -> Option<u32> {
    let r = super::client::request("GET", "/version", None).ok().filter(|r| r.ok())?;
    r.json()["EnginePid"].as_u64().map(|p| p as u32)
}

fn engine_running() -> Option<(u32, u64)> {
    let sock = socket().ok()?;
    if let Some(pid) = socket_pid() {
        // The socket itself identifies the engine; the pidfile only adds
        // the start time for the signal fallback.
        let started = pidfile().and_then(|p| read_pid(&p)).filter(|(p, _)| *p == pid).map(|(_, s)| s).unwrap_or(0);
        return Some((pid, started));
    }
    // Socket dead: only a pidfile that names a live, start-time-matching
    // process counts as running.
    let path = super::config::pidfile(&sock);
    let (pid, started) = read_pid(&path)?;
    pidfile_identity(pid, started).then_some((pid, started))
}

fn stop_pid(pid: u32) -> io::Result<()> {
    // SAFETY: SIGTERM to this pid only; it is ours by the caller's check.
    let rc = unsafe { libc::kill(pid as i32, libc::SIGTERM) };
    if rc != 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(())
}

fn wait_gone(pid: u32, secs: u64) -> bool {
    for _ in 0..secs * 10 {
        if !alive(pid) {
            return true;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    false
}

fn wait_socket_dead(secs: u64) -> bool {
    for _ in 0..secs * 10 {
        if socket_pid().is_none() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    false
}

fn status_json(args: &[String]) -> io::Result<bool> {
    let json = args.iter().any(|a| a == cli_long_json!());
    let unexpected: Vec<&String> = args.iter().filter(|a| a.as_str() != cli_long_json!()).collect();
    if !unexpected.is_empty() {
        return Err(io::Error::other(format!("ctrs engine status: unexpected arguments: {}", unexpected.iter().map(|a| a.as_str()).collect::<Vec<_>>().join(" "))));
    }
    Ok(json)
}

fn status(args: &[String]) -> io::Result<()> {
    let json = status_json(args)?;
    match engine_running() {
        Some((pid, started)) => {
            let rss_kb = Command::new("ps").args(["-o", "rss=", "-p", &pid.to_string()]).output().ok()
                .and_then(|o| String::from_utf8_lossy(&o.stdout).trim().parse::<u64>().ok());
            let uptime = (std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)).saturating_sub(started);
            if json {
                let mut v = serde_json::json!({"running": true, "pid": pid, "rss_kb": rss_kb.unwrap_or(0), "socket": super::config::socket()?.display().to_string()});
                if started != 0 {
                    v["uptime_secs"] = serde_json::json!(uptime);
                }
                println!("{v}");
            } else {
                let rss = rss_kb.map(|k| format!("{} MB", k / 1024)).unwrap_or_else(|| "?".to_owned());
                let up = if started != 0 { format!(", uptime {uptime}s") } else { String::new() };
                println!("ctrs: running (pid {pid}{up}, rss {rss}, socket {})", super::config::socket()?.display());
            }
            Ok(())
        }
        None => {
            if json {
                println!("{{\"running\":false}}");
            } else {
                println!("ctrs: not running");
            }
            std::process::exit(1);
        }
    }
}

fn start() -> io::Result<()> {
    if let Some((pid, _)) = engine_running() {
        println!("ctrs: already running (pid {pid})");
        return Ok(());
    }
    let exe = std::env::current_exe()?;
    let mut child = Command::new(&exe)
        .arg(cli_daemon!())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .process_group(0)
        .spawn()?;
    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        // The socket answers only once the engine is booted; the pidfile
        // does not exist before then, so readiness means readiness.
        if let Some(pid) = socket_pid() {
            println!("ctrs: running (pid {pid})");
            return Ok(());
        }
        match child.try_wait()? {
            Some(status) => {
                // Lost the bind race to a sibling start: the socket answers
                // with that engine's identity, so this one succeeded too.
                if let Some(pid) = socket_pid() {
                    println!("ctrs: running (pid {pid})");
                    return Ok(());
                }
                return Err(io::Error::other(format!("the daemon exited during startup ({status}); see ~/.local/share/ctrs/logs/daemon.log")));
            }
            None => {}
        }
        if Instant::now() > deadline {
            return Err(io::Error::other("the socket did not answer within 10s (see ~/.local/share/ctrs/logs/daemon.log)"));
        }
        std::thread::sleep(Duration::from_millis(50));
    }
}

fn stop() -> io::Result<()> {
    // The engine itself: the same teardown as SIGTERM, asked for over the
    // socket rather than signalled at a pid.
    if let Ok(r) = super::client::request("POST", "/ctrs/shutdown", None)
        && r.ok()
    {
        if wait_socket_dead(10) {
            println!("ctrs: stopped");
            return Ok(());
        }
        return Err(io::Error::other("the engine did not exit within 10s of being asked to stop"));
    }
    // Fallback: a wedged socket or a daemon that never came up. The pidfile
    // gets signalled only when its process is verified against the OS.
    match pidfile().and_then(|path| read_pid(&path).map(|p| (p, path))) {
        Some(((pid, started), path)) => {
            if pidfile_identity(pid, started) {
                stop_pid(pid)?;
                if wait_gone(pid, 10) {
                    let _ = std::fs::remove_file(&path);
                    println!("ctrs: stopped");
                    Ok(())
                } else {
                    Err(io::Error::other("the daemon did not exit within 10s"))
                }
            } else {
                if alive(pid) {
                    Err(io::Error::other(format!("pid {pid} does not look like this engine's daemon; refusing to signal it (verify ~/.local/share/ctrs/logs/daemon.log and the process)")))
                } else {
                    let _ = std::fs::remove_file(&path);
                    println!("ctrs: not running (removed stale pidfile)");
                    Ok(())
                }
            }
        }
        None => {
            println!("ctrs: not running");
            Ok(())
        }
    }
}

fn validate(args: &[String]) -> io::Result<()> {
    match args.first().map(String::as_str) {
        Some(cli_start!() | cli_stop!() | cli_restart!()) if args.len() == 1 => Ok(()),
        Some(cli_start!() | cli_stop!() | cli_restart!()) => Err(io::Error::other(format!("ctrs engine: unexpected arguments: {}", args[1..].join(" ")))),
        Some(cli_status!()) => status_json(&args[1..]).map(drop),
        _ => Err(io::Error::other(USAGE)),
    }
}

#[cfg(test)]
pub(crate) fn validate_args(args: &[String]) -> io::Result<()> { validate(args) }

pub fn run(args: &[String]) -> io::Result<()> {
    validate(args)?;
    match args[0].as_str() {
        cli_start!() => start(),
        cli_stop!() => stop(),
        cli_status!() => status(&args[1..]),
        cli_restart!() => { stop()?; start() }
        _ => unreachable!(),
    }
}

#[cfg(test)]
mod tests {
    use crate::config::pidfile;

    #[test]
    fn the_pidfile_is_named_for_the_socket() {
        assert_eq!(pidfile(std::path::Path::new("/tmp/a.sock")), std::path::Path::new("/tmp/a.sock.pid"));
        assert_eq!(pidfile(std::path::Path::new("/tmp/a.sock")), pidfile(std::path::Path::new("/tmp/a.sock")));
        assert_ne!(pidfile(std::path::Path::new("/tmp/a.sock")), pidfile(std::path::Path::new("/tmp/b.sock")));
    }
}
