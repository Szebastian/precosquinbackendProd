from fastapi import APIRouter, Depends
from typing import Optional, List
from pydantic import BaseModel, EmailStr
import structlog

from app.core.deps import get_current_user, require_role, CurrentUser
from app.core.email import EmailSender, EmailMessage, get_email_sender
from app.db.session import get_supabase

logger = structlog.get_logger()
router = APIRouter()


# ─── Pydantic models ─────────────────────────────────────────────

class EmailRecipient(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    status: Optional[str] = None


class SendImmediateRequest(BaseModel):
    recipients: List[EmailRecipient]
    subject: str
    body: str
    template: Optional[str] = None
    logo_url: Optional[str] = None


class ScheduleRequest(BaseModel):
    recipients: List[EmailRecipient]
    subject: str
    body: str
    template: Optional[str] = None
    scheduled_at: Optional[str] = None
    logo_url: Optional[str] = None


# ─── Endpoints ────────────────────────────────────────────────────

@router.post("/send")
async def send_email(
    req: SendImmediateRequest,
    email_sender: EmailSender = Depends(get_email_sender),
    current_user: CurrentUser = Depends(require_role("organizador", "admin", "staff")),
):
    """
    Send immediate emails to a list of recipients via configured email provider.
    Replaces {nombre}, {categoria}, {subcategoria}, {estado}, {email} per recipient.
    """
    messages = []
    for r in req.recipients:
        body = req.body
        subject = req.subject
        for var, val in [
            ("{nombre}", r.name or ""),
            ("{categoria}", r.category or ""),
            ("{subcategoria}", r.subcategory or ""),
            ("{estado}", r.status or ""),
            ("{email}", r.email or ""),
        ]:
            body = body.replace(var, val)
            subject = subject.replace(var, val)
        messages.append(EmailMessage(to=r.email, subject=subject, html=body, logo_url=req.logo_url))

    results = email_sender.send_bulk(messages)

    sent = sum(1 for r in results if r.status == "sent")
    failed = sum(1 for r in results if r.status != "sent")

    return {"message": f"Enviados: {sent}, Fallidos: {failed}", "sent": sent, "failed": failed}


@router.post("/schedule")
async def schedule_email(
    req: ScheduleRequest,
    current_user: CurrentUser = Depends(require_role("organizador", "admin", "staff")),
):
    """
    Schedule an email for later delivery. Stores in email_jobs table.
    """
    db = get_supabase()

    job_data = {
        "organization_id": current_user.org_id or "",
        "created_by": current_user.id,
        "subject": req.subject,
        "body": req.body,
        "template": req.template,
        "recipients": [r.model_dump() for r in req.recipients],
        "status": "scheduled",
        "sent": 0,
        "failed": 0,
    }

    if req.scheduled_at:
        job_data["scheduled_at"] = req.scheduled_at

    result = db.table("email_jobs").insert(job_data).execute()

    return {
        "message": "Email programado correctamente",
        "job_id": result.data[0]["id"],
    }


@router.get("/jobs")
async def list_jobs(
    current_user: CurrentUser = Depends(require_role("organizador", "admin", "staff")),
):
    """
    List all email jobs (sent, scheduled, failed).
    """
    db = get_supabase()
    result = (
        db.table("email_jobs")
        .select("*")
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return {"data": result.data}
