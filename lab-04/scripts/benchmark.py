#!/usr/bin/env python3
"""Two identical 500-user Locust runs in an isolated *_bench database."""
import json
import os
from pathlib import Path
import secrets
import statistics
import subprocess
import sys
import time
from urllib.request import urlopen
from urllib.error import URLError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from alembic.config import Config
from alembic import command
from app.core.config import Settings
from app.core.jwt import JwtCodec
from app.core.security import passwords,DUMMY_HASH
from app.database import make_session_factory
from app.modules.users.repository import UserRepository
from app.modules.auth.repository import AuthRepository
from app.modules.auth.service import AuthService

ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
settings=Settings()
url=make_url(settings.database_url)
url=make_url(os.environ['BENCH_DATABASE_URL']) if os.environ.get('BENCH_DATABASE_URL') else url.set(database=url.database+'_bench')
if not url.database.endswith('_bench'):
    raise SystemExit('A dedicated database ending in _bench is required; no changes made')
os.environ['DATABASE_URL']=url.render_as_string(hide_password=False)
settings=Settings()
OUT=ROOT/'docs/load'
OUT.mkdir(parents=True,exist_ok=True)
command.upgrade(Config('alembic.ini'),'head')
engine=create_engine(settings.database_url)
with engine.begin() as db:
    db.execute(text('CREATE EXTENSION IF NOT EXISTS pg_stat_statements'))
    db.execute(text('TRUNCATE refresh_tokens,auth_sessions,deliveries,orders,menu,users RESTART IDENTITY CASCADE'))
    db.execute(text("INSERT INTO menu(name,price,category_id) SELECT 'Блюдо '||lpad(g::text,5,'0'),(g%10000)/100.0,1+g%3 FROM generate_series(1,10000) g"))
    db.execute(text('ANALYZE menu'))
factory=make_session_factory(settings.database_url)
with factory() as db:
    password=secrets.token_urlsafe(24)
    UserRepository(db).create('load@example.org',passwords.hash(password),'student')
    pair=AuthService(AuthRepository(db),passwords,JwtCodec(settings),DUMMY_HASH).login('load@example.org',password)
token=pair['access_token']

def snapshot():
    with engine.connect() as db:
        rows=db.execute(text("SELECT query,calls,total_exec_time,rows FROM pg_stat_statements WHERE dbid=(SELECT oid FROM pg_database WHERE datname=current_database()) AND query LIKE 'SELECT%'"))
        data={'select_calls':0,'menu_select_calls':0,'menu_exec_ms':0,'menu_rows':0}
        for query,calls,ms,count in rows:
            data['select_calls']+=calls
            if 'FROM menu ' in query or 'FROM menu\n' in query:
                data['menu_select_calls']+=calls
                data['menu_exec_ms']+=ms
                data['menu_rows']+=count
        return data

summary={'method':{'users':500,'spawn_rate':10,'run_seconds':85,'steady_after_seconds':50,
                   'wait_time_seconds':[.1,.5],'menu_rows':10000,'returned_limit':100,
                   'auth':'same valid student Bearer token; all session/user checks enabled',
                   'workers':1,'order':['baseline','cached']},'phases':{}}
with engine.connect() as db:
    summary['environment']={'postgres':db.scalar(text('SELECT version()')),'cpu_count':os.cpu_count(),
                            'postgres_menu_rows':db.scalar(text('SELECT count(*) FROM menu')),
                            'date':'2026-11-02','database':url.database}
for phase,enabled in [('baseline',False),('cached',True)]:
    print('START',phase,flush=True)
    env={**os.environ,'CACHE_ENABLED':str(enabled).lower(),'CACHE_WARMUP':str(enabled).lower(),
         'BENCHMARK_TOKEN':token,'BENCH_RESULT':str(OUT/(phase+'-steady.json')),
         'BENCH_STEADY_START':'50','BENCH_STEADY_END':'85'}
    # Dedicated local Redis keys, shared rate-limit keys are left alone.
    from app.core.redis import menu_redis
    cache=menu_redis(settings.redis_url)
    keys=list(cache.scan_iter(match='menu:*'))
    if keys: cache.delete(*keys)
    cache.close()
    with (OUT/(phase+'-server.log')).open('w') as serverlog, (OUT/(phase+'-locust.log')).open('w') as loadlog:
        server=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1',
                                 '--port','18004','--no-proxy-headers','--no-access-log'],env=env,stdout=serverlog,stderr=serverlog)
        runner=None
        try:
            for _ in range(100):
                if server.poll() is not None: raise RuntimeError('Server exited; inspect server log')
                try:
                    with urlopen('http://127.0.0.1:18004/health',timeout=1): break
                except URLError: time.sleep(.1)
            else: raise RuntimeError('Server startup timeout')
            before=snapshot()
            load_before=os.getloadavg()
            runner=subprocess.Popen([sys.executable,'-m','locust','-f','locustfile.py','--headless',
                                     '--host','http://127.0.0.1:18004','--users','500','--spawn-rate','10',
                                     '--run-time','85s','--stop-timeout','15','--csv',str(OUT/phase),
                                     '--csv-full-history','--only-summary','--exit-code-on-error','1'],
                                    env=env,stdout=loadlog,stderr=loadlog)
            load_samples=[]
            while runner.poll() is None:
                load_samples.append(os.getloadavg()[0])
                time.sleep(1)
            if runner.returncode:
                raise RuntimeError(f'{phase} Locust failed: inspect {phase}-locust.log')
            after=snapshot()
            steady=json.loads((OUT/(phase+'-steady.json')).read_text())
            assert steady['configured_users']==500 and steady['peak_spawned_users']==500 and steady['failures']==0
            result={'requests':steady['full_requests'],'failures':steady['full_failures'],
                    'rps':steady['full_rps'],'mean_ms':steady['full_mean_ms'],
                    'p95_ms':steady['full_p95_ms'],'host_load_average_1m_before':load_before[0],
                    'host_load_average_1m_mean':statistics.mean(load_samples),
                    'host_load_average_1m_after':os.getloadavg()[0],
                    'postgres':{k:after[k]-before[k] for k in before},'steady':steady}
            summary['phases'][phase]=result
            (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
            print('DONE',phase,json.dumps(result,ensure_ascii=False),flush=True)
        finally:
            if runner and runner.poll() is None:
                runner.terminate();runner.wait(timeout=20)
            server.terminate()
            try:
                server.wait(timeout=20)
            except subprocess.TimeoutExpired:
                server.kill();server.wait(timeout=5)
# Keep numerical artifacts intact while normalizing CSV CRLF for Git.
for artifact in OUT.iterdir():
    if artifact.suffix in {'.csv','.log'}:
        artifact.write_text('\n'.join(line.rstrip() for line in artifact.read_text().splitlines()).rstrip()+'\n')
engine.dispose()
print('Benchmark complete',flush=True)
