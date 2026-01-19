from __future__ import annotations

import os
from io import BytesIO
from typing import Any, Dict

from PIL import Image

try:
    from google import genai
except Exception:
    genai = None


def gemini_edit_image(
    *,
    input_image_path: str,
    prompt: str,
    out_path: str,
    model: str = "gemini-2.5-flash-image",
    api_key_env: str = "GEMINI_API_KEY",
) -> Dict[str, Any]:
    """
    Gemini 이미지 편집 호출 (marker 이미지 기반)
    반환: {"ok": bool, "out_path": str?, "reason": str?}
    """
    if genai is None:
        return {"ok": False, "reason": "google-genai not installed. pip install google-genai"}

    api_key = os.getenv(api_key_env)
    if not api_key:
        return {"ok": False, "reason": f"{api_key_env} missing in environment"}

    if not os.path.exists(input_image_path):
        return {"ok": False, "reason": f"input not found: {input_image_path}"}

    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    try:
        client = genai.Client(api_key=api_key)
        img = Image.open(input_image_path)

        response = client.models.generate_content(
            model=model,
            contents=[prompt, img],
        )

        saved = False
        for cand in (response.candidates or []):
            content = getattr(cand, "content", None)
            if not content:
                continue
            for part in (content.parts or []):
                inline = getattr(part, "inline_data", None)
                if inline and getattr(inline, "data", None):
                    out_img = Image.open(BytesIO(inline.data))
                    out_img.save(out_path)
                    saved = True
                    break
            if saved:
                break

        if not saved:
            return {"ok": False, "reason": "no image returned from gemini"}

        return {"ok": True, "out_path": out_path}

    except Exception as e:
        return {"ok": False, "reason": f"gemini error: {e}"}
