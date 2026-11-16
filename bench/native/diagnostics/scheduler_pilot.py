"""Capture a filtered scheduler diagnostic; this command never qualifies timing."""
import argparse
import atexit
import signal
import sys,os,json,time,secrets,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import runner,ownership,collect,sched_trace
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tools-archive',type=Path,required=True)
parser.add_argument('--engines',default='ctrs,orbstack')
parser.add_argument('--operations',type=int,default=2000)
args=parser.parse_args()
engines=args.engines.split(',')
if args.operations<1 or len(set(engines))!=len(engines) or any(e not in ('ctrs','orbstack') for e in engines):parser.error('invalid engines or work count')
archive=args.tools_archive.resolve()
if runner.sha256_file(archive)!='475ad5495772fa311084f9e15335c18aeffce3e8cb138c3d11e3f9a12b06883b':parser.error('profiler archive differs from the pinned tools')
requested_signal=None

def stop_signal(number, frame):
 global requested_signal
 requested_signal=number
 for item in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP,signal.SIGQUIT):signal.signal(item,signal.SIG_IGN)
 raise SystemExit(128+number)

def restore_signal():
 if requested_signal is not None:
  signal.signal(requested_signal,signal.SIG_DFL)
  os.kill(os.getpid(),requested_signal)

atexit.register(restore_signal)
for number in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP,signal.SIGQUIT):signal.signal(number,stop_signal)
runner.DOCKER=runner.find_docker();run='w2-scheduler-'+time.strftime('%Y%m%dT%H%M%S');root=runner.RESULTS/run;root.mkdir();(root/'driver.py').write_bytes(Path(__file__).read_bytes());print('RESULTS',root,flush=True)
for name in engines:
 e=runner.Engine(name,run);directory=root/name;directory.mkdir();proj=runner.project_name(run,name,'W2sched');port=runner.free_port();base=f'http://127.0.0.1:{port}';tag='np'+secrets.token_hex(6);api=None;proc=None;log=None;primary=None
 override=directory/'compose.json';override.write_text(json.dumps({'services':{'api':{'privileged':True,'command':['python','-u','/diagnostics/w2_scheduler_app.py'],'environment':{'NP_SCHED_TAG':tag},'volumes':[str(Path('bench/native/diagnostics/w2_scheduler_app.py').resolve())+':/diagnostics/w2_scheduler_app.py:ro']}}}))
 def compose(args):return e.sh(['compose','-f',str(runner.COMPOSE_FILE),'-f',str(override),'-p',proj,*args],env_extra={'NP_API_PORT':str(port),'NP_API_TAG':runner.API_TAG},timeout=180)
 try:
  e.ensure_up();compose(['up','-d','--no-build']);assert runner.wait_health(base,60)[0]
  api=compose(['ps','-q','api']).stdout.strip();(directory/'api-inspect.json').write_text(e.sh(['inspect',api]).stdout)
  e.sh(['cp',str(archive),api+':/tmp/np-tools.tar.gz'])
  prepare="import os,tarfile;tarfile.open('/tmp/np-tools.tar.gz').extractall('/tmp/np-tools',filter='data');os.makedirs('/tmp/np-sched');os.mkfifo('/tmp/np-sched/control');os.mkfifo('/tmp/np-sched/ack')"
  e.sh(['exec','--privileged',api,'python','-c',prepare]);e.sh(['exec','--privileged',api,'mount','-t','tracefs','tracefs','/sys/kernel/tracing'])
  warm=subprocess.run([sys.executable,str(runner.LOAD_PY),'--url',base,'--concurrency','4','--operations','1000','--write-ratio','0','--out',str(directory/'warm.json')],capture_output=True,text=True,timeout=60);assert warm.returncode==0,warm.stderr
  snapshot="import json,pathlib;print(json.dumps({d.name:{p:d.joinpath(p).read_text() for p in ['comm','stat','status']} for d in pathlib.Path('/proc/1/task').iterdir()}))"
  before=json.loads(e.sh(['exec',api,'python','-c',snapshot]).stdout);assert all(t['comm'].strip()==tag for t in before.values()),before;(directory/'tasks-before.json').write_text(json.dumps(before,indent=2))
  owned=ownership.discover(e.name,Path(e.socket.removeprefix('unix://')),e.dir)
  (directory/'running-engine.json').write_text(json.dumps(owned,indent=2))
  perf='/tmp/np-tools/usr/bin/perf';libpath='/tmp/np-tools/lib/aarch64-linux-gnu'
  perf_args=[perf,'record','-a','-m','1024','--clockid','mono','--delay=-1','--control','fifo:/tmp/np-sched/control,/tmp/np-sched/ack','-o','/tmp/np-sched/data']
  for event in ('sched_waking','sched_wakeup','sched_migrate_task'):perf_args += ['-e','sched:'+event,'--filter',f'comm == "{tag}"']
  perf_args+=['-e','sched:sched_switch','--filter',f'prev_comm == "{tag}" || next_comm == "{tag}"']
  launch="import os,sys;open('/tmp/np-sched/perf.pid','w').write(str(os.getpid()));os.environ['LD_LIBRARY_PATH']=sys.argv[1];os.execv(sys.argv[2],sys.argv[2:])"
  log=(directory/'perf.log').open('wb');proc=subprocess.Popen([runner.DOCKER,'exec','--privileged',api,'python','-c',launch,libpath,*perf_args],env=e.env(),stdout=log,stderr=subprocess.STDOUT)
  enable="import os,select,json;control=os.open('/tmp/np-sched/control',os.O_RDWR);ack=os.open('/tmp/np-sched/ack',os.O_RDWR|os.O_NONBLOCK);os.write(control,b'enable'+bytes([10]));ready=bool(select.select([ack],[],[],5)[0]);data=os.read(ack,100) if ready else b'';print(json.dumps(dict(ready=ready,data_hex=data.hex())),flush=True);assert ready;assert data==b'ack'+bytes([10,0])"
  enabled=e.sh(['exec','--privileged',api,'python','-c',enable],timeout=15,check=False)
  (directory/'control-enable.txt').write_text(enabled.stdout+enabled.stderr)
  assert enabled.returncode==0,enabled.stdout+enabled.stderr
  (directory/'cpu-before.json').write_text(json.dumps(collect.cpu_boundary(owned),indent=2))
  (directory/'phase-tasks-before.json').write_text(e.sh(['exec',api,'python','-c',snapshot]).stdout)
  load=subprocess.run([sys.executable,str(runner.LOAD_PY),'--url',base,'--concurrency','4','--operations',str(args.operations),'--write-ratio','.3','--seed','7','--out',str(directory/'load.json')],capture_output=True,text=True,timeout=60);assert load.returncode==0,load.stderr
  (directory/'phase-tasks-after.json').write_text(e.sh(['exec',api,'python','-c',snapshot]).stdout)
  (directory/'cpu-after.json').write_text(json.dumps(collect.cpu_boundary(owned),indent=2))
  stop="import os,signal;pid=int(open('/tmp/np-sched/perf.pid').read());assert b'/tmp/np-tools/usr/bin/perf' in open(f'/proc/{pid}/cmdline','rb').read();os.kill(pid,signal.SIGINT)"
  e.sh(['exec','--privileged',api,'python','-c',stop]);code=proc.wait(timeout=15);log.close();(directory/'perf-exit.txt').write_text(str(code));assert code in (0,130),(directory/'perf.log').read_text()
  script=e.sh(['exec','--privileged',api,'env',f'LD_LIBRARY_PATH={libpath}',perf,'script','--ns','--show-lost-events','-F','trace:comm,pid,tid,cpu,time,event,trace','-i','/tmp/np-sched/data'],timeout=60)
  (directory/'sched.txt').write_text(script.stdout);(directory/'sched-stderr.txt').write_text(script.stderr);e.sh(['cp',api+':/tmp/np-sched/data',str(directory/'perf.data')]);(directory/'tasks-after.json').write_text(e.sh(['exec',api,'python','-c',snapshot]).stdout)
  db=compose(['ps','-q','db']).stdout.strip()
  query="SELECT coalesce(json_agg(json_build_array(name,payload)), '[]'::json) FROM items"
  persisted=json.loads(e.sh(['exec',db,'psql','-U','app','-d','app','-At','-c',query]).stdout)
  (directory/'persisted-items.json').write_text(json.dumps(persisted))
  writes=[json.loads(line) for line in (directory/'load.json.writes.jsonl').read_text().splitlines()]
  assert runner.exact_w2_items(persisted,writes),'persisted application state mismatch'
  (directory/'persisted-items.json').write_text(json.dumps(persisted))
  (directory/'identity.json').write_text(json.dumps({'tag':tag,'operations':args.operations,'kind':'capability/grammar diagnostic; timings unqualified; busy host','tools_archive_sha256':runner.sha256_file(archive),'bootstrap_sha256':runner.sha256_file(Path('bench/native/diagnostics/w2_scheduler_app.py')),'parser_sha256':runner.sha256_file(Path(sched_trace.__file__))},indent=2));print(name,'captured',len(script.stdout.splitlines()),'lines',flush=True)
  hz=int(e.sh(['exec',api,'python','-c',"import os;print(os.sysconf('SC_CLK_TCK'))"]).stdout)
  application_cpu=sched_trace.application_cpu_delta(json.loads((directory/'phase-tasks-before.json').read_text()),json.loads((directory/'phase-tasks-after.json').read_text()),hz,required_tids=before)
  (directory/'application-cpu.json').write_text(json.dumps(application_cpu,indent=2))
  assert application_cpu['status']=='ok',application_cpu['errors']
  analysis=sched_trace.analyze(script.stdout,tag=tag,tasks_before=before,tasks_after=json.loads((directory/'tasks-after.json').read_text()))
  (directory/'sched-analysis.json').write_text(json.dumps(analysis,separators=(',',':')))
  assert analysis['status']=='ok',(analysis['errors'],analysis['incomplete'])
 except BaseException as exc:
  primary=exc
  raise
 finally:
  cleanup_errors=[]
  try:
   if proc and proc.poll() is None:
    proc.terminate()
    try:proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
     proc.kill();proc.wait(timeout=5)
  except Exception as exc:cleanup_errors.append(str(exc))
  if log and not log.closed:log.close()
  try:compose(['down','-v','--remove-orphans'])
  except Exception as exc:cleanup_errors.append(str(exc))
  try:e.stop()
  except Exception as exc:cleanup_errors.append(str(exc))
  (directory/'cleanup.json').write_text(json.dumps({'errors':cleanup_errors}))
  if cleanup_errors and primary is None:raise RuntimeError('; '.join(cleanup_errors))
