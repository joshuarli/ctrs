use std::fmt::Write;

struct Command {
    path: &'static str,
    usage: &'static str,
    description: &'static str,
    details: &'static str,
    example: &'static str,
}

const NATIVE: &[Command] = &[
    Command { path: cli_daemon!(), usage: concat!("ctrs ", cli_daemon!()), description: "Run the engine in the foreground.", details: "Arguments are ignored.", example: concat!("ctrs ", cli_daemon!()) },
    Command { path: cli_engine!(), usage: concat!("ctrs ", cli_engine!(), " COMMAND"), description: "Manage the engine.", details: "COMMAND is required: start, stop, status or restart.", example: concat!("ctrs ", cli_engine!(), " ", cli_status!()) },
    Command { path: concat!(cli_engine!(), " ", cli_start!()), usage: concat!("ctrs ", cli_engine!(), " ", cli_start!()), description: "Start the engine in the background.", details: "", example: concat!("ctrs ", cli_engine!(), " ", cli_start!()) },
    Command { path: concat!(cli_engine!(), " ", cli_stop!()), usage: concat!("ctrs ", cli_engine!(), " ", cli_stop!()), description: "Stop the engine.", details: "", example: concat!("ctrs ", cli_engine!(), " ", cli_stop!()) },
    Command { path: concat!(cli_engine!(), " ", cli_status!()), usage: concat!("ctrs ", cli_engine!(), " ", cli_status!(), " [", cli_long_json!(), "]"), description: "Show engine status.", details: concat!(cli_long_json!(), "  Output JSON (default: text); exits 1 if the engine is stopped."), example: concat!("ctrs ", cli_engine!(), " ", cli_status!(), " ", cli_long_json!()) },
    Command { path: concat!(cli_engine!(), " ", cli_restart!()), usage: concat!("ctrs ", cli_engine!(), " ", cli_restart!()), description: "Restart the engine.", details: "", example: concat!("ctrs ", cli_engine!(), " ", cli_restart!()) },
    Command { path: cli_status!(), usage: concat!("ctrs ", cli_status!(), " [", cli_long_json!(), "]"), description: "Show engine status; alias for engine status.", details: concat!(cli_long_json!(), "  Output JSON (default: text); exits 1 if the engine is stopped."), example: concat!("ctrs ", cli_status!(), " ", cli_long_json!()) },
    Command { path: cli_build_with!(), usage: concat!("ctrs ", cli_build_with!(), " [docker|ctrs]"), description: "Show or select the builder for docker build.", details: "The optional value selects the builder; without it, show the current choice. Default: ctrs when no other engine is detected, otherwise docker. Additional arguments are ignored.", example: concat!("ctrs ", cli_build_with!(), " docker") },
    Command { path: cli_diag!(), usage: concat!("ctrs ", cli_diag!(), " COMMAND"), description: "Read diagnostics or create a report.", details: "COMMAND is required: logs or report.", example: concat!("ctrs ", cli_diag!(), " ", cli_logs!()) },
    Command { path: concat!(cli_diag!(), " ", cli_logs!()), usage: concat!("ctrs ", cli_diag!(), " ", cli_logs!(), " [", cli_short_f!(), "] [", cli_long_ui!(), "|", cli_long_engine!(), "|", cli_long_cli!(), "] [", cli_long_errors!(), "] [", cli_long_op!(), " ID] [", cli_short_n!(), " N]"), description: "Read recent logs, oldest first.", details: concat!(cli_short_f!(), ", ", cli_long_follow!(), "  Follow new lines.\n  ", cli_long_ui!(), ", ", cli_long_window!(), "  Include UI logs.\n  ", cli_long_engine!(), ", ", cli_long_daemon!(), "  Include engine logs.\n  ", cli_long_cli!(), "  Include CLI logs.\n  ", cli_long_errors!(), "  Include warnings and errors only.\n  ", cli_long_op!(), " ID  Include one operation.\n  ", cli_short_n!(), " N, -nN  Number of lines (default: 50).\n  Part selectors may repeat; default: all parts."), example: concat!("ctrs ", cli_diag!(), " ", cli_logs!(), " ", cli_long_engine!(), " ", cli_short_n!(), " 20") },
    Command { path: concat!(cli_diag!(), " ", cli_report!()), usage: concat!("ctrs ", cli_diag!(), " ", cli_report!(), " [", cli_long_out!(), " PATH]"), description: "Write a redacted support report.", details: concat!(cli_short_o!(), ", ", cli_long_out!(), " PATH  Output file (default: Desktop if present, otherwise HOME)."), example: concat!("ctrs ", cli_diag!(), " ", cli_report!(), " ", cli_long_out!(), " report.txt") },
];

const ENVIRONMENT: &str = "Environment: CTRS_SOCKET overrides the engine socket; HOME determines default paths.\nCTRS_STATE_DIR overrides diagnostic state; CTRS_LOG sets the log level; CTRS_OP tags logs.\nThe daemon also reads CTRS_GUEST_DIR, CTRS_CPUS, CTRS_MEMORY_MIB, CTRS_IDLE_SECS,\nCTRS_BUILDER_IDLE_SECS, CTRS_BUILD_CACHE_GB and CTRS_SOCKET_GROUP.\nOn Linux, CTRS_AGENT selects the agent and CTRS_BRIDGE_IPV6 enables IPv6.\nOn macOS, CTRS_VMNET, CTRS_NO_BALLOON and CTRS_BALLOON_QUIET_SECS affect the VM.\nDocker routes use DOCKER_CONFIG and BUILDX_CONFIG, set DOCKER_HOST, remove\nDOCKER_CONTEXT and may set BUILDX_BUILDER.";

fn block(out: &mut String, command: &Command) {
    let _ = writeln!(out, "  {}\n    {}", command.usage, command.description);
    if !command.details.is_empty() { let _ = writeln!(out, "    {}", command.details); }
}

pub fn render(path: Option<&str>) -> Option<String> {
    let mut out = String::new();
    if let Some(path) = path {
        if let Some(command) = NATIVE.iter().find(|c| c.path == path) {
            block(&mut out, command);
            out.push_str(concat!("\nOptions: ", cli_short_h!(), ", ", cli_long_help!(), "  Show help.\n\nExamples:\n  "));
            out.push_str(command.example);
            out.push_str(concat!("\n\nSee ctrs ", cli_long_help!(), " for the complete reference.\n"));
            return Some(out);
        }
        if let Some((name, example)) = crate::docker::COMMANDS.iter().find(|(name, _)| *name == path) {
            let _ = writeln!(out, concat!("ctrs {name} [DOCKER ARGS...]\n  Pass arguments to docker {name}; Docker defines its options and nested commands.\n\nOptions: ", cli_short_h!(), ", ", cli_long_help!(), "  Show help.\n\nExamples:\n  ctrs {name}{}{}\n\nSee ctrs ", cli_long_help!(), " for the complete reference."), if example.is_empty() { "" } else { " " }, example, name = name);
            return Some(out);
        }
        return None;
    }
    out.push_str(concat!("Usage: ctrs COMMAND [ARGS...]\n\nOptions:\n  ", cli_short_h!(), ", ", cli_long_help!(), "  Show help.\n\nCommands:\n"));
    for command in NATIVE { block(&mut out, command); }
    out.push_str("\nDocker compatibility routes:\n  Arguments, options and nested commands are passed through to the installed Docker CLI.\n  Docker defines their syntax; consult Docker's own help for details.\n  update: --memory VALUE sets a container memory limit.\n");
    for (name, _) in crate::docker::COMMANDS { let _ = writeln!(out, "  ctrs {name} [DOCKER ARGS...]  Run docker {name} against ctrs."); }
    let _ = writeln!(out, "\n{ENVIRONMENT}\n\nExamples:");
    for command in NATIVE { let _ = writeln!(out, "  {}", command.example); }
    for (name, example) in crate::docker::COMMANDS { let _ = writeln!(out, "  ctrs {name}{}{}", if example.is_empty() { "" } else { " " }, example); }
    Some(out)
}

pub fn requested(args: &[String]) -> Option<String> {
    if args.is_empty() || matches!(args, [flag] if flag == cli_short_h!() || flag == cli_long_help!()) { return render(None); }
    let (flag, path) = args.split_last()?;
    if flag != cli_short_h!() && flag != cli_long_help!() { return None; }
    if let Some(help) = render(Some(&path.join(" "))) { return Some(help); }
    if path.iter().any(|arg| arg == "--") { return None; }
    let command = match path.iter().map(String::as_str).collect::<Vec<_>>().as_slice() {
        [cli_engine!(), cli_status!(), ..] => concat!(cli_engine!(), " ", cli_status!()),
        [cli_status!(), ..] => cli_status!(),
        [cli_diag!(), cli_logs!(), ..] if !matches!(path.last().map(String::as_str), Some(cli_long_op!() | cli_short_n!())) => concat!(cli_diag!(), " ", cli_logs!()),
        [cli_diag!(), cli_report!(), ..] if !matches!(path.last().map(String::as_str), Some(cli_long_out!() | cli_short_o!())) => concat!(cli_diag!(), " ", cli_report!()),
        _ => return None,
    };
    render(Some(command))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashSet;

    #[test]
    fn help_does_not_consume_option_values_or_container_arguments() {
        for args in [vec!["diag", "logs", "--op", "-h"], vec!["diag", "report", "--out", "--help"], vec!["run", "alpine", "--help"], vec!["diag", "logs", "--", "--help"]] {
            assert!(requested(&args.into_iter().map(str::to_owned).collect::<Vec<_>>()).is_none());
        }
    }

    #[test]
    fn examples_follow_the_existing_parsers() {
        let mut native_paths = HashSet::new();
        for command in NATIVE {
            assert!(native_paths.insert(command.path));
            let args: Vec<String> = command.example.split_whitespace().skip(1).map(str::to_owned).collect();
            match args[0].as_str() {
                "daemon" => {},
                "engine" => crate::service::validate_args(&args[1..]).unwrap(),
                "status" => crate::service::validate_args(&args).unwrap(),
                "build-with" => assert!(args.get(1).is_none_or(|v| crate::buildwith::With::parse(v).is_some())),
                "diag" => match args[1].as_str() {
                    "logs" => crate::diag::report::validate_logs_args(&args[2..]).unwrap(),
                    "report" => crate::diag::report::validate_report_args(&args[2..]).unwrap(),
                    _ => panic!("unknown example: {}", command.example),
                },
                _ => panic!("unknown example: {}", command.example),
            }
        }
        let mut names = HashSet::new();
        for (name, example) in crate::docker::COMMANDS {
            assert!(names.insert(*name));
            assert!(crate::docker::handles(name));
            for arg in example.split_whitespace().filter(|arg| arg.starts_with('-')) {
                assert_eq!((*name, arg), ("update", "--memory"));
                assert!(render(None).unwrap().contains("update: --memory VALUE"));
            }
        }
    }
}
