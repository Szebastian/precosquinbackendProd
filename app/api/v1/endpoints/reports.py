from fastapi import APIRouter, Query, Depends
from typing import Optional
from fastapi.responses import StreamingResponse
import csv
import io

from app.core.deps import get_current_user, require_role, CurrentUser
from app.db.session import get_supabase

router = APIRouter()


@router.get("/inscriptions")
async def get_inscriptions_report(
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    province: Optional[str] = None,
    experience: Optional[str] = None,
    current_user: CurrentUser = Depends(require_role("organizador", "admin")),
):
    db = get_supabase()
    query = db.table("inscriptions").select("*")

    if category:
        query = query.eq("category", category)
    if subcategory:
        query = query.eq("subcategory", subcategory)
    if province:
        query = query.eq("province", province)
    if experience:
        query = query.eq("experience_years", experience)

    result = query.execute()

    from collections import Counter
    by_category = Counter(item.get("category") for item in result.data)
    by_subcategory = Counter(item.get("subcategory") for item in result.data)
    by_province = Counter(item.get("province") for item in result.data)

    return {
        "total": len(result.data),
        "by_category": dict(by_category),
        "by_subcategory": dict(by_subcategory),
        "by_province": dict(by_province),
    }


@router.get("/inscriptions/export")
async def export_inscriptions_csv(
    category: Optional[str] = None,
    current_user: CurrentUser = Depends(require_role("organizador", "admin")),
):
    db = get_supabase()
    query = db.table("inscriptions").select("*")

    if category:
        query = query.eq("category", category)

    result = query.execute()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Nombre", "Email", "Teléfono", "Categoría", "Subcategoría", "Estado", "Fecha"])

    for item in result.data:
        writer.writerow([
            item.get("id"),
            item.get("full_name"),
            item.get("email"),
            item.get("phone"),
            item.get("category"),
            item.get("subcategory"),
            item.get("status"),
            item.get("created_at"),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=inscripciones_{category or 'todas'}.csv"},
    )


@router.get("/engagement")
async def get_engagement_report(
    category: Optional[str] = None,
    current_user: CurrentUser = Depends(require_role("organizador", "admin")),
):
    db = get_supabase()

    views = db.table("analytics_events").select("id", count="exact").eq("event_type", "jury_profile_view").execute()
    downloads = db.table("analytics_events").select("id", count="exact").eq("event_type", "rider_download").execute()
    signatures = db.table("analytics_events").select("id", count="exact").eq("event_type", "contract_signed").execute()

    return {
        "jury_views": views.count or 0,
        "rider_downloads": downloads.count or 0,
        "contract_signatures": signatures.count or 0,
    }