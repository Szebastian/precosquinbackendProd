from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List
from pydantic import BaseModel

from app.core.deps import get_current_user, require_role, CurrentUser
from app.db.session import get_supabase

router = APIRouter()


class ChecklistTaskUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


class IncidentCreate(BaseModel):
    artist_id: str
    task_id: Optional[str] = None
    title: str
    description: str
    severity: str


@router.get("/checklist/{artist_id}")
async def get_artist_checklist(artist_id: str, current_user: CurrentUser = Depends(require_role("staff", "organizador", "admin"))):
    db = get_supabase()
    result = db.table("artist_checklist_tasks").select("*").eq("artist_id", artist_id).order("order_index").execute()
    return result.data


@router.patch("/checklist/tasks/{task_id}")
async def update_checklist_task(
    task_id: str,
    update: ChecklistTaskUpdate,
    current_user: CurrentUser = Depends(require_role("staff")),
):
    db = get_supabase()
    result = db.table("artist_checklist_tasks").update({
        "status": update.status,
        "completed_by": current_user.id if update.status == "completed" else None,
        "completed_at": "now()" if update.status == "completed" else None,
    }).eq("id", task_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    return {"message": "Tarea actualizada correctamente"}


@router.post("/incidents", status_code=201)
async def create_incident(
    incident: IncidentCreate,
    current_user: CurrentUser = Depends(require_role("staff")),
):
    db = get_supabase()
    result = db.table("incidents").insert({
        **incident.model_dump(),
        "reported_by": current_user.id,
        "status": "open",
    }).execute()

    return {"id": result.data[0]["id"], "message": "Incidencia creada correctamente"}


@router.get("/incidents")
async def list_incidents(current_user: CurrentUser = Depends(require_role("staff", "organizador", "admin"))):
    db = get_supabase()
    result = db.table("incidents").select("*").order("created_at", desc=True).execute()
    return result.data


@router.patch("/incidents/{incident_id}/status")
async def update_incident_status(
    incident_id: str,
    status: str,
    current_user: CurrentUser = Depends(require_role("staff", "organizador", "admin")),
):
    db = get_supabase()
    result = db.table("incidents").update({
        "status": status,
        "resolved_by": current_user.id if status == "resolved" else None,
        "resolved_at": "now()" if status == "resolved" else None,
    }).eq("id", incident_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Incidencia no encontrada")

    return {"message": "Incidencia actualizada correctamente"}


@router.get("/contacts")
async def list_staff_contacts(current_user: CurrentUser = Depends(require_role("staff"))):
    db = get_supabase()
    result = db.table("staff_artist_contacts").select("*").execute()
    return result.data