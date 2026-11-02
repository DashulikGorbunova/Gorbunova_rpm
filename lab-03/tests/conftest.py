import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from app.core.config import Settings
from app.core.security import passwords
from app.main import create_app
from app.models import UserRow, RoleRow, MenuRow

PASSWORD = 'test-password-123'

@pytest.fixture(scope='session')
def application():
    url = os.environ.get('TEST_DATABASE_URL')
    if not url or not make_url(url).database.endswith('_test'):
        raise RuntimeError('Set TEST_DATABASE_URL to a DEDICATED PostgreSQL database ending in _test')
    redis_url = os.environ.get('TEST_REDIS_URL','redis://127.0.0.1:16380/15')
    if not redis_url.endswith('/15'):
        raise RuntimeError('Dedicated Redis test DB 15 required')
    settings = Settings(database_url=url, redis_url=redis_url, debug=True,
                        jwt_secret='test-only-signing-key-with-more-than-32-bytes')
    return create_app(settings)

@pytest.fixture(autouse=True)
def clean_database(application):
    factory = application.state.session_factory
    with factory() as db:
        db.execute(text('TRUNCATE refresh_tokens,auth_sessions,deliveries,orders,menu,users RESTART IDENTITY CASCADE'))
        roles = {r.name:r.id for r in db.scalars(select(RoleRow))}
        assert set(roles) == {'student','cook','courier','admin'}, 'Run alembic upgrade head on test DB'
        hashed = passwords.hash(PASSWORD)
        for name,role in [('alice','student'),('bob','student'),('chef','cook'),
                          ('rider','courier'),('other-rider','courier'),('root','admin')]:
            db.add(UserRow(email=name+'@example.org',password_hash=hashed,role_id=roles[role]))
        db.add(MenuRow(name='Обед',price=250))
        db.commit()
    cache = application.state.redis
    keys = list(cache.scan_iter(match='sirius:rate:*'))
    if keys:
        cache.delete(*keys)
    yield

@pytest.fixture
def client(application):
    with TestClient(application) as client:
        yield client

@pytest.fixture
def login(client):
    def perform(name='alice'):
        response = client.post('/auth/login',json={'email':name+'@example.org','password':PASSWORD})
        assert response.status_code == 200, response.text
        return response.json()
    return perform

@pytest.fixture
def headers(login):
    def perform(name='alice'):
        return {'Authorization':'Bearer '+login(name)['access_token']}
    return perform
