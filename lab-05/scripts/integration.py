#!/usr/bin/env python3
"""Real API + Redis + prefork worker + Beat + Flower; no eager tasks."""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import signal
import statistics
import subprocess
import sys
import time
from urllib.request import Request,urlopen
from urllib.error import URLError,HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine,select,text,func
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config
from redis import Redis
from app.core.config import Settings
from app.core.security import passwords
from app.database import make_session_factory
from app.models import JobRow,EffectRow,MaintenanceRow,DeadLetterRow,TaskLogRow
from app.modules.users.repository import UserRepository
from app.core.celery_app import build_celery
from app.tasks.dispatch import CeleryDispatcher

parser=argparse.ArgumentParser();parser.add_argument('--quick',action='store_true');args=parser.parse_args()
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT)
OUT=ROOT/'docs'/('ci' if args.quick else 'demo');OUT.mkdir(parents=True,exist_ok=True)
base=Settings();url=make_url(base.database_url)
url=make_url(os.environ['INTEGRATION_DATABASE_URL']) if os.environ.get('INTEGRATION_DATABASE_URL') else url.set(database=url.database+'_integration')
if not url.database.endswith('_integration'):
    raise SystemExit('Dedicated database ending in _integration required')
admin=create_engine(make_url(base.database_url).set(database='postgres'),isolation_level='AUTOCOMMIT')
with admin.connect() as db:
    if not db.scalar(text('SELECT 1 FROM pg_database WHERE datname=:name'),{'name':url.database}):
        db.execute(text('CREATE DATABASE '+admin.dialect.identifier_preparer.quote(url.database)))
admin.dispose()
root_redis=base.redis_url.rsplit('/',1)[0]
os.environ.update(DATABASE_URL=url.render_as_string(hide_password=False),REDIS_URL=root_redis+'/10',
                  CELERY_BROKER_URL=root_redis+'/11',CELERY_RESULT_BACKEND=root_redis+'/12',
                  CACHE_WARMUP='true',NOTIFICATION_MODE='celery',DEMO_FAIL_EMAIL_MODULO='5',
                  RETRY_BASE_SECONDS='.05' if args.quick else '1',
                  SIMULATED_PDF_SECONDS='.05' if args.quick else '2',
                  SIMULATED_EMAIL_SECONDS='.03' if args.quick else '1',
                  SIMULATED_SMS_SECONDS='.03' if args.quick else '1',
                  BEAT_CLEANUP_SECONDS='1' if args.quick else '60',BEAT_OUTBOX_SECONDS='1' if args.quick else '10')
settings=Settings();factory=make_session_factory(settings.database_url)
command.upgrade(Config('alembic.ini'),'head')
with factory() as db:
    db.execute(text('TRUNCATE maintenance_runs,refresh_tokens,auth_sessions,deliveries,orders,menu,users RESTART IDENTITY CASCADE'))
    db.execute(text("INSERT INTO menu(name,price) VALUES ('Demo meal',125.50)"));db.commit()
    password=secrets.token_urlsafe(24)
    UserRepository(db).create('demo@example.org',passwords.hash(password),'student')
for suffix in ('10','11','12'):
    client=Redis.from_url(root_redis+'/'+suffix)
    keys=[k for k in client.scan_iter() if k.startswith((b'sirius05:',b'sirius:rate:',b'menu:'))]
    if keys:client.delete(*keys)
    client.close()
processes=[];handles=[]
credentials='monitor:'+secrets.token_hex(16)
env={**os.environ,'FLOWER_BASIC_AUTH':credentials}
celery=[sys.executable,'-m','celery','-A','app.core.celery_app:celery_app']

def spawn(name,cmd,extra=None):
    handle=(OUT/(name+'.log')).open('w');handles.append(handle)
    p=subprocess.Popen(cmd,env={**env,**(extra or {})},stdout=handle,stderr=handle,start_new_session=True)
    processes.append(p);return p

def stop(p):
    if p.poll() is not None:return
    os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(timeout=8)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=5)

def eventually(callback,timeout=45):
    deadline=time.monotonic()+timeout
    last=None
    while time.monotonic()<deadline:
        try:
            value=callback()
            if value:return value
        except (URLError,ConnectionError,HTTPError) as error:last=type(error).__name__
        time.sleep(.1)
    raise RuntimeError('Timed out waiting for demo condition '+str(last or ''))

def request(path,data=None,token=None,port=18005,basic=False):
    headers={}
    if data is not None:headers['Content-Type']='application/json'
    if token:headers['Authorization']='Bearer '+token
    if basic:headers['Authorization']='Basic '+base64.b64encode(credentials.encode()).decode()
    r=Request(f'http://127.0.0.1:{port}'+path,headers=headers,data=json.dumps(data).encode() if data is not None else None)
    with urlopen(r,timeout=15) as response:
        content=response.read()
        return json.loads(content) if 'application/json' in response.headers.get('Content-Type','') else content

worker_cmd=celery+['worker','--pool=prefork','--concurrency=2','--loglevel=info','-Q','default','-E','--hostname=sirius05-demo@%h']
app=build_celery(settings)
summary={'quick':args.quick,'eager':False,'durations':{},'checks':{},'simulated_delays_seconds':
         {'pdf':settings.simulated_pdf_seconds,'email':settings.simulated_email_seconds,'sms':settings.simulated_sms_seconds}}

def order_state(order_id):
    with factory() as db:
        return {j.kind:j.status for j in db.scalars(select(JobRow).where(JobRow.order_id==order_id))}

def terminal():
    with factory() as db:
        return db.scalar(select(func.count()).select_from(JobRow).where(JobRow.status.in_(['PENDING','RETRYING'])))==0

try:
    worker=spawn('worker',worker_cmd)
    eventually(lambda:app.control.ping(timeout=.5),timeout=30)
    flower=spawn('flower',celery+['flower','--address=127.0.0.1','--port=15555'])
    eventually(lambda:request('/',port=15555,basic=True),timeout=30)
    api_cmd=[sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','18005','--no-proxy-headers','--no-access-log']
    api=spawn('api-sync',api_cmd,{'NOTIFICATION_MODE':'sync'})
    eventually(lambda:request('/health'),timeout=20)
    token=request('/auth/login',{'email':'demo@example.org','password':password})['access_token']
    for mode in ('sync','celery'):
        if mode=='celery':
            stop(api);api=spawn('api-celery',api_cmd)
            eventually(lambda:request('/health'),timeout=20)
        values=[]
        for _ in range(3):
            started=time.perf_counter()
            response=request('/orders/create',{'item_id':1,'quantity':2},token)
            values.append((time.perf_counter()-started)*1000)
            assert response['status']=='success'
        summary['durations'][mode]={'samples_ms':values,'median_ms':statistics.median(values)}
        print(mode,summary['durations'][mode],flush=True)
    beat=spawn('beat',celery+['beat','--loglevel=info','--schedule',str(OUT/'beat-schedule')])
    eventually(terminal,timeout=60)
    assert order_state(5)=={'pdf':'SUCCEEDED','email':'DEAD','sms':'SUCCEEDED'}
    with factory() as db:
        failed=db.scalar(select(JobRow).where(JobRow.order_id==5,JobRow.kind=='email'))
        pdf=db.scalar(select(JobRow).where(JobRow.order_id==4,JobRow.kind=='pdf'))
        failed_id,pdf_id=failed.id,pdf.id
        assert failed.attempts==4 and db.get(DeadLetterRow,failed.id) is not None
        summary['checks']['real_retries_attempts']=failed.attempts
    with Redis.from_url(settings.broker_url) as broker:
        assert broker.llen('sirius05:dlq')==1
    summary['checks']['real_dlq_message']=True
    # Deliver a duplicate with a fresh transport task ID; durable business key still wins.
    duplicate=app.send_task('sirius.generate_order_pdf',args=[pdf_id],queue='default')
    result=duplicate.get(timeout=20)
    assert result['status']=='skipped'
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(EffectRow).where(EffectRow.job_id==pdf_id))==1
    summary['checks']['duplicate_skipped']=True
    eventually(lambda: bool(request('/api/tasks',port=15555,basic=True)),timeout=20)
    summary['checks']['flower_authenticated_api']=True
    # Wait for an actual Beat tick (60 seconds in normal mode, 1 in quick mode).
    def maintenance_ran():
        with factory() as db:return db.scalar(select(func.count()).select_from(MaintenanceRow))>0
    eventually(maintenance_ran,timeout=75)
    summary['checks']['real_beat_cleanup']=True
    stop(beat)
    # Broker endpoint unavailable to this producer; cache/rate-limit Redis stays online.
    stop(api);api=spawn('api-broker-outage',api_cmd,{'CELERY_BROKER_URL':'redis://127.0.0.1:1/11'})
    eventually(lambda:request('/health'),timeout=20)
    response=request('/orders/create',{'item_id':1,'quantity':1},token)
    recovery_order=response['order_id']
    with factory() as db:
        pending=list(db.scalars(select(JobRow).where(JobRow.order_id==recovery_order)))
        assert len(pending)==3 and all(j.published_at is None for j in pending)
    assert CeleryDispatcher(factory,settings).publish_pending(recovery_order)==3
    eventually(lambda:all(s=='SUCCEEDED' for s in order_state(recovery_order).values()),timeout=25)
    summary['checks']['broker_outage_order_preserved_and_recovered']=True
    # Worker offline: tasks remain queued, then are handled by a fresh worker.
    stop(worker);stop(api);api=spawn('api-worker-offline',api_cmd)
    eventually(lambda:request('/health'),timeout=20)
    stopped_order=request('/orders/create',{'item_id':1,'quantity':1},token)['order_id']
    assert set(order_state(stopped_order).values())=={'PENDING'}
    worker=spawn('worker-restarted',worker_cmd)
    if not args.quick:
        with factory() as db:
            crash_job=db.scalar(select(JobRow.id).where(JobRow.order_id==stopped_order,JobRow.kind=='pdf'))
        def active_pdf():
            for tasks in (app.control.inspect(timeout=.3).active() or {}).values():
                for task in tasks:
                    if task['id']==crash_job:return task['worker_pid']
        pid=eventually(active_pdf,timeout=20)
        assert os.getpgid(pid)==worker.pid
        os.kill(pid,signal.SIGKILL)
        summary['checks']['worker_child_killed_during_pdf']=True
    eventually(lambda:all(s=='SUCCEEDED' for s in order_state(stopped_order).values()),timeout=45)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(EffectRow).where(EffectRow.order_id==stopped_order))==3
    summary['checks']['worker_restart_and_effects_once']=True
    if not args.quick:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
            user,secret=credentials.split(':',1)
            page=browser.new_page(viewport={'width':1500,'height':1050},http_credentials={'username':user,'password':secret})
            for path,name in [('/tasks','flower-tasks.png'),('/task/'+failed_id,'flower-failed-task.png')]:
                page.goto('http://127.0.0.1:15555'+path,wait_until='networkidle')
                page.wait_for_timeout(1500)
                page.screenshot(path=str(OUT/name),full_page=True)
            browser.close()
    with factory() as db:
        summary['jobs']=[dict(order_id=j.order_id,kind=j.kind,status=j.status,attempts=j.attempts) for j in db.scalars(select(JobRow).order_by(JobRow.order_id,JobRow.kind))]
        summary['effects']=db.scalar(select(func.count()).select_from(EffectRow))
        summary['maintenance_runs']=db.scalar(select(func.count()).select_from(MaintenanceRow))
        summary['failure_attempt_logs']=[dict(attempt=l.attempt,outcome=l.outcome,created_at=l.created_at.isoformat())
            for l in db.scalars(select(TaskLogRow).where(TaskLogRow.job_id==failed_id).order_by(TaskLogRow.id))]
    (OUT/('quick-results.json' if args.quick else 'results.json')).write_text(json.dumps(summary,indent=2)+'\n')
    print('PASS: real Celery, retries, DLQ, duplicate, broker recovery, worker restart, Beat, Flower',flush=True)
finally:
    for proc in reversed(processes):stop(proc)
    for handle in handles:handle.close()
    for file in OUT.glob('*.log'):
        file.write_text('\n'.join(line.rstrip() for line in file.read_text().splitlines()).rstrip()+'\n')
    # Beat runtime database may contain broker metadata; keep it out of Git.
    for file in OUT.glob('beat-schedule*'):file.unlink()
