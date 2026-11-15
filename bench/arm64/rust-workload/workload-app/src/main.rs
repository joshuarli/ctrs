mod rounds;

extern "C" {
    fn bench_foo(seed: u32) -> u32;
}

fn main() {
    let mut acc: u64 = 0xC0FFEE1234567890;
    for (i, k) in rounds::TABLE.iter().enumerate() {
        acc = rounds::round_names()[i](acc, *k);
    }
    let input = vec![0xA5u8; 1 << 20];
    let ring_digest = ring::digest::digest(&ring::digest::SHA256, &input);
    let mut ring_byte: u64 = 0;
    for b in ring_digest.as_ref() {
        ring_byte = ring_byte.wrapping_mul(131).wrapping_add(u64::from(*b));
    }
    let c = unsafe { bench_foo(42) };
    let via_macro: u32 = workload_macro::answer!();
    println!("bench-rust-workload: {} {} {} {}", acc as u32 ^ 0xFFFFFFFF, ring_byte, c, via_macro);
}
