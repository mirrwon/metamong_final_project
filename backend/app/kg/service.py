from typing import Any, Dict, Optional
from .intent import detect_intent
from .evidence import find_requirement, has_any_evidence
from .prompts_ko import SYSTEM_PROMPT_KO
from .llm_client import LLMClient

def handle_chat(
    question: str,
    user_num: int,
    session_id: Optional[str],
    rules: Dict[str, Any],
    loader,
    llm: LLMClient
) -> Dict[str, Any]:
    intent = detect_intent(question, rules)

    # out_of_scope
    if intent == rules.get("out_of_scope", {}).get("deny_intent", "OUT_OF_SCOPE"):
        tid = rules["out_of_scope"]["deny_response_template_id"]
        return {"answer": [rules["templates"][tid]], "followup_question": ""}

    context = loader.load(user_num=user_num, session_id=session_id)

    # evidence requirements
    req = find_requirement(intent, rules)
    if req:
        ok = has_any_evidence(context, req.get("require_any_paths", []))
        if not ok:
            tid = req.get("when_missing_template_id")
            return {"answer": [rules["templates"][tid]], "followup_question": ""}

    # fallback flow (redo)
    fb = rules.get("fallback_flow", {})
    if intent == fb.get("intent_id"):
        ask = fb.get("ask", {}).get("question", "어떤 부분을 다시 해볼까요?")
        return {"answer": [ask], "followup_question": ""}

    # LLM payload (Korean)
    refusal = "현재 저장된 정보로는 정확히 답하기 어려워요."
    if req and req.get("when_missing_template_id"):
        refusal = rules["templates"][req["when_missing_template_id"]]

    user_payload = {
        "mode": "EVIDENCE_ONLY",
        "intent": intent,
        "question": question,
        "refusal_template": refusal,
        "evidence": context,
        "output_schema": {"answer": ["string"], "followup_question": "string_or_empty"}
    }
    # return llm.generate_json(SYSTEM_PROMPT_KO, user_payload)
    return llm.generate_json( user_payload) # llm_client -> def generate_json 인자 2개사용 중

