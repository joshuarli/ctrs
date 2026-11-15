pub static TABLE: [u64; 96] = [
    0x000000009e3779b1,
    0x000000013c6ef362,
    0x00000001daa66d13,
    0x0000000278dde6c4,
    0x0000000317156075,
    0x00000003b54cda26,
    0x00000004538453d7,
    0x00000004f1bbcd88,
    0x000000058ff34739,
    0x000000062e2ac0ea,
    0x00000006cc623a9b,
    0x000000076a99b44c,
    0x0000000808d12dfd,
    0x00000008a708a7ae,
    0x000000094540215f,
    0x00000009e3779b10,
    0x0000000a81af14c1,
    0x0000000b1fe68e72,
    0x0000000bbe1e0823,
    0x0000000c5c5581d4,
    0x0000000cfa8cfb85,
    0x0000000d98c47536,
    0x0000000e36fbeee7,
    0x0000000ed5336898,
    0x0000000f736ae249,
    0x0000001011a25bfa,
    0x00000010afd9d5ab,
    0x000000114e114f5c,
    0x00000011ec48c90d,
    0x000000128a8042be,
    0x0000001328b7bc6f,
    0x00000013c6ef3620,
    0x000000146526afd1,
    0x00000015035e2982,
    0x00000015a195a333,
    0x000000163fcd1ce4,
    0x00000016de049695,
    0x000000177c3c1046,
    0x000000181a7389f7,
    0x00000018b8ab03a8,
    0x0000001956e27d59,
    0x00000019f519f70a,
    0x0000001a935170bb,
    0x0000001b3188ea6c,
    0x0000001bcfc0641d,
    0x0000001c6df7ddce,
    0x0000001d0c2f577f,
    0x0000001daa66d130,
    0x0000001e489e4ae1,
    0x0000001ee6d5c492,
    0x0000001f850d3e43,
    0x000000202344b7f4,
    0x00000020c17c31a5,
    0x000000215fb3ab56,
    0x00000021fdeb2507,
    0x000000229c229eb8,
    0x000000233a5a1869,
    0x00000023d891921a,
    0x0000002476c90bcb,
    0x000000251500857c,
    0x00000025b337ff2d,
    0x00000026516f78de,
    0x00000026efa6f28f,
    0x000000278dde6c40,
    0x000000282c15e5f1,
    0x00000028ca4d5fa2,
    0x000000296884d953,
    0x0000002a06bc5304,
    0x0000002aa4f3ccb5,
    0x0000002b432b4666,
    0x0000002be162c017,
    0x0000002c7f9a39c8,
    0x0000002d1dd1b379,
    0x0000002dbc092d2a,
    0x0000002e5a40a6db,
    0x0000002ef878208c,
    0x0000002f96af9a3d,
    0x0000003034e713ee,
    0x00000030d31e8d9f,
    0x0000003171560750,
    0x000000320f8d8101,
    0x00000032adc4fab2,
    0x000000334bfc7463,
    0x00000033ea33ee14,
    0x00000034886b67c5,
    0x0000003526a2e176,
    0x00000035c4da5b27,
    0x000000366311d4d8,
    0x0000003701494e89,
    0x000000379f80c83a,
    0x000000383db841eb,
    0x00000038dbefbb9c,
    0x000000397a27354d,
    0x0000003a185eaefe,
    0x0000003ab69628af,
    0x0000003b54cda260,
];

#[inline(never)]
pub fn round_1(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_2(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_3(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_4(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_5(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_6(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_7(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_8(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_9(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_10(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_11(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_12(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_13(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_14(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_15(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_16(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_17(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_18(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_19(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_20(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_21(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_22(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_23(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_24(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_25(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_26(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_27(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_28(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_29(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_30(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_31(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_32(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_33(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_34(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_35(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_36(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_37(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_38(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_39(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_40(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_41(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_42(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_43(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_44(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_45(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_46(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_47(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_48(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_49(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_50(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_51(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_52(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_53(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_54(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_55(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_56(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_57(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_58(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_59(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_60(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_61(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_62(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_63(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_64(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_65(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_66(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_67(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_68(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_69(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_70(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_71(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_72(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_73(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_74(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_75(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_76(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_77(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_78(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_79(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_80(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_81(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_82(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_83(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_84(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_85(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_86(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_87(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_88(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_89(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_90(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_91(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_92(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_93(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_94(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_95(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

#[inline(never)]
pub fn round_96(mut x: u64, k: u64) -> u64 {
    x ^= x.rotate_left(13).wrapping_add(k ^ 0x9E3779B97F4A7C15u64);
    x = x.wrapping_mul(0xD6E8FEB86659FD93u64) ^ x.rotate_right(17);
    x.wrapping_add(x.rotate_left(29) ^ (x >> 11)).wrapping_add(k)
}

pub fn round_names() -> [fn(u64, u64) -> u64; 96] {
    [
        round_1,
        round_2,
        round_3,
        round_4,
        round_5,
        round_6,
        round_7,
        round_8,
        round_9,
        round_10,
        round_11,
        round_12,
        round_13,
        round_14,
        round_15,
        round_16,
        round_17,
        round_18,
        round_19,
        round_20,
        round_21,
        round_22,
        round_23,
        round_24,
        round_25,
        round_26,
        round_27,
        round_28,
        round_29,
        round_30,
        round_31,
        round_32,
        round_33,
        round_34,
        round_35,
        round_36,
        round_37,
        round_38,
        round_39,
        round_40,
        round_41,
        round_42,
        round_43,
        round_44,
        round_45,
        round_46,
        round_47,
        round_48,
        round_49,
        round_50,
        round_51,
        round_52,
        round_53,
        round_54,
        round_55,
        round_56,
        round_57,
        round_58,
        round_59,
        round_60,
        round_61,
        round_62,
        round_63,
        round_64,
        round_65,
        round_66,
        round_67,
        round_68,
        round_69,
        round_70,
        round_71,
        round_72,
        round_73,
        round_74,
        round_75,
        round_76,
        round_77,
        round_78,
        round_79,
        round_80,
        round_81,
        round_82,
        round_83,
        round_84,
        round_85,
        round_86,
        round_87,
        round_88,
        round_89,
        round_90,
        round_91,
        round_92,
        round_93,
        round_94,
        round_95,
        round_96,
    ]
}
