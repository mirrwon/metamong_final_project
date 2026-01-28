from __future__ import annotations

import os
import json
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import StreamingResponse

from app.cv.pipeline import run_pipeline
from app.config import BASE_DIR, RESULT_DIR, UPLOAD_DIR, ASSET_DIR

from app.llm.image_edit import composite_plant_on_original
from app.llm.gemini.gemini_image_edit import gemini_edit_image

# ✅ KG: rules + handle_chat만 사용 (ContextLoader/LLMClient 제거)
from app.kg.rules import load_rules
from app.kg.service import handle_chat

from datetime import datetime
from app.solar.kier_client import KierSolarClient

from app.reco.recommender import recommend_for_analysis


router = APIRouter()

# --- SIMPLE STATE (in-memory) ---
USER_STATE: Dict[str, Dict[str, Any]] = {}
USER_CTX: Dict[str, Dict[str, Any]] = {}
SURVEY_UPLOADS: Dict[str, List[Dict[str, str]]] = {}
SURVEY_DIR = os.path.join(BASE_DIR, "surveys")

# ✅ rules만 로드해서 handle_chat에 전달
KG_RULES = load_rules(ASSET_DIR)

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)
os.makedirs(SURVEY_DIR, exist_ok=True)


def _abs_url(request: Request, path: str) -> str:
    """
    /results/xxx.png 같은 상대경로를
    http://127.0.0.1:8000/results/xxx.png 로 바꿔서 프론트 엑박 방지
    """
    base = str(request.base_url).rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"


def _client_key(request: Request) -> str:
    # 간단히 IP 기반 (로컬 개발용). 배포 시엔 세션/토큰으로 바꾸면 됨.
    host = getattr(request.client, "host", "unknown")
    return str(host)


def _user_key(request: Request, username: Optional[str] = None) -> str:
    # Prefer a stable user id when provided; fall back to IP.
    uname = (username or "").strip()
    if uname:
        return f"user:{uname}"
    return _client_key(request)


def _client_user_num(request: Request, username: Optional[str] = None) -> int:
    """
    handle_chat 시그니처가 user_num: int 를 요구하므로,
    IP 문자열을 안정적으로 int로 변환.
    - username이 있으면 username 기반 hash를 사용
    - IPv4면 마지막 옥텟 기반으로 가볍게
    - 그 외는 hash 기반
    """
    if username:
        return abs(hash(username)) % 1_000_000_000

    host = _client_key(request)
    try:
        parts = host.split(".")
        if len(parts) == 4:
            return int(parts[-1])
    except Exception:
        pass
    return abs(hash(host)) % 1_000_000_000


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


def _collect_survey_values(obj: Any, out: set[str]) -> None:
    if obj is None:
        return
    if isinstance(obj, (list, tuple, set)):
        for item in obj:
            _collect_survey_values(item, out)
        return
    if isinstance(obj, dict):
        for item in obj.values():
            _collect_survey_values(item, out)
        return
    out.add(str(obj))


def _derive_filters_from_survey(survey_answers: Dict[str, Any]) -> Dict[str, Any]:
    values: set[str] = set()
    _collect_survey_values(survey_answers, values)

    derived: Dict[str, Any] = {}
    if {"dog", "cat"} & values:
        # Map pet-related caution answers into the existing pet filter.
        derived["pet"] = ["true"]
    return derived


def _survey_path(username: str) -> str:
    safe = username.strip()
    return os.path.join(SURVEY_DIR, f"{safe}.jsonl")


def _next_survey_id(username: str) -> int:
    path = _survey_path(username)
    if not os.path.exists(path):
        return 1
    last_id = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                try:
                    last_id = max(last_id, int(obj.get("id", 0)))
                except Exception:
                    continue
    except Exception:
        return last_id + 1 if last_id else 1
    return last_id + 1 if last_id else 1


def _append_survey(username: str, record: Dict[str, Any]) -> None:
    path = _survey_path(username)
    record = {"id": _next_survey_id(username), **record}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_latest_survey(username: str) -> Dict[str, Any]:
    path = _survey_path(username)
    if not username or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        if not lines:
            return {}
        return json.loads(lines[-1])
    except Exception:
        return {}


def _load_latest_result() -> Dict[str, Any]:
    latest_json = os.path.join(RESULT_DIR, "result_latest.json")
    if not os.path.exists(latest_json):
        return {}
    with open(latest_json, "r", encoding="utf-8") as f:
        return json.load(f)


def _prompt_for_edit(
    best_point: Any,
    spot_usage: str,
    plant_name: Optional[str] = None,
) -> str:
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


def extract_best_point(data: Dict[str, Any]) -> Optional[Any]:
    if not isinstance(data, dict):
        return None

    best_spot = data.get("best_spot")
    if isinstance(best_spot, dict) and isinstance(best_spot.get("pt"), (list, tuple)) and len(best_spot["pt"]) >= 2:
        return best_spot["pt"]

    spots = data.get("spots")
    if isinstance(spots, list) and len(spots) > 0:
        s0 = spots[0]
        if isinstance(s0, dict) and isinstance(s0.get("pt"), (list, tuple)) and len(s0["pt"]) >= 2:
            return s0["pt"]

    bp = data.get("best_point")
    if isinstance(bp, (list, tuple)) and len(bp) >= 2:
        return bp
    if isinstance(bp, dict) and ("x" in bp and "y" in bp):
        return bp

    return None


def _now_kst_yyyymmdd_hhmm() -> tuple[str, str]:
    now = datetime.now()
    return now.strftime("%Y%m%d"), now.strftime("%H%M")


def _get_lat_lot_from_meta(meta: Optional[str]) -> Optional[dict]:
    if not meta:
        return None
    try:
        obj = json.loads(meta)
    except Exception:
        return None

    if not isinstance(obj, dict):
        return None

    lat = obj.get("lat")
    lot = obj.get("lot") or obj.get("lon")
    try:
        lat = float(lat)
        lot = float(lot)
    except Exception:
        return None

    return {"lat": lat, "lot": lot}


# -------------------------
# v3 Contract: /api/chat/filters
# -------------------------
@router.get("/api/chat/filters")
def get_filters():
    groups = [
        {"key": "experience", "label": "식물 경험", "options": ["beginner", "expert"]},
        {"key": "pet", "label": "반려동물 여부", "options": ["true", "false"]},
    ]
    return {
        "groups": groups,
        "payload": {"type": "filters", "groups": groups},
    }


# -------------------------
# v3 Contract: /api/chat/survey
# -------------------------
@router.get("/api/chat/survey")
def get_survey():
    return {
        "key": "style_survey",
        "label": "선호 스타일 선택",
        "ui": "checkbox",
        "description": "",
        "groups": [
            {
                "key": "caution",
                "multiple": True,
                "label": "주의 사항을 선택해 주세요",
                "options": [
                    {
                        "value": "beginner",
                        "label": "초심자",
                    },
                    {
                        "value": "baby",
                        "label": "아기",
                    },
                    {
                        "value": "dog",
                        "label": "강아지",
                    },
                    {
                        "value": "cat",
                        "label": "고양이",
                    },
                    {
                        "value": "allergy",
                        "label": "알러지",
                    },
                ],
            },
            {
                "key": "size",
                "multiple": True,
                "label": "원하는 식물 크기는 무엇인가요?",
                "options": [
                    {
                        "value": "small",
                        "label": "탁상용",
                    },
                    {
                        "value": "large",
                        "label": "바닥용",
                    },
                ],
            },
            {
                "key": "style",
                "multiple": True,
                "label": "방 분위기를 선택해주세요.",
                "options": [
                    {
                        "value": "natural",
                        "label": "내추럴",
                        "image": "/assets/survey/natural.jpg",
                    },
                    {
                        "value": "minimal",
                        "label": "미니멀",
                        "image": "/assets/survey/minimal.jpg",
                    },
                    {
                        "value": "trendy",
                        "label": "트렌디",
                        "image": "/assets/survey/trendy.jpg",
                    },
                ],
            },
            {
                "key": "Plant_style",
                "multiple": True,
                "label": "당신이 원하는 식물 스타일은 무엇인가요?",
                "options": [
                    {
                        "value": "flowery",
                        "label": "화려한 꽃",
                        "image": "/assets/survey/flowery.jpg",
                    },
                    {
                        "value": "leafy",
                        "label": "푸른 잎",
                        "image": "/assets/survey/leafy.png",
                    },
                    {
                        "value": "fruity",
                        "label": "싱그러운 과일",
                        "image": "/assets/survey/fruity.jpg",
                    },
                ],
            }
        ],
    }


@router.post("/api/chat/survey")
async def submit_survey(request: Request):
    body = await request.json()
    username = body.get("username") if isinstance(body, dict) else None
    key = _user_key(request, username)
    if not SURVEY_UPLOADS.get(key):
        raise HTTPException(status_code=400, detail="survey_image_required")
    answers = body.get("answers") if isinstance(body, dict) else None
    if isinstance(answers, dict):
        USER_CTX.setdefault(key, {})
        USER_CTX[key]["survey"] = answers
        if username:
            record = {
                "answers": answers,
            }
            _append_survey(username, record)
    return {"ok": True, "received": body}


# -------------------------
# v3 Contract: POST /api/chat/survey/image (upload)
# -------------------------
@router.post("/api/chat/survey/image")
async def survey_image_upload(
    request: Request,
    files: Optional[List[UploadFile]] = File(None),
    image: Optional[UploadFile] = File(None),
    survey_key: Optional[str] = Form(None),
    username: Optional[str] = Form(None),
):
    uploads: List[UploadFile] = []
    if files and len(files) > 0:
        uploads = files
    elif image is not None:
        uploads = [image]

    if not uploads:
        return {
            "ok": False,
            "reason": "no_files",
            "message": "No files uploaded.",
        }

    saved_items = []
    first_saved_path: Optional[str] = None
    for idx, upload in enumerate(uploads):
        filename = upload.filename or f"survey_{idx}.jpg"
        _, ext = os.path.splitext(filename)
        ext = ext if ext else ".jpg"
        safe_name = f"survey_{uuid.uuid4().hex}{ext}"
        save_path = os.path.join(UPLOAD_DIR, safe_name)

        content = await upload.read()
        with open(save_path, "wb") as f:
            f.write(content)

        if first_saved_path is None:
            first_saved_path = save_path

        saved_items.append(
            {
                "name": safe_name,
                "url": _abs_url(request, f"/uploads/{safe_name}"),
            }
        )

    if first_saved_path:
        run_pipeline(first_saved_path, debug_viz=True)
        # Also generate marker/composite outputs for survey uploads.
        try:
            latest_json = os.path.join(RESULT_DIR, "result_latest.json")
            data: Dict[str, Any] = {}
            if os.path.exists(latest_json):
                with open(latest_json, "r", encoding="utf-8") as f:
                    data = json.load(f)

            best_point = extract_best_point(data)
            marker_path = os.path.join(RESULT_DIR, "result_latest_marker.png")
            composite_path = os.path.join(RESULT_DIR, "result_latest_composite.png")
            plant_asset = os.path.join(BASE_DIR, "assets", "plants", "default.png")

            _ = composite_plant_on_original(
                original_image_path=first_saved_path,
                best_point_obj=best_point,
                out_path=marker_path,
                plant_png_path=None,
                add_green_dot=True,
                plant_width_ratio=0.22,
                anchor="bottom_center",
            )

            _ = composite_plant_on_original(
                original_image_path=first_saved_path,
                best_point_obj=best_point,
                out_path=composite_path,
                plant_png_path=plant_asset if os.path.exists(plant_asset) else None,
                plant_width_ratio=0.22,
                anchor="bottom_center",
                add_green_dot=True,
            )
        except Exception as e:
            print("[WARN] survey marker/composite generation failed:", e)

    key = _user_key(request, username)
    SURVEY_UPLOADS.setdefault(key, []).extend(saved_items)

    return {
        "ok": True,
        "survey_key": survey_key,
        "items": saved_items,
    }


# -------------------------
# v3 Contract: /api/chat/stream (SSE heartbeat) - 절대 제거 금지
# -------------------------
@router.get("/api/chat/stream")
def chat_stream():
    def gen():
        while True:
            yield 'data: {"messages": []}\n\n'
            time.sleep(15)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)


# -------------------------
# v3 Contract: GET /api/chat (초기 상태)
# -------------------------
@router.get("/api/chat")
def chat_get():
    return {
        "messages": [
            {
                "type": "text",
                "text": "식물을 추천해 드릴게요.",
            }
        ]
    }


# -------------------------
# v3 Contract: GET /api/chat/results (latest images)
# -------------------------
@router.get("/api/chat/results")
def chat_results(request: Request):
    latest_viz = os.path.join(RESULT_DIR, "result_latest_viz.png")
    marker_path = os.path.join(RESULT_DIR, "result_latest_marker.png")
    composite_path = os.path.join(RESULT_DIR, "result_latest_composite.png")

    items = []
    def _versioned_url(path: str, rel: str) -> str:
        ts = int(os.path.getmtime(path)) if os.path.exists(path) else int(time.time())
        return f"{_abs_url(request, rel)}?v={ts}"

    if os.path.exists(latest_viz):
        items.append({"name": "result_latest_viz", "url": _versioned_url(latest_viz, "/results/result_latest_viz.png")})
    if os.path.exists(marker_path):
        items.append({"name": "result_latest_marker", "url": _versioned_url(marker_path, "/results/result_latest_marker.png")})
    if os.path.exists(composite_path):
        items.append({"name": "result_latest_composite", "url": _versioned_url(composite_path, "/results/result_latest_composite.png")})

    return {"ok": True, "images": items}


# -------------------------
# v3 Contract: POST /api/chat (텍스트/버튼 선택 처리)
# -------------------------
@router.post("/api/chat")
async def chat_post(request: Request):
    body = await request.json()
    text = (body.get("text") or "").strip()
    username = body.get("username") if isinstance(body, dict) else None
    key = _user_key(request, username)

    if text == "마음에 들어요":
        return {
            "messages": [
                {
                    "type": "text",
                    "text": "저장할까요? 다음 중 선택해주세요.",
                    "payload": {"options": ["저장 목록 보기", "이미지 생성 프롬프트 만들기", "다른 사진으로 다시 추천"]},
                }
            ]
        }

    is_filter_summary = ("식물 경험" in text) or ("반려동물 여부" in text)
    if is_filter_summary and isinstance(body.get("filters"), dict) and len(body["filters"]) > 0:
        USER_CTX.setdefault(key, {})
        USER_CTX[key]["filters"] = body["filters"]
        return {
            "messages": [
                {"type": "text", "text": f"수신: {text}"},
                {"type": "text", "text": "사진 업로드를 진행해주세요.", "payload": {"input": {"type": "image"}}},
            ]
        }

    if text == "이미지 생성 프롬프트 만들기":
        data = _load_latest_result()
        best_point = extract_best_point(data)

        marker_path = os.path.join(RESULT_DIR, "result_latest_marker.png")
        if not os.path.exists(marker_path):
            return {
                "messages": [
                    {
                        "type": "text",
                        "text": "backend/results/result_latest_marker.png 가 없습니다. 먼저 사진 업로드 후 분석을 진행해주세요.",
                        "payload": {"input": {"type": "image"}},
                    }
                ]
            }

        best_spot = data.get("best_spot", {}) if isinstance(data, dict) else {}
        spot_usage = best_spot.get("spot_usage", "floor_large")

        plant_name = None
        top_plants = best_spot.get("top_plants", [])
        if isinstance(top_plants, list) and len(top_plants) > 0 and isinstance(top_plants[0], dict):
            plant_name = top_plants[0].get("name")

        prompt = _prompt_for_edit(
            best_point=best_point,
            spot_usage=spot_usage,
            plant_name=plant_name,
        )

        out_path = os.path.join(RESULT_DIR, "result_latest_ai_edit.png")
        edit_result = gemini_edit_image(
            input_image_path=marker_path,
            prompt=prompt,
            out_path=out_path,
        )

        messages: List[Dict[str, Any]] = []
        if edit_result.get("ok") and os.path.exists(out_path):
            messages.append({"type": "text", "text": "Gemini 이미지 편집 결과입니다."})
            messages.append(
                {
                    "type": "images",
                    "text": "result_latest_ai_edit",
                    "images": [{"name": "result_latest_ai_edit", "url": _abs_url(request, "/results/result_latest_ai_edit.png")}],
                }
            )
        else:
            messages.append({"type": "text", "text": f"Gemini 편집 실패: {edit_result.get('reason', 'unknown')}"})

        messages.append(
            {
                "type": "text",
                "text": "다음 중 선택해주세요.",
                "payload": {"options": ["마음에 들어요", "상세 입력", "다른 사진으로 다시 추천"]},
            }
        )
        return {"messages": messages}

    if text == "상세 입력":
        USER_STATE.setdefault(key, {})
        USER_STATE[key]["mode"] = "awaiting_detail"
        return {"messages": [{"type": "text", "text": "상세 내용을 입력해주세요.", "payload": {"input": {"type": "text"}}}]}

    if text == "저장 목록 보기":
        return {
            "messages": [
                {
                    "type": "text",
                    "text": "저장 목록 기능은 아직 미구현입니다. (다음 단계: DB 연동)",
                    "payload": {"options": ["마음에 들어요", "상세 입력", "다른 사진으로 다시 추천"]},
                }
            ]
        }

    if text == "다른 사진으로 다시 추천":
        return {
            "messages": [
                {"type": "text", "text": "다른 사진을 업로드해주세요."},
                {"type": "text", "text": "사진 업로드를 진행해주세요.", "payload": {"input": {"type": "image"}}},
            ]
        }

    mode = USER_STATE.get(key, {}).get("mode")

    is_option = text in [
        "마음에 들어요",
        "상세 입력",
        "저장 목록 보기",
        "이미지 생성 프롬프트 만들기",
        "다른 사진으로 다시 추천",
    ]

    if mode == "awaiting_detail" and text and (not is_option):
        USER_STATE[key]["mode"] = None

        constraints = parse_detail_text_to_constraints(text)

        # ✅ 구형 handle_chat 요구사항 충족
        user_num = _client_user_num(request, username)
        session_id = None

        kg_answer = handle_chat(
            question=text,
            user_num=user_num,
            session_id=session_id,
            rules=KG_RULES,
            loader=None,  # ✅ edit-only MVP: loader 없이도 정책/의도/응답 가능하게
            is_authenticated=True,
        )

        USER_CTX.setdefault(key, {})
        USER_CTX[key]["last_detail_text"] = text
        USER_CTX[key]["constraints"] = constraints
        USER_CTX[key]["kg_answer"] = kg_answer

        messages: List[Dict[str, Any]] = []
        messages.append({"type": "text", "text": f"상세 입력 수신: {text}"})

        ans_list = kg_answer.get("answer") or []
        if isinstance(ans_list, list) and ans_list:
            messages.append({"type": "text", "text": "\n".join([str(x) for x in ans_list])})
        else:
            messages.append({"type": "text", "text": "현재 정보로는 답하기 어려워요."})

        fq = kg_answer.get("followup_question") or ""
        if isinstance(fq, str) and fq.strip():
            messages.append({"type": "text", "text": fq.strip()})

        messages.append(
            {
                "type": "text",
                "text": "다음 중 선택해주세요.",
                "payload": {"options": ["이미지 생성 프롬프트 만들기", "다른 사진으로 다시 추천", "마음에 들어요"]},
            }
        )
        return {"messages": messages}

    return {
        "messages": [
            {"type": "text", "text": f"수신: {text}"},
            {"type": "text", "text": "사진 업로드를 진행해주세요.", "payload": {"input": {"type": "image"}}},
        ]
    }


# -------------------------
# v3 Contract: POST /api/chat/image (핵심)
# -------------------------
@router.post("/api/chat/image")
async def chat_image(
    request: Request,
    files: Optional[List[UploadFile]] = File(None),
    image: Optional[UploadFile] = File(None),
    meta: Optional[str] = Form(None),
    username: Optional[str] = Form(None),
):
    upload: Optional[UploadFile] = None
    if files and len(files) > 0:
        upload = files[0]
    elif image is not None:
        upload = image

    if upload is None:
        return {
            "messages": [
                {
                    "type": "text",
                    "text": "업로드 파일을 찾지 못했습니다. (FormData key: files 또는 image 필요)",
                    "payload": {"input": {"type": "image"}},
                }
            ]
        }

    filename = upload.filename or "upload.jpg"
    save_path = os.path.join(UPLOAD_DIR, filename)

    content = await upload.read()
    with open(save_path, "wb") as f:
        f.write(content)

    run_pipeline(save_path)

    solar_payload = None
    loc = _get_lat_lot_from_meta(meta)
    if loc:
        date, hhmm = _now_kst_yyyymmdd_hhmm()
        client = KierSolarClient()
        solar_res = client.fetch_predc(
            lat=loc["lat"],
            lot=loc["lot"],
            date=date,
            time_hhmm=hhmm,
            num_rows=10,
        )
        if solar_res:
            solar_payload = {
                "ok": True,
                "date": solar_res.date,
                "time": solar_res.time,
                "lat": solar_res.lat,
                "lot": solar_res.lot,
                "items": solar_res.items,
            }
        else:
            solar_payload = {"ok": False, "reason": "fetch_failed_or_not_configured"}

    latest_json = os.path.join(RESULT_DIR, "result_latest.json")
    latest_viz = os.path.join(RESULT_DIR, "result_latest_viz.png")
    marker_path = os.path.join(RESULT_DIR, "result_latest_marker.png")
    composite_path = os.path.join(RESULT_DIR, "result_latest_composite.png")

    data: Dict[str, Any] = {}
    if os.path.exists(latest_json):
        with open(latest_json, "r", encoding="utf-8") as f:
            data = json.load(f)

    if solar_payload:
        data["solar_profile"] = solar_payload

    key = _user_key(request, username)
    ctx = USER_CTX.get(key, {}) if isinstance(USER_CTX.get(key, {}), dict) else {}
    filters = ctx.get("filters", {}) if isinstance(ctx.get("filters"), dict) else {}
    survey_answers = ctx.get("survey", {}) if isinstance(ctx.get("survey"), dict) else {}
    if not survey_answers and username:
        latest = _load_latest_survey(username)
        answers = latest.get("answers") if isinstance(latest, dict) else {}
        if isinstance(answers, dict):
            survey_answers = answers
            USER_CTX.setdefault(key, {})
            USER_CTX[key]["survey"] = survey_answers
    derived = _derive_filters_from_survey(survey_answers) if survey_answers else {}
    user_filters = {**filters, **derived}
    if survey_answers:
        user_filters["survey_answers"] = survey_answers
    data = recommend_for_analysis(data, user_filters=user_filters)

    try:
        with open(latest_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[WARN] overwrite result_latest.json failed:", e)

    best_point = extract_best_point(data)

    plant_asset = os.path.join(BASE_DIR, "assets", "plants", "default.png")

    composite_info = composite_plant_on_original(
        original_image_path=save_path,
        best_point_obj=best_point,
        out_path=composite_path,
        plant_png_path=plant_asset if os.path.exists(plant_asset) else None,
        plant_width_ratio=0.22,
        anchor="bottom_center",
        add_green_dot=True,
    )

    _ = composite_plant_on_original(
        original_image_path=save_path,
        best_point_obj=best_point,
        out_path=marker_path,
        plant_png_path=None,
        add_green_dot=True,
        plant_width_ratio=0.22,
        anchor="bottom_center",
    )

    messages: List[Dict[str, Any]] = []
    messages.append({"type": "text", "text": "분석이 완료되었습니다."})

    if os.path.exists(latest_viz):
        messages.append(
            {
                "type": "images",
                "text": "result_latest_viz",
                "images": [{"name": "result_latest_viz", "url": _abs_url(request, "/results/result_latest_viz.png")}],
            }
        )

    if os.path.exists(marker_path):
        messages.append(
            {
                "type": "images",
                "text": "result_latest_marker",
                "images": [{"name": "result_latest_marker", "url": _abs_url(request, "/results/result_latest_marker.png")}],
            }
        )

    if os.path.exists(composite_path):
        messages.append(
            {
                "type": "images",
                "text": "result_latest_composite",
                "images": [{"name": "result_latest_composite", "url": _abs_url(request, "/results/result_latest_composite.png")}],
            }
        )
    else:
        messages.append(
            {
                "type": "text",
                "text": f"backend/results/result_latest_composite.png 생성 실패: {composite_info.get('reason', 'unknown')}",
            }
        )

    best = (data.get("best_spot") or {}) if isinstance(data, dict) else {}
    tops = best.get("top_plants") or []
    if isinstance(tops, list) and tops:
        top3 = tops[:3]
        lines = []
        for i, p in enumerate(top3, start=1):
            if not isinstance(p, dict):
                continue
            name = p.get("name") or "식물"
            reason = p.get("reason") or ""
            lines.append(f"{i}. {name}" + (f" - {reason}" if reason else ""))
        if lines:
            messages.append({"type": "text", "text": "추천 식물 TOP3\n" + "\n".join(lines)})

    messages.append(
        {
            "type": "text",
            "text": "다음 중 선택해주세요.",
            "payload": {"options": ["마음에 들어요", "상세 입력"]},
        }
    )

    return {"messages": messages}
