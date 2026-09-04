import email as email_lib
import json
import structlog
from fastapi import APIRouter, Request, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import re

from app.core.deps import get_db
from app.core.email import EmailMessage, get_email_sender

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

    try:
        _send_auto_reply(from_raw, email_from, subject, message_text)
    except Exception as e:
        logger.error("auto_reply_failed", error=str(e), from_email=email_from)

    return {"status": "ok", "message_id": result.data[0].get("id")}


def _send_auto_reply(from_raw: str, email_from: str, subject: str, message_text: str):
    if subject.lower().startswith("re:"):
        return

    auto_subject = f"Recibimos tu mensaje: {subject}"

    html_body = f'''<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/></head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc">
<tr><td align="center" style="padding:40px 16px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)">

<!-- HEADER -->
<tr><td style="background:linear-gradient(135deg,#1e3a8a,#3b82f6);padding:32px 32px;text-align:center">
  <div style="font-size:20px;font-weight:800;color:#ffffff">Precosquin</div>
  <div style="font-size:13px;color:rgba(255,255,255,0.7);margin-top:6px">Puerto Piramides — Panel de Administración</div>
</td></tr>

<!-- CONTENT -->
<tr><td style="padding:32px">
  <div style="font-size:16px;font-weight:700;color:#1e3a8a;margin-bottom:8px">¡Gracias por escribirnos!</div>
  <p style="font-size:14px;color:#475569;line-height:1.7;margin:0 0 20px">
    Hemos recibido tu mensaje y queremos informarte que nos pondremos en contacto a la brevedad posible.
    Agradecemos tu paciencia mientras revisamos tu consulta.
  </p>

  <div style="background:#f1f5f9;border:1px solid #e2e8f0;border-radius:10px;padding:16px 20px;margin-bottom:20px">
    <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;font-weight:700;margin-bottom:8px">Resumen de tu mensaje</div>
    <div style="font-size:13px;color:#0f172a;font-weight:600;margin-bottom:6px">{subject}</div>
    <div style="font-size:13px;color:#475569;line-height:1.6;white-space:pre-wrap">{message_text[:300]}{"..." if len(message_text) > 300 else ""}</div>
  </div>

  <div style="font-size:13px;color:#64748b;line-height:1.6">
    Si necesitás una respuesta urgente, podés escribirnos nuevamente o contactarnos por teléfono.
  </div>
</td></tr>

<!-- FOOTER -->
<tr><td style="padding:20px 32px 28px;text-align:center;background:#f8fafc">
  <div style="font-size:11px;color:#94a3b8;line-height:1.6">
    Este mensaje fue enviado automáticamente desde el sistema de mensajes de Precosquin Puerto Piramides.<br/>
    No es necesario responder a este correo.
  </div>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>'''

    email_sender = get_email_sender()
    email_msg = EmailMessage(
        to=email_from,
        subject=auto_subject,
        html=html_body,
        reply_to="info@precosquinpiramides.com",
    )
    result = email_sender.send(email_msg)
    logger.info("auto_reply_sent", to=email_from, subject=auto_subject, status=result.status)