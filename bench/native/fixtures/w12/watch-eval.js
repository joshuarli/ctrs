const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const ts = require('/app/node_modules/typescript');
const spec = JSON.parse(process.argv[1]);
const config = ts.readConfigFile('/app/tsconfig.json', ts.sys.readFile);
const options = ts.parseJsonConfigFileContent(config.config, ts.sys, '/app').options;
const hash = x => crypto.createHash('sha256').update(x).digest('hex');
const result = [];
for (const item of spec) {
  const target = path.join('/app/production-server', item.path.replace(/^server\//, '').replace(/\.ts$/, '.js'));
  const expected = ts.transpileModule(item.content, {compilerOptions: options, fileName: path.basename(item.path)}).outputText;
  const actual = fs.existsSync(target) ? fs.readFileSync(target, 'utf8') : null;
  result.push({path: item.path, expected: hash(expected), actual: actual === null ? null : hash(actual)});
}
console.log(JSON.stringify(result));
