import structlog
from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Query, UploadFile, File, Depends
from pydantic import BaseModel, Field
from typing import Optional, List

from app.core.deps import require_role, CurrentUser, get_db, get_current_user
from app.core.constants import UserRole
from app.core.config import settings
from app.core.email import EmailMessage, get_email_sender
from app.api.v1.endpoints.storage import _ensure_bucket

logger = structlog.get_logger(__name__)
router = APIRouter()

TICKET_PRICE = 30000

class SorteoCreate(BaseModel):
    ticket_option: str = Field(default="1", pattern=r"^1$")
    full_name: str = Field(..., min_length=1)
    whatsapp: str = Field(..., min_length=1)
    email: str = Field(..., min_length=1)
    province: Optional[str] = None
    city: str = Field(..., min_length=1)
    comprobante_numero: Optional[str] = None

class SorteoResponse(BaseModel):
    id: str
    ticket_option: str
    full_name: str
    whatsapp: str
    email: str
    province: Optional[str] = None
    city: str
    comprobante_url: Optional[str] = None
    comprobante_numero: Optional[str] = None
    status: str
    created_at: str
    updated_at: str

class SorteoListResponse(BaseModel):
    data: List[SorteoResponse]
    total: int
    page: int
    page_size: int

@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_sorteo(payload: SorteoCreate, db=Depends(get_db)):
    try:
        row = {
            "ticket_option": payload.ticket_option,
            "full_name": payload.full_name,
            "whatsapp": payload.whatsapp,
            "email": payload.email,
            "province": payload.province,
            "city": payload.city,
            "comprobante_numero": payload.comprobante_numero,
            "status": "pendiente_validacion",
        }
        res = db.table("sorteo_avistaje").insert(row).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Error al guardar registro")
        return {"id": res.data[0]["id"], "message": "Registro exitoso"}
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error("sorteo_create_failed", error=error_msg)
        if "does not exist" in error_msg or "relation" in error_msg or "42P01" in error_msg:
            raise HTTPException(status_code=500, detail="Tabla no configurada. Contacte al administrador.")
        raise HTTPException(status_code=500, detail="Error al guardar registro. Intente nuevamente.")

@router.get("/unread-count")
async def sorteo_unread_count(
    db=Depends(get_db),
):
    result = db.table("sorteo_avistaje").select("id", count="exact").eq("status", "pendiente_validacion").execute()
    return {"unread": result.count or 0}

@router.get("/validados")
async def list_validados(
    db=Depends(get_db),
):
    result = (
        db.table("sorteo_avistaje")
        .select("id,full_name,city,province,status")
        .eq("status", "validado")
        .order("created_at", desc=True)
        .execute()
    )
    return {"data": result.data or []}

@router.get("/", response_model=SorteoListResponse)
async def list_sorteo(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    query = db.table("sorteo_avistaje").select("*", count="exact")

    if status_filter:
        query = query.eq("status", status_filter)
    if search:
        query = query.or_(f"full_name.ilike.%{search}%,email.ilike.%{search}%,whatsapp.ilike.%{search}%")

    offset = (page - 1) * page_size
    result = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()

    return SorteoListResponse(
        data=[SorteoResponse(**item) for item in result.data],
        total=result.count or 0,
        page=page,
        page_size=page_size,
    )

@router.patch("/{sorteo_id}/comprobante")
async def upload_comprobante(
    sorteo_id: str,
    file: UploadFile = File(...),
    db=Depends(get_db),
):
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="El archivo excede 10MB")

    allowed = {"image/jpeg", "image/png", "application/pdf"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Tipo de archivo no permitido. Use JPG, PNG o PDF.")

    content = await file.read()
    ext = file.filename.rsplit(".", 1)[-1] if "." in (file.filename or "") else "jpg"
    path = f"comprobantes/{sorteo_id}.{ext}"

    try:
        _ensure_bucket(db, "sorteo_avistaje")
    except Exception as e:
        logger.warning("sorteo_bucket_ensure_failed", error=str(e))

    try:
        db.storage.from_("sorteo_avistaje").upload(path, content, file_options={"content-type": file.content_type})
    except Exception as e:
        logger.error("sorteo_upload_failed", error=str(e), path=path, content_type=file.content_type, content_len=len(content))
        raise HTTPException(status_code=500, detail=f"Error subiendo comprobante: {str(e)}")

    public_url = db.storage.from_("sorteo_avistaje").get_public_url(path)

    db.table("sorteo_avistaje").update({"comprobante_url": public_url}).eq("id", sorteo_id).execute()

    return {"url": public_url, "message": "Comprobante subido correctamente"}


def _send_sorteo_confirmation_email(row: dict):
    """Send confirmation email to the participant when their deposit is validated."""
    try:
        email_sender = get_email_sender()
        full_name = row.get("full_name", "")
        email = row.get("email", "")
        ticket_num = f"SBA-{row.get('id', '')[:8].upper()}"
        comprobante_num = row.get("comprobante_numero") or "-"
        city = row.get("city", "")
        province = row.get("province", "")
        created_at = row.get("created_at", "")

        date_str = ""
        if created_at:
            try:
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                date_str = dt.strftime("%d/%m/%Y")
            except Exception:
                date_str = created_at[:10] if len(created_at) >= 10 else ""
        if not date_str:
            date_str = datetime.now().strftime("%d/%m/%Y")

        logo_url = settings.LOGO_URL or "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0OCIgaGVpZ2h0PSI0OCIgdmlld0JveD0iMCAwIDQ4IDQ4Ij48cGF0aCBkPSJNMTggMThhOCA4IDAgMCAxIDAgMTMgOCA4IDAgMCAxIDEgMTMgOCA4IDAgMCAxIC0xIDExIiBmaWxsPSIjMzdiN2Y5IiBzdHJva2U9IiMzYjc3ZjkiIHN0cm9rZS13aWR0aD0iMiIvPjxwYXRoIGQ9Ik0xNSAyNWE1IDUgMCAwIDEgMTAgMCA1IDUgMCAwIDEgMTAgMCINIiBmaWxsPSIjMzdiN2Y5Ii8+PHBhdGggZD0iTTIgMTBoNDR2LTJIMnp2MXoiIGZpbGw9IiMzYjc3ZjkiLz48cGF0aCBkPSJNMjggMTdsLTEyIDgiIGZpbGw9Im5vbmUiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlPSIjMzdiN2Y5Ii8+PHRleHQgeD0iMjQiIHk9IjQyIiBmb250LWZhbWlseT0ic2Fucy1zZXJpZiIgbW9udGgtc2l6ZT0iMTQiIGZvbnQtc2l6ZT0iMjAiIGZpbGw9IiMzYjc3ZjkiIHRleHQtYW5jaG9yPSJtaWRkbGUiPlByZUNvc3F1aW48L3RleHQ+PC9zdmc+"

        html_body = f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Depósito Confirmado — Sorteo Avistaje de Ballenas y Snorkelling</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased;color:#0f172a">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9">
<tr><td align="center" style="padding:24px 16px">

<!-- Container -->
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)">

<!-- ==================== HEADER ==================== -->
<tr><td style="background:linear-gradient(135deg,#1e3a8a,#3b82f6);padding:28px 32px;text-align:center">
  <img src="{logo_url}" alt="Logo Pre Cosquín Puerto Pirámides" width="48" height="48" style="display:block;margin:0 auto 12px;border-radius:8px;background:#ffffff;padding:4px" />
  <div style="font-size:16px;font-weight:700;color:#ffffff;letter-spacing:0.02em">Pre-Cosquín Puerto Pirámides</div>
</td></tr>

<!-- ==================== SUCCESS BANNER ==================== -->
<tr><td style="padding:32px 32px 16;text-align:center">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#d1fae5;border:1px solid #6ee7b7;border-radius:12px">
  <tr>
    <td style="padding:24px 24px 16;text-align:center">
      <img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2MCIgaGVpZ2h0PSI2MCIgdmlld0JveD0iMCAwIDYwIDYwIiBmaWxsPSJub25lIj48Y2lyY2xlIGN4PSIzMCIgY3k9IjMwIiByPSIyOCIgc3Ryb2tlPSIjMTY2NTA0IiBzdHJva2Utd2lkdGg9IjIiIGZpbGw9IiNmMGZkZjQiLz48cGF0aCBkPSJNMTggMzBsNyA3IDE2LTE2IiBzdHJva2U9IiMxNjY1MDQiIHN0cm9rZS13aWR0aD0iMy41IiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz48L3N2Zz4=" alt="Confirmado" width="60" height="60" style="display:block;margin:0 auto;border-radius:50%%;background:#dbeafe" /><br/>
      <div style="font-size:20px;font-weight:700;color:#065f46;margin:12px 0 4px">¡Depósito Confirmado!</div>
      <div style="font-size:14px;color:#047857">Tu participación en el sorteo quedó confirmada. Mucha suerte 🐋</div>
    </td>
  </tr>
  </table>
</td></tr>

<!-- ==================== TICKET NUMBER ==================== -->
<tr><td style="padding:24px 32px 0">
  <div style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px">Tu Número de Participación</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:linear-gradient(135deg,#eff6ff,#f0fdfa);border:2px dashed #3b82f6;border-radius:12px">
  <tr><td style="padding:16px;text-align:center">
    <div style="font-size:8px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">Número de Sorteo</div>
    <div style="font-size:26px;font-weight:800;color:#06b6d4;font-family:'Courier New',monospace;margin-top:4px;letter-spacing:0.05em">{ticket_num}</div>
    <div style="font-size:10px;color:#94a3b8;margin-top:4px">Guardá este número. Es tu identificador en el sorteo</div>
  </td></tr>
  </table>
</td></tr>

<!-- ==================== PARTICIPANT SUMMARY ==================== -->
<tr><td style="padding:8px 32px 0">
  <div style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px">Datos del Participante</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid #e2e8f0;border-radius:10px">

  <!-- Nombre -->
  <tr><td style="padding:12px 16px 0">
    <div style="font-size:8px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">Nombre y Apellido</div>
    <div style="font-size:14px;font-weight:700;color:#0f172a;margin-top:2px">{full_name}</div>
  </td></tr>
  <!-- Email -->
  <tr><td style="padding:6px 16px 0">
    <div style="font-size:8px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">Email</div>
    <div style="font-size:14px;font-weight:500;color:#0f172a;margin-top:2px">{email}</div>
  </td></tr>
  <!-- WhatsApp -->
  <tr><td style="padding:6px 16px 0">
    <div style="font-size:8px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">WhatsApp</div>
    <div style="font-size:14px;font-weight:500;color:#0f172a;margin-top:2px">{row.get("whatsapp", "-")}</div>
  </td></tr>
  <!-- Ciudad / Provincia -->
  <tr><td style="padding:6px 16px 0">
    <div style="font-size:8px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">Ciudad / Provincia</div>
    <div style="font-size:14px;font-weight:500;color:#0f172a;margin-top:2px">{city}, {province}</div>
  </td></tr>
  <!-- Nro. Comprobante -->
  <tr><td style="padding:6px 16px 0">
    <div style="font-size:8px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">Nro. Comprobante</div>
    <div style="font-size:14px;font-weight:500;color:#0f172a;margin-top:2px;font-family:'Courier New',monospace">{comprobante_num}</div>
  </td></tr>
  <!-- Fecha -->
  <tr><td style="padding:6px 16px 0">
    <div style="font-size:8px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">Fecha de Registro</div>
    <div style="font-size:14px;font-weight:500;color:#0f172a;margin-top:2px">{date_str}</div>
  </td></tr>
  </table>
</td></tr>

<!-- ==================== INFO BOX ==================== -->
<tr><td style="padding:8px 32px 0">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fffbeb;border:1px solid #fde68a;border-radius:10px">
  <tr><td style="padding:14px 16px">
    <div style="font-size:8px;font-weight:700;color:#92400e;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:4px">¿Qué sigue?</div>
    <div style="font-size:13px;color:#78350f;line-height:1.6">
      El día del sorteo, el ganador se anunciará en vivo por nuestro canal de
      <a href="https://www.youtube.com/@PreCosquinPuertoPirámides" style="color:#dc2626;font-weight:700;text-decoration:underline">YouTube: @PreCosquinPuertoPirámides</a>.
      Asegurate de seguirnos y verificar tu número de participación.
    </div>
  </td></tr>
  </table>
</td></tr>

<!-- ==================== FOOTER ==================== -->
<tr><td style="padding:24px 32px;text-align:center;border-top:1px solid #e2e8f0">
  <div style="font-size:9px;color:#94a3b8;line-height:1.6">
    Pre-Cosquín Puerto Pirámides — Sorteo Avistaje de Ballenas y Snorkelling<br/>
    Si tenés dudas comunicate con la organización a través de nuestros canales oficiales.
  </div>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>'''

        text_body = f'''¡Depósito Confirmado! — Sorteo Avistaje de Ballenas y Snorkelling

Hola {full_name},

Tu participación en el sorteo fue confirmada exitosamente.

Tu número de participación: {ticket_num}
Comprobante de transferencia: {comprobante_num}

El día del sorteo, el ganador se anunciará en vivo por YouTube:
@PreCosquinPuertoPirámides

Pre-Cosquín Puerto Pirámides'''

        msg = EmailMessage(
            to=email,
            subject="✅ Depósito Confirmado — Sorteo Avistaje de Ballenas y Snorkelling",
            html=html_body,
            text=text_body,
            reply_to="admin@precosquin.com",
        )
        result = email_sender.send(msg)
        logger.info("sorteo_confirmation_email_sent", to=email, ticket=ticket_num, status=result.status)
    except Exception as e:
        logger.error("sorteo_confirmation_email_failed", email=row.get("email"), error=str(e))


@router.patch("/{sorteo_id}/status")
async def update_sorteo_status(
    sorteo_id: str,
    new_status: str = Query(..., alias="status"),
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    if new_status not in ("pendiente_validacion", "validado", "rechazado"):
        raise HTTPException(status_code=400, detail="Estado inválido")

    # Fetch current row to get participant data before updating
    current = db.table("sorteo_avistaje").select("*").eq("id", sorteo_id).single().execute()
    row = current.data if current.data else None

    db.table("sorteo_avistaje").update({"status": new_status}).eq("id", sorteo_id).execute()

    # Send confirmation email when transitioning to 'validado'
    if new_status == "validado" and row:
        _send_sorteo_confirmation_email(row)

    return {"message": "Estado actualizado"}

@router.delete("/{sorteo_id}")
async def delete_sorteo(
    sorteo_id: str,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    db.table("sorteo_avistaje").delete().eq("id", sorteo_id).execute()
    return {"message": "Participante eliminado"}