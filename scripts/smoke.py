#!/usr/bin/env python3
"""Functional HTTP checks against the real database."""
import json,subprocess,sys,time
from urllib.request import urlopen
from urllib.error import HTTPError,URLError
from pathlib import Path
p=subprocess.Popen([sys.executable,str(Path(__file__).with_name('server.py'))])
def get(path):
    with urlopen('http://127.0.0.1:8080'+path,timeout=10) as r: return json.load(r)
try:
    for _ in range(30):
        if p.poll() is not None: raise RuntimeError('server exited')
        try:
            assert get('/health')=={'status':'ok'}
            break
        except URLError: time.sleep(.2)
    else: raise RuntimeError('server not ready')
    rows=get('/users/123/orders?status=PAID&days=30&limit=50')
    assert len(rows)==50, len(rows)
    assert all(r['status']=='PAID' for r in rows)
    keys=[(r['created_at'],r['id']) for r in rows]
    assert keys==sorted(keys,reverse=True)
    assert get('/users/999999999/orders')==[]
    for path,code in [('/users/123/orders?limit=0',400),('/users/123/orders?status=INVALID',400),('/missing',404),('/users/123/orders?days=abc',400)]:
        try: get(path)
        except HTTPError as e: assert e.code==code
        else: raise AssertionError(path)
    print('PASS: health, 50 filtered orders, deterministic ordering, empty result, 4 invalid requests')
finally:
    p.terminate(); p.wait(timeout=10)
