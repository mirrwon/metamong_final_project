import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, Form, HTTPException, UploadFile, File, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/auth")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DIR = os.path.join(BASE_DIR, "users")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(USER_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_username(name: str) -> str:
    return name.replace(os.sep, "_").replace(os.altsep or "", "_")


def _user_path(username: str) -> str:
    safe = _safe_username(username)
    return os.path.join(USER_DIR, f"{safe}.json")


def _save_profile_image(file: UploadFile, username: str) -> str:
    ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"
    safe = _safe_username(username)
    filename = f"profile_{safe}{ext}"
    dest = os.path.join(UPLOAD_DIR, filename)
    with open(dest, "wb") as f:
        f.write(file.file.read())
    return filename


def _build_profile_image_url(request: Request, filename: Optional[str]) -> Optional[str]:
    if not filename:
        return None
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/uploads/{filename}"


def _load_user(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="User not found")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_user(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@router.post("/register")
def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    name: str = Form(...),
    birthDate: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    profileImage: Optional[UploadFile] = File(None),
    age: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
) -> JSONResponse:
    path = _user_path(username)
    if os.path.exists(path):
        raise HTTPException(status_code=409, detail="Username already exists")

    record: Dict[str, Any] = {
        "user_num": str(uuid4()),
        "username": username,
        "password": password,
        "name": name,
        "birthDate": birthDate,
        "phone": phone,
        "email": email,
        "age": age,
        "gender": gender,
        "created_at": _now_iso(),
    }

    if profileImage:
        record["profile_image_filename"] = _save_profile_image(profileImage, username)

    _save_user(path, record)

    response = {k: v for k, v in record.items() if k != "password"}
    response["profileImageUrl"] = _build_profile_image_url(
        request, record.get("profile_image_filename")
    )
    return JSONResponse(response, status_code=201)


@router.post("/login")
def login(payload: Dict[str, Any], request: Request) -> JSONResponse:
    username = payload.get("username")
    password = payload.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")

    record = _load_user(_user_path(username))
    if record.get("password") != password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    response = {k: v for k, v in record.items() if k != "password"}
    response["profileImageUrl"] = _build_profile_image_url(
        request, record.get("profile_image_filename")
    )
    response["accessToken"] = "local-token"
    return JSONResponse(response)


@router.put("/profile")
def update_profile(
    request: Request,
    username: str = Form(...),
    password: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    birthDate: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    profileImage: Optional[UploadFile] = File(None),
    age: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
) -> JSONResponse:
    path = _user_path(username)
    record = _load_user(path)

    updates = {
        "name": name,
        "birthDate": birthDate,
        "phone": phone,
        "email": email,
        "age": age,
        "gender": gender,
    }
    for key, value in updates.items():
        if value is not None:
            record[key] = value

    if password:
        record["password"] = password

    if profileImage:
        record["profile_image_filename"] = _save_profile_image(profileImage, username)

    record["updated_at"] = _now_iso()
    _save_user(path, record)

    response = {k: v for k, v in record.items() if k != "password"}
    response["profileImageUrl"] = _build_profile_image_url(
        request, record.get("profile_image_filename")
    )
    return JSONResponse(response)