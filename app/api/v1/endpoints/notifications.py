from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List
from pydantic import BaseModel

from app.core.deps import get_current_user, require_role, CurrentUser
from app.db.session import get_supabase

router = APIRouter()


class NotificationSend(BaseModel):
    artist_id: str
    channel: str
    template_id: Optional[str] = None
    subject: Optional[str] = None
    body: str


class NotificationBulkSend(BaseModel):
    artist_ids: List[str]
    channel: str
    template_id: Optional[str] = None
    subject: Optional[str] = None
    body: str


class TemplateCreate(BaseModel):
    name: str
    channel: str
    subject: Optional[str] = None
    body: str
    variables: List[str] = []


@router.post("/send", status_code=201)
async def send_notification(
    notification: NotificationSend,
    current_user: CurrentUser = Depends(require_role("organizador", "admin", "staff")),
):
    db = get_supabase()

    result = db.table("communications_log").insert({
        "artist_id": notification.artist_id,
        "sender_id": current_user.id,
        "channel": notification.channel,
        "template_id": notification.template_id,
        "subject": notification.subject,
        "body": notification.body,
        "status": "PENDING",
    }).execute()

    return {"id": result.data[0]["id"], "message": "Notificación encolada"}


@router.post("/send-bulk")
async def send_bulk_notifications(
    notification: NotificationBulkSend,
    current_user: CurrentUser = Depends(require_role("organizador", "admin")),
):
    db = get_supabase()

    logs = []
    for artist_id in notification.artist_ids:
        result = db.table("communications_log").insert({
            "artist_id": artist_id,
            "sender_id": current_user.id,
            "channel": notification.channel,
            "template_id": notification.template_id,
            "subject": notification.subject,
            "body": notification.body,
            "status": "PENDING",
        }).execute()
        logs.append(result.data[0]["id"])

    return {"message": f"{len(logs)} notificaciones encoladas", "log_ids": logs}


@router.get("/logs")
async def list_notification_logs(
    channel: Optional[str] = None,
    status: Optional[str] = None,
    current_user: CurrentUser = Depends(require_role("organizador", "admin", "staff")),
):
    db = get_supabase()
    query = db.table("communications_log").select("*")

    if channel:
        query = query.eq("channel", channel)
    if status:
        query = query.eq("status", status)

    result = query.order("created_at", desc=True).execute()
    return result.data


@router.get("/templates")
async def list_templates(current_user: CurrentUser = Depends(get_current_user)):
    db = get_supabase()
    result = db.table("communication_templates").select("*").eq("status", "ACTIVE").execute()
    return result.data


@router.post("/templates", status_code=201)
async def create_template(
    template: TemplateCreate,
    current_user: CurrentUser = Depends(require_role("organizador", "admin")),
):
    db = get_supabase()
    result = db.table("communication_templates").insert({
        **template.model_dump(),
        "status": "DRAFT",
        "created_by": current_user.id,
    }).execute()

    return {"id": result.data[0]["id"], "message": "Plantilla creada correctamente"}