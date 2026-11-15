#include "helpers.h"
static unsigned mix(unsigned x) {
    x ^= x << 13; x ^= x >> 17; x ^= x << 5;
    return x * 2654435761u;
}
unsigned workload_chunk_047(unsigned seed) {
    unsigned acc = seed ^ 0x0c2f577fu;
    for (int k = 0; k < 4096; k++) {
        acc = mix(acc + (unsigned)(k * 47));
    }
    return acc;
}
