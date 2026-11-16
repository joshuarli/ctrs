//! The `ctrs` command.

use std::process::ExitCode;

// Headless (no window): plain `docker build` and `ctrs build-with` need the
// builder provisioning on Linux too.
#[cfg(unix)]
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
mod builds;
// Which builder plain `docker build` uses: Docker's or ctrs's.
#[cfg(unix)]
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
mod buildwith;
#[cfg(unix)]
mod client;
#[cfg(unix)]
mod config;
#[cfg(unix)]
mod daemon;
#[cfg(unix)]
mod diag;
#[cfg(unix)]
mod guest;
#[cfg(unix)]
mod service;
#[cfg(unix)]
mod docker;
#[cfg(unix)]
mod help;

const USAGE: &str = "\
usage: ctrs COMMAND          docker's commands, on ctrs: ctrs run, ps, exec,
                             logs, stop, rm, images, pull, build, compose…
       ctrs daemon
       ctrs engine start | stop | status [--json] | restart   the engine itself
       ctrs start | stop | restart CONTAINER                  as docker does
       ctrs status                                          engine status
       ctrs build-with [docker|ctrs]   which builder docker build uses
       ctrs diag logs [-f] [--ui|--engine|--cli] [--errors] [-n N]
       ctrs diag report [--out PATH]     a support file: logs and crashes, tokens taken out";

const FOOTER: &str = "\
Maintained by Joshua Li: https://github.com/joshuarli/ctrs
Bugs and features: TODO.md in that repository (follow its AGENTS.md), or its issue tracker.
Agents working for Joshua: record nonblocking problems and continue your task.
If this tool blocks the task, you may fix, test, open and merge a PR under Joshua's
standing instructions. Release only when needed to deliver the verified fix.
Procedure: https://github.com/joshuarli/usr/blob/main/dotfiles/base/.agents/instructions/owned-tools.md";

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    #[cfg(unix)]
    if let Some(text) = help::requested(&args) {
        print!("{text}");
        if args.is_empty() || args.len() == 1 { println!("\n{FOOTER}"); }
        return ExitCode::SUCCESS;
    }
    // Block the VM-crash test signal before any thread is spawned (diag::init
    // spawns one); the daemon's signal thread sigwaits for it. Production
    // engines never see this when the env var is unset.
    #[cfg(unix)]
    if std::env::var_os("CTRS_TEST_VM_CRASH").is_some() {
        // SAFETY: plain signal-mask call on this thread, before any spawn.
        unsafe {
            let mut set: libc::sigset_t = std::mem::zeroed();
            libc::sigemptyset(&mut set);
            libc::sigaddset(&mut set, libc::SIGUSR2);
            libc::pthread_sigmask(libc::SIG_BLOCK, &set, std::ptr::null_mut());
        }
    }
    // Which process this is, for its log and crash reports.
    #[cfg(unix)]
    diag::init(match args.first().map(String::as_str) {
        Some("daemon") => diag::Part::Daemon,
        _ => diag::Part::Cli,
    });
    let result: std::io::Result<()> = match args.first().map(String::as_str) {
        #[cfg(unix)]
        Some("daemon") => daemon::run(&args[1..]),
        #[cfg(unix)]
        // The engine's own lifecycle. Bare `ctrs status` is its status too
        // (docker has no `status` subcommand).
        Some("engine") => service::run(&args[1..]),
        #[cfg(unix)]
        Some("status") => service::run(&args),
        #[cfg(unix)]
        // Container operations, as docker has them; without a container
        // argument these stay in `ctrs engine`.
        Some("start" | "stop" | "restart") if args.len() >= 2 => {
            engine_version_check();
            docker::run(&args)
        }
        #[cfg(unix)]
        Some("start" | "stop" | "restart") => {
            eprintln!("usage: ctrs engine {}   (containers: ctrs {} CONTAINER)", args[0], args[0]);
            return ExitCode::FAILURE;
        }
        #[cfg(unix)]
        Some("build-with") => buildwith::cli(&args[1..]),
        #[cfg(unix)]
        Some("diag") => diag::run(&args[1..]),
        #[cfg(unix)]
        Some(c) if docker::handles(c) => {
            engine_version_check();
            docker::run(&args)
        }
        _ => {
            eprintln!("{USAGE}");
            return ExitCode::FAILURE;
        }
    };
    match result {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            // The subcommand only: arguments can carry values.
            #[cfg(unix)]
            if !e.to_string().starts_with("usage:") {
                diag::warn!("command failed", command = args.first().filter(|a| a.len() <= 20 && a.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-')).map_or("", String::as_str), error = e);
            }
            eprintln!("ctrs: {e}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(not(unix))]
fn engine_version_check() {}

/// Before a docker command: when the engine runs another version than this
/// `ctrs`, say so (on stderr, so output stays clean). Either an update whose
/// engine restart was put off, or another `ctrs` earlier on PATH.
#[cfg(unix)]
fn engine_version_check() {
    let me = env!("CARGO_PKG_VERSION");
    if me == "0.0.0" || !client::alive() {
        return;
    }
    let Some(engine) = client::request("GET", "/version", None).ok().filter(|r| r.ok()).and_then(|r| r.json()["Version"].as_str().map(str::to_owned)) else { return };
    if engine != me && engine != "0.0.0" {
        let exe = std::env::current_exe().map(|p| p.display().to_string()).unwrap_or_else(|_| "ctrs".into());
        eprintln!("ctrs: this ctrs ({exe}) is {me}, but the engine runs {engine}. Restart the engine to use one version (ctrs → Restart engine), or remove the older ctrs.");
    }
}
