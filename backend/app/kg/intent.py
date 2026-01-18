from typing import Any, Dict

# 유저 질문 텍스트를 보고 의도(intent) 분류

def _contains_any(text: str, keywords: list[str]) -> bool:
    t = (text or "").lower()
    return any((k or "").lower() in t for k in keywords)

def detect_intent(question: str, rules: Dict[str, Any]) -> str:
    """Rule-based intent detection using keyword matching."""
    q = question or ""

    # 1) Out-of-scope deny first
    oos = rules.get("out_of_scope", {})
    deny_any = oos.get("deny_keywords_any", [])
    if _contains_any(q, deny_any):
        return oos.get("deny_intent", "OUT_OF_SCOPE")

    # 2) Keyword intents by priority
    intents = rules.get("intents", [])
    intents = sorted(intents, key=lambda x: int(x.get("priority", 0)), reverse=True)

    for it in intents:
        kws_any = it.get("keywords_any", [])
        kws_all = it.get("keywords_all", [])
        deny = it.get("deny_keywords", [])

        if deny and _contains_any(q, deny):
            continue

        any_ok = True if not kws_any else _contains_any(q, kws_any)

        if kws_all:
            tq = q.lower()
            all_ok = all((k or "").lower() in tq for k in kws_all)
        else:
            all_ok = True

        if any_ok and all_ok:
            return it.get("id", "UNKNOWN")

    return "UNKNOWN"
