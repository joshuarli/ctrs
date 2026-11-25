FROM alpine:3.20
COPY --from=oci.17166969.xyz/owned-tools@sha256:aaec19e7a44cbc53b40db2d22093600ee888689b89be94da90e5398ed02f1883 /opt/laputa /opt/laputa
ENV PATH=$PATH:/opt/laputa/bin
RUN apk add --no-cache musl-dev >/dev/null
COPY fixtures/seccomp-probe.c /seccomp-probe.c
RUN clang -static -O2 -Wall -o /seccomp-probe /seccomp-probe.c
