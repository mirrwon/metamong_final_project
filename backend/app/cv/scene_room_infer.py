import json
from pathlib import Path
from collections import Counter
from typing import Optional

def load_scene_json(scene_root: Path, scene_id: str) -> Optional[dict]:
    scene_path = scene_root / f"{scene_id}.json"
    if not scene_path.exists():
        return None

    try:
        with open(scene_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def infer_room_type_from_scene_json(scene_json: dict) -> str:
    objects = scene_json.get("objects", [])
    if not objects:
        return "기타"

    classes = []
    subclasses = []

    for obj in objects:
        if not isinstance(obj, dict):
            continue
        if obj.get("class"):
            classes.append(obj["class"])
        if obj.get("subclass"):
            subclasses.append(obj["subclass"])

    class_cnt = Counter(classes)
    sub_cnt = Counter(subclasses)

    if class_cnt.get("bathroom_furniture", 0) >= 1:
        return "욕실"
    if sub_cnt.get("bed", 0) >= 1:
        return "침실"
    if any("kitchen" in s for s in subclasses):
        return "주방"
    if sub_cnt.get("sofa", 0) >= 1:
        return "거실"

    return "기타"
