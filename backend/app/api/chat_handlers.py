from __future__ import annotations

import os, json, time, random, uuid, pathlib, glob , inspect

from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from datetime import datetime
from dotenv import load_dotenv

from fastapi import UploadFile, File, Form, Request
from fastapi.responses import JSONResponse

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
from .chat_progress import progress
from .chat_storage import get_user_ctx, set_user_ctx, get_user_state, set_user_state, USER_CTX
from .chat_db import db_save_reco, db_list_recos
from .chat_utils import (
    abs_url,
    to_results_url,
    cache_bust_url,
    load_latest_result,
    pick_latest_result_file,
    extract_best_point,
    scene_to_label,
    now_kst_yyyymmdd_hhmm,
    get_lat_lot_from_meta,
    safe_float,
    parse_hh_from_any,
    scene_id_to_room_label,
)

load_dotenv()

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)

weather_client = AsosWeatherClient()

class AnalyzeBody(BaseModel):
    filters: Dict[str, Any] = {}
    meta: Optional[Dict[str, Any]] = None

class RecommendBody(BaseModel):
    filters: Dict[str, Any] = {}
    meta: Optional[Dict[str, Any]] = None  # 필요하면 받기만

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
        return _json_with_sid({"ok": False, "messages": [{"type": "text", "text": f"분석 중 오류: {e}"}]}, sid, sid_is_new)

    data = out if isinstance(out, dict) else {}

    # ========================================================
    # 🚀 [기상청 ASOS 데이터 주입 및 보정] - 수정 포인트
    # ========================================================
    weather_res = None

    ## 원래 코드 ##
    try:
        weather_res = weather_client.fetch_growth_profile("108")

        # --- 낮시간 테스트를 위한 코드 (확인 후 삭제) ---
        weather_res["solar_radiation"] = "2.5"
        weather_res["ok"] = True
        # -----------------------------------------------



        data["solar"] = weather_res

        solar_summary = _solar_summary_from_asos(weather_res)
        if solar_summary.get("ok"):
            data = _apply_solar_to_spots(data, solar_summary)
            print(f"☀️ 기상청 데이터 적용 성공: {weather_res.get('solar_radiation')} MJ/m2")
    except Exception as solar_err:
        print(f"☀️ 기상청 데이터 처리 중 최종 오류: {solar_err}")

    # =========================
    # 2) 추천 (보정된 data 전달)
    # =========================
    data["space"] = classify_space(data) if isinstance(data, dict) else None

    data = recommend_for_analysis(data, user_filters=user_filters)
    data["image_path"] = str(save_path)


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
    best_point = extract_best_point(data)
    plant_asset = os.path.join(BASE_DIR, "assets", "plants", "default.png")

    composite_plant_on_original(
        original_image_path=str(save_path),
        best_point_obj=best_point,
        out_path=composite_path,
        plant_png_path=plant_asset if os.path.exists(plant_asset) else None,
        plant_width_ratio=0.22,
        anchor="bottom_center",
        add_green_dot=True,
    )

    composite_plant_on_original(
        original_image_path=str(save_path),
        best_point_obj=best_point,
        out_path=marker_path,
        plant_png_path=None,
        plant_width_ratio=0.22,
        anchor="bottom_center",
        add_green_dot=True,
    )

    # (옵션) gemini 편집은 실패해도 전체 플로우는 진행되게
    try:
        pt = best_point.get("pt") if isinstance(best_point, dict) else None
        prompt = (
            "Add a realistic potted plant at the marked spot on the floor. "
            "Match lighting and perspective naturally. Do not change the room layout. "
            "Remove any green dot marker in the final image."
        )
        if pt:
            prompt += f" The spot coordinates are {pt}."
        gemini_edit_image(input_image_path=marker_path, prompt=prompt, out_path=ai_edit_path)
    except Exception as e:
        print("[WARN] gemini_edit_image failed:", e)

    # 5) 응답 (프론트에서 바로 이미지 띄우기)
    ts_ms = int(time.time() * 1000)
    images_payload: List[Dict[str, Any]] = []

    def add_img(label: str, file_path: str):
        if file_path and os.path.exists(file_path):
            images_payload.append({"name": label, "url": cache_bust_url(request, to_results_url(file_path), ts_ms)})

    add_img("marker", marker_path)
    add_img("composite", composite_path)
    if os.path.exists(ai_edit_path):
        add_img("ai_edit", ai_edit_path)

    return _json_with_sid(
        {
            "ok": True,
            "images": images_payload,
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
    plant_name: Optional[str] = None
    regen: bool = False  # 기본은 캐시 모드


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

    spot_index = int(body.spot_index)
    regen = bool(getattr(body, "regen", False))

    latest_json = os.path.join(RESULT_DIR, "result_latest.json")
    if not os.path.exists(latest_json):
        return _json_with_sid(
            {"messages": [{"type": "text", "text": "저장된 분석 결과가 없습니다. 먼저 사진을 업로드해 주세요."}]},
            sid,
            sid_is_new,
        )

    try:
        with open(latest_json, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return _json_with_sid(
            {"messages": [{"type": "text", "text": f"결과 파일을 읽지 못했습니다: {e}"}]},
            sid,
            sid_is_new,
        )

    spots = data.get("spots") if isinstance(data, dict) else None
    if not isinstance(spots, list) or len(spots) == 0:
        return _json_with_sid(
            {"messages": [{"type": "text", "text": "후보(spots)가 없습니다. 다시 분석해 주세요."}]},
            sid,
            sid_is_new,
        )

    if spot_index < 0 or spot_index >= len(spots):
        return _json_with_sid(
            {"messages": [{"type": "text", "text": f"spot_index 범위가 올바르지 않습니다. (0 ~ {len(spots)-1})"}]},
            sid,
            sid_is_new,
        )

    chosen = spots[spot_index]
    if not isinstance(chosen, dict):
        return _json_with_sid(
            {"messages": [{"type": "text", "text": "선택한 후보 데이터 형식이 올바르지 않습니다."}]},
            sid,
            sid_is_new,
        )

    # ✅ 원본 이미지 경로 찾기 (분리 구조에 맞게 보강)
    # 1) ctx last_image_path 우선
    ctx = get_user_ctx(key)
    save_path = (ctx.get("last_image_path") if isinstance(ctx, dict) else None)

    # 2) 없으면 result_latest.json 내부 키 시도
    if not save_path:
        save_path = (
            (data.get("image") if isinstance(data, dict) else None)
            or (data.get("image_path") if isinstance(data, dict) else None)
            or (data.get("save_path") if isinstance(data, dict) else None)
        )

    if not save_path or not os.path.exists(str(save_path)):
        return _json_with_sid(
            {"messages": [{"type": "text", "text": "원본 이미지 경로를 찾지 못했습니다. 다시 사진을 업로드해 주세요."}]},
            sid,
            sid_is_new,
        )

    print(f"[CHAT_SPOT] spot_index={spot_index} regen={regen} save_path={save_path}")

    # best_spot 갱신
    data["best_spot"] = chosen

    marker_path = os.path.join(RESULT_DIR, "result_latest_marker.png")
    composite_path = os.path.join(RESULT_DIR, "result_latest_composite.png")

    best_point = extract_best_point(data)

    plant_asset = os.path.join(BASE_DIR, "assets", "plants", "default.png")

    # composite: 점 없이(원본 유지)
    composite_plant_on_original(
        original_image_path=str(save_path),
        best_point_obj=best_point,
        out_path=composite_path,
        plant_png_path=plant_asset if os.path.exists(plant_asset) else None,
        plant_width_ratio=0.22,
        anchor="bottom_center",
        add_green_dot=False,
    )

    # marker: 점만
    composite_plant_on_original(
        original_image_path=str(save_path),
        best_point_obj=best_point,
        out_path=marker_path,
        plant_png_path=None,
        plant_width_ratio=0.22,
        anchor="bottom_center",
        add_green_dot=True,
    )

    # AI 편집 이미지: 캐시 파일
    ai_edit_path = os.path.join(RESULT_DIR, f"ai_edit_{sid}_spot_{spot_index}.png")

    # top_plants 출처: data.top_plants 우선, 없으면 chosen/top_plants, best_spot.top_plants도 fallback
    top_plants = None
    if isinstance(data, dict):
        top_plants = data.get("top_plants")
        if top_plants is None:
            bs = data.get("best_spot")
            if isinstance(bs, dict):
                top_plants = bs.get("top_plants")
    if top_plants is None and isinstance(chosen, dict):
        top_plants = chosen.get("top_plants")

    plant_name = body.plant_name or _pick_plant_for_spot(top_plants, spot_index)

    pt = best_point.get("pt") if isinstance(best_point, dict) else None

    prompt = (
        f"Add a realistic potted {plant_name} at the marked spot on the floor. "
        "Match lighting and perspective naturally. Do not change the room layout. "
        "Remove any green dot marker in the final image. "
        f"The plant MUST be a {plant_name}."
    )
    if pt:
        prompt += f" The spot coordinates are {pt}."

    use_cache = (not regen) and os.path.exists(ai_edit_path)

    if use_cache:
        print("[CHAT_SPOT] cache hit:", ai_edit_path)
    else:
        print("[CHAT_SPOT] generating ai_edit:", ai_edit_path)
        try:
            edit_res = gemini_edit_image(
                input_image_path=marker_path,
                prompt=prompt,
                out_path=ai_edit_path,
            )
            print("[CHAT_SPOT] gemini_edit_image =", edit_res)
        except Exception as e:
            print("[CHAT_SPOT][WARN] gemini_edit_image exception:", e)
            ai_edit_path = None

    # 최신 결과 저장
    try:
        with open(latest_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[WARN] overwrite latest_json after pick_spot failed:", e)

    # 응답
    ts_ms = int(time.time() * 1000)
    images_payload: List[Dict[str, Any]] = []

    def add_img(label: str, file_path_or_name: Optional[str]):
        if not file_path_or_name:
            return
        abs_path = file_path_or_name if os.path.isabs(file_path_or_name) else os.path.join(RESULT_DIR, os.path.basename(file_path_or_name))
        if not os.path.exists(abs_path):
            return
        images_payload.append({"name": label, "url": cache_bust_url(request, to_results_url(abs_path), ts_ms)})

    add_img("ai_edit", ai_edit_path)

    msgs: List[Dict[str, Any]] = [
        {"type": "text", "text": f"✅ 후보 #{spot_index + 1} 위치로 다시 합성했습니다. (regen={regen})"}
    ]

    if images_payload:
        msgs.append({"type": "images", "text": "재합성 결과", "images": images_payload})

    if pt:
        msgs.append({"type": "text", "text": f"선택 좌표: {pt}"})

    return _json_with_sid({"messages": msgs, "cv_result": data}, sid, sid_is_new)

async def chat_render(request: Request, body: PickSpotBody) -> JSONResponse:
    return await chat_pick_spot(request, body)
