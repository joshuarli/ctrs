#include "helpers.h"
static unsigned mix(unsigned x) {
    x ^= x << 13; x ^= x >> 17; x ^= x << 5;
    return x * 2654435761u;
}
unsigned workload_chunk_028(unsigned seed) {
    unsigned acc = seed ^ 0x4e114f5cu;
    for (int k = 0; k < 4096; k++) {
        acc = mix(acc + (unsigned)(k * 28));
    }
    return acc;
}
