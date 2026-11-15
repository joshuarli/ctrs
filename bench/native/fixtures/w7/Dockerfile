# W7 native image build: multi-stage, offline (base image is a prepared
# service image). Stage 1 compiles the fixture sources and compresses a
# fixed-size payload; stage 2 ships only the outputs. `stamp/note.txt`
# is the incremental-change probe: bumping it re-runs only the last
# layer of stage 1.
FROM python:3.13-slim AS build
COPY src/ /src/
RUN python3 -m compileall -q /src && \
    head -c 67108864 /dev/urandom | gzip -1 > /work_blob.gz
COPY stamp/ /stamp/
RUN mkdir -p /out && cat /stamp/note.txt > /out/note.txt && \
    cp /work_blob.gz /out/blob.gz
FROM python:3.13-slim
COPY --from=build /out/ /out/
CMD ["python3", "-c", "print('npw7-ok')"]
