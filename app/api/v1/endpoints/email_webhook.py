import email as email_lib
import json
import structlog
from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import re

from app.core.deps import get_db

logger = structlog.get_logger(__name__)

router = APIRouter()


def _extract_email_address(raw_email_str: str) -> str:
    if not raw_email_str:
        return ""
    match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", raw_email_str)
    return match.group(0) if match else raw_email_str


def _strip_html(html: str) -> str:
    if not html:
        return ""
    clean = re.sub(r"<[^>]+>", "", html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _parse_raw_mime(raw_mime: str) -> dict:
    result = {"subject": "", "text": "", "html": ""}
    try:
        parsed = email_lib.message_from_string(raw_mime)
        result["subject"] = parsed.get("Subject", "") or ""
        if parsed.is_multipart():
            for part in parsed.walk():
                ct = part.get_content_type()
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                if isinstance(payload, bytes):
                    payload = payload.decode(charset, errors="replace")
                if ct == "text/plain" and not result["text"]:
                    result["text"] = payload or ""
                elif ct == "text/html" and not result["html"]:
                    result["html"] = payload or ""
        else:
            payload = parsed.get_payload(decode=True)
            charset = parsed.get_content_charset() or "utf-8"
            if isinstance(payload, bytes):
                payload = payload.decode(charset, errors="replace")
            ct = parsed.get_content_type()
            if ct == "text/html":
                result["html"] = payload or ""
            else:
                result["text"] = payload or ""
    except Exception as e:
        logger.error("mime_parse_error", error=str(e))
    return result


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
            body = json.loads(raw)
        except Exception:
            body = {}

    from_raw = body.get("from") or body.get("sender") or body.get("from_email") or ""
    raw_mime = body.get("raw") or ""
    subject = body.get("subject") or ""
    text = body.get("text") or ""
    html = body.get("html") or ""

    if raw_mime and not text and not html:
        parsed = _parse_raw_mime(raw_mime)
        subject = subject or parsed["subject"]
        text = text or parsed["text"]
        html = html or parsed["html"]

    email_from = _extract_email_address(str(from_raw))
    message_text = text or _strip_html(html) if html else ""

    if not email_from:
        logger.warning("incoming_email_no_sender", from_raw=from_raw)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Missing sender address"},
        )

    if len(message_text) > 5000:
        message_text = message_text[:5000]

    insert_data = {
        "name": email_from.split("@")[0].replace(".", " ").replace("_", " ").title(),
        "email": email_from,
        "phone": None,
        "subject": str(subject) or "(Sin asunto)",
        "message": message_text or "(Sin contenido)",
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