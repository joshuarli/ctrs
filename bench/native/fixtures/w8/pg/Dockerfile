# W8 portfolio image: a self-contained copy of postgres:17-alpine's rootfs
# under scratch, so pulls never dedup against the cached base image.
FROM postgres:17-alpine AS src
FROM scratch
COPY --from=src / /
