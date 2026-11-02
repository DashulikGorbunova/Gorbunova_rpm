#!/usr/bin/env python3
"""Educational read-only order service, Python standard library + Docker psql."""
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
from db import sql

STATUSES={'NEW','PAID','DELIVERED','CANCELLED'}

def orders_query(user, status=None, days=None, limit=20):
    # Only validated integers and a strict status allowlist reach SQL.
    user=int(user); limit=int(limit)
    if user<0 or not 1<=limit<=100: raise ValueError('user >= 0, limit 1..100')
    predicate=f'user_id={user}'
    if status is not None:
        if status not in STATUSES: raise ValueError('invalid status')
        predicate+=f" AND status='{status}'"
    if days is not None:
        days=int(days)
        if not 1<=days<=730: raise ValueError('days 1..730')
        predicate+=f" AND created_at>=NOW()-{days}*INTERVAL '1 day'"
    return f'SELECT id,amount,status,created_at FROM service.orders WHERE {predicate} ORDER BY created_at DESC,id DESC LIMIT {limit}'

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=urlparse(self.path)
        try:
            if path.path=='/health':
                sql('SELECT 1 FROM service.orders LIMIT 1'); return self.respond(200,{'status':'ok'})
            match=re.fullmatch(r'/users/(\d+)/orders',path.path)
            if not match: return self.respond(404,{'error':'not found'})
            params=parse_qs(path.query)
            if set(params)-{'status','days','limit'}: raise ValueError('unknown parameter')
            get=lambda key,default=None: params.get(key,[default])[0]
            query=orders_query(match[1],get('status'),get('days'),get('limit',20))
            result=json.loads(sql(f"SELECT COALESCE(json_agg(t),'[]'::json) FROM ({query}) t"))
            self.respond(200,result)
        except ValueError as exc: self.respond(400,{'error':str(exc)})
        except Exception: self.respond(503,{'error':'database unavailable'})
    def respond(self,status,body):
        data=json.dumps(body).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)

if __name__=='__main__':
    ThreadingHTTPServer(('127.0.0.1',8080),Handler).serve_forever()
