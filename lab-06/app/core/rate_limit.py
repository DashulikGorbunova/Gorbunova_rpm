import hashlib
from fastapi import Request, HTTPException
from redis.exceptions import RedisError

# INCR and expiry are atomic; TTL cannot be lost between two client commands.
SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return {count, redis.call('TTL', KEYS[1])}
"""

def rate_limit(scope: str, max_requests: int = 5, window: int = 60):
    def checker(request: Request):
        ip = request.client.host if request.client else 'unknown'
        key = 'sirius:rate:' + scope + ':' + hashlib.sha256(ip.encode()).hexdigest()
        try:
            count, ttl = request.app.state.redis.eval(SCRIPT, 1, key, window)
        except RedisError:
            raise HTTPException(503, 'Rate limiter unavailable') from None
        if count > max_requests:
            raise HTTPException(429, 'Too many requests', headers={'Retry-After': str(max(1,ttl))})
    return checker
