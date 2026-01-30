from __future__ import annotations

import os
import json
from typing import Dict, List, Optional, Tuple

# 네 로컬 경로에 맞게 기본값 잡되, 환경변수로도 바꿀 수 있게
DEFAULT_SCENE_ROOT = os.environ.get(
    "SCENE_ROOT",
    # r"C:\Users\나\Desktop\71765_json\71765_json\Training\02.labeling\3D 공간 모델"
    r"C:\Users\201\Desktop\71765_json\71765_json\Training\02.labeling\3D 공간 모델"
)

def load_scene_json(scene_root: str, sid: str) -> Optional[dict]:
    """
    sid.json을 찾아 로드.
    네 데이터 구조가:
      ...\3D 공간 모델\<sid>\<sid>.json
    형태인 걸 기준으로 최대한 안전하게 탐색.
    """
    # 1) 표준 케이스: <root>/<sid>/<sid>.json
    p1 = os.path.join(scene_root, sid, f"{sid}.json")
    if os.path.exists(p1):
        try:
            with open(p1, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    # 2) fallback: <root>/<sid>.json
    p2 = os.path.join(scene_root, f"{sid}.json")
    if os.path.exists(p2):
        try:
            with open(p2, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    return None


def infer_room_type_from_scene_json(scene_json: dict) -> str:
    """
    assets 기반으로 공간 타입 추론.
    (너가 준 예: toilet, washstand, showerhead, bed, cooktop 등)
    """
    assets = scene_json.get("assets") or []
    subs = []
    for a in assets:
        if not isinstance(a, dict):
            continue
        s = a.get("subclass") or ""
        if isinstance(s, str) and s:
            subs.append(s.lower())

    subs_set = set(subs)

    # 욕실
    bathroom_keys = {
        "toilet", "washstand", "bathtap", "bathtub", "showerhead", "shower",
        "bidet", "urinal"
    }
    # 주방
    kitchen_keys = {
        "cooktop", "stove", "sink", "kitchensink", "microwave", "refrigerator",
        "diningtable", "oven", "rangehood"
    }
    # 침실
    bedroom_keys = {
        "bed", "wardrobe", "dresser", "nightstand", "desk", "bookshelf"
    }
    # 거실(=공용/생활공간)
    living_keys = {
        "sofa", "tv", "coffeetable", "sidetable", "armchair", "bookshelf"
    }

    bathroom_score = len(subs_set & bathroom_keys)
    kitchen_score = len(subs_set & kitchen_keys)
    bedroom_score = len(subs_set & bedroom_keys)
    living_score  = len(subs_set & living_keys)

    # 점수 제일 높은 걸로
    scores = [
        ("욕실", bathroom_score),
        ("주방", kitchen_score),
        ("침실", bedroom_score),
        ("거실", living_score),
    ]
    scores.sort(key=lambda x: x[1], reverse=True)

    best_label, best_score = scores[0]
    if best_score <= 0:
        # 아무 단서 없으면 "거실"로 기본(원룸 공용 공간이 많아서)
        return "거실"
    return best_label


def list_scene_ids(scene_root: str = DEFAULT_SCENE_ROOT) -> List[str]:
    """
    scene_root 아래 폴더명을 scene id로 사용.
    """
    if not os.path.isdir(scene_root):
        return []
    out = []
    for name in os.listdir(scene_root):
        p = os.path.join(scene_root, name)
        if os.path.isdir(p):
            out.append(name)
    out.sort()
    return out


def build_room_groups(scene_root: str = DEFAULT_SCENE_ROOT) -> Dict[str, List[Dict[str, str]]]:
    """
    room_type -> [{id, label}] 리스트
    label은 UI에서 보여줄 텍스트. (우선은 id 그대로)
    """
    groups: Dict[str, List[Dict[str, str]]] = {"욕실": [], "주방": [], "침실": [], "거실": []}

    for sid in list_scene_ids(scene_root):
        sj = load_scene_json(scene_root, sid)
