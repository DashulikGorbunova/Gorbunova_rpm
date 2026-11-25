from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from jose import jwt
from sqlalchemy import select
from app.models import UserRow, RefreshRow
from app.core.security import passwords
from tests.conftest import PASSWORD


def create_order(client, auth):
    response = client.post('/orders/create',json={'item_id':1,'quantity':2},headers=auth)
    assert response.status_code == 201, response.text
    return response.json()['order_id']


def test_no_token_401(client):
    r = client.post('/orders/create',json={'item_id':1,'quantity':1})
    assert r.status_code == 401
    assert r.headers['www-authenticate'] == 'Bearer'


def test_register_hashes_and_forces_student(client,application):
    r = client.post('/users/register',json={'email':'new@example.org','password':PASSWORD})
    assert r.status_code == 201
    assert r.json()['role'] == 'student' and 'password_hash' not in r.json()
    with application.state.session_factory() as db:
        user = db.scalar(select(UserRow).where(UserRow.email == 'new@example.org'))
        assert user.password_hash.startswith('$2b$') and user.password_hash != PASSWORD
        assert passwords.verify(PASSWORD,user.password_hash)
    assert client.post('/users/register',json={'email':'NEW@example.org','password':PASSWORD}).status_code == 409
    assert client.post('/users/register',json={'email':'evil@example.org','password':PASSWORD,'role':'admin'}).status_code == 422


def test_bcrypt_salt_and_byte_limit(client):
    assert passwords.hash(PASSWORD) != passwords.hash(PASSWORD)
    assert client.post('/users/register',json={'email':'long@example.org','password':'я'*40}).status_code == 422


def test_wrong_role_403_and_cook_success(client,headers):
    assert client.get('/kitchen/orders',headers=headers()).status_code == 403
    cook = headers('chef')
    assert client.get('/kitchen/orders',headers=cook).status_code == 200
    assert client.post('/orders/create',json={'item_id':1,'quantity':1},headers=cook).status_code == 403


def test_order_idor_denied_and_owner_can_cancel(client,headers):
    alice, bob = headers(), headers('bob')
    order_id = create_order(client,alice)
    assert client.post(f'/orders/{order_id}/cancel',headers=bob).status_code == 403
    assert client.get(f'/orders/{order_id}',headers=bob).status_code == 403
    assert client.get('/orders',headers=bob).json() == []
    assert client.get(f'/orders/{order_id}',headers=alice).json()['status'] == 'PENDING'
    assert client.post(f'/orders/{order_id}/cancel',headers=alice).status_code == 200
    assert client.post(f'/orders/{order_id}/cancel',headers=alice).status_code == 409
    assert client.get('/orders/999999',headers=alice).status_code == 404


def test_owner_cannot_be_spoofed(client,headers):
    alice = headers()
    for field in ('user_id','customer_id'):
        assert client.post('/orders/create',json={'item_id':1,'quantity':1,field:2},headers=alice).status_code == 422
    order_id = create_order(client,alice)
    assert client.get(f'/orders/{order_id}',headers=alice).json()['customer_id'] == 1


def test_menu_mutations_are_restricted(client,headers):
    item = {'name':'Суп','price':'125.50'}
    assert client.post('/menu',json=item,headers=headers()).status_code == 403
    assert client.post('/menu',json=item,headers=headers('chef')).status_code == 201
    assert client.patch('/menu/1',json=item,headers=headers('root')).status_code == 200
    assert client.get('/menu').status_code == 401


def test_users_idor_and_role_escalation(client,headers):
    alice = headers()
    assert client.get('/users/2',headers=alice).status_code == 403
    assert client.get('/users',headers=alice).status_code == 403
    assert client.patch('/users/1',json={'role':'admin'},headers=alice).status_code == 403
    assert 'password_hash' not in client.get('/users/me',headers=alice).json()
    admin = headers('root')
    assert client.patch('/users/2',json={'role':'cook'},headers=admin).status_code == 200
    assert client.get('/users',headers=admin).status_code == 200


def test_role_is_loaded_from_db_not_stale_jwt(client,headers):
    bob = headers('bob')
    admin = headers('root')
    assert client.get('/kitchen/orders',headers=bob).status_code == 403
    client.patch('/users/2',json={'role':'cook'},headers=admin)
    assert client.get('/kitchen/orders',headers=bob).status_code == 200


def test_delivery_owner_and_courier_isolation(client,headers):
    alice, bob, rider, other, admin = (headers(n) for n in ('alice','bob','rider','other-rider','root'))
    order_id = create_order(client,alice)
    r = client.post('/delivery',json={'order_id':order_id,'courier_id':4},headers=admin)
    assert r.status_code == 201, r.text
    delivery_id = r.json()['id']
    for auth in (bob,other):
        assert client.get(f'/delivery/{delivery_id}',headers=auth).status_code == 403
        assert client.get('/delivery',headers=auth).json() == []
        assert client.post(f'/delivery/{delivery_id}/complete',headers=auth).status_code == 403
    assert client.get(f'/delivery/{delivery_id}',headers=alice).status_code == 200
    assert len(client.get('/delivery',headers=rider).json()) == 1
    assert client.post(f'/delivery/{delivery_id}/complete',headers=rider).json()['status'] == 'DELIVERED'


def test_login_rate_limit_429_shared_oauth_bucket(client,application):
    for _ in range(5):
        r = client.post('/auth/login',json={'email':'unknown@example.org','password':'wrong'})
        assert r.status_code == 401
    r = client.post('/auth/token',data={'username':'unknown@example.org','password':'wrong'})
    assert r.status_code == 429 and int(r.headers['retry-after']) > 0
    keys = list(application.state.redis.scan_iter(match='sirius:rate:login:*'))
    assert len(keys) == 1 and 0 < application.state.redis.ttl(keys[0]) <= 60


def test_unknown_account_and_wrong_password_same_response(client):
    a = client.post('/auth/login',json={'email':'unknown@example.org','password':'wrong'})
    b = client.post('/auth/login',json={'email':'alice@example.org','password':'wrong'})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_refresh_rotation_replay_revokes_access_and_new_refresh(client,login,application):
    original = login()
    rotated = client.post('/auth/refresh',json={'refresh_token':original['refresh_token']})
    assert rotated.status_code == 200
    new = rotated.json()
    assert new['refresh_token'] != original['refresh_token']
    auth = {'Authorization':'Bearer '+new['access_token']}
    assert client.get('/users/me',headers=auth).status_code == 200
    assert client.post('/auth/refresh',json={'refresh_token':original['refresh_token']}).status_code == 401
    assert client.post('/auth/refresh',json={'refresh_token':new['refresh_token']}).status_code == 401
    assert client.get('/users/me',headers=auth).status_code == 401
    with application.state.session_factory() as db:
        rows = list(db.scalars(select(RefreshRow)))
        assert len(rows) == 2 and all(len(r.token_hash) == 64 for r in rows)
        assert all(r.token_hash not in (original['refresh_token'],new['refresh_token']) for r in rows)


def test_concurrent_refresh_replay_revokes_family(client,login):
    pair = login()
    payload = {'refresh_token':pair['refresh_token']}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _:client.post('/auth/refresh',json=payload),range(2)))
    assert sorted(r.status_code for r in responses) == [200,401]
    winner = next(r.json() for r in responses if r.status_code == 200)
    assert client.get('/users/me',headers={'Authorization':'Bearer '+winner['access_token']}).status_code == 401


def test_replay_does_not_revoke_independent_session(client,login):
    first, independent = login(),login()
    client.post('/auth/refresh',json={'refresh_token':first['refresh_token']})
    client.post('/auth/refresh',json={'refresh_token':first['refresh_token']})
    assert client.get('/users/me',headers={'Authorization':'Bearer '+independent['access_token']}).status_code == 200


def test_logout_revokes_both_token_types(client,login):
    pair = login()
    auth = {'Authorization':'Bearer '+pair['access_token']}
    assert client.post('/auth/logout',headers=auth).status_code == 200
    assert client.get('/users/me',headers=auth).status_code == 401
    assert client.post('/auth/refresh',json={'refresh_token':pair['refresh_token']}).status_code == 401


def test_blocked_user_loses_session(client,login,headers):
    pair = login()
    admin = headers('root')
    assert client.patch('/users/1',json={'is_blocked':True},headers=admin).status_code == 200
    assert client.get('/users/me',headers={'Authorization':'Bearer '+pair['access_token']}).status_code == 401
    assert client.post('/auth/refresh',json={'refresh_token':pair['refresh_token']}).status_code == 401
    assert client.post('/auth/login',json={'email':'alice@example.org','password':PASSWORD}).status_code == 401
    client.patch('/users/1',json={'is_blocked':False},headers=admin)
    assert client.get('/users/me',headers={'Authorization':'Bearer '+pair['access_token']}).status_code == 401


def test_refresh_cannot_be_used_as_access_and_reverse(client,login):
    pair = login()
    assert client.get('/users/me',headers={'Authorization':'Bearer '+pair['refresh_token']}).status_code == 401
    assert client.post('/auth/refresh',json={'refresh_token':pair['access_token']}).status_code == 401


def test_expired_tampered_wrong_issuer_and_audience(client,login,application):
    pair = login()
    settings = application.state.settings
    secret = settings.jwt_secret.get_secret_value()
    claims = jwt.get_unverified_claims(pair['access_token'])
    for change in ({'exp':int((datetime.now(timezone.utc)-timedelta(seconds=10)).timestamp())},
                   {'iss':'wrong'},{'aud':'wrong'},{'sub':'not-a-number'},{'sid':'invalid'}):
        token = jwt.encode({**claims,**change},secret,algorithm='HS256')
        assert client.get('/users/me',headers={'Authorization':'Bearer '+token}).status_code == 401
    token = jwt.encode(claims,'another-key-with-at-least-32-bytes',algorithm='HS256')
    assert client.get('/users/me',headers={'Authorization':'Bearer '+token}).status_code == 401


def test_swagger_oauth_flow(client):
    r = client.post('/auth/token',data={'username':'alice@example.org','password':PASSWORD})
    assert r.status_code == 200
    assert client.get('/users/me',headers={'Authorization':'Bearer '+r.json()['access_token']}).status_code == 200
    spec = client.get('/openapi.json').json()
    assert spec['components']['securitySchemes']['OAuth2PasswordBearer']['flows']['password']['tokenUrl'] == '/auth/token'


def test_production_hides_docs_and_cors_allowlist(application):
    from app.main import create_app
    from fastapi.testclient import TestClient
    production = create_app(application.state.settings.model_copy(update={'debug':False}))
    with TestClient(production) as c:
        for path in ('/docs','/redoc','/openapi.json'):
            assert c.get(path).status_code == 404
        allowed = c.options('/orders/create',headers={'Origin':'http://localhost:3000','Access-Control-Request-Method':'POST'})
        denied = c.options('/orders/create',headers={'Origin':'https://evil.example','Access-Control-Request-Method':'POST'})
        assert allowed.status_code == 200
        assert denied.status_code == 400 and 'access-control-allow-origin' not in denied.headers


def test_redis_failure_is_closed(client,application):
    from redis.exceptions import ConnectionError
    cache = application.state.redis
    class Unavailable:
        def eval(self,*args):
            raise ConnectionError('test outage')
    try:
        application.state.redis = Unavailable()
        assert client.post('/auth/login',json={'email':'alice@example.org','password':PASSWORD}).status_code == 503
    finally:
        application.state.redis = cache
