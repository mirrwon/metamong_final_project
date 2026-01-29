from __future__ import annotations

import os
import json
import time
import random
import uuid, pathlib
import glob
import inspect

from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from datetime import datetime
from dotenv import load_dotenv

from fastapi import UploadFile, File, Form, Request
from fastapi.responses import JSONResponse

from app.cv.pipeline import run_pipeline
from app.cv.space_classifier import classify_space
from app.config import BASE_DIR, RESULT_DIR, RESULT_JSON_LATEST, UPLOAD_DIR, ASSET_DIR

from app.llm.image_edit import composite_plant_on_original
from app.llm.gemini.gemini_image_edit import gemini_edit_image

from app.solar.kier_client import KierSolarClient
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
    scene_to_label,
    scene_id_to_room_label,
)

load_dotenv()

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)

solar_client = KierSolarClient()

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
def _solar_summary_from_items(items: Any) -> Dict[str, Any]:
    out = {
        "ok": False,
        "times": {"morning": None, "noon": None, "evening": None},
        "ranges": {"morning": [6, 10], "noon": [11, 15], "evening": [16, 19]},
        "source": "kier_predc_items",
        "reason": "",
    }

    if not isinstance(items, list) or len(items) == 0:
        out["reason"] = "items_empty"
        return out

    time_keys = ("time", "hhmm", "tm", "t", "baseTime", "fcstTime", "hour")
    value_keys = (
        "value", "solar", "insolation", "radiation", "ghi", "dni", "dhi",
        "predc", "pred", "y", "val"
    )

    buckets = {"morning": [], "noon": [], "evening": []}

    for row in items:
        if not isinstance(row, dict):
            continue

        hh = None
        for k in time_keys:
            if k in row:
                hh = parse_hh_from_any(row.get(k))
                if hh is not None:
                    break
        if hh is None:
            continue

        vv = None
        for k in value_keys:
            if k in row:
                vv = safe_float(row.get(k))
                if vv is not None:
                    break
        if vv is None:
            continue

        if 6 <= hh <= 10:
            buckets["morning"].append(vv)
        elif 11 <= hh <= 15:
            buckets["noon"].append(vv)
        elif 16 <= hh <= 19:
            buckets["evening"].append(vv)

    def avg(xs: list) -> Optional[float]:
        if not xs:
            return None
        return float(sum(xs) / len(xs))

    out["times"]["morning"] = avg(buckets["morning"])
    out["times"]["noon"] = avg(buckets["noon"])
    out["times"]["evening"] = avg(buckets["evening"])

    if out["times"]["morning"] is None and out["times"]["noon"] is None and out["times"]["evening"] is None:
        out["reason"] = "no_parsable_rows"
        return out

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
    body = await request.json()
    text = (body.get("text") or "").strip()

    sid, sid_is_new = _get_or_create_sid(request)
    key = sid

    if text == "마음에 들어요":
        return _json_with_sid(
            {
                "messages": [
                    {
                        "type": "text",
                        "text": "저장할까요? 다음 중 선택해주세요.",
                        "payload": {"options": ["저장", "저장 목록 보기", "이미지 생성 프롬프트 만들기", "다른 사진으로 다시 추천"]},
                    }
                ]
            },
            sid,
            sid_is_new,
        )

    is_filter_summary = ("식물 경험" in text) or ("반려동물 여부" in text)
    if is_filter_summary and isinstance(body.get("filters"), dict) and len(body["filters"]) > 0:
        set_user_ctx(key, {"filters": body["filters"]}, ttl_sec=60 * 60 * 6)
        return _json_with_sid(
            {
                "messages": [
                    {"type": "text", "text": f"수신: {text}"},
                    {"type": "text", "text": "사진 업로드를 진행해주세요.", "payload": {"input": {"type": "image"}}},
                ]
            },
            sid,
            sid_is_new,
        )

    if text == "저장":
        latest = load_latest_result()
        if not latest:
            return _json_with_sid(
                {
                    "messages": [
                        {
                            "type": "text",
                            "text": "저장할 분석 결과가 없습니다. 먼저 사진 업로드 후 분석을 진행해주세요.",
                            "payload": {"input": {"type": "image"}},
                        }
                    ]
                },
                sid,
                sid_is_new,
            )

        ctx = get_user_ctx(key)
        last_image = ctx.get("last_image_path") if isinstance(ctx, dict) else None

        snapshot = dict(latest) if isinstance(latest, dict) else {}
        if isinstance(ctx, dict):
            for k2 in ("filters", "constraints", "last_detail_text"):
                if k2 in ctx:
                    snapshot[f"_user_{k2}"] = ctx.get(k2)

        try:
            saved_id = db_save_reco(client_key=key, image_path=str(last_image or ""), result=snapshot)
            return _json_with_sid(
                {
                    "messages": [
                        {"type": "text", "text": f"저장 완료! (id={saved_id})"},
                        {
                            "type": "text",
                            "text": "다음 중 선택해주세요.",
                            "payload": {"options": ["저장 목록 보기", "이미지 생성 프롬프트 만들기", "다른 사진으로 다시 추천"]},
                        },
                    ]
                },
                sid,
                sid_is_new,
            )
        except Exception as e:
            return _json_with_sid({"messages": [{"type": "text", "text": f"저장 실패: {str(e)}"}]}, sid, sid_is_new)

    if text == "저장 목록 보기":
        try:
            rows = db_list_recos(client_key=key, limit=20)
        except Exception as e:
            return _json_with_sid({"messages": [{"type": "text", "text": f"저장 목록 조회 실패: {str(e)}"}]}, sid, sid_is_new)

        if not rows:
            return _json_with_sid({"messages": [{"type": "text", "text": "저장된 항목이 없습니다."}]}, sid, sid_is_new)

        lines: List[str] = []
        for r in rows:
            rid = r.get("id")
            created = r.get("created_at")
            imgp = r.get("image_path") or ""
            top1 = ""
            rj = r.get("result_json") or {}
            if isinstance(rj, dict):
                bs = rj.get("best_spot") or {}
                if isinstance(bs, dict):
                    tp = bs.get("top_plants") or []
                    if isinstance(tp, list) and tp and isinstance(tp[0], dict):
                        top1 = tp[0].get("name") or ""
            lines.append(f"- id={rid} / at={created} / top1={top1} / image={imgp}")

        return _json_with_sid(
            {
                "messages": [
                    {"type": "text", "text": "저장 목록\n" + "\n".join(lines)},
                    {"type": "text", "text": "다음 중 선택해주세요.", "payload": {"options": ["다른 사진으로 다시 추천", "이미지 생성 프롬프트 만들기"]}},
                ]
            },
            sid,
            sid_is_new,
        )

    if text == "이미지 생성 프롬프트 만들기":
        data = load_latest_result()
        best_point = extract_best_point(data)

        marker_path = os.path.join(RESULT_DIR, "result_latest_marker.png")
        if not os.path.exists(marker_path):
            return _json_with_sid(
                {
                    "messages": [
                        {
                            "type": "text",
                            "text": "result_latest_marker.png 가 없습니다. 먼저 사진 업로드 후 분석을 진행해주세요.",
                            "payload": {"input": {"type": "image"}},
                        }
                    ]
                },
                sid,
                sid_is_new,
            )

        best_spot = data.get("best_spot", {}) if isinstance(data, dict) else {}
        spot_usage = best_spot.get("spot_usage", "floor_large")

        plant_name = None
        top_plants = best_spot.get("top_plants", [])
        if isinstance(top_plants, list) and len(top_plants) > 0 and isinstance(top_plants[0], dict):
            plant_name = top_plants[0].get("name")

        prompt_txt = _prompt_for_edit(best_point=best_point, spot_usage=spot_usage, plant_name=plant_name)

        out_path = os.path.join(RESULT_DIR, "result_latest_ai_edit.png")
        edit_result = gemini_edit_image(input_image_path=marker_path, prompt=prompt_txt, out_path=out_path)

        messages: List[Dict[str, Any]] = []
        if edit_result.get("ok") and os.path.exists(out_path):
            messages.append({"type": "text", "text": "Gemini 이미지 편집 결과입니다."})
            messages.append(
                {
                    "type": "images",
                    "text": "result_latest_ai_edit",
                    "images": [{"name": "result_latest_ai_edit", "url": abs_url(request, "/results/result_latest_ai_edit.png")}],
                }
            )
        else:
            messages.append({"type": "text", "text": f"Gemini 편집 실패: {edit_result.get('reason', 'unknown')}"})

        messages.append({"type": "text", "text": "다음 중 선택해주세요.", "payload": {"options": ["마음에 들어요", "상세 입력", "다른 사진으로 다시 추천"]}})
        return _json_with_sid({"messages": messages}, sid, sid_is_new)

    if text == "상세 입력":
        set_user_state(key, {"mode": "awaiting_detail"}, ttl_sec=60 * 60 * 6)
        return _json_with_sid({"messages": [{"type": "text", "text": "상세 내용을 입력해주세요.", "payload": {"input": {"type": "text"}}}]}, sid, sid_is_new)

    if text == "다른 사진으로 다시 추천":
        return _json_with_sid(
            {
                "messages": [
                    {"type": "text", "text": "다른 사진을 업로드해주세요."},
                    {"type": "text", "text": "사진 업로드를 진행해주세요.", "payload": {"input": {"type": "image"}}},
                ]
            },
            sid,
            sid_is_new,
        )

    state = get_user_state(key)
    mode = state.get("mode")
    is_option = text in ["마음에 들어요", "상세 입력", "저장", "저장 목록 보기", "이미지 생성 프롬프트 만들기", "다른 사진으로 다시 추천"]

    if mode == "awaiting_detail" and text and (not is_option):
        set_user_state(key, {"mode": None}, ttl_sec=60 * 60 * 6)
        constraints = parse_detail_text_to_constraints(text)

        # kg_answer = handle_chat(
        #     question=text,
        #     user_num=key,
        #     session_id=None,
        #     rules=KG_RULES,
        #     loader=KG_LOADER,
        #     llm=KG_LLM,
        # )

        # set_user_ctx(key, {"last_detail_text": text, "constraints": constraints, "kg_answer": kg_answer}, ttl_sec=60 * 60 * 6)

        # messages: List[Dict[str, Any]] = [{"type": "text", "text": f"상세 입력 수신: {text}"}]
        # ans_list = kg_answer.get("answer") or []
        # messages.append({"type": "text", "text": "\n".join(ans_list) if isinstance(ans_list, list) and ans_list else "현재 정보로는 답하기 어려워요."})

        # fq = kg_answer.get("followup_question") or ""
        # if isinstance(fq, str) and fq.strip():
        #     messages.append({"type": "text", "text": fq.strip()})

        # messages.append({"type": "text", "text": "다음 중 선택해주세요.", "payload": {"options": ["이미지 생성 프롬프트 만들기", "다른 사진으로 다시 추천", "마음에 들어요"]}})
        # return _json_with_sid({"messages": messages}, sid, sid_is_new)

    return _json_with_sid(
        {"messages": [{"type": "text", "text": f"수신: {text}"}, {"type": "text", "text": "사진 업로드를 진행해주세요.", "payload": {"input": {"type": "image"}}}]},
        sid,
        sid_is_new,
    )

def _hhmm_from_meta_or_now(meta) -> str:
    # meta가 JSON string일 수도 있음
    if isinstance(meta, str):
        try:
            import json
            meta = json.loads(meta)
        except Exception:
            meta = {}

    if isinstance(meta, dict):
        t = meta.get("hhmm") or meta.get("time") or meta.get("capture_time")
        if isinstance(t, str):
            s = t.strip().replace(":", "")
            if len(s) == 4 and s.isdigit():
                return s

    # 기본값: 서버 현재시간 (HHMM)
    return datetime.now().strftime("%H%M")

def _sanitize_kier_time(hhmm: str) -> str:
    """
    KIER API가 분(min)이 있는 값(0002 같은 것)을 싫어해서
    'HH00' 형태로 내리고, 너무 이른/늦은 시간은 정오로 보정한다.
    """
    s = (hhmm or "").strip().replace(":", "")
    if len(s) < 2 or not s[:2].isdigit():
        return "1200"

    hh = int(s[:2])
    # 분은 무조건 00으로
    out = f"{hh:02d}00"

    # 새벽/밤 시간은 예측값이 없거나 invalid 뜨는 경우가 많아서 안전하게 정오로 보정
    if hh < 6 or hh > 19:
        return "1200"

    return out

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
# /api/chat/image handler
# =========================
async def handle_chat_image(
    request: Request,
    files: Optional[List[UploadFile]] = File(None),
    image: Optional[UploadFile] = File(None),
    meta: Optional[str] = Form(None),
    scene_id: Optional[str] = Form(None),
) -> JSONResponse:
    sid, sid_is_new = _get_or_create_sid(request)
    key = sid

    upload: Optional[UploadFile] = None
    if files and len(files) > 0:
        upload = files[0]
    elif image is not None:
        upload = image

    cid = _get_client_id(request)

    if upload is None:
        progress(cid, "error", "업로드 파일을 찾지 못했습니다. (FormData key: files 또는 image 필요)")
        return _json_with_sid(
            {"messages": [{"type": "text", "text": "업로드 파일을 찾지 못했습니다. (FormData key: files 또는 image 필요)", "payload": {"input": {"type": "image"}}}]},
            sid,
            sid_is_new,
        )

    orig_name = upload.filename or "upload.jpg"
    ext = pathlib.Path(orig_name).suffix or ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(UPLOAD_DIR, filename)

    content = await upload.read()
    with open(save_path, "wb") as f:
        f.write(content)

    set_user_ctx(key, {"last_image_path": save_path}, ttl_sec=60 * 60 * 6)

    progress(cid, "upload")
    progress(cid, "cv_start")
    progress(cid, "cv_floor")
    progress(cid, "cv_window")
    progress(cid, "cv_light")

    print("[CHAT_IMAGE] scene_id =", scene_id)
    print("[CHAT_IMAGE] filename =", filename, "save_path =", save_path)

    old_ai = os.path.join(RESULT_DIR, "result_latest_ai_edit.png")
    if os.path.exists(old_ai):
        try:
            os.remove(old_ai)
            print("[CHAT_IMAGE] cleared old ai_edit:", old_ai)
        except Exception as e:
            print("[CHAT_IMAGE][WARN] failed to remove old ai_edit:", e)

    user_opts: Dict[str, Any] = {}
    if scene_id:
        user_opts["scene_id"] = scene_id

    try:
        out = _run_pipeline_compat(save_path, user_opts=user_opts)
    except Exception as e:
        progress(cid, "error", f"분석 중 오류가 발생했습니다: {str(e)}")
        return _json_with_sid(
            {"messages": [
                {"type": "text", "text": f"분석 중 오류가 발생했습니다: {str(e)}", "payload": {"input": {"type": "image"}}}]},
            sid,
            sid_is_new,
        )

    # =========================
    # SPACE 분류 + scene 자동추론
    # =========================

    space = None
    if isinstance(out, dict):
        space = classify_space(out)
        out["space"] = space

    auto_scene_id = None

    scene_info = out.get("scene") if isinstance(out, dict) else None
    scenes_raw = scene_info.get("scenes") if isinstance(scene_info, dict) else None

    # 자동추론 조건
    if (
            (not scene_id)  # ✅ 사용자가 선택해서 보낸 scene_id가 있으면 자동추론 금지
            and isinstance(scene_info, dict)
            and scene_info.get("reason") == "scene_required"
            and isinstance(space, dict)
            and space.get("confidence", 0) >= 0.7
            and isinstance(scenes_raw, list)
    ):
        space_type = space.get("type")  # "욕실" | "거실" | "방"

        for s0 in scenes_raw:
            # scenes_raw는 str 또는 dict 섞여올 수 있음 → id 문자열로 정규화
            sid0 = None
            if isinstance(s0, str):
                sid0 = s0
            elif isinstance(s0, dict):
                sid0 = s0.get("id") or s0.get("scene_id")

            if not isinstance(sid0, str) or not sid0.strip():
                continue

            lbl = scene_to_label(sid0)
            if isinstance(lbl, str) and space_type and (space_type in lbl):
                auto_scene_id = sid0.strip()
                break

    # 자동 scene 성공 → pipeline 재실행
    if auto_scene_id:
        user_opts2 = dict(user_opts or {})
        user_opts2["scene_id"] = auto_scene_id

        try:
            out = _run_pipeline_compat(save_path, user_opts=user_opts2)
        except Exception as e:
            progress(cid, "error", f"재분석 중 오류: {str(e)}")
            return _json_with_sid(
                {"messages": [{"type": "text", "text": f"재분석 중 오류: {str(e)}"}]},
                sid,
                sid_is_new,
            )

        # 재분석 후 space 다시 계산
        out["space"] = classify_space(out)




    progress(cid, "cv_done")

    scene_info = out.get("scene")
    if isinstance(scene_info, dict) and scene_info.get("reason") == "scene_required":
        scenes_raw = scene_info.get("scenes") or []

        scenes_for_ui = []
        for x in scenes_raw:
            # scene_id 추출 (str / dict 둘 다 처리)
            _id = None
            if isinstance(x, str):
                _id = x
            elif isinstance(x, dict):
                _id = x.get("id") or x.get("scene_id") or x.get("sceneId")

            if not isinstance(_id, str) or not _id.strip():
                continue

            _id = _id.strip()

            # ✅ 라벨(거실/욕실/침실/주방 등)
            room = scene_id_to_room_label(_id)

            # ✅ 드롭다운에서 중복 안 보이게 id 일부를 같이 보여줌
            short_id = _id
            if len(short_id) > 18:
                short_id = "…" + short_id[-18:]

            scenes_for_ui.append({
                "id": _id,
                "label": f"{room} ({short_id})" if room else short_id,
            })

        return _json_with_sid(
            {
                "messages": [
                    {
                        "type": "text",
                        "text": "이 사진은 어떤 공간(scene)인지 선택이 필요합니다.",
                        "payload": {"type": "scene_required", "scenes": scenes_for_ui},
                    }
                ]
            },
            sid,
            sid_is_new,
        )

    print("[META RAW]", meta, type(meta))
    print("[META PARSED]", get_lat_lot_from_meta(meta))

    # =========================
    # 결과 로드
    # =========================
    progress(cid, "result_load")

    latest_json = os.path.join(RESULT_DIR, "result_latest.json")
    marker_path = os.path.join(RESULT_DIR, "result_latest_marker.png")
    composite_path = os.path.join(RESULT_DIR, "result_latest_composite.png")

    data: Dict[str, Any] = {}
    if os.path.exists(latest_json):
        try:
            with open(latest_json, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    # ✅ fallback: 파일이 없거나 비었으면 out 사용
    if (not isinstance(data, dict) or not data) and isinstance(out, dict) and out:
        data = out

    if not isinstance(data, dict) or not data:
        progress(cid, "error", "분석 결과 파일을 불러오지 못했어요. 다시 시도해 주세요.")
        return _json_with_sid(
            {
                "messages": [
                    {
                        "type": "text",
                        "text": "분석 결과(result_latest.json)를 불러오지 못했습니다. 다시 사진을 업로드해 주세요.",
                        "payload": {"input": {"type": "image"}},
                    }
                ]
            },
            sid,
            sid_is_new,
        )

    # ✅ SOLAR 디버그 기본값(항상 찍히게)
    data["solar_apply"] = False
    data["solar_reason"] = "not_run"
    data["solar_summary"] = None

    loc2 = get_lat_lot_from_meta(meta)
    if not isinstance(loc2, dict):
        loc2 = None

    # ✅ meta에 없으면 기본좌표 fallback (A에서 하던 걸 여기로 옮김)
    if not loc2:
        dlat = os.getenv("SOLAR_DEFAULT_LAT")
        dlon = os.getenv("SOLAR_DEFAULT_LON")
        if dlat and dlon:
            try:
                loc2 = {"lat": float(dlat), "lot": float(dlon)}
            except Exception:
                loc2 = None

    if not loc2 or loc2.get("lat") is None or loc2.get("lot") is None:
        data["solar_reason"] = "no_latlon"
        data["solar_profile"] = {"ok": False, "reason": "no_latlon"}
        data["solar_summary"] = {"ok": False, "reason": "no_latlon"}
        data["solar_apply"] = False

    else:
        try:
            date, hhmm = now_kst_yyyymmdd_hhmm()
            hhmm = _sanitize_kier_time(hhmm)

            solar_res = solar_client.fetch_predc(
                lat=loc2["lat"],
                lot=loc2["lot"],
                date=date,
                time_hhmm=hhmm,
                num_rows=200,
            )

            if solar_res:
                solar_payload2 = {
                    "ok": True,
                    "date": solar_res.date,
                    "time": solar_res.time,
                    "lat": solar_res.lat,
                    "lot": solar_res.lot,
                    "items": solar_res.items,
                }
            else:
                solar_payload2 = {"ok": False, "reason": "fetch_failed_or_invalid_or_not_configured"}

            data["solar_profile"] = solar_payload2

            items = solar_payload2.get("items") if solar_payload2.get("ok") else None
            summary = _solar_summary_from_items(items)
            data["solar_summary"] = summary

            if isinstance(summary, dict) and summary.get("ok"):
                _apply_solar_to_spots(data, summary)
                data["solar_reason"] = "applied"
            else:
                data["solar_reason"] = "no_summary"

        except Exception as e:
            data["solar_reason"] = f"exception:{type(e).__name__}"
            data["solar_profile"] = {"ok": False, "reason": "exception"}
            data["solar_summary"] = {"ok": False, "reason": "exception"}
            data["solar_apply"] = False

    # =========================
    # 추천(recommend)
    # =========================
    progress(cid, "recommend")

    ctx = get_user_ctx(key)
    user_filters = ctx.get("filters", {}) if isinstance(ctx, dict) else {}
    data = recommend_for_analysis(data, user_filters=user_filters)

    # 최신 결과 저장(수정된 data 반영)

    data["image_path"] = save_path  # ✅ pick_spot이 원본이미지 찾는 fallback용

    try:
        with open(latest_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[CHAT_IMAGE][WARN] failed to write result_latest.json:", e)

    # =========================
    # 결과 이미지 생성(합성/마커)
    # =========================
    best_point = extract_best_point(data)

    progress(cid, "compose")

    plant_asset = os.path.join(BASE_DIR, "assets", "plants", "default.png")

    # 합성(식물 + 점)
    composite_plant_on_original(
        original_image_path=save_path,
        best_point_obj=best_point,
        out_path=composite_path,
        plant_png_path=plant_asset if os.path.exists(plant_asset) else None,
        plant_width_ratio=0.22,
        anchor="bottom_center",
        add_green_dot=True,
    )

    # 마커(점만)
    composite_plant_on_original(
        original_image_path=save_path,
        best_point_obj=best_point,
        out_path=marker_path,
        plant_png_path=None,
        plant_width_ratio=0.22,
        anchor="bottom_center",
        add_green_dot=True,
    )

    # =========================
    # AI 편집(Gemini)
    # =========================
    ai_edit_path = os.path.join(RESULT_DIR, "result_latest_ai_edit.png")
    pt = best_point.get("pt") if isinstance(best_point, dict) else None
    prompt = (
        "Add a realistic potted plant at the marked spot on the floor. "
        "Match lighting and perspective naturally. Do not change the room layout. "
        "Remove any green dot marker in the final image."
    )
    if pt:
        prompt += f" The spot coordinates are {pt}."


    try:
        gemini_edit_image(
            input_image_path=marker_path,
            prompt=prompt,
            out_path=ai_edit_path,
        )
    except Exception as e:
        print("[CHAT_IMAGE][WARN] gemini_edit_image exception:", e)

    # =========================
    # 응답
    # =========================
    progress(cid, "respond")

    messages: List[Dict[str, Any]] = [{"type": "text", "text": "분석이 완료되었습니다."}]

    space_type = None
    if isinstance(data, dict):
        sp = data.get("space")
        if isinstance(sp, dict):
            space_type = sp.get("type")

    if space_type:
        messages.append({"type": "text", "text": f"공간 분석 결과: {space_type}"})

    ts_ms = int(time.time() * 1000)
    images_payload: List[Dict[str, Any]] = []

    def add_img(label: str, file_path: Optional[str]) -> None:
        if file_path and os.path.exists(file_path):
            images_payload.append(
                {
                    "name": label,
                    "url": cache_bust_url(request, to_results_url(file_path), ts_ms),
                }
            )

    add_img("marker", marker_path)
    add_img("composite", composite_path)
    add_img("ai_edit", ai_edit_path)

    if images_payload:
        messages.append(
            {
                "type": "images",
                "text": "분석 결과 이미지입니다.",
                "images": images_payload,
            }
        )

    messages.append(
        {"type": "text", "text": "다음 중 선택해주세요.", "payload": {"options": ["마음에 들어요", "상세 입력"]}}
    )

    return _json_with_sid({"messages": messages, "cv_result": data}, sid, sid_is_new)

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
) -> JSONResponse:
    return await handle_chat_image(request, files=files, image=image, meta=meta, scene_id=scene_id)

# =========================
# Spot pick / Filters / Scenes
# =========================

class PickSpotBody(BaseModel):
    spot_index: int
    regen: bool = False  # 기본은 캐시 모드


def get_filters():
    groups = [
        {"key": "experience", "label": "식물 경험", "options": ["초보자", "경험자"]},
        {"key": "pet", "label": "반려동물 여부", "options": ["예", "아니오"]},
    ]
    return {"groups": groups, "payload": {"type": "filters", "groups": groups}}


def get_scenes():
    print("[SCENES_ROUTE] HIT get_scenes()")
    print("[SCENES_ROUTE] FILE =", __file__)
    from app.cv.pipeline import list_71765_scenes

    raw = list_71765_scenes()

    scenes: List[Dict[str, str]] = []

    if isinstance(raw, list):
        for x in raw:
            if isinstance(x, str):
                scenes.append({"id": x, "label": scene_to_label(x)})
            elif isinstance(x, dict):
                _id = x.get("id") or x.get("scene_id")
                if _id:
                    scenes.append({"id": _id, "label": scene_to_label(_id)})
    elif isinstance(raw, dict):
        for k in raw.keys():
            _id = str(k)
            scenes.append({"id": _id, "label": scene_to_label(_id)})

    print("[SCENES_ROUTE] raw type =", type(raw), "raw =", raw)
    return {"ok": True, "scenes": scenes, "raw": raw}


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

    plant_name = _pick_plant_for_spot(top_plants, spot_index)

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