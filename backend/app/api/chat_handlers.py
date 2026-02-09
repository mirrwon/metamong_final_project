from __future__ import annotations

import os, json, time, random, uuid, pathlib, glob, inspect, hashlib, requests, shutil
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from dotenv import load_dotenv

from fastapi import UploadFile, File, Form, Request
from fastapi.responses import JSONResponse
from urllib.parse import urlparse

from app.cv.pipeline import run_pipeline, list_71765_scenes
from app.cv.space_classifier import classify_space
from app.cv.scene_room_infer import infer_room_type_from_scene_json, load_scene_json
from app.cv.scene_catalog import build_room_groups, DEFAULT_SCENE_ROOT, pick_scene_for_room

from app.config import BASE_DIR, RESULT_DIR, RESULT_JSON_LATEST, UPLOAD_DIR, ASSET_DIR
from app.llm.image_edit import composite_plant_on_original
from app.llm.gemini.gemini_image_edit import gemini_edit_image
from app.solar.weather_client import AsosWeatherClient
from app.reco.recommender import recommend_for_analysis

from .chat_session import _get_or_create_sid, _json_with_sid, _get_client_id
from .chat_storage import get_user_ctx, set_user_ctx
from .chat_utils import cache_bust_url, to_results_url, extract_best_point, safe_float

load_dotenv()
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)

weather_client = AsosWeatherClient()

# =========================
# Models
# =========================

class AnalyzeBody(BaseModel):
    filters: Dict[str, Any] = Field(default_factory=dict)
    meta: Optional[Dict[str, Any]] = None

class RecommendBody(BaseModel):
    filters: Dict[str, Any] = Field(default_factory=dict)
    meta: Optional[Dict[str, Any]] = None


async def handle_chat_recommend(request: Request, body: RecommendBody) -> JSONResponse:
    sid, sid_is_new = _get_or_create_sid(request)
    key = sid

    # 1) 기존 분석 결과 로드
    latest_json = os.path.join(RESULT_DIR, "result_latest.json")
    if not os.path.exists(latest_json):
        return _json_with_sid(
            {"ok": False, "messages": [{"type": "text", "text": "저장된 분석 결과가 없습니다. 먼저 analyze를 실행하세요."}]},
            sid, sid_is_new
        )

    try:
        with open(latest_json, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return _json_with_sid(
            {"ok": False, "messages": [{"type": "text", "text": f"result_latest.json 읽기 실패: {e}"}]},
            sid, sid_is_new
        )

    # 2) 필터 저장 + 추천만 재실행
    user_filters = body.filters if isinstance(body.filters, dict) else {}
    set_user_ctx(key, {"filters": user_filters}, ttl_sec=60 * 60 * 6)

    data = recommend_for_analysis(data, user_filters=user_filters)

    # 3) 저장
    try:
        with open(latest_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[WARN] overwrite latest_json failed:", e)

    # 4) 프론트가 쓰기 쉬운 응답
    return _json_with_sid(
        {
            "ok": True,
            "messages": [{"type": "text", "text": "✅ 필터가 적용되어 추천 결과를 갱신했습니다."}],
            "cv_result": data,
        },
        sid, sid_is_new
    )

def _pick_scene_for_room_compat(room_type: str, seed: Optional[str] = None):
    """
    room_type(거실/침실/주방/욕실 또는 영어 변형)를 받아서
    DEFAULT_SCENE_ROOT 기준으로 scene_id를 하나 뽑아 반환한다. (없으면 None)
    """
    rt = (room_type or "").strip()
    rt_key = rt.replace(" ", "").lower()

    rt_map = {
        "거실": "거실", "침실": "침실", "주방": "주방", "욕실": "욕실",
        "livingroom": "거실", "living_room": "거실", "living": "거실",
        "bedroom": "침실", "bed_room": "침실",
        "kitchen": "주방",
        "bathroom": "욕실", "bath_room": "욕실", "restroom": "욕실", "toilet": "욕실",
    }
    room_kor = rt_map.get(rt, rt_map.get(rt_key, rt))

    # ✅ groups를 반드시 dict로 만든 뒤 pick_scene_for_room(groups, room_type)로만 호출
    try:
        groups = build_room_groups(DEFAULT_SCENE_ROOT)
        if not isinstance(groups, dict):
            print("[pick_scene_compat][WARN] groups is not dict:", type(groups))
            return None

        picked = pick_scene_for_room(groups, room_kor, seed=seed)
        return picked
    except Exception as e:
        print("[pick_scene_compat][WARN] build/pick failed:", e)
        return None



# ✅ room groups(options)만
def get_scenes():
    groups = build_room_groups(DEFAULT_SCENE_ROOT)

    options = []
    for k in ["거실", "침실", "주방", "욕실"]:
        cnt = len(groups.get(k) or [])
        options.append({"key": k, "label": f"{k} ({cnt})"})

    return {"ok": True, "type": "room_groups", "options": options}

# ✅ 전체 scene 리스트(라벨 포함) 반환
def get_scenes_all():
    root = pathlib.Path(DEFAULT_SCENE_ROOT)
    scenes = list_71765_scenes()

    out = []
    for sid in scenes:
        scene_json = load_scene_json(root, sid)
        if not scene_json:
            continue

        room_type = infer_room_type_from_scene_json(scene_json)

        meta = scene_json.get("metadata", {}) if isinstance(scene_json, dict) else {}
        space_subclass = meta.get("space_subclass") or ""
        space_detail = meta.get("space_detail") or ""

        label = f"{space_subclass} / {room_type}".strip(" /")
        if space_detail:
            label += f" ({space_detail})"

        out.append({"id": sid, "label": label})

    return {"ok": True, "scenes": out}

def get_results():
    """
    프론트가 /api/chat/results로 받아갈 '최신 결과 메타'를 반환.
    필요하면 형식은 프론트에 맞춰 확장.
    """
    latest_json_path = str(RESULT_JSON_LATEST)
    exists = os.path.exists(latest_json_path)

    # 최신 결과 이미지들(예: result_latest_*.png) 목록
    files = sorted(
        [os.path.basename(p) for p in glob.glob(os.path.join(str(RESULT_DIR), "result_latest_*.png"))]
    )

    return JSONResponse({
        "ok": True,
        "latest_json_exists": exists,
        "latest_json": os.path.basename(latest_json_path),
        "latest_images": files,
    })

# =========================
# Detail text -> constraints (원본 유지)
# =========================
def parse_detail_text_to_constraints(text: str) -> Dict[str, Any]:
    t = (text or "").strip().lower()

    placement = None
    if any(k in t for k in ["테이블", "상판", "선반", "책상"]):
        placement = "table"
    elif any(k in t for k in ["바닥", "플로어", "바닥에"]):
        placement = "floor"

    light_pref = None
    if any(k in t for k in ["햇빛없", "빛없", "어두", "그늘", "저광량"]):
        light_pref = "low"
    elif any(k in t for k in ["햇빛많", "직사광", "고광량", "밝은곳"]):
        light_pref = "high"
    elif any(k in t for k in ["반그늘", "중간", "간접광", "중광량"]):
        light_pref = "medium"

    pet = None
    if any(k in t for k in ["반려묘", "고양이", "강아지", "반려동물"]):
        pet = True

    size = None
    if any(k in t for k in ["큰", "대형", "키큰"]):
        size = "large"
    elif any(k in t for k in ["작은", "소형", "미니"]):
        size = "small"
    elif any(k in t for k in ["중형", "적당한"]):
        size = "medium"

    return {
        "raw_text": text,
        "placement": placement,
        "light_pref": light_pref,
        "size_pref": size,
        "pet_hint": pet,
    }


# =========================
# Gemini prompt builder (원본 유지)
# =========================
def _prompt_for_edit(best_point: Any, spot_usage: str, plant_name: Optional[str] = None) -> str:
    plant_text = plant_name or "실내 화분 식물"

    base_rules = (
        "원본 방 사진은 절대 변경하지 마세요. "
        "가구/창문/바닥/벽/조명/원근/구도는 그대로 유지하세요. "
        "초록색 점으로 표시된 위치에서 반경 40픽셀 이내에만 식물을 배치하세요. "
        "식물은 현실적인 크기와 그림자, 접지감을 가지게 하세요. "
        "다른 물체를 추가/삭제하지 마세요. "
        f"(추천 좌표: {best_point}) "
    )

    if spot_usage == "floor_large":
        mode_rules = (
            f"{plant_text}를 바닥(FLOOR)에 설치하세요. "
            "테이블, 선반, 가구 위에 두지 마세요. "
            "중형~대형 화분으로 표현하세요 (높이 40~90cm). "
        )
    elif spot_usage == "table_small":
        mode_rules = (
            f"{plant_text}를 테이블 또는 상판(TABLETOP)에 올려주세요. "
            "바닥에 두지 마세요. "
            "소형 화분으로 표현하세요 (높이 15~35cm). "
        )
    elif spot_usage == "low_light":
        mode_rules = (
            f"{plant_text}를 저광량 환경에 적합하게 배치하세요. "
            "강한 햇빛을 가정하지 마세요. "
            "소형~중형 화분으로 표현하세요. "
        )
    else:
        mode_rules = f"{plant_text}를 가장 자연스럽고 안전한 방식으로 소형 화분으로 배치하세요. "

    return base_rules + mode_rules


# =========================
# SOLAR helpers (원본 유지)
# =========================
def _solar_summary_from_asos(weather_res: Dict[str, Any]) -> Dict[str, Any]:
    """
    AsosWeatherClient에서 받은 단일 실측 데이터를
    기존 시스템이 이해하는 morning/noon/evening 구조로 변환합니다.
    """
    out = {
        "ok": False,
        "times": {"morning": 0.0, "noon": 0.0, "evening": 0.0},
        "source": "kma_asos",
        "reason": "",
    }

    if not weather_res:
        out["reason"] = "weather_data_empty"
        return out

    # ASOS 실측값 가져오기
    try:
        val = float(weather_res.get("solar_radiation") or 0.0)
    except (ValueError, TypeError):
        val = 0.0

    # 시간 파싱 보강 (observed_at 대응)
    obs_time = str(weather_res.get("observed_at") or "")
    hh = 12 # 기본값

    try:
        if " " in obs_time:
            # "2026-02-03 12" 형식 대응
            hh = int(obs_time.split()[-1].split(":")[0])
        elif len(obs_time) >= 10:
            # "202602031200" 형식 대응 (뒤에서 4~2번째 자리)
            hh = int(obs_time[-4:-2])
    except Exception:
        hh = 12 # 에러 시 정오로 간주

    # 현재 실측된 값을 해당 시간대에 할당
    if 6 <= hh <= 10:
        out["times"]["morning"] = val
    elif 11 <= hh <= 15:
        out["times"]["noon"] = val
    elif 16 <= hh <= 19:
        out["times"]["evening"] = val
    else:
        # 야간(0.0)이거나 범위를 벗어나면 noon에 할당하여 가중치 0으로 처리
        out["times"]["noon"] = val

    out["ok"] = True
    return out


def _normalize_3(t: Dict[str, Optional[float]]) -> Dict[str, float]:
    m = safe_float(t.get("morning")) or 0.0
    n = safe_float(t.get("noon")) or 0.0
    e = safe_float(t.get("evening")) or 0.0
    mx = max(m, n, e)
    if mx <= 0:
        return {"morning": 1.0, "noon": 1.0, "evening": 1.0}
    return {"morning": m / mx, "noon": n / mx, "evening": e / mx}


def _clip01(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def _apply_solar_to_spots(data: Dict[str, Any], solar_summary: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return data
    spots = data.get("spots")
    if not isinstance(spots, list) or not spots:
        return data

    solar_times = (solar_summary or {}).get("times") if isinstance(solar_summary, dict) else None
    if not isinstance(solar_times, dict):
        return data

    scale = _normalize_3(solar_times)

    for s in spots:
        if not isinstance(s, dict):
            continue

        feats = s.get("features")
        if isinstance(feats, dict):
            times = feats.get("times")
            if isinstance(times, dict):
                if "times_cv" not in feats:
                    feats["times_cv"] = dict(times)

                feats["times"] = {
                    "morning": _clip01((safe_float(times.get("morning")) or 0.0) * scale["morning"]),
                    "noon": _clip01((safe_float(times.get("noon")) or 0.0) * scale["noon"]),
                    "evening": _clip01((safe_float(times.get("evening")) or 0.0) * scale["evening"]),
                }

        lp = s.get("light_profile")
        if isinstance(lp, dict):
            lpt = lp.get("times")
            if isinstance(lpt, dict):
                if "times_cv" not in lp:
                    lp["times_cv"] = dict(lpt)

                new_lpt = {
                    "morning": _clip01((safe_float(lpt.get("morning")) or 0.0) * scale["morning"]),
                    "noon": _clip01((safe_float(lpt.get("noon")) or 0.0) * scale["noon"]),
                    "evening": _clip01((safe_float(lpt.get("evening")) or 0.0) * scale["evening"]),
                }
                lp["times"] = new_lpt
                lp["bias"] = max(new_lpt.items(), key=lambda kv: kv[1])[0] if new_lpt else "unknown"

    data["solar_apply"] = {
        "ok": True,
        "scale": scale,
        "note": "features.times and light_profile.times multiplied by normalized solar_summary.times; originals kept in *_times_cv",
    }
    return data

# =========================
# /api/chat (POST) handler
# =========================
async def handle_chat_post(request: Request) -> JSONResponse:
    # 1/2/3 페이지 분리 이후, chat 텍스트 플로우는 사용하지 않음.
    # (프론트가 실수로 호출해도 깨지지 않도록 최소 응답만 반환)
    sid, sid_is_new = _get_or_create_sid(request)
    return _json_with_sid(
        {
            "ok": True,
            "deprecated": True,
            "messages": [
                {"type": "text", "text": "이 엔드포인트(/api/chat POST)는 더 이상 사용하지 않습니다. /api/chat/image 및 /api/chat/analyze를 사용하세요."}
            ],
        },
        sid,
        sid_is_new,
    )


def _run_pipeline_compat(save_path: str, user_opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    run_pipeline 파라미터명이 환경마다 달라서 scene_id가 씹히는 문제를 막기 위한 호환 호출.
    - user_opts / opts / options / kwargs 등 다양한 케이스를 순서대로 시도한다.
    """
    user_opts = user_opts or {}

    # 1) 시그니처 기반으로 가능한 키워드만 시도
    try:
        sig = inspect.signature(run_pipeline)
        params = sig.parameters

        if "user_opts" in params:
            return run_pipeline(save_path, user_opts=user_opts)
        if "opts" in params:
            return run_pipeline(save_path, opts=user_opts)
        if "options" in params:
            return run_pipeline(save_path, options=user_opts)
        if "config" in params:
            # 일부 구현에서 config dict를 받는 경우가 있음
            return run_pipeline(save_path, config=user_opts)
    except Exception:
        # signature 조회 실패하면 아래 fallback들로 간다
        pass

    # 2) 키워드 시도(실패하면 다음으로)
    try:
        return run_pipeline(save_path, user_opts=user_opts)
    except TypeError:
        pass
    try:
        return run_pipeline(save_path, opts=user_opts)
    except TypeError:
        pass
    try:
        return run_pipeline(save_path, options=user_opts)
    except TypeError:
        pass

    # 3) 최후 fallback: opts를 못 받으면 그냥 호출 (단, 이 경우 scene_id 반영 불가)
    return run_pipeline(save_path)

# =========================
# /api/chat/image handler (UPLOAD + ROOM ONLY)
# =========================
async def handle_chat_image(
    request: Request,
    files: Optional[List[UploadFile]] = File(None),
    image: Optional[UploadFile] = File(None),
    meta: Optional[str] = Form(None),
    scene_id: Optional[str] = Form(None),
    room_type: Optional[str] = Form(None),
) -> JSONResponse:
    sid, sid_is_new = _get_or_create_sid(request)
    key = sid
    cid = _get_client_id(request) or sid
    # cid = sid

    upload: Optional[UploadFile] = None
    if files and len(files) > 0:
        upload = files[0]
    elif image is not None:
        upload = image

    if upload is None:
        return _json_with_sid(
            {
                "ok": False,
                "messages": [{"type": "text", "text": "업로드 파일이 없습니다."}],
            },
            sid,
            sid_is_new,
        )

    # 1) 저장
    orig_name = upload.filename or "upload.jpg"
    ext = pathlib.Path(orig_name).suffix or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(UPLOAD_DIR, filename)

    content = await upload.read()
    with open(save_path, "wb") as f:
        f.write(content)

    # ctx에 무조건 저장 (2번에서 analyze가 이걸 씀)
    set_user_ctx(key, {"last_image_path": save_path}, ttl_sec=60 * 60 * 6)

    # meta도 ctx에 저장 (태양광/좌표용)
    if meta:
        m = meta
        try:
            # meta가 JSON 문자열이면 dict로 저장
            if isinstance(m, str) and m.strip().startswith("{"):
                m = json.loads(m)
        except Exception:
            m = meta  # 파싱 실패 시 원문 유지
        set_user_ctx(key, {"meta": m}, ttl_sec=60 * 60 * 6)

    # 2) room_type/scene_id 확정 로직
    user_opts: Dict[str, Any] = {}

    # (A) 사용자가 scene_id를 직접 보내면 최우선
    if scene_id:
        user_opts["scene_id"] = scene_id
        set_user_ctx(key, {"scene_id": scene_id}, ttl_sec=60 * 60 * 6)
        return _json_with_sid(
            {
                "ok": True,
                "need_room_type": False,
                "next": "preferences",
                "saved_image": filename,
            },
            sid,
            sid_is_new,
        )

    # (B) room_type이 왔다면 -> scene_id 픽해서 확정
    if room_type:
        try:
            picked = _pick_scene_for_room_compat(room_type)
        except Exception as e:
            return _json_with_sid(
                {"ok": False, "messages": [{"type": "text", "text": f"room_type 처리 오류: {e}"}]},
                sid,
                sid_is_new,
            )

        if not picked:
            # ✅ 강제 진행: room_type은 저장하고 scene_id 없이도 survey/analyze로 넘긴다
            set_user_ctx(key, {"room_type": str(room_type).strip()}, ttl_sec=60 * 60 * 6)

            return _json_with_sid(
                {
                    "ok": True,
                    "need_room_type": False,
                    "next": "preferences",
                    "room_type": str(room_type).strip(),
                    "scene_id": None,
                    "saved_image": filename,
                    "note": "scene_id_pick_failed_but_forced_next",
                },
                sid,
                sid_is_new,
            )

        # room_type -> scene_id 확정 저장
        set_user_ctx(key, {"room_type": str(room_type).strip(), "scene_id": picked}, ttl_sec=60 * 60 * 6)

        return _json_with_sid(
            {
                "ok": True,
                "need_room_type": False,
                "next": "preferences",
                "room_type": str(room_type).strip(),
                "scene_id": picked,
                "saved_image": filename,
            },
            sid,
            sid_is_new,
        )

    # (C) 아무것도 안 왔으면 -> 일단 pipeline 1회 돌려보고
    # scene_required 뜨면 room_type 선택 요구, 아니면 자동으로 preferences로
    try:
        out = _run_pipeline_compat(save_path, user_opts={})  # scene_id 없이 1회
    except Exception as e:
        return _json_with_sid(
            {"ok": False, "messages": [{"type": "text", "text": f"분석(1차) 중 오류: {e}"}]},
            sid,
            sid_is_new,
        )

    scene_info = out.get("scene") if isinstance(out, dict) else None
    if isinstance(scene_info, dict) and scene_info.get("reason") == "scene_required":
        return _json_with_sid(
            {
                "ok": True,
                "need_room_type": True,
                "payload": {"type": "room_type_required", "options": ["거실", "침실", "주방", "욕실"]},
                "saved_image": filename,
            },
            sid,
            sid_is_new,
        )

    # ✅ scene_required가 아니더라도 pipeline이 scene을 자동 확정했으면 ctx에 저장
    # (out 구조가 달라도 안전하게 key 여러 개 시도)
    if isinstance(out, dict):
        sc = out.get("scene")
        chosen = None
        if isinstance(sc, dict):
            chosen = sc.get("chosen") or sc.get("scene_id") or sc.get("id")
        if isinstance(chosen, str) and chosen.strip():
            set_user_ctx(key, {"scene_id": chosen.strip()}, ttl_sec=60 * 60 * 6)

    # scene_required가 아니면 그냥 다음 단계로
    return _json_with_sid(
        {
            "ok": True,
            "need_room_type": False,
            "next": "preferences",
            "saved_image": filename,
        },
        sid,
        sid_is_new,
    )

# =========================
# render_plan → best_point 강제 반영 헬퍼
# =========================
def _best_point_from_spot(s: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(s, dict):
        return {}
    pt = None
    for k in ["pt", "point", "xy", "center"]:
        v = s.get(k)
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            pt = [float(v[0]), float(v[1])]
            break
        if isinstance(v, dict) and "x" in v and "y" in v:
            pt = [float(v["x"]), float(v["y"])]
            break
    if pt is None:
        feats = s.get("features")
        if isinstance(feats, dict):
            v = feats.get("pt") or feats.get("xy") or feats.get("center")
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                pt = [float(v[0]), float(v[1])]
            elif isinstance(v, dict) and "x" in v and "y" in v:
                pt = [float(v["x"]), float(v["y"])]
    return {"pt": pt, "spot_index": s.get("spot_index")}

def _choose_spot_by_render_plan(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    spots = data.get("spots")
    if not isinstance(spots, list) or not spots:
        return None

    # 1) render_plan이 있으면 그걸 최우선
    rp = data.get("render_plan")
    if isinstance(rp, dict):
        idxs = rp.get("spot_indexes")
        if isinstance(idxs, list) and idxs:
            try:
                i = int(idxs[0])
                if 0 <= i < len(spots) and isinstance(spots[i], dict):
                    return spots[i]
            except Exception:
                pass

    # 2) render_plan이 없거나 깨졌으면 기존 best_spot
    bs = data.get("best_spot")
    if isinstance(bs, dict):
        return bs

    # 3) 최후: 첫 spot
    return spots[0] if isinstance(spots[0], dict) else None



# =========================
# /api/chat/analyze handler (CV + RECO + IMAGES)
# =========================
async def handle_chat_analyze(request: Request, body: AnalyzeBody) -> JSONResponse:
    sid, sid_is_new = _get_or_create_sid(request)
    key = sid

    ctx = get_user_ctx(key) or {}
    save_path = ctx.get("last_image_path")
    scene_id = ctx.get("scene_id")
    room_type = ctx.get("room_type")

    if not save_path or not os.path.exists(str(save_path)):
        return _json_with_sid(
            {"ok": False, "messages": [{"type": "text", "text": "업로드된 이미지가 없습니다."}]},
            sid, sid_is_new,
        )

    user_filters = body.filters if isinstance(body.filters, dict) else {}
    set_user_ctx(key, {"filters": user_filters}, ttl_sec=60 * 60 * 6)

    # 1) CV 실행
    user_opts = {"scene_id": scene_id} if scene_id else {}
    try:
        out = _run_pipeline_compat(str(save_path), user_opts=user_opts)
    except Exception as e:
        return _json_with_sid(
            {"ok": False, "messages": [{"type": "text", "text": f"분석 중 오류: {e}"}]},
            sid, sid_is_new
        )

    data = out if isinstance(out, dict) else {}

    # CV 실행 직후 (out 받은 바로 다음)
    try:
        data["space"] = classify_space(data)
    except Exception as e:
        print("[WARN] classify_space failed:", e)
        data["space"] = {"type": "unknown", "reason": "classify_failed"}

    # ========================================================
    # 🚀 [기상청 ASOS 데이터 주입 및 보정]
    # ========================================================
    weather_res: Optional[Dict[str, Any]] = None

    try:
        weather_res = weather_client.fetch_growth_profile("108")
    except Exception as e:
        print("[WARN] weather_client failed:", e)

    if not isinstance(weather_res, dict):
        weather_res = {"ok": False, "reason": "weather_fetch_failed"}

    # --- 낮시간 테스트 (원하면 유지) ---
    weather_res["solar_radiation"] = "2.5"
    weather_res["ok"] = True
    # ---------------------------------

    data["solar"] = weather_res

    try:
        solar_summary = _solar_summary_from_asos(weather_res)
        if isinstance(solar_summary, dict) and solar_summary.get("ok"):
            data = _apply_solar_to_spots(data, solar_summary)
            print(f"☀️ 기상청 데이터 적용 성공: {weather_res.get('solar_radiation')} MJ/m2")
    except Exception as solar_err:
        print(f"☀️ 기상청 데이터 처리 중 최종 오류: {solar_err}")

    # =========================
    # 2) 추천 (보정된 data 전달)
    # =========================

    data = recommend_for_analysis(data, user_filters=user_filters)
    data["image_path"] = str(save_path)

    # ====== (A) spot 선택 정책 계산: small=table 1개, else=floor 3개(멀리) ======

    def _synthesize_table_spot(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        table 후보가 없을 때, 화면 중간 높이(바닥보다 위)에 '테이블용' spot 1개를 강제로 만든다.
        - 원근/깊이 기반 테이블 검출은 없으니, 최소 UX용 휴리스틱.
        - 나중에 CV에서 진짜 table 후보가 생기면 제거 가능.
        """
        w = int((data.get("image_w") or data.get("w") or 1248))
        h = int((data.get("image_h") or data.get("h") or 832))

        win = data.get("window") if isinstance(data.get("window"), dict) else None
        y = int(h * 0.62)
        x = int(w * 0.55)

        if isinstance(win, dict):
            bb = win.get("bbox") or win.get("xyxy") or win.get("box")
            if isinstance(bb, (list, tuple)) and len(bb) >= 4:
                x1, y1, x2, y2 = [int(v) for v in bb[:4]]
                x = int((x1 + x2) * 0.5)
                y = int(min(h * 0.75, y2 + (h * 0.10)))

        x = max(10, min(w - 10, x))
        y = max(10, min(h - 10, y))

        return {
            "spot_index": None,  # 아래에서 채움
            "surface": "table",  # ✅ 핵심 라벨
            "synthetic": True,
            "score": 999,
            "pt": [x, y],
            "features": {"center": [x, y], "pt": [x, y]},
        }

    def _spot_surface(s: Dict[str, Any]) -> str:
        if not isinstance(s, dict):
            return ""
        for k in ["surface", "spot_usage", "place", "placement", "spot_type"]:
            v = s.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip().lower()
        feats = s.get("features")
        if isinstance(feats, dict):
            for k in ["surface", "place", "placement", "spot_type"]:
                v = feats.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip().lower()
        return ""

    def _spot_index_value(s: Dict[str, Any], fallback: int) -> int:
        if not isinstance(s, dict):
            return fallback
        v = s.get("spot_index", s.get("index", fallback))
        try:
            return int(v)
        except Exception:
            return fallback

    def _pick_one_table_spot(spots: List[Dict[str, Any]]) -> Optional[int]:
        table_like = []
        for i, s in enumerate(spots):
            surf = _spot_surface(s)
            if any(x in surf for x in ["table", "desk", "shelf", "counter", "stand"]):
                table_like.append(i)
        if table_like:
            return table_like[0]

        non_floor = []
        for i, s in enumerate(spots):
            surf = _spot_surface(s)
            if surf and ("floor" not in surf):
                non_floor.append(i)
        if non_floor:
            return non_floor[0]

        return None

    def _get_spot_pt(s: Dict[str, Any]):
        for k in ["pt", "point", "xy", "center"]:
            v = s.get(k)
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                return float(v[0]), float(v[1])
            if isinstance(v, dict) and "x" in v and "y" in v:
                return float(v["x"]), float(v["y"])
        feats = s.get("features")
        if isinstance(feats, dict):
            v = feats.get("pt") or feats.get("xy") or feats.get("center")
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                return float(v[0]), float(v[1])
            if isinstance(v, dict) and "x" in v and "y" in v:
                return float(v["x"]), float(v["y"])
        return None

    def _dist2(a, b):
        return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2

    def pick_far_spot_indexes(
            spots: List[Dict[str, Any]],
            k: int = 3,
            min_dist_px: int = 220,
            top_n: int = 12,
    ) -> List[int]:
        """
        목적: 서로 '멀리' 떨어진 spot index k개 선택

        개선점(분산 강화):
        - 1개는 점수 최상(기존 의도 유지)
        - 이후는 "현재 선택된 점들과의 최소거리"가 가장 큰 후보를 우선 선택 (farthest-point sampling)
        - strict 실패 시 threshold를 여러 단계로 점진 완화(relax pass)하여 k개를 반드시 채움
        - 후보 풀은 top_n보다 조금 넉넉히 사용(너무 가까운 고득점만 몰리는 것 방지)
        """

        def _get_pt(s: Dict[str, Any]):
            if not isinstance(s, dict):
                return None
            pt = s.get("pt")
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                return (float(pt[0]), float(pt[1]))

            feats = s.get("features")
            if isinstance(feats, dict):
                pt2 = feats.get("pt") or feats.get("center") or feats.get("xy")
                if isinstance(pt2, (list, tuple)) and len(pt2) >= 2:
                    return (float(pt2[0]), float(pt2[1]))
                if isinstance(pt2, dict) and "x" in pt2 and "y" in pt2:
                    return (float(pt2["x"]), float(pt2["y"]))
            return None

        def _score(s: Dict[str, Any]) -> float:
            if not isinstance(s, dict):
                return 0.0
            v = s.get("final_score")
            if v is None:
                v = s.get("score")
            try:
                return float(v)
            except Exception:
                return 0.0

        def _dist2(a, b) -> float:
            dx = a[0] - b[0]
            dy = a[1] - b[1]
            return dx * dx + dy * dy

        # 0) 후보 수집
        cand = []
        for i, s in enumerate(spots):
            pt = _get_pt(s)
            if pt is None:
                continue
            cand.append((i, pt, _score(s)))

        if not cand:
            return [0]

        # 1) 점수 내림차순 정렬
        cand.sort(key=lambda x: x[2], reverse=True)

        # 2) 후보 풀: top_n만 쓰면 같은 클러스터 고득점에 몰릴 수 있어 조금 확장
        #    (외부 호출부는 건드리지 않고, 내부에서만 풀을 넓힘)
        pool_n = max(top_n, k * 10, 30)
        cand_pool = cand[:min(len(cand), pool_n)]

        # 3) 첫 선택: 최고 점수 1개(기존 의도 유지)
        chosen: List[int] = [cand_pool[0][0]]
        chosen_pts = [cand_pool[0][1]]

        # 4) relax 단계: min_dist를 여러 단계로 완화하며 채움
        #    (strict -> 점진 완화 -> 최후 0)
        relax_factors = [1.00, 0.90, 0.80, 0.70, 0.55, 0.40, 0.0]

        for rf in relax_factors:
            if len(chosen) >= k:
                break

            d_thr = float(min_dist_px) * float(rf)
            d2_thr = d_thr * d_thr

            # farthest-point sampling:
            # 아직 안 뽑힌 후보 중에서 "선택된 점들까지의 최소거리(minDist)"가 가장 큰 후보를 고름
            while len(chosen) < k:
                best_idx = None
                best_pt = None
                best_min_d2 = -1.0
                best_sc = -1.0

                for idx, pt, sc in cand_pool:
                    if idx in chosen:
                        continue

                    # chosen에 대한 최소 거리
                    min_d2 = min(_dist2(pt, cp) for cp in chosen_pts)

                    # threshold 통과 후보만 우선
                    if min_d2 < d2_thr:
                        continue

                    # 1순위: min_d2 큰 것(멀리)
                    # 2순위: 점수(sc) 큰 것
                    if (min_d2 > best_min_d2) or (min_d2 == best_min_d2 and sc > best_sc):
                        best_min_d2 = min_d2
                        best_sc = sc
                        best_idx = idx
                        best_pt = pt

                if best_idx is None:
                    break  # 이 relax 단계에서 더는 못 고름 → 다음 relax로

                chosen.append(best_idx)
                chosen_pts.append(best_pt)

        # 5) 최후 보정: relax를 다 돌았는데도 부족하면 그냥 점수순으로 채움(중복 없이)
        if len(chosen) < k:
            for idx, pt, sc in cand_pool:
                if idx not in chosen:
                    chosen.append(idx)
                if len(chosen) >= k:
                    break

        # 6) 안전: 그래도 0개면 0
        if not chosen:
            return [0]

        return chosen[:k]

    # ---- 실제 render_plan 적용 ----
    spots = data.get("spots") if isinstance(data, dict) else None
    if isinstance(spots, list) and spots:
        # ✅ 소형 여부 판단
        size_pref = None
        if isinstance(user_filters, dict):
            size_pref = user_filters.get("size") or user_filters.get("size_pref")
        if not size_pref and isinstance(data.get("constraints"), dict):
            size_pref = data["constraints"].get("size_pref")
        size_pref = (str(size_pref).lower().strip() if size_pref else "")

        if size_pref == "small":
            # 1) 진짜 table 후보 있으면 사용
            table_idx = _pick_one_table_spot(spots)

            # 2) 없으면 fake table spot 추가 후 그 인덱스를 사용 (✅ 바닥 fallback 제거)
            if table_idx is None:
                fake = _synthesize_table_spot(data)
                if fake:
                    fake["spot_index"] = len(spots)
                    spots.append(fake)
                    data["spots"] = spots
                    # table_idx = fake["spot_index"]
                    table_idx = len(spots) - 1
                else:
                    # fake 생성도 실패하면 마지막 fallback (여기까지 올 일 거의 없음)
                    table_idx = _spot_index_value(spots[0], 0)

            data["render_plan"] = {"count": 1, "spot_indexes": [table_idx], "reason": "table_small"}

        else:
            idxs = pick_far_spot_indexes(spots, k=3, min_dist_px=180)
            data["render_plan"] = {"count": 3, "spot_indexes": idxs, "reason": "floor_large"}

    # ✅ render_plan이 실제 합성 좌표(best_point) / best_spot에 반영되게 강제
    chosen_spot = _choose_spot_by_render_plan(data)
    if isinstance(chosen_spot, dict):
        data["best_spot"] = chosen_spot  # pick_spot 등 다른 플로우도 일관되게
        forced_best_point = _best_point_from_spot(chosen_spot)
    else:
        forced_best_point = None

    # ✅ 핵심: 합성에 쓰이는 좌표(best_point)까지 render_plan 기반으로 강제 고정
    if isinstance(forced_best_point, dict) and forced_best_point.get("pt"):
        data["best_point"] = {"pt": forced_best_point["pt"], "spot_index": forced_best_point.get("spot_index")}
        # 호환용 키들도 같이 박아두면 extract_best_point 구현이 뭐든 안 흔들림
        data["best_pt"] = forced_best_point["pt"]

    # 3) 결과 저장
    latest_json = os.path.join(RESULT_DIR, "result_latest.json")
    marker_path = os.path.join(RESULT_DIR, "result_latest_marker.png")
    composite_path = os.path.join(RESULT_DIR, "result_latest_composite.png")
    ai_edit_path = os.path.join(RESULT_DIR, "result_latest_ai_edit.png")

    try:
        with open(latest_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[WARN] write result_latest.json failed:", e)

    # 4) 결과 이미지 생성
    rp = data.get("render_plan") if isinstance(data, dict) else None
    render_idxs: List[int] = []

    if isinstance(rp, dict):
        idxs = rp.get("spot_indexes")
        if isinstance(idxs, list):
            for x in idxs:
                try:
                    i = int(x)
                    if 0 <= i < len(data.get("spots") or []):
                        render_idxs.append(i)
                except Exception:
                    pass

    # fallback
    if not render_idxs:
        render_idxs = [0]

    # 중복 제거
    render_idxs = list(dict.fromkeys(render_idxs))

    plant_asset = os.path.join(BASE_DIR, "assets", "plants", "default.png")
    plant_asset = plant_asset if os.path.exists(plant_asset) else None

    # analyze에서는 marker/composite/ai_edit를 "spot별로" 생성
    spot_images: List[Dict[str, Any]] = []
    ts_ms = int(time.time() * 1000)

    spots = data.get("spots") if isinstance(data, dict) else []
    for ridx in render_idxs[:3]:
        if not (0 <= ridx < len(spots)):
            continue
        bp = _best_point_from_spot(spots[ridx])
        if not isinstance(bp, dict) or not bp.get("pt"):
            continue

        marker_path = os.path.join(RESULT_DIR, f"result_latest_marker_spot_{ridx}.png")
        composite_path = os.path.join(RESULT_DIR, f"result_latest_composite_spot_{ridx}.png")
        ai_edit_path = os.path.join(RESULT_DIR, f"result_latest_ai_edit_spot_{ridx}.png")

        # marker (점)
        composite_plant_on_original(
            original_image_path=str(save_path),
            best_point_obj=bp,
            out_path=marker_path,
            plant_png_path=None,
            plant_width_ratio=0.22,
            anchor="bottom_center",
            add_green_dot=True,
        )

        # composite (붙이기)
        composite_plant_on_original(
            original_image_path=str(save_path),
            best_point_obj=bp,
            out_path=composite_path,
            plant_png_path=plant_asset,
            plant_width_ratio=0.22,
            anchor="bottom_center",
            add_green_dot=False,
        )

        # gemini 편집 (옵션)
        try:
            prompt = _prompt_for_edit(bp, spot_usage=(rp.get("reason") if isinstance(rp, dict) else "floor_large"))
            gemini_edit_image(input_image_path=composite_path, prompt=prompt, out_path=ai_edit_path)
        except Exception as e:
            print("[WARN] gemini_edit_image failed:", e)

        # payload 추가 (ai_edit 우선, 없으면 composite)
        if os.path.exists(ai_edit_path):
            spot_images.append({"name": "ai_edit", "url": cache_bust_url(request, to_results_url(ai_edit_path), ts_ms)})
        elif os.path.exists(composite_path):
            spot_images.append(
                {"name": "composite", "url": cache_bust_url(request, to_results_url(composite_path), ts_ms)})

    # 5) 응답
    return _json_with_sid(
        {
            "ok": True,
            "images": spot_images,
            "cv_result": data,
        },
        sid,
        sid_is_new,
    )


# =========================
# Router-facing aliases
# =========================

async def chat_get(request: Request) -> JSONResponse:
    sid, sid_is_new = _get_or_create_sid(request)

    msgs = [
        {"type": "text", "text": "식물추천 AI입니다. 먼저 필터를 선택해주세요.", "payload": get_filters().get("payload")},
        # {"type": "text", "text": "필터를 선택해주세요.", "payload": get_filters().get("payload")},
        # {"type": "text", "text": "사진 업로드를 진행해주세요.", "payload": {"input": {"type": "image"}}},
    ]
    return _json_with_sid({"messages": msgs}, sid, sid_is_new)

async def chat_post(request: Request) -> JSONResponse:
    return await handle_chat_post(request)

async def chat_image(
    request: Request,
    files: Optional[List[UploadFile]] = File(None),
    image: Optional[UploadFile] = File(None),
    meta: Optional[str] = Form(None),
    scene_id: Optional[str] = Form(None),
    room_type: Optional[str] = Form(None),
) -> JSONResponse:
    return await handle_chat_image(request, files=files, image=image, meta=meta, scene_id=scene_id, room_type=room_type,)

# =========================
# Spot pick / Filters / Scenes
# =========================

class PickSpotBody(BaseModel):
    spot_index: int
    plant_id: Optional[str] = None
    plant_name: Optional[str] = None
    plant_image_url: Optional[str] = None
    regen: bool = False
    mode: Optional[str] = None

def _safe_ext_from_url(url: str) -> str:
    try:
        p = urlparse(url)
        ext = pathlib.Path(p.path).suffix.lower()
        if ext in [".png", ".jpg", ".jpeg", ".webp"]:
            return ext
    except Exception:
        pass
    return ".png"

def _download_image_cached(url: str, cache_dir: str, cache_key: str, regen: bool = False) -> Optional[str]:
    """
    S3(또는 외부) 이미지 URL을 로컬 파일로 다운로드해서 composite에서 사용할 수 있게 한다.
    regen=True면 캐시 무시하고 다시 받는다.
    """
    if not url or not isinstance(url, str):
        return None

    os.makedirs(cache_dir, exist_ok=True)

    ext = _safe_ext_from_url(url)
    h = hashlib.sha1((cache_key + "|" + url).encode("utf-8")).hexdigest()[:16]
    out_path = os.path.join(cache_dir, f"plant_{h}{ext}")

    if (not regen) and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        return out_path

    try:
        r = requests.get(url, timeout=10, stream=True)
        if r.status_code != 200:
            print(f"[PLANT_DL][WARN] status={r.status_code} url={url}")
            return None

        ctype = (r.headers.get("content-type") or "").lower()
        if "image" not in ctype:
            # 일부 S3는 content-type이 이상할 수 있어 경고만
            print(f"[PLANT_DL][WARN] non-image content-type={ctype} url={url}")

        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        if os.path.getsize(out_path) <= 0:
            print(f"[PLANT_DL][WARN] empty file url={url}")
            return None

        return out_path
    except Exception as e:
        print(f"[PLANT_DL][ERR] {e} url={url}")
        return None

def _find_plant_image_url(top_plants: Any, pid: str) -> Optional[str]:
    """
    top_plants(list[dict])에서 plant_id에 해당하는 이미지 URL을 찾아온다.
    (키 이름이 image / image_url / url 등 여러 형태일 수 있어서 다 대응)
    """
    if not pid or not isinstance(top_plants, list):
        return None

    for p in top_plants:
        if not isinstance(p, dict):
            continue
        cand_id = p.get("id") or p.get("plant_id")
        if cand_id is not None and str(cand_id) == str(pid):
            return p.get("image_url") or p.get("image") or p.get("url")
    return None


def get_filters():
    groups = [
        {"key": "experience", "label": "식물 경험", "options": ["초보자", "경험자"]},
        {"key": "pet", "label": "반려동물 여부", "options": ["예", "아니오"]},
    ]
    return {"groups": groups, "payload": {"type": "filters", "groups": groups}}

def _pick_plant_for_spot(top_plants: Any, spot_index: int) -> str:
    """
    - score 높은 식물 우선
    - 후보가 많아질수록 랜덤성 증가 (원본 로직 유지)
    """
    if not isinstance(top_plants, list) or len(top_plants) == 0:
        return "potted plant"

    ranked = sorted(
        [p for p in top_plants if isinstance(p, dict)],
        key=lambda x: x.get("score", 0),
        reverse=True,
    )

    if 0 <= spot_index < len(ranked):
        return ranked[spot_index].get("name") or "potted plant"

    weights = [max((p.get("score", 0.1) if isinstance(p, dict) else 0.1), 0.05) for p in ranked]
    chosen = random.choices(ranked, weights=weights, k=1)[0]
    return chosen.get("name") or "potted plant"


async def chat_pick_spot(request: Request, body: PickSpotBody) -> JSONResponse:
    sid, sid_is_new = _get_or_create_sid(request)
    key = sid

    regen = bool(getattr(body, "regen", False))
    mode_raw = getattr(body, "mode", None)
    mode = (str(mode_raw).strip().lower() if mode_raw is not None else "")

    latest_json = os.path.join(RESULT_DIR, "result_latest.json")
    if not os.path.exists(latest_json):
        return _json_with_sid(
            {"messages": [{"type": "text", "text": "저장된 분석 결과가 없습니다. 먼저 analyze를 실행하세요."}]},
            sid, sid_is_new,
        )

    try:
        with open(latest_json, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return _json_with_sid(
            {"messages": [{"type": "text", "text": f"결과 파일을 읽지 못했습니다: {e}"}]},
            sid, sid_is_new,
        )

    spots = data.get("spots")
    if not isinstance(spots, list) or not spots:
        return _json_with_sid(
            {"messages": [{"type": "text", "text": "spots가 없습니다. analyze를 다시 실행하세요."}]},
            sid, sid_is_new,
        )

    # =========================
    # 1) render_plan 기반 렌더 대상 spot index 결정
    # =========================
    rp = data.get("render_plan") if isinstance(data, dict) else None
    render_reason = None
    render_idxs: List[int] = []

    if isinstance(rp, dict):
        render_reason = (rp.get("reason") or "").lower().strip()
        idxs = rp.get("spot_indexes")
        if isinstance(idxs, list):
            for x in idxs:
                try:
                    i = int(x)
                    if 0 <= i < len(spots):
                        render_idxs.append(i)
                except Exception:
                    pass

    # fallback
    if not render_idxs:
        try:
            render_idxs = [int(body.spot_index)]
        except Exception:
            render_idxs = [0]
        render_reason = "manual"

    # ===== helper: spot surface 판단 =====
    def _spot_surface_local(s: Dict[str, Any]) -> str:
        if not isinstance(s, dict):
            return ""
        for k in ["surface", "spot_usage", "place", "placement", "spot_type"]:
            v = s.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip().lower()
        feats = s.get("features")
        if isinstance(feats, dict):
            for k in ["surface", "place", "placement", "spot_type"]:
                v = feats.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip().lower()
        return ""

    # ===== helper: table spot 없을 때 synthetic 생성 =====
    def _synthesize_table_spot_local(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        w = int((data.get("image_w") or data.get("w") or 1248))
        h = int((data.get("image_h") or data.get("h") or 832))
        x = int(w * 0.55)
        y = int(h * 0.62)  # 바닥보다 위

        win = data.get("window") if isinstance(data.get("window"), dict) else None
        if isinstance(win, dict):
            bb = win.get("bbox") or win.get("xyxy") or win.get("box")
            if isinstance(bb, (list, tuple)) and len(bb) >= 4:
                x1, y1, x2, y2 = [int(v) for v in bb[:4]]
                x = int((x1 + x2) * 0.5)
                y = int(min(h * 0.75, y2 + (h * 0.10)))

        x = max(10, min(w - 10, x))
        y = max(10, min(h - 10, y))

        return {
            "spot_index": None,
            "surface": "table",
            "synthetic": True,
            "score": 999,
            "pt": [x, y],
            "features": {"center": [x, y], "pt": [x, y]},
        }

    # ✅ small 판정은 1번만, sp는 항상 초기화
    ctx2 = get_user_ctx(key) or {}
    uf2 = ctx2.get("filters") if isinstance(ctx2, dict) else None

    def _norm_filter_value(v) -> str:
        if v is None:
            return ""
        if isinstance(v, list):
            for it in v:
                if isinstance(it, str) and it.strip():
                    return it.strip().lower()
            return ""
        if isinstance(v, str):
            return v.strip().lower()
        return ""

    sp = ""
    if isinstance(uf2, dict):
        for k in ("size", "size_pref", "plant_size", "pot_size"):
            cand = _norm_filter_value(uf2.get(k))
            if cand:  # ✅ 여기서 "small" 같은 유효 토큰만 채택
                sp = cand
                break

    is_small = (sp == "small")  # ✅ 최종은 small 토큰만 본다

    print(
        "[DEBUG][pick_spot] uf2=", uf2,
        "sp=", sp, "is_small=", is_small,
        "render_reason(before)=", render_reason,
        "render_idxs(before)=", render_idxs
    )

    # small이면 "table_small" + table spot 1개로 강제
    if is_small:
        render_reason = "table_small"

        # 1) table 계열 spot 찾기
        table_idx = None
        for i, s in enumerate(spots):
            surf = _spot_surface_local(s)
            if any(x in surf for x in ["table", "desk", "shelf", "counter", "stand"]):
                table_idx = i
                break

        # 2) 없으면 synthetic table spot 생성
        if table_idx is None:
            fake = _synthesize_table_spot_local(data)
            if fake:
                fake["spot_index"] = len(spots)
                spots.append(fake)
                data["spots"] = spots
                table_idx = len(spots) - 1

        # 3) 최종: small은 무조건 1장 (table_idx가 있으면 그걸 사용, 없으면 기존 첫 idx 사용)
        if table_idx is not None:
            render_idxs = [int(table_idx)]
        elif render_idxs:
            render_idxs = [render_idxs[0]]
        else:
            render_idxs = [0]

    # ✅ 중복 제거(같은 spot 3번 렌더 방지)
    render_idxs = list(dict.fromkeys(render_idxs))

    # ✅ floor_large일 때만 3개를 채운다 (manual/기타에서는 절대 3개로 불리지 않음)
    if render_reason == "floor_large" and len(render_idxs) < 3:
        for i in range(len(spots)):
            if i not in render_idxs:
                render_idxs.append(i)
            if len(render_idxs) >= 3:
                break

    # ✅ 소형(table_small)은 무조건 1장
    if render_reason == "table_small":
        render_idxs = [render_idxs[0]]

    # =========================
    # 2) 원본 이미지 경로
    # =========================
    ctx = get_user_ctx(key) or {}
    save_path = ctx.get("last_image_path")

    if not save_path or not os.path.exists(str(save_path)):
        save_path = data.get("image_path") or data.get("save_path")

    if not save_path or not os.path.exists(str(save_path)):
        return _json_with_sid(
            {"messages": [{"type": "text", "text": "원본 이미지 경로를 찾지 못했습니다."}]},
            sid, sid_is_new,
        )

    # =========================
    # 3) plant 이미지 고정 (유저 선택 = plant_image_url이 진실)
    # =========================
    pid = (str(body.plant_id).strip() if body.plant_id else "")
    pid_safe = pid if pid else "none"

    plant_url = (str(body.plant_image_url).strip() if body.plant_image_url else "")

    if not plant_url:
        return _json_with_sid(
            {"messages": [{"type": "text", "text": "선택한 식물 이미지 URL이 없습니다. (plant_image_url 필수)"}]},
            sid, sid_is_new
        )

    plant_cache_dir = os.path.join(str(RESULT_DIR), "plant_cache")
    plant_asset = _download_image_cached(
        url=plant_url,
        cache_dir=plant_cache_dir,
        cache_key=pid_safe,
        regen=regen,
    )

    if not plant_asset or not os.path.exists(plant_asset):
        return _json_with_sid(
            {"messages": [{"type": "text", "text": f"plant_image_url 다운로드 실패. pid={pid_safe} url={plant_url}"}]},
            sid, sid_is_new,
        )

    # =========================
    # 4) 동일 식물로 spot별 렌더
    # =========================
    ts_ms = int(time.time() * 1000)
    images_payload: List[Dict[str, Any]] = []

    def add_img(label: str, path: str):
        if path and os.path.exists(path):
            images_payload.append({
                "name": label,
                "url": cache_bust_url(request, to_results_url(path), ts_ms)
            })

    for ridx in render_idxs:
        s = spots[ridx]
        forced = _best_point_from_spot(s)
        if not forced or not forced.get("pt"):
            continue

        best_point = {"pt": forced["pt"], "spot_index": forced.get("spot_index")}

        composite_path = os.path.join(
            RESULT_DIR, f"composite_{sid}_spot_{ridx}_plant_{pid_safe}.png"
        )
        ai_edit_path = os.path.join(
            RESULT_DIR, f"ai_edit_{sid}_spot_{ridx}_plant_{pid_safe}.png"
        )

        # 4-1) composite (동일 식물 고정)
        composite_plant_on_original(
            original_image_path=str(save_path),
            best_point_obj=best_point,
            out_path=composite_path,
            plant_png_path=plant_asset,
            plant_width_ratio=0.22,
            anchor="bottom_center",
            add_green_dot=False,
        )

        if not os.path.exists(composite_path):
            continue

        # =========================
        # ✅ 핵심 변경 1: mode가 "composite"여도, 유저가 원하면 ai_edit를 타게 만들 수 있게 함
        # - 프론트가 mode를 안 보내면 기본 "" 이라서 여기 들어옴
        # - mode="composite"면 원래는 스킵했는데, 이제는 "ai_edit"가 아니면 스킵하도록 더 명확히
        #
        # ✅ 권장 정책:
        # - mode == "composite"  → Gemini 안 탐 (빠른 합성만)
        # - mode != "composite"  → Gemini 탐 (배경 제거/블렌딩)
        # =========================

        # ✅ Gemini는 무조건 실행, 실패하면 composite를 내려주지 말고 요청 자체를 실패 처리
        prompt = (
            "You are given an image where a plant photo was pasted onto a room image. "
            "Your ONLY job is to remove the pasted plant's rectangular background and blend edges naturally. "
            "STRICT RULES: "
            "1) Do NOT move, resize, rotate, or re-place the plant. Keep its position and scale EXACTLY. "
            "2) Do NOT change any pixels outside the plant cutout area (the room must remain identical). "
            "3) Do NOT generate a new plant or alter plant identity/pot/leaf shape. "
            "4) Output must keep the same resolution and framing. No cropping. "
            "5) Add a subtle contact shadow ONLY under the plant base without shifting it. "
            f"Plant anchor point must remain at {best_point['pt']}."
        )

        try:
            gemini_edit_image(
                input_image_path=composite_path,
                prompt=prompt,
                out_path=ai_edit_path,
            )
        except Exception as e:
            return _json_with_sid(
                {"ok": False, "messages": [{"type": "text", "text": f"❌ Gemini 실패: {e}"}]},
                sid, sid_is_new
            )

        if not os.path.exists(ai_edit_path):
            return _json_with_sid(
                {"ok": False, "messages": [{"type": "text", "text": "❌ Gemini 실패: ai_edit 파일이 생성되지 않음"}]},
                sid, sid_is_new
            )

        # ✅ 결과는 ai_edit만
        add_img("ai_edit", ai_edit_path)

    # =========================
    # 5) 응답
    # =========================
    if render_reason == "table_small":
        text = "✅ 소형 식물 → 테이블 1개 스팟에 동일 식물로 생성했습니다."
    else:
        text = "✅ 동일 식물로 3개 스팟에 생성했습니다."

    # ✅ 현재 정책: mode와 무관하게 Gemini 무조건 실행
    text += " (Gemini forced)"

    msgs: List[Dict[str, Any]] = [{"type": "text", "text": text}]
    if images_payload:
        msgs.append({"type": "images", "text": "생성 결과", "images": images_payload})

    return _json_with_sid(
        {"messages": msgs, "cv_result": data},
        sid, sid_is_new,
    )

async def chat_render(request: Request, body: PickSpotBody) -> JSONResponse:
    return await chat_pick_spot(request, body)
