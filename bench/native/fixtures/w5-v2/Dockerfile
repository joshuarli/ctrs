FROM node:22.15.0-bookworm-slim@sha256:557e52a0fcb928ee113df7e1fb5d4f60c1341dbda53f55e3d815ca10807efdce
WORKDIR /opt/app
COPY source/package.json source/package-lock.json ./
RUN test "$(node --version)" = v22.15.0 && test "$(npm --version)" = 10.9.2 && npm ci
COPY source/bin ./bin
COPY watch.mjs verify.mjs edit.mjs ./
CMD ["node", "watch.mjs"]
COPY source /opt/seed
