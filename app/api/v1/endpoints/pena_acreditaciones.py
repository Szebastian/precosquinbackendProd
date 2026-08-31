import structlog
from fastapi import APIRouter, HTTPException, status, Query, Depends
from pydantic import BaseModel, Field
from typing import Optional, List

from app.core.deps import require_role, CurrentUser, get_db, get_current_user
from app.core.constants import UserRole

logger = structlog.get_logger(__name__)
router = APIRouter()

class AcompanianteIn(BaseModel):
    nombre: str = Field(..., min_length=1)
    dni: str = Field(..., min_length=1)
    rol: str = Field(..., min_length=1)

class PenaAcreditacionCreate(BaseModel):
    nombreGrupo: str = Field(..., alias="nombre_grupo", min_length=1)
    nombreResponsable: str = Field(..., alias="nombre_responsable", min_length=1)
    dniResponsable: str = Field(..., alias="dni_responsable", min_length=1)
    telefono: str = Field(..., min_length=1)
    diaPresentacion: str = Field(..., alias="dia_presentacion")
    acompaniantes: List[AcompanianteIn] = Field(default_factory=list)

    class Config:
        populate_by_name = True

class PenaAcreditacionResponse(BaseModel):
    id: str
    nombre_grupo: str
    nombre_responsable: str
    dni_responsable: str
    telefono: str
    dia_presentacion: str
    acompaniantes: List[dict]
    status: str
    is_read: bool = False
    created_at: str
    updated_at: str

class PenaListResponse(BaseModel):
    data: List[PenaAcreditacionResponse]
    total: int
    unread: int
    page: int
    page_size: int

@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_pena_acreditacion(payload: PenaAcreditacionCreate, db=Depends(get_db)):
    try:
        row = {
            "nombre_grupo": payload.nombreGrupo,
            "nombre_responsable": payload.nombreResponsable,
            "dni_responsable": payload.dniResponsable,
            "telefono": payload.telefono,
            "dia_presentacion": payload.diaPresentacion,
            "acompaniantes": [a.model_dump() for a in payload.acompaniantes],
            "status": "PENDIENTE",
            "is_read": False,
        }
        res = db.table("pena_acreditaciones").insert(row).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Error al guardar acreditación")
        return {"id": res.data[0]["id"], "message": "Acreditación registrada"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("pena_create_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Error al guardar acreditación")

@router.get("/", response_model=PenaListResponse)
async def list_pena_acreditaciones(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    dia: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    is_read: Optional[bool] = Query(None),
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    try:
        q = db.table("pena_acreditaciones").select("*", count="exact")
        if dia:
            q = q.eq("dia_presentacion", dia)
        if status:
            q = q.eq("status", status)
        if is_read is not None:
            q = q.eq("is_read", is_read)
        if search:
            q = q.or_(f"nombre_grupo.ilike.*{search}*,nombre_responsable.ilike.*{search}*,dni_responsable.ilike.*{search}*")
        offset = (page - 1) * page_size
        res = q.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()

        unread_res = db.table("pena_acreditaciones").select("id", count="exact").eq("is_read", False).execute()

        data = []
        for r in (res.data or []):
            data.append(PenaAcreditacionResponse(
                id=r["id"],
                nombre_grupo=r["nombre_grupo"],
                nombre_responsable=r["nombre_responsable"],
                dni_responsable=r["dni_responsable"],
                telefono=r["telefono"],
                dia_presentacion=r["dia_presentacion"],
                acompaniantes=r.get("acompaniantes") or [],
                status=r.get("status", "PENDIENTE"),
                is_read=r.get("is_read", False),
                created_at=str(r.get("created_at") or ""),
                updated_at=str(r.get("updated_at") or ""),
            ))
        return PenaListResponse(
            data=data,
            total=res.count or 0,
            unread=unread_res.count or 0,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        msg = str(e).lower()
        if "does not exist" in msg or "relation" in msg or "pena_acreditaciones" in msg or "column" in msg:
            logger.warning("pena_table_not_exists", error=str(e))
            return PenaListResponse(data=[], total=0, unread=0, page=page, page_size=page_size)
        logger.error("pena_list_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Error al listar acreditaciones")

@router.get("/unread-count")
async def get_unread_count(
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    try:
        res = db.table("pena_acreditaciones").select("id", count="exact").eq("is_read", False).execute()
        return {"unread": res.count or 0}
    except Exception as e:
        msg = str(e).lower()
        if "does not exist" in msg or "relation" in msg or "column" in msg:
            return {"unread": 0}
        logger.error("pena_unread_count_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Error al contar no leídas")

@router.get("/{id}", response_model=PenaAcreditacionResponse)
async def get_pena_acreditacion(
    id: str,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    res = db.table("pena_acreditaciones").select("*").eq("id", id).single().execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Acreditación no encontrada")
    r = res.data
    return PenaAcreditacionResponse(
        id=r["id"],
        nombre_grupo=r["nombre_grupo"],
        nombre_responsable=r["nombre_responsable"],
        dni_responsable=r["dni_responsable"],
        telefono=r["telefono"],
        dia_presentacion=r["dia_presentacion"],
        acompaniantes=r.get("acompaniantes") or [],
        status=r.get("status", "PENDIENTE"),
        is_read=r.get("is_read", False),
        created_at=str(r.get("created_at") or ""),
        updated_at=str(r.get("updated_at") or ""),
    )


@router.put("/{id}", response_model=PenaAcreditacionResponse)
async def update_pena_acreditacion(
    id: str,
    payload: PenaAcreditacionCreate,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    existing = db.table("pena_acreditaciones").select("id").eq("id", id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Acreditación no encontrada")

    row = {
        "nombre_grupo": payload.nombreGrupo,
        "nombre_responsable": payload.nombreResponsable,
        "dni_responsable": payload.dniResponsable,
        "telefono": payload.telefono,
        "dia_presentacion": payload.diaPresentacion,
        "acompaniantes": [a.model_dump() for a in payload.acompaniantes],
    }
    res = db.table("pena_acreditaciones").update(row).eq("id", id).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Error al actualizar acreditación")

    r = res.data[0]
    return PenaAcreditacionResponse(
        id=r["id"],
        nombre_grupo=r["nombre_grupo"],
        nombre_responsable=r["nombre_responsable"],
        dni_responsable=r["dni_responsable"],
        telefono=r["telefono"],
        dia_presentacion=r["dia_presentacion"],
        acompaniantes=r.get("acompaniantes") or [],
        status=r.get("status", "PENDIENTE"),
        is_read=r.get("is_read", False),
        created_at=str(r.get("created_at") or ""),
        updated_at=str(r.get("updated_at") or ""),
    )


@router.patch("/{id}/read")
async def mark_as_read(
    id: str,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    existing = db.table("pena_acreditaciones").select("id").eq("id", id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Acreditación no encontrada")

    db.table("pena_acreditaciones").update({"is_read": True}).eq("id", id).execute()
    return {"message": "Marcada como leída"}


@router.patch("/read-all")
async def mark_all_as_read(
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    try:
        db.table("pena_acreditaciones").update({"is_read": True}).eq("is_read", False).execute()
        return {"message": "Todas marcadas como leídas"}
    except Exception as e:
        logger.error("pena_read_all_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Error al marcar como leídas")


@router.delete("/{id}")
async def delete_pena_acreditacion(
    id: str,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    existing = db.table("pena_acreditaciones").select("id").eq("id", id).single().execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Acreditación no encontrada")

    db.table("pena_acreditaciones").delete().eq("id", id).execute()
    return {"message": "Acreditación eliminada"}
