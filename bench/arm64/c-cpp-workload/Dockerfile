# The C/C++ workload fixture for S6 (equivalent work, A/B/C comparison).
# Source inputs are frozen (SHA256SUMS); the same compiler is used on every
# path: the pinned messense toolchain, emulated for the target platform
# (A: old BuildKit pin, B: qualified pin) or natively on the build platform
# (C: cross-compilation). Only BUILD_PLATFORM differs.
#
# Each translation unit compiles in its own layer so the incremental state
# (touching exactly one source file — the final TU, t-120.c) rebuilds exactly
# one layer plus the link; earlier TUs cache-hit. Layer hits are the no-op
# case. Do not edit by hand; the per-TU blocks were generated once and
# frozen with the rest of the fixture.
#
# Target-platform (emulated) build:
#   docker build --no-cache --platform linux/arm64 --build-arg BUILD_PLATFORM=linux/arm64 -t bench/c-cpp-workload .
# Cross build:
#   docker build --no-cache --platform linux/arm64 --build-arg BUILD_PLATFORM=linux/amd64 -t bench/c-cpp-workload .
ARG BUILD_PLATFORM=linux/arm64
ARG BUILDER_IMAGE=messense/rust-musl-cross:aarch64-musl@sha256:02e790506c5f15a533bc05b3af8719b16a8a2314480f6f0fdc0166432035d9b4
FROM --platform=${BUILD_PLATFORM} ${BUILDER_IMAGE} AS build
ARG BUILD_PLATFORM
ARG TARGETOS
ARG TARGETARCH
WORKDIR /src
COPY helpers.h .
COPY t-001.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-001.c -o t-001.o
COPY t-002.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-002.c -o t-002.o
COPY t-003.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-003.c -o t-003.o
COPY t-004.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-004.c -o t-004.o
COPY t-005.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-005.c -o t-005.o
COPY t-006.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-006.c -o t-006.o
COPY t-007.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-007.c -o t-007.o
COPY t-008.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-008.c -o t-008.o
COPY t-009.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-009.c -o t-009.o
COPY t-010.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-010.c -o t-010.o
COPY t-011.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-011.c -o t-011.o
COPY t-012.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-012.c -o t-012.o
COPY t-013.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-013.c -o t-013.o
COPY t-014.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-014.c -o t-014.o
COPY t-015.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-015.c -o t-015.o
COPY t-016.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-016.c -o t-016.o
COPY t-017.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-017.c -o t-017.o
COPY t-018.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-018.c -o t-018.o
COPY t-019.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-019.c -o t-019.o
COPY t-020.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-020.c -o t-020.o
COPY t-021.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-021.c -o t-021.o
COPY t-022.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-022.c -o t-022.o
COPY t-023.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-023.c -o t-023.o
COPY t-024.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-024.c -o t-024.o
COPY t-025.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-025.c -o t-025.o
COPY t-026.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-026.c -o t-026.o
COPY t-027.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-027.c -o t-027.o
COPY t-028.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-028.c -o t-028.o
COPY t-029.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-029.c -o t-029.o
COPY t-030.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-030.c -o t-030.o
COPY t-031.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-031.c -o t-031.o
COPY t-032.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-032.c -o t-032.o
COPY t-033.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-033.c -o t-033.o
COPY t-034.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-034.c -o t-034.o
COPY t-035.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-035.c -o t-035.o
COPY t-036.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-036.c -o t-036.o
COPY t-037.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-037.c -o t-037.o
COPY t-038.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-038.c -o t-038.o
COPY t-039.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-039.c -o t-039.o
COPY t-040.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-040.c -o t-040.o
COPY t-041.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-041.c -o t-041.o
COPY t-042.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-042.c -o t-042.o
COPY t-043.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-043.c -o t-043.o
COPY t-044.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-044.c -o t-044.o
COPY t-045.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-045.c -o t-045.o
COPY t-046.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-046.c -o t-046.o
COPY t-047.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-047.c -o t-047.o
COPY t-048.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-048.c -o t-048.o
COPY t-049.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-049.c -o t-049.o
COPY t-050.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-050.c -o t-050.o
COPY t-051.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-051.c -o t-051.o
COPY t-052.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-052.c -o t-052.o
COPY t-053.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-053.c -o t-053.o
COPY t-054.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-054.c -o t-054.o
COPY t-055.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-055.c -o t-055.o
COPY t-056.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-056.c -o t-056.o
COPY t-057.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-057.c -o t-057.o
COPY t-058.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-058.c -o t-058.o
COPY t-059.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-059.c -o t-059.o
COPY t-060.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-060.c -o t-060.o
COPY t-061.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-061.c -o t-061.o
COPY t-062.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-062.c -o t-062.o
COPY t-063.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-063.c -o t-063.o
COPY t-064.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-064.c -o t-064.o
COPY t-065.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-065.c -o t-065.o
COPY t-066.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-066.c -o t-066.o
COPY t-067.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-067.c -o t-067.o
COPY t-068.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-068.c -o t-068.o
COPY t-069.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-069.c -o t-069.o
COPY t-070.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-070.c -o t-070.o
COPY t-071.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-071.c -o t-071.o
COPY t-072.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-072.c -o t-072.o
COPY t-073.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-073.c -o t-073.o
COPY t-074.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-074.c -o t-074.o
COPY t-075.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-075.c -o t-075.o
COPY t-076.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-076.c -o t-076.o
COPY t-077.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-077.c -o t-077.o
COPY t-078.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-078.c -o t-078.o
COPY t-079.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-079.c -o t-079.o
COPY t-080.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-080.c -o t-080.o
COPY t-081.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-081.c -o t-081.o
COPY t-082.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-082.c -o t-082.o
COPY t-083.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-083.c -o t-083.o
COPY t-084.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-084.c -o t-084.o
COPY t-085.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-085.c -o t-085.o
COPY t-086.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-086.c -o t-086.o
COPY t-087.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-087.c -o t-087.o
COPY t-088.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-088.c -o t-088.o
COPY t-089.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-089.c -o t-089.o
COPY t-090.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-090.c -o t-090.o
COPY t-091.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-091.c -o t-091.o
COPY t-092.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-092.c -o t-092.o
COPY t-093.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-093.c -o t-093.o
COPY t-094.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-094.c -o t-094.o
COPY t-095.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-095.c -o t-095.o
COPY t-096.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-096.c -o t-096.o
COPY t-097.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-097.c -o t-097.o
COPY t-098.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-098.c -o t-098.o
COPY t-099.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-099.c -o t-099.o
COPY t-100.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-100.c -o t-100.o
COPY t-101.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-101.c -o t-101.o
COPY t-102.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-102.c -o t-102.o
COPY t-103.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-103.c -o t-103.o
COPY t-104.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-104.c -o t-104.o
COPY t-105.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-105.c -o t-105.o
COPY t-106.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-106.c -o t-106.o
COPY t-107.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-107.c -o t-107.o
COPY t-108.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-108.c -o t-108.o
COPY t-109.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-109.c -o t-109.o
COPY t-110.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-110.c -o t-110.o
COPY t-111.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-111.c -o t-111.o
COPY t-112.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-112.c -o t-112.o
COPY t-113.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-113.c -o t-113.o
COPY t-114.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-114.c -o t-114.o
COPY t-115.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-115.c -o t-115.o
COPY t-116.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-116.c -o t-116.o
COPY t-117.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-117.c -o t-117.o
COPY t-118.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-118.c -o t-118.o
COPY t-119.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-119.c -o t-119.o
COPY t-120.c .
RUN aarch64-unknown-linux-musl-gcc -Os -c t-120.c -o t-120.o
COPY main.cpp ./
RUN echo "build platform ${BUILD_PLATFORM}; target aarch64-unknown-linux-musl" \
    && echo "compiler $(aarch64-unknown-linux-musl-gcc --version | head -1)" \
    && mkdir -p /out \
    && aarch64-unknown-linux-musl-g++ -Os -static -o /out/c-workload main.cpp t-*.o \
    && /out/c-workload
FROM --platform=${TARGETOS}/${TARGETARCH} alpine@sha256:49340b346798875b5592e5d420241f2f9cfba5f47e62ebb1446a1b34734e898f
COPY --from=build /out/c-workload /c-workload
RUN /c-workload
CMD ["/c-workload"]
