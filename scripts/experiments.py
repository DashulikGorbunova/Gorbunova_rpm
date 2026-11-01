#!/usr/bin/env python3
"""Run isolated lab experiments; no Python packages required. Replaces lab schema."""
import json, os, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CONTAINER=os.getenv('PG_CONTAINER','rpm-lab-postgres')
OUT=ROOT/'docs/plans'; OUT.mkdir(parents=True,exist_ok=True)
def sql(s):
    return subprocess.check_output(['docker','--host=unix:///var/run/docker.sock','exec','-i',CONTAINER,'psql','-X','-qAt','-v','ON_ERROR_STOP=1','-U','postgres'],input='SET search_path TO lab;\n'+s,text=True)
results={}
def measure(name,q):
    data=json.loads(sql('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+q))[0]
    (OUT/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    results[name]={'query':q,**data}
    print(name, data['Execution Time'],flush=True)
def drop_indexes():
    sql("DO $$ DECLARE x record; BEGIN FOR x IN SELECT indexname FROM pg_indexes WHERE schemaname='lab' AND tablename='orders' AND indexname<>'orders_pkey' LOOP EXECUTE format('DROP INDEX lab.%I',x.indexname); END LOOP; END $$;")
def idx(name,cols): sql(f'CREATE INDEX {name} ON orders {cols}; ANALYZE orders;')
def main():
    sql((ROOT/'sql/01-seed.sql').read_text())
    q='SELECT * FROM orders WHERE user_id=123'
    (OUT/'03-explain.txt').write_text(sql('EXPLAIN '+q))
    measure('04-user-before',q)
    measure('05-all','SELECT * FROM orders')
    measure('05-amount','SELECT * FROM orders WHERE amount>0')
    idx('idx_orders_user_id','(user_id)'); measure('06-user-after',q)
    idx('idx_orders_status','(status)')
    (OUT/'08-distribution.txt').write_text(sql('SELECT status,count(*),round(count(*)*100.0/(SELECT count(*) FROM orders),2) AS percent FROM orders GROUP BY status ORDER BY status;'))
    for status in ['NEW','PAID','DELIVERED','CANCELLED']:
        measure('07-status-'+status,f"SELECT * FROM orders WHERE status='{status}'")
    recent="SELECT * FROM orders WHERE created_at>NOW()-INTERVAL '7 days'"
    measure('09-range-before',recent); idx('idx_orders_created_at','(created_at)'); measure('09-range-after',recent)
    for period in ['1 day','1 month','1 year']:
        measure('09-range-'+period.replace(' ','-'),f"SELECT * FROM orders WHERE created_at>NOW()-INTERVAL '{period}'")
    measure('10-bitmap',"SELECT * FROM orders WHERE created_at>NOW()-INTERVAL '1 month'")
    combined=q+" AND status='PAID'"
    measure('11-separate',combined); idx('idx_orders_user_status','(user_id,status)'); measure('12-composite',combined)
    # Isolate column-order effects from competing secondary indexes.
    queries=[q,q+" AND created_at>NOW()-INTERVAL '30 days'","SELECT * FROM orders WHERE created_at>NOW()-INTERVAL '30 days'"]
    for name,cols in [('user_created','(user_id,created_at)'),('created_user','(created_at,user_id)')]:
        drop_indexes(); idx('idx_orders_'+name,cols)
        for i,query in enumerate(queries,1): measure(f'13-{name}-{i}',query)
    drop_indexes(); idx('idx_orders_user_id','(user_id)')
    sorted_q=q+' ORDER BY created_at DESC'
    measure('14-sort-before',sorted_q)
    idx('idx_orders_user_created_at_desc','(user_id,created_at DESC)'); measure('14-sort-after',sorted_q)
    drop_indexes(); idx('idx_orders_user_id','(user_id)'); measure('15-pagination-before',sorted_q+' LIMIT 20')
    idx('idx_orders_user_created_at_desc','(user_id,created_at DESC)'); measure('15-pagination-after',sorted_q+' LIMIT 20')
    cover='SELECT id,user_id FROM orders WHERE user_id=123'
    measure('16-cover-before',cover)
    idx('idx_orders_user_id_include','(user_id) INCLUDE(id,status,created_at)')
    sql('VACUUM (ANALYZE) orders;'); measure('16-cover-after',cover)
    # Separate sparse distribution for partial index experiment (1% NEW).
    drop_indexes()
    sql("UPDATE orders SET status='PAID' WHERE status='NEW'; UPDATE orders SET status='NEW' WHERE id%100=0; VACUUM (ANALYZE) orders;")
    partial="SELECT * FROM orders WHERE status='NEW' ORDER BY created_at"
    idx('idx_orders_status','(status)'); measure('17-partial-before',partial)
    sql('DROP INDEX idx_orders_status;'); idx('idx_orders_new',"(created_at) WHERE status='NEW'"); measure('17-partial-after',partial)
    (OUT/'17-index-size.txt').write_text(sql("SELECT indexname,pg_size_pretty(pg_relation_size(indexname::regclass)) FROM pg_indexes WHERE schemaname='lab' AND tablename='orders';"))
    sql('CREATE INDEX idx_users_email ON users(email);')
    u="SELECT * FROM users WHERE LOWER(email)='test@example.com'"
    measure('18-expression-before',u)
    sql('CREATE INDEX idx_users_lower_email ON users(LOWER(email)); ANALYZE users;'); measure('18-expression-after',u)
    # Equal deterministic batches into initially empty tables; primary key in both.
    sql('CREATE TABLE insert_plain (LIKE orders INCLUDING DEFAULTS INCLUDING CONSTRAINTS); ALTER TABLE insert_plain ADD PRIMARY KEY(id); CREATE TABLE insert_indexed (LIKE orders INCLUDING DEFAULTS INCLUDING CONSTRAINTS); ALTER TABLE insert_indexed ADD PRIMARY KEY(id); CREATE INDEX ins_user ON insert_indexed(user_id); CREATE INDEX ins_status ON insert_indexed(status); CREATE INDEX ins_created ON insert_indexed(created_at);')
    for table in ['insert_plain','insert_indexed']:
        measure('19-'+table,f"INSERT INTO {table} SELECT g,g%100000,g%10000,'PAID',100,TIMESTAMP '2026-01-01',TIMESTAMP '2026-01-01' FROM generate_series(1,100000) g")
    # Final exercise: realistic busy user cohort so LIMIT 50 is exercised.
    drop_indexes()
    sql("UPDATE orders SET user_id=123,status='PAID',created_at=NOW()-(id%30)*INTERVAL '1 day' WHERE id%1000=0; VACUUM (ANALYZE) orders;")
    final="SELECT id,amount,status,created_at FROM orders WHERE user_id=123 AND status='PAID' AND created_at>=NOW()-INTERVAL '30 days' ORDER BY created_at DESC LIMIT 50"
    measure('21-final-before',final)
    idx('idx_orders_paid_user_created',"(user_id,created_at DESC) INCLUDE(id,amount,status) WHERE status='PAID'")
    sql('VACUUM (ANALYZE) orders;'); measure('21-final-after',final)
    (OUT/'20-usage.txt').write_text(sql('SELECT pg_stat_clear_snapshot(); SELECT schemaname,relname,indexrelname,idx_scan FROM pg_stat_user_indexes WHERE schemaname=\'lab\' ORDER BY idx_scan;'))
    (OUT/'environment.txt').write_text(sql('SELECT version(); SHOW shared_buffers; SHOW work_mem; SHOW random_page_cost; SHOW max_parallel_workers_per_gather; SELECT count(*) FROM orders;'))
    (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__': main()
