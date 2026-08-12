import structlog
import json
import hashlib
from pathlib import Path
from fastapi import APIRouter, HTTPException, status, Query, Depends, UploadFile, File
from pydantic import BaseModel, EmailStr
from typing import Optional, List

from app.core.deps import require_role, CurrentUser, get_db
from app.core.constants import UserRole
from app.core.utils import exclude_none
from app.core.email import EmailMessage, get_email_sender
from app.db.session import get_supabase

logger = structlog.get_logger(__name__)

router = APIRouter()

STANDS_BUCKET = "stands"


class StandStatus(str):
    PENDING = "PENDIENTE"
    IN_REVIEW = "EN_REVISION"
    APPROVED = "APROBADO"
    REJECTED = "RECHAZADO"
    ASSIGNED = "ASIGNADO"
    CONFIRMED = "CONFIRMADO"
    CANCELLED = "CANCELADO"


# ─── Pydantic Schemas ───────────────────────────────────────────────────────

class StandPerson(BaseModel):
    full_name: str
    dni: str
    phone: str
    email: EmailStr
    locality: str
    province: str
    represents_company: str = "No"


class StandInfo(BaseModel):
    stand_type: str
    stand_name: str
    description: Optional[str] = None
    main_products: str
    instagram: Optional[str] = None
    website: Optional[str] = None


class StandDates(BaseModel):
    days: List[str]
    start_time: str
    end_time: str


class StandEquipment(BaseModel):
    space_size: str
    brings_structure: str
    elements: List[str]
    table_count: Optional[int] = None
    chair_count: Optional[int] = None


class StandElectricity(BaseModel):
    needs_electricity: str
    equipment: Optional[List[str]] = None
    power_watts: Optional[int] = None


class StandGastronomy(BaseModel):
    prepares_food: str
    food_types: Optional[List[str]] = None
    uses_gas: Optional[str] = None
    gas_details: Optional[dict] = None
    has_certification: Optional[str] = None
    certification_doc_url: Optional[str] = None


class CommercialData(BaseModel):
    commercial_modality: Optional[str] = None
    price_range: Optional[str] = None


class StandPersonnel(BaseModel):
    count: int
    names: Optional[List[dict]] = None


class StandLogistics(BaseModel):
    needs_vehicle: Optional[str] = None
    vehicle_details: Optional[dict] = None
    early_access: Optional[str] = None
    needs_help: Optional[str] = None


class StandDocs(BaseModel):
    dni_front_url: Optional[str] = None
    dni_back_url: Optional[str] = None
    cuit_url: Optional[str] = None
    logo_url: Optional[str] = None
    stand_photos: Optional[List[str]] = None
    social_links: Optional[str] = None


class StandObservation(BaseModel):
    observations: Optional[str] = None


class StandCreate(BaseModel):
    person: StandPerson
    info: StandInfo
    dates: StandDates
    equipment: StandEquipment
    electricity: StandElectricity
    gastronomy: Optional[StandGastronomy] = None
    commercial: Optional[CommercialData] = None
    personnel: Optional[StandPersonnel] = None
    logistics: Optional[StandLogistics] = None
    docs: Optional[StandDocs] = None
    observations: Optional[StandObservation] = None


class StandResponse(BaseModel):
    id: str
    status: str
    person: dict
    info: dict
    dates: dict
    equipment: dict
    electricity: dict
    gastronomy: Optional[dict] = None
    commercial: Optional[dict] = None
    personnel: Optional[dict] = None
    logistics: Optional[dict] = None
    docs: Optional[dict] = None
    observations: Optional[str] = None
    stand_number: Optional[str] = None
    location_sector: Optional[str] = None
    location_size: Optional[str] = None
    admin_notes: Optional[str] = None
    created_at: str
    updated_at: str
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None


class StandListResponse(BaseModel):
    data: List[StandResponse]
    total: int
    page: int
    page_size: int


class StatusUpdate(BaseModel):
    status: str
    reason: Optional[str] = None


class LocationAssignment(BaseModel):
    stand_number: Optional[str] = None
    location_sector: Optional[str] = None
    location_size: Optional[str] = None
    admin_notes: Optional[str] = None


class StandListResponse(BaseModel):
    data: List[StandResponse]
    total: int
    page: int
    page_size: int


# ─── Helpers ────────────────────────────────────────────────────────────────

def _ensure_bucket(db, bucket: str):
    from app.api.v1.endpoints.storage import PUBLIC_BUCKETS
    try:
        db.storage.create_bucket(bucket, {"public": True})
    except Exception:
        try:
            db.storage.update_bucket(bucket, {"public": True})
        except Exception:
            pass


def _get_public_url(db, bucket: str, filename: str) -> str:
    _ensure_bucket(db, bucket)
    return db.storage.from_(bucket).get_public_url(filename)


def _upload_file(db, bucket: str, filename: str, content: bytes, content_type: str) -> str:
    _ensure_bucket(db, bucket)
    db.storage.from_(bucket).upload(
        filename, content,
        file_options={"content-type": content_type, "upsert": "true"}
    )
    return _get_public_url(db, bucket, filename)


def _db_row_to_response(row: dict) -> dict:
    def safe_parse(val):
        if val is None:
            return None
        if isinstance(val, str):
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return val
        return val

    return {
        "id": row["id"],
        "status": row.get("status", StandStatus.PENDING),
        "person": safe_parse(row.get("person")),
        "info": safe_parse(row.get("info")),
        "dates": safe_parse(row.get("dates")),
        "equipment": safe_parse(row.get("equipment")),
        "electricity": safe_parse(row.get("electricity")),
        "gastronomy": safe_parse(row.get("gastronomy")),
        "commercial": safe_parse(row.get("commercial")),
        "personnel": safe_parse(row.get("personnel")),
        "logistics": safe_parse(row.get("logistics")),
        "docs": safe_parse(row.get("docs")),
        "observations": row.get("observations"),
        "stand_number": row.get("stand_number"),
        "location_sector": row.get("location_sector"),
        "location_size": row.get("location_size"),
        "admin_notes": row.get("admin_notes"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "approved_by": row.get("approved_by"),
        "approved_at": row.get("approved_at"),
    }


def _send_status_email(db, stand: dict, new_status: str, reason: Optional[str] = None):
    try:
        sender = get_email_sender()
        person = stand.get("person", {}) if isinstance(stand.get("person"), dict) else {}
        email = person.get("email")
        if not email:
            return

        info = stand.get("info", {}) if isinstance(stand.get("info"), dict) else {}
        stand_name = info.get("stand_name", "tu stand")

        status_messages = {
            StandStatus.APPROVED: (
                f"Tu solicitud de stand <strong>{stand_name}</strong> ha sido <strong>APROBADA</strong>.",
            ),
            StandStatus.REJECTED: (
                f"Tu solicitud de stand <strong>{stand_name}</strong> ha sido <strong>RECHAZADA</strong>.",
            ),
            StandStatus.ASSIGNED: (
                f"Tu stand <strong>{stand_name}</strong> ha sido <strong>ASIGNADO</strong>.",
            ),
            StandStatus.CONFIRMED: (
                f"Tu stand <strong>{stand_name}</strong> está ahora <strong>CONFIRMADO</strong>.",
            ),
        }

        if new_status in status_messages:
            title, _ = status_messages[new_status]
            html = f"""
            <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px;">
              <h2 style="color:#1e3a8a;">Actualización de solicitud de stand</h2>
              <p>{title}</p>
              {f'<p><strong>Motivo:</strong> {reason}</p>' if reason else ''}
              <p>Podés consultar elestado de tu solicitud ingresando al <a href="https://precosquinpuertopiramides.com.ar">sitio web</a>.</p>
            </div>
            """
            email_msg = EmailMessage(
                to=email,
                subject=f"Pre-Cosquín — Actualización de stand: {stand_name}",
                html=html,
            )
            sender.send(email_msg)
    except Exception as e:
        logger.warning("stand_status_email_failed", error=str(e), stand_id=stand.get("id"))


# ─── Public Endpoints ───────────────────────────────────────────────────────

@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_stand(stand: StandCreate, db=Depends(get_db)):
    try:
        item_data = {
            "person": json.dumps(stand.person.model_dump()),
            "info": json.dumps(stand.info.model_dump()),
            "dates": json.dumps(stand.dates.model_dump()),
            "equipment": json.dumps(stand.equipment.model_dump()),
            "electricity": json.dumps(stand.electricity.model_dump()),
            "status": StandStatus.PENDING,
        }
        if stand.gastronomy:
            item_data["gastronomy"] = json.dumps(stand.gastronomy.model_dump())
        if stand.commercial:
            item_data["commercial"] = json.dumps(stand.commercial.model_dump())
        if stand.personnel:
            item_data["personnel"] = json.dumps(stand.personnel.model_dump())
        if stand.logistics:
            item_data["logistics"] = json.dumps(stand.logistics.model_dump())
        if stand.docs:
            item_data["docs"] = json.dumps(stand.docs.model_dump())
        if stand.observations:
            item_data["observations"] = stand.observations.observations

        result = db.table("stands").insert(item_data).execute()
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al crear la solicitud de stand",
            )
        return {"id": result.data[0]["id"], "message": "Solicitud recibida"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("stand_create_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear la solicitud de stand",
        )


@router.get("/{stand_id}", response_model=StandResponse)
async def get_stand(stand_id: str, db=Depends(get_db)):
    result = db.table("stands").select("*").eq("id", stand_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Stand no encontrado")
    return _db_row_to_response(result.data)


@router.get("/", response_model=StandListResponse)
async def list_stands(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN, UserRole.STAFF, UserRole.GESTOR_STANDS)),
    db=Depends(get_db),
):
    query = db.table("stands").select("*", count="exact")

    if status_filter:
        query = query.eq("status", status_filter)
    if search:
        query = query.or_(f"person.ilike.*{search}*,info.ilike.*{search}*")

    offset = (page - 1) * page_size
    result = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()

    return StandListResponse(
        data=[_db_row_to_response(item) for item in result.data],
        total=result.count or 0,
        page=page,
        page_size=page_size,
    )


@router.patch("/{stand_id}/status")
async def update_stand_status(
    stand_id: str,
    update: StatusUpdate,
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN, UserRole.GESTOR_STANDS)),
    db=Depends(get_db),
):
    result = db.table("stands").select("*").eq("id", stand_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Stand no encontrado")

    db_result = db.table("stands").update({
        "status": update.status,
        "admin_notes": update.reason,
        "approved_by": current_user.email if update.status in (StandStatus.APPROVED, StandStatus.ASSIGNED, StandStatus.CONFIRMED) else None,
        "approved_at": "now()" if update.status in (StandStatus.APPROVED, StandStatus.ASSIGNED, StandStatus.CONFIRMED) else None,
    }).eq("id", stand_id).execute()

    if not db_result.data:
        raise HTTPException(status_code=404, detail="Stand no encontrado")

    _send_status_email(db, db_result.data[0], update.status, update.reason)

    return {"message": "Estado actualizado"}


@router.patch("/{stand_id}/location")
async def assign_stand_location(
    stand_id: str,
    assignment: LocationAssignment,
    current_user: CurrentUser = Depends(require_role(UserRole.ORGANIZADOR, UserRole.ADMIN, UserRole.GESTOR_STANDS)),
    db=Depends(get_db),
):
    result = db.table("stands").select("id").eq("id", stand_id).single().execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Stand no encontrado")

    update_data = {k: v for k, v in assignment.model_dump().items() if v is not None}
    db.table("stands").update(update_data).eq("id", stand_id).execute()

    return {"message": "Ubicación asignada"}


@router.delete("/{stand_id}")
async def delete_stand(
    stand_id: str,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN)),
    db=Depends(get_db),
):
    result = db.table("stands").select("id").eq("id", stand_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Stand no encontrado")
    db.table("stands").delete().eq("id", stand_id).execute()
    return {"message": "Stand eliminado"}


@router.post("/{stand_id}/upload")
async def upload_stand_document(
    stand_id: str,
    file: UploadFile = File(...),
    doc_type: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(get_current_user),
    db=Depends(get_db),
):
    from app.core.config import settings
    if file.size and file.size > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Archivo excede {settings.MAX_FILE_SIZE_MB}MB")

    stand_result = db.table("stands").select("id").eq("id", stand_id).single().execute()
    if not stand_result.data:
        raise HTTPException(status_code=404, detail="Stand no encontrado")

    content = await file.read()
    file_hash = hashlib.md5(content).hexdigest()
    filename = f"{stand_id}_{doc_type or 'doc'}_{file_hash}{Path(file.filename).suffix}"

    url = _upload_file(db, STANDS_BUCKET, filename, content, file.content_type)

    return {"url": url, "message": "Archivo subido correctamente"}
