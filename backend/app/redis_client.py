import os
from typing import Optional

import redis
from dotenv import load_dotenv
from redis import Redis

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

_client: Optional[Redis] = None
_last_error: Optional[str] = None


def _build_client() -> Redis:
    def _from_url(conn_url: str) -> Redis:
        if hasattr(redis, "from_url"):
            return redis.from_url(conn_url, decode_responses=True)
        if hasattr(redis.Redis, "from_url"):
            return redis.Redis.from_url(conn_url, decode_responses=True)
        raise AttributeError("redis.from_url is not available")

    url = os.getenv("REDIS_URL")
    if url:
        return _from_url(url)

    use_ssl = os.getenv("REDIS_SSL", "").strip().lower() in ("1", "true", "yes", "on")
    host = os.getenv("REDIS_HOST", "localhost")
    port = int(os.getenv("REDIS_PORT", "6379"))
    username = os.getenv("REDIS_USERNAME") or None
    password = os.getenv("REDIS_PASSWORD") or None
    db = int(os.getenv("REDIS_DB", "0"))

    if username:
        scheme = "rediss" if use_ssl else "redis"
        auth = f"{username}:{password or ''}"
        return _from_url(
            f"{scheme}://{auth}@{host}:{port}/{db}",
        )

    return redis.Redis(
        host=host,
        port=port,
        password=password,
        db=db,
        decode_responses=True,
        ssl=use_ssl,
    )


def get_redis() -> Optional[Redis]:
    global _client
    global _last_error
    if _client is None:
        try:
            _client = _build_client()
            _client.ping()
            _last_error = None
        except Exception as exc:
            _client = None
            _last_error = repr(exc)
    return _client


def get_redis_error() -> Optional[str]:
    return _last_error
