import json
import os
from typing import Any, Dict

# 규칙(assets/kg_rules.json)을 가져오는 입구

def load_rules(base_dir: str) -> Dict[str, Any]:
    """Load kg_rules.json from backend/app/assets/kg/kg_rules.json."""
    path = os.path.join(base_dir, "assets", "kg", "kg_rules.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"kg rules json not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
