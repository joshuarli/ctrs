use logmacro::shout;

extern "C" {
    fn cross_foo() -> i32;
}

fn main() {
    assert_eq!(std::env::consts::ARCH, "aarch64", "this binary is the aarch64 target");
    assert_eq!(shout!(), "fixture target ok", "the proc macro ran on the host and expanded for the target");
    let v = unsafe { cross_foo() };
    assert_eq!(v, 42, "the C object built for the target linked and ran");
    println!("cross-fixture: {} ({} via build.rs C linkage)", shout!(), v);
}
