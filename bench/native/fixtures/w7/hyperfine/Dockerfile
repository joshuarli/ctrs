# W7 app 1: pinned hyperfine 2.0.0 — real multi-stage build.
# Stage 1 compiles with cargo; stage 2 ships only the binary plus the
# per-trial note probe. stamp/note.txt sits after the compile so a
# one-file change re-runs only the tail layers (incremental cell).
FROM rust:1.100.0-bookworm AS build
COPY hyperfine-2.0.0.tar.gz /tmp/
RUN mkdir -p /src && tar xzf /tmp/hyperfine-2.0.0.tar.gz -C /src --strip-components=1
WORKDIR /src
RUN cargo build --release --locked
COPY stamp/ /stamp/
RUN mkdir -p /out && cat /stamp/note.txt > /out/note.txt
FROM debian:bookworm-slim
COPY --from=build /src/target/release/hyperfine /usr/local/bin/hyperfine
COPY --from=build /out/note.txt /out/note.txt
