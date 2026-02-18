from __future__ import annotations

import os
import json
import httpx

GPU_SERVER_URL = os.getenv("GPU_SERVER_URL", "http://127.0.0.1:9001")

async def gpu_analyze(image_bytes: bytes, filename: str, user_opts: dict | None = None, max_n: int | None = None):
    url = f"{GPU_SERVER_URL}/cv/analyze"
    files = {"image": (filename, image_bytes, "application/octet-stream")}

    data = {}
    if user_opts is not None:
        data["user_opts"] = json.dumps(user_opts, ensure_ascii=False)
    if max_n is not None:
        data["max_n"] = str(int(max_n))

    # 필요하면 debug_viz/save_outputs도 추가 가능
    data["debug_viz"] = "false"
    data["save_outputs"] = "true"

    async with httpx.AsyncClient(timeout=600.0) as client:
        r = await client.post(url, files=files, data=data)
        r.raise_for_status()
        return r.json()
