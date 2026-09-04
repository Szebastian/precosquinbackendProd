from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, List
from pydantic import BaseModel

from app.core.deps import get_current_user, require_role, CurrentUser, get_db
from app.core.constants import UserRole
from app.core.utils import exclude_none
from app.db.supabase_http import supabase_insert, supabase_select, supabase_update, supabase_delete

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


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    variables: Optional[List[str]] = []


class EmailListCreate(BaseModel):
    name: str
    emails: list
    source: str = "manual"


@router.post("/send", status_code=201)
async def send_notification(
    notification: NotificationSend,
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN, UserRole.STAFF)),
    db=Depends(get_db),
):
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
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN)),
    db=Depends(get_db),
):
    insert_payloads = [
        {
            "artist_id": artist_id,
            "sender_id": current_user.id,
            "channel": notification.channel,
            "template_id": notification.template_id,
            "subject": notification.subject,
            "body": notification.body,
            "status": "PENDING",
        }
        for artist_id in notification.artist_ids
    ]
    result = db.table("communications_log").insert(insert_payloads).execute()
    logs = [item["id"] for item in result.data]

    return {"message": f"{len(logs)} notificaciones encoladas", "log_ids": logs}


@router.get("/logs")
async def list_notification_logs(
    channel: Optional[str] = None,
    status: Optional[str] = None,
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN, UserRole.STAFF)),
    db=Depends(get_db),
):
    query = db.table("communications_log").select("*")

    if channel:
        query = query.eq("channel", channel)
    if status:
        query = query.eq("status", status)

    result = query.order("created_at", desc=True).execute()
    return result.data


@router.get("/templates")
async def list_templates(current_user: CurrentUser = Depends(get_current_user)):
    data = supabase_select("communication_templates", filters={"status": "eq.ACTIVE"})
    return data


@router.post("/templates", status_code=201)
async def create_template(
    template: TemplateCreate,
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN)),
):
    payload = {
        **template.model_dump(),
        "status": "ACTIVE",
        "created_by": current_user.id,
    }
    data = supabase_insert("communication_templates", payload)
    return {"id": data[0]["id"], "message": "Plantilla creada correctamente"}


@router.put("/templates/{template_id}")
async def update_template(
    template_id: str,
    template: TemplateUpdate,
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN)),
):
    update_data = exclude_none(template)
    data = supabase_update("communication_templates", update_data, {"id": f"eq.{template_id}"})
    if not data:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    return {"message": "Plantilla actualizada"}


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN)),
):
    data = supabase_update("communication_templates", {"status": "DELETED"}, {"id": f"eq.{template_id}"})
    if not data:
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")
    return {"message": "Plantilla eliminada"}


@router.get("/email-lists")
async def list_email_lists(current_user: CurrentUser = Depends(get_current_user)):
    try:
        filters = {}
        if current_user.org_id:
            filters["organization_id"] = f"eq.{current_user.org_id}"
        data = supabase_select("email_lists", filters=filters or None, order="created_at.desc")
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/email-lists", status_code=201)
async def create_email_list(
    body: EmailListCreate,
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN, UserRole.STAFF)),
):
    try:
        payload = {
            "organization_id": current_user.org_id or "",
            "name": body.name,
            "emails": body.emails,
            "source": body.source,
            "created_by": current_user.id,
        }
        data = supabase_insert("email_lists", payload)
        return data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/email-lists/{list_id}")
async def update_email_list(
    list_id: str,
    body: EmailListCreate,
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN, UserRole.STAFF)),
):
    try:
        data = supabase_update(
            "email_lists",
            {"name": body.name, "emails": body.emails},
            {"id": f"eq.{list_id}"},
        )
        if not data:
            raise HTTPException(status_code=404, detail="Lista no encontrada")
        return data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/email-lists/{list_id}")
async def delete_email_list(
    list_id: str,
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN, UserRole.STAFF)),
):
    try:
        supabase_delete("email_lists", {"id": f"eq.{list_id}"})
        return {"message": "Lista eliminada"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
