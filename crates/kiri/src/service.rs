//! `kiri start|stop|status|restart`: bring the engine up detached, or stop it,
//! without any window or service manager.
//!
//! `kiri start` spawns `kiri daemon` in its own process group with stdio
//! detached; the child logs through `diag` to `~/.kiri/logs/daemon.log`.
//! `kiri stop` SIGTERMs the pid `~/.kiri/run/kiri.pid` records and waits for
//! the exit (at most 10 s). `kiri status` reports the running engine. A stale
//! pidfile (process gone, or not a kiri daemon) is reported stale, never
//! signalled, and cleaned up by `stop`.
//!
//! Nothing here creates a docker context; the socket is the contract.

use std::io;
use std::os::unix::process::CommandExt;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

const USAGE: &str = "usage: kiri start | kiri stop | kiri status [--json] | kiri restart";

fn pidfile() -> Option<PathBuf> {
    super::config::socket().ok().map(|s| s.with_file_name("kiri.pid"))
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

/// True when the pid looks like a `kiri daemon`, not a recycled pid.
fn ours(pid: u32) -> bool {
    let out = Command::new("ps").args(["-p", &pid.to_string(), "-o", "command="]).output();
    match out {
        Ok(o) => {
            let cmd = String::from_utf8_lossy(&o.stdout);
            cmd.contains("kiri") && cmd.contains("daemon")
        }
        Err(_) => false,
    }
}

fn engine_running() -> Option<(u32, u64)> {
    let path = pidfile()?;
    let (pid, started) = read_pid(&path)?;
    if alive(pid) && ours(pid) { Some((pid, started)) } else { None }
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

fn status(args: &[String]) -> io::Result<()> {
    let json = args.iter().any(|a| a == "--json");
    match engine_running() {
        Some((pid, started)) => {
            let rss_kb = Command::new("ps").args(["-o", "rss=", "-p", &pid.to_string()]).output().ok()
                .and_then(|o| String::from_utf8_lossy(&o.stdout).trim().parse::<u64>().ok());
            let uptime = (std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)).saturating_sub(started);
            if json {
                let v = serde_json::json!({"running": true, "pid": pid, "rss_kb": rss_kb.unwrap_or(0), "uptime_secs": uptime, "socket": super::config::socket()?.display().to_string()});
                println!("{v}");
            } else {
                let rss = rss_kb.map(|k| format!("{} MB", k / 1024)).unwrap_or_else(|| "?".to_owned());
                println!("kiri: running (pid {pid}, uptime {uptime}s, rss {rss}, socket {})", super::config::socket()?.display());
            }
            Ok(())
        }
        None => {
            if json {
                println!("{{\"running\":false}}");
            } else {
                println!("kiri: not running");
            }
            std::process::exit(1);
        }
    }
}

fn start() -> io::Result<()> {
    if let Some((pid, _)) = engine_running() {
        println!("kiri: already running (pid {pid})");
        return Ok(());
    }
    let exe = std::env::current_exe()?;
    let child = Command::new(&exe)
        .arg("daemon")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .process_group(0)
        .spawn()?;
    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        if let Some((pid, _)) = engine_running() {
            println!("kiri: running (pid {pid})");
            return Ok(());
        }
        if !alive(child.id()) {
            return Err(io::Error::other("the daemon did not stay up (see ~/.kiri/logs/daemon.log)"));
        }
        if Instant::now() > deadline {
            return Err(io::Error::other("the socket did not appear within 10s (see ~/.kiri/logs/daemon.log)"));
        }
        std::thread::sleep(Duration::from_millis(100));
    }
}

fn stop() -> io::Result<()> {
    match engine_running() {
        Some((pid, _)) => {
            stop_pid(pid)?;
            if wait_gone(pid, 10) {
                if let Some(path) = pidfile() {
                    let _ = std::fs::remove_file(path);
                }
                println!("kiri: stopped");
                Ok(())
            } else {
                Err(io::Error::other("the daemon did not exit within 10s"))
            }
        }
        None => {
            if let Some(path) = pidfile()
                && path.exists()
            {
                let _ = std::fs::remove_file(path);
                println!("kiri: not running (removed stale pidfile)");
            } else {
                println!("kiri: not running");
            }
            Ok(())
        }
    }
}

pub fn run(args: &[String]) -> io::Result<()> {
    match args.first().map(String::as_str) {
        Some("start") => start(),
        Some("stop") => stop(),
        Some("status") => status(&args[1..]),
        Some("restart") => {
            stop()?;
            start()
        }
        _ => Err(io::Error::other(USAGE)),
    }
}
