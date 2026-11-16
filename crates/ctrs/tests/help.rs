use std::process::Command;

#[test]
fn top_level_help_is_offline_and_ends_with_the_owned_footer() {
    let mut reference = None;
    for args in [&[][..], &["-h"][..], &["--help"][..]] {
        let output = Command::new(env!("CARGO_BIN_EXE_ctrs"))
            .args(args)
            .env_clear()
            .output()
            .unwrap();
        assert!(output.status.success());
        assert!(output.stderr.is_empty());
        let help = String::from_utf8(output.stdout).unwrap();
        assert_eq!(help.matches("Maintained by Joshua Li: https://github.com/joshuarli/ctrs").count(), 1);
        assert!(help.ends_with("Maintained by Joshua Li: https://github.com/joshuarli/ctrs\nBugs and features: TODO.md in that repository (follow its AGENTS.md), or its issue tracker.\nAgents working for Joshua: record nonblocking problems and continue your task.\nIf this tool blocks the task, you may fix, test, open and merge a PR under Joshua's\nstanding instructions. Release only when needed to deliver the verified fix.\nProcedure: https://github.com/joshuarli/usr/blob/main/dotfiles/base/.agents/instructions/owned-tools.md\n"));
        if let Some(reference) = &reference {
            assert_eq!(&help, reference);
        } else {
            reference = Some(help);
        }
    }
}

#[test]
fn every_published_route_has_offline_short_and_long_help() {
    let output = Command::new(env!("CARGO_BIN_EXE_ctrs")).arg("--help").env_clear().output().unwrap();
    let text = String::from_utf8(output.stdout).unwrap();
    assert!(text.contains("\nExamples:\n"));
    assert!(text.contains("--op ID"));
    assert!(text.contains("--window"));
    assert!(text.contains("--daemon"));
    assert!(text.contains("-o, --out PATH"));
    let commands = text.split("\nExamples:\n").next().unwrap();
    let mut paths = Vec::new();
    for line in commands.lines().filter(|line| line.starts_with("  ctrs ")) {
        let mut words = line.split_whitespace().skip(1);
        let first = words.next().unwrap();
        let mut path = vec![first.to_owned()];
        if first == "engine" || first == "diag" {
            let second = words.next().unwrap();
            if !second.starts_with('[') && second != "COMMAND" { path.push(second.to_owned()); }
        }
        paths.push(path);
    }
    assert!(paths.len() > 50);
    for path in paths {
        let example_prefix = format!("  ctrs {}", path.join(" "));
        assert!(text.split("\nExamples:\n").nth(1).unwrap().lines().any(|line| line == example_prefix || line.starts_with(&(example_prefix.clone() + " "))), "{path:?}");
        for flag in ["-h", "--help"] {
            let result = Command::new(env!("CARGO_BIN_EXE_ctrs")).args(&path).arg(flag).env_clear().output().unwrap();
            assert!(result.status.success(), "{path:?} {flag}: {:?}", result);
            assert!(result.stderr.is_empty(), "{path:?} {flag}");
            let help = String::from_utf8(result.stdout).unwrap();
            assert!(help.contains("Examples:\n"), "{path:?} {flag}");
            assert!(help.contains("ctrs --help"), "{path:?} {flag}");
            assert!(!help.contains("Maintained by Joshua Li"));
        }
    }
}

#[test]
fn help_after_native_options_is_offline() {
    for args in [&["engine", "status", "--json", "-h"][..], &["diag", "logs", "--engine", "--help"][..], &["diag", "report", "--out", "report.txt", "-h"][..]] {
        let result = Command::new(env!("CARGO_BIN_EXE_ctrs")).args(args).env_clear().output().unwrap();
        assert!(result.status.success());
        assert!(result.stderr.is_empty());
        assert!(String::from_utf8(result.stdout).unwrap().contains("Examples:"));
    }
}

#[test]
fn status_json_keeps_its_output_and_exit_code_when_stopped() {
    let home = std::env::temp_dir().join(format!("ctrs-help-status-{}", std::process::id()));
    std::fs::create_dir_all(&home).unwrap();
    let result = Command::new(env!("CARGO_BIN_EXE_ctrs"))
        .args(["status", "--json"])
        .env_clear()
        .env("HOME", &home)
        .output()
        .unwrap();
    assert_eq!(result.status.code(), Some(1));
    assert_eq!(result.stdout, b"{\"running\":false}\n");
    assert!(result.stderr.is_empty());
    std::fs::remove_dir_all(home).unwrap();
}
