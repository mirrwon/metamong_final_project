import json
from typing import Any, Dict, Optional

from app.llm.gpt.gpt_judge import judge_with_gpt_4o_mini  # 기존 유틸 재사용
from .prompts_ko import SYSTEM_PROMPT_KO


def _safe_json_load(s: str) -> Dict[str, Any]:
    """
    LLM이 JSON만 내도록 유도하지만, 혹시 앞뒤에 텍스트가 섞이면
    가장 바깥 { ... }만 잘라 파싱을 시도한다.
    """
    s = (s or "").strip()
    if not s:
        return {}

    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        s = s[start : end + 1]

    try:
        return json.loads(s)
    except Exception:
        return {}


class LLMClient:
    def __init__(self, model: Optional[str] = None, system_prompt: Optional[str] = None):
        # model=None이면 env의 DITTO_GPT_MODEL 또는 gpt-4o-mini 사용
        self.model = model
        # system_prompt=None이면 기본 한국어 시스템 프롬프트 사용
        self.system_prompt = system_prompt or SYSTEM_PROMPT_KO

    def generate_json(self, user_payload: Dict[str, Any]) -> Dict[str, Any]:
        prompt = (
            "아래 입력을 보고, output_schema에 맞는 JSON만 출력해.\n\n"
            f"INPUT(JSON):\n{json.dumps(user_payload, ensure_ascii=False, indent=2)}\n"
        )

        resp = judge_with_gpt_4o_mini(
            prompt=prompt,
            system=self.system_prompt,  # ✅ 여기서 SYSTEM_PROMPT_KO가 실제로 쓰임
            model=self.model,
            temperature=0.2,
        )

        out = _safe_json_load((resp or {}).get("text", ""))

        # 최종 안전장치 (키 없으면 기본값)
        answer = out.get("answer")
        if not isinstance(answer, list) or not all(isinstance(x, str) for x in answer):
            answer = [user_payload.get("refusal_template", "현재 정보로는 답하기 어려워요.")]

        follow = out.get("followup_question")
        if not isinstance(follow, str):
            follow = ""

        return {"answer": answer[:3], "followup_question": follow}
