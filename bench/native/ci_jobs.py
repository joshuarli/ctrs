"""Fixed Marked build and CLI jobs for the native CI workload."""
import concurrent.futures
import json
from pathlib import Path
import re
import time
import uuid

import linux_lane

FIXTURE = Path(__file__).parent / 'fixtures/w9-v2/jobs.json'
SPEC = json.loads(FIXTURE.read_text())
TIMEOUT = 120
SCRIPT = r'''
const fs = require('node:fs');
const crypto = require('node:crypto');
const child = require('node:child_process');
const esbuild = require('esbuild');
const cases = JSON.parse(process.argv[1]);
const hash = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
(async () => {
  const tools = {node: process.version, npm: child.execFileSync('npm', ['--version'], {encoding: 'utf8', timeout: 10000}).trim(), esbuild: require('esbuild/package.json').version};
  const source_lock = hash('/opt/seed/package-lock.json');
  fs.mkdirSync('/opt/app/lib', {recursive: true});
  await esbuild.build({entryPoints: ['/opt/seed/src/marked.ts'], outfile: '/opt/app/lib/marked.esm.js', bundle: true, format: 'esm'});
  const artifact = hash('/opt/app/lib/marked.esm.js');
  const tests = cases.map(input => {
    const result = child.spawnSync('node', ['/opt/app/bin/marked.js'], {input, encoding: 'utf8', timeout: 30000});
    if (result.error) throw result.error;
    return {status: result.status, stdout: result.stdout, stderr: result.stderr};
  });
  process.stdout.write(JSON.stringify({tools, source_lock, artifact, tests}));
})().catch(error => { console.error(error.stack || error); process.exitCode = 1; });
'''
_PORTFOLIO = json.loads((Path(__file__).parent / 'fixtures/w8-v6/portfolio.json').read_text())
_MARKED = json.loads((Path(__file__).parent / 'fixtures/w5-v2/workload.json').read_text())
TOOLS = {key: _PORTFOLIO['runtime_versions'][key] for key in ('node', 'npm', 'esbuild')}
SOURCE_LOCK = _MARKED['source']['lock_sha256']
ARTIFACT = _PORTFOLIO['marked_artifact_sha256']
IMAGE_DIGEST = _PORTFOLIO['images']['np-v6/marked']['manifest']


class ConditionFailed(RuntimeError):
    def __init__(self, results):
        self.results = results
        super().__init__('W9 jobs failed: ' + ', '.join(str(r['job']) for r in results if r['error']))


def validate_result(body, cases):
    expected = {'tools': TOOLS, 'source_lock': SOURCE_LOCK, 'artifact': ARTIFACT,
                'tests': [case['result'] for case in cases]}
    if json.dumps(body, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError(f'unexpected W9 job result: {body!r}')


def cleanup(engine, name, owner, *, command=None):
    command = engine.sh if command is None else command
    inspected = command(['inspect', name], timeout=30, check=False)
    if inspected.returncode:
        if 'no such object' in inspected.stderr.lower() or 'no such container' in inspected.stderr.lower():
            return
        raise RuntimeError(f'container inspection failed: {inspected.stderr}')
    info = json.loads(inspected.stdout)
    if len(info) != 1 or info[0]['Config']['Labels'].get('dev.ctrs.campaign.run') != owner:
        raise RuntimeError('container cleanup ownership mismatch')
    command(['rm', '-f', name], timeout=30)


def validate_image_ref(image_digest_ref):
    if linux_lane.enabled():
        if image_digest_ref not in linux_lane.workload_lock()['images']['marked']['ids'].values():
            raise ValueError('W9 requires the frozen native Linux Marked image')
        return
    if (not re.fullmatch(r'[a-z0-9][a-z0-9._:/-]*@sha256:[0-9a-f]{64}', image_digest_ref)
            or image_digest_ref.rsplit('@', 1)[-1] != IMAGE_DIGEST):
        raise ValueError('W9 requires the pinned Marked image digest reference')


def run_condition(engine, image_digest_ref, project_prefix, concurrency, *, cleanup_command=None):
    validate_image_ref(image_digest_ref)
    if not re.fullmatch(r'np-[a-z0-9][a-z0-9-]{0,39}', project_prefix):
        raise ValueError('invalid campaign-owned project prefix')
    if type(concurrency) is not int or concurrency not in SPEC['concurrency']:
        raise ValueError('W9 requires 16 jobs and concurrency 1, 4, 8, or 16')
    cases = SPEC['cases']
    owner = f'{project_prefix}-{uuid.uuid4().hex}'
    inputs = json.dumps([case['input'] for case in cases])

    def job(index):
        name = f'{owner}-{index:02d}'
        result = {'job': index, 'name': name, 'body': None, 'process': None, 'error': None, 'cleanup_error': None}
        try:
            completed = engine.sh(['run', '--rm', '--pull=never', '--name', name, '--label', f'dev.ctrs.campaign.run={owner}',
                                   '--network', 'none', '--entrypoint', 'node', image_digest_ref,
                                   '-e', SCRIPT, inputs], timeout=TIMEOUT, check=False)
            result['process'] = {'status': completed.returncode, 'stdout': completed.stdout, 'stderr': completed.stderr}
            if completed.returncode != 0:
                raise RuntimeError(f'container exited {completed.returncode}: {completed.stderr}')
            if completed.stderr:
                raise ValueError(f'unexpected container stderr: {completed.stderr!r}')
            result['body'] = json.loads(completed.stdout)
            validate_result(result['body'], cases)
        except Exception as exc:
            result['error'] = f'{type(exc).__name__}: {exc}'
            try:
                cleanup(engine, name, owner, command=cleanup_command)
            except Exception as cleanup_exc:
                result['cleanup_error'] = f'{type(cleanup_exc).__name__}: {cleanup_exc}'
        result['completion_seconds'] = time.monotonic() - dispatched
        return result

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)
    try:
        dispatched = time.monotonic()
        results = list(pool.map(job, range(SPEC['fixed_jobs'])))
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    if any(result['error'] or result['cleanup_error'] for result in results):
        raise ConditionFailed(results)
    return results
