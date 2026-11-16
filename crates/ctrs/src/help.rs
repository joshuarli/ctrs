use std::fmt::Write;

struct Command {
    path: &'static str,
    usage: &'static str,
    description: &'static str,
    details: &'static str,
    example: &'static str,
}

const NATIVE: &[Command] = &[
    Command { path: "daemon", usage: "ctrs daemon", description: "Run the engine in the foreground.", details: "Arguments are ignored.", example: "ctrs daemon" },
    Command { path: "engine", usage: "ctrs engine COMMAND", description: "Manage the engine.", details: "COMMAND is required: start, stop, status or restart.", example: "ctrs engine status" },
    Command { path: "engine start", usage: "ctrs engine start", description: "Start the engine in the background.", details: "", example: "ctrs engine start" },
    Command { path: "engine stop", usage: "ctrs engine stop", description: "Stop the engine.", details: "", example: "ctrs engine stop" },
    Command { path: "engine status", usage: "ctrs engine status [--json]", description: "Show engine status.", details: "--json  Output JSON (default: text); exits 1 if the engine is stopped.", example: "ctrs engine status --json" },
    Command { path: "engine restart", usage: "ctrs engine restart", description: "Restart the engine.", details: "", example: "ctrs engine restart" },
    Command { path: "status", usage: "ctrs status [--json]", description: "Show engine status; alias for engine status.", details: "--json  Output JSON (default: text); exits 1 if the engine is stopped.", example: "ctrs status --json" },
    Command { path: "build-with", usage: "ctrs build-with [docker|ctrs]", description: "Show or select the builder for docker build.", details: "The optional value selects the builder; without it, show the current choice. Default: ctrs when no other engine is detected, otherwise docker. Additional arguments are ignored.", example: "ctrs build-with docker" },
    Command { path: "diag", usage: "ctrs diag COMMAND", description: "Read diagnostics or create a report.", details: "COMMAND is required: logs or report.", example: "ctrs diag logs" },
    Command { path: "diag logs", usage: "ctrs diag logs [-f] [--ui|--engine|--cli] [--errors] [--op ID] [-n N]", description: "Read recent logs, oldest first.", details: "-f, --follow  Follow new lines.\n  --ui, --window  Include UI logs.\n  --engine, --daemon  Include engine logs.\n  --cli  Include CLI logs.\n  --errors  Include warnings and errors only.\n  --op ID  Include one operation.\n  -n N, -nN  Number of lines (default: 50).\n  Part selectors may repeat; default: all parts.", example: "ctrs diag logs --engine -n 20" },
    Command { path: "diag report", usage: "ctrs diag report [--out PATH]", description: "Write a redacted support report.", details: "-o, --out PATH  Output file (default: Desktop if present, otherwise HOME).", example: "ctrs diag report --out report.txt" },
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
            out.push_str("\nOptions: -h, --help  Show help.\n\nExamples:\n  ");
            out.push_str(command.example);
            out.push_str("\n\nSee ctrs --help for the complete reference.\n");
            return Some(out);
        }
        if let Some((name, example)) = crate::docker::COMMANDS.iter().find(|(name, _)| *name == path) {
            let _ = writeln!(out, "ctrs {name} [DOCKER ARGS...]\n  Pass arguments to docker {name}; Docker defines its options and nested commands.\n\nOptions: -h, --help  Show help.\n\nExamples:\n  ctrs {name}{}{}\n\nSee ctrs --help for the complete reference.", if example.is_empty() { "" } else { " " }, example);
            return Some(out);
        }
        return None;
    }
    out.push_str("Usage: ctrs COMMAND [ARGS...]\n\nOptions:\n  -h, --help  Show help.\n\nCommands:\n");
    for command in NATIVE { block(&mut out, command); }
    out.push_str("\nDocker compatibility routes:\n  Arguments, options and nested commands are passed through to the installed Docker CLI.\n  Docker defines their syntax; consult Docker's own help for details.\n  update: --memory VALUE sets a container memory limit.\n");
    for (name, _) in crate::docker::COMMANDS { let _ = writeln!(out, "  ctrs {name} [DOCKER ARGS...]  Run docker {name} against ctrs."); }
    let _ = writeln!(out, "\n{ENVIRONMENT}\n\nExamples:");
    for command in NATIVE { let _ = writeln!(out, "  {}", command.example); }
    for (name, example) in crate::docker::COMMANDS { let _ = writeln!(out, "  ctrs {name}{}{}", if example.is_empty() { "" } else { " " }, example); }
    Some(out)
}

pub fn requested(args: &[String]) -> Option<String> {
    if args.is_empty() || matches!(args, [flag] if flag == "-h" || flag == "--help") { return render(None); }
    let (flag, path) = args.split_last()?;
    if flag != "-h" && flag != "--help" { return None; }
    if let Some(help) = render(Some(&path.join(" "))) { return Some(help); }
    if path.iter().any(|arg| arg == "--") { return None; }
    let command = match path.iter().map(String::as_str).collect::<Vec<_>>().as_slice() {
        ["engine", "status", ..] => "engine status",
        ["status", ..] => "status",
        ["diag", "logs", ..] if !matches!(path.last().map(String::as_str), Some("--op" | "-n")) => "diag logs",
        ["diag", "report", ..] if !matches!(path.last().map(String::as_str), Some("--out" | "-o")) => "diag report",
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
