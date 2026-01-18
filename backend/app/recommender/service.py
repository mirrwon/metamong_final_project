from __future__ import annotations
from typing import Any, Dict, List, Optional

from app.solar.solar_client import SolarClient
# DB 붙이면
# from app.db.mysql_client import MySQLClient



# ✅ 제품형 인터페이스:
# - 입력: analysis(result_latest.json dict), user_filters(dict)
# - 출력: analysis dict에 spots[*].top_plants 채워서 반환

def recommend_for_analysis(
    analysis: Dict[str, Any],
    user_filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    제품형 recommender 자리.
    지금은 DB 없으니 임시 규칙/목록으로 채우되,
    나중에 DB+Solar+LLaMA로 내부만 교체하면 됨.
    """
    if not isinstance(analysis, dict):
        return analysis

    spots = analysis.get("spots")
    if not isinstance(spots, list):
        return analysis

    # filters normalize
    user_filters = user_filters or {}
    exp = (user_filters.get("experience") or "").lower()   # "beginner" / "expert"
    pet = str(user_filters.get("pet", "")).lower()         # "true"/"false" or bool

    is_beginner = (exp != "expert")
    has_pet = (pet == "true") or (pet is True)

    # ✅ 임시 후보군 (나중에 DB plant_catalog에서 읽게 바꿀 것)
    catalog = [
        {"name": "산세베리아", "pet_safe": True,  "difficulty": 1, "light": ["dim", "medium"]},
        {"name": "스투키",     "pet_safe": True,  "difficulty": 1, "light": ["dim", "medium"]},
        {"name": "아레카야자", "pet_safe": True,  "difficulty": 2, "light": ["medium", "bright"]},
        {"name": "몬스테라",   "pet_safe": False, "difficulty": 2, "light": ["medium", "bright"]},
        {"name": "올리브나무", "pet_safe": True,  "difficulty": 3, "light": ["bright"]},
    ]

    def ok(p: Dict[str, Any], light_level: str) -> bool:
        if has_pet and (p.get("pet_safe") is False):
            return False
        if is_beginner and int(p.get("difficulty", 2)) >= 3:
            return False
        if light_level and light_level not in (p.get("light") or []):
            return False
        return True

    def pick(light_level: str, spot_usage: str, k: int = 3) -> List[Dict[str, str]]:
        picked: List[Dict[str, str]] = []
        for p in catalog:
            if ok(p, light_level):
                reason = f"{spot_usage} + {light_level} 환경 + 필터 반영"
                picked.append({"name": p["name"], "reason": reason})
            if len(picked) >= k:
                break
        return picked

    for s in spots:
        if not isinstance(s, dict):
            continue
        spot_usage = s.get("spot_usage") or "floor_large"
        light_level = ((s.get("light_profile") or {}).get("level")) or "medium"

        s["top_plants"] = pick(light_level=light_level, spot_usage=spot_usage, k=3)

    # best_spot도 spots[0]과 동일 객체라 자동 반영되지만,
    # 혹시 스키마가 달라질 수 있으니 best_spot도 sync
    if isinstance(analysis.get("best_spot"), dict) and isinstance(spots[0], dict):
        analysis["best_spot"]["top_plants"] = spots[0].get("top_plants", [])

    return analysis
