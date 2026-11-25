#!/usr/bin/env python3
"""Demonstrate independent HTTP and gRPC OS processes, including real streaming."""
import base64
import json
import os
from pathlib import Path
import queue
import secrets
import signal
import subprocess
import sys
import time
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import grpc
import delivery_pb2 as pb
import delivery_pb2_grpc as wire
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from alembic.config import Config
from alembic import command
from redis import Redis
from app.core.config import Settings
from app.core.security import passwords
from app.database import make_session_factory
from app.modules.users.repository import UserRepository

ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT)
OUT=ROOT/'docs/live';OUT.mkdir(parents=True,exist_ok=True)
base=Settings();url=make_url(base.database_url)
url=make_url(os.environ['INTEGRATION_DATABASE_URL']) if os.environ.get('INTEGRATION_DATABASE_URL') else url.set(database=url.database+'_integration')
if not url.database.endswith('_integration'):raise SystemExit('Dedicated _integration database required')
admin=create_engine(make_url(base.database_url).set(database='postgres'),isolation_level='AUTOCOMMIT')
with admin.connect() as db:
    if not db.scalar(text('SELECT 1 FROM pg_database WHERE datname=:name'),{'name':url.database}):
        db.execute(text('CREATE DATABASE '+admin.dialect.identifier_preparer.quote(url.database)))
admin.dispose()
redis_base=base.redis_url.rsplit('/',1)[0]
os.environ.update(DATABASE_URL=url.render_as_string(hide_password=False),REDIS_URL=redis_base+'/10',
                  CELERY_BROKER_URL=redis_base+'/11',CELERY_RESULT_BACKEND=redis_base+'/12',
                  DELIVERY_GRPC_TARGET='127.0.0.1:19051',DELIVERY_GRPC_BIND='127.0.0.1:19051',
                  DELIVERY_POLL_SECONDS='.1' if '--quick' in sys.argv else '2')
settings=Settings();command.upgrade(Config('alembic.ini'),'head')
factory=make_session_factory(settings.database_url)
password=secrets.token_urlsafe(24)
with factory() as db:
    db.execute(text('TRUNCATE maintenance_runs,refresh_tokens,auth_sessions,deliveries,orders,menu,users RESTART IDENTITY CASCADE'))
    db.execute(text("INSERT INTO menu(name,price) VALUES ('Live demo',125.50)"));db.commit()
    repository=UserRepository(db)
    for name,role in [('alice','student'),('bob','student'),('rider','courier'),('root','admin')]:
        repository.create(name+'@example.org',passwords.hash(password),role)
for suffix in ('10','11','12'):
    with Redis.from_url(redis_base+'/'+suffix) as redis:
        keys=[k for k in redis.scan_iter() if k.startswith((b'sirius06:',b'sirius:rate:',b'menu:'))]
        if keys:redis.delete(*keys)
processes=[];logs=[]

def spawn(name,cmd):
    log=(OUT/(name+'.log')).open('w');logs.append(log)
    proc=subprocess.Popen(cmd,env=os.environ.copy(),stdout=log,stderr=log,start_new_session=True)
    processes.append(proc);return proc

def stop(proc):
    if proc.poll() is not None:return
    os.killpg(proc.pid,signal.SIGTERM)
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)

def eventually(action,timeout=20):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            value=action()
            if value:return value
        except (URLError,grpc.FutureTimeoutError):pass
        time.sleep(.1)
    raise RuntimeError('Live demo readiness timeout')

def http(path,token=None,data=None):
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    request=Request('http://127.0.0.1:18006'+path,headers=headers,
                    data=json.dumps(data).encode() if data is not None else None)
    with urlopen(request,timeout=10) as response:return json.load(response)

result={'checks':{},'tracking':[],'chat':[],'transport':'real TCP gRPC / HTTP in separate OS processes'}
channel=grpc.insecure_channel(settings.delivery_grpc_target,options=[('grpc.enable_retries',0)])
stub=wire.DeliveryServiceStub(channel)
class Peer:
    def __init__(self, token, delivery):
        self.q=queue.Queue();self.q.put(pb.ChatMessage(delivery_id=delivery))
        def outgoing():
            while True:
                item=self.q.get()
                if item is None:return
                yield item
        self.call=stub.ChatWithCourier(outgoing(),metadata=(('authorization','Bearer '+token),),timeout=10)
        assert next(self.call).event=='joined'
    def close(self):self.call.cancel();self.q.put(None)
try:
    delivery=spawn('delivery',[sys.executable,'delivery_server.py'])
    eventually(lambda:grpc.channel_ready_future(channel).result(timeout=.5) is None)
    api=spawn('monolith',[sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','18006','--no-proxy-headers','--no-access-log'])
    eventually(lambda:http('/health'))
    tokens={name:http('/auth/login',data={'email':name+'@example.org','password':password})['access_token']
            for name in ('alice','bob','rider','root')}
    order=http('/orders/create',tokens['alice'],{'item_id':1,'quantity':1})['order_id']
    d=http('/delivery/assign',tokens['root'],{'order_id':order,'courier_id':3})
    assert http('/delivery/'+str(d['id']),tokens['alice'])==d
    result['checks']['http_assign_get_via_grpc']=True
    for token in (tokens['bob'],'invalid'):
        try:stub.GetDelivery(pb.DeliveryLookup(delivery_id=d['id']),metadata=(('authorization','Bearer '+token),),timeout=2)
        except grpc.RpcError as error:
            expected=grpc.StatusCode.PERMISSION_DENIED if token==tokens['bob'] else grpc.StatusCode.UNAUTHENTICATED
            assert error.code()==expected
        else:raise AssertionError('Unauthorized direct RPC succeeded')
    result['checks']['grpc_enforces_jwt_and_ownership']=True
    track=stub.TrackDelivery(pb.DeliveryId(delivery_id=d['id']),metadata=(('authorization','Bearer '+tokens['alice']),),timeout=15)
    result['tracking'].append(next(track).status)
    http(f"/delivery/{d['id']}/start",tokens['rider'],{})
    result['tracking'].append(next(track).status)
    http(f"/delivery/{d['id']}/complete",tokens['rider'],{})
    result['tracking'].append(next(track).status)
    assert result['tracking']==['ASSIGNED','ON_THE_WAY','DELIVERED']
    track.cancel();result['checks']['real_server_stream']=True
    a,b=Peer(tokens['alice'],d['id']),Peer(tokens['rider'],d['id'])
    try:
        a.q.put(pb.ChatMessage(delivery_id=d['id'],text='Where are you?'))
        own,received=next(a.call),next(b.call)
        assert own.text==received.text and received.sender_id==1
        result['chat'].append({'sender_id':received.sender_id,'text':received.text})
        b.q.put(pb.ChatMessage(delivery_id=d['id'],text='At the entrance'))
        received,own=next(a.call),next(b.call)
        assert own.text==received.text and received.sender_id==3
        result['chat'].append({'sender_id':received.sender_id,'text':received.text})
    finally:a.close();b.close()
    result['checks']['two_real_bidi_chat_clients']=True
    second=http('/orders/create',tokens['alice'],{'item_id':1,'quantity':1})['order_id']
    another=http('/delivery/assign',tokens['root'],{'order_id':second,'courier_id':3})
    timed=stub.TrackDelivery(pb.DeliveryId(delivery_id=another['id']),metadata=(('authorization','Bearer '+tokens['alice']),),timeout=.3)
    next(timed)
    try:next(timed)
    except grpc.RpcError as error:assert error.code()==grpc.StatusCode.DEADLINE_EXCEEDED
    else:raise AssertionError('Missing stream deadline')
    result['checks']['real_deadline_exceeded']=True
    stop(delivery)
    try:http('/delivery/'+str(d['id']),tokens['alice'])
    except HTTPError as error:
        assert error.code==503;result['checks']['stopped_service_http_503']=True
    else:raise AssertionError('Expected 503')
    assert http('/menu/items',tokens['alice'])
    result['checks']['monolith_other_modules_remain_available']=True
    delivery=spawn('delivery-restarted',[sys.executable,'delivery_server.py'])
    eventually(lambda:http('/delivery/'+str(d['id']),tokens['alice']))
    assert http('/delivery/'+str(d['id']),tokens['alice'])['status']=='DELIVERED'
    result['checks']['reconnect_and_delivery_persisted']=True
    result['process_ids']={'monolith':api.pid,'delivery':delivery.pid}
    assert api.pid!=delivery.pid
    (OUT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: independent processes, unary, JWT, tracking, bidirectional chat, deadline, outage and recovery')
finally:
    channel.close()
    for proc in reversed(processes):stop(proc)
    for log in logs:log.close()
    for file in OUT.glob('*.log'):
        file.write_text('\n'.join(line.rstrip() for line in file.read_text().splitlines()).rstrip()+'\n')
