import json
import os
from typing import Any, Dict

# 규칙(assets/kg_rules.json)을 가져오는 입구


def load_rules(base_dir: str) -> dict:
    """Load kg_rules.json from backend/app/assets/kg/kg_rules.json."""

    # 1) base_dir/assets/kg/kg_rules.json
    cand1 = os.path.join(base_dir, "assets", "kg", "kg_rules.json")
    # 2) base_dir/kg/kg_rules.json  (base_dir가 assets일 때)
    cand2 = os.path.join(base_dir, "kg", "kg_rules.json")

    path = cand1 if os.path.exists(cand1) else cand2

    if not os.path.exists(path):
        raise FileNotFoundError(f"kg rules json not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
