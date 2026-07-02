from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List
from pydantic import BaseModel

from app.core.deps import get_current_user, CurrentUser
from app.db.session import get_supabase

router = APIRouter()


class ArtistResponse(BaseModel):
    id: str
    full_name: str
    email: str
    phone: Optional[str]
    category: str
    subcategory: str
    status: str
    created_at: str


@router.get("/", response_model=List[ArtistResponse])
async def list_artists(
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    db = get_supabase()
    query = db.table("inscriptions").select("*")

    if category:
        query = query.eq("category", category)
    if subcategory:
        query = query.eq("subcategory", subcategory)
    if status:
        query = query.eq("status", status)
    if search:
        query = query.or_(f"full_name.ilike.%{search}%,email.ilike.%{search}%")

    result = query.order("created_at", desc=True).execute()
    return [ArtistResponse(**item) for item in result.data]


@router.get("/{artist_id}")
async def get_artist(artist_id: str, current_user: CurrentUser = Depends(get_current_user)):
    db = get_supabase()
    result = db.table("inscriptions").select("*").eq("id", artist_id).single().execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Artista no encontrado")

    return result.data


@router.get("/{artist_id}/documents")
async def get_artist_documents(artist_id: str, current_user: CurrentUser = Depends(get_current_user)):
    db = get_supabase()
    result = db.table("documents").select("*").eq("artist_id", artist_id).execute()
    return result.data


@router.patch("/{artist_id}/internal")
async def update_artist_internal(
    artist_id: str,
    internal_notes: Optional[str] = None,
    staff_observations: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    db = get_supabase()
    update_data = {}

    if internal_notes is not None:
        update_data["internal_notes"] = internal_notes
    if staff_observations is not None:
        update_data["staff_observations"] = staff_observations

    if not update_data:
        raise HTTPException(status_code=400, detail="No hay datos para actualizar")

    result = db.table("inscriptions").update(update_data).eq("id", artist_id).execute()
    return {"message": "Artista actualizado correctamente"}