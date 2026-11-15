# The Rust workload fixture for S6 (equivalent work, A/B/C comparison).
# Frozen source inputs (Cargo.lock, SHA256SUMS); the same toolchain on every
# path: the pinned messense stable, emulated for the target platform
# (A: old BuildKit pin, B: qualified pin) or natively on the build platform
# (C: cross-compilation). ring supplies the CPU-heavy C codegen; the proc
# macro and the build script keep host tooling in the loop.
#
# Dependencies compile against a dummy main first, so the real sources'
# layer carries only the workload-app rebuild; the incremental state
# touches exactly one file and rebuilds exactly that layer.
#
# Target-platform (emulated) build:
#   docker build --no-cache --platform linux/arm64 --build-arg BUILD_PLATFORM=linux/arm64 -t bench/rust-workload .
# Cross build:
#   docker build --no-cache --platform linux/arm64 --build-arg BUILD_PLATFORM=linux/amd64 -t bench/rust-workload .
ARG BUILD_PLATFORM=linux/arm64
ARG BUILDER_IMAGE=messense/rust-musl-cross:aarch64-musl@sha256:02e790506c5f15a533bc05b3af8719b16a8a2314480f6f0fdc0166432035d9b4
FROM --platform=${BUILD_PLATFORM} ${BUILDER_IMAGE} AS build
ARG BUILD_PLATFORM
ARG TARGETOS
ARG TARGETARCH
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY workload-macro ./workload-macro
COPY workload-app/Cargo.toml ./workload-app/Cargo.toml
RUN mkdir -p workload-app/src && printf 'fn main() {}\n' > workload-app/src/main.rs \
    && RUSTUP_TOOLCHAIN=stable CARGO_ENCODED_RUSTFLAGS='' \
       cargo build --release --target aarch64-unknown-linux-musl -p workload-app
COPY workload-app ./workload-app
RUN echo "build platform ${BUILD_PLATFORM}; target aarch64-unknown-linux-musl" \
    && echo "rustc $(rustc --version)" \
    && mkdir -p /out \
    && RUSTUP_TOOLCHAIN=stable CARGO_ENCODED_RUSTFLAGS='' \
       cargo build --release --target aarch64-unknown-linux-musl -p workload-app \
    && cp target/aarch64-unknown-linux-musl/release/workload-app /out/rust-workload \
    && /out/rust-workload
FROM --platform=${TARGETOS}/${TARGETARCH} alpine@sha256:49340b346798875b5592e5d420241f2f9cfba5f47e62ebb1446a1b34734e898f
COPY --from=build /out/rust-workload /rust-workload
RUN /rust-workload
CMD ["/rust-workload"]
