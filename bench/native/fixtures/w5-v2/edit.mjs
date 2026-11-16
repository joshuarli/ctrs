import fs from 'node:fs';
import path from 'node:path';

const before = 'return `<h${depth}>${this.parser.parseInline(tokens)}</h${depth}>\\n`;';
const after = 'return `<h${depth} class="w5">${this.parser.parseInline(tokens)}</h${depth}>\\n`;';
const [root, state] = process.argv.slice(2);
if (!root || !['edited', 'original'].includes(state) || process.argv.length !== 4) {
  throw new Error('usage: node edit.mjs SOURCE_DIR edited|original');
}
const file = path.join(root, 'src/Renderer.ts');
const text = fs.readFileSync(file, 'utf8');
const [oldText, newText] = state === 'edited' ? [before, after] : [after, before];
if (text.split(oldText).length !== 2 || text.includes(newText)) {
  throw new Error('unexpected renderer source; refusing edit');
}
fs.writeFileSync(file, text.replace(oldText, newText));
