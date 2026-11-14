fn main() {
    let target = std::env::var("TARGET").expect("TARGET");
    let host = std::env::var("HOST").expect("HOST");
    println!("cargo:warning=fixture build: host={host} target={target}");
    let cc = std::env::var(format!("TARGET_CC_{}", target.replace('-', "_")))
        .or_else(|_| std::env::var("TARGET_CC"))
        .unwrap_or_else(|_| "cc".into());
    println!("cargo:warning=foo.c compiles with {cc} (host tools compile, the target links)");
    // Host and target are different architectures here: the C object must be
    // compiled for the target, or the link fails. The cc fallback ("cc")
    // would be wrong for a cross build; the message above says what ran.
    cc::Build::new().file("foo.c").compile("crossfoo");
}
