import os
import subprocess
import sys
import pytest
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer
from sqlalchemy import select
from fastapi.testclient import TestClient
@pytest.fixture
def environment(monkeypatch):
    with PostgresContainer('postgres:17-bookworm') as pg, RedisContainer('redis:7.4-bookworm') as redis:
        url=pg.get_connection_url()
        redis_url=f'redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0'
        for key,value in dict(DATABASE_URL=url,REDIS_URL=redis_url,JWT_SECRET='test-only-secret-012345678901234567890123456789',NOTIFICATION_MODE='sync',SIMULATED_PDF_SECONDS='0',SIMULATED_EMAIL_SECONDS='0',SIMULATED_SMS_SECONDS='0',CACHE_WARMUP='false',OTEL_EXPORTER_OTLP_ENDPOINT='',SENTRY_DSN='').items():
            monkeypatch.setenv(key,value)
        subprocess.run([sys.executable,'-m','alembic','upgrade','head'],check=True)
        from app.main import create_app
        from app.models import RoleRow,UserRow,CategoryRow,MenuRow
        from app.core.security import passwords
        app=create_app()
        with app.state.session_factory() as db:
            role=db.scalar(select(RoleRow).where(RoleRow.name=='student'))
            category=db.scalar(select(CategoryRow))
            if category is None:
                category=CategoryRow(name='Test');db.add(category);db.flush()
            user=UserRow(email='student@example.org',password_hash=passwords.hash('test-password-123'),role_id=role.id)
            item=MenuRow(name='Сырники',price=150,category_id=category.id)
            db.add_all([user,item]);db.commit()
            uid,iid=user.id,item.id
        with TestClient(app) as client:
            response=client.post('/auth/login',json={'email':'student@example.org','password':'test-password-123'})
            assert response.status_code==200,response.text
            yield client,app,uid,iid,{'Authorization':'Bearer '+response.json()['access_token'],'X-Correlation-ID':'lab10-test'}
