"""
Acreditaciones endpoint — Festival Pre-Cosquín 2027
Handles QR/DNI check-in, accreditation, participant listing, stats, and audit log.
"""
import structlog
from fastapi import APIRouter, HTTPException, status, Query, Depends
from pydantic import BaseModel
from typing import Optional, List

from app.core.deps import get_current_user, require_role, CurrentUser, get_db
from app.core.constants import UserRole
from app.core.qr import decrypt_qr_payload

logger = structlog.get_logger(__name__)

router = APIRouter()


# ── Request / Response Models ──────────────────────────────────────

class QRCheckInRequest(BaseModel):
    qrCode: str

class DNICheckInRequest(BaseModel):
    dni: str

class AccrediteRequest(BaseModel):
    operator: str
    method: str  # 'qr' | 'dni' | 'manual'

class CheckInParticipant(BaseModel):
    id: str
    inscriptionId: str
    registrationNumber: str
    representativeName: str
    groupName: str
    category: str
    subcategory: str
    province: str
    locality: str
    dni: str
    phone: str
    email: str
    presentationTime: str
    presentationDay: str
    presentationOrder: int
    stage: str
    memberCount: int
    status: str
    photoUrl: Optional[str] = None
    accreditedAt: Optional[str] = None
    accreditedBy: Optional[str] = None
    createdAt: str
    updatedAt: str

class CheckInResult(BaseModel):
    type: str  # 'found' | 'not_found' | 'already_accredited' | 'not_approved'
    participant: Optional[CheckInParticipant] = None
    message: str


def _normalize_status(db_status: str) -> str:
    """Map DB status (PENDIENTE/ACREDITADO) to frontend status (pending/accredited)."""
    mapping = {"PENDIENTE": "pending", "ACREDITADO": "accredited", "BLOQUEADO": "blocked"}
    return mapping.get(db_status, db_status.lower() if db_status else "pending")


def _map_participant(row: dict, inscription: dict = None) -> CheckInParticipant:
    """Map a DB row + inscription data to CheckInParticipant."""
    ins = inscription or {}
    return CheckInParticipant(
        id=row.get("id", ""),
        inscriptionId=row.get("inscription_id", ""),
        registrationNumber=row.get("inscription_id", ""),
        representativeName=row.get("participant_name", ""),
        groupName=ins.get("stage_name") or ins.get("full_name", ""),
        category=row.get("category") or ins.get("category", ""),
        subcategory=row.get("subcategory") or ins.get("subcategory", ""),
        province=ins.get("province", ""),
        locality=ins.get("locality", ""),
        dni=row.get("dni") or ins.get("dni", ""),
        phone=ins.get("phone", ""),
        email=ins.get("email", ""),
        presentationTime="",
        presentationDay="",
        presentationOrder=0,
        stage="",
        memberCount=len(ins.get("members") or []),
        status=_normalize_status(row.get("status", "PENDIENTE")),
        photoUrl=None,
        accreditedAt=row.get("accredited_at"),
        accreditedBy=row.get("accredited_by"),
        createdAt=row.get("created_at", ""),
        updatedAt=row.get("updated_at", ""),
    )


# ── Check-in by QR ────────────────────────────────────────────────

@router.post("/checkin/qr", response_model=CheckInResult)
async def checkin_by_qr(
    req: QRCheckInRequest,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR, UserRole.STAFF)),
    db=Depends(get_db),
):
    try:
        payload = decrypt_qr_payload(req.qrCode)
    except ValueError as e:
        logger.warning("qr_decrypt_failed", error=str(e), user_id=current_user.id)
        raise HTTPException(status_code=400, detail=str(e))

    inscription_id = payload.get("id")
    if not inscription_id:
        raise HTTPException(status_code=400, detail="QR no contiene ID de inscripción")

    # Look up the inscription
    try:
        ins_result = db.table("inscriptions").select("*").eq("id", inscription_id).execute()
    except Exception as e:
        logger.error("db_error", error=str(e))
        raise HTTPException(status_code=500, detail="Error al buscar inscripción")

    if not ins_result.data:
        return CheckInResult(type="not_found", message="Inscripción no encontrada")

    ins = ins_result.data[0]

    # Check status
    if ins.get("status") not in ("APROBADA", "PENDIENTE", "EN_REVISION"):
        return CheckInResult(type="not_approved", message=f"Estado no válido: {ins.get('status')}")

    # Check if already accredited
    try:
        existing = db.table("acreditaciones").select("id, status").eq("inscription_id", inscription_id).execute()
    except Exception as e:
        logger.error("db_error", error=str(e))
        raise HTTPException(status_code=500, detail="Error al verificar acreditación")

    if existing.data:
        acc = existing.data[0]
        if acc.get("status") == "ACREDITADO":
            return CheckInResult(type="already_accredited", message="Este participante ya fue acreditado")

        # Auto-accredit existing pending record
        from datetime import datetime
        try:
            db.table("acreditaciones").update({
                "status": "ACREDITADO",
                "accredited_at": datetime.utcnow().isoformat(),
                "accredited_by": str(current_user.id),
                "checkin_method": "qr",
            }).eq("id", acc["id"]).execute()
        except Exception as e:
            logger.error("db_update_error", error=str(e))

        # Update inscription status
        try:
            db.table("inscriptions").update({"status": "ACREDITADO"}).eq("id", inscription_id).execute()
        except Exception as e:
            logger.warning("inscription_status_update_failed", error=str(e))

        participant = _map_participant({**acc, "status": "ACREDITADO", "accredited_at": datetime.utcnow().isoformat()}, ins)
        return CheckInResult(type="found", participant=participant, message="Participante acreditado")

    # Create acreditacion record — auto-accredited
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    try:
        acc_result = db.table("acreditaciones").insert({
            "inscription_id": inscription_id,
            "participant_name": ins.get("full_name", ""),
            "dni": ins.get("dni"),
            "category": ins.get("category"),
            "subcategory": ins.get("subcategory"),
            "stage_name": ins.get("stage_name"),
            "status": "ACREDITADO",
            "accredited_at": now,
            "accredited_by": str(current_user.id),
            "checkin_method": "qr",
        }).execute()
    except Exception as e:
        logger.error("db_insert_error", error=str(e))
        raise HTTPException(status_code=500, detail="Error al crear acreditación")

    if not acc_result.data:
        raise HTTPException(status_code=500, detail="Error al crear acreditación")

    acc = acc_result.data[0]

    # Update inscription status
    try:
        db.table("inscriptions").update({"status": "ACREDITADO"}).eq("id", inscription_id).execute()
    except Exception as e:
        logger.warning("inscription_status_update_failed", error=str(e))

    participant = _map_participant(acc, ins)

    # Audit log
    try:
        db.table("acreditacion_audit").insert({
            "acreditacion_id": acc["id"],
            "action": "accredit",
            "performed_by": current_user.id,
            "details": {"method": "qr", "auto": True},
        }).execute()
    except Exception as e:
        logger.error("audit_log_error", error=str(e))

    return CheckInResult(type="found", participant=participant, message="Participante acreditado")


# ── Check-in by DNI ───────────────────────────────────────────────

@router.post("/checkin/dni", response_model=CheckInResult)
async def checkin_by_dni(
    req: DNICheckInRequest,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR, UserRole.STAFF)),
    db=Depends(get_db),
):
    dni_clean = req.dni.replace(".", "").replace("-", "").strip()

    try:
        ins_result = db.table("inscriptions").select("*").eq("dni", dni_clean).execute()
    except Exception as e:
        logger.error("db_error", error=str(e))
        raise HTTPException(status_code=500, detail="Error al buscar por DNI")

    if not ins_result.data:
        return CheckInResult(type="not_found", message=f"No se encontró inscripción con DNI {dni_clean}")

    ins = ins_result.data[0]

    if ins.get("status") not in ("APROBADA", "PENDIENTE", "EN_REVISION"):
        return CheckInResult(type="not_approved", message=f"Estado no válido: {ins.get('status')}")

    # Check if already accredited
    try:
        existing = db.table("acreditaciones").select("id, status").eq("inscription_id", ins["id"]).execute()
    except Exception as e:
        logger.error("db_error", error=str(e))
        raise HTTPException(status_code=500, detail="Error al verificar acreditación")

    if existing.data:
        acc = existing.data[0]
        if acc.get("status") == "ACREDITADO":
            return CheckInResult(type="already_accredited", message="Este participante ya fue acreditado")

        # Auto-accredit existing pending record
        from datetime import datetime
        try:
            db.table("acreditaciones").update({
                "status": "ACREDITADO",
                "accredited_at": datetime.utcnow().isoformat(),
                "accredited_by": str(current_user.id),
                "checkin_method": "dni",
            }).eq("id", acc["id"]).execute()
        except Exception as e:
            logger.error("db_update_error", error=str(e))

        # Update inscription status
        try:
            db.table("inscriptions").update({"status": "ACREDITADO"}).eq("id", ins["id"]).execute()
        except Exception as e:
            logger.warning("inscription_status_update_failed", error=str(e))

        participant = _map_participant({**acc, "status": "ACREDITADO", "accredited_at": datetime.utcnow().isoformat()}, ins)
        return CheckInResult(type="found", participant=participant, message="Participante acreditado")

    # Create acreditacion record — auto-accredited
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    try:
        acc_result = db.table("acreditaciones").insert({
            "inscription_id": ins["id"],
            "participant_name": ins.get("full_name", ""),
            "dni": ins.get("dni"),
            "category": ins.get("category"),
            "subcategory": ins.get("subcategory"),
            "stage_name": ins.get("stage_name"),
            "status": "ACREDITADO",
            "accredited_at": now,
            "accredited_by": str(current_user.id),
            "checkin_method": "dni",
        }).execute()
    except Exception as e:
        logger.error("db_insert_error", error=str(e))
        raise HTTPException(status_code=500, detail="Error al crear acreditación")

    if not acc_result.data:
        raise HTTPException(status_code=500, detail="Error al crear acreditación")

    acc = acc_result.data[0]

    # Update inscription status
    try:
        db.table("inscriptions").update({"status": "ACREDITADO"}).eq("id", ins["id"]).execute()
    except Exception as e:
        logger.warning("inscription_status_update_failed", error=str(e))

    participant = _map_participant(acc, ins)

    try:
        db.table("acreditacion_audit").insert({
            "acreditacion_id": acc["id"],
            "action": "accredit",
            "performed_by": current_user.id,
            "details": {"method": "dni", "auto": True},
        }).execute()
    except Exception as e:
        logger.error("audit_log_error", error=str(e))

    return CheckInResult(type="found", participant=participant, message="Participante acreditado")


# ── Accredit ──────────────────────────────────────────────────────

@router.patch("/{acreditacion_id}/accredit")
async def accredit_participant(
    acreditacion_id: str,
    req: AccrediteRequest,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    try:
        result = db.table("acreditaciones").select("id, status").eq("id", acreditacion_id).execute()
    except Exception as e:
        logger.error("db_error", error=str(e))
        raise HTTPException(status_code=500, detail="Error al buscar acreditación")

    if not result.data:
        raise HTTPException(status_code=404, detail="Acreditación no encontrada")

    acc = result.data[0]
    if acc.get("status") == "ACREDITADO":
        return {"message": "Ya estaba acreditado", "id": acreditacion_id, "already": True}

    try:
        db.table("acreditaciones").update({
            "status": "ACREDITADO",
            "accredited_at": "now()",
            "accredited_by": current_user.id,
        }).eq("id", acreditacion_id).execute()
    except Exception as e:
        logger.error("db_update_error", error=str(e))
        raise HTTPException(status_code=500, detail="Error al acreditar")

    # Audit log
    try:
        db.table("acreditacion_audit").insert({
            "acreditacion_id": acreditacion_id,
            "action": "accredit",
            "performed_by": current_user.id,
            "details": {"method": req.method, "operator": req.operator},
        }).execute()
    except Exception as e:
        logger.error("audit_log_error", error=str(e))

    logger.info("participant_accredited", acreditacion_id=acreditacion_id, user_id=current_user.id)

    return {"message": "Participante acreditado correctamente", "id": acreditacion_id}


# ── List Participants ─────────────────────────────────────────────

@router.get("/")
async def list_participants(
    search: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    category: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    query = db.table("acreditaciones").select("*")

    if status_filter:
        query = query.eq("status", status_filter)
    if category:
        query = query.eq("category", category)
    if search:
        query = query.or_(f"participant_name.ilike.%{search}%,dni.ilike.%{search}%")

    try:
        count_result = query.execute()
        total = len(count_result.data) if count_result.data else 0

        result = query.order("created_at", desc=True).range(
            (page - 1) * page_size,
            page * page_size - 1
        ).execute()
    except Exception as e:
        logger.error("db_error", error=str(e))
        raise HTTPException(status_code=500, detail="Error al listar participantes")

    participants = [_map_participant(row) for row in (result.data or [])]

    return {
        "data": [p.model_dump() for p in participants],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ── Stats ─────────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(
    current_user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    try:
        all_result = db.table("acreditaciones").select("status").execute()
    except Exception as e:
        logger.error("db_error", error=str(e))
        raise HTTPException(status_code=500, detail="Error al obtener estadísticas")

    rows = all_result.data or []
    total = len(rows)
    accredited = sum(1 for r in rows if r.get("status") == "ACREDITADO")
    pending = sum(1 for r in rows if r.get("status") == "PENDIENTE")
    rejected = sum(1 for r in rows if r.get("status") == "RECHAZADO")

    return {
        "pendingCount": pending,
        "accreditedTodayCount": accredited,
        "absentCount": rejected,
        "lateCount": 0,
        "totalParticipants": total,
    }


# ── Audit Log ─────────────────────────────────────────────────────

@router.get("/audit-log")
async def get_audit_log(
    participantId: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    query = db.table("acreditacion_audit").select("*")

    if participantId:
        query = query.eq("acreditacion_id", participantId)

    try:
        count_result = query.execute()
        total = len(count_result.data) if count_result.data else 0

        result = query.order("created_at", desc=True).range(
            (page - 1) * page_size,
            page * page_size - 1
        ).execute()
    except Exception as e:
        logger.error("db_error", error=str(e))
        raise HTTPException(status_code=500, detail="Error al obtener audit log")

    entries = []
    for row in (result.data or []):
        entries.append({
            "id": row.get("id", ""),
            "participantId": row.get("acreditacion_id", ""),
            "participantName": "",
            "groupName": "",
            "dni": "",
            "operator": row.get("performed_by", ""),
            "method": (row.get("details") or {}).get("method", "manual"),
            "timestamp": row.get("created_at", ""),
        })

    return {"data": entries, "total": total}
