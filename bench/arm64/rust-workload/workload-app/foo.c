unsigned int bench_foo(unsigned int seed) {
    unsigned int acc = seed ^ 0x5DEECE66Du;
    for (int k = 0; k < 8192; k++) {
        acc = acc * 1664525u + 1013904223u;
        acc ^= acc >> 13;
    }
    return acc;
}
