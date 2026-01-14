import os
from typing import Optional, Tuple

import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

_last_error: Optional[str] = None


def _get_settings() -> Tuple[str, str]:
    api_url = os.getenv("VERCEL_BLOB_API_URL", "https://api.vercel.com/v2/blob")
    token = os.getenv("metamong_READ_WRITE_TOKEN", "")
    return api_url, token


def ping_vercel_blob() -> bool:
    global _last_error
    api_url, token = _get_settings()
    if not token:
        _last_error = "missing_token"
        return False

    try:
        resp = requests.get(
            api_url,
            headers={"Authorization": f"Bearer {token}"},
            params={"limit": 1},
            timeout=5,
        )
    except Exception as exc:
        _last_error = repr(exc)
        return False

    if resp.status_code in (200, 204):
        _last_error = None
        return True

    _last_error = f"status_{resp.status_code}"
    return False


def get_vercel_blob_error() -> Optional[str]:
    return _last_error
