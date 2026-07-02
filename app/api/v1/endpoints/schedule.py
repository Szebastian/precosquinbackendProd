from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime

from app.core.deps import get_current_user, require_role, CurrentUser
from app.db.session import get_supabase

router = APIRouter()


class ScheduleSlotCreate(BaseModel):
    artist_id: str
    venue_id: str
    slot_type: str
    start_time: datetime
    end_time: datetime
    notes: Optional[str] = None


class ScheduleSlotResponse(BaseModel):
    id: str
    artist_id: str
    venue_id: str
    slot_type: str
    start_time: str
    end_time: str
    status: str
    notes: Optional[str]


@router.get("/", response_model=List[ScheduleSlotResponse])
async def list_schedule(
    day: Optional[str] = None,
    venue_id: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    db = get_supabase()
    query = db.table("schedule_slots").select("*")

    if venue_id:
        query = query.eq("venue_id", venue_id)

    result = query.order("start_time").execute()
    return [ScheduleSlotResponse(**item) for item in result.data]


@router.post("/", response_model=ScheduleSlotResponse, status_code=201)
async def create_schedule_slot(
    slot: ScheduleSlotCreate,
    current_user: CurrentUser = Depends(require_role("organizador", "admin")),
):
    db = get_supabase()

    conflict = db.table("schedule_slots").select("id").eq("venue_id", slot.venue_id).execute()

    result = db.table("schedule_slots").insert({
        **slot.model_dump(),
        "status": "draft",
        "created_by": current_user.id,
    }).execute()

    return ScheduleSlotResponse(**result.data[0])


@router.patch("/{slot_id}")
async def update_schedule_slot(
    slot_id: str,
    slot: ScheduleSlotCreate,
    current_user: CurrentUser = Depends(require_role("organizador", "admin")),
):
    db = get_supabase()
    result = db.table("schedule_slots").update(slot.model_dump()).eq("id", slot_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Slot no encontrado")

    return {"message": "Slot actualizado correctamente"}


@router.delete("/{slot_id}")
async def delete_schedule_slot(
    slot_id: str,
    current_user: CurrentUser = Depends(require_role("organizador", "admin")),
):
    db = get_supabase()
    result = db.table("schedule_slots").delete().eq("id", slot_id).execute()
    return {"message": "Slot eliminado correctamente"}