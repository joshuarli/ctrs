import * as esbuild from 'esbuild';
import { spawnSync } from 'node:child_process';
import { input, verify } from './verify.mjs';

const context = await esbuild.context({
  entryPoints: ['/src/src/marked.ts'],
  bundle: true,
  format: 'esm',
  outfile: '/opt/app/lib/marked.esm.js',
  plugins: [{
    name: 'cli-test',
    setup(build) {
      build.onEnd(result => {
        try {
          if (result.errors.length) throw new Error('build failed');
          const run = spawnSync(process.execPath, ['/opt/app/bin/marked.js'], {
            input, encoding: 'utf8', timeout: 30000,
          });
          const state = verify({ status: run.status, stdout: run.stdout, stderr: run.stderr });
          console.log(JSON.stringify({ event: 'tested', state, output: run.stdout }));
        } catch (error) {
          console.error(error);
          process.exit(1);
        }
      });
    },
  }],
});
await context.watch();
