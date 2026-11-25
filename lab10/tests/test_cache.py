import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from decimal import Decimal
from fastapi.testclient import TestClient
from redis import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry
from sqlalchemy import event, text
from app.main import create_app
from app.modules.menu.cache import MenuCache
from app.modules.menu.repository import MenuRepository

@contextmanager
def menu_queries(application):
    queries=[]
    engine=application.state.session_factory.kw['bind']
    def record(conn,cursor,statement,parameters,context,executemany):
        if re.search(r'\bFROM menu\b',statement):
            queries.append(statement)
    event.listen(engine,'before_cursor_execute',record)
    try:
        yield queries
    finally:
        event.remove(engine,'before_cursor_execute',record)

def cache(application,**settings):
    return MenuCache(application.state.menu_redis,application.state.settings.model_copy(update=settings))

def test_miss_hit_and_json_decimal(client,headers,application):
    auth=headers()
    application.state.menu_redis.delete('menu:all')
    with menu_queries(application) as queries:
        first=client.get('/menu/items',headers=auth)
        second=client.get('/menu/items',headers=auth)
    assert first.status_code==200 and first.json()==second.json()
    assert first.json()[0]['price']=='250.00'
    assert len(queries)==1
    assert 0 < application.state.menu_redis.ttl('menu:all') <= 300
    assert isinstance(json.loads(application.state.menu_redis.get('menu:all')),list)
    assert client.get('/menu/items').status_code==401  # A hit never bypasses authentication.


def test_empty_menu_is_cached(client,headers,application):
    auth=headers()
    with application.state.session_factory() as db:
        db.execute(text('DELETE FROM menu'));db.commit()
    application.state.menu_redis.delete('menu:all')
    with menu_queries(application) as queries:
        for _ in range(2):
            assert client.get('/menu/items',headers=auth).json()==[]
    assert len(queries)==1 and application.state.menu_redis.get('menu:all')=='[]'


def test_create_invalidates_all_and_category_after_commit(client,headers,application):
    auth=headers('chef')
    client.get('/menu/categories/1',headers=auth)
    assert application.state.menu_redis.exists('menu:all','menu:category:1')==2
    result=client.post('/menu/items',json={'name':'Суп','price':'100.01'},headers=auth)
    assert result.status_code==201
    assert application.state.menu_redis.exists('menu:all','menu:category:1')==0
    assert any(i['name']=='Суп' for i in client.get('/menu/items',headers=auth).json())
    assert any(i['name']=='Суп' for i in client.get('/menu/categories/1',headers=auth).json())


def test_move_invalidates_old_and_new_category(client,headers,application):
    auth=headers('chef')
    for category in (1,2,3):
        assert client.get(f'/menu/categories/{category}',headers=auth).status_code==200
    r=client.patch('/menu/items/1',json={'name':'Обед новый','price':'125.50','category_id':2},headers=auth)
    assert r.status_code==200 and r.json()['category_name']=='Супы'
    redis=application.state.menu_redis
    assert redis.exists('menu:all','menu:category:1','menu:category:2')==0
    assert redis.exists('menu:category:3')==1
    assert client.get('/menu/categories/1',headers=auth).json()==[]
    assert client.get('/menu/categories/2',headers=auth).json()[0]['price']=='125.50'


def test_invalid_update_does_not_invalidate_or_change_data(client,headers,application):
    auth=headers('chef')
    old=application.state.menu_redis.get('menu:all')
    assert client.patch('/menu/items/1',json={'name':'Wrong','price':'1','category_id':9999},headers=auth).status_code==404
    assert application.state.menu_redis.get('menu:all')==old
    assert client.get('/menu/items',headers=auth).json()[0]['name']=='Обед'


def test_category_ttl_and_missing_category(client,headers,application):
    auth=headers()
    assert client.get('/menu/categories/2',headers=auth).json()==[]
    assert 0 < application.state.menu_redis.ttl('menu:category:2') <= 600
    assert client.get('/menu/categories/9999',headers=auth).status_code==404
    assert not application.state.menu_redis.exists('menu:category:9999')


def test_ttl_expiration_loads_database_again(application):
    c=cache(application,menu_ttl=1)
    with application.state.session_factory() as db:
        repository=MenuRepository(db,c)
        with menu_queries(application) as queries:
            repository.list()
            assert c.redis.ttl('menu:all') <= 1
            time.sleep(1.1)
            repository.list()
        assert len(queries)==2


def test_corrupt_cache_recovers(client,headers,application):
    auth=headers()
    for payload in ('not-json','{}','[{"price":"nan"}]'):
        application.state.menu_redis.set('menu:all',payload,ex=300)
        r=client.get('/menu/items',headers=auth)
        assert r.status_code==200 and r.json()[0]['name']=='Обед'


def test_cache_redis_failure_reads_and_writes_database(client,headers,application):
    auth=headers('chef')
    original=application.state.menu_redis
    broken=Redis(host='127.0.0.1',port=1,socket_connect_timeout=.05,socket_timeout=.05,
                 retry=Retry(NoBackoff(),0))
    application.state.menu_redis=broken
    try:
        assert client.get('/menu/items',headers=auth).status_code==200
        assert client.post('/menu/items',json={'name':'Offline','price':'12.30'},headers=auth).status_code==201
        assert any(i['name']=='Offline' for i in client.get('/menu/items',headers=auth).json())
    finally:
        application.state.menu_redis=original
        broken.close()
        # Simulate Redis recovery: bounded stale cache is an explicitly documented limit.
        cache(application).invalidate([1])


def test_distributed_single_flight(application):
    calls=[]
    start=threading.Barrier(20)
    c1,c2=cache(application),cache(application)
    def read(i):
        start.wait(timeout=10)
        with application.state.session_factory() as db:
            repository=MenuRepository(db)
            def loader():
                calls.append(i)
                time.sleep(.05)
                return repository.list()
            return (c1 if i%2 else c2).get_or_load('menu:all',300,loader)
    with ThreadPoolExecutor(max_workers=20) as pool:
        values=list(pool.map(read,range(20)))
    assert len(calls)==1 and all(v==values[0] for v in values)
    assert not c1.redis.exists('menu:all:lock')


def test_invalidation_prevents_stale_loader_publication(application):
    loaded,release=threading.Event(),threading.Event()
    c=cache(application)
    def slow_read():
        with application.state.session_factory() as db:
            repository=MenuRepository(db)
            def loader():
                old=repository.list()
                loaded.set()
                assert release.wait(5)
                return old
            return c.get_or_load('menu:all',300,loader)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(slow_read)
        assert loaded.wait(5)
        try:
            with application.state.session_factory() as db:
                MenuRepository(db,c).update(1,'Changed',Decimal('15.01'))
        finally:
            release.set()
        assert future.result()[0].name=='Обед'  # Reader overlapped the write.
    assert c.redis.get('menu:all') is None      # Old value cannot be published.
    with application.state.session_factory() as db:
        assert MenuRepository(db,c).list()[0].name=='Changed'


def test_wait_is_bounded_and_does_not_publish_without_lock(application):
    c=cache(application,cache_wait_seconds=.05)
    c.redis.set('menu:all:lock','another-owner',ex=10)
    before=time.monotonic()
    with application.state.session_factory() as db:
        assert MenuRepository(db,c).list()
    assert time.monotonic()-before < 1
    assert c.redis.get('menu:all') is None
    assert c.redis.get('menu:all:lock')=='another-owner'


def test_lease_owner_cannot_delete_replacement_lock(application):
    c=cache(application)
    def loader():
        c.redis.set('menu:all:lock','replacement-owner',ex=10)
        with application.state.session_factory() as db:
            return MenuRepository(db).list()
    assert c.get_or_load('menu:all',300,loader)
    assert c.redis.get('menu:all') is None
    assert c.redis.get('menu:all:lock')=='replacement-owner'


def test_warmup_and_disabled_baseline(application):
    settings=application.state.settings
    with TestClient(create_app(settings)) as c:
        assert c.app.state.menu_redis.get('menu:all') is not None
    application.state.menu_redis.delete('menu:all')
    disabled=create_app(settings.model_copy(update={'cache_enabled':False}))
    with TestClient(disabled) as c:
        assert c.app.state.menu_redis.get('menu:all') is None
        with disabled.state.session_factory() as db:
            repository=MenuRepository(db,MenuCache(disabled.state.menu_redis,disabled.state.settings))
            with menu_queries(disabled) as queries:
                repository.list();repository.list()
            assert len(queries)==2
        assert c.app.state.menu_redis.get('menu:all') is None


def test_publish_failure_does_not_repeat_database_read(application,monkeypatch):
    from redis.exceptions import ConnectionError
    from app.modules.menu.cache import PUBLISH
    c=cache(application)
    original=c.redis.eval
    def fail_publish(script,*args,**kwargs):
        if script==PUBLISH:
            raise ConnectionError('publish outage')
        return original(script,*args,**kwargs)
    monkeypatch.setattr(c.redis,'eval',fail_publish)
    with application.state.session_factory() as db:
        with menu_queries(application) as queries:
            assert MenuRepository(db,c).list()
    assert len(queries)==1 and c.redis.get('menu:all') is None


def test_read_connections_are_released_before_response(client,headers,application):
    from app.core.dependencies import get_current_user
    from app.core.jwt import JwtCodec
    from app.core.security import passwords,DUMMY_HASH
    from app.modules.auth.service import AuthService
    from app.modules.auth.repository import AuthRepository
    auth=headers()
    factory=application.state.session_factory
    with factory() as db:
        svc=AuthService(AuthRepository(db),passwords,application.state.codec,DUMMY_HASH)
        user=get_current_user(auth['Authorization'][7:],svc,db)
        assert user.id==1 and not db.in_transaction()
        repository=MenuRepository(db)
        assert repository.list()
        assert not db.in_transaction()
    assert factory.kw['bind'].pool.checkedout()==0
