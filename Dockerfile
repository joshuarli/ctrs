FROM rust:1.100.0-alpine

# config.toml's rust-lld cannot find musl crt objects in this image; cc links instead (as `cargo xtask linux` passes itself).
ENV CARGO_TARGET_AARCH64_UNKNOWN_LINUX_MUSL_LINKER=cc

RUN apk add --no-cache musl-dev binutils git ca-certificates \
    && rustup component add clippy
