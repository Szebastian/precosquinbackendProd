import structlog
from fastapi import APIRouter, HTTPException, status, Query, UploadFile, File, Depends
from pydantic import BaseModel, Field
from typing import Optional, List

from app.core.deps import require_role, CurrentUser, get_db, get_current_user
from app.core.constants import UserRole
from app.core.config import settings
from app.api.v1.endpoints.storage import _ensure_bucket

logger = structlog.get_logger(__name__)
router = APIRouter()

TICKET_PRICE = 30000

class SorteoCreate(BaseModel):
    ticket_option: str = Field(default="1", pattern=r"^1$")
    full_name: str = Field(..., min_length=1)
    whatsapp: str = Field(..., min_length=1)
    email: str = Field(..., min_length=1)
    city: str = Field(..., min_length=1)
    comprobante_numero: Optional[str] = None

class SorteoResponse(BaseModel):
    id: str
    ticket_option: str
    full_name: str
    whatsapp: str
    email: str
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
        logger.error("sorteo_upload_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Error subiendo comprobante")

    public_url = db.storage.from_("sorteo_avistaje").get_public_url(path)

    db.table("sorteo_avistaje").update({"comprobante_url": public_url}).eq("id", sorteo_id).execute()

    return {"url": public_url, "message": "Comprobante subido correctamente"}

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

@router.patch("/{sorteo_id}/status")
async def update_sorteo_status(
    sorteo_id: str,
    new_status: str = Query(..., alias="status"),
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    if new_status not in ("pendiente_validacion", "validado", "rechazado"):
        raise HTTPException(status_code=400, detail="Estado inválido")

    db.table("sorteo_avistaje").update({"status": new_status}).eq("id", sorteo_id).execute()
    return {"message": "Estado actualizado"}
