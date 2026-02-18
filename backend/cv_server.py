from __future__ import annotations

import os
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse

app = FastAPI(title="Ditto GPU Server", version="0.1.0")

# GPU 서버 내부 저장 폴더 (컨테이너 기준)
GPU_UPLOAD_DIR = Path(os.getenv("GPU_UPLOAD_DIR", "/app/uploads"))
GPU_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/health")
def health():
    return {"ok": True, "service": "ditto-gpu", "port": 9001}


def _get_run_pipeline():
    # ✅ 여기 import 경로는 “GPU 서버에서만” 유효해야 함
    # 지금 너 구조가 backend/app/cv/pipeline.py 라면:
    from cv_app.cv.pipeline import run_pipeline
    return run_pipeline


@app.post("/cv/analyze")
async def cv_analyze(
    image: UploadFile = File(...),
    user_opts: str | None = Form(None),
    max_n: int | None = Form(None),
    debug_viz: bool = Form(False),
    save_outputs: bool = Form(True),
):
    """
    API 서버가 이미지(UploadFile)를 보내면
    GPU 서버는 파일로 저장 후 run_pipeline(image_path=...)로 실행.
    """
    run_pipeline = _get_run_pipeline()

    # 1) 파일 저장
    ext = Path(image.filename or "upload.jpg").suffix or ".jpg"
    fname = f"{uuid.uuid4().hex}{ext}"
    fpath = GPU_UPLOAD_DIR / fname

    data = await image.read()
    fpath.write_bytes(data)

    # 2) user_opts 파싱
    opts = None
    if user_opts:
        try:
            opts = json.loads(user_opts)
        except Exception:
            # 문자열로 그냥 들어오면 None 처리
            opts = None

    # 3) 실행
    try:
        out = run_pipeline(
            image_path=str(fpath),
            user_opts=opts,
            max_n=max_n,
            debug_viz=bool(debug_viz),
            save_outputs=bool(save_outputs),
        )
        return JSONResponse({"ok": True, "payload": out})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
