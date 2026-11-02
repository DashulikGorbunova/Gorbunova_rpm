"""Infrastructure only: distributed single-flight with versioned publication."""
import json
import logging
import time
import uuid
from decimal import Decimal
from redis.exceptions import RedisError
from app.domain.entities import MenuItem

log = logging.getLogger(__name__)
# A loader may publish only while it still owns its lease and no write happened.
PUBLISH = """
if redis.call('GET',KEYS[2]) ~= ARGV[1] then return 0 end
local generation = redis.call('GET',KEYS[3]) or '0'
if generation ~= ARGV[2] then return 0 end
redis.call('SET',KEYS[1],ARGV[3],'EX',ARGV[4])
return 1
"""
UNLOCK = """
if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('DEL',KEYS[1]) end
return 0
"""
INVALIDATE = """
redis.call('INCR',KEYS[1])
for i=2,#KEYS do redis.call('DEL',KEYS[i]) end
return 1
"""

class MenuCache:
    def __init__(self, redis, settings):
        self.redis, self.settings = redis, settings

    @staticmethod
    def encode(items):
        return json.dumps([{'id':i.id,'name':i.name,'price':str(i.price),
                            'category_id':i.category_id,'category_name':i.category_name}
                           for i in items],ensure_ascii=False)

    @staticmethod
    def decode(raw):
        values = json.loads(raw)
        if not isinstance(values,list):
            raise ValueError('Invalid menu cache payload')
        items = []
        for value in values:
            # Cache content is a DTO, never an ORM object or pickle.
            if (set(value) != {'id','name','price','category_id','category_name'}
                    or not isinstance(value['id'],int) or not isinstance(value['category_id'],int)
                    or not isinstance(value['name'],str) or not isinstance(value['category_name'],str)):
                raise ValueError('Invalid menu cache item')
            price = Decimal(value['price'])
            if not price.is_finite() or price < 0:
                raise ValueError('Invalid price')
            items.append(MenuItem(value['id'],value['name'],price,value['category_id'],value['category_name']))
        return items

    def _get(self, key):
        raw = self.redis.get(key)
        if raw is None:
            return None
        try:
            return self.decode(raw)
        except (ValueError,TypeError,KeyError,ArithmeticError):
            log.warning('Invalid menu cache payload; reloading')
            self.redis.delete(key)
            return None

    def get_or_load(self, key, ttl, loader):
        if not self.settings.cache_enabled:
            return loader()
        lock_key, owner = key+':lock', str(uuid.uuid4())
        locked = False
        loaded = False
        items = None
        try:
            cached = self._get(key)
            if cached is not None:  # Empty menu [] is also a hit.
                return cached
            deadline = time.monotonic()+self.settings.cache_wait_seconds
            while True:
                locked = bool(self.redis.set(lock_key,owner,nx=True,ex=self.settings.cache_lock_seconds))
                if locked:
                    # Another loader could have filled it between GET and SET NX.
                    cached = self._get(key)
                    if cached is not None:
                        return cached
                    generation = self.redis.get('menu:generation') or '0'
                    items = loader()
                    loaded = True
                    self.redis.eval(PUBLISH,3,key,lock_key,'menu:generation',owner,generation,self.encode(items),ttl)
                    return items
                cached = self._get(key)
                if cached is not None:
                    return cached
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.01)
        except RedisError:
            log.warning('Menu Redis unavailable; reading PostgreSQL')
        finally:
            if locked:
                try:
                    self.redis.eval(UNLOCK,1,lock_key,owner)
                except RedisError:
                    pass
        # Bounded wait: if the owner stalls/dies, keep serving from the source.
        # Never cache an uncoordinated fallback read.
        return items if loaded else loader()

    def invalidate(self, category_ids):
        keys = ['menu:generation','menu:all']
        keys += [f'menu:category:{category_id}' for category_id in sorted(set(category_ids))]
        try:
            self.redis.eval(INVALIDATE,len(keys),*keys)
        except RedisError:
            # Commit already succeeded. TTL bounds stale data on Redis recovery.
            log.warning('Menu invalidation unavailable; stale cache bounded by TTL')
