import os

import redis
from dotenv import load_dotenv

load_dotenv()

#TODO set this up with an in house redis cache
REDIS_URL = os.environ.get("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError(
        "REDIS_URL is not set. Copy .env.example to .env and fill it in, "
        "or export REDIS_URL yourself."
    )

redis_client = redis.from_url(REDIS_URL, decode_responses=True)

#TODO BOTH FUCNTIOSN BELOW FOR IF REDIS IS OUT!
# def get_cached_location(key: str):
#     try:
#         return redis_client.get(key)
#     except RedisError:
#         return None

# def cache_location(key: str, value: str):
#     try:
#         redis_client.set(key, value, ex=3600)
#     except RedisError:
#         pass