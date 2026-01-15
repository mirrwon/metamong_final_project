from typing import Any, Dict, Optional

# 의도(intent)별로 이 질문에 답하려면 최소 어떤 근거가 필요해? 를 검사하는 도구

def get_path(obj: Dict[str, Any], path: str) -> Any:
    """Get nested value by dotted path. Returns None if missing."""
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur

def has_any_evidence(context: Dict[str, Any], paths: list[str]) -> bool:
    return any(get_path(context, p) is not None for p in paths)

def find_requirement(intent_id: str, rules: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for r in rules.get("evidence_requirements", []):
        if r.get("intent_id") == intent_id:
            return r
    return None
