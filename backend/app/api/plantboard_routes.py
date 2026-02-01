from fastapi import APIRouter, Body, Query
from typing import List, Optional
from app.services import plantboard_service

router = APIRouter(prefix="/api/plantboard", tags=["plantboard"])

# Temporary mock user since auth might not be fully linked in frontend yet
# In real integration, we would extract user from token
def get_current_user_id():
    return "test_user" 

@router.get("/plants")
def get_plants(username: Optional[str] = None):
    # If username not provided, use default
    user = username or get_current_user_id()
    plants = plantboard_service.get_user_plants(user)
    return {"ok": True, "items": plants}

@router.post("/plants")
def add_plant(payload: dict = Body(...)):
    user = payload.get("username") or get_current_user_id()
    plant_data = payload.get("plant", {})
    
    new_plant = plantboard_service.add_user_plant(user, plant_data)
    return {"ok": True, "item": new_plant}

@router.get("/logs")
def get_logs(username: Optional[str] = None):
    user = username or get_current_user_id()
    logs = plantboard_service.get_plant_logs(user)
    return {"ok": True, "items": logs}

@router.post("/logs")
def add_log(payload: dict = Body(...)):
    user = payload.get("username") or get_current_user_id()
    log_data = payload.get("log", {})
    
    new_log = plantboard_service.add_plant_log(user, log_data)
    return {"ok": True, "item": new_log}

@router.delete("/logs/{log_id}")
def delete_log(log_id: str, username: Optional[str] = None):
    user = username or get_current_user_id()
    success = plantboard_service.delete_plant_log(user, log_id)
    return {"ok": success}
