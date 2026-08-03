import structlog
from fastapi import APIRouter, HTTPException, status, Query, Depends, UploadFile, File, Response
from pydantic import BaseModel, EmailStr
from typing import Optional, List

from app.core.deps import get_current_user, require_role, CurrentUser, get_db
from app.core.constants import InscriptionStatus, UserRole
from app.core.utils import exclude_none
from app.core.email import EmailMessage, EmailAttachment, get_email_sender

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
    qr_code_base64: Optional[str] = None


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

    qr_b64 = None
    try:
        from app.core.qr import generate_inscription_qr
        qr_b64 = generate_inscription_qr(
            inscription_id=created.get("id", ""),
            full_name=created.get("full_name", ""),
            stage_name=created.get("stage_name"),
            dni=created.get("dni"),
            category=created.get("category", ""),
            subcategory=created.get("subcategory", ""),
            status=created.get("status", ""),
        )
        created["qr_code_base64"] = qr_b64
    except Exception as e:
        logger.error("qr_generation_failed", inscription_id=created.get("id"), error=str(e))

    try:
        _send_confirmation_email(inscription, created, qr_b64)
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


@router.get("/{inscription_id}/qr-image")
async def get_qr_image(inscription_id: str, db=Depends(get_db)):
    """Public endpoint: serves the QR code PNG image for an inscription."""
    try:
        result = db.table("inscriptions").select("id, full_name, stage_name, dni, category, subcategory, status").eq("id", inscription_id).execute()
    except Exception as e:
        logger.error("db_error", error=str(e))
        raise HTTPException(status_code=500, detail="Error al buscar inscripción")

    if not result.data:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada")

    ins = result.data[0]

    try:
        from app.core.qr import generate_inscription_qr
        import base64 as b64
        qr_b64 = generate_inscription_qr(
            inscription_id=ins.get("id", ""),
            full_name=ins.get("full_name", ""),
            stage_name=ins.get("stage_name"),
            dni=ins.get("dni"),
            category=ins.get("category", ""),
            subcategory=ins.get("subcategory", ""),
            status=ins.get("status", ""),
        )
        qr_bytes = b64.b64decode(qr_b64)
        return Response(content=qr_bytes, media_type="image/png", headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Disposition": f'inline; filename="qr-{inscription_id[:8]}.png"',
        })
    except Exception as e:
        logger.error("qr_generation_error", error=str(e), inscription_id=inscription_id)
        raise HTTPException(status_code=500, detail="Error al generar QR")


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


@router.delete("/{inscription_id}", status_code=status.HTTP_200_OK)
async def delete_inscription(
    inscription_id: str,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    try:
        result = db.table("inscriptions").select("id, full_name").eq("id", inscription_id).execute()
    except Exception as e:
        logger.error("Error fetching inscription for deletion", inscription_id=inscription_id, error=str(e), user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener la inscripción: {str(e)}",
        )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inscripción no encontrada",
        )

    participant_name = result.data[0].get("full_name", "desconocido")

    try:
        del_result = db.table("inscriptions").delete().eq("id", inscription_id).execute()
        verify = db.table("inscriptions").select("id").eq("id", inscription_id).execute()
        if verify.data:
            logger.error("DELETE_FAILED_STILL_EXISTS", inscription_id=inscription_id, user_id=current_user.id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="La inscripción no pudo ser eliminada. Verifique los permisos de la tabla en Supabase.",
            )
        logger.info("inscription_deleted", inscription_id=inscription_id, participant_name=participant_name, user_id=current_user.id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting inscription", inscription_id=inscription_id, error=str(e), user_id=current_user.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar la inscripción: {str(e)}",
        )

    logger.info("Inscription deleted", inscription_id=inscription_id, participant_name=participant_name, user_id=current_user.id)

    return {"message": f"Inscripción de {participant_name} eliminada correctamente"}


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

    if new_status in ("EN_REVISION", "APROBADA", "RECHAZADA"):
        try:
            full_data = db.table("inscriptions").select("*").eq("id", inscription_id).single().execute()
            if full_data.data:
                _send_status_change_email(full_data.data, new_status, reason)
        except Exception as e:
            logger.error("status_change_email_failed", inscription_id=inscription_id, error=str(e))

    logger.info("Inscription status updated successfully", inscription_id=inscription_id, from_status=from_status, to_status=new_status, user_id=current_user.id)
    return {"message": f"Inscripción actualizada a {new_status}"}


class BulkDeleteRequest(BaseModel):
    ids: List[str]


@router.post("/bulk-delete", status_code=status.HTTP_200_OK)
async def bulk_delete_inscriptions(
    req: BulkDeleteRequest,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    if not req.ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se proporcionaron IDs")

    try:
        result = db.table("inscriptions").select("id, full_name").in_("id", req.ids).execute()
    except Exception as e:
        logger.error("Error fetching inscriptions for bulk delete", ids=req.ids, error=str(e), user_id=current_user.id)
        raise HTTPException(status_code=500, detail=f"Error al obtener inscripciones: {str(e)}")

    found_ids = [r["id"] for r in (result.data or [])]
    not_found = [i for i in req.ids if i not in found_ids]

    if not found_ids:
        raise HTTPException(status_code=404, detail="Ninguna inscripción encontrada")

    try:
        db.table("inscriptions").delete().in_("id", found_ids).execute()
    except Exception as e:
        logger.error("Error bulk deleting inscriptions", ids=found_ids, error=str(e), user_id=current_user.id)
        raise HTTPException(status_code=500, detail=f"Error al eliminar inscripciones: {str(e)}")

    logger.info("Bulk delete inscriptions", count=len(found_ids), user_id=current_user.id)

    return {"message": f"{len(found_ids)} inscripción(es) eliminada(s)", "deleted": len(found_ids), "not_found": not_found}


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


def _send_confirmation_email(inscription: InscriptionCreate, created: dict, qr_b64: str | None = None):
    name = inscription.full_name or inscription.first_name or inscription.email
    email = inscription.email
    category = inscription.category or ""
    subcategory = inscription.subcategory or ""
    inscription_id = created.get("id", "")
    created_at = created.get("created_at", "")

    cat_label = "Música" if category == "musica" else "Danza" if category == "danza" else category
    subcat_label = subcategory.replace("_", " ").replace("-", " ").title() if subcategory else "-"

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

    qr_section = ''
    qr_attachment = None
    if qr_b64:
        import base64 as _b64
        qr_bytes = _b64.b64decode(qr_b64)
        qr_attachment = EmailAttachment(
            content_id="qr-precosquin-2027",
            filename="qr-acreditacion.png",
            content=qr_bytes,
            content_type="image/png",
        )
        qr_section = (
            '<!-- QR CODE -->\n'
            '<tr><td style="padding:20px 32px 0;text-align:center">\n'
            '  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px">\n'
            '  <tr>\n'
            '    <td style="padding:20px 16px;text-align:center">\n'
            '      <div style="font-size:9px;font-weight:700;color:#2563eb;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px">C&#243;digo QR para Acreditaci&#243;n</div>\n'
            '      <img src="cid:qr-precosquin-2027" alt="QR Acreditaci&#243;n" width="160" height="160" style="display:block;margin:0 auto;border-radius:8px;border:2px solid #e2e8f0" />\n'
            '      <div style="font-size:10px;color:#64748b;margin-top:10px;line-height:1.4">Present&#225; este c&#243;digo QR en la acreditaci&#243;n del<br/>Festival Pre-Cosqu&#237;n 2027 &#183; Puerto Pir&#225;mides</div>\n'
            '    </td>\n'
            '  </tr>\n'
            '  </table>\n'
            '</td></tr>\n\n'
        )

    def td_label(label: str) -> str:
        return f'<td style="padding:4px 8px 4px 0;font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;font-weight:700;white-space:nowrap;vertical-align:top">{label}</td>'

    def td_value(value: str) -> str:
        return f'<td style="padding:4px 0;font-size:12px;color:#0f172a;font-weight:500;vertical-align:top">{value or "-"}</td>'

    def td_cell(value: str, bg: bool = False) -> str:
        style = "padding:6px 10px;font-size:12px;color:#0f172a;font-weight:500;vertical-align:top"
        if bg:
            style += ";background:#f8fafc"
        return f'<td style="{style}">{value or "-"}</td>'

    def td_label_cell(label: str, bg: bool = False) -> str:
        style = "padding:6px 10px;font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;font-weight:700;vertical-align:top"
        if bg:
            style += ";background:#f8fafc"
        return f'<td style="{style}">{label}</td>'

    html_body = f'''<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9">
<tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="580" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)">

<!-- HEADER -->
<tr><td style="background:linear-gradient(135deg,#1e3a8a,#3b82f6);padding:28px 32px;text-align:center">
  <div style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:0.02em">Festival Pre-Cosquín 2027</div>
  <div style="font-size:11px;color:rgba(255,255,255,0.7);margin-top:4px">Puerto Pirámides, Chubut</div>
</td></tr>

<!-- TITLE + DATE -->
<tr><td style="padding:24px 32px 0;text-align:center">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td style="font-size:17px;font-weight:700;color:#1e3a8a;text-align:center">Constancia de Inscripción</td>
  </tr>
  <tr>
    <td style="font-size:11px;color:#94a3b8;text-align:center;padding-top:4px">Fecha de registro: {date_str}</td>
  </tr>
  </table>
</td></tr>

<!-- INSCRIPTION ID -->
<tr><td style="padding:20px 32px 0">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px">
  <tr>
    <td style="padding:12px 16px;text-align:center">
      <div style="font-size:8px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">N° de Inscripción</div>
      <div style="font-size:13px;font-weight:700;color:#2563eb;font-family:'Courier New',monospace;margin-top:3px;word-break:break-all">{inscription_id}</div>
    </td>
  </tr>
  </table>
</td></tr>

{qr_section}
<!-- DIVIDER -->
<tr><td style="padding:20px 32px 0"><div style="border-top:1px solid #e2e8f0"></div></td></tr>

<!-- DATOS PERSONALES -->
<tr><td style="padding:16px 32px 0">
  <div style="font-size:9px;font-weight:700;color:#2563eb;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px">Datos Personales</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
  <tr>{td_label("Nombre")}{td_value(full)}</tr>
  </table>
</td></tr>

<tr><td style="padding:8px 32px 0">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
  <tr>
    {td_label_cell("DNI")}
    {td_cell(dni, True)}
    {td_label_cell("Nacimiento")}
    {td_cell(birth)}
    {td_label_cell("Edad")}
    {td_cell(age + " años" if age != "-" else "-", True)}
  </tr>
  </table>
</td></tr>

<tr><td style="padding:8px 32px 0">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
  <tr>
    {td_label_cell("Domicilio")}
    {td_cell(address, True)}
    {td_label_cell("Localidad")}
    {td_cell(locality)}
    {td_label_cell("Provincia")}
    {td_cell(province, True)}
  </tr>
  </table>
</td></tr>

<tr><td style="padding:8px 32px 0">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
  <tr>
    {td_label_cell("Teléfono")}
    {td_cell(phone, True)}
    {td_label_cell("Email")}
    <td colspan="2" style="padding:6px 10px;font-size:12px;color:#0f172a;font-weight:500;vertical-align:top;word-break:break-all">{email}</td>
  </tr>
  </table>
</td></tr>

<!-- DIVIDER -->
<tr><td style="padding:20px 32px 0"><div style="border-top:1px solid #e2e8f0"></div></td></tr>

<!-- PARTICIPACIÓN -->
<tr><td style="padding:16px 32px 0">
  <div style="font-size:9px;font-weight:700;color:#2563eb;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px">Participación</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
  <tr>
    {td_label_cell("Categoría")}
    <td style="padding:6px 10px;font-size:13px;color:#1e3a8a;font-weight:700;vertical-align:top">{cat_label}</td>
    {td_label_cell("Subcategoría")}
    <td style="padding:6px 10px;font-size:13px;color:#1e3a8a;font-weight:700;vertical-align:top">{subcat_label}</td>
  </tr>
  </table>
</td></tr>

<!-- STATUS -->
<tr><td style="padding:20px 32px 0">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px">
  <tr>
    <td style="padding:14px 16px;text-align:center">
      <div style="font-size:13px;font-weight:700;color:#166534">Estado: PENDIENTE</div>
      <div style="font-size:11px;color:#15803d;margin-top:4px">Nuestro equipo revisará tu inscripción y te contactaremos pronto.</div>
    </td>
  </tr>
  </table>
</td></tr>

<!-- NOTE -->
<tr><td style="padding:12px 32px 0">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fffbeb;border:1px solid #fde68a;border-radius:10px">
  <tr>
    <td style="padding:12px 16px">
      <div style="font-size:11px;color:#92400e;line-height:1.5">Conservá este correo como comprobante de tu registro.</div>
    </td>
  </tr>
  </table>
</td></tr>

<!-- FOOTER -->
<tr><td style="padding:24px 32px 28px;text-align:center">
  <div style="font-size:11px;color:#94a3b8;line-height:1.6">Si tenés consultas, respondé a este correo o escribinos a <a href="mailto:info@precosquin.com" style="color:#2563eb;text-decoration:none">info@precosquin.com</a></div>
  <div style="font-size:10px;color:#cbd5e1;margin-top:6px">Precosquin — Festival Provincial de Folklore · Puerto Pirámides, Chubut</div>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>'''

    email_sender = get_email_sender()
    msg = EmailMessage(
        to=email,
        subject="Pre-Cosquín — Constancia de Inscripción",
        html=html_body,
        reply_to="info@precosquin.com",
        attachments=[qr_attachment] if qr_attachment else None,
    )
    result = email_sender.send(msg)
    logger.info("confirmation_email_sent", to=email, status=result.status, message_id=result.message_id)


def _send_status_change_email(inscription_data: dict, new_status: str, reason: Optional[str] = None):
    email = inscription_data.get("email", "")
    full_name = inscription_data.get("full_name", "")
    inscription_id = inscription_data.get("id", "")
    category = inscription_data.get("category", "")
    subcategory = inscription_data.get("subcategory", "")

    cat_label = "Música" if category == "musica" else "Danza" if category == "danza" else category
    subcat_label = subcategory.replace("_", " ").replace("-", " ").title() if subcategory else "-"

    status_config = {
        "EN_REVISION": {
            "subject": "Pre-Cosquín — Tu inscripción está en revisión",
            "title": "Tu inscripción está siendo revisada",
            "message": "Nuestro equipo está evaluando tu inscripción. Te avisaremos cuando tengamos un resultado.",
            "bg_color": "#eff6ff",
            "border_color": "#bfdbfe",
            "title_color": "#1e40af",
            "msg_color": "#1e3a8a",
            "icon": '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>',
        },
        "APROBADA": {
            "subject": "Pre-Cosquín — ¡Tu inscripción fue aprobada!",
            "title": "¡Tu inscripción fue aprobada!",
            "message": "Felicitaciones, tu inscripción al Festival Pre-Cosquín 2027 fue aprobada. Pronto nos contactaremos con los próximos pasos.",
            "bg_color": "#f0fdf4",
            "border_color": "#bbf7d0",
            "title_color": "#166534",
            "msg_color": "#15803d",
            "icon": '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>',
        },
        "RECHAZADA": {
            "subject": "Pre-Cosquín — Resultado de tu inscripción",
            "title": "Resultado de tu inscripción",
            "message": "Lamentamos informarte que tu inscripción no fue aprobada en esta edición del festival.",
            "bg_color": "#fef2f2",
            "border_color": "#fecaca",
            "title_color": "#991b1b",
            "msg_color": "#b91c1c",
            "icon": '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg>',
        },
    }

    config = status_config.get(new_status)
    if not config:
        return

    reason_html = ""
    if reason and new_status == "RECHAZADA":
        reason_html = f'''
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:16px;background:#fffbeb;border:1px solid #fde68a;border-radius:10px">
        <tr>
          <td style="padding:14px 16px">
            <div style="font-size:9px;color:#92400e;text-transform:uppercase;letter-spacing:0.1em;font-weight:700;margin-bottom:6px">Motivo del rechazo</div>
            <div style="font-size:12px;color:#78350f;line-height:1.5">{reason}</div>
          </td>
        </tr>
        </table>'''

    html_body = f'''<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9">
<tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="580" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)">

<!-- HEADER -->
<tr><td style="background:linear-gradient(135deg,#1e3a8a,#3b82f6);padding:28px 32px;text-align:center">
  <div style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:0.02em">Festival Pre-Cosquín 2027</div>
  <div style="font-size:11px;color:rgba(255,255,255,0.7);margin-top:4px">Puerto Pirámides, Chubut</div>
</td></tr>

<!-- ICON + TITLE -->
<tr><td style="padding:32px 32px 0;text-align:center">
  <div style="margin-bottom:16px">{config["icon"]}</div>
  <div style="font-size:18px;font-weight:700;color:{config["title_color"]};margin-bottom:8px">{config["title"]}</div>
  <div style="font-size:13px;color:{config["msg_color"]};line-height:1.6;max-width:420px;margin:0 auto">{config["message"]}</div>
</td></tr>

<!-- STATUS CARD -->
<tr><td style="padding:24px 32px 0">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{config["bg_color"]};border:1px solid {config["border_color"]};border-radius:10px">
  <tr>
    <td style="padding:16px;text-align:center">
      <div style="font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700;margin-bottom:4px">N° de Inscripción</div>
      <div style="font-size:13px;font-weight:700;color:#2563eb;font-family:'Courier New',monospace;word-break:break-all">{inscription_id}</div>
      <div style="border-top:1px solid {config["border_color"]};margin:12px 0"></div>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td style="padding:4px 0;font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;font-weight:700;width:100px">Nombre</td>
        <td style="padding:4px 0;font-size:12px;color:#0f172a;font-weight:500">{full_name}</td>
      </tr>
      <tr>
        <td style="padding:4px 0;font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;font-weight:700">Categoría</td>
        <td style="padding:4px 0;font-size:12px;color:#0f172a;font-weight:500">{cat_label} › {subcat_label}</td>
      </tr>
      </table>
    </td>
  </tr>
  </table>
</td></tr>

{reason_html}

<!-- NOTE -->
<tr><td style="padding:20px 32px 0">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px">
  <tr>
    <td style="padding:14px 16px">
      <div style="font-size:11px;color:#475569;line-height:1.5">Si tenés consultas, respondé a este correo o escribinos a <a href="mailto:info@precosquin.com" style="color:#2563eb;text-decoration:none">info@precosquin.com</a></div>
    </td>
  </tr>
  </table>
</td></tr>

<!-- FOOTER -->
<tr><td style="padding:24px 32px 28px;text-align:center">
  <div style="font-size:10px;color:#cbd5e1">Precosquin — Festival Provincial de Folklore · Puerto Pirámides, Chubut</div>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>'''

    email_sender = get_email_sender()
    msg = EmailMessage(
        to=email,
        subject=config["subject"],
        html=html_body,
        reply_to="info@precosquin.com",
    )
    result = email_sender.send(msg)
    logger.info("status_change_email_sent", to=email, new_status=new_status, status=result.status, message_id=result.message_id)