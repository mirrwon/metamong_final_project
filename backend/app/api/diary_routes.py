import base64
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.api.deps import get_current_user
from app.db.mysql_repo import execute, fetch_all, fetch_one
from app.db.s3_client import get_object_url, upload_bytes

router = APIRouter(prefix="/api/diary")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value or "")


def _fetch_user_id(username: str) -> int:
    row = fetch_one("SELECT id FROM users WHERE username=%s LIMIT 1", (username,))
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return int(row["id"])


def _upload_diary_image(file: UploadFile, user_id: int, diary_id: str) -> tuple[Optional[str], Optional[str]]:
    content = file.file.read()
    if not content:
        return None, None

    ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"
    content_type = file.content_type or "application/octet-stream"
    key = f"diary/{user_id}/{diary_id}{ext}"

    if upload_bytes(key, content, content_type=content_type):
        return key, (get_object_url(key) or "")

    # Fallback for environments without S3.
    encoded = base64.b64encode(content).decode("ascii")
    return None, f"data:{content_type};base64,{encoded}"


def _serialize_diary(row: Dict[str, Any], username: str) -> Dict[str, Any]:
    image_url = row.get("image_url") or ""
    return {
        "id": row.get("id"),
        "title": row.get("title") or "",
        "content": row.get("content") or "",
        "username": username,
        "image_url": image_url,
        "imageUrl": image_url,
        "created_at": _to_iso(row.get("created_at")),
        "updated_at": _to_iso(row.get("updated_at")),
    }


@router.get("")
def list_diary(current_user: dict = Depends(get_current_user)) -> JSONResponse:
    username = current_user.get("user_name")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = _fetch_user_id(username)
    rows = fetch_all(
        "SELECT id, title, content, image_url, created_at, updated_at "
        "FROM diary_entries WHERE user_id=%s ORDER BY updated_at DESC",
        (user_id,),
    )
    items = [_serialize_diary(row, username) for row in rows]
    return JSONResponse({"items": items})


@router.get("/{diary_id}")
def get_diary(
    diary_id: str,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    username = current_user.get("user_name")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = _fetch_user_id(username)
    row = fetch_one(
        "SELECT id, title, content, image_url, created_at, updated_at "
        "FROM diary_entries WHERE id=%s AND user_id=%s LIMIT 1",
        (diary_id, user_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Diary not found")

    return JSONResponse(_serialize_diary(row, username))


@router.post("")
def create_diary(
    title: str = Form(...),
    content: str = Form(...),
    image: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    username = current_user.get("user_name")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = _fetch_user_id(username)
    diary_id = str(uuid4())
    image_key = None
    image_url = None

    if image:
        image_key, image_url = _upload_diary_image(image, user_id, diary_id)

    execute(
        "INSERT INTO diary_entries ("
        "id, user_id, title, content, image_s3_key, image_url, created_at, updated_at"
        ") VALUES ("
        "%s, %s, %s, %s, %s, %s, NOW(3), NOW(3)"
        ")",
        (diary_id, user_id, title, content, image_key, image_url),
    )

    row = fetch_one(
        "SELECT id, title, content, image_url, created_at, updated_at "
        "FROM diary_entries WHERE id=%s LIMIT 1",
        (diary_id,),
    )
    if not row:
        raise HTTPException(status_code=500, detail="Failed to create diary")

    return JSONResponse(_serialize_diary(row, username), status_code=201)


@router.put("/{diary_id}")
def update_diary(
    diary_id: str,
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    username = current_user.get("user_name")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = _fetch_user_id(username)
    exists = fetch_one(
        "SELECT id FROM diary_entries WHERE id=%s AND user_id=%s LIMIT 1",
        (diary_id, user_id),
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Diary not found")

    updates: Dict[str, Any] = {}
    if title is not None:
        updates["title"] = title
    if content is not None:
        updates["content"] = content
    if image:
        image_key, image_url = _upload_diary_image(image, user_id, diary_id)
        updates["image_s3_key"] = image_key
        updates["image_url"] = image_url

    if updates:
        clauses = [f"{col}=%s" for col in updates.keys()]
        params = list(updates.values())
        params.extend([diary_id, user_id])
        execute(
            f"UPDATE diary_entries SET {', '.join(clauses)}, updated_at=NOW(3) "
            "WHERE id=%s AND user_id=%s",
            params,
        )
    else:
        execute(
            "UPDATE diary_entries SET updated_at=NOW(3) WHERE id=%s AND user_id=%s",
            (diary_id, user_id),
        )

    row = fetch_one(
        "SELECT id, title, content, image_url, created_at, updated_at "
        "FROM diary_entries WHERE id=%s AND user_id=%s LIMIT 1",
        (diary_id, user_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail="Diary not found")

    return JSONResponse(_serialize_diary(row, username))


@router.delete("/{diary_id}")
def delete_diary(
    diary_id: str,
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    username = current_user.get("user_name")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = _fetch_user_id(username)
    deleted = execute("DELETE FROM diary_entries WHERE id=%s AND user_id=%s", (diary_id, user_id))
    if deleted <= 0:
        raise HTTPException(status_code=404, detail="Diary not found")

    return JSONResponse({"ok": True, "id": diary_id})
