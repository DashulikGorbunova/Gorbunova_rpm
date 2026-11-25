"""Redis adapters use a short deadline; menu cache errors never become API errors."""
from redis import Redis
from redis.backoff import NoBackoff
from redis.retry import Retry

def menu_redis(url):
    return Redis.from_url(url, decode_responses=True, socket_connect_timeout=0.1,
                          socket_timeout=0.1, retry=Retry(NoBackoff(), 0))
