import os
import json
import time
import glob
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from fastapi import Request

from app.config import RESULT_DIR


# =========================
# URL / PATH
# =========================
def abs_url(request: Request, path: str) -> str:
    base = str(request.base_url).rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"


def to_results_url(path_or_name: str) -> str:
    return f"/results/{os.path.basename(path_or_name)}"


def cache_bust_url(request: Request, path: str, ts_ms: Optional[int] = None) -> str:
    base = abs_url(request, path)
    if ts_ms is None:
        ts_ms = int(time.time() * 1000)
    joiner = "&" if "?" in base else "?"
    return f"{base}{joiner}t={ts_ms}"


# =========================
# CLIENT / TIME
# =========================
def client_key_from_request(request: Request) -> str:
    """
    ⚠️ 단독 host 기반은 위험(NAT/공유IP로 세션 섞임).
    가능하면 sid/cid를 우선 사용.
    - sid: chat_session에서 발급한 세션 id (cookie)
    - cid: stream에서 내려준 client id (cookie)
    """
    # 1) sid cookie
    sid = request.cookies.get("sid")
    if sid:
        return str(sid)

    # 2) cid cookie
    cid = request.cookies.get("cid")
    if cid:
        return str(cid)

    # 3) fallback: host
    host = getattr(getattr(request, "client", None), "host", None) or "unknown"
    return str(host)


def now_kst_yyyymmdd_hhmm() -> Tuple[str, str]:
    now = datetime.now()
    return now.strftime("%Y%m%d"), now.strftime("%H%M")


# =========================
# RESULT FILES
# =========================
def load_latest_result() -> Dict[str, Any]:
    latest_json = os.path.join(RESULT_DIR, "result_latest.json")
    if not os.path.exists(latest_json):
        return {}
    try:
        with open(latest_json, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def pick_latest_result_file(prefix: str) -> Optional[str]:
    pattern = os.path.join(RESULT_DIR, f"{prefix}*.png")
    files = glob.glob(pattern)
    if not files:
        return None
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files[0]


# =========================
# SCENE
# =========================
def scene_to_label(s: Any) -> str:
    if isinstance(s, str):
        return s
    if isinstance(s, dict):
        for k in ("label", "name", "title", "text", "value", "id", "scene_id", "scene"):
            v = s.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        try:
            return json.dumps(s, ensure_ascii=False)
        except Exception:
            return str(s)
    return str(s)


# =========================
# SAFE PARSE
# =========================
def safe_float(v) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def parse_hh_from_any(v) -> Optional[int]:
    """
    "HHMM" / "HH:MM" / "HH" / int / float 대응
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        hh = int(v)
        return hh if 0 <= hh <= 23 else None

    s = str(v).strip()
    if not s:
        return None

    if ":" in s:
        try:
            hh = int(s.split(":")[0])
            return hh if 0 <= hh <= 23 else None
        except Exception:
            return None

    if len(s) >= 2 and s[:2].isdigit():
        try:
            hh = int(s[:2])
            return hh if 0 <= hh <= 23 else None
        except Exception:
            return None

    return None


# =========================
# BEST POINT
# =========================
def extract_best_point(data: Dict[str, Any]) -> Optional[Any]:
    if not isinstance(data, dict):
        return None

    best_spot = data.get("best_spot")
    if isinstance(best_spot, dict):
        pt = best_spot.get("pt")
        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
            return pt

    spots = data.get("spots")
    if isinstance(spots, list) and spots:
        s0 = spots[0]
        if isinstance(s0, dict):
            pt = s0.get("pt")
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                return pt

    bp = data.get("best_point")
    if isinstance(bp, (list, tuple)) and len(bp) >= 2:
        return bp
    if isinstance(bp, dict) and ("x" in bp and "y" in bp):
        return bp

    return None


# =========================
# META → LAT/LON
# =========================
def get_lat_lot_from_meta(meta):
    import json

    if meta is None:
        return None

    # str -> dict
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            return None

    if not isinstance(meta, dict):
        return None

    # ✅ 후보 dict들을 순서대로 훑기 (중첩 구조 대비)
    candidates = [meta]
    for k in ("location", "coords", "gps", "geo"):
        v = meta.get(k)
        if isinstance(v, dict):
            candidates.append(v)

    def pick(d: dict):
        lat = d.get("lat", d.get("latitude"))
        lot = d.get("lot")
        if lot is None: lot = d.get("lon")
        if lot is None: lot = d.get("lng")
        if lot is None: lot = d.get("longitude")
        if lat is None or lot is None:
            return None
        try:
            return {"lat": float(lat), "lot": float(lot)}
        except Exception:
            return None

    for d in candidates:
        out = pick(d)
        if out:
            return out

    return None


# =========================
# JSON SAFE (추가)
# =========================
def to_jsonable(x: Any) -> Any:
    """
    json.dump 실패 방지용.
    - numpy/torch 등 객체가 섞일 때 대비
    """
    try:
        json.dumps(x, ensure_ascii=False)
        return x
    except Exception:
        return str(x)


def read_json_safely(path: str) -> Dict[str, Any]:
    """
    결과 json 읽기 공통화 (load_latest_result랑 역할 분리 가능)
    """
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}