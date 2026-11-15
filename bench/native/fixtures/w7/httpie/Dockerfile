# W7 app 2: httpie 3.2.4 — real PyPI sdist -> wheel -> slim runtime.
# The sdist sha256 is the PyPI-published digest. stamp/note.txt sits
# after the wheel build so a one-file change re-runs only tail layers.
FROM python:3.13-slim AS build
COPY httpie-3.2.4.tar.gz /tmp/
RUN pip wheel --no-cache-dir -w /wheels /tmp/httpie-3.2.4.tar.gz
COPY stamp/ /stamp/
RUN mkdir -p /out && cat /stamp/note.txt > /out/note.txt
FROM python:3.13-slim
COPY --from=build /wheels/ /tmp/wheels/
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels httpie==3.2.4 \
    && rm -rf /tmp/wheels
COPY --from=build /out/note.txt /out/note.txt
