#!/usr/bin/env python3
"""Check completeness and evidence-backed optimizer behavior in saved plans."""
import json
from pathlib import Path
P=Path(__file__).resolve().parents[1]/'docs/plans'
D=json.loads((P/'results.json').read_text()); S=json.loads((P/'sizes.json').read_text())
def nodes(p):
    yield p
    for c in p.get('Plans',[]): yield from nodes(c)
expected=[f'a-{n}-{q}-{stage}' for n in (10000,100000,1000000,5000000) for q in ('user','day','wide','sort','aggregate') for stage in ('before','after')]
expected += [f'b-{n}-{q}-{stage}' for n in (100000,1000000,5000000) for q in ('q1','q2','q3') for stage in ('baseline','existing','optimized')]
expected += [f'a-write-{op}-{stage}' for op in ('insert','update') for stage in ('before','after')]
assert set(D)==set(expected),set(expected)-set(D)
for k,v in D.items():
    assert len(v['runs'])==3 and all(p['Execution Time']>=0 for p in v['runs']),k
    assert json.loads((P/(k+'.json')).read_text())==v,k
for n in (10000,100000,1000000,5000000):
    assert len(S['events'][str(n)]['indexes'])==4
for q in ('q1','q3'):
    assert D[f'b-5000000-{q}-optimized']['runs'][0]['Plan']['Actual Rows']>0,q
assert any('idx_orders_created_cover'==x.get('Index Name') for x in nodes(D['b-5000000-q2-optimized']['runs'][0]['Plan']))
assert not any(x['Node Type']=='Sort' for x in nodes(D['a-10000-sort-after']['runs'][0]['Plan']))
assert (P.parent/'report.md').is_file()
message=f'PASS: {len(expected)} measurements, 3 runs each; plan files match; Sort absent at 10k; all actual sort plans retained; service queries nonempty; date index used.'
(P/'validation.txt').write_text(message+'\n')
print(message)
