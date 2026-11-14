FROM rust:1-alpine

RUN apk add --no-cache musl-dev binutils git ca-certificates
