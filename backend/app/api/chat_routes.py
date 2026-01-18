from __future__ import annotations

import os
import json
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, UploadFile, File, Form, Request
from fastapi.responses import StreamingResponse

from app.cv.pipeline import run_pipeline
from app.config import BASE_DIR, RESULT_DIR, UPLOAD_DIR, ASSET_DIR

from app.llm.image_edit import composite_plant_on_original
from app.llm.gemini.gemini_image_edit import gemini_edit_image

from app.kg.rules import load_rules
from app.kg.context_loader import ContextLoader
from app.kg.llm_client import LLMClient
from app.kg.service import handle_chat

from datetime import datetime
from app.solar.kier_client import KierSolarClient


from app.reco.recommender import recommend_for_analysis



router = APIRouter()


# --- SIMPLE STATE (in-memory) ---
USER_STATE: Dict[str, Dict[str, Any]] = {}
USER_CTX: Dict[str, Dict[str, Any]] = {}

KG_RULES = load_rules(ASSET_DIR)
KG_LOADER = ContextLoader(
    mysql_client=None,
    redis_client=None,
    base_dir=BASE_DIR,
    user_ctx=USER_CTX,
)
KG_LLM = LLMClient()  # model/system_prompt 필요하면 여기서 지정

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)

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

def parse_detail_text_to_constraints(text: str) -> Dict[str, Any]:
    t = (text or "").strip().lower()

    # 설치 위치 힌트
    placement = None
    if any(k in t for k in ["테이블", "상판", "선반", "책상"]):
        placement = "table"
    elif any(k in t for k in ["바닥", "플로어", "바닥에"]):
        placement = "floor"

    # 광량 요구 힌트(사용자 의도)
    light_pref = None
    if any(k in t for k in ["햇빛없", "빛없", "어두", "그늘", "저광량"]):
        light_pref = "low"
    elif any(k in t for k in ["햇빛많", "직사광", "고광량", "밝은곳"]):
        light_pref = "high"
    elif any(k in t for k in ["반그늘", "중간", "간접광", "중광량"]):
        light_pref = "medium"

    # 반려동물/초보 여부는 이미 filters로 받지만, 상세입력에서도 힌트가 있으면 덮어쓸 수 있게
    pet = None
    if any(k in t for k in ["반려묘", "고양이", "강아지", "반려동물"]):
        pet = True
    if any(k in t for k in ["반려동물없", "없음"]):
        # 너무 공격적이면 제거해도 됨. 일단 최소로 둠.
        pass

    # 크기 힌트
    size = None
    if any(k in t for k in ["큰", "대형", "키큰"]):
        size = "large"
    elif any(k in t for k in ["작은", "소형", "미니"]):
        size = "small"
    elif any(k in t for k in ["중형", "적당한"]):
        size = "medium"

    # 키워드 그대로 보존(팀 KG가 쓰기 좋게)
    return {
        "raw_text": text,
        "placement": placement,     # floor/table/None
        "light_pref": light_pref,   # low/medium/high/None
        "size_pref": size,          # small/medium/large/None
        "pet_hint": pet,            # True/None
    }

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
    else:  # avoid
        mode_rules = (
            f"{plant_text}를 가장 자연스럽고 안전한 방식으로 소형 화분으로 배치하세요. "
        )

    return base_rules + mode_rules

def extract_best_point(data: Dict[str, Any]) -> Optional[Any]:
    """
    result_latest.json에서 best point를 다양한 스키마로 안전 추출.
    현재 너 JSON 기준: best_spot.pt 가 정답.
    반환은 (x,y) 형태(list/tuple/dict) 그대로 두고 image_edit에서 파싱하게 둠.
    """
    if not isinstance(data, dict):
        return None

    # 1) 새 스키마(현재 너 결과): best_spot.pt
    best_spot = data.get("best_spot")
    if isinstance(best_spot, dict) and isinstance(best_spot.get("pt"), (list, tuple)) and len(best_spot["pt"]) >= 2:
        return best_spot["pt"]

    # 2) spots[0].pt
    spots = data.get("spots")
    if isinstance(spots, list) and len(spots) > 0:
        s0 = spots[0]
        if isinstance(s0, dict) and isinstance(s0.get("pt"), (list, tuple)) and len(s0["pt"]) >= 2:
            return s0["pt"]

    # 3) 구버전 호환: best_point
    bp = data.get("best_point")
    if isinstance(bp, (list, tuple)) and len(bp) >= 2:
        return bp
    if isinstance(bp, dict) and ("x" in bp and "y" in bp):
        return bp

    return None

def _now_kst_yyyymmdd_hhmm() -> tuple[str, str]:
    # 서버가 한국이면 그냥 localtime 써도 됨(가장 단순/안정)
    now = datetime.now()
    return now.strftime("%Y%m%d"), now.strftime("%H%M")


def _get_lat_lot_from_meta(meta: Optional[str]) -> Optional[dict]:
    """
    프론트에서 meta(FormData)로 JSON 문자열을 보내는 걸 전제로 함.
    예: {"lat": 37.5665, "lot": 126.9780}
    """
    if not meta:
        return None
    try:
        obj = json.loads(meta)
    except Exception:
        return None

    if not isinstance(obj, dict):
        return None

    lat = obj.get("lat")
    lot = obj.get("lot") or obj.get("lon")  # 혹시 프론트가 lon으로 보내면 수용

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
# v3 Contract: /api/chat/stream (SSE heartbeat) - 절대 제거 금지
# 프론트 Chat.js는 onmessage에서 JSON.parse를 시도하므로, JSON 문자열로 보냄
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
                "text": "필터를 선택해주세요.",
                "payload": {
                    "type": "filters",
                    "groups": [
                        {"key": "experience", "label": "식물 경험", "options": ["beginner", "expert"]},
                        {"key": "pet", "label": "반려동물 여부", "options": ["true", "false"]},
                    ],
                },
            }
        ]
    }

# -------------------------
# v3 Contract: POST /api/chat (텍스트/버튼 선택 처리)
# -------------------------
@router.post("/api/chat")
async def chat_post(request: Request):
    body = await request.json()
    text = (body.get("text") or "").strip()

    # ✅ 1) "마음에 들어요" -> 반드시 3옵션 (v3 계약)
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

    # ✅ 2) 필터 전송(sendWithFilters)만 업로드로 넘기기
    # - sendWithFilters는 "식물 경험: ..." "반려동물 여부: ..." 요약 텍스트를 보냄
    is_filter_summary = ("식물 경험" in text) or ("반려동물 여부" in text)
    if is_filter_summary and isinstance(body.get("filters"), dict) and len(body["filters"]) > 0:
        key = _client_key(request)
        USER_CTX.setdefault(key, {})
        USER_CTX[key]["filters"] = body["filters"]  # ✅ 제품형 필수: 추천/DB/KG에 쓸 user evidence

        return {
            "messages": [
                {"type": "text", "text": f"수신: {text}"},
                {"type": "text", "text": "사진 업로드를 진행해주세요.", "payload": {"input": {"type": "image"}}},
            ]
        }

    # ✅ 3) "이미지 생성 프롬프트 만들기" -> Gemini 편집 실행 + 결과 이미지 반환
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

        # pipeline 추천 1순위(백업)
        plant_name = None
        top_plants = best_spot.get("top_plants", [])
        if isinstance(top_plants, list) and len(top_plants) > 0:
            plant_name = top_plants[0].get("name")

        # ✅ KG 추천 가져오기 (있으면 이게 우선)
        # key = _client_key(request)
        # kg_result = USER_CTX.get(key, {}).get("kg_result")

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

    # ✅ 4) "상세 입력" -> text input
    if text == "상세 입력":
        key = _client_key(request)
        USER_STATE.setdefault(key, {})
        USER_STATE[key]["mode"] = "awaiting_detail"
        return {
            "messages": [
                {"type": "text", "text": "상세 내용을 입력해주세요.", "payload": {"input": {"type": "text"}}}
            ]
        }

    # ✅ 5) "저장 목록 보기" -> 최소 구현(나중에 DB 붙이기)
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

    # ✅ 6) "다른 사진으로 다시 추천" -> 업로드로
    if text == "다른 사진으로 다시 추천":
        return {
            "messages": [
                {"type": "text", "text": "다른 사진을 업로드해주세요."},
                {"type": "text", "text": "사진 업로드를 진행해주세요.", "payload": {"input": {"type": "image"}}},
            ]
        }

    # ✅ 상세 입력 대기 상태면: 텍스트를 KG로 연결
    key = _client_key(request)
    mode = USER_STATE.get(key, {}).get("mode")

    # 사용자가 옵션 텍스트가 아닌 "진짜 상세요청"을 보냈을 때만 처리
    is_option = text in [
        "마음에 들어요",
        "상세 입력",
        "저장 목록 보기",
        "이미지 생성 프롬프트 만들기",
        "다른 사진으로 다시 추천",
    ]

    if mode == "awaiting_detail" and text and (not is_option):
        USER_STATE[key]["mode"] = None  # 한번 처리했으면 해제

        constraints = parse_detail_text_to_constraints(text)

        # (선택) session_id/user_num: 로컬 개발용 기본값
        user_num = _client_key(request)
        session_id = None

        # KG 엔진 호출 (룰 + evidence + LLM evidence-only)
        kg_answer = handle_chat(
            question=text,
            user_num=user_num,
            session_id=session_id,
            rules=KG_RULES,
            loader=KG_LOADER,
            llm=KG_LLM,
        )

        print("[DEBUG CONTEXT]", KG_LOADER.load(user_num=user_num, session_id=session_id))
        print("[DEBUG KG_ANSWER]", kg_answer)

        # 저장(원하면)
        USER_CTX.setdefault(key, {})
        USER_CTX[key]["last_detail_text"] = text
        USER_CTX[key]["constraints"] = constraints
        USER_CTX[key]["kg_answer"] = kg_answer

        messages: List[Dict[str, Any]] = []
        messages.append({"type": "text", "text": f"상세 입력 수신: {text}"})

        # kg_answer 형식: {"answer": ["...","..."], "followup_question": "..."}
        ans_list = kg_answer.get("answer") or []
        if isinstance(ans_list, list) and ans_list:
            messages.append({"type": "text", "text": "\n".join(ans_list)})
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

    # ✅ 7) 기본 응답 (절대 None 반환 금지)
    return {
        "messages": [
            {"type": "text", "text": f"수신: {text}"},
            {"type": "text", "text": "사진 업로드를 진행해주세요.", "payload": {"input": {"type": "image"}}},
        ]
    }


# -------------------------
# v3 Contract: POST /api/chat/image (핵심)
# ✅ FIX: 프론트가 "files"로 보내든 "image"로 보내든 둘 다 받는다
# -------------------------
@router.post("/api/chat/image")
async def chat_image(
    request: Request,
    files: Optional[List[UploadFile]] = File(None),
    image: Optional[UploadFile] = File(None),
    meta: Optional[str] = Form(None),
):
    # 1) 업로드 파일 결정
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

    # 2) pipeline 실행
    run_pipeline(save_path)

    # ✅ Solar API 호출 (lat/lot가 있는 경우만)
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
                "items": solar_res.items,   # ✅ 원본 item list
            }
        else:
            solar_payload = {"ok": False, "reason": "fetch_failed_or_not_configured"}


    # 3) 결과 파일 풀네임
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


    # ✅ 제품형: recommender로 top_plants 채우기 (filters 기반)
    key = _client_key(request)
    user_filters = USER_CTX.get(key, {}).get("filters", {}) if isinstance(USER_CTX.get(key, {}), dict) else {}

    data = recommend_for_analysis(data, user_filters=user_filters)

    # ✅ result_latest.json 다시 저장 (pipeline은 spots/features만, 추천은 여기서 채움)
    try:
        with open(latest_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[WARN] overwrite result_latest.json failed:", e)


    best_point = extract_best_point(data)

    # 4) 로컬 합성(편집) 결과 (식물 PNG 있으면 합성, 없으면 점만)
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

    # marker는 점만 찍어서 생성 (Gemini 편집 입력용)
    _ = composite_plant_on_original(
        original_image_path=save_path,
        best_point_obj=best_point,
        out_path=marker_path,
        plant_png_path=None,
        add_green_dot=True,
        plant_width_ratio=0.22,
        anchor="bottom_center",
    )

    # 5) 응답
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

    # --- 추천 요약 텍스트(프론트에 바로 보이게) ---
    best = (data.get("best_spot") or {}) if isinstance(data, dict) else {}
    tops = best.get("top_plants") or []
    if isinstance(tops, list) and tops:
        top3 = tops[:3]
        lines = []
        for i, p in enumerate(top3, start=1):
            name = p.get("name") or "식물"
            reason = p.get("reason") or ""
            lines.append(f"{i}. {name}" + (f" - {reason}" if reason else ""))
        messages.append({"type": "text", "text": "추천 식물 TOP3\n" + "\n".join(lines)})

    # 6) v3 핵심: 분석 후 options 유지
    messages.append(
        {
            "type": "text",
            "text": "다음 중 선택해주세요.",
            "payload": {"options": ["마음에 들어요", "상세 입력"]},
        }
    )

    return {"messages": messages}
