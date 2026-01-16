import json
import os
from typing import Any, Dict, Optional

#실제 DB/Redis/파일에서 데이터를 모아서 **context** 를 만들어주는 곳

class ContextLoader:
    """
    목적: 질문 처리 시 필요한 DB/Redis/파일 기반 컨텍스트를 모아 반환.
    반환 스키마(중요):
    {
      "db": {...},
      "snapshot": {...}
    }
    """
    def __init__(
        self,
        mysql_client=None,
        redis_client=None,
        base_dir: Optional[str] = None,
        user_ctx: Optional[dict] = None,
     ):
        self.mysql = mysql_client
        self.redis = redis_client
        self.base_dir = base_dir
        self.user_ctx = user_ctx or {}

    def _load_result_latest_json(self) -> Optional[Dict[str, Any]]:
        """Fallback: backend/results/result_latest.json 읽기 (로컬 개발용)."""
        if not self.base_dir:
            return None
        p = os.path.join(self.base_dir, "..", "results", "result_latest.json")
        p = os.path.normpath(p)
        if not os.path.exists(p):
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def load(self, user_num: Any, session_id: Optional[str] = None) -> Dict[str, Any]:
        # TODO: 여기를 너희 DB/Redis 클라이언트로 채우면 됨.
        # 지금은 result_latest.json(있으면)에서 best_spot만 가져오는 최소 fallback 제공.
        snapshot: Dict[str, Any] = {}
        latest = self._load_result_latest_json()
        if latest and isinstance(latest, dict) and latest.get("best_spot"):
            snapshot["best_spot"] = latest.get("best_spot")

        profile: Dict[str, Any] = {}

        # 🔹 USER_CTX에서 유저 정보 가져오기
        u = self.user_ctx.get(user_num, {})

        filters = u.get("filters", {})
        if isinstance(filters, dict):
            exp = filters.get("experience")
            pet = filters.get("pet")

            if exp:
                profile["skill_level"] = exp  # "beginner" | "expert"

            if pet is not None:
                profile["has_pet"] = True if str(pet).lower() == "true" else False

        return {
            "db": {
                "reco_session": {"session_id": session_id} if session_id else {},
                "user_profile": profile,
                "recommendation_item": {},
                "plant": {},
                "spot_light_conditions": {},
                "render": {}
            },
            "snapshot": snapshot
        }
