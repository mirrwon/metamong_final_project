from fastapi import APIRouter, Body, Query, Depends
from typing import List, Optional
from app.services import plantboard_service
from app.api.deps import get_current_user

router = APIRouter(prefix="/api/plantboard", tags=["plantboard"]) 

@router.get("/plants")
def get_plants(current_user: dict = Depends(get_current_user)):
    user = current_user["user_name"]
    plants = plantboard_service.get_user_plants(user)
    return {"ok": True, "items": plants}

@router.post("/plants")
def add_plant(payload: dict = Body(...), current_user: dict = Depends(get_current_user)):
    user = current_user["user_name"]
    plant_data = payload.get("plant", {})
    
    new_plant = plantboard_service.add_user_plant(user, plant_data)
    return {"ok": True, "item": new_plant}

@router.get("/logs")
def get_logs(current_user: dict = Depends(get_current_user)):
    user = current_user["user_name"]
    logs = plantboard_service.get_plant_logs(user)
    return {"ok": True, "items": logs}

@router.post("/logs")
def add_log(payload: dict = Body(...), current_user: dict = Depends(get_current_user)):
    user = current_user["user_name"]
    log_data = payload.get("log", {})
    
    new_log = plantboard_service.add_plant_log(user, log_data)
    return {"ok": True, "item": new_log}

@router.delete("/logs/{log_id}")
def delete_log(log_id: str, current_user: dict = Depends(get_current_user)):
    user = current_user["user_name"]
    success = plantboard_service.delete_plant_log(user, log_id)
    return {"ok": success}
