FROM node:22.15.0-bookworm-slim@sha256:557e52a0fcb928ee113df7e1fb5d4f60c1341dbda53f55e3d815ca10807efdce
ENV NODE_OPTIONS=--openssl-legacy-provider
COPY source.tar.gz /fixture/source.tar.gz
COPY npm-cache/ /fixture/npm-cache/
RUN echo '862d34f41327889f09a81860aa00b81ebe583a5fc7158212925d22a0209cb966  /fixture/source.tar.gz' | sha256sum -c - && mkdir /fixture/source && tar xzf /fixture/source.tar.gz --strip-components=1 -C /fixture/source && echo 'c69b3bf74df203f046f6db3f143f17f9ec0f019bf40273c2054e6340420d4876  /fixture/source/package-lock.json' | sha256sum -c -
