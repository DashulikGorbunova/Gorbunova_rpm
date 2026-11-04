#!/usr/bin/env python3
"""Generate local credentials once without writing them to stdout."""
from pathlib import Path
import secrets

path = Path(__file__).resolve().parents[1]/'.env'
if path.exists():
    raise SystemExit('.env already exists; left unchanged')
password = secrets.token_hex(24)
path.write_text(
    f'POSTGRES_PASSWORD={password}\nJWT_SECRET={secrets.token_hex(48)}\n'
    f'DATABASE_URL=postgresql+psycopg2://sirius:{password}@127.0.0.1:15436/sirius\n'
    'REDIS_URL=redis://127.0.0.1:16383/0\nDEBUG=false\n'
    f'FLOWER_BASIC_AUTH=monitor:{secrets.token_hex(24)}\n'
    'ALLOWED_ORIGINS=["http://localhost:3000"]\n')
path.chmod(0o600)
print('Created private .env; enable DEBUG=true locally for Swagger')
