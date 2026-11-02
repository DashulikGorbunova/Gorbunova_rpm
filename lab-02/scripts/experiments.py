#!/usr/bin/env python3
"""Reproducible growth experiments; touches only lab02 in a dedicated container."""
import json, os, sys, statistics, platform
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'lab-01/scripts'))
from db import sql
from server import orders_query
OUT=Path(__file__).resolve().parents[1]/'docs/plans'
OUT.mkdir(parents=True,exist_ok=True)
results={}
def run(q): return sql('SET search_path=lab02,public; '+q)
def measure(key,q):
    plans=[json.loads(run('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+q))[0] for _ in range(3)]
    item={'sql':q,'runs':plans,'median_ms':statistics.median(p['Execution Time'] for p in plans)}
    results[key]=item
    (OUT/(key+'.json')).write_text(json.dumps(item,indent=2)+'\n')
    print(key, item['median_ms'],flush=True)
def indexes(table):
    return json.loads(run(f"SELECT json_agg(t) FROM (SELECT indexrelname,pg_relation_size(indexrelid) bytes FROM pg_stat_user_indexes WHERE schemaname='lab02' AND relname='{table}' ORDER BY indexrelname) t"))
def sizes(table):
    return json.loads(run(f"SELECT json_build_object('heap',pg_relation_size('{table}'),'total',pg_total_relation_size('{table}'),'indexes',pg_indexes_size('{table}'))"))
# Refuse accidental reuse: fresh container or manually chosen fresh database required.
if sql("SELECT count(*) FROM pg_namespace WHERE nspname='lab02'")!='0':
    raise SystemExit('lab02 already exists. Use a fresh dedicated PG_CONTAINER; nothing changed.')
run('CREATE SCHEMA lab02;')
env={'postgres':sql('SELECT version()'),'python':platform.python_version(),'container':os.getenv('PG_CONTAINER','rpm-lab-postgres'),'settings':sql("SELECT name,setting,unit FROM pg_settings WHERE name IN ('shared_buffers','work_mem','max_parallel_workers_per_gather','random_page_cost')"),'anchor':sql('SELECT current_timestamp'),'service_rows_before':0}
(OUT/'environment.json').write_text(json.dumps(env,indent=2)+'\n')
run('''CREATE TABLE events(id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL,event_type VARCHAR(50) NOT NULL,payload JSONB,created_at TIMESTAMP NOT NULL);
CREATE TABLE anchor AS SELECT LOCALTIMESTAMP AS ts;''')
# Stable hash-like arithmetic avoids changing random samples between runs.
def event_data(start,end):
    return f"SELECT g,1+((g::bigint*7919)%100000),CASE WHEN g%10<4 THEN 'MESSAGE' WHEN g%10<7 THEN 'LOGIN' WHEN g%10<9 THEN 'PURCHASE' ELSE 'OTHER' END,'{{}}'::jsonb,(SELECT ts FROM anchor)-((g::bigint*104729)%31536000)*INTERVAL '1 second' FROM generate_series({start},{end}) g"
A={}; B={}
for n in (10000,100000,1000000,5000000):
    print('Events',n,flush=True)
    run('TRUNCATE events RESTART IDENTITY; INSERT INTO events '+event_data(1,n)+'; ANALYZE events;')
    A[str(n)]={'before':sizes('events')}
    user='SELECT * FROM events WHERE user_id=123'
    day="SELECT * FROM events WHERE created_at >= NOW()-INTERVAL '1 day'"
    wide="SELECT * FROM events WHERE created_at >= NOW()-INTERVAL '365 days'"
    ordered=user+' ORDER BY created_at DESC LIMIT 100'
    aggregate="SELECT event_type,COUNT(*) FROM events WHERE created_at>=NOW()-INTERVAL '30 days' GROUP BY event_type"
    for name,q in [('user',user),('day',day),('wide',wide),('aggregate',aggregate)]: measure(f'a-{n}-{name}-before',q)
    run('CREATE INDEX idx_events_user_id ON events(user_id);')
    measure(f'a-{n}-user-after',user)
    measure(f'a-{n}-sort-before',ordered)
    run('CREATE INDEX idx_events_created_at ON events(created_at);')
    for name,q in [('day',day),('wide',wide),('aggregate',aggregate)]: measure(f'a-{n}-{name}-after',q)
    run('CREATE INDEX idx_events_user_created ON events(user_id,created_at DESC);')
    measure(f'a-{n}-sort-after',ordered)
    A[str(n)].update(after=sizes('events'),indexes=indexes('events'))
    run('DROP INDEX idx_events_user_id,idx_events_created_at,idx_events_user_created;')
# Same populated starting state, same 100k batch; rollback keeps cardinality constant.
# EXPLAIN ANALYZE executes writes. Each repetition rolls back and VACUUM reclaims versions.
for stage in ('before','after'):
    if stage=='after': run('CREATE INDEX idx_events_user_id ON events(user_id); CREATE INDEX idx_events_created_at ON events(created_at); CREATE INDEX idx_events_user_created ON events(user_id,created_at DESC);')
    for op,q in [('insert','INSERT INTO events '+event_data(5000001,5100000)),('update','UPDATE events SET user_id=user_id+100000,created_at=created_at+INTERVAL \'1 second\' WHERE id<=100000')]:
        plans=[]
        for i in range(3):
            raw=run('BEGIN; EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+q+'; ROLLBACK;')
            plans.append(json.loads(raw)[0]); run('VACUUM (ANALYZE) events;')
        item={'sql':q,'runs':plans,'median_ms':statistics.median(p['Execution Time'] for p in plans)}
        results[f'a-write-{op}-{stage}']=item
        (OUT/f'a-write-{op}-{stage}.json').write_text(json.dumps(item,indent=2)+'\n')
# Exact service schema and indexes, isolated from service.orders.
root=Path(__file__).resolve().parents[2]/'lab-01'
run((root/'migrations/001_orders.sql').read_text().replace('CREATE SCHEMA service;','').replace('service.orders','lab02.orders'))
for n in (100000,1000000,5000000):
    print('Orders',n,flush=True)
    run(f"TRUNCATE orders RESTART IDENTITY; INSERT INTO orders(id,user_id,product_id,status,amount,created_at,updated_at) SELECT g,1+((g::bigint*7919)%10000),1+g%1000,CASE WHEN (g/10000)%10<4 THEN 'PAID' WHEN (g/10000)%10<7 THEN 'NEW' WHEN (g/10000)%10<9 THEN 'DELIVERED' ELSE 'CANCELLED' END,(g%100000)/100.0,(SELECT ts FROM anchor)-((g::bigint*104729)%31536000)*INTERVAL '1 second',(SELECT ts FROM anchor) FROM generate_series(1,{n}) g; ANALYZE orders;")
    # Q1/Q3 reuse actual endpoint SQL; Q2 is date-range diagnostic on its entity.
    queries={'q1':orders_query(123,limit=100).replace('service.orders','lab02.orders'),
             'q2':"SELECT id,amount,status,created_at FROM orders WHERE created_at>=NOW()-INTERVAL '30 days' AND created_at<NOW()",
             'q3':orders_query(123,'PAID',30,50).replace('service.orders','lab02.orders')}
    B[str(n)]={'before':sizes('orders')}
    for name,q in queries.items(): measure(f'b-{n}-{name}-baseline',q)
    run((root/'migrations/002_indexes.sql').read_text().replace('service.orders','lab02.orders'))
    run('VACUUM (ANALYZE) orders;')
    for name,q in queries.items(): measure(f'b-{n}-{name}-existing',q)
    run('CREATE INDEX idx_orders_created_cover ON orders(created_at) INCLUDE(id,amount,status); VACUUM (ANALYZE) orders;')
    for name,q in queries.items(): measure(f'b-{n}-{name}-optimized',q)
    B[str(n)].update(after=sizes('orders'),indexes=indexes('orders'))
    run('DROP INDEX idx_service_orders_user_created,idx_service_orders_paid_user_created,idx_orders_created_cover;')
(OUT/'sizes.json').write_text(json.dumps({'events':A,'orders':B},indent=2)+'\n')
(OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n')
print('DONE',flush=True)
