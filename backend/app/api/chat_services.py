from __future__ import annotations

import os
import json
import time
import random
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Request, UploadFile
from app.config import BASE_DIR, RESULT_DIR, UPLOAD_DIR, ASSET_DIR

from app.cv.pipeline import run_pipeline
from app.reco.recommender import recommend_for_analysis
from app.solar.kier_client import KierSolarClient

from app.llm.image_edit import composite_plant_on_original
from app.llm.gemini.gemini_image_edit import gemini_edit_image

from app.kg.rules import load_rules
from app.kg.context_loader import ContextLoader
from app.kg.llm_client import LLMClient
from app.kg.service import handle_chat

from .chat_progress import progress
from .chat_storage import (
    get_user_ctx, set_user_ctx, get_user_state, set_user_state,
    db_save_reco, db_list_recos,
)
from .chat_utils import (
    abs_url, cache_bust_url, to_results_url, scene_to_label,
    now_kst_yyyymmdd_hhmm, get_lat_lot_from_meta, extract_best_xy
)

KG_RULES = load_rules(ASSET_DIR)
KG_LOADER = ContextLoader(mysql_client=None, redis_client=None, base_dir=BASE_DIR, user_ctx={})
KG_LLM = LLMClient()

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)

LATEST_JSON = os.path.join(RESULT_DIR, "result_latest.json")
LATEST_MARKER = os.path.join(RESULT_DIR, "result_latest_marker.png")
LATEST_COMPOSITE = os.path.join(RESULT_DIR, "result_latest_composite.png")
AI_EDIT_AUTO = os.path.join(RESULT_DIR, "result_latest_ai_edit_auto.png")
AI_EDIT_MANUAL = os.path.join(RESULT_DIR, "result_latest_ai_edit_manual.png")

def load_latest_result() -> Dict[str, Any]:
    if not os.path.exists(LATEST_JSON):
        return {}
    with open(LATEST_JSON, "r", encoding="utf-8") as f:
        obj = json.load(f)
    return obj if isinstance(obj, dict) else {}

def save_latest_result(data: Dict[str, Any]):
    with open(LATEST_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def gen_auto_ai_edit(marker_path: str, best_xy: Optional[List[float]]):
    prompt = (
        "Add a realistic potted plant at the recommended spot on the floor. "
        "Match lighting and perspective naturally. Do not change the room layout."
    )
    if best_xy:
        prompt += f" The spot coordinates are {best_xy}."
    return gemini_edit_image(input_image_path=marker_path, prompt=prompt, out_path=AI_EDIT_AUTO)

def gen_manual_ai_edit(marker_path: str, prompt: str):
    return gemini_edit_image(input_image_path=marker_path, prompt=prompt, out_path=AI_EDIT_MANUAL)

def build_images_payload(request: Request, files: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
    ts_ms = int(time.time() * 1000)
    out: List[Dict[str, Any]] = []
    for label, abs_path in files:
        if abs_path and os.path.exists(abs_path):
            out.append({"name": label, "url": cache_bust_url(request, to_results_url(abs_path), ts_ms)})
    return out

def pick_plant_for_spot(top_plants: Any, spot_index: int) -> str:
    if not isinstance(top_plants, list) or len(top_plants) == 0:
        return "potted plant"
    ranked = sorted([p for p in top_plants if isinstance(p, dict)], key=lambda x: x.get("score", 0), reverse=True)
    if spot_index < len(ranked):
        return ranked[spot_index].get("name") or "potted plant"
    weights = [max(p.get("score", 0.1), 0.05) for p in ranked]
    chosen = random.choices(ranked, weights=weights, k=1)[0]
    return chosen.get("name") or "potted plant"