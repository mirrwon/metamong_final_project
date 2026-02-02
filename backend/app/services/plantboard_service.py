import os
import json
import time
import base64
import uuid
import re
from typing import List, Optional
from app.config import PLANTS_DIR

# ✅ Conflict-free independent storage path
# Using 'plantboard_store' to avoid collision with other team members' 'data' folders
STORE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "plantboard_store")
PLANTS_FILE = os.path.join(STORE_DIR, "user_plants.json")
LOGS_FILE = os.path.join(STORE_DIR, "plant_logs.json")

# Ensure directory exists
os.makedirs(STORE_DIR, exist_ok=True)

def _load_json(filepath: str, default_val: any):
    if not os.path.exists(filepath):
        return default_val
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default_val

def _save_json(filepath: str, data: any):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[PlantBoard] Save Error: {e}")

def _process_base64_image(image_data: str, prefix: str = "img") -> str:
    """
    Base64 이미지를 파일로 저장하고 접근 가능한 URL을 반환합니다.
    이미 URL 형태이거나 비어있는 경우 그대로 반환합니다.
    """
    if not image_data or not isinstance(image_data, str):
        return image_data
    
    # 이미 URL인 경우 (http, /plants/ 등) 처리 생략
    if image_data.startswith(("http", "/api", "/plants", "/uploads", "/results")):
        return image_data
    
    # Base64 패턴 확인 (data:image/png;base64,...)
    match = re.match(r"data:image/(\w+);base64,(.*)", image_data)
    if not match:
        return image_data
    
    ext = match.group(1)
    base64_str = match.group(2)
    
    try:
        # 고유 파일명 생성
        filename = f"{prefix}_{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(PLANTS_DIR, filename)
        
        # 디렉토리 보장
        os.makedirs(PLANTS_DIR, exist_ok=True)
        
        # 디코딩 및 저장
        with open(filepath, "wb") as f:
            f.write(base64.b64decode(base64_str))
            
        # 프론트엔드에서 접근 가능한 정적 경로 반환
        return f"/plants/{filename}"
    except Exception as e:
        print(f"[PlantBoard] Image Process Error: {e}")
        return image_data

# --- Plants ---

def get_user_plants(username: str) -> List[dict]:
    # Structure: { username: [ {id, name, ...} ] }
    all_data = _load_json(PLANTS_FILE, {})
    return all_data.get(username, [])

def add_user_plant(username: str, plant_data: dict) -> dict:
    all_data = _load_json(PLANTS_FILE, {})
    user_list = all_data.get(username, [])
    
    # Image processing
    if "coverUrl" in plant_data:
        plant_data["coverUrl"] = _process_base64_image(plant_data["coverUrl"], "plant")
    
    # Simple ID generation
    new_id = f"plant_{int(time.time())}_{len(user_list)}"
    plant_data["id"] = new_id
    plant_data["created_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    
    user_list.append(plant_data)
    all_data[username] = user_list
    _save_json(PLANTS_FILE, all_data)
    return plant_data

# --- Logs ---

def get_plant_logs(username: str) -> List[dict]:
    # Structure: { username: [ {id, plant_id, action, date...} ] }
    all_data = _load_json(LOGS_FILE, {})
    user_logs = all_data.get(username, [])
    
    # Sort by date desc
    user_logs.sort(key=lambda x: x.get("date", ""), reverse=True)
    return user_logs

def add_plant_log(username: str, log_data: dict) -> dict:
    all_data = _load_json(LOGS_FILE, {})
    user_logs = all_data.get(username, [])
    
    # Image processing
    if "imageUrl" in log_data:
        log_data["imageUrl"] = _process_base64_image(log_data["imageUrl"], "log")
    
    new_id = f"log_{int(time.time())}_{len(user_logs)}"
    log_data["id"] = new_id
    # Ensure date exists
    if "date" not in log_data:
        log_data["date"] = time.strftime("%Y-%m-%d")
        
    user_logs.insert(0, log_data) # Prepend
    all_data[username] = user_logs
    _save_json(LOGS_FILE, all_data)
    return log_data

def delete_plant_log(username: str, log_id: str) -> bool:
    all_data = _load_json(LOGS_FILE, {})
    user_logs = all_data.get(username, [])
    
    initial_len = len(user_logs)
    user_logs = [log for log in user_logs if log.get("id") != log_id]
    
    if len(user_logs) != initial_len:
        all_data[username] = user_logs
        _save_json(LOGS_FILE, all_data)
        return True
    return False
