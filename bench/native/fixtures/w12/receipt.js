const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const hash = data => crypto.createHash('sha256').update(data).digest('hex');
function tree(root) {
  const files = [];
  function walk(dir) {
    for (const entry of fs.readdirSync(dir, {withFileTypes: true}).sort((a, b) => a.name.localeCompare(b.name))) {
      const p = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(p);
      else if (entry.isFile()) {
        const data = fs.readFileSync(p);
        files.push({path: path.relative(root, p), bytes: data.length, sha256: hash(data)});
      } else throw new Error('unexpected output entry ' + p);
    }
  }
  walk(root);
  files.sort((a, b) => a.path < b.path ? -1 : a.path > b.path ? 1 : 0);
  return {sha256: hash(JSON.stringify(files)), files: files.length, bytes: files.reduce((n, f) => n + f.bytes, 0)};
}
const id = fs.readFileSync('/app/client/.next/BUILD_ID', 'utf8').trim();
const original = fs.readFileSync('/app/client/.next/build-manifest.json', 'utf8');
const runtime = {};
for (const name of ['main', 'polyfills']) {
  const paths = [...original.matchAll(new RegExp(`static/runtime/${name}-[0-9a-f]+\\.js`, 'g'))].map(x => x[0]);
  if (!paths.length || new Set(paths).size !== 1) throw new Error('unexpected runtime manifest entries ' + name);
  const content = fs.readFileSync(path.join('/app/client/.next', paths[0]), 'utf8');
  const normalized = content.replace(/(\.push\(\[\[)\d+(\])/, '$1<BUILD_CHUNK_ID>$2');
  if (content === normalized) throw new Error('runtime chunk ID missing ' + name);
  runtime[name] = hash(normalized);
}
const manifestText = original.split(id).join('<BUILD_ID>')
  .replace(/(static\/chunks\/)[0-9a-f]{40}(?=\.)/g, '$1<BUILD_CHUNK>')
  .replace(/(static\/runtime\/(?:main|polyfills)-)[0-9a-f]+(?=\.js)/g, '$1<BUILD_CHUNK_HASH>');
const manifest = JSON.parse(manifestText);
console.log(JSON.stringify({server: tree('/app/production-server'), client_manifest_sha256: hash(JSON.stringify(manifest)), runtime}));
