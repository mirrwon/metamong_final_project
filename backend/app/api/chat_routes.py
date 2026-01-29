from __future__ import annotations

from fastapi import APIRouter, Request, UploadFile, File, Form
from typing import Optional, List

from .chat_progress import stream_route
from .chat_handlers import (
    chat_get,
    chat_post,
    chat_image,
    chat_pick_spot,
    get_filters,
    get_scenes,
    PickSpotBody,
)

from .chat_survey import survey_router

router = APIRouter()

# survey API 호출
router.include_router(survey_router)

# -------------------------
# v3 Contract: /api/chat/filters
# -------------------------
@router.get("/api/chat/filters")
def route_filters():
    return get_filters()

@router.get("/api/chat/scenes")
def route_scenes():
    return get_scenes()

# -------------------------
# v3 Contract: /api/chat/stream (SSE heartbeat) - 절대 제거 금지
# -------------------------
@router.get("/api/chat/stream")
def route_stream(request: Request):
    return stream_route(request)

@router.get("/api/chat")
async def route_chat_get(request: Request):
    return await chat_get(request)

@router.post("/api/chat")
async def route_chat_post(request: Request):
    return await chat_post(request)

@router.post("/api/chat/image")
async def route_chat_image(
    request: Request,
    files: Optional[List[UploadFile]] = File(None),
    image: Optional[UploadFile] = File(None),
    meta: Optional[str] = Form(None),
    scene_id: Optional[str] = Form(None),
):
    return await chat_image(request, files=files, image=image, meta=meta, scene_id=scene_id)

@router.post("/api/chat/spot")
async def route_chat_spot(request: Request, body: PickSpotBody):
    return await chat_pick_spot(request, body)