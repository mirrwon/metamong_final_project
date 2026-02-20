import base64
import json
import os
import re
import tempfile
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

from app.db.mysql_repo import execute, fetch_all, fetch_one
from app.db.s3_client import get_object_url, upload_bytes
from app.llm.gemini.gemini_image_edit import gemini_edit_image

TAMAGOTCHI_PIXEL_PROMPT = (
    "Transform this interior photo into 1990s tamagotchi-style pixel art. "
    "Moderate pixelation with visible 6-10px pixel blocks (not overly chunky). "
    "Limited palette (8-14 colors). "
    "Muted pastel colors with reduced saturation (low to medium saturation). "
    "Soft, slightly desaturated tones - avoid bright or neon colors. "
    "Clean 1-2px outlines, simplified shapes, minimal texture. "
    "Subtle light/shadow blocks (no gradients). "
    "Cute cozy room vibe, soft nostalgic 90s digital aesthetic. "
    "No blur, no gradients, no noise, no halftone, no dithering."
)

DATA_URL_RE = re.compile(r"^data:(?P<mime>[\w.+\-/]+);base64,(?P<data>.+)$", re.IGNORECASE)


def _now_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _now_time() -> str:
    return datetime.now().strftime("%H:%M")


def _to_iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value or "")


def _ensure_user_id(username: str) -> int:
    row = fetch_one("SELECT id FROM users WHERE username=%s LIMIT 1", (username,))
    if row:
        return int(row["id"])

    execute(
        "INSERT IGNORE INTO users (username, provider, created_at, updated_at) VALUES (%s, %s, NOW(3), NOW(3))",
        (username, "local"),
    )
    row = fetch_one("SELECT id FROM users WHERE username=%s LIMIT 1", (username,))
    if not row:
        raise RuntimeError("failed_to_create_user")
    return int(row["id"])


def _json_loads_dict(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        obj = json.loads(str(raw))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _json_loads_any(raw: Any) -> Any:
    if raw in (None, ""):
        return None
    try:
        return json.loads(str(raw))
    except Exception:
        return raw


def _json_dumps_safe(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    try:
        return json.dumps(raw, ensure_ascii=False)
    except Exception:
        return str(raw)


def _ext_from_content_type(content_type: str) -> str:
    ct = (content_type or "").lower()
    if "png" in ct:
        return ".png"
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "webp" in ct:
        return ".webp"
    if "gif" in ct:
        return ".gif"
    return ".bin"


def _decode_data_url(data_url: str) -> Optional[Tuple[bytes, str]]:
    match = DATA_URL_RE.match(data_url or "")
    if not match:
        return None
    mime = (match.group("mime") or "application/octet-stream").strip()
    b64_data = match.group("data")
    try:
        payload = base64.b64decode(b64_data)
    except Exception:
        return None
    return payload, mime


def _upload_image_bytes(prefix: str, user_id: int, content: bytes, content_type: str) -> tuple[Optional[str], Optional[str]]:
    if not content:
        return None, None

    ext = _ext_from_content_type(content_type)
    key = f"plantboard/{prefix}/{user_id}/{uuid.uuid4().hex}{ext}"
    if upload_bytes(key, content, content_type=content_type):
        return key, (get_object_url(key) or "")

    # Fallback if S3 is not configured.
    encoded = base64.b64encode(content).decode("ascii")
    return None, f"data:{content_type};base64,{encoded}"


def _normalize_image_value(value: Any, prefix: str, user_id: int) -> tuple[Optional[str], Optional[str]]:
    if not isinstance(value, str):
        return None, None

    image_data = value.strip()
    if not image_data:
        return None, None

    decoded = _decode_data_url(image_data)
    if decoded is not None:
        payload, mime = decoded
        return _upload_image_bytes(prefix, user_id, payload, mime)

    if image_data.startswith(("http://", "https://")):
        return image_data, None

    if image_data.startswith("/"):
        base_url = os.getenv("BACKEND_PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
        return f"{base_url}{image_data}", None

    return image_data, None


def _serialize_plant_row(row: Dict[str, Any]) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "id": row.get("id"),
        "name": row.get("name") or "",
        "sourcePlantId": row.get("source_plant_id"),
        "sourcePlantName": row.get("source_plant_name"),
        "createdBy": row.get("created_by"),
        "coverUrl": row.get("cover_url"),
        "roomImageUrl": row.get("room_image_url"),
        "roomImagePixelUrl": row.get("room_image_pixel_url"),
        "characterName": row.get("character_name"),
        "characterImageUrl": row.get("character_image_url"),
        "personality": row.get("personality"),
        "created_at": _to_iso(row.get("created_at")),
        "updated_at": _to_iso(row.get("updated_at")),
    }

    extra = _json_loads_dict(row.get("extra"))
    for key, value in extra.items():
        if key not in item or item[key] in (None, ""):
            item[key] = value

    return item


def _serialize_log_row(row: Dict[str, Any]) -> Dict[str, Any]:
    meta = _json_loads_any(row.get("meta"))
    item: Dict[str, Any] = {
        "id": row.get("id"),
        "type": row.get("log_type") or "",
        "date": row.get("log_date") or "",
        "time": row.get("log_time") or "",
        "plantId": row.get("plant_id") or "",
        "plantName": row.get("source_plant_name") or "",
        "title": row.get("title") or "",
        "detail": row.get("detail") or "",
        "imageUrl": row.get("image_url") or "",
        "sourcePlantId": row.get("source_plant_id") or "",
        "sourcePlantName": row.get("source_plant_name") or "",
        "plantImageUrl": row.get("plant_image_url") or "",
        "plantCharacterName": row.get("plant_character_name") or "",
        "plantPersonality": row.get("plant_personality") or "",
        "roomImageUrl": row.get("room_image_url") or "",
        "roomImagePixelUrl": row.get("room_image_pixel_url") or "",
        "created_at": _to_iso(row.get("created_at")),
        "updated_at": _to_iso(row.get("updated_at")),
    }
    if meta is not None:
        item["meta"] = meta
    return item


def _download_image_bytes(image_url: str) -> tuple[Optional[bytes], str]:
    image_url = str(image_url or "").strip()
    if not image_url:
        return None, "application/octet-stream"

    decoded = _decode_data_url(image_url)
    if decoded is not None:
        return decoded

    if image_url.startswith("/"):
        base_url = os.getenv("BACKEND_PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
        image_url = f"{base_url}{image_url}"

    if image_url.startswith(("http://", "https://")):
        try:
            response = requests.get(image_url, timeout=20)
            if not response.ok:
                return None, "application/octet-stream"
            content_type = response.headers.get("content-type", "application/octet-stream").split(";")[0]
            return response.content, content_type
        except Exception:
            return None, "application/octet-stream"

    possible_url = get_object_url(image_url)
    if possible_url:
        try:
            response = requests.get(possible_url, timeout=20)
            if not response.ok:
                return None, "application/octet-stream"
            content_type = response.headers.get("content-type", "application/octet-stream").split(";")[0]
            return response.content, content_type
        except Exception:
            return None, "application/octet-stream"

    return None, "application/octet-stream"


def _generate_pixel_image_from_url(image_url: str, user_id: int) -> Dict[str, Any]:
    if not image_url:
        return {"ok": False, "reason": "image_url missing"}

    payload, content_type = _download_image_bytes(image_url)
    if not payload:
        return {"ok": False, "reason": "input image not found"}

    input_ext = _ext_from_content_type(content_type)
    if input_ext == ".bin":
        input_ext = ".png"

    with tempfile.TemporaryDirectory(prefix="metamong_pixel_") as tmp_dir:
        input_path = os.path.join(tmp_dir, f"room{input_ext}")
        out_path = os.path.join(tmp_dir, "room_pixel.png")

        with open(input_path, "wb") as f:
            f.write(payload)

        res = gemini_edit_image(
            input_image_path=input_path,
            prompt=TAMAGOTCHI_PIXEL_PROMPT,
            out_path=out_path,
        )

        if not res.get("ok"):
            return {"ok": False, "reason": res.get("reason", "gemini failed")}

        try:
            with open(out_path, "rb") as f:
                out_bytes = f.read()
        except Exception:
            return {"ok": False, "reason": "pixel output read failed"}

    s3_key, pixel_url = _upload_image_bytes("room_pixel", user_id, out_bytes, "image/png")
    if not pixel_url:
        return {"ok": False, "reason": "pixel upload failed"}

    return {"ok": True, "url": pixel_url, "s3_key": s3_key}


# --- Plants ---

def get_user_plants(username: str) -> List[dict]:
    user_id = _ensure_user_id(username)
    rows = fetch_all(
        "SELECT * FROM plant_instances WHERE user_id=%s ORDER BY created_at ASC",
        (user_id,),
    )
    return [_serialize_plant_row(row) for row in rows]


def add_user_plant(username: str, plant_data: dict) -> dict:
    user_id = _ensure_user_id(username)
    data = dict(plant_data or {})

    cover_url, cover_key = _normalize_image_value(data.get("coverUrl"), "cover", user_id)
    room_image_url, room_image_key = _normalize_image_value(data.get("roomImageUrl"), "room", user_id)
    room_pixel_url, room_pixel_key = _normalize_image_value(data.get("roomImagePixelUrl"), "room_pixel", user_id)

    plant_id = f"plant_{int(time.time())}_{uuid.uuid4().hex[:8]}"

    known_keys = {
        "name",
        "sourcePlantId",
        "sourcePlantName",
        "createdBy",
        "coverUrl",
        "roomImageUrl",
        "roomImagePixelUrl",
        "characterName",
        "characterImageUrl",
        "personality",
    }
    extra = {k: v for k, v in data.items() if k not in known_keys}

    execute(
        "INSERT INTO plant_instances ("
        "id, user_id, name, source_plant_id, source_plant_name, created_by, "
        "cover_s3_key, cover_url, room_image_s3_key, room_image_url, "
        "room_image_pixel_s3_key, room_image_pixel_url, character_name, "
        "character_image_url, personality, extra, created_at, updated_at"
        ") VALUES ("
        "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(3), NOW(3)"
        ")",
        (
            plant_id,
            user_id,
            data.get("name"),
            data.get("sourcePlantId"),
            data.get("sourcePlantName"),
            data.get("createdBy"),
            cover_key,
            cover_url,
            room_image_key,
            room_image_url,
            room_pixel_key,
            room_pixel_url,
            data.get("characterName"),
            data.get("characterImageUrl"),
            data.get("personality"),
            _json_dumps_safe(extra),
        ),
    )

    row = fetch_one("SELECT * FROM plant_instances WHERE id=%s LIMIT 1", (plant_id,))
    if not row:
        return {"id": plant_id, **data}
    return _serialize_plant_row(row)


# --- Logs ---

def get_plant_logs(username: str) -> List[dict]:
    user_id = _ensure_user_id(username)
    rows = fetch_all(
        "SELECT * FROM plant_logs WHERE user_id=%s "
        "ORDER BY COALESCE(log_date, '') DESC, COALESCE(log_time, '') DESC, created_at DESC",
        (user_id,),
    )
    return [_serialize_log_row(row) for row in rows]


def add_plant_log(username: str, log_data: dict) -> dict:
    user_id = _ensure_user_id(username)
    data = dict(log_data or {})

    image_url, image_key = _normalize_image_value(data.get("imageUrl"), "log", user_id)

    log_id = f"log_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    log_date = str(data.get("date") or _now_date())
    log_time = str(data.get("time") or _now_time())

    meta_value = data.get("meta")
    meta_json = _json_dumps_safe(meta_value)

    source_plant_name = data.get("plantName") or data.get("sourcePlantName")
    source_plant_id = data.get("sourcePlantId")

    execute(
        "INSERT INTO plant_logs ("
        "id, user_id, plant_id, log_type, log_date, log_time, title, detail, "
        "image_s3_key, image_url, source_plant_id, source_plant_name, plant_image_url, "
        "plant_character_name, plant_personality, room_image_url, room_image_pixel_url, "
        "meta, created_at, updated_at"
        ") VALUES ("
        "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(3), NOW(3)"
        ")",
        (
            log_id,
            user_id,
            data.get("plantId"),
            data.get("type"),
            log_date,
            log_time,
            data.get("title"),
            data.get("detail"),
            image_key,
            image_url,
            source_plant_id,
            source_plant_name,
            data.get("plantImageUrl"),
            data.get("plantCharacterName"),
            data.get("plantPersonality"),
            data.get("roomImageUrl"),
            data.get("roomImagePixelUrl"),
            meta_json,
        ),
    )

    row = fetch_one("SELECT * FROM plant_logs WHERE id=%s LIMIT 1", (log_id,))
    if not row:
        return {"id": log_id, **data}
    return _serialize_log_row(row)


def delete_plant_log(username: str, log_id: str) -> bool:
    user_id = _ensure_user_id(username)
    affected = execute("DELETE FROM plant_logs WHERE user_id=%s AND id=%s", (user_id, log_id))
    return affected > 0


# --- Pixel generation ---

def generate_tamagotchi_room_pixel_image(username: str, image_url: str, plant_id: Optional[str] = None) -> Dict[str, Any]:
    user_id = _ensure_user_id(username)
    res = _generate_pixel_image_from_url(image_url, user_id)
    if not res.get("ok"):
        return res

    pixel_url = res.get("url")
    s3_key = res.get("s3_key")

    if plant_id:
        execute(
            "UPDATE plant_instances SET room_image_pixel_s3_key=%s, room_image_pixel_url=%s, updated_at=NOW(3) "
            "WHERE user_id=%s AND id=%s",
            (s3_key, pixel_url, user_id, plant_id),
        )
        row = fetch_one(
            "SELECT * FROM plant_instances WHERE user_id=%s AND id=%s LIMIT 1",
            (user_id, plant_id),
        )
        if row:
            return {"ok": True, "url": pixel_url, "plant": _serialize_plant_row(row)}

    return {"ok": True, "url": pixel_url}


def generate_tamagotchi_room_pixel_images_for_user(username: str, force: bool = False) -> Dict[str, Any]:
    user_id = _ensure_user_id(username)
    rows = fetch_all("SELECT * FROM plant_instances WHERE user_id=%s ORDER BY created_at ASC", (user_id,))

    failures: List[Dict[str, Any]] = []
    for row in rows:
        plant_id = row.get("id")
        room_url = row.get("room_image_url")
        room_pixel_url = row.get("room_image_pixel_url")

        if not room_url:
            continue
        if room_pixel_url and not force:
            continue

        res = _generate_pixel_image_from_url(room_url, user_id)
        if not res.get("ok"):
            failures.append({"id": plant_id, "reason": res.get("reason")})
            continue

        execute(
            "UPDATE plant_instances SET room_image_pixel_s3_key=%s, room_image_pixel_url=%s, updated_at=NOW(3) "
            "WHERE user_id=%s AND id=%s",
            (res.get("s3_key"), res.get("url"), user_id, plant_id),
        )

    return {
        "ok": True,
        "items": get_user_plants(username),
        "failures": failures,
    }
