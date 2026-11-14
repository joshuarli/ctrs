# Cross-build an aarch64 musl Rust binary. Copy this pattern for your own
# crate: native BUILDPLATFORM toolchain, target via TARGETOS/TARGETARCH,
# static output, run on the target platform.
#
#   docker buildx build --platform linux/arm64 -t myapp examples/cross/rust-musl
#
# The build stage runs on the build platform (native tools, build scripts
# and proc macros included); the final stage runs on the target platform.
# Default: the pinned cross toolchain (rustc 1.96.1, gcc 12.4.0). On x86_64
# it runs natively; on Apple Silicon it is the arm64 variant, native too.
ARG BUILDER_IMAGE=messense/rust-musl-cross:aarch64-musl@sha256:02e790506c5f15a533bc05b3af8719b16a8a2314480f6f0fdc0166432035d9b4
FROM --platform=$BUILDPLATFORM ${BUILDER_IMAGE} AS build
ARG TARGETOS
ARG TARGETARCH
ARG TARGETVARIANT
ARG BUILDPLATFORM
# For --platform linux/amd64 use the stock image instead:
#   rust:1-alpine@sha256:2cccd8b212b37dad15a555589c1b6787da4ab913fe24d8a9b2d99d3498869409 (rustc 1.100.0)
WORKDIR /src
COPY Cargo.toml ./
COPY app ./app
COPY logmacro ./logmacro
RUN triple="$(printf '%s' "$TARGETARCH" | sed -e 's/amd64/x86_64/' -e 's/arm64/aarch64/')"-unknown-linux-musl \
    && echo "build platform $BUILDPLATFORM; target $TARGETOS/$TARGETARCH${TARGETVARIANT:+/$TARGETVARIANT}; triple $triple" \
    && CARGO_ENCODED_RUSTFLAGS='' cargo build --release --target "$triple" -p fixture-app \
    && mkdir -p /out && cp "target/$triple/release/fixture-app" /out/fixture-app

FROM --platform=${TARGETOS}/${TARGETARCH} alpine@sha256:49340b346798875b5592e5d420241f2f9cfba5f47e62ebb1446a1b34734e898f
COPY --from=build /out/fixture-app /fixture-app
RUN /fixture-app
CMD ["/fixture-app"]
