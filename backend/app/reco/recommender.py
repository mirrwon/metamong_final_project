from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

def _load_plants_from_json(json_path: str) -> List[Dict[str, Any]]:
    try:
        p = Path(json_path)
        if not p.is_file():
            return []
        with p.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        items = obj.get("items")
        if isinstance(items, list):
            return [x for x in items if isinstance(x, dict)]
        return []
    except Exception:
        return []


def _clamp01(x: float) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except Exception:
        return 0.0


def _safe_get(d: dict, keys: list, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _light_score_from_times(times: dict) -> dict:
    """
    times: {"morning": f, "noon": f, "evening": f} (상대값)
    -> 0~1 normalize 후 가중평균
    """
    m = float(times.get("morning", 0.0) or 0.0)
    n = float(times.get("noon", 0.0) or 0.0)
    e = float(times.get("evening", 0.0) or 0.0)

    # 상대값 -> 0~1로 정규화 (max 기준)
    mx = max(m, n, e, 1e-9)
    mn = m / mx
    nn = n / mx
    en = e / mx

    # 정오 비중을 조금 더 주는 기본 가중치
    w_m, w_n, w_e = 0.30, 0.45, 0.25
    avg = (w_m * mn + w_n * nn + w_e * en)

    # bias 라벨
    bias = "noon"
    if mn >= nn and mn >= en:
        bias = "morning"
    elif en >= mn and en >= nn:
        bias = "evening"

    return {
        "m_norm": _clamp01(mn),
        "n_norm": _clamp01(nn),
        "e_norm": _clamp01(en),
        "avg": _clamp01(avg),
        "bias": bias,
    }


def _compute_spot_score(spot: dict) -> dict:
    """
    spot에서 가능한 값들로 점수 계산 + breakdown 리턴
    spot 구조를 '바꾸지 않고', 결과만 추가한다.
    """
    W_LIGHT = 0.60
    W_DIST = 0.20
    W_STAB = 0.20
    W_PENALTY = 0.80

    features = spot.get("features") or {}
    # solar 적용 전/후에 관계없이: times 우선, 없으면 times_cv, 둘 다 없으면 빈 dict
    times = features.get("times") or features.get("times_cv") or {}
    light = _light_score_from_times(times)
    light_score = light["avg"]  # 0~1

    # 거리: 값이 있으면 0~1로 매핑. 없으면 0.5 고정(중립)
    dist_raw = (
        features.get("dist_to_window")
        or features.get("distance_to_window")
        or features.get("distance")
    )
    if dist_raw is None:
        dist_score = 0.5
    else:
        # 가까울수록 좋음: 0m=1, 3m=0 정도로 선형(대충) 클램프
        d = max(0.0, float(dist_raw))
        dist_score = _clamp01(1.0 - (d / 3.0))

    # 안정도: 있으면 그대로(0~1 가정), 없으면 0.5
    stab_raw = features.get("stability") or features.get("depth_stability")
    if stab_raw is None:
        stab_score = 0.5
    else:
        stab_score = _clamp01(float(stab_raw))

    # 패널티: 있으면 0~1로 클램프, 없으면 0
    pen_raw = features.get("penalty") or features.get("occ_penalty") or 0.0
    penalty_score = _clamp01(float(pen_raw))

    base = (W_LIGHT * light_score + W_DIST * dist_score + W_STAB * stab_score)
    score = 100.0 * base - 100.0 * (W_PENALTY * penalty_score)

    return {
        "score": float(score),
        "breakdown": {
            "weights": {
                "W_LIGHT": W_LIGHT,
                "W_DIST": W_DIST,
                "W_STAB": W_STAB,
                "W_PENALTY": W_PENALTY,
            },
            "light": {
                "avg": light_score,
                "bias": light["bias"],
                "m_norm": light["m_norm"],
                "n_norm": light["n_norm"],
                "e_norm": light["e_norm"],
            },
            "dist": {"raw": dist_raw, "score": dist_score},
            "stability": {"raw": stab_raw, "score": stab_score},
            "penalty": {"raw": pen_raw, "score": penalty_score},
            "base": base,
        },
    }

def recommend_for_analysis(data: Dict[str, Any], user_filters: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {}

    user_filters = user_filters or {}
    pet = str(user_filters.get("pet", "")).lower()
    exp = str(user_filters.get("experience", "")).lower()

    # ✅ JSON 후보 로드 (프로젝트 구조에 맞게 상대경로 고정)
    # recommender.py 위치: app/reco/recommender.py 라는 가정
    base_dir = Path(__file__).resolve().parents[2]          # .../backend
    json_path = base_dir / "plantsData" / "plants_sample.json"
    plants = _load_plants_from_json(str(json_path))

    # ✅ 1차 필터: 반려동물 옵션
    if pet in ("true", "1", "yes"):
        plants = [p for p in plants if p.get("pet_safe") is True]

    # ✅ (임시) 경험치에 따른 간단 룰: beginner면 care 문구가 쉬운 쪽 우선
    # 지금은 데이터가 적으니까 "정렬 기준"만 둠
    def _ease_score(p: Dict[str, Any]) -> float:
        care = str(p.get("care", "")).lower()
        # 대충 키워드로만 가중치
        score = 0.0
        if "low" in care or "shade" in care or "indirect" in care:
            score += 0.3
        if "water when" in care or "dry" in care:
            score += 0.2
        return score

    if exp == "beginner":
        plants = sorted(plants, key=_ease_score, reverse=True)

    # ✅ candidates 형태로 변환(프론트가 기대하는 형태)
    candidates = []
    for p in plants:
        name = p.get("name") or p.get("id") or "unknown"
        candidates.append({
            "id": p.get("id"),
            "name": name,
            "image": p.get("image"),      # "/plants/monstera.jpg" 같은 값 그대로
            "reason": p.get("care") or "",
            "score": None,                # 지금은 비워도 됨(나중에 DB 붙이면 채움)
            "pet_safe": p.get("pet_safe"),
            "allergy": p.get("allergy"),
        })

    # ✅ 프론트 안정화: 항상 존재하게
    data["top_plants"] = candidates[:3]

    # ---- spots scoring / sorting (너 코드 그대로) ----
    spots = data.get("spots") or []
    for s in spots:
        if not isinstance(s, dict):
            continue
        res = _compute_spot_score(s)
        s.setdefault("features", {})
        s["features"]["score"] = res["score"]
        s["features"]["score_breakdown"] = res["breakdown"]

    spots_sorted = sorted(
        [s for s in spots if isinstance(s, dict)],
        key=lambda x: (x.get("features") or {}).get("score", -1e9),
        reverse=True
    )
    data["spots"] = spots_sorted
    data["best_spot"] = spots_sorted[0] if spots_sorted else None

    best_spot = data.get("best_spot")
    if isinstance(best_spot, dict):
        best_spot["top_plants"] = candidates[:3]

    return data