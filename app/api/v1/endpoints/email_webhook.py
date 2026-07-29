import structlog
from fastapi import APIRouter, Request, HTTPException, status, Depends
from pydantic import BaseModel
from typing import Optional
import re

from app.core.deps import get_db

logger = structlog.get_logger(__name__)

router = APIRouter()


class EmailWebhookPayload(BaseModel):
    from_email: Optional[str] = None
    sender: Optional[str] = None
    to: Optional[str] = None
    subject: Optional[str] = None
    text: Optional[str] = None
    html: Optional[str] = None
    body: Optional[str] = None
    date: Optional[str] = None
    attachments: Optional[list] = None


def _extract_email_address(raw: str) -> str:
    if not raw:
        return ""
    match = re.search(r'[\w.+-]+@[\w-]+\.[\w.]+', raw)
    return match.group(0) if match else raw


def _strip_html(html: str) -> str:
    if not html:
        return ""
    clean = re.sub(r'<[^>]+>', '', html)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


@router.post("/incoming")
async def receive_incoming_email(request: Request, db=Depends(get_db)):
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        body = await request.json()
    elif "multipart/form-data" in content_type:
        form = await request.form()
        body = dict(form)
    else:
        raw = await request.body()
        try:
            import json
            body = json.loads(raw)
        except Exception:
            body = {}

    from_raw = body.get("from") or body.get("sender") or body.get("from_email") or ""
    to_raw = body.get("to") or ""
    subject = body.get("subject") or "(Sin asunto)"
    text = body.get("text") or body.get("body") or ""
    html = body.get("html") or ""
    date = body.get("date") or ""

    email_from = _extract_email_address(str(from_raw))

    message_text = text or _strip_html(html) if html else ""

    if not email_from:
        logger.warning("incoming_email_no_sender", body=body)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing sender address",
        )

    insert_data = {
        "name": email_from.split("@")[0].replace(".", " ").replace("_", " ").title(),
        "email": email_from,
        "phone": None,
        "subject": str(subject),
        "message": message_text[:5000] if message_text else "(Sin contenido)",
        "inscription_id": None,
        "source": "email",
    }

    try:
        result = db.table("messages").insert(insert_data).execute()
    except Exception as e:
        logger.error("incoming_email_db_error", error=str(e), from_email=email_from)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error saving email",
        )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error saving email",
        )

    logger.info("incoming_email_saved", from_email=email_from, subject=subject, id=result.data[0].get("id"))

    return {"status": "ok", "message_id": result.data[0].get("id")}
