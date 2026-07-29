import structlog
from fastapi import APIRouter, HTTPException, status, Query, Depends, UploadFile, File
from pydantic import BaseModel, EmailStr
from typing import Optional, List

from app.core.deps import get_current_user, require_role, CurrentUser, get_db
from app.core.constants import InscriptionStatus, UserRole
from app.core.utils import exclude_none
from app.core.email import EmailMessage, get_email_sender

logger = structlog.get_logger(__name__)

router = APIRouter()


class InscriptionCreate(BaseModel):
    email: EmailStr
    phone: str
    category: str
    subcategory: str
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    stage_name: Optional[str] = None
    dni: Optional[str] = None
    birth_date: Optional[str] = None
    age: Optional[int] = None
    address: Optional[str] = None
    locality: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    experience_years: Optional[int] = None
    bio: Optional[str] = None
    technical_needs: Optional[str] = None
    proposal_name: Optional[str] = None
    choreographer_name: Optional[str] = None
    style: Optional[str] = None
    dance_list: Optional[str] = None
    themes: Optional[list] = None
    members: Optional[list] = None
    accompanying_persons: Optional[list] = None
    rider_tecnico: Optional[dict] = None
    website: Optional[str] = None
    instagram: Optional[str] = None
    youtube: Optional[str] = None
    spotify: Optional[str] = None
    dance_style: Optional[str] = None
    dance_themes: Optional[list] = None
    work_title: Optional[str] = None
    assistants_count: Optional[int] = None
    band_members: Optional[list] = None
    accept_no_prior_win: Optional[bool] = None
    accept_not_juror_org: Optional[bool] = None
    accept_regulations: Optional[bool] = None
    instrument_type: Optional[str] = None
    instrument_name: Optional[str] = None
    has_accompaniment: Optional[bool] = None
    accompaniment_instrument: Optional[str] = None
    accompaniment_musician: Optional[str] = None
    accept_purely_instrumental: Optional[bool] = None
    accept_one_instrument: Optional[bool] = None
    accept_no_prerecorded: Optional[bool] = None
    accept_no_instrument_change: Optional[bool] = None
    presentation: Optional[str] = None
    artistic_name: Optional[str] = None
    songs_list: Optional[str] = None


class InscriptionResponse(BaseModel):
    id: str
    email: str
    phone: str
    category: str
    subcategory: str
    full_name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    stage_name: Optional[str] = None
    status: str
    created_at: str
    updated_at: str
    dni: Optional[str] = None
    birth_date: Optional[str] = None
    age: Optional[int] = None
    address: Optional[str] = None
    locality: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    bio: Optional[str] = None
    technical_needs: Optional[str] = None
    proposal_name: Optional[str] = None
    choreographer_name: Optional[str] = None
    style: Optional[str] = None
    dance_list: Optional[str] = None
    themes: Optional[list] = None
    members: Optional[list] = None
    accompanying_persons: Optional[list] = None
    rider_tecnico: Optional[dict] = None
    website: Optional[str] = None
    instagram: Optional[str] = None
    youtube: Optional[str] = None
    spotify: Optional[str] = None
    dance_style: Optional[str] = None
    dance_themes: Optional[list] = None
    work_title: Optional[str] = None
    assistants_count: Optional[int] = None
    band_members: Optional[list] = None
    accept_no_prior_win: Optional[bool] = None
    accept_not_juror_org: Optional[bool] = None
    accept_regulations: Optional[bool] = None
    instrument_type: Optional[str] = None
    instrument_name: Optional[str] = None
    has_accompaniment: Optional[bool] = None
    accompaniment_instrument: Optional[str] = None
    accompaniment_musician: Optional[str] = None
    accept_purely_instrumental: Optional[bool] = None
    accept_one_instrument: Optional[bool] = None
    accept_no_prerecorded: Optional[bool] = None
    accept_no_instrument_change: Optional[bool] = None
    presentation: Optional[str] = None
    artistic_name: Optional[str] = None
    songs_list: Optional[str] = None


class InscriptionListResponse(BaseModel):
    data: List[InscriptionResponse]
    total: int
    page: int
    page_size: int


@router.get("/", response_model=InscriptionListResponse)
async def list_inscriptions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN, UserRole.STAFF, UserRole.JURADO)),
    db=Depends(get_db),
):
    query = db.table("inscriptions").select("*", count="exact")

    if category:
        query = query.eq("category", category)
    if subcategory:
        query = query.eq("subcategory", subcategory)
    if status_filter:
        query = query.eq("status", status_filter)

    offset = (page - 1) * page_size
    result = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()

    return InscriptionListResponse(
        data=[InscriptionResponse(**item) for item in result.data],
        total=result.count or 0,
        page=page,
        page_size=page_size,
    )


@router.post("/", response_model=InscriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_inscription(inscription: InscriptionCreate, db=Depends(get_db)):
    if not inscription.full_name and inscription.first_name and inscription.last_name:
        inscription.full_name = f"{inscription.first_name} {inscription.last_name}"
    elif inscription.first_name and not inscription.full_name:
        inscription.full_name = inscription.first_name
    elif inscription.last_name and not inscription.full_name:
        inscription.full_name = inscription.last_name
    try:
        existing = db.table("inscriptions").select("id").eq("email", inscription.email).eq("status", InscriptionStatus.PENDIENTE).execute()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error consultando inscripciones: {str(e)}",
        )
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una inscripción pendiente con este email",
        )

    insert_data = exclude_none(inscription)
    insert_data["status"] = InscriptionStatus.PENDIENTE.value
    allowed_columns = {
        "email", "phone", "category", "subcategory", "full_name", "first_name", "last_name", "stage_name",
        "dni", "birth_date", "age", "address", "locality", "province", "city",
        "experience_years", "bio", "technical_needs", "proposal_name",
        "choreographer_name", "style", "dance_list", "themes", "members",
        "accompanying_persons", "rider_tecnico", "website", "instagram",
        "youtube", "spotify", "dance_style", "dance_themes", "work_title",
        "assistants_count", "band_members", "accept_no_prior_win",
        "accept_not_juror_org", "accept_regulations", "instrument_type", "instrument_name",
        "has_accompaniment", "accompaniment_instrument", "accompaniment_musician",
        "accept_purely_instrumental", "accept_one_instrument", "accept_no_prerecorded",
        "accept_no_instrument_change", "presentation", "artistic_name", "songs_list",
    }
    insert_data = {k: v for k, v in insert_data.items() if k in allowed_columns}

    try:
        result = db.table("inscriptions").insert(insert_data).execute()
    except Exception as e:
        detail_msg = str(e)
        if '422' in detail_msg or 'column' in detail_msg.lower() or 'schema' in detail_msg.lower():
            detail_msg = f"Error de esquema en la base de datos. Verificá que todas las columnas existan: {detail_msg}"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al crear inscripción en base de datos: {detail_msg}",
        )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear inscripción",
        )

    created = result.data[0]

    try:
        _send_confirmation_email(inscription, created)
    except Exception as e:
        logger.error("confirmation_email_failed", inscription_id=created.get("id"), error=str(e))

    return InscriptionResponse(**created)


@router.get("/check-email")
async def check_email_exists(email: str = Query(...), db=Depends(get_db)):
    try:
        result = db.table("inscriptions").select("id").eq("email", email).eq("status", InscriptionStatus.PENDIENTE).execute()
        return {"exists": bool(result.data)}
    except Exception as e:
        logger.error("Error checking email", error=str(e), email=email)
        return {"exists": False}


@router.get("/{inscription_id}", response_model=InscriptionResponse)
async def get_inscription(
    inscription_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    result = db.table("inscriptions").select("*").eq("id", inscription_id).single().execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inscripción no encontrada",
        )

    return InscriptionResponse(**result.data)


@router.patch("/{inscription_id}/status")
async def update_inscription_status(
    inscription_id: str,
    new_status: str,
    reason: Optional[str] = None,
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN, UserRole.JURADO)),
    db=Depends(get_db),
):
    valid_statuses = [s.value for s in InscriptionStatus]
    if new_status not in valid_statuses:
        logger.warning("Invalid status update attempt", inscription_id=inscription_id, new_status=new_status, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Estado inválido. Debe ser uno de: {', '.join(valid_statuses)}",
        )

    try:
        existing = db.table("inscriptions").select("id, status").eq("id", inscription_id).execute()
    except Exception as e:
        logger.error("Error fetching inscription for status update", inscription_id=inscription_id, error=str(e), user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener la inscripción: {str(e)}",
        )

    if not existing.data:
        logger.warning("Inscription not found for status update", inscription_id=inscription_id, user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inscripción no encontrada",
        )

    from_status = existing.data[0].get("status")

    update_data = {
        "status": new_status,
    }

    if reason:
        update_data["rejection_reason"] = reason

    try:
        result = db.table("inscriptions").update(update_data).eq("id", inscription_id).execute()
    except Exception as e:
        logger.error("Error updating inscription status", inscription_id=inscription_id, new_status=new_status, error=str(e), user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar el estado de la inscripción: {str(e)}",
        )

    logger.info("Inscription update result", inscription_id=inscription_id, result_data=result.data if hasattr(result, 'data') else "no data attr")

    try:
        db.table("inscription_audit").insert({
            "inscription_id": inscription_id,
            "action": f"status_changed_to_{new_status}",
            "from_status": from_status,
            "to_status": new_status,
            "reason": reason,
        }).execute()
    except Exception as e:
        logger.warning("Audit log failed (non-blocking)", inscription_id=inscription_id, error=str(e))

    logger.info("Inscription status updated successfully", inscription_id=inscription_id, from_status=from_status, to_status=new_status, user_id=current_user.id)
    return {"message": f"Inscripción actualizada a {new_status}"}


@router.post("/upload/{inscription_id}")
async def upload_inscription_file(
    inscription_id: str,
    file_type: str = Query(..., description="dni_front, dni_back, promo_photo, lyrics, score"),
    file: UploadFile = File(...),
    db=Depends(get_db),
):
    try:
        existing = db.table("inscriptions").select("id").eq("id", inscription_id).single().execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="Inscripción no encontrada")
    except Exception as e:
        logger.error("Error checking inscription existence", error=str(e), inscription_id=inscription_id)
        raise HTTPException(status_code=500, detail=f"Error al consultar inscripción: {str(e)}")

    allowed_types = {
        "dni_front": ["image/jpeg", "image/png"],
        "dni_back": ["image/jpeg", "image/png"],
        "promo_photo": ["image/jpeg", "image/png"],
        "lyrics": ["application/pdf", "text/plain", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
        "score": ["application/pdf", "image/jpeg", "image/png"],
    }

    if file_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Tipo de archivo inválido: {file_type}")

    if file.content_type not in allowed_types[file_type]:
        raise HTTPException(status_code=400, detail=f"Tipo de archivo no permitido para {file_type}: {file.content_type}")

    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
    path = f"inscriptions/{inscription_id}/{file_type}.{ext}"

    try:
        content = await file.read()
        logger.info("Read file content successfully", size_bytes=len(content), file_type=file_type, filename=file.filename)
    except Exception as e:
        logger.error("Error reading uploaded file", error=str(e), file_type=file_type, filename=file.filename)
        raise HTTPException(status_code=500, detail=f"Error al leer el archivo: {str(e)}")

    try:
        logger.info("Attempting to upload to Supabase Storage", path=path, content_type=file.content_type)
        db.storage.from_("inscriptions").upload(
            path,
            content,
            file_options={"content-type": file.content_type},
        )
        logger.info("File uploaded successfully", path=path)
    except Exception as e:
        logger.error("Error uploading file to Supabase Storage", error=str(e), path=path, file_type=file_type)
        raise HTTPException(status_code=500, detail=f"Error al subir archivo: {str(e)}")

    column_map = {
        "dni_front": "dni_front_url",
        "dni_back": "dni_back_url",
        "promo_photo": "promo_photo_url",
        "lyrics": "lyrics_url",
        "score": "score_url",
    }

    try:
        logger.info("Updating inscriptions table", inscription_id=inscription_id, column=column_map[file_type], path=path)
        db.table("inscriptions").update({column_map[file_type]: path}).eq("id", inscription_id).execute()
        logger.info("Database update successful")
    except Exception as e:
        logger.error("Error updating inscription record with file path", error=str(e), inscription_id=inscription_id, column=column_map[file_type])
        raise HTTPException(status_code=500, detail=f"Error al actualizar la inscripción: {str(e)}")

    return {"path": path, "message": "Archivo subido correctamente"}


def _send_confirmation_email(inscription: InscriptionCreate, created: dict):
    name = inscription.full_name or inscription.first_name or inscription.email
    email = inscription.email
    category = inscription.category or ""
    subcategory = inscription.subcategory or ""
    inscription_id = created.get("id", "")
    created_at = created.get("created_at", "")

    cat_label = "Música" if category == "musica" else "Danza" if category == "danza" else category

    date_str = ""
    if created_at:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            date_str = dt.strftime("%d/%m/%Y")
        except Exception:
            date_str = created_at[:10] if len(created_at) >= 10 else ""
    if not date_str:
        from datetime import datetime
        date_str = datetime.now().strftime("%d/%m/%Y")

    def f(label: str, value: str) -> str:
        return f'''<div style="margin-bottom:8px"><span style="font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:0.05em">{label}</span><br><span style="font-size:12px;color:#0f172a;font-weight:500">{value or '-'}</span></div>'''

    first = inscription.first_name or ""
    last = inscription.last_name or ""
    full = f"{first} {last}".strip() or name
    dni = inscription.dni or ""
    birth = inscription.birth_date or ""
    age = str(inscription.age) if inscription.age else "-"
    address = inscription.address or ""
    locality = inscription.locality or ""
    province = inscription.province or ""
    phone = inscription.phone or ""

    html_body = f'''<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:Arial,Helvetica,sans-serif;">
<div style="max-width:600px;margin:0 auto;padding:32px 24px;">
<div style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.06);">
<div style="background:linear-gradient(135deg,#1e3a8a,#4c8be6);height:6px;"></div>
<div style="padding:32px;">
  <div style="text-align:center;margin-bottom:24px;">
    <div style="font-size:20px;font-weight:800;color:#0f172a;">Festival Pre-Cosquín 2027</div>
    <div style="font-size:11px;color:#64748b;margin-top:4px;">Puerto Pirámides, Chubut</div>
  </div>
  <div style="text-align:center;margin-bottom:24px;">
    <div style="font-size:16px;font-weight:700;color:#1e3a8a;">Constancia de Inscripción</div>
    <div style="font-size:11px;color:#64748b;margin-top:4px;">Fecha: {date_str}</div>
  </div>
  <div style="background:#f1f5f9;border-radius:8px;padding:12px 16px;margin-bottom:24px;text-align:center;">
    <div style="font-size:9px;color:#64748b;text-transform:uppercase">N° de Inscripción</div>
    <div style="font-size:14px;font-weight:700;color:#2563eb;font-family:'Courier New',monospace;margin-top:2px">{inscription_id}</div>
  </div>
  <hr style="border:none;border-top:1px solid #e2e8f0;margin:16px 0">
  <div style="font-size:10px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:12px">Datos Personales</div>
  {f('Nombre Completo', full)}
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">
    {f('DNI', dni)}{f('Nacimiento', birth)}{f('Edad', age + ' años' if age != '-' else '-')}
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px">
    {f('Domicilio', address)}{f('Localidad', locality)}{f('Provincia', province)}
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
    {f('Teléfono', phone)}{f('Email', email)}
  </div>
  <hr style="border:none;border-top:1px solid #e2e8f0;margin:16px 0">
  <div style="font-size:10px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:12px">Participación</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
    {f('Categoría', cat_label)}{f('Subcategoría', subcategory)}
  </div>
  <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:14px 16px;margin-top:20px;text-align:center;">
    <p style="margin:0;font-size:13px;color:#166534;"><strong>Estado: PENDIENTE</strong></p>
    <p style="margin:6px 0 0;font-size:12px;color:#15803d;">Nuestro equipo revisará tu inscripción y te contactaremos pronto.</p>
  </div>
  <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;padding:14px 16px;margin-top:12px;">
    <p style="margin:0;font-size:12px;color:#92400e;">Conservá este correo como comprobante de tu registro.</p>
  </div>
</div>
</div>
<div style="text-align:center;padding:16px 0;">
  <p style="margin:0;font-size:11px;color:#9ca3af;">Si tenés consultas, respondé a este correo o escribinos a <a href="mailto:info@precosquin.com" style="color:#4c8be6;">info@precosquin.com</a></p>
  <p style="margin:4px 0 0;font-size:10px;color:#cbd5e1;">Precosquin - Festival Provincial de Folklore · Puerto Pirámides, Chubut</p>
</div>
</div>
</body>
</html>'''

    email_sender = get_email_sender()
    msg = EmailMessage(
        to=email,
        subject="Pre-Cosquín - Constancia de Inscripción",
        html=html_body,
        reply_to="info@precosquin.com",
    )
    result = email_sender.send(msg)
    logger.info("confirmation_email_sent", to=email, status=result.status, message_id=result.message_id)