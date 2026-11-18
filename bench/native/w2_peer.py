"""Run the W2 client in an owned peer on the fixture's application network."""
import json


URL = 'http://api:8000'
OUTPUT_DIR = '/work'
SCRIPT = f'{OUTPUT_DIR}/load.py'


def prepare(engine, peer, owner, project, api_id, image, source, expected_sha):
    engine.sh(['create', '--pull', 'never', '--name', peer, '--label', 'dev.ctrs.campaign.run=' + owner,
               '--network', project + '_appnet', '--tmpfs', OUTPUT_DIR + ':size=64m', '--entrypoint', 'python',
               image, '-c', 'import time; time.sleep(86400)'])
    engine.sh(['start', peer])
    info, = json.loads(engine.sh(['inspect', peer]).stdout)
    if info['Config']['Image'] != image or info['Id'] == api_id:
        raise ValueError('guest client identity differs from selected peer image')
    engine.sh(['exec', peer, 'python', '-c',
               "import pathlib,sys;pathlib.Path('/work/load.py').write_bytes(sys.argv[1].encode('utf-8'))",
               source.read_bytes().decode('utf-8')])
    digest = engine.sh(['exec', peer, 'python', '-c',
                       "import hashlib;print(hashlib.sha256(open('/work/load.py','rb').read()).hexdigest())"]).stdout.strip()
    if digest != expected_sha:
        raise ValueError('guest client source differs from pin')
    return info


def run(engine, peer, label, args, timeout):
    wrapper = ("import subprocess,sys; f=open(sys.argv[1],'w'); e=open(sys.argv[2],'w'); "
               "sys.exit(subprocess.run([sys.executable,'/work/load.py',*sys.argv[3:]],stdout=f,stderr=e).returncode)")
    return engine.sh(['exec', peer, 'python', '-c', wrapper, f'{OUTPUT_DIR}/{label}.stdout',
                      f'{OUTPUT_DIR}/{label}.stderr', *args], timeout=timeout, check=False)


def copy_results(engine, peer, directory, label):
    for suffix in ('.stdout', '.stderr', '.json', '.json.writes.jsonl', '.json.errors.jsonl'):
        result = engine.sh(['exec', peer, 'python', '-c',
                            "import pathlib,sys;sys.stdout.write(pathlib.Path(sys.argv[1]).read_bytes().decode('utf-8'))",
                            f'{OUTPUT_DIR}/{label}{suffix}'], timeout=60)
        (directory / (label + suffix)).write_bytes(result.stdout.encode('utf-8'))


def get(engine, peer, url, timeout):
    script = ("import json,sys,urllib.request; "
              "opener=urllib.request.build_opener(urllib.request.ProxyHandler({})); "
              "r=opener.open(sys.argv[1],timeout=float(sys.argv[2])); "
              "print(json.dumps([r.status,json.load(r)]))")
    result = engine.sh(['exec', peer, 'python', '-c', script, url, str(timeout)],
                       timeout=timeout + 5, check=False)
    return json.loads(result.stdout) if result.returncode == 0 else (0, result.stderr)
