# app/reco/recommender.py
from __future__ import annotations
from typing import Any, Dict, List


def recommend_for_analysis(data: Dict[str, Any], user_filters: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    목적:
    - pipeline 결과(result_latest.json)의 best_spot/top_plants를 채워준다.
    - 지금 단계에서는 "동작 보장"이 목표 (추천 로직은 이후에 고도화)

    입력:
      data: pipeline이 만든 dict (best_spot, spots 포함)
      user_filters: {"experience": "...", "pet": "..."} 같은 필터

    출력:
      top_plants가 채워진 data
    """

    if not isinstance(data, dict):
        return {}

    user_filters = user_filters or {}

    # ---- 최소 더미 추천 리스트(나중에 DB/Redis 붙이면 여기만 교체) ----
    # pet=true면 독성 낮은 쪽, beginner면 관리 쉬운 쪽으로 대충 분기만 해둠
    pet = str(user_filters.get("pet", "")).lower()
    exp = str(user_filters.get("experience", "")).lower()

    if pet in ("true", "1", "yes"):
        candidates = [
            {"name": "테이블야자", "reason": "반려동물 친화로 많이 추천됨", "score": 0.86},
            {"name": "아레카야자", "reason": "실내 공기정화 + 비교적 안전", "score": 0.82},
            {"name": "스파티필름", "reason": "저광량에서도 버팀(단, 과습 주의)", "score": 0.78},
        ]
    elif exp == "beginner":
        candidates = [
            {"name": "스투키", "reason": "초보자도 관리 쉬움", "score": 0.86},
            {"name": "산세베리아", "reason": "물 적게 줘도 됨", "score": 0.83},
            {"name": "몬스테라", "reason": "성장 빠르고 관리 난이도 중", "score": 0.78},
        ]
    else:
        candidates = [
            {"name": "몬스테라", "reason": "공간 연출 좋음", "score": 0.84},
            {"name": "떡갈고무나무", "reason": "중대형 포인트 식물", "score": 0.80},
            {"name": "필로덴드론", "reason": "잎 연출 좋고 다양한 품종", "score": 0.77},
        ]

    # ---- best_spot/top_plants 채우기 ----
    best_spot = data.get("best_spot")
    if isinstance(best_spot, dict):
        best_spot["top_plants"] = candidates[:3]

    # ---- spots 각각도 채우기(원하면) ----
    spots = data.get("spots")
    if isinstance(spots, list):
        for s in spots:
            if isinstance(s, dict):
                s["top_plants"] = candidates[:3]

    return data
