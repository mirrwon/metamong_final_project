import base64
import json
import os
import secrets
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

import requests
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.deps import get_current_user
from app.api.security import (
    clear_access_cookie,
    create_access_token,
    get_password_hash,
    is_password_hash,
    set_access_cookie,
    verify_password,
)
from app.db.mysql_repo import execute, fetch_all, fetch_one
from app.db.s3_client import get_object_url, upload_bytes

router = APIRouter(prefix="/api/auth")

OAUTH_STATE_TTL_SEC = 600
_oauth_state_cache: Dict[str, float] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value or "")


def _cleanup_oauth_state() -> None:
    now = time.time()
    expired = [key for key, ts in _oauth_state_cache.items() if now - ts > OAUTH_STATE_TTL_SEC]
    for key in expired:
        _oauth_state_cache.pop(key, None)


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise HTTPException(status_code=500, detail=f"Missing {name}")
    return value


def _google_oauth_config() -> Dict[str, str]:
    return {
        "client_id": _require_env("GOOGLE_CLIENT_ID"),
        "client_secret": _require_env("GOOGLE_CLIENT_SECRET"),
        "redirect_uri": _require_env("GOOGLE_REDIRECT_URI"),
    }


def _encode_oauth_payload(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False)
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def _safe_username(name: str) -> str:
    return "".join(c for c in (name or "") if c.isalnum() or c in ("-", "_", ".", "@"))[:120]


def _next_user_num() -> str:
    row = fetch_one(
        "SELECT MAX(CAST(user_num AS UNSIGNED)) AS max_num "
        "FROM users WHERE user_num REGEXP '^[0-9]+$'"
    )
    try:
        max_num = int((row or {}).get("max_num") or 0)
    except Exception:
        max_num = 0
    return str(max_num + 1)


def _fetch_user(username: str) -> Optional[Dict[str, Any]]:
    if not username:
        return None
    return fetch_one("SELECT * FROM users WHERE username=%s LIMIT 1", (username,))


def _user_response(row: Dict[str, Any], fallback_profile_url: Optional[str] = None) -> Dict[str, Any]:
    profile_url = row.get("profile_image_url") or fallback_profile_url
    return {
        "user_num": str(row.get("user_num") or ""),
        "user_name": row.get("username") or "",
        "username": row.get("username") or "",
        "name": row.get("name") or "",
        "birthDate": row.get("birth_date") or "",
        "phone": row.get("phone") or "",
        "email": row.get("email") or "",
        "gender": row.get("gender") or "",
        "zipcode": row.get("zipcode") or "",
        "address1": row.get("address1") or "",
        "address2": row.get("address2") or "",
        "provider": row.get("provider") or "",
        "oauth_sub": row.get("oauth_sub") or "",
        "created_at": _to_iso(row.get("created_at")),
        "profileImageUrl": profile_url,
    }


def _needs_profile(record: Dict[str, Any]) -> bool:
    required = ["gender", "birthDate", "phone", "zipcode", "address1"]
    for key in required:
        value = str(record.get(key, "") or "").strip()
        if not value:
            return True
    return False


def _upload_profile_image(file: UploadFile, username: str) -> tuple[Optional[str], Optional[str]]:
    content = file.file.read()
    if not content:
        return None, None

    ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"
    content_type = file.content_type or "application/octet-stream"
    safe_user = _safe_username(username) or "user"
    key = f"profiles/{safe_user}/{uuid4().hex}{ext}"

    if upload_bytes(key, content, content_type=content_type):
        return key, (get_object_url(key) or "")

    # Fallback for environments without configured S3.
    encoded = base64.b64encode(content).decode("ascii")
    return None, f"data:{content_type};base64,{encoded}"


def _verify_or_migrate_password(row: Dict[str, Any], password: str) -> bool:
    stored = str(row.get("password_hash") or "")
    if not stored or stored == "google-oauth":
        return False

    if is_password_hash(stored):
        try:
            return verify_password(password, stored)
        except Exception:
            return False

    if stored == password:
        execute(
            "UPDATE users SET password_hash=%s, updated_at=NOW(3) WHERE id=%s",
            (get_password_hash(password), row.get("id")),
        )
        return True

    return False


@router.get("/google")
def google_login() -> RedirectResponse:
    config = _google_oauth_config()
    _cleanup_oauth_state()
    state = secrets.token_urlsafe(24)
    _oauth_state_cache[state] = time.time()
    params = {
        "client_id": config["client_id"],
        "redirect_uri": config["redirect_uri"],
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return RedirectResponse(auth_url)


@router.get("/google/callback")
def google_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
) -> RedirectResponse:
    if error:
        raise HTTPException(status_code=400, detail=error)
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")

    _cleanup_oauth_state()
    if state and state not in _oauth_state_cache:
        raise HTTPException(status_code=400, detail="Invalid state")
    if state:
        _oauth_state_cache.pop(state, None)

    config = _google_oauth_config()
    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "redirect_uri": config["redirect_uri"],
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    if not token_resp.ok:
        raise HTTPException(status_code=400, detail="Token exchange failed")

    token_data = token_resp.json()
    id_token = token_data.get("id_token")
    if not id_token:
        raise HTTPException(status_code=400, detail="Missing id_token")

    info_resp = requests.get(
        "https://oauth2.googleapis.com/tokeninfo",
        params={"id_token": id_token},
        timeout=10,
    )
    if not info_resp.ok:
        raise HTTPException(status_code=400, detail="Token verification failed")
    info = info_resp.json()
    if info.get("aud") != config["client_id"]:
        raise HTTPException(status_code=400, detail="Invalid audience")

    email = info.get("email")
    sub = info.get("sub") or ""
    name = info.get("name")
    picture = info.get("picture")

    username = email or f"google_{sub}"
    row = _fetch_user(username)

    if row is None:
        execute(
            "INSERT INTO users ("
            "user_num, username, password_hash, name, birth_date, phone, email, gender, zipcode, "
            "address1, address2, provider, oauth_sub, profile_image_s3_key, profile_image_url, "
            "created_at, updated_at"
            ") VALUES ("
            "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(3), NOW(3)"
            ")",
            (
                _next_user_num(),
                username,
                "google-oauth",
                name or username,
                "",
                "",
                email or "",
                "",
                "",
                "",
                "",
                "google",
                sub,
                None,
                picture or None,
            ),
        )
    else:
        execute(
            "UPDATE users SET provider=%s, oauth_sub=%s, "
            "email=COALESCE(NULLIF(email, ''), %s), "
            "name=COALESCE(NULLIF(name, ''), %s), "
            "profile_image_url=COALESCE(NULLIF(profile_image_url, ''), %s), "
            "updated_at=NOW(3) WHERE id=%s",
            ("google", sub, email or "", name or "", picture or "", row.get("id")),
        )

    row = _fetch_user(username)
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to load oauth user")

    response = _user_response(row, fallback_profile_url=picture)
    response["needsProfile"] = _needs_profile(response)

    frontend_redirect = os.getenv("FRONTEND_OAUTH_REDIRECT", "http://localhost:3000/login")
    payload = _encode_oauth_payload(response)
    redirect_url = f"{frontend_redirect}?oauth=google&payload={urllib.parse.quote(payload)}"

    access_token = create_access_token(data={"sub": username})
    resp = RedirectResponse(redirect_url)
    set_access_cookie(resp, access_token)
    return resp


@router.post("/register")
def register(
    username: str = Form(...),
    password: str = Form(...),
    name: str = Form(...),
    birthDate: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    profileImage: Optional[UploadFile] = File(None),
    gender: Optional[str] = Form(None),
    zipcode: Optional[str] = Form(None),
    address1: Optional[str] = Form(None),
    address2: Optional[str] = Form(None),
) -> JSONResponse:
    existing = _fetch_user(username)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Username already exists")

    profile_key = None
    profile_url = None
    if profileImage:
        profile_key, profile_url = _upload_profile_image(profileImage, username)

    execute(
        "INSERT INTO users ("
        "user_num, username, password_hash, name, birth_date, phone, email, gender, zipcode, "
        "address1, address2, provider, oauth_sub, profile_image_s3_key, profile_image_url, "
        "created_at, updated_at"
        ") VALUES ("
        "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(3), NOW(3)"
        ")",
        (
            _next_user_num(),
            username,
            get_password_hash(password),
            name,
            birthDate,
            phone,
            email,
            gender,
            zipcode,
            address1,
            address2,
            "local",
            None,
            profile_key,
            profile_url,
        ),
    )

    row = _fetch_user(username)
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create user")

    response = _user_response(row)
    access_token = create_access_token(data={"sub": username})
    resp = JSONResponse(response, status_code=201)
    set_access_cookie(resp, access_token)
    return resp


@router.post("/login")
def login(payload: Dict[str, Any]) -> JSONResponse:
    username = payload.get("username")
    password = payload.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")

    row = _fetch_user(username)
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not _verify_or_migrate_password(row, password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    row = _fetch_user(username)
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    response = _user_response(row)
    access_token = create_access_token(data={"sub": username})
    resp = JSONResponse(response)
    set_access_cookie(resp, access_token)
    return resp


@router.put("/profile")
def update_profile(
    current_user: dict = Depends(get_current_user),
    password: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    birthDate: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    profileImage: Optional[UploadFile] = File(None),
    gender: Optional[str] = Form(None),
    zipcode: Optional[str] = Form(None),
    address1: Optional[str] = Form(None),
    address2: Optional[str] = Form(None),
) -> JSONResponse:
    username = current_user.get("user_name")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")

    row = _fetch_user(username)
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")

    is_oauth_user = row.get("provider") == "google" or bool(row.get("oauth_sub"))
    if password and is_oauth_user:
        raise HTTPException(status_code=400, detail="OAuth users cannot change password")

    updates: Dict[str, Any] = {}
    if name is not None:
        updates["name"] = name
    if birthDate is not None:
        updates["birth_date"] = birthDate
    if phone is not None:
        updates["phone"] = phone
    if email is not None:
        updates["email"] = email
    if gender is not None:
        updates["gender"] = gender
    if zipcode is not None:
        updates["zipcode"] = zipcode
    if address1 is not None:
        updates["address1"] = address1
    if address2 is not None:
        updates["address2"] = address2
    if password:
        updates["password_hash"] = get_password_hash(password)

    if profileImage:
        profile_key, profile_url = _upload_profile_image(profileImage, username)
        updates["profile_image_s3_key"] = profile_key
        updates["profile_image_url"] = profile_url

    if updates:
        clauses = [f"{col}=%s" for col in updates.keys()]
        params = list(updates.values())
        params.append(row.get("id"))
        execute(
            f"UPDATE users SET {', '.join(clauses)}, updated_at=NOW(3) WHERE id=%s",
            params,
        )

    row = _fetch_user(username)
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")

    return JSONResponse(_user_response(row))


@router.post("/logout")
def logout() -> JSONResponse:
    resp = JSONResponse({"ok": True})
    clear_access_cookie(resp)
    return resp


@router.get("/results")
def list_results() -> JSONResponse:
    rows = fetch_all(
        "SELECT id, image_path, image_s3_key, created_at "
        "FROM saved_recos ORDER BY id DESC LIMIT 100"
    )

    items = []
    for row in rows:
        image_key = str(row.get("image_s3_key") or "").strip()
        image_path = str(row.get("image_path") or "").strip()
        url = get_object_url(image_key) if image_key else image_path
        if not url:
            continue
        created_at = row.get("created_at")
        try:
            mtime = float(created_at.timestamp()) if created_at else 0.0
        except Exception:
            mtime = 0.0
        items.append(
            {
                "name": str(row.get("id") or ""),
                "url": url,
                "mtime": mtime,
            }
        )

    return JSONResponse({"items": items})
