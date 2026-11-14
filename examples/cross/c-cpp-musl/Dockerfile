# Cross-compile a static aarch64 musl C/C++ binary. Copy this pattern:
# native BUILDPLATFORM toolchain, target via TARGETOS/TARGETARCH, static
# output, run on the target platform.
#
#   docker buildx build --platform linux/arm64 -t myapp examples/cross/c-cpp-musl
#
# The helper.c translation unit is compiled by the C driver, main.cpp by the
# C++ driver, linked static with musl. The final stage runs on the target.
ARG BUILDER_IMAGE=messense/rust-musl-cross:aarch64-musl@sha256:02e790506c5f15a533bc05b3af8719b16a8a2314480f6f0fdc0166432035d9b4
FROM --platform=$BUILDPLATFORM ${BUILDER_IMAGE} AS build
ARG TARGETOS
ARG TARGETARCH
ARG TARGETVARIANT
ARG BUILDPLATFORM
WORKDIR /src
COPY main.cpp helper.c ./
RUN triple="$(printf '%s' "$TARGETARCH" | sed -e 's/amd64/x86_64/' -e 's/arm64/aarch64/')"-unknown-linux-musl \
    && echo "build platform $BUILDPLATFORM; target $TARGETOS/$TARGETARCH${TARGETVARIANT:+/$TARGETVARIANT}; triple $triple" \
    && mkdir -p /out \
    && "$triple"-gcc -Os -c helper.c -o helper.o \
    && "$triple"-g++ -Os -static -o /out/cfixture main.cpp helper.o

FROM --platform=${TARGETOS}/${TARGETARCH} alpine@sha256:49340b346798875b5592e5d420241f2f9cfba5f47e62ebb1446a1b34734e898f
COPY --from=build /out/cfixture /cfixture
RUN /cfixture
CMD ["/cfixture"]
