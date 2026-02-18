from fastapi import APIRouter, Body, Depends
from app.api.deps import get_current_user

router = APIRouter(prefix="/api/tamagotchi", tags=["tamagotchi"])


@router.post("/state")
def get_tamagotchi_state(payload: dict = Body(default_factory=dict), current_user: dict = Depends(get_current_user)):
    # Placeholder route: model integration will populate this response.
    return {"ok": False, "reason": "not_implemented", "state": None}
