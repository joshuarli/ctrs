import fs from 'node:fs';
const contract = JSON.parse(fs.readFileSync(new URL('./workload.json', import.meta.url), 'utf8'));
export const { input, original, edited } = contract.test;

export function verify(result) {
  if (result.status !== 0 || result.stderr !== '' || ![original, edited].includes(result.stdout)) {
    throw new Error(`CLI test failed: ${JSON.stringify(result)}`);
  }
  return result.stdout === original ? 'original' : 'edited';
}
