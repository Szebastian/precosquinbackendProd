from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta, timezone

from app.core.deps import get_current_user, CurrentUser
from app.db.session import get_supabase
from app.core.page_view_tracker import get_daily_views, get_hourly_views, get_daily_views_with_hours, record_view

router = APIRouter()


class CategoryBreakdown(BaseModel):
    name: str
    count: int
    percentage: float


class StatusBreakdown(BaseModel):
    status: str
    count: int


class PipelineStage(BaseModel):
    label: str
    count: int
    total: int
    percentage: float


class RecentInscription(BaseModel):
    id: str
    full_name: str
    stage_name: Optional[str] = None
    category: str
    subcategory: Optional[str] = None
    status: str
    created_at: str


class OrganizerDashboard(BaseModel):
    total_inscripciones: int
    inscripciones_pendientes: int
    inscripciones_aprobadas: int
    inscripciones_rechazadas: int
    inscripciones_en_evaluacion: int
    acreditaciones_acreditadas: int
    acreditaciones_total: int
    jurados_activos: int
    documents_uploaded: int

    pipeline: List[PipelineStage]
    by_category: List[CategoryBreakdown]
    by_status: List[StatusBreakdown]
    recent: List[RecentInscription]


def _count_where(db, table: str, filters: dict = None) -> int:
    q = db.table(table).select("id", count="exact")
    if filters:
        for col, val in filters.items():
            q = q.eq(col, val)
    result = q.execute()
    return result.count or 0


def _select_all(db, table: str, filters: dict = None, order_col: str = None, desc: bool = False, limit: int = None):
    q = db.table(table).select("*")
    if filters:
        for col, val in filters.items():
            q = q.eq(col, val)
    if order_col:
        q = q.order(order_col, desc=desc)
    if limit:
        q = q.limit(limit)
    return q.execute().data


@router.get("/stats", response_model=OrganizerDashboard)
async def get_dashboard_stats(
    current_user: CurrentUser = Depends(get_current_user),
):
    db = get_supabase()

    # --- Inscriptions ---
    total = _count_where(db, "inscriptions")
    pendientes = _count_where(db, "inscriptions", {"status": "PENDIENTE"})
    aprobadas = _count_where(db, "inscriptions", {"status": "APROBADA"})
    rechazadas = _count_where(db, "inscriptions", {"status": "RECHAZADA"})
    en_evaluacion = _count_where(db, "inscriptions", {"status": "EN_EVALUACION"})

    # --- Acreditaciones ---
    acreditadas = _count_where(db, "acreditaciones", {"status": "ACREDITADO"})
    acreditaciones_total = _count_where(db, "acreditaciones")

    # --- Jurados: count from profiles table ---
    jurados_activos = 0
    try:
        all_profiles = _select_all(db, "profiles")
        jurados_activos = sum(1 for p in all_profiles if p.get("role") == "jurado")
    except Exception:
        pass

    # --- Documents ---
    documents_uploaded = _count_where(db, "documents")

    # --- All inscriptions for breakdowns ---
    all_inscriptions = _select_all(db, "inscriptions", order_col="created_at", desc=True, limit=100)

    # Category breakdown
    cat_counts: dict = {}
    for ins in all_inscriptions:
        cat = (ins.get("category") or "Otro").capitalize()
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    by_category = [
        CategoryBreakdown(
            name=name,
            count=count,
            percentage=round(count / total * 100, 1) if total > 0 else 0,
        )
        for name, count in sorted(cat_counts.items(), key=lambda x: -x[1])
    ]

    # Status breakdown
    status_counts: dict = {}
    for ins in all_inscriptions:
        st = ins.get("status") or "DESCONOCIDO"
        status_counts[st] = status_counts.get(st, 0) + 1

    by_status = [
        StatusBreakdown(status=status, count=count)
        for status, count in sorted(status_counts.items(), key=lambda x: -x[1])
    ]

    # Pipeline: inscription flow
    pipeline = [
        PipelineStage(label="Inscripciones", count=total, total=total, percentage=100.0),
        PipelineStage(
            label="En Evaluación",
            count=en_evaluacion,
            total=total,
            percentage=round(en_evaluacion / total * 100, 1) if total > 0 else 0,
        ),
        PipelineStage(
            label="Aprobadas",
            count=aprobadas,
            total=total,
            percentage=round(aprobadas / total * 100, 1) if total > 0 else 0,
        ),
        PipelineStage(
            label="Acreditadas",
            count=acreditadas,
            total=total,
            percentage=round(acreditadas / total * 100, 1) if total > 0 else 0,
        ),
    ]

    # Recent inscriptions (last 5)
    recent = [
        RecentInscription(
            id=ins["id"],
            full_name=ins.get("full_name", ""),
            stage_name=ins.get("stage_name"),
            category=ins.get("category", ""),
            subcategory=ins.get("subcategory"),
            status=ins.get("status", ""),
            created_at=ins.get("created_at", ""),
        )
        for ins in all_inscriptions[:5]
    ]

    return OrganizerDashboard(
        total_inscripciones=total,
        inscripciones_pendientes=pendientes,
        inscripciones_aprobadas=aprobadas,
        inscripciones_rechazadas=rechazadas,
        inscripciones_en_evaluacion=en_evaluacion,
        acreditaciones_acreditadas=acreditadas,
        acreditaciones_total=acreditaciones_total,
        jurados_activos=jurados_activos,
        documents_uploaded=documents_uploaded,
        pipeline=pipeline,
        by_category=by_category,
        by_status=by_status,
        recent=recent,
    )


# --- Temporal Metrics ---

class DayMetric(BaseModel):
    date: str
    inscriptions: int
    page_views: int
    unique_visitors: int


class HourlyMetric(BaseModel):
    hour: int
    hour_label: str
    views: int
    unique_visitors: int
    pages: int


class TemporalWithHourly(BaseModel):
    date: str
    total_views: int
    unique_visitors: int
    hourly: List[HourlyMetric]


@router.get("/temporal", response_model=List[DayMetric])
async def get_temporal_metrics(
    days: int = Query(default=30, ge=1, le=90),
    current_user: CurrentUser = Depends(get_current_user),
):
    db = get_supabase()

    all_inscriptions = _select_all(db, "inscriptions", order_col="created_at", desc=False)
    ins_by_day: dict = {}
    for ins in all_inscriptions:
        created = ins.get("created_at", "")
        if created:
            day = created[:10]
            ins_by_day[day] = ins_by_day.get(day, 0) + 1

    pv_data = get_daily_views(days)
    pv_by_day = {item["date"]: item for item in pv_data}

    today = datetime.now(timezone.utc).date()
    result = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        pv = pv_by_day.get(d, {"total_views": 0, "unique_visitors": 0})
        result.append(DayMetric(
            date=d,
            inscriptions=ins_by_day.get(d, 0),
            page_views=pv.get("total_views", 0),
            unique_visitors=pv.get("unique_visitors", 0),
        ))
    return result


@router.get("/hourly", response_model=List[HourlyMetric])
async def get_hourly_metrics(
    date: Optional[str] = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
):
    return get_hourly_views(date)


@router.get("/temporal-hourly", response_model=List[TemporalWithHourly])
async def get_temporal_with_hourly(
    days: int = Query(default=7, ge=1, le=30),
    current_user: CurrentUser = Depends(get_current_user),
):
    return get_daily_views_with_hours(days)


class PageViewRequest(BaseModel):
    path: str
    visitor_id: str = "anon"


@router.post("/pageview")
async def record_page_view(req: PageViewRequest):
    record_view(req.path, req.visitor_id)
    return {"ok": True}
