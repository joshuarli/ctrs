import { createHash } from 'node:crypto';
import { lstatSync, readFileSync, readdirSync } from 'node:fs';
import { join, relative } from 'node:path';

function hashFiles(root, paths) {
  const files = Object.create(null);
  function visit(path) {
    const stat = lstatSync(path);
    if (stat.isDirectory()) {
      for (const name of readdirSync(path)) visit(join(path, name));
      return;
    }
    if (!stat.isFile()) throw new Error(`W5 nonregular input: ${path}`);
    files[relative(root, path)] = createHash('sha256').update(readFileSync(path)).digest('hex');
  }
  for (const path of paths) visit(join(root, path));
  return files;
}

console.log(JSON.stringify({
  mounted_files: hashFiles(process.argv[1], ['']),
  app_files: hashFiles(process.argv[2], ['bin', 'package.json', 'package-lock.json']),
}));
