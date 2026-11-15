#include "helpers.h"
static unsigned mix(unsigned x) {
    x ^= x << 13; x ^= x >> 17; x ^= x << 5;
    return x * 2654435761u;
}
unsigned workload_chunk_041(unsigned seed) {
    unsigned acc = seed ^ 0x56e27d59u;
    for (int k = 0; k < 4096; k++) {
        acc = mix(acc + (unsigned)(k * 41));
    }
    return acc;
}
