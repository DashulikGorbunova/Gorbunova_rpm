#!/usr/bin/env python3
"""Run migrations and security tests on a dedicated sibling *_test database."""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy.engine import make_url
from alembic.config import Config
from alembic import command
from app.core.config import Settings
import pytest

root = Path(__file__).resolve().parents[1]
os.chdir(root)
settings = Settings()
base = make_url(settings.database_url)
url = os.environ.get('TEST_DATABASE_URL')
if not url:
    name = base.database if base.database.endswith('_test') else base.database+'_test'
    url = base.set(database=name).render_as_string(hide_password=False)
if not make_url(url).database.endswith('_test'):
    raise SystemExit('Refusing tests on a database without _test suffix')
os.environ['DATABASE_URL'] = os.environ['TEST_DATABASE_URL'] = url
os.environ.setdefault('TEST_REDIS_URL',settings.redis_url.rsplit('/',1)[0]+'/15')
os.environ.setdefault('CELERY_BROKER_URL',settings.redis_url.rsplit('/',1)[0]+'/13')
os.environ.setdefault('CELERY_RESULT_BACKEND',settings.redis_url.rsplit('/',1)[0]+'/14')
config = Config(str(root/'alembic.ini'))
command.upgrade(config,'head')
command.upgrade(config,'head')
command.check(config)
raise SystemExit(pytest.main(['-q','--junitxml=docs/test-results.xml']))
