import os
import json
from typing import Any, Dict, Optional

import redis

from .chat_env import env_bool

# Fallback in-memory (Redis down 대비)
USER_STATE: Dict[str, Dict[str, Any]] = {}
USER_CTX: Dict[str, Dict[str, Any]] = {}


def _redis_client() -> Optional[redis.Redis]:
    host = os.getenv("REDIS_HOST")
    port = os.getenv("REDIS_PORT")
    if not host or not port:
        return None

    username = os.getenv("REDIS_USERNAME") or None
    password = os.getenv("REDIS_PASSWORD") or None
    use_ssl = env_bool(os.getenv("REDIS_SSL"), default=False)
    db = int(os.getenv("REDIS_DB", "0"))

    try:
        r = redis.Redis(
            host=host,
            port=int(port),
            username=username,
            password=password,
            db=db,
            ssl=use_ssl,
            decode_responses=True,
        )
        r.ping()
        return r
    except Exception:
        return None


def _rk_ctx(client_key: str) -> str:
    return f"user_ctx:{client_key}"


def _rk_state(client_key: str) -> str:
    return f"user_state:{client_key}"


def _rget_json(r: redis.Redis, key: str) -> Dict[str, Any]:
    raw = r.get(key)
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _rset_json(r: redis.Redis, key: str, obj: Dict[str, Any], ttl_sec: Optional[int] = None):
    payload = json.dumps(obj, ensure_ascii=False)
    if ttl_sec and ttl_sec > 0:
        r.setex(key, int(ttl_sec), payload)
    else:
        r.set(key, payload)


def get_user_ctx(client_key: str) -> Dict[str, Any]:
    r = _redis_client()
    if r is not None:
        return _rget_json(r, _rk_ctx(client_key))
    v = USER_CTX.get(client_key, {})
    return v if isinstance(v, dict) else {}


def set_user_ctx(client_key: str, updates: Dict[str, Any], ttl_sec: Optional[int] = None):
    r = _redis_client()
    if r is not None:
        cur = _rget_json(r, _rk_ctx(client_key))
        if isinstance(updates, dict):
            cur.update(updates)
        _rset_json(r, _rk_ctx(client_key), cur, ttl_sec=ttl_sec)
        return

    USER_CTX.setdefault(client_key, {})
    if isinstance(updates, dict):
        USER_CTX[client_key].update(updates)


def get_user_state(client_key: str) -> Dict[str, Any]:
    r = _redis_client()
    if r is not None:
        return _rget_json(r, _rk_state(client_key))
    v = USER_STATE.get(client_key, {})
    return v if isinstance(v, dict) else {}


def set_user_state(client_key: str, updates: Dict[str, Any], ttl_sec: Optional[int] = None):
    r = _redis_client()
    if r is not None:
        cur = _rget_json(r, _rk_state(client_key))
        if isinstance(updates, dict):
            cur.update(updates)
        _rset_json(r, _rk_state(client_key), cur, ttl_sec=ttl_sec)
        return

    USER_STATE.setdefault(client_key, {})
    if isinstance(updates, dict):
        USER_STATE[client_key].update(updates)