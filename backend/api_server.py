import os
import json
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from app.config import RESULT_DIR, UPLOAD_DIR, PLANTS_DIR, ASSET_DIR  # ✅ config 단일 소스 사용

from app.db.redis_client import get_redis, get_redis_error
from app.db.mysql_client import get_mysql, get_mysql_error
from app.db.s3_client import ping_s3, get_s3_error, get_presigned_url

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
os.makedirs(ASSET_DIR, exist_ok=True)

load_dotenv()

app = FastAPI()

# ✅ 정적 파일 mount는 여기(api_server)에서만 한다 (chat_routes에 넣지 말기)
# ✅ 중복 mount 제거: /results는 1번만
app.mount("/results", StaticFiles(directory=RESULT_DIR), name="results")
app.mount("/plants", StaticFiles(directory=PLANTS_DIR), name="plants")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/assets", StaticFiles(directory=ASSET_DIR), name="assets")
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


def _get_scan_limit() -> int:
    raw = os.getenv("REDIS_PLANTS_SCAN_LIMIT", "").strip()
    try:
        return max(0, int(raw))
    except Exception:
        return 0


def _normalize_plant_id(key: str, prefix: str) -> str:
    if prefix and key.startswith(prefix):
        return key[len(prefix) :]
    if key.startswith("plant:"):
        return key.split("plant:", 1)[1]
    return key


def _sort_plant_keys(keys, prefix: str) -> list:
    def _parse_int(key: str):
        key = _normalize_plant_id(key, prefix)
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

    ids_set = os.getenv("REDIS_PLANTS_ID_SET", "").strip() or "plants:ids"
    keys = []
    if ids_set:
        try:
            if r.exists(ids_set):
                keys = list(r.smembers(ids_set))
        except Exception:
            keys = []

    if keys:
        keys = _sort_plant_keys(keys, prefix)
        if cache_ttl:
            _plants_key_cache[cache_key] = {"ts": time.time(), "keys": keys}
        return keys

    cursor = 0
    scan_limit = _get_scan_limit()
    while True:
        cursor, batch = r.scan(cursor=cursor, match=f"{prefix}*" if prefix else None, count=1000)
        keys.extend(batch)
        if scan_limit and len(keys) >= scan_limit:
            keys = keys[:scan_limit]
            break
        if cursor == 0:
            break

    if not prefix and ids_set:
        keys = [key for key in keys if key != ids_set]

    keys = _sort_plant_keys(keys, prefix)
    if cache_ttl:
        _plants_key_cache[cache_key] = {"ts": time.time(), "keys": keys}
    return keys


def _fetch_redis_json_items(r, keys: list, json_path: str) -> list:
    if not keys:
        return []
    try:
        raw_items = r.execute_command("JSON.MGET", *keys, json_path)
    except Exception:
        raw_items = None

    if raw_items is None:
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

    items = []
    for payload in raw_items:
        if payload is None:
            items.append(None)
            continue
        try:
            decoded = json.loads(payload)
        except Exception:
            decoded = payload
        if isinstance(decoded, list) and len(decoded) == 1:
            decoded = decoded[0]
        items.append(decoded)
    return items


def _get_s3_settings() -> tuple[str, bool, str]:
    base_url = os.getenv("S3_PLANT_IMAGE_BASE_URL", "").strip().rstrip("/")
    use_presigned = os.getenv("S3_USE_PRESIGNED_URLS", "").strip().lower() in ("1", "true", "yes")
    prefix_path = os.getenv("S3_PLANT_IMAGE_PREFIX", "").strip().strip("/") or "plant_img"
    return base_url, use_presigned, prefix_path


def _s3_extract_key(value: str, base_url: str, prefix_path: str) -> str | None:
    if not value:
        return None
    val = value.strip()
    if not val:
        return None

    key = None
    if val.lower().startswith(("http://", "https://")):
        if base_url and val.startswith(base_url):
            remainder = val[len(base_url) :].lstrip("/")
            if base_url.lower().endswith(prefix_path.lower()):
                key = f"{prefix_path}/{remainder}" if remainder else prefix_path
            else:
                key = remainder
        elif ".amazonaws.com/" in val:
            remainder = val.split(".amazonaws.com/", 1)[1]
            key = remainder.lstrip("/")
        else:
            return None
    else:
        key = val
        if base_url and val.startswith(base_url):
            key = val[len(base_url) :].lstrip("/")

    if not key:
        return None
    if not key.lower().startswith(f"{prefix_path.lower()}/"):
        key = f"{prefix_path}/{key.lstrip('/')}"
    return key


def _s3_presign_value(value: str, base_url: str, prefix_path: str) -> str:
    key = _s3_extract_key(value, base_url, prefix_path)
    if not key:
        return value
    return get_presigned_url(key) or value


def _resolve_plant_image(raw: dict, key: str, prefix: str):
    image = raw.get("image") or raw.get("\uc774\ubbf8\uc9c0")
    base_url, use_presigned, prefix_path = _get_s3_settings()

    if isinstance(image, str) and image.strip():
        image = image.strip()
        if use_presigned:
            return _s3_presign_value(image, base_url, prefix_path)
        if image.lower().startswith(("http://", "https://")):
            return image

        if not base_url:
            return image

        prefix_token = f"{prefix_path.lower()}/"
        if image.lower().startswith(prefix_token) and base_url.lower().endswith(prefix_path.lower()):
            image = image[len(prefix_path) + 1 :]
        image = image.lstrip("/")
        return f"{base_url}/{image}"

    if not base_url and not use_presigned:
        return None

    exts = os.getenv("S3_PLANT_IMAGE_EXTS", "").strip()
    ext_list = [ext.strip() for ext in exts.split(",") if ext.strip()] or [".jpg"]
    ext = ext_list[0]
    if not ext.startswith("."):
        ext = f".{ext}"

    plant_id = _normalize_plant_id(key, prefix)
    if not plant_id:
        return None
    filename = f"plant_{plant_id}_1{ext}"
    if use_presigned:
        key_path = f"{prefix_path}/{filename}"
        return get_presigned_url(key_path)
    return f"{base_url}/{filename}"


def _resolve_plant_images(raw: dict, key: str, prefix: str) -> list:
    base_url, use_presigned, prefix_path = _get_s3_settings()
    if not base_url and not use_presigned:
        return []

    image_count = (
        raw.get("photo_count")
        or raw.get("photoCount")
        or raw.get("photo_cnt")
        or raw.get("image_count")
        or raw.get("imageCount")
        or raw.get("images_count")
        or raw.get("imagesCount")
        or raw.get("\uc0ac\uc9c4_\uac1c\uc218")
        or raw.get("\uc0ac\uc9c4_\uac2f\uc218")
    )
    try:
        image_count = int(image_count)
        if image_count < 1:
            image_count = None
    except Exception:
        image_count = None

    images_raw = raw.get("images") or raw.get("\uc774\ubbf8\uc9c0\ub4e4")
    if isinstance(images_raw, list):
        resolved = []
        for item in images_raw:
            if not isinstance(item, str) or not item.strip():
                continue
            item = item.strip()
            if use_presigned:
                resolved.append(_s3_presign_value(item, base_url, prefix_path))
                continue
            if item.lower().startswith(("http://", "https://")):
                resolved.append(item)
                continue
            prefix_token = f"{prefix_path.lower()}/"
            if item.lower().startswith(prefix_token) and base_url.lower().endswith(prefix_path.lower()):
                item = item[len(prefix_path) + 1 :]
            item = item.lstrip("/")
            resolved.append(f"{base_url}/{item}")
        return resolved

    exts = os.getenv("S3_PLANT_IMAGE_EXTS", "").strip()
    ext_list = [ext.strip() for ext in exts.split(",") if ext.strip()] or [".jpg"]
    ext = ext_list[0]
    if not ext.startswith("."):
        ext = f".{ext}"

    max_images_raw = os.getenv("S3_PLANT_IMAGE_MAX", "").strip()
    try:
        max_images = max(1, min(int(max_images_raw), 12))
    except Exception:
        max_images = 4
    if image_count:
        max_images = min(max_images, image_count)

    plant_id = _normalize_plant_id(key, prefix)
    if not plant_id:
        return []

    filenames = [f"plant_{plant_id}_{idx}{ext}" for idx in range(1, max_images + 1)]
    if use_presigned:
        signed = [get_presigned_url(f"{prefix_path}/{name}") for name in filenames]
        return [url for url in signed if url]
    return [f"{base_url}/{name}" for name in filenames]


def _normalize_plant_payload(raw, key: str, prefix: str) -> dict:
    if not isinstance(raw, dict):
        raw = {}

    def _join_list(val):
        if isinstance(val, list):
            return ", ".join([str(item) for item in val if item is not None])
        return val

    name_ko = raw.get("\uc774\ub984ko") or raw.get("\uc774\ub984_\ud55c\uad6d\uc5b4")
    name_en = raw.get("\uc774\ub984_en") or raw.get("\uc774\ub984_\uc601\uc5b4")
    care_level = raw.get("\uad00\ub9ac_\ub09c\uc774\ub3c4") or raw.get("\uad00\ub9ac_\uc694\uad6c\ub3c4")
    allergy_notice = raw.get("\uc0ac\ub78c_\uc54c\ub7ec\uc9c0_\uc8fc\uc758")
    allergy_type = raw.get("\uc0ac\ub78c_\uc54c\ub7ec\uc9c0_\uc720\ud615")
    allergy_symptom = raw.get("\uc0ac\ub78c_\uc54c\ub7ec\uc9c0_\uc99d\uc0c1")
    allergy = allergy_type or allergy_notice or allergy_symptom

    pet_target = raw.get("\ubc18\ub824\ub3d9\ubb3c_\ub300\uc0c1")
    pet_symptom = raw.get("\ubc18\ub824\ub3d9\ubb3c_\uc99d\uc0c1")
    pet_target_value = _join_list(pet_target)
    if pet_symptom in (None, "", "\uc5c6\uc74c") and pet_target_value in (None, "", "\uc5c6\uc74c"):
        pet_safe = None
    elif pet_symptom == "\uc5c6\uc74c":
        pet_safe = True
    else:
        pet_safe = False

    light_lux = raw.get("\uad11_\uc694\uad6c\ub3c4_Lux") or raw.get("\uad11\ub7c9")
    light_min = raw.get("\uad11\ub7c9_min")
    light_max = raw.get("\uad11\ub7c9_max")
    if isinstance(light_lux, list) and light_lux:
        light_min = light_lux[0]
        if len(light_lux) > 1:
            light_max = light_lux[-1]
        else:
            light_max = None
    light_min = _join_list(light_min)
    light_max = _join_list(light_max)

    placement = raw.get("\uad8c\uc7a5_\ubc30\uce58_\uacf5\uac04")
    placement = _join_list(placement)

    image = _resolve_plant_image(raw, key, prefix)
    images = _resolve_plant_images(raw, key, prefix)
    if image:
        if image not in images:
            images = [image, *images]

    return {
        "id": _normalize_plant_id(key, prefix),
        "name": name_ko or name_en or key,
        "name_ko": name_ko,
        "name_en": name_en,
        "type": raw.get("\uc885\ub958"),
        "size": raw.get("\ud06c\uae30_\uad6c\ubd84"),
        "light_min": light_min,
        "light_max": light_max,
        "placement": placement,
        "care": care_level,
        "allergy": allergy,
        "pet_safe": pet_safe,
        "image": image,
        "images": images,
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
    ids_set = os.getenv("REDIS_PLANTS_ID_SET", "").strip() or "plants:ids"
    count = None
    if prefix:
        try:
            if ids_set and r.exists(ids_set):
                count = r.scard(ids_set)
            else:
                cursor = 0
                count = 0
                limit = 5000
                scan_limit = _get_scan_limit()
                if scan_limit:
                    limit = min(limit, scan_limit)
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
            raw = r.execute_command("JSON.GET", sample_key, "$.\uc774\ub984_\ud55c\uad6d\uc5b4")
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
            raw_items = _fetch_redis_json_items(r, slice_keys, json_path)
            for key, decoded in zip(slice_keys, raw_items):
                if decoded is None:
                    continue
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
                raw_items = _fetch_redis_json_items(r, keys, json_path)
                for key, decoded in zip(keys, raw_items):
                    if decoded is None:
                        continue
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

@app.get("/debug/s3")
def s3_debug():
    ok = ping_s3()
    if not ok:
        return {"ok": False, "error": get_s3_error()}
    return {"ok": True}
