from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.deps import get_current_user, CurrentUser
from app.db.session import get_supabase

router = APIRouter()


class DashboardStats(BaseModel):
    total_inscripciones: int
    inscripciones_pendientes: int
    inscripciones_aprobadas: int
    artistas_confirmados: int
    jurados_activos: int
    eventos_proximos: int
    incidencias_abiertas: int
    contratos_pendientes: int


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    current_user: CurrentUser = Depends(get_current_user),
):
    db = get_supabase()

    total = db.table("inscriptions").select("id", count="exact").execute()
    pendientes = db.table("inscriptions").select("id", count="exact").eq("status", "PENDIENTE").execute()
    aprobadas = db.table("inscriptions").select("id", count="exact").eq("status", "APROBADA").execute()

    return DashboardStats(
        total_inscripciones=total.count or 0,
        inscripciones_pendientes=pendientes.count or 0,
        inscripciones_aprobadas=aprobadas.count or 0,
        artistas_confirmados=aprobadas.count or 0,
        jurados_activos=8,
        eventos_proximos=3,
        incidencias_abiertas=2,
        contratos_pendientes=5,
    )