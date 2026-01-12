# api_server.py
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from chat_routes import router as chat_router
from app.redis_client import get_redis, get_redis_error

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_DIR = os.path.join(BASE_DIR, "results")
os.makedirs(RESULT_DIR, exist_ok=True)

load_dotenv(os.path.join(BASE_DIR, ".env"))

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# viz 이미지 접근용
app.mount("/results", StaticFiles(directory=RESULT_DIR), name="results")

app.include_router(chat_router)

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/debug/redis")
def redis_debug():
    r = get_redis()
    if not r:
        return {"ok": False, "reason": "no_connection", "error": get_redis_error()}
    try:
        r.ping()
    except Exception:
        return {"ok": False, "reason": "ping_failed"}

    prefix = os.getenv("REDIS_PLANTS_PREFIX", "").strip()
    count = None
    if prefix:
        try:
            cursor = 0
            count = 0
            limit = 5000
            while True:
                cursor, keys = r.scan(cursor=cursor, match=f"{prefix}*", count=200)
                count += len(keys)
                if cursor == 0 or count >= limit:
                    break
        except Exception:
            count = None

    sample_name = None
    if prefix:
        try:
            sample_key = f"{prefix}1"
            raw = r.execute_command("JSON.GET", sample_key, "$.이름ko")
            sample_name = raw
        except Exception:
            sample_name = None

    return {
        "ok": True,
        "prefix": prefix or None,
        "key_count": count,
        "sample_name": sample_name,
    }
