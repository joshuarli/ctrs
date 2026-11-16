export const input = '# Hello *world*\n\nA [link](https://example.com).\n';
export const original = '<h1>Hello <em>world</em></h1>\n<p>A <a href="https://example.com">link</a>.</p>\n';
export const edited = '<h1 class="w5">Hello <em>world</em></h1>\n<p>A <a href="https://example.com">link</a>.</p>\n';

export function verify(result) {
  if (result.status !== 0 || result.stderr !== '' || ![original, edited].includes(result.stdout)) {
    throw new Error(`CLI test failed: ${JSON.stringify(result)}`);
  }
  return result.stdout === original ? 'original' : 'edited';
}
