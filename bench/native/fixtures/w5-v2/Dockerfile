ARG NODE_IMAGE
FROM ${NODE_IMAGE}
WORKDIR /opt/app
COPY source/package.json source/package-lock.json ./
COPY workload.json ./
RUN node -e 'const c=require("./workload.json"); const n=require("node:child_process").execFileSync("npm",["--version"],{encoding:"utf8"}).trim(); if(process.version!==c.tools.node||n!==c.tools.npm)process.exit(1)' && npm ci
COPY source/bin ./bin
COPY watch.mjs verify.mjs edit.mjs ./
CMD ["node", "watch.mjs"]
COPY source /opt/seed
