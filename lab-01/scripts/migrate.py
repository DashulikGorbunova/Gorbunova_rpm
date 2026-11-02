#!/usr/bin/env python3
from pathlib import Path
import sys
from db import sql

def migrate(target=2):
    sql('CREATE TABLE IF NOT EXISTS public.schema_migrations(version INTEGER PRIMARY KEY);')
    root=Path(__file__).resolve().parents[1]
    for path in sorted((root/'migrations').glob('*.sql')):
        version=int(path.name.split('_')[0])
        if version>target: continue
        if sql(f'SELECT count(*) FROM public.schema_migrations WHERE version={version}')=='0':
            sql('BEGIN;'+path.read_text()+f'INSERT INTO public.schema_migrations VALUES({version}); COMMIT;')
            print('Applied',path.name)
if __name__=='__main__': migrate(int(sys.argv[1]) if len(sys.argv)>1 else 2)
