import structlog
from fastapi import APIRouter, HTTPException, status, Query, Depends
from pydantic import BaseModel, EmailStr
from typing import Optional, List

from app.core.deps import get_current_user, require_role, CurrentUser, get_db
from app.core.constants import UserRole
from app.core.email import EmailMessage, get_email_sender

logger = structlog.get_logger(__name__)

router = APIRouter()


class MessageCreate(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    subject: str
    message: str
    inscription_id: Optional[str] = None


class MessageResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: Optional[str] = None
    subject: str
    message: str
    inscription_id: Optional[str] = None
    is_read: bool
    created_at: str
    source: Optional[str] = "web"


class MessageListResponse(BaseModel):
    data: List[MessageResponse]
    total: int
    unread: int


@router.post("/", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message(msg: MessageCreate, db=Depends(get_db)):
    insert_data = {
        "name": msg.name,
        "email": msg.email,
        "phone": msg.phone,
        "subject": msg.subject,
        "message": msg.message,
        "inscription_id": msg.inscription_id,
    }

    try:
        result = db.table("messages").insert(insert_data).execute()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al enviar el mensaje: {str(e)}",
        )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al enviar el mensaje",
        )

    created = result.data[0]

    try:
        _send_message_to_admin(msg)
    except Exception as e:
        logger.error("admin_notification_email_failed", error=str(e))

    return MessageResponse(**created)


@router.get("/", response_model=MessageListResponse)
async def list_messages(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = False,
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN, UserRole.STAFF)),
    db=Depends(get_db),
):
    query = db.table("messages").select("*")

    if unread_only:
        query = query.eq("is_read", False)

    offset = (page - 1) * page_size
    result = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()

    count_query = db.table("messages").select("id", count="exact")
    if unread_only:
        count_query = count_query.eq("is_read", False)
    count_result = count_query.execute()

    unread_result = db.table("messages").select("id", count="exact").eq("is_read", False).execute()

    return MessageListResponse(
        data=[MessageResponse(**item) for item in result.data],
        total=count_result.count if hasattr(count_result, 'count') else len(result.data),
        unread=unread_result.count if hasattr(unread_result, 'count') else 0,
    )


@router.patch("/{message_id}/read")
async def mark_message_read(
    message_id: str,
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN, UserRole.STAFF)),
    db=Depends(get_db),
):
    try:
        result = db.table("messages").update({"is_read": True}).eq("id", message_id).execute()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al marcar mensaje: {str(e)}",
        )

    return {"message": "Mensaje marcado como leído"}


@router.delete("/{message_id}")
async def delete_message(
    message_id: str,
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN)),
    db=Depends(get_db),
):
    try:
        db.table("messages").delete().eq("id", message_id).execute()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar mensaje: {str(e)}",
        )

    return {"message": "Mensaje eliminado"}


class MessageReply(BaseModel):
    to: str
    subject: str = ""
    body: str = ""


@router.post("/{message_id}/reply")
async def reply_to_message(
    message_id: str,
    reply: MessageReply,
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN, UserRole.STAFF)),
    db=Depends(get_db),
):
    try:
        sender = get_email_sender()
        html_reply = f'''<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"/></head>
<body style="margin:0;padding:24px;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;max-width:600px;margin:0 auto">
<tr><td style="padding:24px 32px">
<div style="font-size:16px;font-weight:700;color:#1e3a8a;margin-bottom:16px">Respuesta de Precosquin</div>
<div style="font-size:14px;color:#1e293b;line-height:1.7;white-space:pre-wrap">{reply.body}</div>
<div style="margin-top:24px;padding-top:16px;border-top:1px solid #e2e8f0;font-size:12px;color:#94a3b8">
Este mensaje fue enviado desde el panel de administración de Precosquin.
</div>
</td></tr>
</table>
</body>
</html>'''
        email_msg = EmailMessage(
            to=reply.to,
            subject=reply.subject or f"Re: {reply.subject}",
            html=html_reply,
            reply_to="admin@precosquinpiramides.com",
        )
        result = sender.send(email_msg)
    except Exception as e:
        logger.error("reply_email_failed", error=str(e), to=reply.to)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al enviar la respuesta: {str(e)}",
        )

    insert_data = {
        "name": "Admin",
        "email": "admin@precosquinpiramides.com",
        "phone": None,
        "subject": f"Re: {reply.subject}",
        "message": reply.body,
        "inscription_id": None,
        "source": "reply",
    }

    try:
        result_db = db.table("messages").insert(insert_data).execute()
    except Exception as e:
        logger.error("reply_save_error", error=str(e))

    return {"message": "Respuesta enviada", "email_status": result.status}


def _send_message_to_admin(msg: MessageCreate):
    html_body = f'''<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9">
<tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="580" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)">

<!-- HEADER -->
<tr><td style="background:linear-gradient(135deg,#1e3a8a,#3b82f6);padding:24px 32px;text-align:center">
  <div style="font-size:18px;font-weight:800;color:#ffffff">Nuevo mensaje de contacto</div>
  <div style="font-size:11px;color:rgba(255,255,255,0.7);margin-top:4px">Precosquin — Panel de administración</div>
</td></tr>

<!-- CONTENT -->
<tr><td style="padding:24px 32px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td style="padding:6px 0;font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;font-weight:700;width:100px;vertical-align:top">Nombre</td>
    <td style="padding:6px 0;font-size:13px;color:#0f172a;font-weight:500">{msg.name}</td>
  </tr>
  <tr>
    <td style="padding:6px 0;font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;font-weight:700;vertical-align:top">Email</td>
    <td style="padding:6px 0;font-size:13px;color:#0f172a;font-weight:500"><a href="mailto:{msg.email}" style="color:#2563eb;text-decoration:none">{msg.email}</a></td>
  </tr>
  {"<tr><td style='padding:6px 0;font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;font-weight:700;vertical-align:top'>Teléfono</td><td style='padding:6px 0;font-size:13px;color:#0f172a;font-weight:500'>" + msg.phone + "</td></tr>" if msg.phone else ""}
  <tr>
    <td style="padding:6px 0;font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;font-weight:700;vertical-align:top">Asunto</td>
    <td style="padding:6px 0;font-size:13px;color:#0f172a;font-weight:700">{msg.subject}</td>
  </tr>
  </table>

  <div style="border-top:1px solid #e2e8f0;margin:16px 0"></div>

  <div style="font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;font-weight:700;margin-bottom:8px">Mensaje</div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;font-size:13px;color:#1e293b;line-height:1.6;white-space:pre-wrap">{msg.message}</div>

  {f"<div style='margin-top:12px;font-size:11px;color:#64748b'>Inscripción asociada: <code style='background:#f1f5f9;padding:2px 6px;border-radius:4px;font-size:10px'>{msg.inscription_id}</code></div>" if msg.inscription_id else ""}
</td></tr>

<!-- FOOTER -->
<tr><td style="padding:16px 32px 24px;text-align:center">
  <div style="font-size:11px;color:#94a3b8">Respondé a este correo para comunicarte con {msg.name}</div>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>'''

    email_sender = get_email_sender()
    email_msg = EmailMessage(
        to="info@precosquin.com",
        subject=f"[Precosquin] {msg.subject}",
        html=html_body,
        reply_to=msg.email,
    )
    result = email_sender.send(email_msg)
    logger.info("admin_notification_sent", to="info@precosquin.com", from_email=msg.email, status=result.status)
