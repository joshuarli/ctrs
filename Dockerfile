FROM rust:1.100.0-alpine@sha256:de1e0058543a81ed7b046629167db587c67a94bdf37cce14eb27f0ec83baaffb

# config.toml selects rust-lld for aarch64-unknown-linux-musl, which cannot find this image's musl CRT objects; cc links against musl-dev instead.
ENV CARGO_TARGET_AARCH64_UNKNOWN_LINUX_MUSL_LINKER=cc

RUN apk add --no-cache musl-dev binutils git ca-certificates \
    && rustup component add clippy
