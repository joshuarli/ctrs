//! The `kiri` command.

use std::process::ExitCode;

// builds, cli_pins, scan and tools on Linux too: the daemon reads an
// image's layers and scans it; the CLI needs them as well.
#[cfg(unix)]
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
mod builds;
// Which builder plain `docker build` uses: Docker's or Kiri's.
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

const USAGE: &str = "\
usage: kiri COMMAND          docker's commands, on Kiri: kiri run, ps, exec,
                             logs, stop, rm, images, pull, build, compose…
       kiri daemon
       kiri engine start | stop | status [--json] | restart   the engine itself
       kiri start | stop | restart CONTAINER                  as docker does
       kiri status                                          engine status
       kiri build-with [docker|kiri]   which builder docker build uses
       kiri diag logs [-f] [--ui|--engine|--cli] [--errors] [-n N]
       kiri diag report [--out PATH]     a support file: logs and crashes, tokens taken out";

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
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
        // The engine's own lifecycle. Bare `kiri status` is its status too
        // (docker has no `status` subcommand).
        Some("engine") => service::run(&args[1..]),
        #[cfg(unix)]
        Some("status") => service::run(&args),
        #[cfg(unix)]
        // Container operations, as docker has them; without a container
        // argument these stay in `kiri engine`.
        Some("start" | "stop" | "restart") if args.len() >= 2 => {
            engine_version_check();
            docker::run(&args)
        }
        #[cfg(unix)]
        Some("start" | "stop" | "restart") => {
            eprintln!("usage: kiri engine {}   (containers: kiri {} CONTAINER)", args[0], args[0]);
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
            eprintln!("kiri: {e}");
            ExitCode::FAILURE
        }
    }
}

#[cfg(not(unix))]
fn engine_version_check() {}

/// Before a docker command: when the engine runs another version than this
/// `kiri`, say so (on stderr, so output stays clean). Either an update whose
/// engine restart was put off, or another `kiri` earlier on PATH.
#[cfg(unix)]
fn engine_version_check() {
    let me = env!("CARGO_PKG_VERSION");
    if me == "0.0.0" || !client::alive() {
        return;
    }
    let Some(engine) = client::request("GET", "/version", None).ok().filter(|r| r.ok()).and_then(|r| r.json()["Version"].as_str().map(str::to_owned)) else { return };
    if engine != me && engine != "0.0.0" {
        let exe = std::env::current_exe().map(|p| p.display().to_string()).unwrap_or_else(|_| "kiri".into());
        eprintln!("kiri: this kiri ({exe}) is {me}, but the engine runs {engine}. Restart the engine to use one version (Kiri → Restart engine), or remove the older kiri.");
    }
}
