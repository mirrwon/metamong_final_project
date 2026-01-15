import os
import time
import json
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, UploadFile, File, Form, Body, Request
from fastapi.responses import JSONResponse, StreamingResponse
from dotenv import load_dotenv

# ✅ 너 프로젝트 구조
from app.pipeline import run_pipeline
from app.gpt_judge import judge_with_gpt_4o_mini
from app.redis_client import get_redis

router = APIRouter(prefix="/api")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
RESULT_DIR = os.path.join(BASE_DIR, "results")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)


def _ts() -> int:
    return int(time.time() * 1000)


def _msg_text(text: str) -> Dict[str, Any]:
    return {
        "id": f"msg-{_ts()}",
        "role": "assistant",
        "type": "text",
        "text": text,
        "timestamp": _ts(),
    }


def _msg_images(url: str, name: str = "result_latest_viz") -> Dict[str, Any]:
    # ✅ normalizeMessages가 item.text 없으면 메시지에서 날려버리니까 text는 반드시 넣음
    return {
        "id": f"img-{_ts()}",
        "role": "assistant",
        "type": "images",
        "text": name,
        "images": [{"url": url, "name": name}],
        "timestamp": _ts(),
    }


def _safe_read_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _default_filter_groups() -> List[Dict[str, Any]]:
    return [
        {"key": "experience", "label": "식물 경험", "options": ["beginner", "expert"]},
        {"key": "pet", "label": "반려동물 여부", "options": ["true", "false"]},
    ]


@router.get("/chat/filters")
def chat_filters():
    return JSONResponse({"groups": _default_filter_groups()})


@router.get("/chat")
def chat_start():
    return JSONResponse(
        {
            "messages": [
                _msg_text("안녕하세요 🌿 몇 가지만 선택해주시면 맞춤 추천을 도와드릴게요."),
                _msg_text("체크박스를 선택하고 아래 ‘전송’ 버튼을 눌러주세요."),
            ],
            "payload": {
                "type": "filters",
                "groups": _default_filter_groups(),
                "question": "조건을 선택해주세요",
                "options": [],
                "input": None,
            },
        }
    )


@router.post("/chat")
def chat_step(payload: Dict[str, Any] = Body(...)):
    return JSONResponse(
        {
            "messages": [
                _msg_text("좋아요! 조건이 저장됐어요."),
                _msg_text("이제 방 사진 1장을 업로드해주세요."),
            ],
            "payload": {
                "type": "",
                "groups": [],
                "question": "",
                "options": [],
                "input": {"type": "image", "placeholder": "공간 사진을 업로드해주세요"},
            },
        }
    )


@router.get("/chat/stream")
def chat_stream():
    def gen():
        while True:
            yield f"data: {json.dumps({'ts': _ts()}, ensure_ascii=False)}\n\n"
            time.sleep(15)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/chat/image")
async def chat_image(
    request: Request,  # ✅ 여기서 base_url 얻어서 결과 이미지 절대경로로 만들기
    files: List[UploadFile] = File(...),
    text: Optional[str] = Form(None),
):
    load_dotenv()

    if not files:
        return JSONResponse({"messages": [_msg_text("❌ 업로드된 파일이 없습니다.")]} , status_code=400)

    first = files[0]

    ext = os.path.splitext(first.filename or "")[1].lower() or ".jpg"
    img_path = os.path.join(UPLOAD_DIR, f"upload_{_ts()}{ext}")

    content = await first.read()
    with open(img_path, "wb") as f:
        f.write(content)

    # Ditto pipeline 실행
    try:
        run_pipeline(
            image_path=img_path,
            debug_viz=True,
            result_dir=RESULT_DIR,
        )
    except TypeError:
        run_pipeline(img_path)

    # 결과 파일
    result_json_path = os.path.join(RESULT_DIR, "result_latest.json")
    viz_path = os.path.join(RESULT_DIR, "result_latest_viz.png")

    result = _safe_read_json(result_json_path)

    # ✅ 핵심 수정: viz_url을 절대 URL로 내려주기 (3000이 아니라 8000으로 가게)
    viz_url = None
    if os.path.exists(viz_path):
        base = str(request.base_url).rstrip("/")  # e.g. http://localhost:8000
        viz_url = f"{base}/results/result_latest_viz.png?t={_ts()}"

    redis_client = get_redis()
    if redis_client:
        try:
            cache_payload = {
                "result": result,
                "viz_url": viz_url,
                "ts": _ts(),
            }
            await redis_client.setex(
                "result:latest",
                3600,
                json.dumps(cache_payload, ensure_ascii=False),
            )
        except Exception:
            pass

    # GPT 요약
    gpt_text = None
    try:
        judged = judge_with_gpt_4o_mini(
            prompt=f"다음 결과를 사용자에게 한국어로 3~6줄로 요약해줘:\n{json.dumps(result, ensure_ascii=False)}"
        )
        if isinstance(judged, dict):
            gpt_text = judged.get("text")
        else:
            gpt_text = str(judged)
    except Exception:
        gpt_text = None

    messages = [_msg_text("✅ 사진 분석이 완료되었습니다!")]
    if gpt_text:
        messages.append(_msg_text(gpt_text))

    if viz_url:
        messages.append(_msg_images(viz_url, name="result_latest_viz"))

    messages.append(_msg_text("이 추천이 마음에 드시나요?\n1) 마음에 들어요\n2) 상세 입력"))

    return JSONResponse(
        {
            "messages": messages,
            "payload": {
                "type": "",
                "groups": [],
                "question": "",
                "options": ["마음에 들어요", "상세 입력"],
                "input": None,
                "result": result,
                "viz_url": viz_url,
            },
        }
    )
