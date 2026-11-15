# W7 app 1: pinned hyperfine 2.0.0 — real multi-stage build.
# Stage 1 compiles with cargo; stage 2 ships only the binary plus the
# per-trial note probe. stamp/note.txt sits after the compile so a
# one-file change re-runs only the tail layers (incremental cell).
FROM rust:1.100.0-bookworm@sha256:ade39a710ef85f3506cffcfec3e8a24ba090badef1dff2fb798f71d878833fea AS build
COPY hyperfine-2.0.0.tar.gz /tmp/
RUN mkdir -p /src && tar xzf /tmp/hyperfine-2.0.0.tar.gz -C /src --strip-components=1
WORKDIR /src
RUN cargo build --release --locked
COPY stamp/ /stamp/
RUN mkdir -p /out && cat /stamp/note.txt > /out/note.txt
FROM debian:bookworm-slim@sha256:734a72b3d6142a71993b4bc580ca01d8ca687f77a2c422d96a961d3376b179bc
COPY --from=build /src/target/release/hyperfine /usr/local/bin/hyperfine
COPY --from=build /out/note.txt /out/note.txt
