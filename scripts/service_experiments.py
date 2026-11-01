#!/usr/bin/env python3
import json
from experiments import measure,results,OUT
from db import sql
from migrate import migrate
from server import orders_query
migrate(1)
if sql('SELECT count(*) FROM service.orders')!='0':
    raise SystemExit('Service measurements require empty service.orders; use a fresh dedicated database')
sql('INSERT INTO service.orders SELECT * FROM lab.orders; SELECT setval(pg_get_serial_sequence(\'service.orders\',\'id\'),(SELECT max(id) FROM service.orders)); ANALYZE service.orders;')
queries={
 'query1':'SELECT * FROM service.orders WHERE user_id=123',
 'query2':"SELECT * FROM service.orders WHERE user_id=123 AND status='PAID'",
 'query3':orders_query(123,'PAID',30,50)}
for name,q in queries.items():
    (OUT/('service-'+name+'-explain.txt')).write_text(sql('EXPLAIN '+q))
    measure('service-'+name+'-before',q)
(OUT/'service-indexes-before.txt').write_text(sql("SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='service';"))
migrate()
migrate() # repeatability check
sql('VACUUM (ANALYZE) service.orders;')
for name,q in queries.items(): measure('service-'+name+'-after',q)
(OUT/'service-indexes-after.txt').write_text(sql("SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='service'; SELECT pg_stat_clear_snapshot(); SELECT indexrelname,idx_scan FROM pg_stat_user_indexes WHERE schemaname='service' ORDER BY idx_scan;"))
(OUT/'service-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
