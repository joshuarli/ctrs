# W6 compiled-app CI: real zlib 1.3.1 source (vendored tarball),
# configure -> parallel make -> make check -> static lib artifact.
# stamp.txt is written per trial so every build is a cold compile.
FROM gcc:14.2.0-bookworm@sha256:b99b86a28812b1e6453a231a947dc43d76fe192788a12f344a9b568bf9f5d24c
COPY zlib-1.3.1.tar.gz /tmp/
RUN mkdir -p /src && tar xzf /tmp/zlib-1.3.1.tar.gz -C /src --strip-components=1
COPY stamp.txt /tmp/stamp.txt
WORKDIR /src
RUN ./configure && make -j"$(nproc)" && make check
