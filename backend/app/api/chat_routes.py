from __future__ import annotations

from fastapi import APIRouter, Request, UploadFile, File, Form
from typing import Optional, List
from pathlib import Path

from .chat_progress import stream_route
from .chat_handlers import (
    chat_get,
    chat_post,
    chat_image,
    chat_pick_spot,
    get_filters,
    PickSpotBody,
    get_results,
)

from .chat_survey import survey_router

from app.cv.pipeline import list_71765_scenes
from app.cv.scene_room_infer import infer_room_type_from_scene_json, load_scene_json
from app.cv.scene_catalog import build_room_groups, DEFAULT_SCENE_ROOT, pick_scene_for_room

SCENE_ROOT = Path(r"C:\Users\201\Desktop\71765_json\71765_json")

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
    groups = build_room_groups(DEFAULT_SCENE_ROOT)

    # UI는 options만 필요하니까 간단히
    options = []
    for k in ["거실", "침실", "주방", "욕실"]:
        cnt = len(groups.get(k) or [])
        options.append({"key": k, "label": f"{k} ({cnt})"})

    return {"ok": True, "type": "room_groups", "options": options}

def get_scenes():
    scenes = list_71765_scenes()
    out = []

    for sid in scenes:
        scene_json = load_scene_json(SCENE_ROOT, sid)
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

@router.get("/api/chat/scenes/all")
def route_scenes_all():
    scenes = list_71765_scenes()
    out = []

    for sid in scenes:
        scene_json = load_scene_json(SCENE_ROOT, sid)
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
    room_type: Optional[str] = Form(None),
):
    return await chat_image(
        request,
        files=files,
        image=image,
        meta=meta,
        scene_id=scene_id,
        room_type=room_type,
    )

@router.post("/api/chat/spot")
async def route_chat_spot(request: Request, body: PickSpotBody):
    return await chat_pick_spot(request, body)

@router.get("/api/chat/results")
def route_results():
    return get_results()

