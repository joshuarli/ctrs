const fs = require('fs');
const path = require('path');
const edits = JSON.parse(process.argv[1]);
const starts = [];
const begin = process.hrtime.bigint();
for (const edit of edits) {
  starts.push(Number(process.hrtime.bigint() - begin) / 1e6);
  const target = path.join('/app', edit.path);
  if (edit.kind === 'rename') {
    fs.renameSync(path.join('/app', edit.from), target);
    fs.writeFileSync(target, edit.content);
  } else if (edit.kind === 'delete') {
    fs.unlinkSync(target);
  } else if (edit.kind === 'atomic') {
    const temporary = target + '.w12-tmp';
    fs.writeFileSync(temporary, edit.content);
    fs.renameSync(temporary, target);
  } else {
    fs.mkdirSync(path.dirname(target), {recursive: true});
    fs.writeFileSync(target, edit.content);
  }
}
console.log(JSON.stringify(starts));
