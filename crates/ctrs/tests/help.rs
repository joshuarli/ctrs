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
        assert!(help.ends_with("Procedure: https://github.com/joshuarli/usr/blob/main/dotfiles/base/.agents/instructions/owned-tools.md\n"));
        if let Some(reference) = &reference {
            assert_eq!(&help, reference);
        } else {
            reference = Some(help);
        }
    }
}
