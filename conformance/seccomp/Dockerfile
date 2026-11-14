FROM alpine:3.20
RUN apk add --no-cache gcc musl-dev >/dev/null
COPY fixtures/seccomp-probe.c /seccomp-probe.c
RUN gcc -static -O2 -Wall -o /seccomp-probe /seccomp-probe.c
