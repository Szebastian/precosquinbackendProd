import structlog
import random
import time
from fastapi import APIRouter, HTTPException, status, Query, Depends, UploadFile, File, Response
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
    qr_code_base64: Optional[str] = None
    dni_front_url: Optional[str] = None
    dni_back_url: Optional[str] = None
    promo_photo_url: Optional[str] = None
    lyrics_url: Optional[str] = None
    score_url: Optional[str] = None


class InscriptionListResponse(BaseModel):
    data: List[InscriptionResponse]
    total: int
    page: int
    page_size: int


@router.get("/", response_model=InscriptionListResponse)
async def list_inscriptions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN, UserRole.STAFF, UserRole.JURADO, UserRole.SEDE)),
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

    items = [InscriptionResponse(**item) for item in result.data]
    if current_user.role == UserRole.SEDE:
        for item in items:
            item.rider_tecnico = None

    return InscriptionListResponse(
        data=items,
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


# ─── OTP Verification ───────────────────────────────────────────────────────

_otp_store: dict[str, dict] = {}  # email -> {code, expires_at}
_otp_last_send: dict[str, float] = {}  # email -> last_send_timestamp
OTP_SEND_COOLDOWN = 60  # seconds


class OtpSendRequest(BaseModel):
    email: EmailStr


class OtpVerifyRequest(BaseModel):
    email: EmailStr
    code: str


@router.post("/send-otp")
async def send_otp(req: OtpSendRequest, db=Depends(get_db)):
    last_send = _otp_last_send.get(req.email, 0)
    elapsed = time.time() - last_send
    if elapsed < OTP_SEND_COOLDOWN:
        remaining = int(OTP_SEND_COOLDOWN - elapsed)
        raise HTTPException(
            status_code=429,
            detail=f"Debés esperar {remaining} segundos antes de solicitar un nuevo código.",
        )

    code = f"{random.randint(0, 999999):06d}"
    _otp_store[req.email] = {"code": code, "expires_at": time.time() + 600}
    _otp_last_send[req.email] = time.time()

    try:
        sender = get_email_sender()
        msg = EmailMessage(
            to=req.email,
            subject="Pre-Cosquín — Código de verificación",
            html=f"""
            <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px;">
              <h2 style="color:#1e3a8a;">Código de verificación</h2>
              <p>Tu código de verificación es:</p>
              <div style="font-size:2.5rem;font-weight:700;letter-spacing:0.3em;color:#1e3a8a;text-align:center;padding:20px;background:#eff6ff;border-radius:12px;margin:20px 0;">{code}</div>
              <p style="color:#64748b;font-size:0.875rem;">Este código expira en 10 minutos. Si no solicitaste este código, podés ignorar este mensaje.</p>
            </div>
            """,
        )
        sender.send(msg)
    except Exception as e:
        logger.error("Failed to send OTP", error=str(e), email=req.email)

    return {"message": "Código enviado"}


@router.post("/verify-otp")
async def verify_otp(req: OtpVerifyRequest):
    stored = _otp_store.get(req.email)
    if not stored:
        raise HTTPException(status_code=400, detail="No se envió un código a este email. Solicitá uno nuevo.")
    if time.time() > stored["expires_at"]:
        _otp_store.pop(req.email, None)
        raise HTTPException(status_code=400, detail="El código expiró. Solicitá uno nuevo.")
    if stored["code"] != req.code:
        raise HTTPException(status_code=400, detail="Código incorrecto. Verificá e intentá de nuevo.")
    _otp_store.pop(req.email, None)
    return {"message": "Email verificado correctamente"}


@router.get("/check-email")
async def check_email_exists(email: str = Query(...), db=Depends(get_db)):
    try:
        result = db.table("inscriptions").select("id, status, full_name, category, subcategory, created_at").eq("email", email).order("created_at", desc=True).limit(1).execute()
        if not result.data:
            return {"exists": False}
        ins = result.data[0]
        return {
            "exists": True,
            "inscription_id": ins.get("id"),
            "status": ins.get("status"),
            "full_name": ins.get("full_name"),
            "category": ins.get("category"),
            "subcategory": ins.get("subcategory"),
            "created_at": ins.get("created_at"),
        }
    except Exception as e:
        logger.error("Error checking email", error=str(e), email=email)
        return {"exists": False}


@router.get("/check-dni")
async def check_dni_exists(dni: str = Query(...), db=Depends(get_db)):
    """Check if a DNI is already registered in the inscriptions table."""
    dni_clean = dni.replace(".", "").replace("-", "").strip()
    if not dni_clean:
        return {"exists": False}
    try:
        result = (
            db.table("inscriptions")
            .select("id, status, full_name, email, category, subcategory, created_at")
            .eq("dni", dni_clean)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not result.data:
            return {"exists": False}
        ins = result.data[0]
        return {
            "exists": True,
            "inscription_id": ins.get("id"),
            "status": ins.get("status"),
            "full_name": ins.get("full_name"),
            "email": ins.get("email"),
            "category": ins.get("category"),
            "subcategory": ins.get("subcategory"),
            "created_at": ins.get("created_at"),
        }
    except Exception as e:
        logger.error("Error checking dni", error=str(e), dni=dni_clean)
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
            "Cache-Control": "public, max-age=31536000, immutable",
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

    data = InscriptionResponse(**result.data)
    if current_user.role == UserRole.SEDE:
        data.rider_tecnico = None

    return data


class InscriptionUpdatePartial(BaseModel):
    """Partial update for inscriptions - all fields optional."""
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    stage_name: Optional[str] = None
    dni: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
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


@router.put("/{inscription_id}", response_model=InscriptionResponse)
async def update_inscription(
    inscription_id: str,
    payload: InscriptionUpdatePartial,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    existing = db.table("inscriptions").select("id").eq("id", inscription_id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada")

    if not payload.full_name and payload.first_name and payload.last_name:
        payload.full_name = f"{payload.first_name} {payload.last_name}"

    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}

    try:
        res = db.table("inscriptions").update(update_data).eq("id", inscription_id).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Error al actualizar inscripción")
        return InscriptionResponse(**res.data[0])
    except HTTPException:
        raise
    except Exception as e:
        logger.error("inscription_update_failed", error=str(e), inscription_id=inscription_id)
        raise HTTPException(status_code=500, detail=f"Error al actualizar inscripción: {str(e)}")


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

    # Delete from all child tables first to avoid FK violations
    child_tables = ["inscription_audit", "acreditaciones", "evaluations"]
    for table in child_tables:
        try:
            db.table(table).delete().eq("inscription_id", inscription_id).execute()
        except Exception as e:
            logger.warning("Child table delete skipped (non-blocking)", table=table, inscription_id=inscription_id, error=str(e), user_id=current_user.id)
    # documents uses artist_id (same value as inscription id)
    try:
        db.table("documents").delete().eq("artist_id", inscription_id).execute()
    except Exception as e:
        logger.warning("Child table delete skipped (non-blocking)", table="documents", inscription_id=inscription_id, error=str(e), user_id=current_user.id)

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
                if new_status == "APROBADA":
                    from app.core.qr import generate_inscription_qr
                    qr_b64 = generate_inscription_qr(
                        inscription_id=inscription_id,
                        full_name=full_data.data.get("full_name", ""),
                        stage_name=full_data.data.get("stage_name"),
                        dni=full_data.data.get("dni"),
                        category=full_data.data.get("category", ""),
                        subcategory=full_data.data.get("subcategory", ""),
                        status="APROBADA",
                    )
                    try:
                        db.table("inscriptions").update({"qr_code_base64": qr_b64}).eq("id", inscription_id).execute()
                    except Exception as e:
                        logger.warning("qr_store_failed", inscription_id=inscription_id, error=str(e))
                    _send_approval_email(full_data.data, qr_b64)
                else:
                    _send_status_change_email(full_data.data, new_status, reason)
        except Exception as e:
            logger.error("status_change_email_failed", inscription_id=inscription_id, error=str(e))

    logger.info("Inscription status updated successfully", inscription_id=inscription_id, from_status=from_status, to_status=new_status, user_id=current_user.id)
    return {"message": f"Inscripción actualizada a {new_status}"}


@router.post("/{inscription_id}/approve")
async def approve_inscription(
    inscription_id: str,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    """Approve an inscription: generate QR, store it, send approval email with QR attached."""
    from app.core.qr import generate_inscription_qr

    try:
        existing = db.table("inscriptions").select("*").eq("id", inscription_id).single().execute()
    except Exception as e:
        logger.error("Error fetching inscription for approval", inscription_id=inscription_id, error=str(e), user_id=current_user.id)
        raise HTTPException(status_code=500, detail=f"Error al obtener la inscripción: {str(e)}")

    if not existing.data:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada")

    ins = existing.data
    current_status = ins.get("status")
    if current_status not in ("PENDIENTE", "EN_REVISION"):
        raise HTTPException(
            status_code=400,
            detail=f"No se puede aprobar una inscripción con estado {current_status}. Debe estar PENDIENTE o EN_REVISION.",
        )

    qr_base64 = generate_inscription_qr(
        inscription_id=inscription_id,
        full_name=ins.get("full_name", ""),
        stage_name=ins.get("stage_name"),
        dni=ins.get("dni"),
        category=ins.get("category", ""),
        subcategory=ins.get("subcategory", ""),
        status="APROBADA",
    )

    try:
        db.table("inscriptions").update({
            "status": "APROBADA",
            "qr_code_base64": qr_base64,
        }).eq("id", inscription_id).execute()
    except Exception as e:
        logger.error("Error updating inscription to APROBADA", inscription_id=inscription_id, error=str(e), user_id=current_user.id)
        raise HTTPException(status_code=500, detail=f"Error al aprobar la inscripción: {str(e)}")

    try:
        db.table("inscription_audit").insert({
            "inscription_id": inscription_id,
            "action": "status_changed_to_APROBADA",
            "from_status": current_status,
            "to_status": "APROBADA",
        }).execute()
    except Exception as e:
        logger.warning("Audit log failed (non-blocking)", inscription_id=inscription_id, error=str(e))

    try:
        _send_approval_email(ins, qr_base64)
    except Exception as e:
        logger.error("approval_email_failed", inscription_id=inscription_id, error=str(e))

    logger.info("inscription_approved", inscription_id=inscription_id, user_id=current_user.id)
    return {"message": "Inscripción aprobada correctamente", "qr_code_base64": qr_base64}


@router.post("/{inscription_id}/reject")
async def reject_inscription(
    inscription_id: str,
    reason: Optional[str] = None,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    """Reject an inscription with optional reason."""
    try:
        existing = db.table("inscriptions").select("id, status, full_name, email").eq("id", inscription_id).single().execute()
    except Exception as e:
        logger.error("Error fetching inscription for rejection", inscription_id=inscription_id, error=str(e), user_id=current_user.id)
        raise HTTPException(status_code=500, detail=f"Error al obtener la inscripción: {str(e)}")

    if not existing.data:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada")

    ins = existing.data
    current_status = ins.get("status")
    if current_status in ("RECHAZADA", "APROBADA"):
        raise HTTPException(
            status_code=400,
            detail=f"No se puede rechazar una inscripción con estado {current_status}.",
        )

    update_data = {"status": "RECHAZADA"}
    if reason:
        update_data["rejection_reason"] = reason

    try:
        db.table("inscriptions").update(update_data).eq("id", inscription_id).execute()
    except Exception as e:
        logger.error("Error updating inscription to RECHAZADA", inscription_id=inscription_id, error=str(e), user_id=current_user.id)
        raise HTTPException(status_code=500, detail=f"Error al rechazar la inscripción: {str(e)}")

    try:
        db.table("inscription_audit").insert({
            "inscription_id": inscription_id,
            "action": "status_changed_to_RECHAZADA",
            "from_status": current_status,
            "to_status": "RECHAZADA",
            "reason": reason,
        }).execute()
    except Exception as e:
        logger.warning("Audit log failed (non-blocking)", inscription_id=inscription_id, error=str(e))

    try:
        full_data = db.table("inscriptions").select("*").eq("id", inscription_id).single().execute()
        if full_data.data:
            _send_status_change_email(full_data.data, "RECHAZADA", reason)
    except Exception as e:
        logger.error("rejection_email_failed", inscription_id=inscription_id, error=str(e))

    logger.info("inscription_rejected", inscription_id=inscription_id, user_id=current_user.id)
    return {"message": "Inscripción rechazada correctamente"}


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

    # Delete from all child tables first to avoid FK violations
    child_tables = ["inscription_audit", "acreditaciones", "evaluations"]
    for table in child_tables:
        try:
            db.table(table).delete().in_("inscription_id", found_ids).execute()
        except Exception as e:
            logger.warning("Child table delete skipped (non-blocking)", table=table, ids=found_ids, error=str(e), user_id=current_user.id)
    # documents uses artist_id (same value as inscription id)
    try:
        db.table("documents").delete().in_("artist_id", found_ids).execute()
    except Exception as e:
        logger.warning("Child table delete skipped (non-blocking)", table="documents", ids=found_ids, error=str(e), user_id=current_user.id)

    try:
        db.table("inscriptions").delete().in_("id", found_ids).execute()
    except Exception as e:
        error_detail = str(e)
        logger.error("Error bulk deleting inscriptions", ids=found_ids, error=error_detail, user_id=current_user.id)
        if "foreign key" in error_detail.lower() or "violates" in error_detail.lower():
            raise HTTPException(status_code=500, detail=f"Error de integridad referencial. Tabla hija bloquea la eliminación: {error_detail}")
        raise HTTPException(status_code=500, detail=f"Error al eliminar inscripciones: {error_detail}")

    logger.info("Bulk delete inscriptions", count=len(found_ids), user_id=current_user.id)

    return {"message": f"{len(found_ids)} inscripción(es) eliminada(s)", "deleted": len(found_ids), "not_found": not_found}


# ─── PUBLIC SELF-SERVICE ENDPOINTS ────────────────────────────────
# These endpoints allow participants to manage their own inscriptions
# after OTP verification (email-based authentication).


class InscriptionUpdatePublic(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    dni: Optional[str] = None
    birth_date: Optional[str] = None
    age: Optional[int] = None
    address: Optional[str] = None
    locality: Optional[str] = None
    province: Optional[str] = None
    stage_name: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    artistic_name: Optional[str] = None
    proposal_name: Optional[str] = None
    choreographer_name: Optional[str] = None
    style: Optional[str] = None
    dance_list: Optional[str] = None
    bio: Optional[str] = None
    presentation: Optional[str] = None
    songs_list: Optional[str] = None
    themes: Optional[list] = None
    members: Optional[list] = None
    accompanying_persons: Optional[list] = None
    rider_tecnico: Optional[dict] = None
    dance_style: Optional[str] = None
    dance_themes: Optional[list] = None
    work_title: Optional[str] = None
    assistants_count: Optional[int] = None
    band_members: Optional[list] = None
    instrument_type: Optional[str] = None
    instrument_name: Optional[str] = None
    has_accompaniment: Optional[bool] = None
    accompaniment_instrument: Optional[str] = None
    accompaniment_musician: Optional[str] = None
    technical_needs: Optional[str] = None


class CancelRequest(BaseModel):
    email: EmailStr


@router.put("/{inscription_id}/update-public")
async def update_inscription_public(
    inscription_id: str,
    data: InscriptionUpdatePublic,
    db=Depends(get_db),
):
    """Public endpoint: participant updates their own inscription after OTP verification."""
    try:
        existing = db.table("inscriptions").select("id, email, status").eq("id", inscription_id).single().execute()
    except Exception as e:
        logger.error("db_error", error=str(e), inscription_id=inscription_id)
        raise HTTPException(status_code=500, detail="Error al buscar inscripción")

    if not existing.data:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada")

    if existing.data["email"].lower() != data.email.lower():
        raise HTTPException(status_code=403, detail="El email no coincide con esta inscripción")

    update_fields = data.model_dump(exclude_unset=True, exclude={"email"})
    if not update_fields:
        raise HTTPException(status_code=400, detail="No se proporcionaron campos para actualizar")

    if "first_name" in update_fields or "last_name" in update_fields:
        fn = update_fields.get("first_name") or ""
        ln = update_fields.get("last_name") or ""
        if fn or ln:
            update_fields["full_name"] = f"{fn} {ln}".strip()

    update_fields["updated_at"] = "now()"

    try:
        db.table("inscriptions").update(update_fields).eq("id", inscription_id).execute()
    except Exception as e:
        logger.error("update_public_error", error=str(e), inscription_id=inscription_id)
        raise HTTPException(status_code=500, detail="Error al actualizar la inscripción")

    try:
        db.table("inscription_audit").insert({
            "inscription_id": inscription_id,
            "action": "participant_update",
            "from_status": existing.data["status"],
            "to_status": existing.data["status"],
        }).execute()
    except Exception as e:
        logger.warning("audit_log_failed", inscription_id=inscription_id, error=str(e))

    try:
        full_data = db.table("inscriptions").select("*").eq("id", inscription_id).single().execute()
        if full_data.data:
            _send_update_email(full_data.data)
    except Exception as e:
        logger.error("update_email_failed", inscription_id=inscription_id, error=str(e))

    logger.info("inscription_updated_public", inscription_id=inscription_id)
    return {"message": "Inscripción actualizada correctamente"}


@router.get("/{inscription_id}/get-public")
async def get_inscription_public(inscription_id: str, email: str = Query(...), db=Depends(get_db)):
    """Public endpoint: get full inscription data after OTP verification."""
    try:
        result = db.table("inscriptions").select("*").eq("id", inscription_id).single().execute()
    except Exception as e:
        logger.error("db_error", error=str(e))
        raise HTTPException(status_code=500, detail="Error al buscar inscripción")

    if not result.data:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada")

    if result.data["email"].lower() != email.lower():
        raise HTTPException(status_code=403, detail="El email no coincide con esta inscripción")

    return result.data


@router.post("/{inscription_id}/cancel")
async def cancel_inscription_public(
    inscription_id: str,
    data: CancelRequest,
    db=Depends(get_db),
):
    """Public endpoint: participant cancels their inscription after OTP verification."""
    try:
        existing = db.table("inscriptions").select("id, email, status, full_name").eq("id", inscription_id).single().execute()
    except Exception as e:
        logger.error("db_error", error=str(e), inscription_id=inscription_id)
        raise HTTPException(status_code=500, detail="Error al buscar inscripción")

    if not existing.data:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada")

    if existing.data["email"].lower() != data.email.lower():
        raise HTTPException(status_code=403, detail="El email no coincide con esta inscripción")

    from_status = existing.data.get("status")
    participant_name = existing.data.get("full_name", "")

    try:
        db.table("inscription_audit").delete().eq("inscription_id", inscription_id).execute()
        db.table("inscriptions").delete().eq("id", inscription_id).execute()
        verify = db.table("inscriptions").select("id").eq("id", inscription_id).execute()
        if verify.data:
            raise HTTPException(status_code=500, detail="No se pudo eliminar la inscripción")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("cancel_error", error=str(e), inscription_id=inscription_id)
        raise HTTPException(status_code=500, detail="Error al cancelar la inscripción")

    try:
        db.table("inscription_audit").insert({
            "inscription_id": inscription_id,
            "action": "participant_cancel",
            "from_status": from_status,
            "to_status": "CANCELADA",
        }).execute()
    except Exception as e:
        logger.warning("audit_log_failed", inscription_id=inscription_id, error=str(e))

    try:
        _send_cancel_email(data.email, participant_name)
    except Exception as e:
        logger.error("cancel_email_failed", inscription_id=inscription_id, error=str(e))

    logger.info("inscription_cancelled_public", inscription_id=inscription_id, participant_name=participant_name)
    return {"message": "Inscripción cancelada correctamente"}


@router.get("/{inscription_id}/constancia-html")
async def get_constancia_html(inscription_id: str, db=Depends(get_db)):
    """Public endpoint: returns constancia as printable HTML (browser prints as PDF)."""
    try:
        result = db.table("inscriptions").select("*").eq("id", inscription_id).single().execute()
    except Exception as e:
        logger.error("db_error", error=str(e))
        raise HTTPException(status_code=500, detail="Error al buscar inscripción")

    if not result.data:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada")

    ins = result.data
    full_name = ins.get("full_name", "")
    email = ins.get("email", "")
    category = ins.get("category", "")
    subcategory = ins.get("subcategory", "")
    status_val = ins.get("status", "")
    created = ins.get("created_at", "")
    dni = ins.get("dni", "")
    locality = ins.get("locality", "")
    province = ins.get("province", "")
    phone = ins.get("phone", "")
    birth_date = ins.get("birth_date", "")
    age = ins.get("age", "")
    address = ins.get("address", "")
    artistic_name = ins.get("artistic_name", "")
    proposal_name = ins.get("proposal_name", "")
    stage_name = ins.get("stage_name", "")
    bio = ins.get("bio", "")
    themes = ins.get("themes") or []
    members = ins.get("members") or []

    cat_label = "Música" if category == "musica" else "Danza" if category == "danza" else category
    subcat_label = subcategory.replace("_", " ").title() if subcategory else "-"
    display_name = artistic_name or proposal_name or stage_name or full_name

    from app.core.config import settings
    logo_url = "data:image/webp;base64,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"

    themes_html = ""
    if themes:
        themes_html = '<div style="margin-top:12px"><strong style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:0.05em">Temas</strong><ul style="margin:4px 0 0;padding-left:18px;font-size:11px;color:#334155">'
        for t in themes:
            if isinstance(t, dict):
                title = t.get("title", "")
                rhythm = t.get("rhythm", "")
                author = t.get("author", "")
                themes_html += f'<li>{title}'
                if rhythm:
                    themes_html += f' — {rhythm}'
                if author:
                    themes_html += f' ({author})'
                themes_html += '</li>'
            else:
                themes_html += f'<li>{t}</li>'
        themes_html += '</ul></div>'

    members_html = ""
    if members:
        members_html = '<div style="margin-top:12px"><strong style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:0.05em">Integrantes</strong><ul style="margin:4px 0 0;padding-left:18px;font-size:11px;color:#334155">'
        for m in members:
            if isinstance(m, dict):
                name = m.get("fullName", m.get("full_name", ""))
                role = m.get("role", "")
                members_html += f'<li>{name}'
                if role:
                    members_html += f' — {role}'
                members_html += '</li>'
            else:
                members_html += f'<li>{m}</li>'
        members_html += '</ul></div>'

    html = f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<title>Constancia de Inscripción — Pre-Cosquín 2027</title>
<style>
  @media print {{
    body {{ margin: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    .no-print {{ display: none !important; }}
    @page {{ size: A4; margin: 15mm; }}
  }}
  body {{ font-family: Arial, Helvetica, sans-serif; background: #f1f5f9; color: #1e293b; margin: 0; padding: 20px; }}
  .card {{ max-width: 600px; margin: 0 auto; background: #fff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }}
  .header {{ background: linear-gradient(135deg, #0f172a, #1e293b); padding: 24px 28px; text-align: center; }}
  .header img {{ width: 40px; height: 40px; border-radius: 8px; background: #fff; padding: 3px; margin-bottom: 10px; }}
  .header h1 {{ color: #fff; font-size: 16px; margin: 0; font-weight: 700; letter-spacing: 0.02em; }}
  .header p {{ color: #94a3b8; font-size: 10px; margin: 4px 0 0; }}
  .badge {{ display: inline-block; background: #f59e0b; color: #fff; font-size: 9px; font-weight: 700; padding: 4px 12px; border-radius: 12px; text-transform: uppercase; letter-spacing: 0.08em; margin-top: 10px; }}
  .body {{ padding: 24px 28px; }}
  .title {{ font-size: 15px; font-weight: 700; color: #0f172a; margin: 0 0 16px; padding-bottom: 12px; border-bottom: 1px solid #e2e8f0; }}
  .id-box {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px; margin-bottom: 16px; text-align: center; }}
  .id-label {{ font-size: 8px; color: #64748b; text-transform: uppercase; letter-spacing: 0.1em; font-weight: 700; }}
  .id-value {{ font-size: 12px; font-weight: 700; color: #2563eb; font-family: 'Courier New', monospace; word-break: break-all; margin-top: 2px; }}
  .section {{ margin-bottom: 14px; }}
  .section-title {{ font-size: 9px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; margin-bottom: 6px; }}
  .row {{ display: flex; padding: 5px 0; border-bottom: 1px solid #f1f5f9; }}
  .row-label {{ width: 110px; font-size: 10px; color: #64748b; font-weight: 500; flex-shrink: 0; }}
  .row-value {{ font-size: 11px; color: #1e293b; font-weight: 500; }}
  .status-box {{ display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-radius: 8px; margin-bottom: 16px; }}
  .status-box.pendiente {{ background: #fffbeb; border: 1px solid #fde68a; }}
  .status-box.revision {{ background: #eff6ff; border: 1px solid #bfdbfe; }}
  .status-box.aprobada {{ background: #f0fdf4; border: 1px solid #bbf7d0; }}
  .status-box.rechazada {{ background: #fef2f2; border: 1px solid #fecaca; }}
  .status-dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
  .status-box.pendiente .status-dot {{ background: #f59e0b; }}
  .status-box.revision .status-dot {{ background: #3b82f6; }}
  .status-box.aprobada .status-dot {{ background: #22c55e; }}
  .status-box.rechazada .status-dot {{ background: #ef4444; }}
  .status-text {{ font-size: 11px; font-weight: 600; color: #334155; }}
  .note {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px; font-size: 10px; color: #64748b; line-height: 1.5; margin-top: 16px; }}
  .footer {{ padding: 16px 28px; text-align: center; font-size: 9px; color: #cbd5e1; border-top: 1px solid #f1f5f9; }}
  .actions {{ padding: 16px 28px; text-align: center; border-top: 1px solid #f1f5f9; }}
  .btn {{ display: inline-block; padding: 10px 20px; border-radius: 8px; font-size: 12px; font-weight: 600; cursor: pointer; border: none; margin: 4px; }}
  .btn-primary {{ background: #2563eb; color: #fff; }}
  .btn-secondary {{ background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }}
</style>
</head>
<body>
<div class="card">
  <div class="header">
    <img src="{logo_url}" alt="Pre-Cosquín"/>
    <h1>Festival Pre-Cosquín 2027</h1>
    <p>Puerto Pirámides, Chubut</p>
    <div class="badge">Inscripción Registrada</div>
  </div>
  <div class="body">
    <div class="title">Constancia de Inscripción</div>
    <div class="id-box">
      <div class="id-label">N° de Inscripción</div>
      <div class="id-value">{inscription_id}</div>
    </div>
    <div class="section">
      <div class="section-title">Datos Personales</div>
      <div class="row"><span class="row-label">Nombre</span><span class="row-value">{full_name}</span></div>
      <div class="row"><span class="row-label">DNI</span><span class="row-value">{dni or '-'}</span></div>
      <div class="row"><span class="row-label">Fecha de nacimiento</span><span class="row-value">{birth_date or '-'}</span></div>
      <div class="row"><span class="row-label">Edad</span><span class="row-value">{age or '-'}</span></div>
      <div class="row"><span class="row-label">Domicilio</span><span class="row-value">{address or '-'}</span></div>
      <div class="row"><span class="row-label">Localidad</span><span class="row-value">{locality or '-'}</span></div>
      <div class="row"><span class="row-label">Provincia</span><span class="row-value">{province or '-'}</span></div>
      <div class="row"><span class="row-label">Teléfono</span><span class="row-value">{phone or '-'}</span></div>
      <div class="row"><span class="row-label">Email</span><span class="row-value">{email}</span></div>
    </div>
    <div class="section">
      <div class="section-title">Participación</div>
      <div class="row"><span class="row-label">Categoría</span><span class="row-value">{cat_label} › {subcat_label}</span></div>
      <div class="row"><span class="row-label">Nombre artístico</span><span class="row-value">{display_name}</span></div>
      {'<div class="row"><span class="row-label">Biografía</span><span class="row-value">' + bio[:200] + '...</span></div>' if bio else ''}
      {themes_html}
      {members_html}
    </div>
    <div class="status-box {'pendiente' if status_val == 'PENDIENTE' else 'revision' if status_val == 'EN_REVISION' else 'aprobada' if status_val == 'APROBADA' else 'rechazada'}">
      <div class="status-dot"></div>
      <span class="status-text">Estado: {status_val.replace('_', ' ').title()}</span>
    </div>
    <div class="note">
      <strong>Nota:</strong> Tu código QR de acreditación se generará una vez que tu inscripción sea aprobada por el equipo organizador.
    </div>
  </div>
  <div class="actions no-print">
    <button class="btn btn-primary" onclick="window.print()">Imprimir / Guardar PDF</button>
  </div>
  <div class="footer">
    Precosquin — Festival Provincial de Folklore · Puerto Pirámides, Chubut
  </div>
</div>
</body>
</html>'''

    return Response(content=html, media_type="text/html; charset=utf-8")


@router.post("/{inscription_id}/resend-constancia")
async def resend_constancia(inscription_id: str, data: CancelRequest, db=Depends(get_db)):
    """Public endpoint: resend constancia email after OTP verification."""
    try:
        existing = db.table("inscriptions").select("id, email, full_name").eq("id", inscription_id).single().execute()
    except Exception as e:
        logger.error("db_error", error=str(e))
        raise HTTPException(status_code=500, detail="Error al buscar inscripción")

    if not existing.data:
        raise HTTPException(status_code=404, detail="Inscripción no encontrada")

    if existing.data["email"].lower() != data.email.lower():
        raise HTTPException(status_code=403, detail="El email no coincide con esta inscripción")

    try:
        _send_constancia_email(existing.data)
    except Exception as e:
        logger.error("resend_constancia_failed", inscription_id=inscription_id, error=str(e))
        raise HTTPException(status_code=500, detail="Error al enviar el correo")

    return {"message": "Constancia enviada correctamente"}


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
    path = f"{inscription_id}/{file_type}.{ext}"

    try:
        content = await file.read()
        logger.info("Read file content successfully", size_bytes=len(content), file_type=file_type, filename=file.filename)
    except Exception as e:
        logger.error("Error reading uploaded file", error=str(e), file_type=file_type, filename=file.filename)
        raise HTTPException(status_code=500, detail=f"Error al leer el archivo: {str(e)}")

    # Ensure the inscriptions bucket exists before uploading
    try:
        from app.api.v1.endpoints.storage import _ensure_bucket
        _ensure_bucket(db, "inscriptions")
    except Exception as e:
        logger.warning("Could not ensure bucket exists", error=str(e))

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
    from app.core.config import settings

    frontend_url = settings.FRONTEND_URL or "https://app.precosquin.com"
    logo_url = "data:image/webp;base64,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"

    full_name = inscription.full_name or f"{inscription.first_name or ''} {inscription.last_name or ''}".strip() or inscription.email
    email = inscription.email
    phone = inscription.phone or "-"
    dni = inscription.dni or "-"
    birth_date = inscription.birth_date or "-"
    age = f"{inscription.age} años" if inscription.age else "-"
    address = inscription.address or "-"
    locality = inscription.locality or "-"
    province = inscription.province or "-"

    inscription_id = created.get("id", "")
    created_at = created.get("created_at", "")

    cat_label = "Música" if inscription.category == "musica" else "Danza" if inscription.category == "danza" else inscription.category or "-"
    subcat_label = inscription.subcategory.replace("_", " ").replace("-", " ").title() if inscription.subcategory else "-"
    stage_name = inscription.stage_name or "-"

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

    html_body = f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta http-equiv="X-UA-Compatible" content="IE=edge"/>
<title>Confirmación de Inscripción - Pre Cosquín Puerto Pirámides 2027</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased;color:#0f172a">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9">
<tr><td align="center" style="padding:24px 16px">

<!-- Container -->
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)">

<!-- ==================== HEADER ==================== -->
<tr><td style="background:linear-gradient(135deg,#1e3a8a,#3b82f6);padding:28px 32px;text-align:center">
  <img src="{logo_url}" alt="Logo Pre Cosquín Puerto Pirámides" width="48" height="48" style="display:block;margin:0 auto 12px;border-radius:8px;background:#ffffff;padding:4px" />
  <div style="font-size:16px;font-weight:700;color:#ffffff;letter-spacing:0.02em">Pre-Cosquín Puerto Pirámides 2027</div>
</td></tr>

<!-- ==================== SUCCESS BANNER ==================== -->
<tr><td style="padding:32px 32px 16;text-align:center">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:12px">
  <tr>
    <td style="padding:24px 24px 16;text-align:center">
      <img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2MCIgaGVpZ2h0PSI2MCIgdmlld0JveD0iMCAwIDYwIDYwIiBmaWxsPSJub25lIj48Y2lyY2xlIGN4PSIzMCIgY3k9IjMwIiByPSIyOCIgc3Ryb2tlPSIjMTZhMzRhIiBzdHJva2Utd2lkdGg9IjIiIGZpbGw9IiNmMGZkZjQiLz48cGF0aCBkPSJNMTggMzBsNyA3IDE2LTE2IiBzdHJva2U9IiMxNmEzNGEiIHN0cm9rZS13aWR0aD0iMy41IiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz48L3N2Zz4=" alt="Confirmado" width="60" height="60" style="display:block;margin:0 auto;border-radius:50%%;background:#dbeafe" /><br/>
      <div style="font-size:20px;font-weight:700;color:#166534;margin:12px 0 4px">¡Inscripción recibida correctamente!</div>
      <div style="font-size:14px;color:#15803d">Tu inscripción fue registrada y se encuentra en proceso de revisión administrativa.</div>
    </td>
  </tr>
  </table>
</td></tr>

  <!-- ==================== REGISTRATION SUMMARY ==================== -->
  <tr><td style="padding:24px 32px 0">
    <div style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px">Resumen de Inscripción</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px">
    <tr>
      <td style="padding:16px;text-align:center">
        <div style="font-size:8px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">Número de Inscripción</div>
        <div style="font-size:18px;font-weight:700;color:#2563eb;font-family:'Courier New',monospace;margin-top:3px;word-break:break-all">{inscription_id}</div>
        <div style="font-size:10px;color:#94a3b8;margin-top:4px">Guardá este número para futuras comunicaciones</div>
      </td>
    </tr>
    </table>
  </td></tr>

  <!-- ==================== PARTICIPANT SUMMARY ==================== -->
  <tr><td style="padding:8px 32px 0">
    <div style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px">Datos del Participante</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid #e2e8f0;border-radius:10px">

    <!-- Nombre -->
    <tr>
      <td style="padding:12px 16px 0">
        <div style="font-size:8px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">Nombre</div>
        <div style="font-size:14px;font-weight:700;color:#1e3a8a;margin-top:2px;word-break:break-word">{full_name}</div>
      </td>
    </tr>
    <!-- DNI -->
    <tr>
      <td style="padding:6px 16px 0">
        <div style="font-size:8px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">DNI</div>
        <div style="font-size:14px;font-weight:500;color:#0f172a;margin-top:2px">{dni}</div>
      </td>
    </tr>
    <!-- Email -->
    <tr>
      <td style="padding:6px 16px 0">
        <div style="font-size:8px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">Email</div>
        <div style="font-size:14px;font-weight:500;color:#0f172a;margin-top:2px;word-break:break-all">{email}</div>
      </td>
    </tr>
    <!-- Teléfono -->
    <tr>
      <td style="padding:6px 16px 0">
        <div style="font-size:8px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">Teléfono</div>
        <div style="font-size:14px;font-weight:500;color:#0f172a;margin-top:2px">{phone}</div>
      </td>
    </tr>
    <!-- Provincia -->
    <tr>
      <td style="padding:6px 16px 0">
        <div style="font-size:8px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">Provincia</div>
        <div style="font-size:14px;font-weight:500;color:#0f172a;margin-top:2px">{province}</div>
      </td>
    </tr>
    <!-- Nombre Artístico -->
    <tr>
      <td style="padding:6px 16px 12px">
        <div style="font-size:8px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">Nombre Artístico</div>
        <div style="font-size:14px;font-weight:500;color:#0f172a;margin-top:2px">{stage_name}</div>
      </td>
    </tr>

    </table>
  </td></tr>

  <!-- ==================== PARTICIPATION INFO ==================== -->
  <tr><td style="padding:8px 32px 0">
    <div style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px">Participación</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid #e2e8f0;border-radius:10px">

    <!-- Categoría -->
    <tr>
      <td style="padding:12px 16px 0">
        <div style="font-size:8px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">Categoría</div>
        <div style="font-size:14px;font-weight:700;color:#1e3a8a;margin-top:2px">{cat_label}</div>
      </td>
    </tr>
    <!-- Subcategoría -->
    <tr>
      <td style="padding:6px 16px 12px">
        <div style="font-size:8px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">Subcategoría</div>
        <div style="font-size:14px;font-weight:700;color:#1e3a8a;margin-top:2px">{subcat_label}</div>
      </td>
    </tr>

     </table>
  </td></tr>

<!-- ==================== STATUS CARD ==================== -->
<tr><td style="padding:32px 32px 0">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:12px">
  <tr>
    <td style="padding:24px;text-align:center">
      <div style="font-size:9px;font-weight:700;color:#2563eb;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px">Estado Actual</div>
      <div style="font-size:16px;font-weight:700;color:#166534">En espera a prueba para Precosquín Puerto Pirámides</div>
      <div style="font-size:12px;color:#15803d;margin-top:6px">Primera etapa - tu inscripción está en proceso. Te contactaremos pronto.</div>
      <div style="font-size:11px;color:#15803d;margin-top:8px">Tiempo estimado de revisión: 3-7 días hábiles.</div>
    </td>
  </tr>
  </table>
</td></tr>

<!-- ==================== TIMELINE ==================== -->
<tr><td style="padding:32px 32px 0">

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td style="padding:4px 0;text-align:center">
      <div style="font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">Proceso de Participación</div>
    </td>
  </tr>
  </table>

  <!-- Step 1 (Current) -->
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td width="40" style="text-align:center;padding:4px 0 0">
      <table role="presentation" width="32" height="32" cellpadding="0" cellspacing="0" style="background:#22c55e;border-radius:50%;margin:0 auto">
      <tr><td style="text-align:center">
        <div style="font-size:13px;font-weight:700;color:#ffffff">1</div>
      </td></tr>
      </table>
    </td>
    <td style="padding:4px 0 0">
      <div style="font-size:13px;font-weight:700;color:#166534">Inscripción recibida</div>
      <div style="font-size:11px;color:#475569">Tu inscripción fue registrada correctamente</div>
    </td>
  </tr>
  </table>

  <!-- Step 2 -->
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td width="40" style="text-align:center;padding:8px 0 0">
      <table role="presentation" width="32" height="32" cellpadding="0" cellspacing="0" style="background:#e2e8f0;border-radius:50%;margin:0 auto">
      <tr><td style="text-align:center">
        <div style="font-size:13px;font-weight:700;color:#94a3b8">2</div>
      </td></tr>
      </table>
    </td>
    <td style="padding:8px 0 0">
      <div style="font-size:13px;font-weight:700;color:#64748b">Revisión administrativa</div>
      <div style="font-size:11px;color:#94a3b8">Evaluación de tu inscripción</div>
    </td>
  </tr>
  </table>

  <!-- Step 3 -->
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td width="40" style="text-align:center;padding:8px 0 0">
      <table role="presentation" width="32" height="32" cellpadding="0" cellspacing="0" style="background:#e2e8f0;border-radius:50%;margin:0 auto">
      <tr><td style="text-align:center">
        <div style="font-size:13px;font-weight:700;color:#94a3b8">3</div>
      </td></tr>
      </table>
    </td>
    <td style="padding:8px 0 0">
      <div style="font-size:13px;font-weight:700;color:#64748b">Aprobación</div>
      <div style="font-size:11px;color:#94a3b8">Confirmación de participación</div>
    </td>
  </tr>
  </table>

  <!-- Step 4 -->
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td width="40" style="text-align:center;padding:8px 0 0">
      <table role="presentation" width="32" height="32" cellpadding="0" cellspacing="0" style="background:#e2e8f0;border-radius:50%;margin:0 auto">
      <tr><td style="text-align:center">
        <div style="font-size:13px;font-weight:700;color:#94a3b8">4</div>
      </td></tr>
      </table>
    </td>
    <td style="padding:8px 0 0">
      <div style="font-size:13px;font-weight:700;color:#64748b">Prueba</div>
      <div style="font-size:11px;color:#94a3b8">Presentación artística</div>
    </td>
  </tr>
  </table>

  <!-- Step 5 -->
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td width="40" style="text-align:center;padding:8px 0 0">
      <table role="presentation" width="32" height="32" cellpadding="0" cellspacing="0" style="background:#e2e8f0;border-radius:50%;margin:0 auto">
      <tr><td style="text-align:center">
        <div style="font-size:13px;font-weight:700;color:#94a3b8">5</div>
      </td></tr>
      </table>
    </td>
    <td style="padding:8px 0 8px">
      <div style="font-size:13px;font-weight:700;color:#64748b">Resultados</div>
      <div style="font-size:11px;color:#94a3b8">Comunicación de resultados</div>
    </td>
  </tr>
  </table>
</td></tr>

<!-- ==================== IMPORTANT INFO ==================== -->
<tr><td style="padding:24px 32px 0">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:12px">
  <tr>
    <td style="padding:20px">
      <div style="font-size:9px;font-weight:700;color:#2563eb;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:8px">Información Importante</div>
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr>
        <td width="24" style="text-align:center;padding-right:8px">
          <img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2MCIgaGVpZ2h0PSI2MCIgdmlld0JveD0iMCAwIDYwIDYwIiBmaWxsPSJub25lIj48Y2lyY2xlIGN4PSIzMCIgY3k9IjMwIiByPSIyOCIgc3Ryb2tlPSIjMTZhMzRhIiBzdHJva2Utd2lkdGg9IjIiIGZpbGw9IiNmMGZkZjQiLz48cGF0aCBkPSJNMTggMzBsNyA3IDE2LTE2IiBzdHJva2U9IiMxNmEzNGEiIHN0cm9rZS13aWR0aD0iMy41IiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz48L3N2Zz4=" alt="" width="18" height="18" style="display:block" />
        </td>
        <td>
          <div style="font-size:13px;color:#1e40af;line-height:1.6"><strong>No asistas al festival todavía.</strong> Debes esperar a la aprobación oficial de tu inscripción. Te enviaremos comunicaciones a este email con los próximos pasos y tu fecha de presentación.</div>
        </td>
      </tr>
      </table>
    </td>
  </tr>
  </table>
</td></tr>

<!-- ==================== CALL TO ACTION ==================== -->
<tr><td style="padding:24px 32px 0;text-align:center">
  <table role="presentation" cellpadding="0" cellspacing="0">
  <tr>
    <td align="center" bgcolor="#1e3a8a" style="border-radius:8px">
      <a href="{frontend_url}" style="display:inline-block;padding:14px 32px;font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;border:1px solid #1e3a8a;border-radius:8px">Visitar Sitio Oficial</a>
    </td>
  </tr>
  </table>
</td></tr>

<!-- ==================== CONTACT ==================== -->
<tr><td style="padding:32px 32px 0">
  <div style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px">¿Necesitás ayuda?</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px">
  <tr>
    <td style="padding:16px">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">

      <!-- Email -->
      <tr>
        <td width="24" valign="top" style="padding-right:12px">
          <img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2MCIgaGVpZ2h0PSI2MCIgdmlld0JveD0iMCAwIDYwIDYwIiBmaWxsPSJub25lIj48Y2lyY2xlIGN4PSIzMCIgY3k9IjMwIiByPSIyOCIgc3Ryb2tlPSIjMTZhMzRhIiBzdHJva2Utd2lkdGg9IjIiIGZpbGw9IiNmMGZkZjQiLz48cGF0aCBkPSJNMTggMzBsNyA3IDE2LTE2IiBzdHJva2U9IiMxNmEzNGEiIHN0cm9rZS13aWR0aD0iMy41IiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz48L3N2Zz4=" alt="" width="18" height="18" style="display:inline-block" />
        </td>
        <td style="padding-top:0">
          <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;font-weight:700">Email</div>
          <a href="mailto:info@precosquinpiramides.com" style="font-size:13px;color:#1e3a8a;font-weight:500;text-decoration:none">info@precosquinpiramides.com</a>
        </td>
      </tr>

      <!-- WhatsApp -->
      <tr><td colspan="2" style="padding:8px 0 0">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td width="24" valign="top" style="padding-right:12px">
            <img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2MCIgaGVpZ2h0PSI2MCIgdmlld0JveD0iMCAwIDYwIDYwIiBmaWxsPSJub25lIj48Y2lyY2xlIGN4PSIzMCIgY3k9IjMwIiByPSIyOCIgc3Ryb2tlPSIjMTZhMzRhIiBzdHJva2Utd2lkdGg9IjIiIGZpbGw9IiNmMGZkZjQiLz48cGF0aCBkPSJNMTggMzBsNyA3IDE2LTE2IiBzdHJva2U9IiMxNmEzNGEiIHN0cm9rZS13aWR0aD0iMy41IiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz48L3N2Zz4=" alt="" width="18" height="18" style="display:inline-block" />
          </td>
          <td style="padding-top:0">
            <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;font-weight:700">WhatsApp</div>
            <a href="https://wa.me/5492801234567" style="font-size:13px;color:#1e3a8a;font-weight:500;text-decoration:none">+54 9 280 123-4567</a>
          </td>
        </tr>
        </table>
      </td></tr>

      <!-- Website -->
      <tr><td colspan="2" style="padding:8px 0 0">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td width="24" valign="top" style="padding-right:12px">
            <img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI2MCIgaGVpZ2h0PSI2MCIgdmlld0JveD0iMCAwIDYwIDYwIiBmaWxsPSJub25lIj48Y2lyY2xlIGN4PSIzMCIgY3k9IjMwIiByPSIyOCIgc3Ryb2tlPSIjMTZhMzRhIiBzdHJva2Utd2lkdGg9IjIiIGZpbGw9IiNmMGZkZjQiLz48cGF0aCBkPSJNMTggMzBsNyA3IDE2LTE2IiBzdHJva2U9IiMxNmEzNGEiIHN0cm9rZS13aWR0aD0iMy41IiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiLz48L3N2Zz4=" alt="" width="18" height="18" style="display:inline-block" />
          </td>
          <td style="padding-top:0">
            <div style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;font-weight:700">Sitio Web</div>
            <a href="{frontend_url}" style="font-size:13px;color:#1e3a8a;font-weight:500;text-decoration:none">www.precosquinpiramides.com</a>
          </td>
        </tr>
        </table>
      </td></tr>

      </table>
    </td>
  </tr>
  </table>
</td></tr>

<!-- ==================== FOOTER ==================== -->
<tr><td style="padding:28px 32px 24;text-align:center;border-top:1px solid #e2e8f0">
  <div style="font-size:11px;color:#94a3b8;line-height:1.6;margin-bottom:6px">Precosquin — Organización Cultural info@precosquinpiramides.com</div>
  <div style="font-size:10px;color:#cbd5e1">Puerto Pirámides, Chubut · 2027</div>
</td></tr>

</table>
</td></tr>
</table>

</body>
</html>'''

    email_sender = get_email_sender()
    msg = EmailMessage(
        to=email,
        subject="Pre-Cosquín Puerto Pirámides — Confirmación de Inscripción",
        html=html_body,
        reply_to="info@precosquinpiramides.com",
        attachments=None,
    )
    result = email_sender.send(msg)
    logger.info("confirmation_email_sent", to=email, status=result.status, message_id=result.message_id)


def _send_update_email(inscription_data: dict):
    """Send email when participant updates their inscription."""
    email = inscription_data.get("email", "")
    full_name = inscription_data.get("full_name", "")
    inscription_id = inscription_data.get("id", "")

    from app.core.config import settings
    frontend_url = settings.FRONTEND_URL or "https://app.precosquin.com"
    logo_url = "data:image/webp;base64,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"

    html_body = f'''<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"/></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9">
<tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="580" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)">
<tr><td style="background:linear-gradient(135deg,#1e40af,#3b82f6);padding:28px 32px;text-align:center">
  <img src="{logo_url}" alt="Logo" width="40" height="40" style="display:block;margin:0 auto 10px;border-radius:8px;background:#fff;padding:3px"/>
  <div style="font-size:20px;font-weight:800;color:#ffffff">Inscripción Actualizada</div>
  <div style="font-size:11px;color:rgba(255,255,255,0.8);margin-top:4px">Pre-Cosquín 2027</div>
</td></tr>
<tr><td style="padding:28px 32px;text-align:center">
  <div style="font-size:16px;font-weight:700;color:#1e293b;margin-bottom:8px">Hola {full_name}</div>
  <div style="font-size:13px;color:#475569;line-height:1.6;max-width:420px;margin:0 auto 16px">
    Tu inscripción fue actualizada correctamente con los cambios que realizaste.
  </div>
  <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:12px 16px;display:inline-block;margin-bottom:16px">
    <div style="font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">N° de Inscripción</div>
    <div style="font-size:12px;font-weight:700;color:#2563eb;font-family:'Courier New',monospace;margin-top:2px">{inscription_id}</div>
  </div>
  <div style="font-size:12px;color:#64748b">Si tenés consultas, escribinos a <a href="mailto:info@precosquinpiramides.com" style="color:#2563eb">info@precosquinpiramides.com</a></div>
</td></tr>
<tr><td style="padding:20px 32px;text-align:center;border-top:1px solid #f1f5f9">
  <div style="font-size:9px;color:#cbd5e1">Precosquin — Puerto Pirámides, Chubut</div>
</td></tr>
</table></td></tr></table>
</body></html>'''

    email_sender = get_email_sender()
    msg = EmailMessage(
        to=email,
        subject="Pre-Cosquín — Tu inscripción fue actualizada correctamente",
        html=html_body,
        reply_to="info@precosquinpiramides.com",
    )
    result = email_sender.send(msg)
    logger.info("update_email_sent", to=email, status=result.status, message_id=result.message_id)


def _send_cancel_email(email: str, full_name: str):
    """Send email when participant cancels their inscription."""
    from app.core.config import settings
    frontend_url = settings.FRONTEND_URL or "https://app.precosquin.com"
    logo_url = "data:image/webp;base64,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"

    html_body = f'''<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"/></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9">
<tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="580" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)">
<tr><td style="background:linear-gradient(135deg,#991b1b,#ef4444);padding:28px 32px;text-align:center">
  <img src="{logo_url}" alt="Logo" width="40" height="40" style="display:block;margin:0 auto 10px;border-radius:8px;background:#fff;padding:3px"/>
  <div style="font-size:20px;font-weight:800;color:#ffffff">Inscripción Cancelada</div>
  <div style="font-size:11px;color:rgba(255,255,255,0.8);margin-top:4px">Festival Pre-Cosquín 2027</div>
</td></tr>
<tr><td style="padding:28px 32px;text-align:center">
  <div style="font-size:16px;font-weight:700;color:#1e293b;margin-bottom:8px">Hola {full_name}</div>
  <div style="font-size:13px;color:#475569;line-height:1.6;max-width:420px;margin:0 auto 16px">
    Tu inscripción fue cancelada correctamente. Esta acción ya no se puede deshacer.
  </div>
  <div style="font-size:12px;color:#64748b;line-height:1.6;margin-bottom:16px">
    Si querés participar, podés realizar una nueva inscripción cuando lo desees.
  </div>
  <a href="{frontend_url}/inscripcion" style="display:inline-block;background:#2563eb;color:#fff;padding:10px 24px;border-radius:8px;font-size:12px;font-weight:600;text-decoration:none">Nueva inscripción</a>
  <div style="font-size:12px;color:#64748b;margin-top:16px">Si tenés consultas, escribinos a <a href="mailto:info@precosquinpiramides.com" style="color:#2563eb">info@precosquinpiramides.com</a></div>
</td></tr>
<tr><td style="padding:20px 32px;text-align:center;border-top:1px solid #f1f5f9">
  <div style="font-size:9px;color:#cbd5e1">Precosquin — Puerto Pirámides, Chubut</div>
</td></tr>
</table></td></tr></table>
</body></html>'''

    email_sender = get_email_sender()
    msg = EmailMessage(
        to=email,
        subject="Pre-Cosquín — Tu inscripción fue cancelada",
        html=html_body,
        reply_to="info@precosquinpiramides.com",
    )
    result = email_sender.send(msg)
    logger.info("cancel_email_sent", to=email, status=result.status, message_id=result.message_id)


def _send_constancia_email(inscription_data: dict):
    """Send constancia email with link to download PDF."""
    email = inscription_data.get("email", "")
    full_name = inscription_data.get("full_name", "")
    inscription_id = inscription_data.get("id", "")
    category = inscription_data.get("category", "")
    subcategory = inscription_data.get("subcategory", "")

    from app.core.config import settings
    frontend_url = settings.FRONTEND_URL or "https://app.precosquin.com"
    logo_url = "data:image/webp;base64,UklGRuQPAABXRUJQVlA4WAoAAAAQAAAAhwAAhwAAQUxQSLQDAAABoEZtk2HbqR4c2+fEtm3btm3btm3btnau97VtHRsb3RUnVV2VX1lZETEB8F/iUckKWx9yyuW33HHHbTdedNIBmy1bFOoTN+x2xcujFnZlHP65zXTOSzx94XY1kRqmes/7Brdk8Z9ONyZu2Cxfg+oj3mzMInVq4g0bRrJFWz66wCLPvm+PLJIr/5Bv+5BxdtJFVTIVHDE6i8zdvEsq5In2HZZBD93UY3KFWevNFHqa+XITI0jhZU3ocftNJWKs/Z1Fr+3PG8oQHrkYvW88NRKg4LZ+FDD1cIl3le9bFNF+XuvZcj+hmENX8WrlESjo+DU9WnU0ijpuNW9WGI3Cjlrek6oEivttlRfF76O87r1CD8J7nEBobwn5HT6AIvcdxG7NRSj0vFWZ5X2GYr+fx+vsrFyZM1mt2YiCL1mNUfQ6iv5axGfXftn6d2GTn0Dhv8vjcnBGuvR+THIHo/g/xTz2Scs3sAuL8BNU8LWAw/rdGrSuxOE+1NCdx6Bstgo4Ko9uz4wOvevTPY5KXkOWP12LREi1wYAWnStSnYlauiOJzKtq4CNEuZP0SMY09a16NNXQbJXWI7UZzTFOD3c8zdWo6A00T2vyHM37mnxIYn7SZFhIEY7WZEYhyXhNFpaSjPvXMFKTREgRJDR5Dkg/1uQxmpc0uY7mVk0upzlLEXcmzT5Wj+zeNGv36dG3Nk1lox6NVTTxKD1G5dCYl/R40dDAJXpcAKSFhyTVyGxHER86KotqLi4jqHwpjYp+Zgi2/+jjTz4ZPNvp4M4FyiAIgnC9Hh06VyP5w/gnHb4J6eBEq4E9ARhWzddgQRUHuFODe4DlGu3yda7Nwzwj35uGB6zXLl3vVsDUPCTdmyEXWG6BbJ3rAd+zrGj3B4wKvpdsei1w3rRDroGDgbW51or1dMQL8j+ValItcF9pukytWwH/nTokGjjBeGBOSsljbwvAx/D6rDTuxXzwM/dZJ8yXZeBr4VtOlEQt+Fv6nhNk8LLgc8kbTgr3TR34XfBIWgb7Vjn4Hp/fI0HqrgLw3+w117+mY0IQcdWPrV/ux/UNCJl/YbNPPbcUg5xmzXcGfLFDtg9A1Hiv8c6L2ecUgbhlF8127JrvrAWRay6Z6Ti5uTetZEDqijOTKS6p5DnVBiTP2frBKVm67NR7N88B+Yv3fGJqP4HrSN6/WzFoWbD+WS+Nbku7v2P7Fnx/9yErxKBsTv0mR93w6rfDR42dMG5McvAHj16wxxqlIahtwijOiaMoMPB/lQFWUDggCgwAAJA2AJ0BKogAiAA+kTyYSKWjIiEstgw4sBIJYwhwAZOzyae5Y/M/irJRwQPwRrtxlzyTxMP6f+DvuH8Lv1347eevlZ9v+3HKoaafvfM3vb4AXrfwPdtvsfmHe3/3TvwdUfIA/WD/keVz4NHofsE/ob9gPdh/wvIf+f/6/2DP15633oyJQg64FAvIUpw3+FhS0y+hie1p5NtD8f7p+IN+zsA6F/69i7gIx7lfAt33UZFQCn7b4FLRbJl5wUSWxRiuPyvm/5K2vI5ACwdhg+8nVFP859BzdwrD2FjrYiBaPnyC0G999assZbVDQg33gqAblM4F2wm36kEz7p5HvXlY6GTlB5qHX/kAsC6nsEnKfvEPMjR3a8ajsKq5n12hsU9OOGmK3CnDxjrqD1ITylwuN5CyLprNOjDsuqQS7V994se96XiKgwMWuxokqq3Y0B/RW4c/oF30c0EFJJ780rdnhv/Ho/P3UTDQew2WZACXr519Wk072xdqTEFMX8jpt+KSAVUo0P2c4oPfxDlyZ6HFTgA+Z732kWBZ7d+xWcHo47ctdLxefw216wfPn9SHMS0PkHdn39w9Ahpy53qQwsAA/s1wJ6bVj7sKC5Wzs/MZqRYYWaHPYQEf48RT/iErVKqR7R/JBYmM4aKuGjrJZxKJVwfzYNn2OIuiUo1Ij2TOhQgHxOdo4Zezn0a4cNuVyGhwXrS1SYQSfw6jBk47fnq3qYJuJP2yzVTRS2dG12IcXr4xhSY4aP0ppquQXA6LjlvHTyLD/v1jVBjhHTpXXWFl9ONgUTT7tCavf6nb1hqbsD6ux39uYnWQVeQFlLHS5WaUEr2mjQGjAyWT+hEY1tiz+xZ7HpwtESUTEVLAMcz7IWc9elwuYE2WsaF2E9yHxLvKIT1D/+hIV00hsXAWuGJxUkVJjGML72uHA2ILtjhf0YLD5Noh0dtjfin17zSs0WP6IL17hWqx7vB3lUwdCzZfnwih40MEnfO3NEfuWpW16vVymN/9rryL3WEaF4HoOnA2tNzRjs+c/R4+oiF0syOa75dlsoXVhS+lI1xrH0I+nW45SMC67+iNALj6CdwRTWean7VxbDNkE6eTEn2cHDcey5Fi/FChtl98ZR9swfrRLfrsxNbj+rxT98VXHpVdHj0YDmqgfc4ZS0I1xTnzO7LttAp2WLGcG/k41Opp5KmxukC8LqihDcsgwNZXKj352ts/TwbElKU6nkf4Ny5U2I9CVHs3LMKby0FNDEIUwfT7WDDLxKJ0Bm1IQF5x8zc13RBNeu4BziJvDfcvC/0+2McexYsf8ELJotquBHLQinFerc34dt297+lHcXJNTrApfwwDKCl2DEb7hA66wZE6VN7gYY5hjK+ERwMQn/VCq83ijfZQnW+wHMQJIT4M5deTvDQ8hz/q9PpmJtHBp1FY6DONG1fGFT74O7NytvD9tyfV1DPOCsX9GZJQ+XL4579R6L19R45Z7rDLCWfyW/JgyVQK/amXgjmB15P5OaYNlvvtoOEbPtCN1p+ym1b7Y/AndyTZ/zT7vWvCp1/2X1++lUGVej89AumWPqCXsOGHJW4+qsK2gBLVURPJEIyfBvSlmCUD6WA+A6ARBjBbW3jEGVg7B2oFlns/JhFiKHUINNJxXpqJp1WJamvcHqIlZ9vB/N7QKFEfjjTo0teVmwxweVa/Ve5yl6Wuh9gYu71kin+83fqBhT8KOsjuZ03creO0uEvjWfezwKJcstxBetoDpubqXGcptl67ZER8kNgZ01XXpC76OlkuMaPEAGCzsahgNvR+kmGNsMLAsG+27r5x9mTfI8jUZRTL//+Xony1vHKt4LZdoZ2wrI8iYvYIGlh0sFwqZ8Vfiv6t79v0OVB3EvvUdOdCDnauRTDwNu4D1vterC+z0+sGu8DMb3i3VzUvY7kbjX+dx2J3/C1+8MHIwtqs5VywYkPeuMyM/RN/LdTc5clrcNR/7paT7j/AIJUTso/w8rNfOCBLkvnZjHdXfAjOh9qAWa1hT0A7lW8dB9uvlvW11Ypii5PYj7GpxknrRG2Lxwj93pz3SdKlERXuDieMGOr7xnMTEwoJwEUO5fyG3WMT0rltOZ8g7fFaacNkmfyK4juFCNfBjJ6G+KeUs97nZF3XsNasuTGFkER5nvKRyTsoPC/92MQrmXod/teHlX3hY1w6BRlDm0HF19IU26e9ZuYSH5sKicnAxITDcomH4b0OvdHrNwA0eUNyEsRKE6NTm/Sb1jV0DrFFedrp4JXoTNrcCNEFLiOzVntT/hr9RMtv+bCm2R8BU9olkqqAOmTjjaDCgE+UZ1t485Xeu0U3qaCM8imZ1VX8YCJWMpyeu5+46aMmaxcJwzliK7dYv8wMrVQhdcGnHXfl2a+VYeIq49r7hY6YjJwpAKoFiaiPgOjreCPQ0Wdw3OqhVFBFLnhvPejC2BNg6Ya0Wx+pAx4YbY8XOkuyd415LJMdmQ3EI8fZhBX0zLBPTtOCc68FtXSKeJCONYNrU1/DjIogET1eknOCpCdDZQOY901TKk1sG2709vntaOU5wiwA9kn6PLT9OpThJP4kkVZRLePeXa+a8FSiTRgdMrewLROi632A3YKZRd3zScMBe8YteoKHWb+k/vm2ktm0gQ/6SM5j70omD9K7tvhZA02tmhqehuxcw5KGm36rxZexPzdKeExWYhe/v2G07j3EbxohFmLawSyixHxKpuok01PLB7m+7VC5JPDZCbIW/IHYhoyKAilB7ZQDe+cajl3vMVrZQqeyU4dmQOAKjNlPz/ekL/+O0dajIuWwPi33jqTfOu+QLTbhMoIsxsZIsVBx/+5Own+FC47/kX5LHV49Pl3+3ngtrU9iDvj73lrDS3mzxCXnCL4gCG/ANGSHumm4OVi0NyJh63j5T05DUmaEvp9Vjr45tpyqVRWAy34FFAxeiXie9zfCWEHh9gnorLmcqe8UUh2ijrgrrMwbrjVlCwX8qv9pETilMxllv4HjIJcZDZUXgLUc1+DYeNen9H5vA/iMSh2M1nrXMmxNqQrfxN3hCwvcfUJJB07JfoHrGD43I/E3kekOjqT/ZjmU8+dtDBf+grfUlMl5460Uhij1MgSuVYmeI45P18+jDE5DfTyVwJWDNI99lhLE+Nr9R7QS2DB1WUddKYGL5Z/g9qsSi693OApGT+/+DTTwJEgBInlQJJe0AJ379wgL1CHRGhW+CihJOSX0l5MyyNEoVQN7kyIiy673FfpJgIbcVDDSdrlW5jDtfyu3nCkOw8/IsMTgZFRaQGqWE8eQMe0okXxO7+KY8GhhB+8n6ue4I8uje33KoyRRAID0jK29AxusZpBwz8O2UCXim2iNZ22K3gdjaR5HLNI2u587OQAX33xi5/1ks10NQTfzMTQxPuMhMGzAhI0iCdGBsX/7GSDlNNoUTkc1D/SjosO6yCy6f10oqDKWxUDrZtae3YgBDFx1cxUccX0jHqp/0Pai6pZSXGGO444z1jKyoz1UeqGyqKtaSSK1dh+PxrepAzwAOe2oBw0DcAKc7G9pRZk6eEJgQMnb5en3R1xsVrXq9lvmgv4Yh6w2lYHFUhphVngCJ54AxArc0gxwWxtNETv7gdsKfl/UicdVsvNDy0d0zBjxLrdTAp2wxwVm9wGKJDa+L9JD9HDH4rHMNO4/d/0nw5Liho/fGDUMYfZz/nWev4dRq+yCgCGRRvcDazg7yGGlRuyrSD0jgHS+IaSSYJk2tBA6CCkokCBPIYn9GjfodCABwaLFUoZ8N7UBhiRoeduZd2pwf9UDzkl8Ca9K1U3WI0RShQrVQG4IZNtds/N1uP14YGdvgxpVqrmZ2lrdjCePPTp8uEWWjsT3Aq9fdLJTu/5A8dYKH3l3Bl51kNzTu7ERvWdXYt7FsiFC1qPZEfBYtgijTIBnDJUfCskvkfJEzQ/FTk6mqdXX/Ch/CYuAK8I9AEB0n5hqOYA4jGq1nFlfK6+7qrnIGr/1yoaxilMsAAuBJiYO5gGpFSBfeGSlC6sOPP50err6IfiVJ/TWCADrC037EkYByUjhFQGPlGMjZrSNpgArzCKnosf+Bqjucn+oCZgsTUwwyVH+nJ5256d/4Co0AAAAAAAAAAA="
    constancia_url = f"{frontend_url}/inscripcion/constancia/{inscription_id}"

    cat_label = "Música" if category == "musica" else "Danza" if category == "danza" else category
    subcat_label = subcategory.replace("_", " ").title() if subcategory else "-"

    html_body = f'''<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"/></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9">
<tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="580" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)">
<tr><td style="background:linear-gradient(135deg,#0f172a,#1e293b);padding:28px 32px;text-align:center">
  <img src="{logo_url}" alt="Logo" width="40" height="40" style="display:block;margin:0 auto 10px;border-radius:8px;background:#fff;padding:3px"/>
  <div style="font-size:20px;font-weight:800;color:#ffffff">Constancia de Inscripción</div>
  <div style="font-size:11px;color:rgba(255,255,255,0.8);margin-top:4px">Pre-Cosquín 2027</div>
</td></tr>
<tr><td style="padding:28px 32px;text-align:center">
  <div style="font-size:16px;font-weight:700;color:#1e293b;margin-bottom:8px">Hola {full_name}</div>
  <div style="font-size:13px;color:#475569;line-height:1.6;max-width:420px;margin:0 auto 16px">
    Acá tenés tu constancia de inscripción en <strong>{cat_label} › {subcat_label}</strong>.
  </div>
  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 16px;margin-bottom:16px">
    <div style="font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700">N° de Inscripción</div>
    <div style="font-size:12px;font-weight:700;color:#2563eb;font-family:'Courier New',monospace;margin-top:2px">{inscription_id}</div>
  </div>
  <a href="{constancia_url}" style="display:inline-block;background:#2563eb;color:#fff;padding:12px 28px;border-radius:8px;font-size:13px;font-weight:600;text-decoration:none">Ver constancia / Imprimir PDF</a>
  <div style="font-size:12px;color:#64748b;margin-top:16px">Si tenés consultas, escribinos a <a href="mailto:info@precosquinpiramides.com" style="color:#2563eb">info@precosquinpiramides.com</a></div>
</td></tr>
<tr><td style="padding:20px 32px;text-align:center;border-top:1px solid #f1f5f9">
  <div style="font-size:9px;color:#cbd5e1">Precosquin — Puerto Pirámides, Chubut</div>
</td></tr>
</table></td></tr></table>
</body></html>'''

    email_sender = get_email_sender()
    msg = EmailMessage(
        to=email,
        subject="Pre-Cosquín — Tu constancia de inscripción",
        html=html_body,
        reply_to="info@precosquinpiramides.com",
    )
    result = email_sender.send(msg)
    logger.info("constancia_email_sent", to=email, status=result.status, message_id=result.message_id)


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
            "message": "Felicitaciones, tu inscripción al Pre-Cosquín 2027 fue aprobada. Pronto nos contactaremos con los próximos pasos.",
            "bg_color": "#f0fdf4",
            "border_color": "#bbf7d0",
            "title_color": "#166534",
            "msg_color": "#15803d",
            "icon": '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>',
        },
        "RECHAZADA": {
            "subject": "Pre-Cosquín — Resultado de tu inscripción",
            "title": "Resultado de tu inscripción",
            "message": "Lamentamos informarte que tu inscripción no fue aprobada en esta edición.",
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
  <div style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:0.02em">Pre-Cosquín 2027</div>
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
      <div style="font-size:11px;color:#475569;line-height:1.5">Si tenés consultas, respondé a este correo o escribinos a <a href="mailto:info@precosquinpiramides.com" style="color:#2563eb;text-decoration:none">info@precosquinpiramides.com</a></div>
    </td>
  </tr>
  </table>
</td></tr>

<!-- FOOTER -->
<tr><td style="padding:24px 32px 28px;text-align:center">
  <div style="font-size:10px;color:#cbd5e1">Precosquin — Puerto Pirámides, Chubut</div>
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
        reply_to="info@precosquinpiramides.com",
    )
    result = email_sender.send(msg)
    logger.info("status_change_email_sent", to=email, new_status=new_status, status=result.status, message_id=result.message_id)


def _send_approval_email(inscription_data: dict, qr_code_base64: str):
    """Send approval email with QR code embedded as CID attachment."""
    import base64 as b64
    from app.core.email import EmailAttachment
    from app.core.config import settings

    email = inscription_data.get("email", "")
    full_name = inscription_data.get("full_name", "")
    inscription_id = inscription_data.get("id", "")
    category = inscription_data.get("category", "")
    subcategory = inscription_data.get("subcategory", "")
    stage_name = inscription_data.get("stage_name") or full_name

    frontend_url = settings.FRONTEND_URL or "https://app.precosquin.com"
    logo_url = "data:image/webp;base64,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"
    constancia_url = f"{frontend_url}/inscripcion/constancia/{inscription_id}"

    cat_label = "Música" if category == "musica" else "Danza" if category == "danza" else category
    subcat_label = subcategory.replace("_", " ").replace("-", " ").title() if subcategory else "-"

    qr_png_bytes = b64.b64decode(qr_code_base64)

    qr_section_html = f'''
<!-- ==================== QR CODE ==================== -->
<tr><td style="padding:24px 32px 0;text-align:center">
  <div style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px">Código QR de Acreditación</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ffffff;border:2px solid #bbf7d0;border-radius:12px">
  <tr>
    <td style="padding:20px;text-align:center">
      <img src="cid:qr-precosquin-2027" alt="QR de acreditación" width="180" height="180" style="display:block;margin:0 auto;border-radius:8px" />
      <div style="font-size:12px;color:#166534;margin-top:12px;font-weight:600">Presentá este código QR en la acreditación</div>
    </td>
  </tr>
  </table>
</td></tr>'''

    html_body = f'''<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9">
<tr><td align="center" style="padding:32px 16px">
<table role="presentation" width="580" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08)">

<!-- HEADER -->
<tr><td style="background:linear-gradient(135deg,#166534,#22c55e);padding:28px 32px;text-align:center">
  <img src="{logo_url}" alt="Logo Pre Cosquín" width="48" height="48" style="display:block;margin:0 auto 12px;border-radius:8px;background:#ffffff;padding:4px" />
  <div style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:0.02em">¡Inscripción Aprobada!</div>
  <div style="font-size:11px;color:rgba(255,255,255,0.8);margin-top:4px">Pre-Cosquín 2027 · Puerto Pirámides</div>
</td></tr>

<!-- CONGRATS -->
<tr><td style="padding:32px 32px 0;text-align:center">
  <div style="font-size:18px;font-weight:700;color:#166534;margin-bottom:8px">Felicitaciones, {full_name}</div>
  <div style="font-size:13px;color:#15803d;line-height:1.6;max-width:420px;margin:0 auto">
    Tu inscripción <strong>{cat_label} › {subcat_label}</strong> fue aprobada por nuestro equipo. 
    A continuación encontrás tu código QR de acreditación que deberás presentar al llegar al momento de acreditarte.
  </div>
</td></tr>

<!-- REGISTRATION ID -->
<tr><td style="padding:24px 32px 0">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:10px">
  <tr>
    <td style="padding:16px;text-align:center">
      <div style="font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;font-weight:700;margin-bottom:4px">N° de Inscripción</div>
      <div style="font-size:13px;font-weight:700;color:#2563eb;font-family:'Courier New',monospace;word-break:break-all">{inscription_id}</div>
    </td>
  </tr>
  </table>
</td></tr>

{qr_section_html}

<!-- NEXT STEPS -->
<tr><td style="padding:24px 32px 0">
  <div style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:12px">Próximos Pasos</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px">
  <tr>
    <td style="padding:16px">
      <div style="font-size:12px;color:#1e3a8a;line-height:1.8">
        <strong>1.</strong> Guardá tu código QR (también lo tenés en tu constancia online)<br/>
        <strong>2.</strong> Presentalo en la mesa de acreditación<br/>
      </div>
    </td>
  </tr>
  </table>
</td></tr>

<!-- NOTE -->
<tr><td style="padding:20px 32px 0">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px">
  <tr>
    <td style="padding:14px 16px">
      <div style="font-size:11px;color:#475569;line-height:1.5">Si tenés consultas, respondé a este correo o escribinos a <a href="mailto:info@precosquinpiramides.com" style="color:#2563eb;text-decoration:none">info@precosquinpiramides.com</a></div>
    </td>
  </tr>
  </table>
</td></tr>

<!-- FOOTER -->
<tr><td style="padding:24px 32px 28px;text-align:center">
  <div style="font-size:10px;color:#cbd5e1">Precosquin · Puerto Pirámides, Chubut</div>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>'''

    email_sender = get_email_sender()
    msg = EmailMessage(
        to=email,
        subject="Pre-Cosquín — ¡Tu inscripción fue aprobada! Tu código QR de acreditación",
        html=html_body,
        reply_to="info@precosquinpiramides.com",
        attachments=[
            EmailAttachment(
                content_id="qr-precosquin-2027",
                filename="qr-acreditacion.png",
                content=qr_png_bytes,
                content_type="image/png",
            )
        ],
    )
    result = email_sender.send(msg)
    logger.info("approval_email_sent", to=email, status=result.status, message_id=result.message_id)