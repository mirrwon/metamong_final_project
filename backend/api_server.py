import os
import json
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from app.config import RESULT_DIR, UPLOAD_DIR, PLANTS_DIR  # ✅ config 단일 소스 사용

from app.db.redis_client import get_redis, get_redis_error
from app.db.mysql_client import get_mysql, get_mysql_error
from app.db.vercel_blob_client import ping_vercel_blob, get_vercel_blob_error

from app.api.chat_routes import router as chat_router
from app.api.diary_routes import router as diary_router
from app.api.login_routes import router as login_router
import os
import json
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from app.config import RESULT_DIR, UPLOAD_DIR, PLANTS_DIR  # ✅ config 단일 소스 사용

from app.db.redis_client import get_redis, get_redis_error
from app.db.mysql_client import get_mysql, get_mysql_error
from app.db.vercel_blob_client import ping_vercel_blob, get_vercel_blob_error

from app.api.chat_routes import router as chat_router
from app.api.diary_routes import router as diary_router
from app.api.login_routes import router as login_router

# (선택) backend 루트 경로가 필요하면 유지
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUTH_UPLOAD_DIR = os.path.normpath(os.path.join(BASE_DIR, "app", "api", "uploads"))
AUTH_UPLOAD_MOUNT = "/auth-uploads"

# ✅ 디렉토리 보장 (config에서 경로만 만들고, 여기서도 안전하게 한번 더)
os.makedirs(RESULT_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PLANTS_DIR, exist_ok=True)

load_dotenv()

app = FastAPI()

# ✅ 정적 파일 mount는 여기(api_server)에서만 한다 (chat_routes에 넣지 말기)
# ✅ 중복 mount 제거: /results는 1번만
app.mount("/results", StaticFiles(directory=RESULT_DIR), name="results")
app.mount("/plants", StaticFiles(directory=PLANTS_DIR), name="plants")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount(AUTH_UPLOAD_MOUNT, StaticFiles(directory=AUTH_UPLOAD_DIR), name="auth-uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(chat_router)
app.include_router(diary_router)
app.include_router(login_router)

_plants_cache = {}
_plants_key_cache = {}
# (선택) backend 루트 경로가 필요하면 유지
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUTH_UPLOAD_DIR = os.path.normpath(os.path.join(BASE_DIR, "app", "api", "uploads"))
AUTH_UPLOAD_MOUNT = "/auth-uploads"

# ✅ 디렉토리 보장 (config에서 경로만 만들고, 여기서도 안전하게 한번 더)
os.makedirs(RESULT_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PLANTS_DIR, exist_ok=True)

load_dotenv()

app = FastAPI()

# ✅ 정적 파일 mount는 여기(api_server)에서만 한다 (chat_routes에 넣지 말기)
# ✅ 중복 mount 제거: /results는 1번만
app.mount("/results", StaticFiles(directory=RESULT_DIR), name="results")
app.mount("/plants", StaticFiles(directory=PLANTS_DIR), name="plants")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount(AUTH_UPLOAD_MOUNT, StaticFiles(directory=AUTH_UPLOAD_DIR), name="auth-uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(chat_router)
app.include_router(diary_router)
app.include_router(login_router)

_plants_cache = {}
_plants_key_cache = {}


def _sort_plant_keys(keys, prefix: str) -> list:
    def _parse_int(key: str):
        if prefix and key.startswith(prefix):
            key = key[len(prefix) :]
        try:
            return int(key)
        except Exception:
            return None

    parsed = [(_parse_int(k), k) for k in keys]
    if all(p[0] is not None for p in parsed):
        parsed.sort(key=lambda item: item[0])
        return [p[1] for p in parsed]
    return sorted(keys)


def _get_cached_keys(r, prefix: str, cache_ttl: int) -> list:
    cache_key = prefix or "__all__"
    cached = _plants_key_cache.get(cache_key)
    if cache_ttl and cached and (time.time() - cached["ts"] <= cache_ttl):
        return cached["keys"]

    cursor = 0
    keys = []
    while True:
        cursor, batch = r.scan(cursor=cursor, match=f"{prefix}*" if prefix else None, count=1000)
        keys.extend(batch)
        if cursor == 0:
            break

    keys = _sort_plant_keys(keys, prefix)
    if cache_ttl:
        _plants_key_cache[cache_key] = {"ts": time.time(), "keys": keys}
    return keys


def _resolve_plant_image(raw: dict, key: str, prefix: str):
    image = raw.get("image") or raw.get("\uc774\ubbf8\uc9c0")
    if isinstance(image, str) and image.strip():
        image = image.strip()
        if image.lower().startswith(("http://", "https://")):
            return image

        base_url = os.getenv("VERCEL_PLANT_IMAGE_BASE_URL", "").strip().rstrip("/")
        if not base_url:
            return image

        if image.lower().startswith("plant_img/") and base_url.lower().endswith("plant_img"):
            image = image[len("plant_img/") :]
        image = image.lstrip("/")
        return f"{base_url}/{image}"

    base_url = os.getenv("VERCEL_PLANT_IMAGE_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        return None

    exts = os.getenv("VERCEL_PLANT_IMAGE_EXTS", "").strip()
    ext_list = [ext.strip() for ext in exts.split(",") if ext.strip()] or [".jpg"]
    ext = ext_list[0]
    if not ext.startswith("."):
        ext = f".{ext}"

    plant_id = key[len(prefix) :] if prefix and key.startswith(prefix) else key
    if not plant_id:
        return None
    return f"{base_url}/plant_{plant_id}{ext}"


def _normalize_plant_payload(raw, key: str, prefix: str) -> dict:
    if not isinstance(raw, dict):
        raw = {}

    name_ko = raw.get("\uc774\ub984ko")
    name_en = raw.get("\uc774\ub984_en")
    care_level = raw.get("\uad00\ub9ac_\ub09c\uc774\ub3c4") or raw.get("\uad00\ub9ac_\uc694\uad6c\ub3c4")
    allergy = raw.get("\uc0ac\ub78c_\uc54c\ub7ec\uc9c0_\uc8fc\uc758") or raw.get("\uc0ac\ub78c_\uc54c\ub7ec\uc9c0_\uc720\ud615")
    pet_target = raw.get("\ubc18\ub824\ub3d9\ubb3c_\ub300\uc0c1")
    pet_symptom = raw.get("\ubc18\ub824\ub3d9\ubb3c_\uc99d\uc0c1")
    if pet_target is None and pet_symptom is None:
        pet_safe = None
    else:
        pet_safe = pet_target == "\uc5c6\uc74c" and pet_symptom == "\uc5c6\uc74c"

    return {
        "id": key[len(prefix) :] if prefix and key.startswith(prefix) else key,
        "name": name_ko or name_en or key,
        "name_ko": name_ko,
        "name_en": name_en,
        "type": raw.get("\uc885\ub958"),
        "size": raw.get("\ud06c\uae30_\uad6c\ubd84"),
        "light_min": raw.get("\uad11\ub7c9_min"),
        "light_max": raw.get("\uad11\ub7c9_max"),
        "placement": raw.get("\uad8c\uc7a5_\ubc30\uce58_\uacf5\uac04"),
        "care": care_level,
        "allergy": allergy,
        "pet_safe": pet_safe,
        "image": _resolve_plant_image(raw, key, prefix),
    }

@app.get("/health")
def health():
    return {"ok": True}


@app.get("/debug/redis")
def redis_debug():
    r = get_redis()
    if not r:
        return {"ok": False, "reason": "no_connection", "error": get_redis_error()}
    try:
        r.ping()
    except Exception:
        return {"ok": False, "reason": "ping_failed"}

    prefix = os.getenv("REDIS_PLANTS_PREFIX", "").strip()
    count = None
    if prefix:
        try:
            cursor = 0
            count = 0
            limit = 5000
            while True:
                cursor, keys = r.scan(cursor=cursor, match=f"{prefix}*", count=200)
                count += len(keys)
                if cursor == 0 or count >= limit:
                    break
        except Exception:
            count = None

    sample_name = None
    if prefix:
        try:
            sample_key = f"{prefix}1"
            raw = r.execute_command("JSON.GET", sample_key, "$.이름ko")
            sample_name = raw
        except Exception:
            sample_name = None

    return {
        "ok": True,
        "prefix": prefix or None,
        "key_count": count,
        "sample_name": sample_name,
    }


@app.get("/api/plants")
def list_plants(cursor: int = 0, limit: int = 24, offset: int | None = None):
    cache_sec = os.getenv("REDIS_PLANTS_CACHE_SEC", "").strip()
    try:
        cache_ttl = max(0, int(cache_sec))
    except Exception:
        cache_ttl = 0

    r = get_redis()
    if not r:
        return {
            "ok": False,
            "items": [],
            "next_cursor": 0,
            "reason": "no_connection",
            "error": get_redis_error(),
        }

    prefix = os.getenv("REDIS_PLANTS_PREFIX", "").strip()
    json_path = os.getenv("REDIS_PLANTS_JSON_PATH", "$").strip() or "$"

    try:
        scan_cursor = max(int(cursor), 0)
    except Exception:
        scan_cursor = 0

    try:
        limit_val = max(1, min(int(limit), 100))
    except Exception:
        limit_val = 24

    if offset is not None:
        try:
            offset_val = max(0, int(offset))
        except Exception:
            offset_val = 0

        cache_key = ("offset", offset_val, limit_val)
        if cache_ttl:
            cached = _plants_cache.get(cache_key)
            if cached and (time.time() - cached["ts"] <= cache_ttl):
                return cached["payload"]

        keys = _get_cached_keys(r, prefix, cache_ttl)
        total = len(keys)
        slice_keys = keys[offset_val : offset_val + limit_val]
        items = []
        if slice_keys:
            try:
                pipe = r.pipeline()
                for key in slice_keys:
                    pipe.execute_command("JSON.GET", key, json_path)
                raw_items = pipe.execute()
            except Exception:
                pipe = r.pipeline()
                for key in slice_keys:
                    pipe.get(key)
                raw_items = pipe.execute()

            for key, payload in zip(slice_keys, raw_items):
                if payload is None:
                    continue
                try:
                    decoded = json.loads(payload)
                except Exception:
                    decoded = payload

                if isinstance(decoded, list) and len(decoded) == 1:
                    decoded = decoded[0]
                items.append(_normalize_plant_payload(decoded, key, prefix))

        next_offset = offset_val + limit_val
        payload = {
            "ok": True,
            "items": items,
            "next_offset": next_offset if next_offset < total else None,
            "total": total,
        }
    else:
        cache_key = ("cursor", scan_cursor, limit_val)
        if cache_ttl:
            cached = _plants_cache.get(cache_key)
            if cached and (time.time() - cached["ts"] <= cache_ttl):
                return cached["payload"]

        items = []
        while len(items) < limit_val:
            scan_cursor, keys = r.scan(
                cursor=scan_cursor,
                match=f"{prefix}*" if prefix else None,
                count=max(limit_val * 2, 50),
            )
            if keys:
                try:
                    pipe = r.pipeline()
                    for key in keys:
                        pipe.execute_command("JSON.GET", key, json_path)
                    raw_items = pipe.execute()
                except Exception:
                    pipe = r.pipeline()
                    for key in keys:
                        pipe.get(key)
                    raw_items = pipe.execute()
                for key, payload in zip(keys, raw_items):
                    if payload is None:
                        continue
                    try:
                        decoded = json.loads(payload)
                    except Exception:
                        decoded = payload

                    if isinstance(decoded, list) and len(decoded) == 1:
                        decoded = decoded[0]

                    items.append(_normalize_plant_payload(decoded, key, prefix))
                    if len(items) >= limit_val:
                        break

            if scan_cursor == 0:
                break

        payload = {"ok": True, "items": items, "next_cursor": scan_cursor}
    if cache_ttl:
        _plants_cache[cache_key] = {"ts": time.time(), "payload": payload}
    return payload
    
@app.get("/debug/mysql")
def mysql_debug():
    conn = get_mysql()
    if not conn:
        return {"ok": False, "reason": "no_connection", "error": get_mysql_error()}
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return {"ok": False, "reason": "ping_failed"}
    return {"ok": True}

@app.get("/debug/vercel-blob")
def vercel_blob_debug():
    ok = ping_vercel_blob()
    if not ok:
        return {"ok": False, "error": get_vercel_blob_error()}
    return {"ok": True}
