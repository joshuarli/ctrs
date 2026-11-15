use std::env;
use std::process::Command;

// Real C linkage, cross-target aware: the target selects the C compiler.
// The host dependencies keep the host cc; the target object goes through
// the cross compiler on aarch64, never through the host one.
fn main() {
    let target = env::var("TARGET").expect("TARGET");
    let cc = match target.as_str() {
        "aarch64-unknown-linux-musl" => "aarch64-unknown-linux-musl-gcc",
        "x86_64-unknown-linux-gnu" | "x86_64-unknown-linux-musl" => "cc",
        other => panic!("workload-fixture: no C compiler mapping for {other}"),
    };
    let out = env::var("OUT_DIR").expect("OUT_DIR");
    let obj = format!("{out}/foo.o");
    let status = Command::new(cc)
        .args(["-Os", "-c", "foo.c", "-o", &obj])
        .status()
        .expect("spawn C compiler");
    assert!(status.success(), "C compiler failed for {target}");
    println!("cargo:rustc-link-arg={obj}");
    println!("cargo:rerun-if-changed=foo.c");
}
