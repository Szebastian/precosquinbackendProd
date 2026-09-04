import structlog
from fastapi import APIRouter, HTTPException, status, Query, Depends
from pydantic import BaseModel, Field
from typing import Optional, List

from app.core.deps import require_role, CurrentUser, get_db
from app.core.constants import UserRole

logger = structlog.get_logger(__name__)
router = APIRouter()


class PartnerCreate(BaseModel):
    name: str = Field(..., min_length=1)
    logo_url: str = Field(..., min_length=1)
    link_url: Optional[str] = None
    category: str = Field(default="colaborador", pattern=r"^(sponsor|colaborador)$")
    order: int = Field(default=0)
    is_active: bool = Field(default=True)


class PartnerUpdate(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
    link_url: Optional[str] = None
    category: Optional[str] = Field(default=None, pattern=r"^(sponsor|colaborador)$")
    order: Optional[int] = None
    is_active: Optional[bool] = None


class PartnerResponse(BaseModel):
    id: str
    name: str
    logo_url: str
    link_url: Optional[str] = None
    category: str
    order: int
    is_active: bool
    created_at: str
    updated_at: str


class PartnerListResponse(BaseModel):
    data: List[PartnerResponse]
    total: int


@router.get("/", response_model=PartnerListResponse)
async def list_partners(
    category: Optional[str] = Query(None, pattern=r"^(sponsor|colaborador)$"),
    include_inactive: bool = Query(False),
    db=Depends(get_db),
):
    """List partners. Public endpoint — only active by default, admin can include inactive."""
    query = db.table("partners").select("*", count="exact")
    if not include_inactive:
        query = query.eq("is_active", True)
    if category:
        query = query.eq("category", category)
    result = query.order("order").execute()
    return PartnerListResponse(
        data=[PartnerResponse(**item) for item in (result.data or [])],
        total=result.count or 0,
    )


@router.get("/all")
async def list_all_partners(
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    """Admin: list all partners including inactive."""
    result = db.table("partners").select("*", count="exact").order("category").order("order").execute()
    return {"data": result.data or [], "total": result.count or 0}


@router.post("/", response_model=PartnerResponse, status_code=status.HTTP_201_CREATED)
async def create_partner(
    payload: PartnerCreate,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    row = {
        "name": payload.name,
        "logo_url": payload.logo_url,
        "link_url": payload.link_url,
        "category": payload.category,
        "order": payload.order,
        "is_active": payload.is_active,
    }
    res = db.table("partners").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Error al crear partner")
    return PartnerResponse(**res.data[0])


@router.put("/{partner_id}", response_model=PartnerResponse)
async def update_partner(
    partner_id: str,
    payload: PartnerUpdate,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="Sin cambios para guardar")
    update_data["updated_at"] = "now()"
    res = db.table("partners").update(update_data).eq("id", partner_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Partner no encontrado")
    return PartnerResponse(**res.data[0])


@router.delete("/{partner_id}")
async def delete_partner(
    partner_id: str,
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    db.table("partners").delete().eq("id", partner_id).execute()
    return {"message": "Partner eliminado"}


@router.patch("/{partner_id}/reorder")
async def reorder_partner(
    partner_id: str,
    new_order: int = Query(..., alias="order"),
    current_user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.ORGANIZADOR)),
    db=Depends(get_db),
):
    db.table("partners").update({"order": new_order, "updated_at": "now()"}).eq("id", partner_id).execute()
    return {"message": "Orden actualizado"}
