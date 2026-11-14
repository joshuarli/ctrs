#include <cstdio>

extern "C" int cfixture_answer(void);

int main() {
    std::printf("cross-fixture: C++ musl static ok (%d)\n", cfixture_answer());
    return 0;
}
