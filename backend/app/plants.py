# 식물추천

import json
import os
import time
from typing import Any, Dict, List, Optional

from .redis_client import get_redis

PLANTS = [
    {"name":"산세베리아", "min":0.70, "max":1.20, "pet_safe":True,  "care":1, "tags":["초보","저광량"]},
    {"name":"스투키",     "min":0.60, "max":1.10, "pet_safe":True,  "care":1, "tags":["초보","저광량"]},
    {"name":"아레카야자", "min":1.10, "max":1.70, "pet_safe":True,  "care":2, "tags":["공기정화"]},
    {"name":"올리브나무", "min":1.40, "max":2.20, "pet_safe":True,  "care":3, "tags":["고광량","관리어려움"]},
    {"name":"몬스테라",   "min":1.00, "max":1.60, "pet_safe":False, "care":2, "tags":["주의(반려동물)"]},
]

_CACHE_TS = 0.0
_CACHE_PLANTS: Optional[List[Dict[str, Any]]] = None

_LIGHT_LEVEL_MAP = {
    "그늘": 0.5,
    "반그늘": 0.7,
    "저광": 0.6,
    "낮은광": 0.6,
    "약광": 0.6,
    "중간광": 1.0,
    "중광": 1.0,
    "밝은간접광": 1.4,
    "밝은 간접광": 1.4,
    "밝은광": 1.7,
    "강광": 1.9,
    "강한광": 1.9,
    "직사광": 2.2,
    "강한직사광": 2.3,
}


def _to_float(val: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if val is None:
            return default
        return float(val)
    except Exception:
        return default


def _to_int(val: Any, default: int = 0) -> int:
    try:
        if val is None:
            return default
        return int(float(val))
    except Exception:
        return default


def _to_bool(val: Any, default: bool = False) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return bool(val)
    s = str(val).strip().lower()
    if s in ("1", "true", "yes", "y", "t"):
        return True
    if s in ("0", "false", "no", "n", "f"):
        return False
    return default


def _normalize_tags(val: Any) -> List[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(v).strip() for v in val if str(v).strip()]
    if isinstance(val, str):
        return [v.strip() for v in val.replace(";", ",").split(",") if v.strip()]
    return [str(val)]


def _light_level_value(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return None
    if s in _LIGHT_LEVEL_MAP:
        return _LIGHT_LEVEL_MAP[s]
    for key, value in _LIGHT_LEVEL_MAP.items():
        if key in s:
            return value
    return None


def _parse_light_range(val: Any) -> tuple[Optional[float], Optional[float]]:
    if val is None:
        return None, None
    if isinstance(val, (int, float)):
        v = float(val)
        return v, v
    s = str(val).strip()
    if not s:
        return None, None
    for sep in ("~", "-", "–"):
        if sep in s:
            left, right = (part.strip() for part in s.split(sep, 1))
            return _light_level_value(left), _light_level_value(right)
    v = _light_level_value(s)
    return v, v


def _parse_range_cm(val: Any) -> tuple[Optional[float], Optional[float]]:
    if val is None:
        return None, None
    if isinstance(val, (int, float)):
        v = float(val)
        return v, v
    s = str(val).strip()
    if not s:
        return None, None
    s = s.replace("cm", "").replace("CM", "").replace("㎝", "").strip()
    for sep in ("~", "-", "–", "—"):
        if sep in s:
            left, right = (part.strip() for part in s.split(sep, 1))
            return _to_float(left), _to_float(right)
    v = _to_float(s)
    return v, v


def _humidity_level(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        v = float(val)
        return max(0.0, min(1.0, v))
    s = str(val).strip().lower()
    if not s:
        return None
    if any(k in s for k in ("고습", "높음", "high")):
        return 0.9
    if any(k in s for k in ("건조", "낮음", "저습", "low")):
        return 0.3
    if any(k in s for k in ("보통", "중간", "일반", "medium")):
        return 0.6
    return None


def _parse_care_level(val: Any) -> Optional[int]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(float(val))
    s = str(val).strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if any(k in s for k in ("쉬움", "낮음")) or s in ("하", "하급"):
        return 1
    if any(k in s for k in ("보통", "중간")) or s in ("중",):
        return 2
    if any(k in s for k in ("어려움", "높음")) or s in ("상", "상급"):
        return 3
    return None


def _pet_safe_from_raw(raw: Dict[str, Any]) -> Optional[bool]:
    symptom = raw.get("반려동물_증상") or raw.get("반려동물_메모")
    caution = raw.get("반려동물_주의") or raw.get("반려동물_경고")
    value = symptom if symptom is not None else caution
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if s in ("없음", "none", "n/a", "-"):
        return True
    return False


def _normalize_plant(raw: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None

    name = str(
        raw.get("name")
        or raw.get("plant_name")
        or raw.get("title")
        or raw.get("이름ko")
        or raw.get("이름_en")
        or ""
    ).strip()

    raw_min = raw.get("min") or raw.get("min_light") or raw.get("light_min") or raw.get("광량_min")
    raw_max = raw.get("max") or raw.get("max_light") or raw.get("light_max") or raw.get("광량_max")

    mn = _to_float(raw_min)
    if mn is None:
        mn = _light_level_value(raw_min)
    mx = _to_float(raw_max)
    if mx is None:
        mx = _light_level_value(raw_max)

    if mn is None or mx is None:
        range_val = raw.get("광량") or raw.get("광량_범위")
        rmin, rmax = _parse_light_range(range_val)
        if mn is None:
            mn = rmin
        if mx is None:
            mx = rmax

    if mn is not None and mx is not None and mn > mx:
        mn, mx = mx, mn

    if not name or mn is None or mx is None:
        return None

    care_raw = raw.get("care") or raw.get("관리_난이도") or raw.get("관리_요구도")
    care = _parse_care_level(care_raw)
    if care is None:
        care = _to_int(raw.get("care"), 2)

    pet_safe = _pet_safe_from_raw(raw)
    if pet_safe is None:
        pet_safe = _to_bool(raw.get("pet_safe") if "pet_safe" in raw else raw.get("petSafe"), True)

    tags = []
    tags.extend(_normalize_tags(raw.get("tags")))
    tags.extend(_normalize_tags(raw.get("스타일_태그")))
    tags.extend(_normalize_tags(raw.get("기능성_정보")))

    temp_min = _to_float(raw.get("생육온도_min_C") or raw.get("생육온도_min") or raw.get("온도_min"))
    temp_max = _to_float(raw.get("생육온도_max_C") or raw.get("생육온도_max") or raw.get("온도_max"))

    humidity = _humidity_level(raw.get("습도_선호") or raw.get("습도"))

    window_range = raw.get("권장_창문거리_구간") or raw.get("권장_창문거리") or raw.get("창문거리")
    window_min, window_max = _parse_range_cm(window_range)

    plant = {
        "name": name,
        "min": mn,
        "max": mx,
        "pet_safe": pet_safe,
        "care": int(care),
        "tags": [t for t in tags if t],
        "temp_min_c": temp_min,
        "temp_max_c": temp_max,
        "humidity": humidity,
        "window_distance_min_cm": window_min,
        "window_distance_max_cm": window_max,
    }

    return plant


def _parse_json(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return None


def _json_get(r, key: str, path: str) -> Optional[Any]:
    try:
        raw = r.execute_command("JSON.GET", key, path)
    except Exception:
        return None
    if raw is None:
        return None
    return _parse_json(raw)


def _extract_plants_from_item(item: Any, item_prefix: str, r) -> List[Dict[str, Any]]:
    plants: List[Dict[str, Any]] = []
    if isinstance(item, dict):
        plant = _normalize_plant(item)
        if plant:
            plants.append(plant)
        return plants
    if isinstance(item, list):
        for sub in item:
            plants.extend(_extract_plants_from_item(sub, item_prefix, r))
        return plants
    if isinstance(item, str):
        parsed = _parse_json(item)
        if isinstance(parsed, (dict, list)):
            return _extract_plants_from_item(parsed, item_prefix, r)
        if item_prefix:
            plants.extend(_load_from_key(r, f"{item_prefix}{item}", item_prefix))
        return plants
    return plants


def _load_from_key(r, key: str, item_prefix: str) -> List[Dict[str, Any]]:
    plants: List[Dict[str, Any]] = []
    key_type = r.type(key)
    if key_type == "string":
        raw = r.get(key)
        if raw:
            plants.extend(_extract_plants_from_item(raw, item_prefix, r))
    elif key_type == "hash":
        plant = _normalize_plant(r.hgetall(key))
        if plant:
            plants.append(plant)
    elif key_type == "list":
        items = r.lrange(key, 0, -1)
        for item in items:
            plants.extend(_extract_plants_from_item(item, item_prefix, r))
    elif key_type == "set":
        items = r.smembers(key)
        for item in items:
            plants.extend(_extract_plants_from_item(item, item_prefix, r))
    elif key_type == "zset":
        items = [m for m, _ in r.zrange(key, 0, -1, withscores=True)]
        for item in items:
            plants.extend(_extract_plants_from_item(item, item_prefix, r))
    elif str(key_type).lower().startswith("rejson"):
        path = os.getenv("REDIS_PLANTS_JSON_PATH", "$")
        raw = _json_get(r, key, path)
        if raw is not None:
            plants.extend(_extract_plants_from_item(raw, item_prefix, r))

    if not plants:
        path = os.getenv("REDIS_PLANTS_JSON_PATH", "$")
        raw = _json_get(r, key, path)
        if raw is not None:
            plants.extend(_extract_plants_from_item(raw, item_prefix, r))
    return plants


def _load_from_prefix(r, prefix: str, item_prefix: str) -> List[Dict[str, Any]]:
    plants: List[Dict[str, Any]] = []
    cursor = 0
    pattern = f"{prefix}*"
    while True:
        cursor, keys = r.scan(cursor=cursor, match=pattern, count=200)
        for key in keys:
            plants.extend(_load_from_key(r, key, item_prefix))
        if cursor == 0:
            break
    return plants


def _range_score(value: Optional[float], mn: Optional[float], mx: Optional[float], soften: float) -> Optional[float]:
    if value is None or mn is None or mx is None:
        return None
    if mn <= value <= mx:
        return 1.0
    d = min(abs(value - mn), abs(value - mx))
    return float(1.0 / (1.0 + d / max(soften, 1e-6)))


def get_plants() -> List[Dict[str, Any]]:
    global _CACHE_TS, _CACHE_PLANTS
    cache_sec = int(os.getenv("REDIS_PLANTS_CACHE_SEC", "60"))
    now = time.time()
    if _CACHE_PLANTS is not None and now - _CACHE_TS < cache_sec:
        return _CACHE_PLANTS

    plants: List[Dict[str, Any]] = []
    r = get_redis()
    if r:
        key = os.getenv("REDIS_PLANTS_KEY", "").strip()
        prefix = os.getenv("REDIS_PLANTS_PREFIX", "").strip()
        index_key = os.getenv("REDIS_PLANTS_INDEX_KEY", "").strip()
        item_prefix = os.getenv("REDIS_PLANTS_ITEM_PREFIX", "").strip()

        try:
            if key:
                plants = _load_from_key(r, key, item_prefix)
            elif index_key:
                plants = _load_from_key(r, index_key, item_prefix)
            elif prefix:
                plants = _load_from_prefix(r, prefix, item_prefix)
        except Exception:
            plants = []

    plants = [p for p in plants if p.get("name") and p.get("min") is not None and p.get("max") is not None]
    if not plants:
        plants = PLANTS

    _CACHE_PLANTS = plants
    _CACHE_TS = now
    return plants

def plant_light_score(light_eff, p):
    mn, mx = float(p["min"]), float(p["max"])
    if mn <= light_eff <= mx:
        return 1.0
    d = (mn - light_eff) if light_eff < mn else (light_eff - mx)
    return float(1.0 / (1.0 + d * 2.0))

def plant_care_penalty(is_beginner, plant_care):
    try:
        c = int(plant_care)
    except:
        c = 2
    if is_beginner:
        return float({1: 0.0, 2: 0.15, 3: 0.35}.get(c, 0.2))
    else:
        return 0.0

def recommend_plants(light_eff: float, user_opts: Dict, topk: int = 5) -> List[Dict]:
    rec = []
    pet = bool((user_opts or {}).get("pet", False))
    is_beginner = bool((user_opts or {}).get("is_beginner", True))
    user_temp = _to_float((user_opts or {}).get("temp_c"))
    user_humidity = _humidity_level((user_opts or {}).get("humidity"))
    user_distance = _to_float((user_opts or {}).get("window_distance_cm"))

    for p in get_plants():
        if pet and (p.get("pet_safe", True) is False):
            continue

        ls = plant_light_score(float(light_eff), p)

        plant_care = p.get("care", 2) or 2
        pen = float(plant_care_penalty(is_beginner, plant_care))
        care_score = max(0.0, 1.0 - pen)

        temp_score = _range_score(user_temp, p.get("temp_min_c"), p.get("temp_max_c"), 5.0)
        humidity_score = None
        if user_humidity is not None and p.get("humidity") is not None:
            humidity_score = max(0.0, 1.0 - abs(float(user_humidity) - float(p.get("humidity"))))
        distance_score = _range_score(
            user_distance,
            p.get("window_distance_min_cm"),
            p.get("window_distance_max_cm"),
            50.0,
        )

        scores = [ls, care_score]
        weights = [0.70, 0.30]
        if temp_score is not None:
            scores.append(temp_score)
            weights.append(0.15)
        if humidity_score is not None:
            scores.append(humidity_score)
            weights.append(0.10)
        if distance_score is not None:
            scores.append(distance_score)
            weights.append(0.10)

        final = float(sum(s * w for s, w in zip(scores, weights)) / sum(weights))
        in_range = (float(p["min"]) <= float(light_eff) <= float(p["max"]))

        reason = []
        reason.append("광량 적합" if in_range else "광량 근접")
        if is_beginner:
            reason.append("초보 OK" if int(plant_care) <= 2 else "초보에 어려움")
        else:
            reason.append("관리 여유")

        rec.append({
            "name": p["name"],
            "score": float(final),
            "in_range": bool(in_range),
            "light_score": float(ls),
            "care_score": float(care_score),
            "temp_score": float(temp_score) if temp_score is not None else None,
            "humidity_score": float(humidity_score) if humidity_score is not None else None,
            "distance_score": float(distance_score) if distance_score is not None else None,
            "care": int(plant_care),
            "pet_safe": bool(p.get("pet_safe", True)),
            "reason": " / ".join(reason),
            "tags": p.get("tags", []),
            "min": float(p["min"]),
            "max": float(p["max"]),
            "temp_min_c": p.get("temp_min_c"),
            "temp_max_c": p.get("temp_max_c"),
            "humidity": p.get("humidity"),
            "window_distance_min_cm": p.get("window_distance_min_cm"),
            "window_distance_max_cm": p.get("window_distance_max_cm"),
        })

    rec.sort(key=lambda x: x["score"], reverse=True)
    return rec[:topk]
