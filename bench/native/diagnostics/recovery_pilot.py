"""Bounded diagnostic restart trace, separate from W10 acceptance scoring."""
import argparse
import sys,os,json,time,threading,socket,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import runner,recovery_trace,collect,recovery_client,diagnostic_signals
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--ctrs-binary',type=Path,required=True)
parser.add_argument('--engines',default='ctrs,orbstack')
parser.add_argument('--pairs',type=int,default=1)
parser.add_argument('--read-concurrency',type=int,default=4)
parser.add_argument('--read-interval',type=float,default=.02)
args=parser.parse_args()
engines=args.engines.split(',')
if not engines or len(set(engines))!=len(engines) or any(e not in ('ctrs','orbstack','dockerd') for e in engines):parser.error('invalid engines')
if not 1<=args.pairs<=10 or not 1<=args.read_concurrency<=32 or not math.isfinite(args.read_interval) or not 0<=args.read_interval<=1:parser.error('require 1..10 pairs, 1..32 readers and finite interval 0..1s')
diagnostic_signals.install_cleanup_signals()
runner.DOCKER=runner.find_docker();runner.CTRS_BIN=args.ctrs_binary.resolve()
os.environ['CTRS_LOG']='debug'
run='w10-trace-'+time.strftime('%Y%m%dT%H%M%S');root=runner.RESULTS/run;root.mkdir()
print('RESULTS',root,flush=True)
(root/'driver.py').write_bytes(Path(__file__).read_bytes())
(root/'recovery_client.py').write_bytes(Path(recovery_client.__file__).read_bytes())
(root/'plan.json').write_text(json.dumps({'client_version':recovery_client.VERSION,'client_sha256':runner.sha256_file(Path(recovery_client.__file__)),'kind':'diagnostic; policy identity comes from actual binary hash','read_concurrency':args.read_concurrency,'read_interval_s':args.read_interval,'probe_interval_s':.002,'planned_down_s':.5,'pre_post_s':1,'command_timeout_s':120,'recovery_poll_deadline_s':30,'binary_sha256':runner.sha256_file(runner.CTRS_BIN),'bootstrap_sha256':runner.sha256_file(Path('bench/native/diagnostics/w10_service.py'))},indent=2))
(root/'override.json').write_text(json.dumps({'services':{'api':{'command':['python','-u','/diagnostics/w10_service.py'],'volumes':[str(Path('bench/native/diagnostics/w10_service.py').resolve())+':/diagnostics/w10_service.py:ro']}}}))
all_results=[]
for pair in range(1,args.pairs+1):
 for ename in (engines if pair%2 else engines[::-1]):
  e=runner.Engine(ename,run);proj=runner.project_name(run,ename,'W10');d=root/f'{pair:02d}-{ename}';d.mkdir();stop=threading.Event();threads=[];attempts=[];tcp=[];sampler=None;timeline={};logoffset=0;api=None
  port=runner.free_port();base=f'http://127.0.0.1:{port}';env={'NP_API_PORT':str(port),'NP_API_TAG':runner.API_TAG}
  def compose(args):return e.sh(['compose','-f',str(runner.COMPOSE_FILE),'-f',str(root/'override.json'),'-p',proj,*args],env_extra=env,timeout=120)
  def probe(kind):
   client=recovery_client.ProbeClient('127.0.0.1',port)
   try:
    while not stop.is_set():
     t=time.monotonic();attempts.append(client.query(kind));stop.wait(max(0,(.002 if kind=='health' else args.read_interval)-(time.monotonic()-t)))
   finally:
    client.close()
  def tcp_probe():
   while not stop.is_set():
    a=time.monotonic_ns();error=None;error_errno=None
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.05):pass
    except Exception as exc:
     error,error_errno=recovery_trace.transport_error(exc)
    tcp.append(dict(started_ns=a,ended_ns=time.monotonic_ns(),ok=error is None,error=error,error_errno=error_errno));stop.wait(.01)
  try:
   e.ensure_up();compose(['up','-d','--no-build']);ready,_=runner.wait_health(base,90);assert ready
   api=compose(['ps','-q','api']).stdout.strip();assert api
   initial=json.loads(e.sh(['inspect',api]).stdout)[0];(d/'initial-inspect.json').write_text(json.dumps(initial,indent=2))
   for service in ('api','db','cache'):
    ident=compose(['ps','-q',service]).stdout.strip();(d/f'{service}-image.json').write_text(e.sh(['image','inspect',json.loads(e.sh(['inspect',ident]).stdout)[0]['Image']]).stdout)
   clock=[]
   for _ in range(5):
    a=time.time_ns();g=json.loads(e.sh(['exec',api,'python','-c','import time,json;print(json.dumps(dict(wall_ns=time.time_ns(),monotonic_ns=time.monotonic_ns())))']).stdout);b=time.time_ns();clock.append(dict(host_begin_ns=a,host_end_ns=b,guest_ns=g['wall_ns'],guest_monotonic_ns=g['monotonic_ns']))
   (d/'clock-before.json').write_text(json.dumps(clock,indent=2))
   for i in range(3):
    status,body=runner.http_json_write(base+'/records',{'key':f'committed-{i}','value':f'exact-value-{i}'});assert status==200 and body=={'stored':f'committed-{i}'}
   sampler,trace=runner.start_sampler(e,d)
   actual=e.measurement_identity
   if ename=='ctrs':
    executable=[p['executable']['sha256'] for p in actual['required_processes'] if p['role']=='daemon']
    assert executable==[runner.sha256_file(runner.CTRS_BIN)],'running daemon differs from requested diagnostic binary'
   (d/'measurement-identity.json').write_text(json.dumps(actual,indent=2))
   if ename=='ctrs':
    logpath=e.dir/'state/logs/daemon.log';logoffset=logpath.stat().st_size if logpath.exists() else 0
   before=collect.cpu_boundary(e.measurement_identity)
   marks={"healthy_before":before}
   for kind in ['health']+['read']*args.read_concurrency:
    t=threading.Thread(target=probe,args=(kind,));threads.append(t);t.start()
   t=threading.Thread(target=tcp_probe);threads.append(t);t.start()
   time.sleep(1)
   marks["healthy_after"]=collect.cpu_boundary(e.measurement_identity)
   timeline['kill_command_begin_ns']=time.monotonic_ns();timeline['kill_wall_ns']=time.time_ns();e.sh(['kill',api]);timeline['kill_command_returned_ns']=time.monotonic_ns()
   marks["outage_before"]=collect.cpu_boundary(e.measurement_identity)
   time.sleep(.5)
   marks["outage_after"]=collect.cpu_boundary(e.measurement_identity)
   timeline['start_command_begin_ns']=time.monotonic_ns();timeline['start_wall_ns']=time.time_ns();e.sh(['start',api]);timeline['start_command_returned_ns']=time.monotonic_ns();timeline['start_return_wall_ns']=time.time_ns()
   deadline=time.monotonic()+30
   while time.monotonic()<deadline:
    successes=[a for a in attempts if a['kind']=='health' and a['ok'] and a['started_ns']>=timeline['start_command_begin_ns']]
    if successes:
     timeline['first_success_ns']=min(a['ended_ns'] for a in successes);break
    time.sleep(.002)
   assert 'first_success_ns' in timeline,'recovery deadline'
   marks["post_before"]=collect.cpu_boundary(e.measurement_identity)
   time.sleep(1);stop.set()
   for t in threads:t.join(timeout=2);assert not t.is_alive()
   after=collect.cpu_boundary(e.measurement_identity)
   marks['post_after']=after
   (d/'phase-cpu.json').write_text(json.dumps({name:collect.cpu_delta(marks[name+'_before'],marks[name+'_after']) for name in ('healthy','outage','post')},indent=2))
   operation_cpu=collect.cpu_delta(before,after)
   (d/'operation-cpu.json').write_text(json.dumps(operation_cpu,indent=2))
   assert not operation_cpu['errors'],operation_cpu['errors']
   for i in range(3):
    status,body=runner.http_json(base+f'/records/committed-{i}');assert status==200 and body=={'key':f'committed-{i}','value':f'exact-value-{i}','cache_match':True},body
   db=compose(['ps','-q','db']).stdout.strip();rows=e.sh(['exec',db,'psql','-U','app','-d','app','-At','-c',"SELECT coalesce(json_agg(x ORDER BY key),'[]'::json) FROM (SELECT key,value FROM records) x"]).stdout
   assert json.loads(rows)==[{'key':f'committed-{i}','value':f'exact-value-{i}'} for i in range(3)],rows
   (d/'exact-records.json').write_text(rows)
   guest_events=e.sh(['exec',api,'cat','/tmp/np-recovery-events.jsonl']).stdout;(d/'guest-events.jsonl').write_text(guest_events)
   final=json.loads(e.sh(['inspect',api]).stdout)[0];(d/'final-inspect.json').write_text(json.dumps(final,indent=2))
   guest_after=[]
   for _ in range(5):
    a=time.time_ns();g=int(e.sh(['exec',api,'python','-c','import time;print(time.time_ns())']).stdout);b=time.time_ns();guest_after.append(dict(host_begin_ns=a,host_end_ns=b,guest_ns=g))
   (d/'clock-after.json').write_text(json.dumps(guest_after,indent=2))
   failures=recovery_trace.classify_failures(attempts,timeline['kill_command_begin_ns'],timeline['first_success_ns'])
   (d/'request-validation.json').write_text(json.dumps(failures,indent=2))
   assert failures['host_client_valid'],'host address allocation failed; measurement invalid'
   assert not failures['unexpected_errors'],f"unexpected request errors: {len(failures['unexpected_errors'])}; see request-validation.json"
   result=dict(engine=ename,measurement_valid=False,measurement_errors=['diagnostic; frozen inputs and exclusivity not certified'],client_version=recovery_client.VERSION,connect_attempts=sum(a['connect_attempts'] for a in attempts),connections_opened=sum(a['connections_opened'] for a in attempts),reused_socket_attempts=sum(a['reused_socket'] for a in attempts),correctness=True,timeline=timeline,intervals=recovery_trace.recovery_intervals(timeline),clock_before=recovery_trace.clock_bracket(clock),clock_after=recovery_trace.clock_bracket(guest_after),expected_outage_errors=len(failures['expected_outage_errors']),unexpected_errors=len(failures['unexpected_errors']),read_successes=sum(a['ok'] and a['kind']=='read' for a in attempts),tcp_note='host accept only; not guest readiness')
   (d/'result.json').write_text(json.dumps(result,indent=2));all_results.append(result);print(json.dumps(result),flush=True)
  finally:
   stop.set()
   (d/'timeline.json').write_text(json.dumps(timeline,indent=2))
   for t in threads:t.join(timeout=2)
   (d/'attempts.jsonl').write_text(''.join(json.dumps(a)+'\n' for a in sorted(attempts,key=lambda a:a['started_ns'])))
   (d/'tcp.jsonl').write_text(''.join(json.dumps(a)+'\n' for a in tcp))
   if ename=='ctrs':
    logpath=e.dir/'state/logs/daemon.log'
    if logpath.exists():(d/'daemon-events.jsonl').write_bytes(logpath.read_bytes()[logoffset:])
   try:
    if api is not None:
     logs=e.sh(['logs','--timestamps',api],check=False)
     (d/'container-logs.txt').write_text(logs.stdout+logs.stderr)
    compose(['down','-v','--remove-orphans'])
   finally:
    try:
     if sampler:runner.stop_sampler(sampler)
    finally:
     e.stop()
(root/'summary.json').write_text(json.dumps(all_results,indent=2));print('COMPLETED',root,flush=True)
