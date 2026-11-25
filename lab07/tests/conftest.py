import os
import pytest
from redis import Redis
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
    redis_url = os.environ.get('TEST_REDIS_URL','redis://127.0.0.1:16383/15')
    if not redis_url.endswith('/15'):
        raise RuntimeError('Dedicated Redis test DB 15 required')
    settings = Settings(database_url=url, redis_url=redis_url, debug=True,
                        jwt_secret='test-only-signing-key-with-more-than-32-bytes')
    from delivery_service.server import build_server
    settings=settings.model_copy(update={'delivery_grpc_bind':'127.0.0.1:0','delivery_poll_seconds':.03})
    server,port=build_server(settings)
    server.start()
    settings=settings.model_copy(update={'delivery_grpc_target':f'127.0.0.1:{port}'})
    yield create_app(settings)
    server.stop(0).wait()


@pytest.fixture(autouse=True)
def clean_database(application):
    factory = application.state.session_factory
    with factory() as db:
        db.execute(text('TRUNCATE maintenance_runs,refresh_tokens,auth_sessions,deliveries,orders,menu,users RESTART IDENTITY CASCADE'))
        roles = {r.name:r.id for r in db.scalars(select(RoleRow))}
        assert set(roles) == {'student','cook','courier','admin'}, 'Run alembic upgrade head on test DB'
        hashed = passwords.hash(PASSWORD)
        for name,role in [('alice','student'),('bob','student'),('chef','cook'),
                          ('rider','courier'),('other-rider','courier'),('root','admin')]:
            db.add(UserRow(email=name+'@example.org',password_hash=hashed,role_id=roles[role]))
        db.add(MenuRow(name='Обед',price=250))
        db.commit()
    # Fixture maintenance uses a fresh connection and a larger timeout; application
    # rate-limiter/cache deadlines remain unchanged and are tested separately.
    cache = Redis.from_url(application.state.settings.redis_url,socket_timeout=10,socket_connect_timeout=10)
    keys = list(cache.scan_iter(match='sirius:rate:*'))
    if keys:
        cache.delete(*keys)
    menu_keys = list(cache.scan_iter(match='menu:*'))
    if menu_keys:
        cache.delete(*menu_keys)
    for url in (application.state.settings.broker_url,application.state.settings.result_backend):
        if not url.endswith(('/13','/14')):
            raise RuntimeError('Dedicated Celery Redis DBs 13 and 14 required')
        backend=Redis.from_url(url)
        task_keys=list(backend.scan_iter(match='sirius06:*'))
        if task_keys:
            backend.delete(*task_keys)
        backend.close()
    cache.close()
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
