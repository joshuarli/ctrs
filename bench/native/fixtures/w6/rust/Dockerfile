# W6 Rust half: pinned hyperfine 2.0.0 — cargo build --release --locked
# then cargo test --release --locked (real compile + test + package).
# stamp.txt is written per trial/pair so the timed build is never a
# silent cache hit; --no-cache is also passed explicitly.
FROM rust:1.100.0-bookworm@sha256:ade39a710ef85f3506cffcfec3e8a24ba090badef1dff2fb798f71d878833fea
COPY hyperfine-2.0.0.tar.gz /tmp/
RUN mkdir -p /src && tar xzf /tmp/hyperfine-2.0.0.tar.gz -C /src --strip-components=1
COPY stamp.txt /tmp/stamp.txt
WORKDIR /src
RUN cargo build --release --locked && cargo test --release --locked
